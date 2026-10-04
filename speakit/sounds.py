"""Acht ruhige Klang-Presets, jeweils ein Ton für Aufnahme-Start und Aufnahme-Stopp (synthetisch erzeugt)."""
import io
import math
import random
import struct
import threading
import time
import wave
import winsound

RATE = 22050


# ---------------------------------------------------------------- Bausteine (liefern Sample-Listen)
def tone(freq, dur=0.35, vol=1.0, attack=0.01, decay=14.0, harm=((2, 0.22),)):
    n = int(RATE * dur)
    out = []
    for i in range(n):
        t = i / RATE
        env = min(1.0, t / attack) * math.exp(-t * decay)
        s = math.sin(2 * math.pi * freq * t)
        for mult, amp in harm:
            s += amp * math.sin(2 * math.pi * freq * mult * t)
        out.append(s * env * vol)
    return out


def sweep(f0, f1, dur=0.12, vol=1.0, decay=14.0, attack=0.004):
    n = int(RATE * dur)
    out, phase = [], 0.0
    for i in range(n):
        t = i / RATE
        f = f0 + (f1 - f0) * (i / n)
        phase += 2 * math.pi * f / RATE
        out.append(math.sin(phase) * min(1.0, t / attack) * math.exp(-t * decay) * vol)
    return out


def click(thump=160, dur=0.06, vol=1.0, bright=0.35):
    rnd = random.Random(7)
    n = int(RATE * dur)
    out, lp = [], 0.0
    for i in range(n):
        t = i / RATE
        lp += bright * (rnd.uniform(-1, 1) - lp)
        s = lp * math.exp(-t * 260) * 0.8 + math.sin(2 * math.pi * thump * t) * math.exp(-t * 90) * 0.7
        out.append(s * vol)
    return out


def _render(parts, gain=0.12):
    """parts: Liste (Startzeit s, Samples)."""
    total = max(int(st * RATE) + len(sm) for st, sm in parts) + int(RATE * 0.05)
    buf = [0.0] * total
    for st, sm in parts:
        o = int(st * RATE)
        for i, v in enumerate(sm):
            buf[o + i] += v
    pcm = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v)) * gain * 32767)) for v in buf)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return out.getvalue()


# ---------------------------------------------------------------- Presets: name -> (start, stop)
def _sanft():
    return (
        _render([(0, tone(523.25)), (0.07, tone(659.25, vol=0.9))]),
        _render([(0, tone(659.25, vol=0.9)), (0.07, tone(523.25))]),
    )


def _blub():
    return (
        _render([(0, sweep(260, 640, 0.13, decay=15)), (0.08, sweep(340, 800, 0.1, vol=0.55, decay=18))], 0.16),
        _render([(0, sweep(640, 240, 0.15, decay=13)), (0.08, sweep(480, 200, 0.1, vol=0.5, decay=16))], 0.16),
    )


def _tropfen():
    return (
        _render([(0, tone(1318.5, 0.3, decay=22, harm=((2, 0.1),)))], 0.10),
        _render([(0, tone(880, 0.3, decay=20, harm=((2, 0.1),))), (0.09, tone(660, 0.3, vol=0.8, decay=20, harm=()))], 0.10),
    )


def _klack():
    return (
        _render([(0, click(190, 0.06, 1.0, 0.45))], 0.22),
        _render([(0, click(120, 0.07, 0.9, 0.3))], 0.22),
    )


def _marimba():
    h = ((4, 0.35), (10, 0.08))
    return (
        _render([(0, tone(440, 0.5, decay=9, harm=h)), (0.08, tone(659.25, 0.5, vol=0.9, decay=9, harm=h))], 0.12),
        _render([(0, tone(659.25, 0.5, vol=0.9, decay=9, harm=h)), (0.08, tone(440, 0.5, decay=9, harm=h))], 0.12),
    )


def _glas():
    h = ((2.76, 0.3), (5.4, 0.12))
    return (
        _render([(0, tone(1046.5, 0.7, decay=6, harm=h)), (0.1, tone(1568, 0.7, vol=0.8, decay=6, harm=h))], 0.07),
        _render([(0, tone(1568, 0.7, vol=0.8, decay=6, harm=h)), (0.1, tone(1046.5, 0.7, decay=6, harm=h))], 0.07),
    )


def _pop():
    return (
        _render([(0, sweep(760, 190, 0.06, decay=38))], 0.2),
        _render([(0, sweep(520, 140, 0.07, decay=34))], 0.2),
    )


def _pad():
    h = ((2, 0.12),)
    return (
        _render([(0, tone(392, 0.6, attack=0.05, decay=5, harm=h)), (0.06, tone(523.25, 0.6, vol=0.8, attack=0.05, decay=5, harm=h))], 0.11),
        _render([(0, tone(523.25, 0.6, vol=0.8, attack=0.05, decay=5, harm=h)), (0.06, tone(392, 0.6, attack=0.05, decay=5, harm=h))], 0.11),
    )


BUILDERS = {
    "Sanft": _sanft, "Blub (Wasser)": _blub, "Tropfen": _tropfen, "Klack": _klack,
    "Marimba": _marimba, "Glas": _glas, "Pop": _pop, "Pad": _pad,
}
PRESETS = list(BUILDERS)
DEFAULT = "Sanft"
_cache: dict = {}
_error = None


def _get(preset):
    if preset not in BUILDERS:
        preset = DEFAULT
    if preset not in _cache:
        _cache[preset] = BUILDERS[preset]()
    return _cache[preset]


def _play_bytes(data):
    threading.Thread(target=lambda: winsound.PlaySound(data, winsound.SND_MEMORY), daemon=True).start()


def play(kind, preset=DEFAULT):
    """kind: 'start', 'stop' oder 'error'."""
    global _error
    if kind == "error":
        if _error is None:
            _error = _render([(0, tone(349.23, 0.3, decay=12)), (0.12, tone(293.66, 0.35, decay=12))], 0.11)
        _play_bytes(_error)
        return
    start, stop = _get(preset)
    _play_bytes(start if kind == "start" else stop)


def preview(preset):
    """Beide Töne nacheinander anhören."""
    def run():
        start, stop = _get(preset)
        winsound.PlaySound(start, winsound.SND_MEMORY)
        time.sleep(0.45)
        winsound.PlaySound(stop, winsound.SND_MEMORY)
    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------- Fertig-Signal
_plop_cache = None


def _plop_wav():
    """Kurzes, weiches Plop wie ein Tropfen: fallender Ton mit kleinem Nachklang."""
    samples = [a + b for a, b in zip(sweep(620, 190, dur=0.11, vol=1.0, decay=26.0, attack=0.002),
                                     tone(880, dur=0.11, vol=0.18, decay=40.0, harm=()))]
    pcm = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v)) * 0.16 * 32767)) for v in samples)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return out.getvalue()


def plop():
    global _plop_cache
    if _plop_cache is None:
        _plop_cache = _plop_wav()
    threading.Thread(target=lambda: winsound.PlaySound(_plop_cache, winsound.SND_MEMORY), daemon=True).start()
