import ctypes
import sys

from .config import setup_logging


def main():
    setup_logging()
    # Nur eine Instanz
    ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\SpeakIt_single_instance")
    if ctypes.windll.kernel32.GetLastError() == 183:
        sys.exit(0)
    from .app import App
    App().run()


if __name__ == "__main__":
    main()
