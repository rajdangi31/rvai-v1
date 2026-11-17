"""FastAPI Backend, CommandCoordinator, ObservationStore, and MatterPort tests."""

from __future__ import annotations

import asyncio
import io
import json
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from ai_pipeline.intent_router import IntentRouter
from ai_pipeline.llm_client import LLMClient, LLMError
from ai_pipeline.stt_engine import STTEngine, StubSTTBackend
from backend.app import create_app
from backend.coordinator import CommandCoordinator
from matter_bridge.adapter import MatterAdapter
from tests.fakes.matter_port import FakeMatterPort

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


class _OfflineLLM(LLMClient):
    def generate_completion(self, user_prompt: str, **kwargs) -> str:
        raise LLMError("offline test")


def _wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 1600)
    return buf.getvalue()


def _make_stack(registry, settings, *, stt_text: str = "turn on the galley"):
    settings.confirm_timeout_seconds = 0.2
    fake = FakeMatterPort()
    matter = MatterAdapter(registry=registry, settings=settings, transport=fake)
    stt = STTEngine(settings=settings, backend=StubSTTBackend(stt_text))
    router = IntentRouter(
        registry=registry,
        settings=settings,
        llm_client=_OfflineLLM(settings),
        stt_engine=stt,
    )
    coord = CommandCoordinator(
        settings=settings,
        registry=registry,
        intent_router=router,
        matter_adapter=matter,
    )
    return coord, fake


def _load_schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def test_fastapi_command_text_audio_and_state(registry, settings):
    coord, _fake = _make_stack(registry, settings)
    app = create_app(coord)

    with TestClient(app) as client:
        # After startup reads, fake MatterPort establishes OFF/fresh for commissioned targets.
        initial = {item["target"]: item for item in client.get("/api/state").json()}
        assert initial["kitchen"]["actual"] == "OFF"
        assert initial["kitchen"]["fresh"] is True
        assert initial["kitchen"]["fault_available"] is True

        res = client.post("/api/command", json={"target": "kitchen", "cmd": "ON"})
        assert res.status_code == 200
        body = res.json()
        assert body["result"] == "confirmed"
        assert body["actual"] == "ON"
        assert body["fresh"] is True
        assert "fault_available" in body

        assert client.post("/api/command", json={"target": "kitchen", "cmd": "ON", "extra": 1}).status_code == 422
        assert client.post("/api/command", json={"target": "kitchen", "action": "ON"}).status_code == 422

        blocked = client.post("/api/command", json={"target": "all", "cmd": "OFF"}).json()
        assert blocked["result"] == "blocked"
        assert blocked["reason_code"] == "all_denied"

        txt = client.post("/api/text", json={"text": "turn off the galley"}).json()
        assert txt["result"] == "confirmed"
        assert txt["target"] == "kitchen"
        assert txt["actual"] == "OFF"

        clar = client.post("/api/text", json={"text": "turn on kitchen and bedroom"}).json()
        assert clar["result"] == "clarification"

        aud = client.post("/api/audio", content=_wav_bytes(), headers={"Content-Type": "audio/wav"}).json()
        assert aud["result"] == "confirmed"
        assert aud["target"] == "kitchen"
        assert aud["actual"] == "ON"


def test_websocket_snapshot_and_manual_change_updates(registry, settings):
    coord, fake = _make_stack(registry, settings)
    app = create_app(coord)

    with TestClient(app) as client:
        with client.websocket_connect("/api/state") as ws:
            snap = ws.receive_json()
            assert snap["type"] == "snapshot"
            assert len(snap["states"]) == 5

            asyncio.run(fake.emit_manual_change("bedroom", "ON"))
            event = ws.receive_json()
            assert event["type"] == "state"
            assert event["state"]["target"] == "bedroom"
            assert event["state"]["actual"] == "ON"
            assert event["state"]["fresh"] is True
            assert event["state"]["fault_available"] is True


def test_fault_is_displayed_but_does_not_block_on(registry, settings):
    coord, fake = _make_stack(registry, settings)

    async def scenario():
        await coord.start()
        await fake.emit_manual_change("exterior", "OFF", fault="overcurrent")

        allowed_on = await coord.handle_tap("exterior", "ON")
        assert allowed_on.result == "confirmed"
        assert allowed_on.fault == "overcurrent"
        assert allowed_on.fault_available is True

        status = await coord.handle_tap("exterior", "STATUS")
        assert status.result == "confirmed"
        assert status.fault == "overcurrent"
        await coord.stop()

    asyncio.run(scenario())


def test_timeout_returns_unconfirmed_and_pending_blocks_overlap(registry, settings):
    coord, fake = _make_stack(registry, settings)

    async def scenario():
        await coord.start()
        fake.set_drop("bathroom", True)
        task1 = asyncio.create_task(coord.handle_tap("bathroom", "ON"))
        await asyncio.sleep(0.02)
        busy = await coord.handle_tap("bathroom", "OFF")
        assert busy.result == "blocked"
        assert busy.reason_code == "target_busy"

        first = await task1
        assert first.result == "unconfirmed"
        assert coord.observations.get("bathroom").actual == "OFF"
        await coord.stop()

    asyncio.run(scenario())


def test_http_busy_returns_409(registry, settings):
    coord, _fake = _make_stack(registry, settings)
    app = create_app(coord)

    with TestClient(app) as client:
        view = coord.observations.get("kitchen")
        assert view is not None
        coord.observations._views["kitchen"] = view.model_copy(update={"pending": "ON"})
        res = client.post("/api/command", json={"target": "kitchen", "cmd": "OFF"})
        assert res.status_code == 409
        body = res.json()
        assert body["result"] == "blocked"
        assert body["reason_code"] == "target_busy"


def test_contradictory_report_waits_for_matching_observation(registry, settings):
    coord, fake = _make_stack(registry, settings)
    settings.confirm_timeout_seconds = 0.5

    async def scenario():
        await coord.start()
        await fake.invoke_off(registry.get("kitchen"))
        fake.set_stale_first("kitchen", True)
        outcome = await coord.handle_tap("kitchen", "ON")
        assert outcome.result == "confirmed"
        assert outcome.actual == "ON"
        await coord.stop()

    asyncio.run(scenario())


def test_old_cached_state_cannot_confirm_new_command(registry, settings):
    coord, fake = _make_stack(registry, settings)

    async def scenario():
        await coord.start()
        await fake.emit_manual_change("kitchen", "ON")
        fake.set_drop("kitchen", True)
        outcome = await coord.handle_tap("kitchen", "OFF")
        assert outcome.result == "unconfirmed"
        assert coord.observations.get("kitchen").actual == "ON"
        await coord.stop()

    asyncio.run(scenario())


def test_contract_outcome_and_ws_shapes(registry, settings):
    outcome_schema = _load_schema("command_outcome.schema.json")
    state_schema = _load_schema("state_view.schema.json")
    assert "result" in outcome_schema["required"]
    assert "fault_available" in state_schema["required"]

    coord, _fake = _make_stack(registry, settings)
    app = create_app(coord)
    with TestClient(app) as client:
        body = client.post("/api/command", json={"target": "kitchen", "cmd": "STATUS"}).json()
        for key in outcome_schema["required"]:
            assert key in body
        for key in ("actual", "fault", "fault_available", "fresh"):
            assert key in body

        with client.websocket_connect("/api/state") as ws:
            snap = ws.receive_json()
            assert set(snap.keys()) == {"type", "states"}
            assert snap["type"] == "snapshot"
            for state in snap["states"]:
                for key in state_schema["required"]:
                    assert key in state
