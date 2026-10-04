import ctypes
import sys

from .config import FROZEN, setup_logging


def main():
    setup_logging()
    if FROZEN:
        from .installer import ensure_installed
        if ensure_installed():
            return
    # Nur eine Instanz
    ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\SpeakIt_single_instance")
    if ctypes.windll.kernel32.GetLastError() == 183:
        sys.exit(0)
    from .app import App
    App().run(background="--background" in sys.argv)


if __name__ == "__main__":
    main()
