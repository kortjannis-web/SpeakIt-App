"""Ruhige, weiche Glockentöne (Sinus + leiser Oberton, sanfte Hüllkurve)."""
import io
import math
import struct
import threading
import wave
import winsound

RATE = 22050
MASTER = 0.10


def _chime(notes, tail=0.22, rate=RATE):
    """notes: Liste (Frequenz, Startzeit s, Lautstärke 0..1)."""
    total = int(rate * (max(s for _, s, _ in notes) + tail + 0.12))
    buf = [0.0] * total
    for freq, start, vol in notes:
        n0 = int(start * rate)
        dur = int(rate * (tail + 0.12))
        for i in range(min(dur, total - n0)):
            tt = i / rate
            attack = min(1.0, tt / 0.012)
            env = attack * math.exp(-tt * 14)
            s = math.sin(2 * math.pi * freq * tt) + 0.22 * math.sin(2 * math.pi * freq * 2 * tt)
            buf[n0 + i] += s * env * vol
    pcm = b"".join(struct.pack("<h", int(max(-1, min(1, v)) * MASTER * 32767)) for v in buf)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


_SOUNDS = {
    "start": _chime([(523.25, 0.00, 1.0), (659.25, 0.07, 0.9)]),
    "stop": _chime([(659.25, 0.00, 0.9), (523.25, 0.07, 1.0)]),
    "done": _chime([(783.99, 0.00, 0.55)], tail=0.14),
    "error": _chime([(349.23, 0.00, 1.0), (293.66, 0.12, 1.0)], tail=0.3),
}


def play(name):
    data = _SOUNDS[name]
    threading.Thread(
        target=lambda: winsound.PlaySound(data, winsound.SND_MEMORY),
        daemon=True,
    ).start()
