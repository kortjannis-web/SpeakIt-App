"""Selbstinstallation der EXE: kopiert sich nach %LOCALAPPDATA%\\Programs\\SpeakIt, legt Autostart und
Startmenü-Eintrag an und startet die installierte Kopie."""
import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import autostart
from .config import FROZEN

START_MENU = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/SpeakIt.lnk"


def _msg(text):
    ctypes.windll.user32.MessageBoxW(0, text, "SpeakIt", 0x40)


def ensure_installed() -> bool:
    """True, wenn dieser Prozess beendet werden soll (die installierte Kopie wurde gestartet)."""
    if not FROZEN or os.environ.get("SPEAKIT_NO_INSTALL"):
        return False
    me = Path(sys.executable).resolve()
    target = autostart.INSTALLED_EXE
    if target.exists() and me == target.resolve():
        return False
    autostart.INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(me, target)
    except OSError:
        _msg("SpeakIt läuft noch. Bitte im Tray (unten rechts) mit Rechtsklick auf das Symbol beenden "
             "und diese Datei danach erneut öffnen.")
        return True
    autostart.set_enabled(True)
    autostart.make_shortcut(START_MENU, background=False)
    subprocess.Popen([str(target)], cwd=str(autostart.INSTALL_DIR), creationflags=0x00000008)
    return True


def uninstall(app):
    """Autostart und Startmenü entfernen, Programmordner nach dem Beenden löschen. Daten bleiben erhalten."""
    for lnk in (autostart.LNK, START_MENU):
        try:
            lnk.unlink()
        except OSError:
            pass
    d = str(autostart.INSTALL_DIR)
    subprocess.Popen(
        f'cmd /c ping 127.0.0.1 -n 4 >nul & rmdir /s /q "{d}"',
        shell=True, creationflags=0x08000000,
    )
    app._quit()
