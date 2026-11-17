"""
Raj: JSON <-> Matter Translator and Controller.

MatterPort boundary (runtime/README.md):
  start/stop; invoke_on; invoke_off; read_onoff; continuous observation stream.

Transports (RVAI_MATTER_BACKEND):
  - chip_tool:     chip-tool subprocess over OTBR + RCP (default; proves Thread path first)
  - matter_server: Python Matter Server JSON WebSocket (loopback :5580/ws)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import uuid4

from shared.schemas import Action, ActualState, DeviceObservation
from shared.settings import Settings, get_settings
from shared.targets import TargetRecord, TargetRegistry, get_target_registry

logger = logging.getLogger(__name__)

ONOFF_CLUSTER_ID = 6
ONOFF_ATTR_ID = 0

ObservationCallback = Callable[[DeviceObservation], Optional[Awaitable[Any]]]


class MatterError(RuntimeError):
    """Raised when the Matter controller / transport rejects or fails a call."""


def _bool_to_actual(value: object) -> Optional[ActualState]:
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, int) and value in (0, 1):
        return "ON" if value == 1 else "OFF"
    if isinstance(value, str):
        token = value.strip().upper()
        if token in {"ON", "TRUE", "1"}:
            return "ON"
        if token in {"OFF", "FALSE", "0"}:
            return "OFF"
    return None


class MatterPort(ABC):
    """Controller boundary used by the command service."""

    @abstractmethod
    async def invoke_on(self, target: TargetRecord) -> None:
        """Send Matter On. ACK != physical confirmation."""

    @abstractmethod
    async def invoke_off(self, target: TargetRecord) -> None:
        """Send Matter Off. ACK != physical confirmation."""

    @abstractmethod
    async def read_onoff(self, target: TargetRecord) -> DeviceObservation:
        """Read Matter OnOff attribute and emit a normalized observation."""

    async def start(self, on_observation: ObservationCallback) -> None:
        """Optional background listener for unsolicited Matter attribute reports."""

    async def stop(self) -> None:
        """Clean shutdown hook."""


# Back-compat alias.
MatterTransport = MatterPort


class MatterServerTransport(MatterPort):
    """
    Python Matter Server WebSocket client (ws://127.0.0.1:5580/ws).
    Reconnects on drop, marks observations stale via callback policy in the adapter.
    """

    def __init__(self, ws_url: str, registry: TargetRegistry, *, reconnect_seconds: float = 2.0):
        self.ws_url = ws_url
        self.registry = registry
        self.reconnect_seconds = reconnect_seconds
        self._ws: Any = None
        self._pending: Dict[str, asyncio.Future[Any]] = {}
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._callback: Optional[ObservationCallback] = None
        self._stop = asyncio.Event()
        self._connected = asyncio.Event()

    async def start(self, on_observation: ObservationCallback) -> None:
        self._callback = on_observation
        self._stop.clear()
        self._reader_task = asyncio.create_task(self._connection_loop())
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=10.0)
        except asyncio.TimeoutError as exc:
            raise MatterError(f"Could not connect to Matter Server at {self.ws_url}") from exc

    async def stop(self) -> None:
        self._stop.set()
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        self._connected.clear()

    async def invoke_on(self, target: TargetRecord) -> None:
        await self._device_command(target, "On")
        await self.read_onoff(target)

    async def invoke_off(self, target: TargetRecord) -> None:
        await self._device_command(target, "Off")
        await self.read_onoff(target)

    async def read_onoff(self, target: TargetRecord) -> DeviceObservation:
        attr_path = f"{target.endpoint_id}/{ONOFF_CLUSTER_ID}/{ONOFF_ATTR_ID}"
        result = await self._rpc(
            "read_attribute",
            {"node_id": target.node_id, "attribute_path": attr_path},
        )
        raw_val = result.get(attr_path) if isinstance(result, dict) else result
        obs = DeviceObservation(
            target=target.id,
            actual=_bool_to_actual(raw_val),
            fault=None,
            fault_available=False,
            fresh=True,
        )
        await self._emit(obs)
        return obs

    async def _device_command(self, target: TargetRecord, command_name: str) -> None:
        await self._rpc(
            "device_command",
            {
                "node_id": target.node_id,
                "endpoint_id": target.endpoint_id,
                "cluster_id": ONOFF_CLUSTER_ID,
                "command_name": command_name,
                "payload": {},
            },
        )

    async def _rpc(self, command: str, args: Dict[str, Any]) -> Any:
        if self._ws is None or not self._connected.is_set():
            raise MatterError("Matter Server WebSocket is not connected.")
        msg_id = str(uuid4())
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut
        await self._ws.send(json.dumps({"message_id": msg_id, "command": command, "args": args}))
        try:
            return await asyncio.wait_for(fut, timeout=10.0)
        finally:
            self._pending.pop(msg_id, None)

    async def _connection_loop(self) -> None:
        try:
            import websockets  # type: ignore
        except ImportError as exc:
            raise MatterError("Install websockets to use matter_server backend.") from exc

        while not self._stop.is_set():
            try:
                self._ws = await websockets.connect(self.ws_url)
                await self._ws.recv()  # greeting
                await self._ws.send(json.dumps({"message_id": str(uuid4()), "command": "start_listening", "args": {}}))
                self._connected.set()
                await self._reader_loop()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Matter Server connection issue: %s", exc)
            finally:
                self._connected.clear()
                if self._ws is not None:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(MatterError("Matter Server disconnected"))
                self._pending.clear()
            if self._stop.is_set():
                break
            await asyncio.sleep(self.reconnect_seconds)

    async def _reader_loop(self) -> None:
        assert self._ws is not None
        async for raw in self._ws:
            frame = json.loads(raw)
            msg_id = frame.get("message_id")
            if msg_id and msg_id in self._pending:
                fut = self._pending[msg_id]
                if "error_code" in frame:
                    fut.set_exception(MatterError(frame.get("details") or "Matter RPC error"))
                else:
                    fut.set_result(frame.get("result"))
            elif frame.get("event") == "attribute_updated":
                await self._handle_attribute_event(frame.get("data"))

    async def _handle_attribute_event(self, data: Any) -> None:
        if not isinstance(data, list) or len(data) < 3:
            return
        node_id, path, value = data[0], str(data[1]), data[2]
        parts = path.split("/")
        if len(parts) != 3:
            return
        endpoint_id, cluster_id, attr_id = int(parts[0]), int(parts[1]), int(parts[2])
        if cluster_id != ONOFF_CLUSTER_ID or attr_id != ONOFF_ATTR_ID:
            return
        record = self.registry.by_node_endpoint(int(node_id), endpoint_id)
        if record is None:
            return
        await self._emit(
            DeviceObservation(
                target=record.id,
                actual=_bool_to_actual(value),
                fault=None,
                fault_available=False,
                fresh=True,
            )
        )

    async def _emit(self, obs: DeviceObservation) -> None:
        if self._callback is not None:
            maybe = self._callback(obs)
            if asyncio.iscoroutine(maybe):
                await maybe


class ChipToolTransport(MatterPort):
    """Subprocess adapter for `chip-tool onoff on|off|read on-off <node> <ep>`."""

    _BOOL_RE = re.compile(r"OnOff:\s*(TRUE|FALSE|1|0)", re.IGNORECASE)

    def __init__(self, binary: str = "chip-tool"):
        self.binary = binary
        self._callback: Optional[ObservationCallback] = None

    async def start(self, on_observation: ObservationCallback) -> None:
        self._callback = on_observation

    async def invoke_on(self, target: TargetRecord) -> None:
        await self._run(["onoff", "on", str(target.node_id), str(target.endpoint_id)])
        await self.read_onoff(target)

    async def invoke_off(self, target: TargetRecord) -> None:
        await self._run(["onoff", "off", str(target.node_id), str(target.endpoint_id)])
        await self.read_onoff(target)

    async def read_onoff(self, target: TargetRecord) -> DeviceObservation:
        output = await self._run(
            ["onoff", "read", "on-off", str(target.node_id), str(target.endpoint_id)]
        )
        match = self._BOOL_RE.search(output)
        obs = DeviceObservation(
            target=target.id,
            actual=_bool_to_actual(match.group(1)) if match else None,
            fault=None,
            fault_available=False,
            fresh=True,
        )
        if self._callback is not None:
            maybe = self._callback(obs)
            if asyncio.iscoroutine(maybe):
                await maybe
        return obs

    async def _run(self, args: list[str]) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError as exc:
            raise MatterError(f"'{self.binary}' binary not found on PATH") from exc
        stdout, _ = await proc.communicate()
        text = stdout.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise MatterError(f"chip-tool failed ({proc.returncode}): {text[-240:]}")
        return text


class MatterAdapter:
    """High-level JSON <-> Matter bridge used by Backend CommandCoordinator."""

    def __init__(
        self,
        registry: Optional[TargetRegistry] = None,
        settings: Optional[Settings] = None,
        transport: Optional[MatterPort] = None,
    ):
        self.settings = settings or get_settings()
        self.registry = registry or get_target_registry(str(self.settings.resolved_targets_path()))
        self.transport = transport or self._build_transport()
        self._on_observation: Optional[ObservationCallback] = None

    def _build_transport(self) -> MatterPort:
        mode = self.settings.matter_backend
        if mode == "matter_server":
            return MatterServerTransport(
                self.settings.matter_server_ws_url,
                self.registry,
                reconnect_seconds=self.settings.matter_reconnect_seconds,
            )
        if mode == "chip_tool":
            return ChipToolTransport(self.settings.chip_tool_binary)
        raise ValueError(f"Unsupported matter_backend: {mode}")

    async def start(self, on_observation: ObservationCallback) -> None:
        async def _wrapped(obs: DeviceObservation):
            maybe = on_observation(obs)
            if asyncio.iscoroutine(maybe):
                await maybe

        self._on_observation = _wrapped
        await self.transport.start(_wrapped)

    async def stop(self) -> None:
        await self.transport.stop()

    async def invoke_on(self, target_id: str) -> None:
        await self.transport.invoke_on(self._require(target_id))

    async def invoke_off(self, target_id: str) -> None:
        await self.transport.invoke_off(self._require(target_id))

    async def read_onoff(self, target_id: str) -> DeviceObservation:
        return await self.transport.read_onoff(self._require(target_id))

    async def dispatch(self, target_id: str, action: Action) -> None:
        if action == "ON":
            await self.invoke_on(target_id)
        elif action == "OFF":
            await self.invoke_off(target_id)
        elif action == "STATUS":
            await self.read_onoff(target_id)
        else:
            raise MatterError(f"Unsupported action '{action}'")

    def _require(self, target_id: str) -> TargetRecord:
        record = self.registry.get(target_id)
        if record is None:
            raise MatterError(f"Unknown target '{target_id}'")
        if not record.commissioned:
            raise MatterError(f"Target '{target_id}' is not commissioned")
        return record
