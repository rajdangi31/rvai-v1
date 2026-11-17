"""
Raj: Voice Input — Jetson push-to-talk microphone capture (Week 06 Architecture).

Tablet audio streaming is deferred in V1; local USB/I2S mic capture produces WAV bytes
for STTEngine / POST /api/audio.
"""

from __future__ import annotations

import io
import wave
from pathlib import Path


class AudioCaptureError(RuntimeError):
    pass


def load_wav_bytes(path: str | Path) -> bytes:
    """Read a WAV file from disk."""
    data = Path(path).read_bytes()
    if not data:
        raise AudioCaptureError(f"WAV file is empty: {path}")
    return data


def record_push_to_talk(seconds: float = 4.0, sample_rate: int = 16000) -> bytes:
    """Capture mono 16-bit PCM from the default Jetson/system microphone into WAV bytes."""
    try:
        import sounddevice as sd  # type: ignore
    except ImportError as exc:
        raise AudioCaptureError(
            "Microphone capture requires 'sounddevice' (pip install sounddevice)."
        ) from exc

    frames = int(seconds * sample_rate)
    recording = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="int16")
    sd.wait()

    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(recording.tobytes())
    return buf.getvalue()
