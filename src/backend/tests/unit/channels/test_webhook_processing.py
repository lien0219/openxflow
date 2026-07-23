import asyncio

import pytest

from langflow.channels.services.webhook_processing import WebhookProcessingLimiter


def test_webhook_limiter_rejects_work_beyond_pending_capacity() -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=2)

    assert limiter.try_reserve() is True
    assert limiter.try_reserve() is True
    assert limiter.try_reserve() is False
    assert limiter.snapshot().pending == 2

    limiter.release()
    assert limiter.try_reserve() is True
    limiter.release()
    limiter.release()
    assert limiter.snapshot().pending == 0


@pytest.mark.asyncio
async def test_webhook_limiter_caps_concurrent_callbacks() -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=2)
    assert limiter.try_reserve() is True
    assert limiter.try_reserve() is True

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

    limiter.release()
    limiter.release()


def test_webhook_limiter_validates_configuration() -> None:
    with pytest.raises(ValueError, match="max_concurrency"):
        WebhookProcessingLimiter(max_concurrency=0, max_pending=1)
    with pytest.raises(ValueError, match="max_pending"):
        WebhookProcessingLimiter(max_concurrency=2, max_pending=1)
