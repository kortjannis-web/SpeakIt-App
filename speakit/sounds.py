import io
import math
import struct
import threading
import wave
import winsound


def _tone(freqs, ms=70, vol=0.25, rate=22050):
    frames = bytearray()
    for f in freqs:
        n = int(rate * ms / 1000)
        for i in range(n):
            env = min(1.0, i / 200, (n - i) / 400)
            frames += struct.pack("<h", int(32767 * vol * env * math.sin(2 * math.pi * f * i / rate)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


_SOUNDS = {
    "start": _tone([660, 880]),
    "stop": _tone([880, 600]),
    "done": _tone([990], ms=55, vol=0.18),
    "error": _tone([300, 220], ms=110),
}


def play(name):
    data = _SOUNDS[name]
    threading.Thread(
        target=lambda: winsound.PlaySound(data, winsound.SND_MEMORY),
        daemon=True,
    ).start()
