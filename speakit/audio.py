import io
import threading
import wave

import numpy as np
import sounddevice as sd

RATE = 16000


def list_mics():
    out = []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0 and d["name"] not in out:
            out.append(d["name"])
    return out


def _find_device(name):
    if not name:
        return None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and name.lower() in d["name"].lower():
            return i
    return None


class Recorder:
    def __init__(self):
        self.stream = None
        self.chunks = []
        self.level = 0.0
        self.lock = threading.Lock()

    def start(self, mic=""):
        self.chunks = []
        self.level = 0.0
        self.stream = sd.InputStream(
            samplerate=RATE, channels=1, dtype="int16",
            device=_find_device(mic), callback=self._cb, blocksize=800,
        )
        self.stream.start()

    def _cb(self, data, frames, time_info, status):
        with self.lock:
            self.chunks.append(data.copy())
        rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2))) / 32768.0
        self.level = min(1.0, rms * 8)

    @property
    def seconds(self):
        with self.lock:
            return sum(len(c) for c in self.chunks) / RATE

    def stop(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            finally:
                self.stream = None
        self.level = 0.0
        with self.lock:
            if not self.chunks:
                return np.zeros(0, dtype=np.int16)
            return np.concatenate(self.chunks).flatten()


def has_speech(pcm: np.ndarray) -> bool:
    """Grobe Stille-Erkennung, spart API-Kosten und Whisper-Halluzinationen."""
    if len(pcm) < RATE * 0.3:
        return False
    win = RATE // 50
    n = len(pcm) // win
    if n == 0:
        return False
    frames = pcm[: n * win].reshape(n, win).astype(np.float32)
    rms = np.sqrt((frames ** 2).mean(axis=1)) / 32768.0
    return int((rms > 0.008).sum()) >= 6


def to_wav(pcm: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
