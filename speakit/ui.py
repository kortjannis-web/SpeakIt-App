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
        self.overlay = Overlay(self.root, app.rec)
        self.win = MainWindow(self)
        self.root.after(30, self._loop)

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
        self.root.after(33, self._loop)
