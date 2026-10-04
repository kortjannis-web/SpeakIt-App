import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pyperclip
import pystray
from PIL import Image, ImageDraw

from . import sounds
from .audio import Recorder, has_speech, to_wav
from .cleanup import clean
from .config import FAILED_DIR, LOG_PATH, Config, load_env
from .storage import Contexts, History, apply_replacements, llm_cost, stt_cost
from .hotkey import HotkeyManager, pretty
from .paste import active_window_title, paste_text
from .stt import SttError, transcribe
from .ui import UI

HALLUCINATIONS = {
    "untertitel der amara.org-community", "vielen dank fürs zuschauen",
    "untertitelung des zdf, 2020", "danke fürs zuschauen", "thanks for watching",
    "vielen dank", "tschüss", "ciao",
}


def _icon(color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 62, 62), fill=color)
    d.rounded_rectangle((24, 12, 40, 36), radius=8, fill="white")
    d.arc((18, 22, 46, 46), 0, 180, fill="white", width=3)
    d.line((32, 46, 32, 54), fill="white", width=3)
    d.line((24, 54, 40, 54), fill="white", width=3)
    return img


class App:
    def __init__(self):
        load_env()
        self.cfg = Config()
        self.contexts = Contexts()
        self.history = History()
        self.rec = Recorder()
        self.hk = HotkeyManager(self.on_press, self.on_release, self.cancel)
        self.hk.cancel_armed = lambda: self.recording
        self.ui = UI(self)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.lock = threading.Lock()
        self.recording = False
        self.press_started = False
        self.press_t = 0.0
        self.pending = 0
        self.last_text = ""
        self.tray = None

    # ---- Start ----
    def run(self, background=False):
        try:
            self.hk.set_hotkey(self.cfg["hotkey"])
        except ValueError:
            logging.error("Hotkey ungültig, nutze F9")
            self.cfg.set(hotkey=["f9"])
            self.hk.set_hotkey(["f9"])
        self.hk.start()
        self._start_tray()
        threading.Thread(target=self._watchdog, daemon=True).start()
        no_key = self.cfg["stt_provider"] == "groq" and not os.environ.get("GROQ_API_KEY")
        if no_key:
            self.ui.open_window("Einstellungen")
        elif not background:
            self.ui.open_window("Verlauf")
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
            last = now

    # ---- Tray ----
    def _start_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem(lambda _i: f"Taste: {pretty(self.cfg['hotkey'])}", None, enabled=False),
            pystray.MenuItem(
                "Textnachbearbeitung", self._toggle_cleanup,
                checked=lambda _i: self.cfg["cleanup"],
            ),
            pystray.MenuItem("SpeakIt öffnen", lambda: self.ui.open_window("Verlauf"), default=True),
            pystray.MenuItem("Einstellungen …", lambda: self.ui.open_settings()),
            pystray.MenuItem("Letzten Text kopieren", self._copy_last),
            pystray.MenuItem("Kontexte bearbeiten", lambda: self.ui.open_window("Kontexte")),
            pystray.MenuItem("Log öffnen", lambda: os.startfile(LOG_PATH)),
            pystray.MenuItem("Beenden", self._quit),
        )
        self.tray = pystray.Icon("SpeakIt", _icon("#52525b"), "SpeakIt", menu)
        self.tray.run_detached()

    def refresh_tray(self):
        if self.tray:
            self.tray.update_menu()

    def _tray_color(self, color):
        if self.tray:
            self.tray.icon = _icon(color)

    def _toggle_cleanup(self):
        self.cfg.set(cleanup=not self.cfg["cleanup"])

    def _copy_last(self):
        if self.last_text:
            pyperclip.copy(self.last_text)

    def uninstall(self):
        from . import installer
        installer.uninstall(self)

    def _quit(self):
        self.hk.stop()
        if self.tray:
            self.tray.stop()
        self.ui.quit()
        threading.Timer(1.0, lambda: os._exit(0)).start()

    # ---- Aufnahme-Logik ----
    def on_press(self):
        with self.lock:
            if self.recording:
                self.press_started = False
                self._stop()
                return
            if self._start():
                self.press_started = True
                self.press_t = time.time()

    def on_release(self):
        with self.lock:
            if not self.press_started:
                return
            self.press_started = False
            if not self.recording or self.cfg["mode"] == "toggle":
                return
            if time.time() - self.press_t >= self.cfg["hold_threshold"]:
                self._stop()
            elif self.cfg["mode"] == "hold":
                self.cancel(locked=True)

    def cancel(self, locked=False):
        def go():
            if not self.recording:
                return
            self.recording = False
            self.rec.stop()
            self._tray_color("#52525b")
            self.ui.set_state("idle")
            self._sound("stop")
        if locked:
            go()
        else:
            with self.lock:
                go()

    def _start(self):
        try:
            self.rec.start(self.cfg["mic"])
        except Exception as e:
            logging.exception("Mikrofon")
            self._error(f"Mikrofon: {str(e)[:40]}")
            return False
        self.recording = True
        self._sound("start")
        self._tray_color("#dc2626")
        self.ui.set_state("rec")
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
            self._tray_color("#52525b")
            self.ui.set_state("done", "Nichts gehört", 1200)
            return
        self.pending += 1
        self._tray_color("#d97706")
        eta = 1.5 + len(pcm) / 16000 * 0.05
        self.ui.set_state("busy", f"{eta:.1f}")
        self.pool.submit(self._process, pcm, title)

    # ---- Verarbeitung ----
    def _process(self, pcm, title):
        t0 = time.time()
        secs = len(pcm) / 16000
        try:
            wav = to_wav(pcm)
            raw = transcribe(
                wav, self.cfg["stt_provider"], self.cfg["language"], self.contexts.whisper_terms()
            )
            t1 = time.time()
            if not raw or raw.lower().strip(" .!?") in HALLUCINATIONS and secs < 4:
                self.ui.set_state("done", "Nichts erkannt", 1200)
                return
            text, t_in, t_out = raw, 0, 0
            if self.cfg["cleanup"]:
                text, t_in, t_out = clean(
                    raw, self.cfg["cleanup_model"], self.contexts.llm_context(), title
                )
            text = apply_replacements(text, self.contexts.active_repl())
            self.last_text = text
            paste_text(text, self.hk)
            cost = stt_cost(self.cfg["stt_provider"], secs) + llm_cost(t_in, t_out)
            self.history.add(raw, text, secs, t_in, t_out, cost)
            self.ui.call(self.ui.on_new_dictation)
            logging.info(
                "%.1fs Audio, STT %.1fs, gesamt %.1fs, %d Zeichen, Token %d/%d, %.4f $",
                secs, t1 - t0, time.time() - t0, len(text), t_in, t_out, cost,
            )
            if self.pending <= 1:
                self.ui.set_state("done", "Eingefügt", 700)
        except SttError as e:
            self._save_failed(pcm)
            self._error(str(e)[:60])
        except Exception as e:
            logging.exception("Verarbeitung")
            self._save_failed(pcm)
            self._error(f"Fehler: {str(e)[:50]}")
        finally:
            self.pending -= 1
            if self.pending <= 0 and not self.recording:
                self._tray_color("#52525b")

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

    def _sound(self, name):
        if self.cfg["sounds"]:
            sounds.play(name, self.cfg["sound_preset"])
