"""Background processing for provider webhooks after a fast acknowledgement."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from threading import Lock
from typing import Awaitable, Callable, TypeVar
from uuid import UUID

from lfx.log.logger import logger

from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.domain.exceptions import DuplicateChannelEventError
from langflow.channels.services.deduplication import ChannelEventDeduplicator
from langflow.channels.services.dispatch import ChannelDispatchService
from langflow.channels.services.gateway import ChannelGateway
from langflow.services.database.models.channel.model import ChannelConnection
from langflow.services.deps import session_scope

_T = TypeVar("_T")


def _positive_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


@dataclass(frozen=True)
class WebhookLimiterSnapshot:
    pending: int
    max_pending: int
    max_concurrency: int


class WebhookProcessingLimiter:
    """Bound webhook background work without acknowledging events that would be dropped."""

    def __init__(self, *, max_concurrency: int, max_pending: int) -> None:
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        if max_pending < max_concurrency:
            raise ValueError("max_pending must be greater than or equal to max_concurrency")
        self.max_concurrency = max_concurrency
        self.max_pending = max_pending
        self._pending = 0
        self._pending_lock = Lock()
        self._semaphore_lock = Lock()
        self._semaphores: dict[int, asyncio.Semaphore] = {}

    def try_reserve(self) -> bool:
        """Reserve one queue slot before returning a successful provider ACK."""
        with self._pending_lock:
            if self._pending >= self.max_pending:
                return False
            self._pending += 1
            return True

    def release(self) -> None:
        with self._pending_lock:
            self._pending = max(0, self._pending - 1)

    def snapshot(self) -> WebhookLimiterSnapshot:
        with self._pending_lock:
            pending = self._pending
        return WebhookLimiterSnapshot(
            pending=pending,
            max_pending=self.max_pending,
            max_concurrency=self.max_concurrency,
        )

    async def run(self, callback: Callable[..., Awaitable[_T]], /, *args, **kwargs) -> _T:
        semaphore = self._semaphore_for_current_loop()
        async with semaphore:
            return await callback(*args, **kwargs)

    def _semaphore_for_current_loop(self) -> asyncio.Semaphore:
        loop_key = id(asyncio.get_running_loop())
        with self._semaphore_lock:
            semaphore = self._semaphores.get(loop_key)
            if semaphore is None:
                semaphore = asyncio.Semaphore(self.max_concurrency)
                self._semaphores[loop_key] = semaphore
            return semaphore


_webhook_limiter = WebhookProcessingLimiter(
    max_concurrency=_positive_int_env("LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY", 16),
    max_pending=_positive_int_env("LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING", 128),
)


def reserve_provider_webhook_slot() -> bool:
    return _webhook_limiter.try_reserve()


def release_provider_webhook_slot() -> None:
    _webhook_limiter.release()


def webhook_limiter_snapshot() -> WebhookLimiterSnapshot:
    return _webhook_limiter.snapshot()


async def process_reserved_provider_webhook(
    *,
    connection_id: UUID,
    expected_channel_type: str,
    headers: dict[str, str],
    payload: bytes,
) -> None:
    """Run one reserved callback and always release its queue capacity."""
    try:
        await _webhook_limiter.run(
            process_provider_webhook,
            connection_id=connection_id,
            expected_channel_type=expected_channel_type,
            headers=headers,
            payload=payload,
        )
    finally:
        release_provider_webhook_slot()


async def process_provider_webhook(
    *,
    connection_id: UUID,
    expected_channel_type: str,
    headers: dict[str, str],
    payload: bytes,
) -> None:
    """Process one already-validated provider callback in an isolated DB session."""
    async with session_scope() as session:
        connection = await session.get(ChannelConnection, connection_id)
        if connection is None or connection.channel_type != expected_channel_type or not connection.enabled:
            await logger.awarning(
                "Skipping channel webhook for missing or disabled connection %s",
                connection_id,
            )
            return

        adapter = build_channel_adapter(connection)
        gateway = ChannelGateway()
        gateway.register_adapter(connection_id, adapter)
        deduplicator = ChannelEventDeduplicator(session)
        dispatcher = ChannelDispatchService(session, connection, adapter)

        try:
            await gateway.receive(
                connection_id,
                headers,
                payload,
                dispatcher.handle,
                deduplicator=deduplicator,
            )
        except DuplicateChannelEventError:
            await session.rollback()
            await logger.adebug(
                "Ignored duplicate %s channel webhook for connection %s",
                expected_channel_type,
                connection_id,
            )
            return
        except Exception:  # noqa: BLE001
            await session.rollback()
            await logger.aexception(
                "Background %s channel webhook processing failed for connection %s",
                expected_channel_type,
                connection_id,
            )
            return

        await session.commit()
