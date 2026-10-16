"""Sprachmodell für Feinschliff, Struktur, Übersetzen und Umschreiben.

Groq (gpt-oss, gleicher Key wie Whisper, Gratis-Kontingent) ist Standard, Claude Haiku die Alternative.
Fällt der gewählte Anbieter aus (kein Key, Limit, Netzwerk), springt der andere ein, sofern ein Key da ist.
"""
import logging
import os
import re

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CLAUDE_URL = "https://api.anthropic.com/v1/messages"
PROVIDERS = ("groq", "claude")
KEYS = {"groq": "GROQ_API_KEY", "claude": "ANTHROPIC_API_KEY"}


class LlmError(Exception):
    pass


def has_key(provider: str) -> bool:
    return bool(os.environ.get(KEYS[provider], ""))


def order(preferred: str) -> list[str]:
    """Gewählter Anbieter zuerst, dann der andere. Nur Anbieter mit Key."""
    first = preferred if preferred in PROVIDERS else "groq"
    return [p for p in (first, *(p for p in PROVIDERS if p != first)) if has_key(p)]


def _groq(system: str, user: str, model: str, max_tokens: int, timeout: float):
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_completion_tokens": max_tokens,
    }
    if "gpt-oss" in model:  # Denk-Modell: kurz denken, Gedanken nicht mitschicken
        body["reasoning_effort"] = "low"
        body["include_reasoning"] = False
    r = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {os.environ[KEYS['groq']]}"},
                      json=body, timeout=timeout)
    if r.status_code != 200:
        raise LlmError(f"Groq {r.status_code}: {r.text[:200]}")
    j = r.json()
    usage = j.get("usage", {})
    text = ((j.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


def _claude(system: str, user: str, model: str, max_tokens: int, timeout: float):
    r = requests.post(
        CLAUDE_URL,
        headers={"x-api-key": os.environ[KEYS["claude"]], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": model, "max_tokens": max_tokens, "temperature": 0, "system": system,
              "messages": [{"role": "user", "content": user}]},
        timeout=timeout,
    )
    if r.status_code != 200:
        raise LlmError(f"Claude {r.status_code}: {r.text[:200]}")
    j = r.json()
    usage = j.get("usage", {})
    text = "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text")
    return text, usage.get("input_tokens", 0), usage.get("output_tokens", 0)


def complete(system: str, user: str, cfg, max_tokens: int, timeout: float):
    """Gibt (text, provider, tokens_in, tokens_out) zurück. Wirft LlmError, wenn kein Anbieter klappt."""
    providers = order(cfg["llm_provider"])
    if not providers:
        raise LlmError("Kein Groq- oder Anthropic-Key (Einstellungen öffnen)")
    last = None
    for p in providers:
        try:
            if p == "groq":
                text, t_in, t_out = _groq(system, user, cfg["groq_model"], max_tokens, timeout)
            else:
                text, t_in, t_out = _claude(system, user, cfg["cleanup_model"], max_tokens, timeout)
            text = strip_wrappers(text)
            if text:
                return text, p, t_in, t_out
            last = LlmError(f"{p}: leere Antwort")
        except (requests.RequestException, LlmError, ValueError) as e:
            last = e if isinstance(e, LlmError) else LlmError(f"{p}: {e}")
        logging.warning("LLM %s fehlgeschlagen: %s", p, last)
    raise last


def strip_wrappers(text: str) -> str:
    """Entfernt Tags und Code-Zäune, die Modelle gelegentlich um die Antwort legen."""
    t = (text or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\n(.*)\n```$", r"\1", t, flags=re.S).strip()
    t = re.sub(r"^<(transcript|text|output)>\s*|\s*</(transcript|text|output)>$", "", t).strip()
    return t
