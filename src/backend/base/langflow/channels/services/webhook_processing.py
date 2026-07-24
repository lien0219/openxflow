"""Background processing for provider webhooks after a fast acknowledgement."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import TypeVar
from uuid import UUID
from weakref import WeakKeyDictionary

from lfx.log.logger import logger

from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.domain.exceptions import DuplicateChannelEventError
from langflow.channels.services.deduplication import ChannelEventDeduplicator
from langflow.channels.services.dispatch import ChannelDispatchService
from langflow.channels.services.gateway import ChannelGateway
from langflow.channels.services.runtime_config import (
    DEFAULT_WEBHOOK_MAX_PENDING_BYTES,
    webhook_limiter_limits_from_env,
    webhook_queue_timeout_seconds,
    webhook_task_timeout_seconds,
)
from langflow.channels.services.timing_metrics import (
    record_webhook_execution,
    record_webhook_queue_wait,
)
from langflow.services.database.models.channel.model import ChannelConnection
from langflow.services.deps import session_scope

_T = TypeVar("_T")


class WebhookQueueTimeoutError(TimeoutError):
    """Raised when a reserved webhook cannot obtain an execution slot in time."""


@dataclass(frozen=True)
class WebhookReservation:
    """Opaque capacity reservation issued by one webhook limiter instance."""

    _token: object = field(repr=False)


@dataclass(frozen=True)
class WebhookLimiterSnapshot:
    pending: int
    active: int
    queued: int
    pending_bytes: int
    max_pending: int
    max_pending_bytes: int
    max_concurrency: int
    accepted_total: int
    rejected_total: int
    rejected_pending_total: int
    rejected_bytes_total: int
    rejected_both_total: int
    succeeded_total: int
    failed_total: int
    queue_timed_out_total: int
    cancelled_total: int
    client_disconnected_total: int


class WebhookProcessingLimiter:
    """Bound webhook background work without acknowledging events that would be dropped."""

    def __init__(
        self,
        *,
        max_concurrency: int,
        max_pending: int,
        max_pending_bytes: int = DEFAULT_WEBHOOK_MAX_PENDING_BYTES,
    ) -> None:
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        if max_pending < max_concurrency:
            raise ValueError("max_pending must be greater than or equal to max_concurrency")
        if max_pending_bytes <= 0:
            raise ValueError("max_pending_bytes must be positive")
        self.max_concurrency = max_concurrency
        self.max_pending = max_pending
        self.max_pending_bytes = max_pending_bytes
        self._pending = 0
        self._pending_bytes = 0
        self._active = 0
        self._accepted_total = 0
        self._rejected_total = 0
        self._rejected_pending_total = 0
        self._rejected_bytes_total = 0
        self._rejected_both_total = 0
        self._succeeded_total = 0
        self._failed_total = 0
        self._queue_timed_out_total = 0
        self._cancelled_total = 0
        self._client_disconnected_total = 0
        self._reservations: dict[object, int] = {}
        self._state_lock = Lock()
        self._semaphore_lock = Lock()
        self._semaphores: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = WeakKeyDictionary()

    def try_reserve(self, payload_size: int = 0) -> WebhookReservation | None:
        """Reserve queue count and retained-payload capacity before returning a successful ACK."""
        self._validate_payload_size(payload_size)
        with self._state_lock:
            pending_full = self._pending >= self.max_pending
            bytes_full = self._pending_bytes + payload_size > self.max_pending_bytes
            if pending_full or bytes_full:
                self._rejected_total += 1
                if pending_full and bytes_full:
                    self._rejected_both_total += 1
                elif pending_full:
                    self._rejected_pending_total += 1
                else:
                    self._rejected_bytes_total += 1
                return None
            token = object()
            self._reservations[token] = payload_size
            self._pending += 1
            self._pending_bytes += payload_size
            self._accepted_total += 1
            return WebhookReservation(token)

    def cancel_reservation(self, reservation: WebhookReservation, *, cancelled: bool = False) -> None:
        with self._state_lock:
            payload_size = self._consume_reservation_locked(reservation)
            self._pending -= 1
            self._pending_bytes -= payload_size
            if cancelled:
                self._cancelled_total += 1

    def finish(
        self,
        reservation: WebhookReservation,
        *,
        success: bool,
        queue_timed_out: bool = False,
    ) -> None:
        with self._state_lock:
            payload_size = self._consume_reservation_locked(reservation)
            self._pending -= 1
            self._pending_bytes -= payload_size
            if success:
                self._succeeded_total += 1
            else:
                self._failed_total += 1
                if queue_timed_out:
                    self._queue_timed_out_total += 1

    def record_client_disconnect(self) -> None:
        """Record a callback upload that ended before the request body was complete."""
        with self._state_lock:
            self._client_disconnected_total += 1

    def snapshot(self) -> WebhookLimiterSnapshot:
        with self._state_lock:
            pending = self._pending
            active = self._active
            return WebhookLimiterSnapshot(
                pending=pending,
                active=active,
                queued=max(0, pending - active),
                pending_bytes=self._pending_bytes,
                max_pending=self.max_pending,
                max_pending_bytes=self.max_pending_bytes,
                max_concurrency=self.max_concurrency,
                accepted_total=self._accepted_total,
                rejected_total=self._rejected_total,
                rejected_pending_total=self._rejected_pending_total,
                rejected_bytes_total=self._rejected_bytes_total,
                rejected_both_total=self._rejected_both_total,
                succeeded_total=self._succeeded_total,
                failed_total=self._failed_total,
                queue_timed_out_total=self._queue_timed_out_total,
                cancelled_total=self._cancelled_total,
                client_disconnected_total=self._client_disconnected_total,
            )

    async def run(
        self,
        callback: Callable[..., Awaitable[_T]],
        /,
        *args,
        queue_timeout_seconds: float = 0.0,
        record_timings: bool = False,
        **kwargs,
    ) -> _T:
        semaphore = self._semaphore_for_current_loop()
        acquired = False
        queue_started_at = time.perf_counter()
        try:
            if queue_timeout_seconds > 0:
                try:
                    await asyncio.wait_for(semaphore.acquire(), timeout=queue_timeout_seconds)
                except TimeoutError as exc:
                    if record_timings:
                        record_webhook_queue_wait(time.perf_counter() - queue_started_at)
                    raise WebhookQueueTimeoutError("Webhook queue wait timed out") from exc
            else:
                await semaphore.acquire()
            acquired = True
            if record_timings:
                record_webhook_queue_wait(time.perf_counter() - queue_started_at)
            with self._state_lock:
                self._active += 1
            execution_started_at = time.perf_counter()
            try:
                return await callback(*args, **kwargs)
            finally:
                if record_timings:
                    record_webhook_execution(time.perf_counter() - execution_started_at)
                with self._state_lock:
                    self._active -= 1
        finally:
            if acquired:
                semaphore.release()

    @staticmethod
    def _validate_payload_size(payload_size: int) -> None:
        if payload_size < 0:
            raise ValueError("payload_size must be non-negative")

    def _consume_reservation_locked(self, reservation: WebhookReservation) -> int:
        if not isinstance(reservation, WebhookReservation):
            raise TypeError("reservation must be a WebhookReservation")
        try:
            return self._reservations.pop(reservation._token)
        except KeyError as exc:
            raise ValueError("Webhook reservation is not active for this limiter") from exc

    def _semaphore_for_current_loop(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        with self._semaphore_lock:
            semaphore = self._semaphores.get(loop)
            if semaphore is None:
                semaphore = asyncio.Semaphore(self.max_concurrency)
                self._semaphores[loop] = semaphore
            return semaphore


def _webhook_limiter_from_env() -> WebhookProcessingLimiter:
    limits = webhook_limiter_limits_from_env()
    return WebhookProcessingLimiter(
        max_concurrency=limits.max_concurrency,
        max_pending=limits.max_pending,
        max_pending_bytes=limits.max_pending_bytes,
    )


_webhook_limiter = _webhook_limiter_from_env()


def reserve_provider_webhook_slot(payload_size: int = 0) -> WebhookReservation | None:
    return _webhook_limiter.try_reserve(payload_size)


def release_provider_webhook_slot(reservation: WebhookReservation) -> None:
    _webhook_limiter.cancel_reservation(reservation)


def record_provider_webhook_client_disconnect() -> None:
    _webhook_limiter.record_client_disconnect()


def webhook_limiter_snapshot() -> WebhookLimiterSnapshot:
    return _webhook_limiter.snapshot()


async def _process_provider_webhook_with_timeout(
    *,
    connection_id: UUID,
    expected_channel_type: str,
    headers: dict[str, str],
    payload: bytes,
) -> bool:
    try:
        return await asyncio.wait_for(
            process_provider_webhook(
                connection_id=connection_id,
                expected_channel_type=expected_channel_type,
                headers=headers,
                payload=payload,
            ),
            timeout=webhook_task_timeout_seconds(),
        )
    except TimeoutError:
        await logger.aerror(
            "Background %s channel webhook timed out for connection %s",
            expected_channel_type,
            connection_id,
        )
        return False


async def process_reserved_provider_webhook(
    *,
    reservation: WebhookReservation,
    connection_id: UUID,
    expected_channel_type: str,
    headers: dict[str, str],
    payload: bytes,
) -> None:
    """Run one reserved callback and always release its queue and payload capacity."""
    success = False
    cancelled = False
    queue_timed_out = False
    try:
        try:
            success = await _webhook_limiter.run(
                _process_provider_webhook_with_timeout,
                connection_id=connection_id,
                expected_channel_type=expected_channel_type,
                headers=headers,
                payload=payload,
                queue_timeout_seconds=webhook_queue_timeout_seconds(),
                record_timings=True,
            )
        except WebhookQueueTimeoutError:
            queue_timed_out = True
            await logger.aerror(
                "Background %s channel webhook queue wait timed out for connection %s",
                expected_channel_type,
                connection_id,
            )
        except asyncio.CancelledError:
            cancelled = True
            raise
    finally:
        if cancelled:
            _webhook_limiter.cancel_reservation(reservation, cancelled=True)
        else:
            _webhook_limiter.finish(
                reservation,
                success=success,
                queue_timed_out=queue_timed_out,
            )


async def process_provider_webhook(
    *,
    connection_id: UUID,
    expected_channel_type: str,
    headers: dict[str, str],
    payload: bytes,
    preverified: bool = False,
) -> bool:
    """Process one provider callback in an isolated database session."""
    async with session_scope() as session:
        connection = await session.get(ChannelConnection, connection_id)
        if connection is None or connection.channel_type != expected_channel_type or not connection.enabled:
            await logger.awarning(
                "Skipping channel webhook for missing or disabled connection %s",
                connection_id,
            )
            return True

        adapter = build_channel_adapter(connection)
        gateway = ChannelGateway()
        gateway.register_adapter(connection_id, adapter)
        deduplicator = ChannelEventDeduplicator(session)
        dispatcher = ChannelDispatchService(session, connection, adapter)

        try:
            if preverified:
                await gateway.receive_verified(
                    connection_id,
                    payload,
                    dispatcher.handle,
                    deduplicator=deduplicator,
                )
            else:
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
            return True
        except Exception:  # noqa: BLE001
            await session.rollback()
            await logger.aexception(
                "Background %s channel webhook processing failed for connection %s",
                expected_channel_type,
                connection_id,
            )
            return False

        await session.commit()
        return True
