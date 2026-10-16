import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pyperclip
import pystray

from . import sounds
from .audio import Recorder, has_speech, to_wav
from .cleanup import process
from .precleanup import preclean
from .config import FAILED_DIR, LOG_PATH, Config, load_env
from .storage import Contexts, History, apply_replacements, llm_cost, stt_cost
from .hotkey import HotkeyManager, pretty
from .icon import drop_icon
from .paste import active_window_title, copy_selection, paste_text
from .stt import SttError, transcribe
from .ui import UI
from . import updater

HALLUCINATIONS = {
    "untertitel der amara.org-community", "vielen dank fürs zuschauen",
    "untertitelung des zdf, 2020", "danke fürs zuschauen", "thanks for watching",
    "vielen dank", "tschüss", "ciao",
}


IDLE, OFF = "#f59e0b", "#b8b2a4"
DOUBLE_TAP = 0.45  # nächster Druck innerhalb dieser Zeit = eine Stufe weiter (Feinschliff, dann Struktur)
LEVELS = ("raw", "clean", "structure")  # 1x, 2x, 3x tippen
DOT = {1: "#ef4444", 2: "#8b5cf6"}  # Punktfarbe in der Kapsel: rot = Feinschliff, violett = Struktur
REWRITE_DOT = "#3b82f6"  # blau = markierten Text umschreiben


def _icon(color):
    return drop_icon(64, color)


class App:
    def __init__(self):
        load_env()
        self.cfg = Config()
        self.contexts = Contexts()
        self.history = History()
        self.rec = Recorder()
        self.hk = HotkeyManager(self.on_press, self.on_release, self.cancel)
        self.hk.cancel_armed = lambda: self.recording
        # Zweite Taste: markierten Text per Sprachanweisung umschreiben (Esc fängt schon die erste ab)
        self.hk2 = HotkeyManager(lambda: self.on_press("rewrite"), lambda: self.on_release("rewrite"))
        self.hk2.paused = lambda: self.hk.capture is not None or self.hk.injecting
        self.ui = UI(self)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.lock = threading.Lock()
        self.recording = False
        self.press_started = False
        self.press_t = 0.0
        self.start_t = 0.0
        self.last_tap_t = 0.0
        self.taps = 0  # Modus "Halten": Zahl der kurzen Tipps direkt vor dem Halten
        self.tap_t = 0.0  # letzter Tipp während der laufenden Aufnahme
        self.level = 0  # 0 Rohtext, 1 Feinschliff, 2 Struktur (laufende Aufnahme)
        self.kind = "dictate"  # dictate | rewrite
        self.pending = 0
        self.last_text = ""
        self.tray = None
        self.hk.enabled = bool(self.cfg["enabled"])
        self.hk2.enabled = bool(self.cfg["enabled"]) and bool(self.cfg["rewrite_enabled"])
        self.ui.overlay.on_full = self._done_sound

    # ---- Start ----
    def run(self, background=False):
        try:
            self.hk.set_hotkey(self.cfg["hotkey"])
        except ValueError:
            logging.error("Hotkey ungültig, nutze F9")
            self.cfg.set(hotkey=["f9"])
            self.hk.set_hotkey(["f9"])
        self.hk.start()
        self._set_rewrite_hotkey(self.cfg["rewrite_hotkey"])
        self.hk2.start()
        self._start_tray()
        threading.Thread(target=self._watchdog, daemon=True).start()
        updater.start_background(on_ready=self.refresh_tray)
        updater.start_source_updates(on_ready=self.refresh_tray)
        no_key = self.cfg["stt_provider"] == "groq" and not os.environ.get("GROQ_API_KEY")
        if no_key:
            self.ui.open_window("Einstellungen")
        elif not background:
            self.ui.open_window("Verlauf")
        if not self.cfg["tutorial_done"] and (not background or no_key):
            self.ui.call(self.ui.win.open_tutorial)
        logging.info("SpeakIt läuft, Taste: %s", pretty(self.cfg["hotkey"]))
        self.ui.run()

    def _watchdog(self):
        """Nach Standby/Sperre kann Windows den Hook verlieren."""
        last = time.monotonic()
        while True:
            time.sleep(5)
            now = time.monotonic()
            if now - last > 20:
                self.hk.reinstall()
                self.hk2.reinstall()
            last = now

    # ---- Tray ----
    def _start_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("SpeakIt aktiv", lambda: self.set_enabled(not self.cfg["enabled"]),
                             checked=lambda _i: self.cfg["enabled"]),
            pystray.MenuItem(lambda _i: f"Taste: {pretty(self.cfg['hotkey'])}", None, enabled=False),
            pystray.MenuItem(
                "Textnachbearbeitung", self._toggle_cleanup,
                checked=lambda _i: self.cfg["cleanup"],
            ),
            pystray.MenuItem(
                lambda _i: f"Übersetzen ({self.cfg['translate_to'] or self.cfg.data.get('translate_last') or 'Englisch'})",
                self._toggle_translate, checked=lambda _i: bool(self.cfg["translate_to"]),
            ),
            pystray.MenuItem("SpeakIt öffnen", lambda: self.ui.open_window("Verlauf"), default=True),
            pystray.MenuItem("Einstellungen …", lambda: self.ui.open_settings()),
            pystray.MenuItem("Letzten Text kopieren", self._copy_last),
            pystray.MenuItem("Kontexte bearbeiten", lambda: self.ui.open_window("Kontexte")),
            pystray.MenuItem("Update installieren (Neustart)", lambda: updater.restart_now(self._quit),
                             visible=lambda _i: updater.pending()),
            pystray.MenuItem("Update aktivieren (Neustart)", lambda: updater.restart_source(self._quit),
                             visible=lambda _i: updater._source_ready),
            pystray.MenuItem("Log öffnen", lambda: os.startfile(LOG_PATH)),
            pystray.MenuItem("Beenden", self._quit),
        )
        self.tray = pystray.Icon("SpeakIt", _icon(self._idle()), "SpeakIt", menu)
        self.tray.run_detached()

    def refresh_tray(self):
        if self.tray:
            self.tray.update_menu()

    def _tray_color(self, color):
        if self.tray:
            self.tray.icon = _icon(color)

    def _idle(self):
        return IDLE if self.cfg["enabled"] else OFF

    def set_enabled(self, on: bool):
        """Globaler An/Aus-Schalter: aus = Taste wird nicht mehr abgefangen, nichts wird aufgenommen."""
        self.cfg.set(enabled=bool(on))
        self.hk.enabled = bool(on)
        self.hk2.enabled = bool(on) and bool(self.cfg["rewrite_enabled"])
        if not on:
            self.hk.reset_state()
            self.hk2.reset_state()
            self.cancel()
        self._tray_color(self._idle())
        self.refresh_tray()
        self.ui.call(self.ui.win.sync_enabled)

    def _toggle_cleanup(self):
        self.cfg.set(cleanup=not self.cfg["cleanup"])
        self.ui.call(self.ui.win.sync_enabled)

    def set_translate(self, lang: str):
        """"" = aus. Die zuletzt gewählte Sprache bleibt für das schnelle Wiedereinschalten gemerkt."""
        self.cfg.set(translate_to=lang, **({"translate_last": lang} if lang else {}))
        self.refresh_tray()
        self.ui.call(self.ui.win.sync_enabled)

    def _toggle_translate(self):
        self.set_translate("" if self.cfg["translate_to"] else (self.cfg.data.get("translate_last") or "Englisch"))

    def _set_rewrite_hotkey(self, names):
        try:
            self.hk2.set_hotkey(names)
        except ValueError:
            logging.error("Umschreiben-Taste ungültig, nutze Umschalt + F9")
            self.cfg.set(rewrite_hotkey=["shift", "f9"])
            self.hk2.set_hotkey(["shift", "f9"])

    def set_rewrite(self, enabled: bool, names=None):
        """Wirft ValueError bei unbekannter Taste (dann bleibt die alte)."""
        if names:
            self.hk2.set_hotkey(names)
            self.cfg.set(rewrite_hotkey=list(names))
        self.cfg.set(rewrite_enabled=bool(enabled))
        self.hk2.enabled = bool(enabled) and bool(self.cfg["enabled"])
        self.hk2.reset_state()

    def _copy_last(self):
        if self.last_text:
            pyperclip.copy(self.last_text)

    def uninstall(self):
        from . import installer
        installer.uninstall(self)

    def _quit(self):
        self.hk.stop()
        self.hk2.stop()
        if self.tray:
            self.tray.stop()
        self.ui.quit()
        threading.Timer(1.0, lambda: os._exit(0)).start()

    # ---- Aufnahme-Logik ----
    def _gesture(self):
        """Mehrfach-Tippen schaltet Stufen weiter, solange die Nachbearbeitung an ist."""
        return bool(self.cfg["cleanup"])

    def _base_level(self):
        return 1 if self.cfg["cleanup"] and self.cfg["clean_trigger"] == "always" else 0

    def _set_level(self, level):
        self.level = min(len(LEVELS) - 1, level)
        self.ui.set_state("dot", DOT.get(self.level, ""))

    def on_press(self, kind="dictate"):
        with self.lock:
            now = time.time()
            if self.recording:
                if (kind == self.kind == "dictate" and self._gesture() and self.level < len(LEVELS) - 1
                        and now - self.tap_t < DOUBLE_TAP):
                    self._set_level(self.level + 1)  # weiterer Tipp: Aufnahme läuft weiter, eine Stufe höher
                    self.tap_t = now
                    self.press_started = True
                    self.press_t = now
                    return
                self.press_started = False
                self._stop()
                return
            if self._start(kind):
                self.press_started = True
                self.press_t = self.start_t = self.tap_t = now
                if kind == "dictate" and self._gesture() and now - self.last_tap_t < DOUBLE_TAP:
                    self._set_level(self._base_level() + self.taps)  # Modus "Halten": tippen (2x), dann halten

    def on_release(self, kind="dictate"):
        with self.lock:
            if not self.press_started or kind != self.kind:
                return
            self.press_started = False
            if not self.recording or self.cfg["mode"] == "toggle":
                return
            if time.time() - self.press_t >= self.cfg["hold_threshold"]:
                self._stop()
            elif self.cfg["mode"] == "hold":
                now = time.time()
                if self.kind != "dictate":
                    self.cancel(locked=True)
                    return
                self.taps = self.taps + 1 if now - self.last_tap_t < DOUBLE_TAP else 1
                self.last_tap_t = now
                self.cancel(locked=True)

    def cancel(self, locked=False):
        def go():
            if not self.recording:
                return
            self.recording = False
            self.rec.stop()
            self._tray_color(self._idle())
            self.ui.set_state("idle")
            self._sound("stop")
        if locked:
            go()
        else:
            with self.lock:
                go()

    def _start(self, kind="dictate"):
        try:
            self.rec.start(self.cfg["mic"])
        except Exception as e:
            logging.exception("Mikrofon")
            self._error(f"Mikrofon: {str(e)[:40]}")
            return False
        self.recording = True
        self.kind = kind
        self.level = self._base_level() if kind == "dictate" else 0
        self._sound("start")
        self._tray_color("#ef4444")
        self.ui.set_state("rec")
        if kind == "rewrite":
            self.ui.set_state("dot", REWRITE_DOT)
        elif self.level:
            self.ui.set_state("dot", DOT[self.level])
        threading.Thread(target=self._max_guard, daemon=True).start()
        return True

    def _max_guard(self):
        while self.recording:
            if self.rec.seconds > self.cfg["max_seconds"]:
                with self.lock:
                    if self.recording:
                        self._stop()
                return
            time.sleep(0.5)

    def _stop(self):
        self.recording = False
        pcm = self.rec.stop()
        self._sound("stop")
        title = active_window_title()
        if not has_speech(pcm):
            self._tray_color(self._idle())
            self.ui.set_state("done", "Nichts gehört", 1200)
            return
        self.pending += 1
        self._tray_color("#fbbf24")
        secs_ = len(pcm) / 16000
        mode = "rewrite" if self.kind == "rewrite" else LEVELS[self.level]
        lang = self.cfg["translate_to"]
        self.taps = 0
        if mode == "structure":
            eta = 2.4 + secs_ * 0.05
        elif mode != "raw" or lang:
            eta = 1.6 + secs_ * 0.04
        else:
            eta = 0.8 + secs_ * 0.02
        self.ui.set_state("busy", f"{eta:.1f}")
        self.pool.submit(self._process, pcm, title, mode, lang)

    # ---- Verarbeitung ----
    def _process(self, pcm, title, mode, lang=""):
        t0 = time.time()
        secs = len(pcm) / 16000
        selection, clip, pasted = "", None, False
        try:
            if mode == "rewrite":
                selection, clip = copy_selection(self.hk)
                if not selection.strip():
                    self.ui.set_state("err", "Nichts markiert", 2200)
                    return
            wav = to_wav(pcm)
            raw = transcribe(
                wav, self.cfg["stt_provider"], self.cfg["language"], self.contexts.whisper_terms()
            )
            t1 = time.time()
            if not raw or raw.lower().strip(" .!?") in HALLUCINATIONS and secs < 4:
                self.ui.set_state("done", "Nichts erkannt", 1200)
                return
            text = preclean(raw)  # kostenlos, immer
            if mode != "rewrite":
                text = apply_replacements(text, self.contexts.active_repl())  # vorher, damit die KI richtige Namen sieht
            text, prov, t_in, t_out = process(
                mode, text, self.cfg, self.contexts.llm_context(), title, lang, selection
            )
            if mode != "rewrite":
                text = apply_replacements(text, self.contexts.active_repl())
            if mode == "rewrite" and not prov:
                self.ui.set_state("err", "Umschreiben fehlgeschlagen", 2500)
                return
            self.last_text = text
            ai_missing = mode == "structure" and not prov
            if self.pending <= 1 and not ai_missing:  # Kapsel sofort füllen und schließen, Einfügen läuft parallel
                self.ui.set_state("done", "Eingefügt", 700)
            paste_text(text, self.hk, restore=clip if mode == "rewrite" else None)
            pasted = True
            if ai_missing:
                self.ui.set_state("err", "KI nicht erreichbar, Rohtext", 3000)
            cost = stt_cost(self.cfg["stt_provider"], secs) + llm_cost(t_in, t_out, prov)
            stored = (mode if mode != "raw" or not prov else "clean") if prov else "raw"
            if prov and lang:
                stored += f"+{lang}"
            raw_store = f"{raw}\n\n[Markierung]\n{selection}" if mode == "rewrite" else raw
            self.history.add(raw_store, text, secs, t_in, t_out, cost, mode=stored)
            self.ui.call(self.ui.on_new_dictation)
            logging.info(
                "%s %.1fs Audio, STT %.1fs, gesamt %.1fs, %d Zeichen, %s Token %d/%d, %.4f $",
                stored, secs, t1 - t0, time.time() - t0, len(text), prov or "-", t_in, t_out, cost,
            )
        except SttError as e:
            self._save_failed(pcm)
            self._error(str(e)[:60])
        except Exception as e:
            logging.exception("Verarbeitung")
            self._save_failed(pcm)
            self._error(f"Fehler: {str(e)[:50]}")
        finally:
            if mode == "rewrite" and clip is not None and not pasted:
                try:  # Markierung lag noch in der Zwischenablage: alten Inhalt zurück
                    pyperclip.copy(clip)
                except Exception:
                    pass
            self.pending -= 1
            if self.pending <= 0 and not self.recording:
                self._tray_color(self._idle())

    def _save_failed(self, pcm):
        try:
            FAILED_DIR.mkdir(exist_ok=True)
            (FAILED_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}.wav").write_bytes(to_wav(pcm))
        except Exception:
            pass

    def _error(self, msg):
        logging.error(msg)
        self._sound("error")
        self.ui.set_state("err", msg, 3500)

    def _done_sound(self):
        if self.cfg["done_sound"]:
            sounds.plop()

    def _sound(self, name):
        if self.cfg["sounds"]:
            sounds.play(name, self.cfg["sound_preset"])
