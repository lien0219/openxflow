"""Lifecycle-managed DingTalk Stream clients for enabled channel connections."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import UUID

from filelock import FileLock, Timeout as FileLockTimeout
from lfx.log.logger import logger
from sqlmodel import select

from langflow.channels.adapters.dingtalk_resilient import ResilientDingTalkChannelAdapter
from langflow.channels.domain.exceptions import DuplicateChannelEventError
from langflow.channels.security.credentials import decrypt_credentials
from langflow.channels.services.deduplication import ChannelEventDeduplicator
from langflow.channels.services.dispatch import ChannelDispatchService
from langflow.channels.services.gateway import ChannelGateway
from langflow.channels.services.runtime_config import channel_streams_enabled
from langflow.channels.services.timing_metrics import record_stream_callback
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConnectionStatus,
)
from langflow.services.deps import session_scope

_REFRESH_SECONDS = 15.0
_MAX_RECONNECT_SECONDS = 60.0


@dataclass(frozen=True)
class DingTalkStreamRuntimeSnapshot:
    """Process-local aggregate state for lifecycle-managed DingTalk Stream clients."""

    running_managers: int
    leader_managers: int
    managed_clients: int
    sync_errors_total: int
    connection_errors_total: int
    reconnect_attempts_total: int
    successful_sync_total: int
    last_successful_sync_timestamp_seconds: float


class _DingTalkStreamRuntimeRegistry:
    """Track scalar Stream state without retaining event-loop-bound tasks or managers."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._states: dict[object, tuple[bool, int]] = {}
        self._sync_errors_total = 0
        self._connection_errors_total = 0
        self._reconnect_attempts_total = 0
        self._successful_sync_total = 0
        self._last_successful_sync_timestamp_seconds = 0.0

    def register(self, token: object) -> None:
        with self._lock:
            self._states[token] = (False, 0)

    def update(self, token: object, *, leader: bool, managed_clients: int) -> None:
        if managed_clients < 0:
            raise ValueError("managed_clients must be non-negative")
        with self._lock:
            if token in self._states:
                self._states[token] = (leader, managed_clients)

    def unregister(self, token: object) -> None:
        with self._lock:
            self._states.pop(token, None)

    def record_sync_error(self) -> None:
        with self._lock:
            self._sync_errors_total += 1

    def record_connection_error(self) -> None:
        with self._lock:
            self._connection_errors_total += 1

    def record_reconnect_attempt(self) -> None:
        with self._lock:
            self._reconnect_attempts_total += 1

    def record_successful_sync(self, timestamp_seconds: float | None = None) -> None:
        timestamp = time.time() if timestamp_seconds is None else timestamp_seconds
        if timestamp < 0:
            raise ValueError("timestamp_seconds must be non-negative")
        with self._lock:
            self._successful_sync_total += 1
            self._last_successful_sync_timestamp_seconds = timestamp

    def snapshot(self) -> DingTalkStreamRuntimeSnapshot:
        with self._lock:
            states = tuple(self._states.values())
            sync_errors_total = self._sync_errors_total
            connection_errors_total = self._connection_errors_total
            reconnect_attempts_total = self._reconnect_attempts_total
            successful_sync_total = self._successful_sync_total
            last_successful_sync_timestamp_seconds = self._last_successful_sync_timestamp_seconds
        return DingTalkStreamRuntimeSnapshot(
            running_managers=len(states),
            leader_managers=sum(1 for leader, _managed in states if leader),
            managed_clients=sum(managed for _leader, managed in states),
            sync_errors_total=sync_errors_total,
            connection_errors_total=connection_errors_total,
            reconnect_attempts_total=reconnect_attempts_total,
            successful_sync_total=successful_sync_total,
            last_successful_sync_timestamp_seconds=last_successful_sync_timestamp_seconds,
        )

    def reset(self) -> None:
        with self._lock:
            self._states.clear()
            self._sync_errors_total = 0
            self._connection_errors_total = 0
            self._reconnect_attempts_total = 0
            self._successful_sync_total = 0
            self._last_successful_sync_timestamp_seconds = 0.0


_stream_runtime_registry = _DingTalkStreamRuntimeRegistry()


def dingtalk_stream_runtime_snapshot() -> DingTalkStreamRuntimeSnapshot:
    return _stream_runtime_registry.snapshot()


def reset_dingtalk_stream_runtime_for_testing() -> None:
    _stream_runtime_registry.reset()


@dataclass
class _ManagedStream:
    fingerprint: str
    task: asyncio.Task[None]


async def process_dingtalk_stream_payload(connection_id: UUID, data: dict[str, Any]) -> None:
    """Process one authenticated SDK callback through the normal gateway pipeline."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    async with session_scope() as session:
        connection = await session.get(ChannelConnection, connection_id)
        if connection is None or not connection.enabled or connection.channel_type != "dingtalk":
            return
        credentials = decrypt_credentials(connection.credentials_encrypted)
        adapter = ResilientDingTalkChannelAdapter(
            connection.id,
            client_id=credentials.get("client_id", ""),
            client_secret=credentials.get("client_secret", ""),
            robot_code=credentials.get("robot_code"),
            api_base_url=str(connection.settings_data.get("api_base_url", "https://api.dingtalk.com")),
            stream_authenticated=True,
        )
        gateway = ChannelGateway()
        gateway.register_adapter(connection.id, adapter)
        deduplicator = ChannelEventDeduplicator(session)
        dispatcher = ChannelDispatchService(session, connection, adapter)
        try:
            await gateway.receive(
                connection.id,
                {},
                payload,
                dispatcher.handle,
                deduplicator=deduplicator,
            )
        except DuplicateChannelEventError:
            await session.rollback()
            return
        except Exception:
            await session.rollback()
            raise
        await session.commit()


class DingTalkStreamManager:
    """Keep one Stream SDK connection per enabled DingTalk connection."""

    def __init__(self) -> None:
        lock_name = hashlib.sha256(str(Path.cwd()).encode()).hexdigest()[:16]
        self._leader_lock = FileLock(Path(tempfile.gettempdir()) / f"openxflow-dingtalk-{lock_name}.lock")
        self._has_leader_lock = False
        self._managed: dict[UUID, _ManagedStream] = {}
        self._stop_event = asyncio.Event()
        self._runtime_token = object()

    async def run(self) -> None:
        if not channel_streams_enabled():
            await logger.adebug("Channel Stream clients disabled by LANGFLOW_CHANNEL_STREAMS_ENABLED")
            return
        _stream_runtime_registry.register(self._runtime_token)
        try:
            while not self._stop_event.is_set():
                if not self._has_leader_lock:
                    await self._try_become_leader()
                if self._has_leader_lock:
                    try:
                        await self._sync_connections()
                    except asyncio.CancelledError:
                        raise
                    except Exception:  # noqa: BLE001
                        _stream_runtime_registry.record_sync_error()
                        await logger.aexception("DingTalk Stream connection synchronization failed")
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=_REFRESH_SECONDS)
                except TimeoutError:
                    pass
        finally:
            await self._cancel_all()
            if self._has_leader_lock:
                with suppress(Exception):
                    await asyncio.to_thread(self._leader_lock.release)
                self._has_leader_lock = False
            self._publish_runtime_state()
            _stream_runtime_registry.unregister(self._runtime_token)

    async def stop(self) -> None:
        self._stop_event.set()
        await self._cancel_all()

    async def _try_become_leader(self) -> None:
        try:
            await asyncio.to_thread(self._leader_lock.acquire, timeout=0)
        except FileLockTimeout:
            return
        self._has_leader_lock = True
        self._publish_runtime_state()
        await logger.ainfo("This worker is managing DingTalk Stream connections")

    async def _sync_connections(self) -> None:
        async with session_scope() as session:
            statement = select(ChannelConnection).where(
                ChannelConnection.channel_type == "dingtalk",
                ChannelConnection.enabled.is_(True),
                ChannelConnection.connection_mode == "stream",
            )
            connections = list((await session.exec(statement)).all())

        desired = {connection.id: self._fingerprint(connection) for connection in connections}
        for connection_id, managed in list(self._managed.items()):
            if connection_id not in desired or managed.fingerprint != desired[connection_id]:
                managed.task.cancel()
                with suppress(asyncio.CancelledError):
                    await managed.task
                self._managed.pop(connection_id, None)

        for connection in connections:
            if connection.id not in self._managed:
                task = asyncio.create_task(
                    self._run_connection(connection.id),
                    name=f"dingtalk-stream-{connection.id}",
                )
                self._managed[connection.id] = _ManagedStream(
                    fingerprint=desired[connection.id],
                    task=task,
                )
        self._publish_runtime_state()
        _stream_runtime_registry.record_successful_sync()

    async def _run_connection(self, connection_id: UUID) -> None:
        delay = 2.0
        attempt = 0
        while not self._stop_event.is_set():
            if attempt > 0:
                _stream_runtime_registry.record_reconnect_attempt()
            attempt += 1
            try:
                await self._run_sdk_client(connection_id)
                delay = 2.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                _stream_runtime_registry.record_connection_error()
                await self._set_status(connection_id, ChannelConnectionStatus.ERROR, str(exc))
                await logger.aexception("DingTalk Stream connection failed for %s", connection_id)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                except TimeoutError:
                    pass
                delay = min(_MAX_RECONNECT_SECONDS, delay * 2)

    async def _run_sdk_client(self, connection_id: UUID) -> None:
        try:
            import dingtalk_stream
        except ImportError as exc:
            raise RuntimeError(
                "DingTalk Stream SDK is not installed; install dingtalk-stream>=0.24.3"
            ) from exc

        async with session_scope() as session:
            connection = await session.get(ChannelConnection, connection_id)
            if connection is None or not connection.enabled:
                return
            credentials = decrypt_credentials(connection.credentials_encrypted)
            client_id = credentials.get("client_id", "")
            client_secret = credentials.get("client_secret", "")

        manager = self

        class OpenXFlowChatbotHandler(dingtalk_stream.ChatbotHandler):
            async def process(self, callback):  # type: ignore[no-untyped-def]
                started_at = time.perf_counter()
                success = False
                cancelled = False
                try:
                    try:
                        await process_dingtalk_stream_payload(connection_id, callback.data)
                    except ValueError as exc:
                        await logger.awarning("Invalid DingTalk Stream payload: %s", exc)
                        return dingtalk_stream.AckMessage.STATUS_BAD_REQUEST, str(exc)
                    except Exception as exc:  # noqa: BLE001
                        await logger.aexception("DingTalk Stream event processing failed")
                        return dingtalk_stream.AckMessage.STATUS_SYSTEM_EXCEPTION, str(exc)
                    await manager._set_status(connection_id, ChannelConnectionStatus.CONNECTED)
                    success = True
                    return dingtalk_stream.AckMessage.STATUS_OK, "OK"
                except asyncio.CancelledError:
                    cancelled = True
                    raise
                finally:
                    if not cancelled:
                        record_stream_callback(
                            success=success,
                            duration_seconds=time.perf_counter() - started_at,
                        )

        credential = dingtalk_stream.Credential(client_id, client_secret)
        client = dingtalk_stream.DingTalkStreamClient(credential)
        client.register_callback_handler(
            dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
            OpenXFlowChatbotHandler(),
        )
        await self._set_status(connection_id, ChannelConnectionStatus.CONNECTED)
        await client.start()

    async def _set_status(
        self,
        connection_id: UUID,
        status: ChannelConnectionStatus,
        error: str | None = None,
    ) -> None:
        async with session_scope() as session:
            connection = await session.get(ChannelConnection, connection_id)
            if connection is None:
                return
            connection.status = status.value
            connection.last_error = error[:2000] if error else None
            if status is ChannelConnectionStatus.CONNECTED:
                from datetime import datetime, timezone

                connection.last_connected_at = datetime.now(timezone.utc)
            session.add(connection)

    async def _cancel_all(self) -> None:
        tasks = [managed.task for managed in self._managed.values()]
        self._managed.clear()
        self._publish_runtime_state()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _publish_runtime_state(self) -> None:
        _stream_runtime_registry.update(
            self._runtime_token,
            leader=self._has_leader_lock,
            managed_clients=len(self._managed),
        )

    @staticmethod
    def _fingerprint(connection: ChannelConnection) -> str:
        raw = "|".join(
            (
                connection.credentials_encrypted,
                connection.connection_mode,
                str(connection.enabled),
                connection.updated_at.isoformat(),
            )
        )
        return hashlib.sha256(raw.encode()).hexdigest()


@asynccontextmanager
async def channel_stream_lifespan(_app):  # type: ignore[no-untyped-def]
    # Create lifecycle state per FastAPI lifespan invocation. This keeps test
    # clients, reloads, and repeated app factories from inheriting a stopped
    # asyncio.Event or tasks bound to a previous event loop.
    manager = DingTalkStreamManager()
    task = asyncio.create_task(manager.run(), name="channel-stream-manager")
    try:
        yield
    finally:
        await manager.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
