import logging
import os

import requests

PROVIDERS = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/audio/transcriptions",
        "model": "whisper-large-v3-turbo",
        "key": "GROQ_API_KEY",
    },
    "openai": {
        "url": "https://api.openai.com/v1/audio/transcriptions",
        "model": "gpt-4o-mini-transcribe",
        "key": "OPENAI_API_KEY",
    },
}


class SttError(Exception):
    pass


def transcribe(wav: bytes, provider: str, language: str, terms: list[str]) -> str:
    p = PROVIDERS[provider]
    key = os.environ.get(p["key"], "")
    if not key:
        raise SttError(f"{p['key']} fehlt (Einstellungen öffnen)")
    data = {"model": p["model"], "response_format": "json", "temperature": "0"}
    if language:
        data["language"] = language
    if terms:
        data["prompt"] = ("Begriffe: " + ", ".join(terms))[:800]
    last = None
    for attempt in range(2):
        try:
            r = requests.post(
                p["url"],
                headers={"Authorization": f"Bearer {key}"},
                files={"file": ("audio.wav", wav, "audio/wav")},
                data=data,
                timeout=60,
            )
            if r.status_code == 200:
                return r.json().get("text", "").strip()
            last = SttError(f"STT {r.status_code}: {r.text[:200]}")
            if r.status_code < 500 and r.status_code != 429:
                raise last
        except requests.RequestException as e:
            last = SttError(f"Netzwerk: {e}")
        logging.warning("STT Versuch %s fehlgeschlagen: %s", attempt + 1, last)
    raise last
