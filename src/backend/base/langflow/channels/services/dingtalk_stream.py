"""Lifecycle-managed DingTalk Stream clients for enabled channel connections."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from filelock import FileLock, Timeout as FileLockTimeout
from lfx.log.logger import logger
from sqlmodel import select

from langflow.channels.adapters.dingtalk import DingTalkChannelAdapter
from langflow.channels.domain.exceptions import DuplicateChannelEventError
from langflow.channels.security.credentials import decrypt_credentials
from langflow.channels.services.deduplication import ChannelEventDeduplicator
from langflow.channels.services.dispatch import ChannelDispatchService
from langflow.channels.services.gateway import ChannelGateway
from langflow.channels.services.runtime_config import channel_streams_enabled
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConnectionStatus,
)
from langflow.services.deps import session_scope

_REFRESH_SECONDS = 15.0
_MAX_RECONNECT_SECONDS = 60.0


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
        adapter = DingTalkChannelAdapter(
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

    async def run(self) -> None:
        if not channel_streams_enabled():
            await logger.adebug("Channel Stream clients disabled by LANGFLOW_CHANNEL_STREAMS_ENABLED")
            return
        try:
            while not self._stop_event.is_set():
                if not self._has_leader_lock:
                    await self._try_become_leader()
                if self._has_leader_lock:
                    await self._sync_connections()
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

    async def stop(self) -> None:
        self._stop_event.set()
        await self._cancel_all()

    async def _try_become_leader(self) -> None:
        try:
            await asyncio.to_thread(self._leader_lock.acquire, timeout=0)
        except FileLockTimeout:
            return
        self._has_leader_lock = True
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

    async def _run_connection(self, connection_id: UUID) -> None:
        delay = 2.0
        while not self._stop_event.is_set():
            try:
                await self._run_sdk_client(connection_id)
                delay = 2.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
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
                try:
                    await process_dingtalk_stream_payload(connection_id, callback.data)
                except ValueError as exc:
                    await logger.awarning("Invalid DingTalk Stream payload: %s", exc)
                    return dingtalk_stream.AckMessage.STATUS_BAD_REQUEST, str(exc)
                except Exception as exc:  # noqa: BLE001
                    await logger.aexception("DingTalk Stream event processing failed")
                    return dingtalk_stream.AckMessage.STATUS_SYSTEM_EXCEPTION, str(exc)
                await manager._set_status(connection_id, ChannelConnectionStatus.CONNECTED)
                return dingtalk_stream.AckMessage.STATUS_OK, "OK"

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
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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
