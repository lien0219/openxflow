import asyncio

import pytest

from langflow.channels.services.timing_metrics import (
    channel_timing_metrics_snapshot,
    reset_channel_timing_metrics_for_testing,
)
from langflow.channels.services.webhook_processing import (
    WebhookProcessingLimiter,
    WebhookQueueTimeoutError,
)


@pytest.fixture(autouse=True)
def reset_timing_metrics():
    reset_channel_timing_metrics_for_testing()
    yield
    reset_channel_timing_metrics_for_testing()


@pytest.mark.asyncio
async def test_webhook_limiter_records_queue_and_execution_duration() -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=1)

    async def callback() -> str:
        await asyncio.sleep(0)
        return "ok"

    result = await limiter.run(callback, record_timings=True)

    assert result == "ok"
    snapshot = channel_timing_metrics_snapshot()
    assert snapshot.webhook_queue_wait_duration.count == 1
    assert snapshot.webhook_execution_duration.count == 1
    assert snapshot.webhook_queue_wait_duration.sum_seconds >= 0
    assert snapshot.webhook_execution_duration.sum_seconds >= 0


@pytest.mark.asyncio
async def test_webhook_queue_timeout_records_wait_without_execution() -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=2)
    blocker_started = asyncio.Event()
    release_blocker = asyncio.Event()

    async def blocker() -> None:
        blocker_started.set()
        await release_blocker.wait()

    async def should_not_run() -> None:
        raise AssertionError("queued callback unexpectedly started")

    blocker_task = asyncio.create_task(limiter.run(blocker))
    await blocker_started.wait()

    with pytest.raises(WebhookQueueTimeoutError):
        await limiter.run(
            should_not_run,
            queue_timeout_seconds=0.01,
            record_timings=True,
        )

    release_blocker.set()
    await blocker_task

    snapshot = channel_timing_metrics_snapshot()
    assert snapshot.webhook_queue_wait_duration.count == 1
    assert snapshot.webhook_execution_duration.count == 0
    assert snapshot.webhook_queue_wait_duration.sum_seconds >= 0.01
