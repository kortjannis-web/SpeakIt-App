import os
import subprocess
import sys
from pathlib import Path

from .config import ROOT

LNK = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/SpeakIt.lnk"


def _pythonw():
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def _ps(script):
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
        check=False, creationflags=0x08000000,
    )


def is_enabled():
    return LNK.exists()


def set_enabled(on: bool):
    if on:
        _ps(
            f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{LNK}');"
            f"$s.TargetPath='{_pythonw()}';$s.Arguments='-m speakit';"
            f"$s.WorkingDirectory='{ROOT}';$s.WindowStyle=7;$s.Save()"
        )
    elif LNK.exists():
        LNK.unlink()
