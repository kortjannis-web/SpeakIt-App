"""Selbst-Update über GitHub Releases.

Jeder Push auf master baut per GitHub Actions eine neue SpeakIt.exe und veröffentlicht sie als Release.
Die installierte App fragt beim Start und danach alle paar Stunden nach, lädt eine neuere Version im
Hintergrund herunter und tauscht sie beim nächsten Start aus (laufende EXE umbenennen, neue an ihren Platz)."""
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

from . import autostart
from .config import FROZEN
from .version import VERSION

REPO = "kortjannis-web/SpeakIt-App"
ASSET = "SpeakIt.exe"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
NEW = autostart.INSTALL_DIR / "SpeakIt.update.exe"
OLD = autostart.INSTALL_DIR / "SpeakIt.old.exe"
EVERY = 6 * 3600


def parse(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3]) or (0,)


def enabled() -> bool:
    return FROZEN and not os.environ.get("SPEAKIT_NO_UPDATE")


def _is_installed() -> bool:
    try:
        return Path(sys.executable).resolve() == autostart.INSTALLED_EXE.resolve()
    except OSError:
        return False


def pending() -> bool:
    return NEW.exists()


def apply_pending() -> bool:
    """Beim Start: liegt ein geladenes Update bereit, wird es eingesetzt und gestartet. True = diesen Prozess beenden."""
    if not enabled() or not _is_installed():
        return False
    try:
        OLD.unlink(missing_ok=True)  # Rest vom letzten Update
    except OSError:
        pass
    if not NEW.exists():
        return False
    exe = autostart.INSTALLED_EXE
    try:
        os.replace(exe, OLD)  # eine laufende EXE darf umbenannt werden
        try:
            os.replace(NEW, exe)
        except OSError:
            os.replace(OLD, exe)  # zurückrollen
            raise
    except OSError:
        logging.exception("Update einsetzen")
        return False
    logging.info("Update eingesetzt, starte neu")
    subprocess.Popen([str(exe)] + sys.argv[1:], cwd=str(autostart.INSTALL_DIR), creationflags=0x00000008)
    return True


def check_once() -> bool:
    """Neuere Version vorhanden? Dann herunterladen. True = Update liegt bereit."""
    r = requests.get(LATEST, timeout=10, headers={"Accept": "application/vnd.github+json"})
    if r.status_code != 200:
        logging.info("Update-Prüfung: HTTP %s", r.status_code)
        return pending()
    rel = r.json()
    if parse(rel.get("tag_name", "")) <= parse(VERSION):
        return pending()
    url = next((a["browser_download_url"] for a in rel.get("assets", []) if a.get("name") == ASSET), None)
    if not url:
        return pending()
    part = NEW.with_suffix(".part")
    with requests.get(url, stream=True, timeout=30) as d:
        d.raise_for_status()
        with open(part, "wb") as f:
            for chunk in d.iter_content(1 << 16):
                f.write(chunk)
    if part.stat().st_size < 5_000_000:  # eine echte SpeakIt.exe ist deutlich größer
        part.unlink(missing_ok=True)
        return pending()
    os.replace(part, NEW)
    logging.info("Update %s geladen, wird beim nächsten Start installiert", rel.get("tag_name"))
    return True


def start_background(on_ready=None):
    """Prüft kurz nach dem Start und danach alle 6 Stunden."""
    if not enabled() or not _is_installed():
        return

    def loop():
        time.sleep(15)
        while True:
            try:
                if check_once() and on_ready:
                    on_ready()
            except Exception as e:  # Netzwerk weg o. Ä.: beim nächsten Mal wieder
                logging.info("Update-Prüfung fehlgeschlagen: %s", e)
            time.sleep(EVERY)

    threading.Thread(target=loop, daemon=True).start()


def restart_now(quit_fn):
    """Beenden und nach kurzer Pause neu starten, beim Start wird das Update eingesetzt."""
    exe = str(autostart.INSTALLED_EXE)
    subprocess.Popen(f'cmd /c ping 127.0.0.1 -n 3 >nul & start "" "{exe}"', shell=True, creationflags=0x08000000)
    quit_fn()
