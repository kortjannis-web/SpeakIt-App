import ctypes
import time

import pyperclip


def active_window_title() -> str:
    try:
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
    except Exception:
        return ""


def paste_text(text: str, hk):
    """Text per Zwischenablage + Strg+V einfügen, alte Zwischenablage zurück."""
    try:
        old = pyperclip.paste()
    except Exception:
        old = ""
    pyperclip.copy(text)
    time.sleep(0.05)
    hk.wait_released()
    hk.send("ctrl+v")
    time.sleep(0.25)
    if old:
        try:
            pyperclip.copy(old)
        except Exception:
            pass
