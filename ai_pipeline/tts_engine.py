"""
Raj: Piper TTS engine for spoken outcome feedback.

Backends (RVAI_TTS_BACKEND):
  - stub:  returns None
  - piper: runs `piper --model <onnx> --output_file <wav>` and returns the WAV path

Optional playback (RVAI_TTS_PLAY=true) for Jetson-connected speakers.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional
from uuid import uuid4

from shared.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class TTSEngine:
    """Synthesizes honest outcome replies into WAV files via Piper."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def synthesize_speech(self, text: str, *, play: bool = False) -> Optional[str]:
        cleaned = (text or "").strip()
        if not cleaned or self.settings.tts_backend == "stub":
            return None

        model_path = self.settings.piper_model_path
        if model_path is None or not Path(model_path).exists():
            logger.warning("Piper TTS enabled but RVAI_PIPER_MODEL_PATH is missing: %s", model_path)
            return None

        out_dir = Path(self.settings.tts_output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"reply_{uuid4().hex[:10]}.wav"

        try:
            proc = subprocess.run(
                [self.settings.piper_binary, "--model", str(model_path), "--output_file", str(out_file)],
                input=cleaned.encode("utf-8"),
                capture_output=True,
                timeout=15,
                check=False,
            )
            if proc.returncode != 0 or not out_file.exists():
                logger.warning(
                    "Piper exited %s: %s",
                    proc.returncode,
                    proc.stderr.decode("utf-8", "replace")[:200],
                )
                return None
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            logger.warning("Piper TTS unavailable: %s", exc)
            return None

        if play or self.settings.tts_play:
            self._play(out_file)
        return str(out_file)

    @staticmethod
    def _play(path: Path) -> None:
        try:
            if sys.platform.startswith("win"):
                import winsound

                winsound.PlaySound(str(path), winsound.SND_FILENAME)
                return
            # Jetson / Linux: prefer aplay, then paplay.
            for binary in ("aplay", "paplay"):
                try:
                    subprocess.run([binary, str(path)], check=False, capture_output=True, timeout=30)
                    return
                except FileNotFoundError:
                    continue
            logger.warning("No audio player found for %s", path)
        except Exception as exc:
            logger.warning("TTS playback failed: %s", exc)
