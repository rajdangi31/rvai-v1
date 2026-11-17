"""
Raj: FastAPI Backend Ingress & Display WebSocket.

Contract: RVAI/runtime/contracts/FRONTEND_CONTRACT.md v0.1
  POST /api/command  {"target","cmd"} -> outcome (result/actual/fault/fault_available/fresh)
  WS   /api/state    snapshot.states / state.state
  POST /api/text     later-stage language path (same command service)
  422 invalid body · 409 target busy · 503 backend not ready
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict, List, Literal, Optional, Union

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.coordinator import CommandCoordinator
from shared.schemas import CommandOutcome, SafetyReasonCode, TargetStateView


class TapPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    cmd: Literal["ON", "OFF", "STATUS"]

    @field_validator("cmd", mode="before")
    @classmethod
    def normalize_cmd(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class TextPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)


def create_app(coordinator: Optional[CommandCoordinator] = None) -> FastAPI:
    coord = coordinator or CommandCoordinator()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await coord.start()
        try:
            yield
        finally:
            await coord.stop()

    app = FastAPI(title="Smart RV V1 Backend (Raj)", version="0.4.0", lifespan=lifespan)
    app.state.coordinator = coord

    def _ensure_ready() -> None:
        if not coord.ready:
            raise HTTPException(status_code=503, detail="Backend is not ready.")

    def _outcome_response(outcome: CommandOutcome) -> Union[JSONResponse, CommandOutcome]:
        if outcome.reason_code == SafetyReasonCode.TARGET_BUSY.value:
            return JSONResponse(status_code=409, content=outcome.model_dump())
        return outcome

    @app.get("/api/health")
    async def health() -> Dict[str, object]:
        return {
            "status": "ok" if coord.ready else "starting",
            "ready": coord.ready,
            "matter_backend": coord.settings.matter_backend,
            "llm_model": coord.settings.llm_model,
            "stt_backend": coord.settings.stt_backend,
            "tts_backend": coord.settings.tts_backend,
            "targets": coord.registry.ids(),
            "commissioned": coord.registry.commissioned_ids(),
        }

    @app.get("/api/ready")
    async def ready() -> Any:
        if not coord.ready:
            return JSONResponse(status_code=503, content={"ready": False})
        return {"ready": True}

    @app.post("/api/command", response_model=CommandOutcome)
    async def post_command(body: TapPayload) -> Any:
        _ensure_ready()
        return _outcome_response(await coord.handle_tap(body.target, body.cmd))

    @app.post("/api/text", response_model=CommandOutcome)
    async def post_text(body: TextPayload) -> Any:
        _ensure_ready()
        return _outcome_response(await coord.handle_text(body.text))

    @app.post("/api/audio", response_model=CommandOutcome)
    async def post_audio(request: Request, file: Optional[UploadFile] = File(default=None)) -> Any:
        _ensure_ready()
        data = await file.read() if file is not None else await request.body()
        if not data:
            raise HTTPException(status_code=400, detail="Empty audio payload.")
        return _outcome_response(await coord.handle_audio(data))

    @app.get("/api/state", response_model=List[TargetStateView])
    async def get_state() -> List[TargetStateView]:
        _ensure_ready()
        return coord.observations.snapshot()

    @app.websocket("/api/state")
    async def ws_state(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json(
            {"type": "snapshot", "states": [v.model_dump() for v in coord.observations.snapshot()]}
        )

        async def push(event: Dict[str, object]) -> None:
            await websocket.send_json(event)

        coord.observations.subscribe(push)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            coord.observations.unsubscribe(push)

    return app


app = create_app()
