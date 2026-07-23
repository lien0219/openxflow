import asyncio
from uuid import uuid4

import pytest

from langflow.channels.services import webhook_processing
from langflow.channels.services.webhook_processing import WebhookProcessingLimiter


def test_webhook_limiter_rejects_payloads_beyond_byte_capacity() -> None:
    limiter = WebhookProcessingLimiter(
        max_concurrency=1,
        max_pending=4,
        max_pending_bytes=5,
    )

    assert limiter.try_reserve(3) is True
    assert limiter.try_reserve(2) is True
    assert limiter.try_reserve(1) is False

    snapshot = limiter.snapshot()
    assert snapshot.pending == 2
    assert snapshot.pending_bytes == 5
    assert snapshot.max_pending_bytes == 5
    assert snapshot.rejected_total == 1

    limiter.release(3)
    assert limiter.snapshot().pending_bytes == 2
    assert limiter.try_reserve(3) is True


def test_webhook_limiter_rejects_negative_payload_sizes() -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=1)

    with pytest.raises(ValueError, match="payload_size"):
        limiter.try_reserve(-1)
    with pytest.raises(ValueError, match="payload_size"):
        limiter.release(-1)
    with pytest.raises(ValueError, match="payload_size"):
        limiter.finish(success=True, payload_size=-1)


@pytest.mark.asyncio
async def test_completed_webhook_releases_payload_bytes(monkeypatch) -> None:
    payload = b"payload"
    limiter = WebhookProcessingLimiter(
        max_concurrency=1,
        max_pending=1,
        max_pending_bytes=len(payload),
    )
    assert limiter.try_reserve(len(payload)) is True

    async def succeed(**_kwargs) -> bool:
        return True

    monkeypatch.setattr(webhook_processing, "_webhook_limiter", limiter)
    monkeypatch.setattr(webhook_processing, "process_provider_webhook", succeed)

    await webhook_processing.process_reserved_provider_webhook(
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
    assert limiter.try_reserve(len(payload)) is True
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
