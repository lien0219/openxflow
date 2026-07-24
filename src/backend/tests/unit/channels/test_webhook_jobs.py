import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langflow.channels.services import webhook_jobs
from langflow.channels.services.timing_metrics import (
    channel_timing_metrics_snapshot,
    reset_channel_timing_metrics_for_testing,
)
from langflow.channels.services.webhook_job_metrics import (
    durable_webhook_job_metrics_snapshot,
    reset_durable_webhook_job_metrics_for_testing,
)
from langflow.services.database.models.channel.webhook_job_model import (
    ChannelWebhookJob,
    ChannelWebhookJobStatus,
)


def setup_function() -> None:
    reset_channel_timing_metrics_for_testing()
    reset_durable_webhook_job_metrics_for_testing()


def teardown_function() -> None:
    reset_channel_timing_metrics_for_testing()
    reset_durable_webhook_job_metrics_for_testing()


def _job(*, attempts: int = 1, max_attempts: int = 5) -> ChannelWebhookJob:
    return ChannelWebhookJob(
        connection_id=uuid4(),
        channel_type="telegram",
        external_event_id="event-1",
        headers_data={"content-type": "application/json"},
        payload=b"{}",
        status=ChannelWebhookJobStatus.PROCESSING.value,
        attempts=attempts,
        max_attempts=max_attempts,
    )


def test_durable_webhook_job_defaults() -> None:
    job = _job(attempts=0)
    job.status = ChannelWebhookJobStatus.PENDING.value

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


@pytest.mark.asyncio
async def test_durable_webhook_worker_completes_successful_job(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = webhook_jobs.DurableWebhookJobWorker()
    job = _job()
    completed = []

    @asynccontextmanager
    async def fake_session_scope():
        yield object()

    async def execute(_job) -> bool:
        return True

    async def complete(_session, *, job_id, worker_id) -> bool:
        completed.append((job_id, worker_id))
        return True

    monkeypatch.setattr(webhook_jobs, "session_scope", fake_session_scope)
    monkeypatch.setattr(worker, "_execute", execute)
    monkeypatch.setattr(webhook_jobs, "complete_provider_webhook_job", complete)
    monkeypatch.setattr(webhook_jobs, "webhook_task_timeout_seconds", lambda: 1.0)

    await worker._process(job)

    assert completed == [(job.id, worker.worker_id)]
    assert durable_webhook_job_metrics_snapshot().completed_total == 1
    assert channel_timing_metrics_snapshot().webhook_execution_duration.count == 1


@pytest.mark.asyncio
async def test_durable_webhook_worker_retries_timed_out_job(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = webhook_jobs.DurableWebhookJobWorker()
    job = _job(attempts=1, max_attempts=3)
    failed = []

    @asynccontextmanager
    async def fake_session_scope():
        yield object()

    async def never_finishes(_job) -> bool:
        await asyncio.Event().wait()
        return True

    async def fail(_session, *, job, worker_id, error) -> bool:
        failed.append((job.id, worker_id, error))
        return True

    monkeypatch.setattr(webhook_jobs, "session_scope", fake_session_scope)
    monkeypatch.setattr(worker, "_execute", never_finishes)
    monkeypatch.setattr(webhook_jobs, "fail_provider_webhook_job", fail)
    monkeypatch.setattr(webhook_jobs, "webhook_task_timeout_seconds", lambda: 0.001)

    await worker._process(job)

    assert failed[0][0] == job.id
    assert failed[0][1] == worker.worker_id
    assert "timed out" in failed[0][2]
    assert durable_webhook_job_metrics_snapshot().retried_total == 1
    assert channel_timing_metrics_snapshot().webhook_execution_duration.count == 1


@pytest.mark.asyncio
async def test_durable_webhook_worker_cancellation_keeps_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = webhook_jobs.DurableWebhookJobWorker()
    job = _job()
    started = asyncio.Event()
    persisted = False

    async def never_finishes(_job) -> bool:
        started.set()
        await asyncio.Event().wait()
        return True

    @asynccontextmanager
    async def fail_if_persisted():
        nonlocal persisted
        persisted = True
        yield object()

    monkeypatch.setattr(worker, "_execute", never_finishes)
    monkeypatch.setattr(webhook_jobs, "session_scope", fail_if_persisted)
    monkeypatch.setattr(webhook_jobs, "webhook_task_timeout_seconds", lambda: 60.0)

    task = asyncio.create_task(worker._process(job))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert persisted is False
    assert durable_webhook_job_metrics_snapshot().completed_total == 0
    assert durable_webhook_job_metrics_snapshot().retried_total == 0
    assert durable_webhook_job_metrics_snapshot().failed_total == 0
    assert channel_timing_metrics_snapshot().webhook_execution_duration.count == 1
