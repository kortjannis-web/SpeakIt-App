import ctypes
import threading
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


def paste_text(text: str, hk, restore=None):
    """Text per Zwischenablage + Strg+V einfügen, alte Zwischenablage (oder `restore`) zurück."""
    if restore is not None:
        old = restore
    else:
        try:
            old = pyperclip.paste()
        except Exception:
            old = ""
    pyperclip.copy(text)
    time.sleep(0.03)
    hk.wait_released()
    hk.send("ctrl+v")
    if old:  # alte Zwischenablage im Hintergrund zurück, damit der Aufrufer nicht wartet
        def restore():
            time.sleep(0.35)
            try:
                pyperclip.copy(old)
            except Exception:
                pass
        threading.Thread(target=restore, daemon=True).start()


def copy_selection(hk, timeout=0.6) -> tuple[str, str]:
    """Markierten Text per Strg+C holen. Gibt (markierung, alte_zwischenablage) zurück; leer = nichts markiert.

    Die Zwischenablage wird vorher geleert, damit ein alter Inhalt nicht als Markierung durchgeht.
    """
    try:
        old = pyperclip.paste()
    except Exception:
        old = ""
    try:
        pyperclip.copy("")
    except Exception:
        pass
    hk.wait_released()
    hk.send("ctrl+c")
    end = time.time() + timeout
    sel = ""
    while time.time() < end:
        try:
            sel = pyperclip.paste()
        except Exception:
            sel = ""
        if sel:
            break
        time.sleep(0.03)
    if not sel and old:
        try:
            pyperclip.copy(old)
        except Exception:
            pass
    return sel, old
