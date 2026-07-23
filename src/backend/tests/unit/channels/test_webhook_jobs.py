from types import SimpleNamespace
from uuid import uuid4

import pytest

from langflow.channels.services import webhook_jobs
from langflow.services.database.models.channel.webhook_job_model import (
    ChannelWebhookJob,
    ChannelWebhookJobStatus,
)


def test_durable_webhook_job_defaults() -> None:
    job = ChannelWebhookJob(
        connection_id=uuid4(),
        channel_type="telegram",
        external_event_id="event-1",
        headers_data={"content-type": "application/json"},
        payload=b"{}",
    )

    assert job.status == ChannelWebhookJobStatus.PENDING.value
    assert job.attempts == 0
    assert job.max_attempts == 5
    assert job.lease_owner is None
    assert job.lease_expires_at is None
    assert job.completed_at is None


def test_durable_webhook_retry_delay_is_exponential_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        webhook_jobs,
        "durable_webhook_job_config",
        lambda: SimpleNamespace(retry_base_seconds=2.0, retry_max_seconds=10.0),
    )

    assert webhook_jobs.retry_delay_seconds(1) == 2.0
    assert webhook_jobs.retry_delay_seconds(2) == 4.0
    assert webhook_jobs.retry_delay_seconds(3) == 8.0
    assert webhook_jobs.retry_delay_seconds(4) == 10.0
    assert webhook_jobs.retry_delay_seconds(20) == 10.0


@pytest.mark.parametrize("attempts", [0, -1, -10])
def test_durable_webhook_retry_delay_rejects_non_positive_attempts(attempts: int) -> None:
    with pytest.raises(ValueError, match="attempts"):
        webhook_jobs.retry_delay_seconds(attempts)


@pytest.mark.asyncio
async def test_disabled_durable_webhook_worker_does_not_start_consumers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        webhook_jobs,
        "durable_webhook_job_config",
        lambda: SimpleNamespace(enabled=False),
    )
    worker = webhook_jobs.DurableWebhookJobWorker()

    await worker.run()

    assert worker._tasks == []
