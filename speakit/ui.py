"""Tk-UI: Overlay (Pille unten mittig) und Einstellungsfenster. Laeuft im Haupt-Thread."""
import collections
import ctypes
import os
import queue
import tkinter as tk
from tkinter import ttk

from . import autostart
from .audio import list_mics
from .config import CONTEXTS_PATH, save_env
from .hotkey import pretty

KEY = "#ff00ff"  # transparente Farbe
BG = "#18181b"
RED, GREEN, AMBER, FG = "#ef4444", "#22c55e", "#f59e0b", "#f4f4f5"
W, H = 260, 46

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
        self.state = "idle"
        self.text = ""
        self.tick = 0
        self.levels = collections.deque([0.0] * 22, maxlen=22)
        self.hide_at = 0
        self.settings = None
        self._build_overlay()
        self.root.after(30, self._loop)

    # ---- Thread-sicherer Zugriff ----
    def call(self, fn, *a):
        self.q.put((fn, a))

    def set_state(self, state, text="", hold_ms=0):
        self.call(self._set_state, state, text, hold_ms)

    def on_new_dictation(self):
        pass

    def run(self):
        self.root.mainloop()

    def quit(self):
        self.call(self.root.quit)

    # ---- Overlay ----
    def _build_overlay(self):
        self.ov = tk.Toplevel(self.root)
        self.ov.overrideredirect(True)
        self.ov.attributes("-topmost", True)
        self.ov.configure(bg=KEY)
        self.ov.attributes("-transparentcolor", KEY)
        sw, sh = self.ov.winfo_screenwidth(), self.ov.winfo_screenheight()
        self.ov.geometry(f"{W}x{H}+{(sw - W) // 2}+{sh - 120}")
        self.cv = tk.Canvas(self.ov, width=W, height=H, bg=KEY, highlightthickness=0)
        self.cv.pack()
        self.ov.update_idletasks()
        try:  # nie den Fokus klauen, klick-durchlaessig
            u = ctypes.windll.user32
            hwnd = u.GetParent(self.ov.winfo_id()) or self.ov.winfo_id()
            ex = u.GetWindowLongW(hwnd, -20)
            u.SetWindowLongW(hwnd, -20, ex | 0x08000000 | 0x80 | 0x20)
        except Exception:
            pass
        self.ov.withdraw()

    def _set_state(self, state, text, hold_ms):
        self.state, self.text = state, text
        if state == "idle":
            self.ov.withdraw()
            return
        self.hide_at = self.tick + hold_ms // 33 if hold_ms else 0
        if state == "rec":
            self.levels.extend([0.0] * self.levels.maxlen)
        self.ov.deiconify()
        self.ov.attributes("-topmost", True)

    def _pill(self):
        c = self.cv
        c.delete("all")
        r = H // 2
        c.create_oval(0, 0, H, H, fill=BG, outline=BG)
        c.create_oval(W - H, 0, W, H, fill=BG, outline=BG)
        c.create_rectangle(r, 0, W - r, H, fill=BG, outline=BG)

    def _draw(self):
        self._pill()
        c, t = self.cv, self.tick
        cy = H // 2
        if self.state == "rec":
            pulse = 0.6 + 0.4 * abs(((t % 30) / 15) - 1)
            rr = int(6 * pulse) + 2
            c.create_oval(22 - rr, cy - rr, 22 + rr, cy + rr, fill=RED, outline=RED)
            lv = self.app.rec.level
            if t % 2 == 0:
                self.levels.append(lv)
            n = len(self.levels)
            for i, v in enumerate(self.levels):
                h = 3 + v * 26
                x = 44 + i * 9
                c.create_rectangle(x, cy - h / 2, x + 5, cy + h / 2, fill=FG, outline=FG)
        elif self.state == "busy":
            for i in range(3):
                a = (t // 6 + i) % 3
                rr = 4 + (2 if a == 0 else 0)
                x = 28 + i * 16
                c.create_oval(x - rr, cy - rr, x + rr, cy + rr, fill=AMBER, outline=AMBER)
            c.create_text(
                88, cy, text=self.text or "Transkribiere", fill=FG, anchor="w",
                font=("Segoe UI", 10),
            )
        else:
            col = GREEN if self.state == "done" else RED
            c.create_oval(14, cy - 7, 28, cy + 7, fill=col, outline=col)
            c.create_text(
                38, cy, text=self.text[:30], fill=FG, anchor="w", font=("Segoe UI", 10)
            )

    def _loop(self):
        try:
            while True:
                fn, a = self.q.get_nowait()
                try:
                    fn(*a)
                except Exception:
                    import logging
                    logging.exception("UI-Aufruf")
        except queue.Empty:
            pass
        self.tick += 1
        if self.state != "idle":
            if self.hide_at and self.tick >= self.hide_at:
                self._set_state("idle", "", 0)
            else:
                self._draw()
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
