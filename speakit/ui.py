"""Tk-UI im Haupt-Thread: Overlay und Einstellungen."""
import logging
import os
import queue
import tkinter as tk
from tkinter import ttk

from . import autostart
from .audio import list_mics
from .config import CONTEXTS_PATH, save_env
from .hotkey import pretty
from .overlay import Overlay

MODES = {
    "Halten oder Tippen (beides)": "both",
    "Nur halten (Push-to-talk)": "hold",
    "Nur tippen (Start/Stopp)": "toggle",
}
LANGS = {"Deutsch": "de", "Englisch": "en", "Automatisch": ""}


class UI:
    def __init__(self, app):
        self.app = app
        self.q = queue.Queue()
        self.root = tk.Tk()
        self.root.withdraw()
        self.settings = None
        self.overlay = Overlay(self.root, app.rec)
        self.root.after(30, self._loop)

    def call(self, fn, *a):
        self.q.put((fn, a))

    def set_state(self, state, text="", hold_ms=0):
        self.call(self.overlay.set_state, state, text, hold_ms)

    def on_new_dictation(self):
        pass

    def run(self):
        self.root.mainloop()

    def quit(self):
        self.call(self.root.quit)

    def _loop(self):
        try:
            while True:
                fn, a = self.q.get_nowait()
                try:
                    fn(*a)
                except Exception:
                    logging.exception("UI-Aufruf")
        except queue.Empty:
            pass
        self.overlay.tick()
        self.root.after(33, self._loop)

    # ---- Einstellungen ----
    def open_settings(self):
        self.call(self._open_settings)

    def _open_settings(self):
        if self.settings and self.settings.winfo_exists():
            self.settings.lift()
            return
        cfg = self.app.cfg
        win = self.settings = tk.Toplevel(self.root)
        win.title("SpeakIt Einstellungen")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        pad = {"padx": 10, "pady": 4}
        frm = ttk.Frame(win, padding=12)
        frm.pack()

        def row(r, label):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", **pad)

        hotkey = list(cfg["hotkey"])
        row(0, "Aufnahme-Taste")
        hk_var = tk.StringVar(value=pretty(hotkey))
        hk_btn = ttk.Button(frm, textvariable=hk_var, width=28)
        hk_btn.grid(row=0, column=1, sticky="ew", **pad)

        def capture():
            hk_var.set("Taste(n) drücken, dann loslassen …")

            def done(keys):
                def apply():
                    hotkey[:] = keys
                    hk_var.set(pretty(keys))
                self.call(apply)

            self.app.hk.start_capture(done)

        hk_btn.config(command=capture)

        row(1, "Bedienung")
        mode_var = tk.StringVar(value=next(k for k, v in MODES.items() if v == cfg["mode"]))
        ttk.Combobox(frm, textvariable=mode_var, values=list(MODES), state="readonly", width=30).grid(row=1, column=1, **pad)

        row(2, "Sprache")
        lang_var = tk.StringVar(value=next((k for k, v in LANGS.items() if v == cfg["language"]), "Deutsch"))
        ttk.Combobox(frm, textvariable=lang_var, values=list(LANGS), state="readonly", width=30).grid(row=2, column=1, **pad)

        row(3, "Mikrofon")
        mic_var = tk.StringVar(value=cfg["mic"] or "Standard")
        try:
            mics = ["Standard"] + list_mics()
        except Exception:
            mics = ["Standard"]
        ttk.Combobox(frm, textvariable=mic_var, values=mics, state="readonly", width=30).grid(row=3, column=1, **pad)

        row(4, "STT-Anbieter")
        prov_var = tk.StringVar(value=cfg["stt_provider"])
        ttk.Combobox(frm, textvariable=prov_var, values=["groq", "openai"], state="readonly", width=30).grid(row=4, column=1, **pad)

        clean_var = tk.BooleanVar(value=cfg["cleanup"])
        snd_var = tk.BooleanVar(value=cfg["sounds"])
        auto_var = tk.BooleanVar(value=autostart.is_enabled())
        ttk.Checkbutton(frm, text="Textnachbearbeitung mit Claude Haiku", variable=clean_var).grid(row=5, column=1, sticky="w", **pad)
        ttk.Checkbutton(frm, text="Töne", variable=snd_var).grid(row=6, column=1, sticky="w", **pad)
        ttk.Checkbutton(frm, text="Mit Windows starten", variable=auto_var).grid(row=7, column=1, sticky="w", **pad)

        keys = {}
        for i, (label, env) in enumerate(
            [("Groq API-Key", "GROQ_API_KEY"), ("Anthropic API-Key", "ANTHROPIC_API_KEY"), ("OpenAI API-Key (optional)", "OPENAI_API_KEY")]
        ):
            row(8 + i, label)
            v = tk.StringVar(value=os.environ.get(env, ""))
            ttk.Entry(frm, textvariable=v, show="•", width=33).grid(row=8 + i, column=1, **pad)
            keys[env] = v

        def save():
            cfg.set(
                hotkey=hotkey, mode=MODES[mode_var.get()], language=LANGS[lang_var.get()],
                mic="" if mic_var.get() == "Standard" else mic_var.get(),
                stt_provider=prov_var.get(), cleanup=clean_var.get(), sounds=snd_var.get(),
            )
            save_env({k: v.get().strip() for k, v in keys.items()})
            if auto_var.get() != autostart.is_enabled():
                autostart.set_enabled(auto_var.get())
            try:
                self.app.hk.set_hotkey(hotkey)
            except ValueError:
                self.set_state("err", "Taste unbekannt", 2500)
            self.app.refresh_tray()
            win.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=11, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btns, text="Begriffsliste öffnen", command=lambda: os.startfile(CONTEXTS_PATH)).pack(side="left", padx=6)
        ttk.Button(btns, text="Speichern", command=save).pack(side="left", padx=6)
        ttk.Button(btns, text="Abbrechen", command=win.destroy).pack(side="left", padx=6)
