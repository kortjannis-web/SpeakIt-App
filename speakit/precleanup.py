"""Kostenlose Vorreinigung ohne KI: Füllwörter, Wortdoppler, Leerzeichen, Großschreibung am Satzanfang."""
import re

FILLERS = r"ähm+|äh+|öhm+|ehm+|hm+|mhm|hmm+|uhm+|ähem"
_FILLER = re.compile(r"(?i)(?:,\s*)?\b(?:" + FILLERS + r")\b(?:\s*,)?")
_DOUBLE = re.compile(r"(?i)\b(\w+)(\s+\1\b)+")
KEEP_DOUBLE = {"die", "der", "das", "den", "dem", "des", "sie", "was", "wer"}  # "die die Regeln kennen" ist korrekt


def preclean(text: str) -> str:
    t = _FILLER.sub(" ", text or "")
    t = _DOUBLE.sub(lambda m: m.group(0) if m.group(1).lower() in KEEP_DOUBLE else m.group(1), t)
    t = re.sub(r"\s+([,.!?;:])", r"\1", t)  # kein Leerzeichen vor Satzzeichen
    t = re.sub(r"([,;:])(?=[^\s\d])", r"\1 ", t)
    t = re.sub(r",\s*([.!?])", r"\1", t)
    t = re.sub(r"([.!?])\s*,", r"\1", t)
    t = re.sub(r"^\s*[,.;:]\s*", "", t)
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    # Satzanfang groß
    t = re.sub(r"(^|[.!?]\s+|\n\s*)([a-zäöü])", lambda m: m.group(1) + m.group(2).upper(), t)
    return t
