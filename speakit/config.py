import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
ENV_PATH = ROOT / ".env"
VOCAB_PATH = ROOT / "vocabulary.txt"
LOG_PATH = ROOT / "speakit.log"
FAILED_DIR = ROOT / "failed"

DEFAULTS = {
    "hotkey": ["f9"],
    "mode": "both",  # both | hold | toggle
    "hold_threshold": 0.4,
    "language": "de",  # "" = automatisch
    "stt_provider": "groq",  # groq | openai
    "cleanup": True,
    "cleanup_model": "claude-haiku-4-5-20251001",
    "sounds": True,
    "mic": "",
    "max_seconds": 600,
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
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")


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


def read_vocabulary():
    """Gibt (begriffe, ersetzungen, themen) zurueck."""
    terms, repl, topics = [], [], []
    if VOCAB_PATH.exists():
        for line in VOCAB_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("thema:"):
                topics.append(line[6:].strip())
            elif "=>" in line:
                a, b = (x.strip() for x in line.split("=>", 1))
                if a and b:
                    repl.append((a, b))
                    terms.append(b)
            else:
                terms.append(line)
    return terms, repl, topics
