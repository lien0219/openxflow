import asyncio
from uuid import uuid4

import pytest

from langflow.channels.services import webhook_processing
from langflow.channels.services.webhook_processing import WebhookProcessingLimiter


@pytest.mark.asyncio
async def test_reserved_webhook_queue_timeout_releases_capacity_without_starting_work(monkeypatch) -> None:
    limiter = WebhookProcessingLimiter(
        max_concurrency=1,
        max_pending=1,
        max_pending_bytes=16,
    )
    reservation = limiter.try_reserve(7)
    assert reservation is not None

    blocker_started = asyncio.Event()
    release_blocker = asyncio.Event()
    webhook_started = False

    async def occupy_slot() -> None:
        blocker_started.set()
        await release_blocker.wait()

    async def process(**_kwargs) -> bool:
        nonlocal webhook_started
        webhook_started = True
        return True

    monkeypatch.setattr(webhook_processing, "_webhook_limiter", limiter)
    monkeypatch.setattr(webhook_processing, "process_provider_webhook", process)
    monkeypatch.setattr(webhook_processing, "webhook_queue_timeout_seconds", lambda: 0.01)
    monkeypatch.setattr(webhook_processing, "webhook_task_timeout_seconds", lambda: 60.0)

    blocker_task = asyncio.create_task(limiter.run(occupy_slot))
    await blocker_started.wait()

    await webhook_processing.process_reserved_provider_webhook(
        reservation=reservation,
        connection_id=uuid4(),
        expected_channel_type="telegram",
        headers={},
        payload=b"payload",
    )

    snapshot = limiter.snapshot()
    assert webhook_started is False
    assert snapshot.pending == 0
    assert snapshot.pending_bytes == 0
    assert snapshot.active == 1
    assert snapshot.failed_total == 1
    assert snapshot.queue_timed_out_total == 1
    assert snapshot.succeeded_total == 0
    assert snapshot.cancelled_total == 0

    release_blocker.set()
    await blocker_task
    assert limiter.snapshot().active == 0


@pytest.mark.asyncio
async def test_zero_queue_timeout_keeps_waiting_until_slot_is_available(monkeypatch) -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=1)
    reservation = limiter.try_reserve()
    assert reservation is not None

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
    monkeypatch.setattr(webhook_processing, "webhook_queue_timeout_seconds", lambda: 0.0)
    monkeypatch.setattr(webhook_processing, "webhook_task_timeout_seconds", lambda: 60.0)

    blocker_task = asyncio.create_task(limiter.run(occupy_slot))
    await blocker_started.wait()
    webhook_task = asyncio.create_task(
        webhook_processing.process_reserved_provider_webhook(
            reservation=reservation,
            connection_id=uuid4(),
            expected_channel_type="telegram",
            headers={},
            payload=b"{}",
        )
    )

    await asyncio.sleep(0.02)
    assert webhook_started.is_set() is False
    assert webhook_task.done() is False

    release_blocker.set()
    await asyncio.gather(blocker_task, webhook_task)

    snapshot = limiter.snapshot()
    assert webhook_started.is_set() is True
    assert snapshot.queue_timed_out_total == 0
    assert snapshot.succeeded_total == 1
