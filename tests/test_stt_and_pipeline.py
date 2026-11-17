"""STT validation + SmartRVPipeline wrapper tests."""

from __future__ import annotations

import io
import wave

from ai_pipeline.intent_router import IntentRouter
from ai_pipeline.llm_client import LLMClient, LLMError
from ai_pipeline.stt_engine import STTEngine, StubSTTBackend
from backend.coordinator import CommandCoordinator
from backend.main_pipeline import SmartRVPipeline
from matter_bridge.adapter import MatterAdapter
from tests.fakes.matter_port import FakeMatterPort
from shared.schemas import ClarificationReason, CommandRequest


class _BoomLLM(LLMClient):
    def generate_completion(self, user_prompt: str, **kwargs) -> str:
        raise LLMError("down")


def _wav_bytes(seconds: float = 0.1, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


def test_stt_empty_and_oversize(settings):
    engine = STTEngine(settings=settings, backend=StubSTTBackend("hello"))
    assert engine.transcribe(b"") == (None, ClarificationReason.NO_SPEECH)

    settings.max_audio_bytes = 10
    engine = STTEngine(settings=settings, backend=StubSTTBackend("hello"))
    assert engine.transcribe(b"0123456789012345") == (None, ClarificationReason.NOT_UNDERSTOOD)


def test_stt_no_speech_and_success(settings):
    assert STTEngine(settings=settings, backend=StubSTTBackend("   ")).transcribe(_wav_bytes()) == (
        None,
        ClarificationReason.NO_SPEECH,
    )
    text, err = STTEngine(settings=settings, backend=StubSTTBackend("turn on kitchen")).transcribe(_wav_bytes())
    assert err is None and text == "turn on kitchen"


def test_interpret_audio_path(registry, settings):
    stt = STTEngine(settings=settings, backend=StubSTTBackend("turn on the kitchen"))
    router = IntentRouter(
        registry=registry,
        settings=settings,
        llm_client=_BoomLLM(settings),
        stt_engine=stt,
    )
    result = router.interpret_audio(_wav_bytes())
    assert isinstance(result, CommandRequest)
    assert result.source == "voice"
    assert result.target == "kitchen"


def test_pipeline_text_and_tap(registry, settings):
    router = IntentRouter(registry=registry, settings=settings, llm_client=_BoomLLM(settings))
    matter = MatterAdapter(registry=registry, settings=settings, transport=FakeMatterPort())
    coord = CommandCoordinator(settings=settings, registry=registry, intent_router=router, matter_adapter=matter)
    pipeline = SmartRVPipeline(coordinator=coord)

    out_off = pipeline.process_text_command("turn off bathroom")
    assert out_off["result"] == "confirmed"
    assert out_off["actual"] == "OFF"

    out_tap = pipeline.process_tap_command("kitchen", "STATUS")
    assert out_tap["result"] == "confirmed"

    out_unclear = pipeline.process_text_command("do something nice")
    assert out_unclear["result"] == "clarification"
