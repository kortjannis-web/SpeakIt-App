"""UI im Haupt-Thread: Hauptfenster (customtkinter) und Overlay."""
import logging
import queue

import customtkinter as ctk

from .overlay import Overlay
from .window import MainWindow


class UI:
    def __init__(self, app):
        self.app = app
        self.q = queue.Queue()
        ctk.set_appearance_mode("light")
        self.root = ctk.CTk()
        self.root.withdraw()
        self._set_window_icon()
        self.overlay = Overlay(self.root, app.rec)
        self.win = MainWindow(self)
        self.ticks = 0
        self.root.after(30, self._loop)

    def _set_window_icon(self):
        """Orange Tropfen als Fenster-Symbol (customtkinter setzt nach 200 ms ein eigenes, daher nochmal)."""
        try:
            from .config import DATA
            from .icon import save_ico
            path = str(DATA / "app.ico")
            save_ico(path)
            self.root.iconbitmap(path)
            self.root.after(300, lambda: self.root.iconbitmap(path))
        except Exception:
            logging.exception("Fenster-Icon")

    # Thread-sicherer Zugriff
    def call(self, fn, *a):
        self.q.put((fn, a))

    def set_state(self, state, text="", hold_ms=0):
        self.call(self.overlay.set_state, state, text, hold_ms)

    def open_window(self, page=None):
        self.call(self.win.show, page)

    def open_settings(self):
        self.open_window("Einstellungen")

    def on_new_dictation(self):
        if self.win.built:
            self.win.on_new_dictation()

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
        self.ticks += 1
        if self.ticks % 1800 == 0 and self.win.built:  # ca. alle 30 s: Heute/Monat neu berechnen (Mitternacht)
            self.win.refresh_mini()
            if self.win.visible and self.win.page == "Statistik":
                self.win.refresh_stats()
        self.root.after(16, self._loop)
