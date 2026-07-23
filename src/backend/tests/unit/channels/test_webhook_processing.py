import asyncio
from uuid import uuid4

import pytest

from langflow.channels.services import webhook_processing
from langflow.channels.services.webhook_processing import WebhookProcessingLimiter


def _reserve(limiter: WebhookProcessingLimiter, payload_size: int = 0):
    reservation = limiter.try_reserve(payload_size)
    assert reservation is not None
    return reservation


def test_webhook_limiter_rejects_work_beyond_pending_capacity() -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=2)

    first = _reserve(limiter)
    second = _reserve(limiter)
    assert limiter.try_reserve() is None
    snapshot = limiter.snapshot()
    assert snapshot.pending == 2
    assert snapshot.rejected_total == 1
    assert snapshot.rejected_pending_total == 1
    assert snapshot.rejected_bytes_total == 0
    assert snapshot.rejected_both_total == 0

    limiter.cancel_reservation(first)
    third = _reserve(limiter)
    limiter.cancel_reservation(second)
    limiter.cancel_reservation(third)
    assert limiter.snapshot().pending == 0


def test_webhook_reservation_cannot_be_consumed_twice_or_by_another_limiter() -> None:
    first_limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=1)
    second_limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=1)
    reservation = _reserve(first_limiter, 5)

    with pytest.raises(ValueError, match="not active"):
        second_limiter.cancel_reservation(reservation)

    first_limiter.cancel_reservation(reservation)
    with pytest.raises(ValueError, match="not active"):
        first_limiter.cancel_reservation(reservation)

    assert first_limiter.snapshot().pending == 0
    assert first_limiter.snapshot().pending_bytes == 0


@pytest.mark.asyncio
async def test_webhook_limiter_caps_concurrent_callbacks() -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=2)
    first_reservation = _reserve(limiter)
    second_reservation = _reserve(limiter)

    first_started = asyncio.Event()
    allow_first_to_finish = asyncio.Event()
    second_started = asyncio.Event()

    async def first() -> None:
        first_started.set()
        await allow_first_to_finish.wait()

    async def second() -> None:
        second_started.set()

    first_task = asyncio.create_task(limiter.run(first))
    await first_started.wait()
    second_task = asyncio.create_task(limiter.run(second))
    await asyncio.sleep(0)

    assert second_started.is_set() is False
    allow_first_to_finish.set()
    await asyncio.gather(first_task, second_task)
    assert second_started.is_set() is True

    limiter.cancel_reservation(first_reservation)
    limiter.cancel_reservation(second_reservation)


@pytest.mark.asyncio
async def test_reserved_webhook_slot_is_released_after_failure(monkeypatch) -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=1)
    reservation = _reserve(limiter, 2)

    async def fail(**_kwargs) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(webhook_processing, "_webhook_limiter", limiter)
    monkeypatch.setattr(webhook_processing, "process_provider_webhook", fail)

    with pytest.raises(RuntimeError, match="boom"):
        await webhook_processing.process_reserved_provider_webhook(
            reservation=reservation,
            connection_id=uuid4(),
            expected_channel_type="telegram",
            headers={},
            payload=b"{}",
        )

    assert limiter.snapshot().pending == 0
    replacement = _reserve(limiter)
    limiter.cancel_reservation(replacement)


@pytest.mark.asyncio
async def test_reserved_webhook_timeout_releases_capacity(monkeypatch) -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=1)
    reservation = _reserve(limiter, 2)
    never_finishes = asyncio.Event()

    async def block(**_kwargs) -> bool:
        await never_finishes.wait()
        return True

    monkeypatch.setattr(webhook_processing, "_webhook_limiter", limiter)
    monkeypatch.setattr(webhook_processing, "process_provider_webhook", block)
    monkeypatch.setattr(webhook_processing, "webhook_task_timeout_seconds", lambda: 0.01)

    await webhook_processing.process_reserved_provider_webhook(
        reservation=reservation,
        connection_id=uuid4(),
        expected_channel_type="telegram",
        headers={},
        payload=b"{}",
    )

    snapshot = limiter.snapshot()
    assert snapshot.pending == 0
    assert snapshot.active == 0
    assert snapshot.failed_total == 1
    assert snapshot.cancelled_total == 0


@pytest.mark.asyncio
async def test_queued_webhook_does_not_consume_execution_timeout(monkeypatch) -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=1)
    reservation = _reserve(limiter, len(b"second"))

    blocker_started = asyncio.Event()
    release_blocker = asyncio.Event()
    webhook_started = asyncio.Event()

    async def occupy_slot() -> None:
        blocker_started.set()
        await release_blocker.wait()

    async def process(**_kwargs) -> bool:
        webhook_started.set()
        return True

    monkeypatch.setattr(webhook_processing, "_webhook_limiter", limiter)
    monkeypatch.setattr(webhook_processing, "process_provider_webhook", process)
    monkeypatch.setattr(webhook_processing, "webhook_task_timeout_seconds", lambda: 0.02)

    blocker_task = asyncio.create_task(limiter.run(occupy_slot))
    await blocker_started.wait()
    webhook_task = asyncio.create_task(
        webhook_processing.process_reserved_provider_webhook(
            reservation=reservation,
            connection_id=uuid4(),
            expected_channel_type="telegram",
            headers={},
            payload=b"second",
        )
    )

    await asyncio.sleep(0.04)
    assert webhook_started.is_set() is False
    assert webhook_task.done() is False

    release_blocker.set()
    await asyncio.gather(blocker_task, webhook_task)

    snapshot = limiter.snapshot()
    assert webhook_started.is_set() is True
    assert snapshot.pending == 0
    assert snapshot.succeeded_total == 1
    assert snapshot.failed_total == 0


@pytest.mark.asyncio
async def test_reserved_webhook_external_cancellation_propagates_without_failure(monkeypatch) -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=1)
    reservation = _reserve(limiter, 2)
    started = asyncio.Event()
    never_finishes = asyncio.Event()

    async def block(**_kwargs) -> bool:
        started.set()
        await never_finishes.wait()
        return True

    monkeypatch.setattr(webhook_processing, "_webhook_limiter", limiter)
    monkeypatch.setattr(webhook_processing, "process_provider_webhook", block)
    monkeypatch.setattr(webhook_processing, "webhook_task_timeout_seconds", lambda: 60.0)

    task = asyncio.create_task(
        webhook_processing.process_reserved_provider_webhook(
            reservation=reservation,
            connection_id=uuid4(),
            expected_channel_type="telegram",
            headers={},
            payload=b"{}",
        )
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    snapshot = limiter.snapshot()
    assert snapshot.pending == 0
    assert snapshot.active == 0
    assert snapshot.failed_total == 0
    assert snapshot.succeeded_total == 0
    assert snapshot.cancelled_total == 1


def test_webhook_timeout_non_finite_values_fall_back(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS", "nan")
    assert webhook_processing.webhook_task_timeout_seconds() == 300.0

    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS", "inf")
    assert webhook_processing.webhook_task_timeout_seconds() == 300.0


def test_webhook_limiter_env_clamps_pending_to_concurrency(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY", "8")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING", "2")

    limiter = webhook_processing._webhook_limiter_from_env()

    assert limiter.max_concurrency == 8
    assert limiter.max_pending == 8


def test_webhook_limiter_validates_configuration() -> None:
    with pytest.raises(ValueError, match="max_concurrency"):
        WebhookProcessingLimiter(max_concurrency=0, max_pending=1)
    with pytest.raises(ValueError, match="max_pending"):
        WebhookProcessingLimiter(max_concurrency=2, max_pending=1)
