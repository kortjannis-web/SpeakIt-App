import json
import logging
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
ROOT = Path(__file__).resolve().parent.parent
# Entwicklung: Daten im Projektordner. Als EXE: %APPDATA%\SpeakIt
DATA = (Path(os.environ.get("APPDATA", str(Path.home()))) / "SpeakIt") if FROZEN else ROOT
DATA.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = DATA / "config.json"
ENV_PATH = DATA / ".env"
LEGACY_VOCAB_PATH = DATA / "vocabulary.txt"
CONTEXTS_PATH = DATA / "contexts.json"
HISTORY_PATH = DATA / "history.db"
LOG_PATH = DATA / "speakit.log"
FAILED_DIR = DATA / "failed"

DEFAULTS = {
    "hotkey": ["f9"],
    "mode": "both",  # both | hold | toggle
    "hold_threshold": 0.4,
    "language": "de",  # "" = automatisch
    "stt_provider": "groq",  # groq | openai
    "cleanup": True,
    "clean_trigger": "double",  # double = nur nach Doppeltipp | always = jede Aufnahme
    "cleanup_model": "claude-haiku-4-5-20251001",
    "sounds": True,
    "sound_preset": "Sanft",
    "enabled": True,
    "tutorial_done": False,
    "mic": "",
    "max_seconds": 720,
}


def setup_logging():
    handlers = [logging.FileHandler(LOG_PATH, encoding="utf-8")]
    if sys.stderr:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def load_env():
    try:
        from .bundled import KEYS  # nur in der verteilbaren EXE vorhanden
        for k, v in KEYS.items():
            os.environ.setdefault(k, v)
    except ImportError:
        pass
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")


def read_env_file() -> dict:
    out = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def save_env(values: dict):
    existing = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()
    existing.update({k: v for k, v in values.items() if v is not None})
    ENV_PATH.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n", encoding="utf-8"
    )
    for k, v in values.items():
        if v is not None:
            os.environ[k] = v


class Config:
    def __init__(self):
        self.data = dict(DEFAULTS)
        if CONFIG_PATH.exists():
            try:
                self.data.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
            except Exception:
                logging.exception("config.json unlesbar, nutze Standard")

    def __getitem__(self, k):
        return self.data[k]

    def set(self, **kw):
        self.data.update(kw)
        CONFIG_PATH.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
