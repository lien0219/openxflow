import asyncio
from uuid import uuid4

import pytest
from langflow.channels.services import webhook_processing
from langflow.channels.services.webhook_processing import WebhookProcessingLimiter


def _reserve(limiter: WebhookProcessingLimiter, payload_size: int = 0):
    reservation = limiter.try_reserve(payload_size)
    assert reservation is not None
    return reservation


def test_webhook_limiter_rejects_payloads_beyond_byte_capacity() -> None:
    limiter = WebhookProcessingLimiter(
        max_concurrency=1,
        max_pending=4,
        max_pending_bytes=5,
    )

    first = _reserve(limiter, 3)
    second = _reserve(limiter, 2)
    assert limiter.try_reserve(1) is None

    snapshot = limiter.snapshot()
    assert snapshot.pending == 2
    assert snapshot.pending_bytes == 5
    assert snapshot.max_pending_bytes == 5
    assert snapshot.rejected_total == 1
    assert snapshot.rejected_pending_total == 0
    assert snapshot.rejected_bytes_total == 1
    assert snapshot.rejected_both_total == 0

    limiter.cancel_reservation(first)
    assert limiter.snapshot().pending_bytes == 2
    third = _reserve(limiter, 3)

    limiter.cancel_reservation(second)
    limiter.cancel_reservation(third)
    assert limiter.snapshot().pending_bytes == 0


def test_webhook_limiter_classifies_combined_capacity_rejection_once() -> None:
    limiter = WebhookProcessingLimiter(
        max_concurrency=1,
        max_pending=1,
        max_pending_bytes=5,
    )
    reservation = _reserve(limiter, 5)

    assert limiter.try_reserve(1) is None

    snapshot = limiter.snapshot()
    assert snapshot.rejected_total == 1
    assert snapshot.rejected_pending_total == 0
    assert snapshot.rejected_bytes_total == 0
    assert snapshot.rejected_both_total == 1
    assert (
        snapshot.rejected_pending_total + snapshot.rejected_bytes_total + snapshot.rejected_both_total
        == snapshot.rejected_total
    )
    limiter.cancel_reservation(reservation)


def test_webhook_limiter_rejects_negative_payload_sizes() -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=1)

    with pytest.raises(ValueError, match="payload_size"):
        limiter.try_reserve(-1)


def test_webhook_limiter_rejects_non_reservation_release() -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=1)

    with pytest.raises(TypeError, match="WebhookReservation"):
        limiter.cancel_reservation(1)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_completed_webhook_releases_payload_bytes(monkeypatch) -> None:
    payload = b"payload"
    limiter = WebhookProcessingLimiter(
        max_concurrency=1,
        max_pending=1,
        max_pending_bytes=len(payload),
    )
    reservation = _reserve(limiter, len(payload))

    async def succeed(**_kwargs) -> bool:
        return True

    monkeypatch.setattr(webhook_processing, "_webhook_limiter", limiter)
    monkeypatch.setattr(webhook_processing, "process_provider_webhook", succeed)

    await webhook_processing.process_reserved_provider_webhook(
        reservation=reservation,
        connection_id=uuid4(),
        expected_channel_type="telegram",
        headers={},
        payload=payload,
    )

    snapshot = limiter.snapshot()
    assert snapshot.pending == 0
    assert snapshot.pending_bytes == 0
    assert snapshot.succeeded_total == 1


@pytest.mark.asyncio
async def test_cancelled_webhook_releases_payload_bytes_without_failure(monkeypatch) -> None:
    payload = b"payload"
    limiter = WebhookProcessingLimiter(
        max_concurrency=1,
        max_pending=1,
        max_pending_bytes=len(payload),
    )
    reservation = _reserve(limiter, len(payload))
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
            payload=payload,
        )
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    snapshot = limiter.snapshot()
    assert snapshot.pending == 0
    assert snapshot.pending_bytes == 0
    assert snapshot.failed_total == 0
    assert snapshot.cancelled_total == 1
