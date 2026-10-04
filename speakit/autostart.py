import os
import subprocess
import sys
from pathlib import Path

from .config import FROZEN, ROOT

STARTUP = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
LNK = STARTUP / "SpeakIt.lnk"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "SpeakIt"
INSTALLED_EXE = INSTALL_DIR / "SpeakIt.exe"


def _pythonw():
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def _ps(script):
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        check=False, creationflags=0x08000000,
    )


def make_shortcut(lnk: Path, background=True):
    if FROZEN:
        target, args, workdir = str(INSTALLED_EXE), "--background" if background else "", str(INSTALL_DIR)
    else:
        target, args, workdir = _pythonw(), "-m speakit" + (" --background" if background else ""), str(ROOT)
    _ps(
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        f"$s.TargetPath='{target}';$s.Arguments='{args}';$s.WorkingDirectory='{workdir}';"
        f"$s.IconLocation='{target},0';$s.WindowStyle=7;$s.Save()"
    )


def is_enabled():
    return LNK.exists()


def set_enabled(on: bool):
    if on:
        make_shortcut(LNK)
    elif LNK.exists():
        LNK.unlink()
