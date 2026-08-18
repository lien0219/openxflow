"""In-process stream response coordination for WeCom AI Bot webhook callbacks."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from dataclasses import dataclass
from uuid import UUID
from weakref import WeakKeyDictionary

from lfx.log.logger import logger

from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.adapters.wecom_ai import WeComAIBotChannelAdapter
from langflow.channels.domain.models import ChannelEvent, ChannelMessage
from langflow.channels.services.deduplication import ChannelEventDeduplicator
from langflow.channels.services.dispatch import ChannelDispatchService
from langflow.channels.services.message_planning import plan_channel_messages
from langflow.channels.services.message_records import (
    safe_mark_inbound_message,
    safe_record_inbound_message,
    safe_record_outbound_message,
)
from langflow.services.database.models.channel.message_model import ChannelMessageRecordStatus
from langflow.services.database.models.channel.model import ChannelConnection
from langflow.services.deps import session_scope

_DEFAULT_TTL_SECONDS = 15 * 60
_DEFAULT_PENDING_TEXT = "⏳ 正在处理中，请稍候…"
_DEFAULT_FAILURE_TEXT = "工作流执行失败，请在 OpenXFlow 运行记录中查看错误详情。"
_DUPLICATE_FINISHED_TEXT = "该消息已处理，请勿重复提交。"


@dataclass
class WeComAIStreamState:
    stream_id: str
    event_id: str
    content: str = _DEFAULT_PENDING_TEXT
    finished: bool = False
    failed: bool = False
    updated_at: float = 0.0


class WeComAIResponseRuntime:
    """Keep stream state per event loop without sharing asyncio primitives across reloads."""

    def __init__(self, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = max(60.0, ttl_seconds)
        self._lock = asyncio.Lock()
        self._by_stream: dict[str, WeComAIStreamState] = {}
        self._stream_by_event: dict[str, str] = {}

    async def reserve(self, connection_id: UUID, event_id: str) -> tuple[WeComAIStreamState, bool]:
        now = time.monotonic()
        key = f"{connection_id}:{event_id}"
        async with self._lock:
            self._cleanup_locked(now)
            existing_stream = self._stream_by_event.get(key)
            if existing_stream is not None:
                existing = self._by_stream.get(existing_stream)
                if existing is not None:
                    return self._snapshot(existing), False
            digest = hashlib.sha256(key.encode()).hexdigest()[:32]
            stream_id = f"oxf_{digest}"
            state = WeComAIStreamState(stream_id=stream_id, event_id=event_id, updated_at=now)
            self._by_stream[stream_id] = state
            self._stream_by_event[key] = stream_id
            return self._snapshot(state), True

    async def poll(self, stream_id: str) -> WeComAIStreamState | None:
        now = time.monotonic()
        async with self._lock:
            self._cleanup_locked(now)
            state = self._by_stream.get(stream_id)
            return self._snapshot(state) if state is not None else None

    async def complete(self, stream_id: str, content: str) -> None:
        async with self._lock:
            state = self._by_stream.get(stream_id)
            if state is None:
                return
            state.content = content
            state.finished = True
            state.failed = False
            state.updated_at = time.monotonic()

    async def fail(self, stream_id: str, content: str = _DEFAULT_FAILURE_TEXT) -> None:
        async with self._lock:
            state = self._by_stream.get(stream_id)
            if state is None:
                return
            state.content = content
            state.finished = True
            state.failed = True
            state.updated_at = time.monotonic()

    @staticmethod
    def _snapshot(state: WeComAIStreamState) -> WeComAIStreamState:
        return WeComAIStreamState(
            stream_id=state.stream_id,
            event_id=state.event_id,
            content=state.content,
            finished=state.finished,
            failed=state.failed,
            updated_at=state.updated_at,
        )

    def _cleanup_locked(self, now: float) -> None:
        expired = [
            stream_id for stream_id, state in self._by_stream.items() if now - state.updated_at > self.ttl_seconds
        ]
        if not expired:
            return
        expired_set = set(expired)
        for stream_id in expired:
            self._by_stream.pop(stream_id, None)
        for key, stream_id in tuple(self._stream_by_event.items()):
            if stream_id in expired_set:
                self._stream_by_event.pop(key, None)


_RUNTIME_GUARD = threading.Lock()
_RUNTIMES: WeakKeyDictionary[asyncio.AbstractEventLoop, WeComAIResponseRuntime] = WeakKeyDictionary()


def wecom_ai_response_runtime() -> WeComAIResponseRuntime:
    loop = asyncio.get_running_loop()
    with _RUNTIME_GUARD:
        runtime = _RUNTIMES.get(loop)
        if runtime is None:
            runtime = WeComAIResponseRuntime()
            _RUNTIMES[loop] = runtime
        return runtime


def _response_text(adapter: WeComAIBotChannelAdapter, response: ChannelMessage | None) -> str:
    if response is None:
        return ""
    rendered: list[str] = []
    for part in plan_channel_messages("wecom", response):
        text = adapter.render_message_text(part)
        if text:
            rendered.append(text)
    return "\n\n".join(rendered)


async def process_wecom_ai_event(
    *,
    connection_id: UUID,
    event: ChannelEvent,
    stream_id: str,
) -> None:
    """Run one WeCom AI Bot event through normal routing and publish its stream result."""
    runtime = wecom_ai_response_runtime()
    try:
        async with session_scope() as session:
            connection = await session.get(ChannelConnection, connection_id)
            if connection is None or not connection.enabled or connection.connection_mode != "ai_bot":
                await runtime.fail(stream_id, "企业微信智能机器人连接已停用或不存在。")
                return
            adapter = build_channel_adapter(connection)
            if not isinstance(adapter, WeComAIBotChannelAdapter):
                await runtime.fail(stream_id, "企业微信智能机器人连接配置无效。")
                return

            payload = json.dumps(event.raw_payload, ensure_ascii=False, separators=(",", ":")).encode()
            deduplicator = ChannelEventDeduplicator(session)
            receipt = await deduplicator.claim(event, payload)
            if receipt is None:
                await runtime.complete(stream_id, _DUPLICATE_FINISHED_TEXT)
                return

            try:
                await safe_record_inbound_message(event)
                dispatcher = ChannelDispatchService(session, connection, adapter)
                response = await asyncio.wait_for(
                    dispatcher.handle(event),
                    timeout=float(connection.task_timeout_seconds),
                )
                content = adapter.truncate_utf8(_response_text(adapter, response), 2048)
                await safe_record_outbound_message(
                    event,
                    response or ChannelMessage(text=""),
                    status=ChannelMessageRecordStatus.SENT.value,
                    provider_message_id=stream_id,
                )
                await safe_mark_inbound_message(event, status=ChannelMessageRecordStatus.PROCESSED.value)
                await deduplicator.complete(receipt)
            except asyncio.TimeoutError as exc:
                await deduplicator.fail(receipt, exc)
                await safe_mark_inbound_message(
                    event,
                    status=ChannelMessageRecordStatus.FAILED.value,
                    error=exc,
                )
                await runtime.fail(stream_id, "工作流执行超时，请稍后重试。")
                return
            except asyncio.CancelledError as exc:
                await deduplicator.fail(receipt, exc)
                await runtime.fail(stream_id, "工作流执行已取消，请稍后重试。")
                raise
            except Exception as exc:  # noqa: BLE001
                await deduplicator.fail(receipt, exc)
                await safe_mark_inbound_message(
                    event,
                    status=ChannelMessageRecordStatus.FAILED.value,
                    error=exc,
                )
                await runtime.fail(stream_id)
                raise
            else:
                await runtime.complete(stream_id, content)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        await logger.aexception("WeCom AI Bot event processing failed", exception=exc)
        await runtime.fail(stream_id)
