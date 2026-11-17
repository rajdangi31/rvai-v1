"""Speech-to-text engine (stub | openai_compatible | faster_whisper | whisper_cpp)."""

from __future__ import annotations

import io
import logging
import subprocess
import tempfile
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple

import httpx

from shared.schemas import ClarificationReason
from shared.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class STTError(RuntimeError):
    pass


class STTBackend(ABC):
    @abstractmethod
    def transcribe(self, audio_bytes: bytes, language: str) -> str:
        raise NotImplementedError


class StubSTTBackend(STTBackend):
    def __init__(self, fixed_text: str = ""):
        self.fixed_text = fixed_text

    def transcribe(self, audio_bytes: bytes, language: str) -> str:
        return self.fixed_text


class OpenAICompatibleSTTBackend(STTBackend):
    def __init__(self, settings: Settings, client: Optional[httpx.Client] = None):
        self.settings = settings
        self._client = client

    def transcribe(self, audio_bytes: bytes, language: str) -> str:
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"} if self.settings.llm_api_key else {}
        client = self._client or httpx.Client(
            base_url=self.settings.stt_base_url.rstrip("/"),
            timeout=self.settings.llm_timeout_seconds,
            headers=headers,
        )
        try:
            response = client.post(
                "/audio/transcriptions",
                data={"model": self.settings.stt_model, "language": language},
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
            )
            response.raise_for_status()
            text = response.json().get("text", "")
            if not isinstance(text, str):
                raise STTError("STT response missing text")
            return text
        except httpx.HTTPError as exc:
            raise STTError(f"STT request failed: {exc}") from exc
        finally:
            if self._client is None:
                client.close()


class FasterWhisperSTTBackend(STTBackend):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None

    def transcribe(self, audio_bytes: bytes, language: str) -> str:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel  # type: ignore
            except ImportError as exc:
                raise STTError("Install faster-whisper via: pip install '.[stt-local]'") from exc
            self._model = WhisperModel(
                self.settings.faster_whisper_model,
                device=self.settings.faster_whisper_device,
                compute_type=self.settings.faster_whisper_compute_type,
            )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            handle.write(audio_bytes)
            path = Path(handle.name)
        try:
            segments, _ = self._model.transcribe(str(path), language=language or None)
            return " ".join(s.text.strip() for s in segments).strip()
        finally:
            path.unlink(missing_ok=True)


class WhisperCppSTTBackend(STTBackend):
    """Offline whisper.cpp path proven in RVAI real-voice tests (ggml-base.en)."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def transcribe(self, audio_bytes: bytes, language: str) -> str:
        model = self.settings.whisper_model_path
        if model is None or not Path(model).exists():
            raise STTError("RVAI_WHISPER_MODEL_PATH is missing for whisper_cpp backend")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            raw_path = tmp_path / "input.bin"
            wav_path = tmp_path / "input.wav"
            raw_path.write_bytes(audio_bytes)

            # Normalize to 16 kHz mono WAV when ffmpeg is available; otherwise assume WAV input.
            if _looks_like_wav(audio_bytes):
                wav_path.write_bytes(audio_bytes)
            else:
                ffmpeg = self.settings.ffmpeg_binary
                conv = subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-i",
                        str(raw_path),
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        "-c:a",
                        "pcm_s16le",
                        str(wav_path),
                    ],
                    capture_output=True,
                    timeout=60,
                    check=False,
                )
                if conv.returncode != 0 or not wav_path.exists():
                    raise STTError(
                        f"ffmpeg failed: {conv.stderr.decode('utf-8', 'replace')[:200]}"
                    )

            out_prefix = tmp_path / "transcript"
            cmd = [
                self.settings.whisper_cli_binary,
                "-m",
                str(model),
                "-f",
                str(wav_path),
                "-otxt",
                "-of",
                str(out_prefix),
            ]
            if language:
                cmd.extend(["-l", language])
            proc = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
            text_file = Path(str(out_prefix) + ".txt")
            if proc.returncode != 0 or not text_file.exists():
                raise STTError(
                    f"whisper-cli failed: {proc.stderr.decode('utf-8', 'replace')[:200]}"
                )
            return text_file.read_text(encoding="utf-8").strip()


class STTEngine:
    """Validates audio size/duration and returns (transcript, error_reason)."""

    def __init__(self, settings: Optional[Settings] = None, backend: Optional[STTBackend] = None):
        self.settings = settings or get_settings()
        self.backend = backend or self._build_backend(self.settings)

    @staticmethod
    def _build_backend(settings: Settings) -> STTBackend:
        if settings.stt_backend == "stub":
            return StubSTTBackend("")
        if settings.stt_backend == "openai_compatible":
            return OpenAICompatibleSTTBackend(settings)
        if settings.stt_backend == "faster_whisper":
            return FasterWhisperSTTBackend(settings)
        if settings.stt_backend == "whisper_cpp":
            return WhisperCppSTTBackend(settings)
        raise ValueError(f"Unknown STT backend: {settings.stt_backend}")

    def transcribe(self, audio_bytes: bytes) -> Tuple[Optional[str], Optional[ClarificationReason]]:
        if not audio_bytes:
            return None, ClarificationReason.NO_SPEECH
        if len(audio_bytes) > self.settings.max_audio_bytes:
            return None, ClarificationReason.NOT_UNDERSTOOD
        duration = _wav_duration_seconds(audio_bytes)
        if duration is not None and duration > self.settings.max_audio_seconds:
            return None, ClarificationReason.NOT_UNDERSTOOD

        try:
            text = self.backend.transcribe(audio_bytes, self.settings.stt_language).strip()
        except STTError as exc:
            logger.warning("STT failed: %s", exc)
            return None, ClarificationReason.AI_UNAVAILABLE
        if not text:
            return None, ClarificationReason.NO_SPEECH
        return text, None


def _looks_like_wav(audio_bytes: bytes) -> bool:
    return len(audio_bytes) >= 12 and audio_bytes[0:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE"


def _wav_duration_seconds(audio_bytes: bytes) -> Optional[float]:
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as handle:
            rate = handle.getframerate()
            return (handle.getnframes() / float(rate)) if rate > 0 else None
    except wave.Error:
        return None
