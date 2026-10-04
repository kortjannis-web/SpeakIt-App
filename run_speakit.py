"""Einstiegspunkt für die EXE (PyInstaller)."""
import os
import sys

if "--selftest" in sys.argv:
    # Prüft, ob alle Module und Bibliotheken in der EXE vorhanden sind
    out = os.path.join(os.environ.get("TEMP", "."), "speakit_selftest.txt")
    try:
        import customtkinter  # noqa: F401
        import keyboard  # noqa: F401
        import pystray  # noqa: F401
        import sounddevice as sd
        sd.query_devices()
        import speakit.app  # noqa: F401
        import speakit.window  # noqa: F401
        open(out, "w").write("OK")
    except Exception as e:  # noqa: BLE001
        open(out, "w").write("FEHLER: " + repr(e))
        sys.exit(1)
    sys.exit(0)

from speakit.__main__ import main  # noqa: E402

main()
