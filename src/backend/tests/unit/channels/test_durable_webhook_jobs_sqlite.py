from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.services.webhook_jobs import (
    claim_provider_webhook_job,
    cleanup_durable_webhook_jobs,
    complete_provider_webhook_job,
    durable_webhook_job_depths,
    enqueue_provider_webhook_job,
)
from langflow.services.database.models.channel.model import utc_now
from langflow.services.database.models.channel.webhook_job_model import (
    ChannelWebhookJob,
    ChannelWebhookJobStatus,
)

_CREATE_JOB_TABLE = """
CREATE TABLE channel_webhook_job (
    id CHAR(32) NOT NULL PRIMARY KEY,
    connection_id CHAR(32) NOT NULL,
    channel_type VARCHAR(32) NOT NULL,
    external_event_id VARCHAR(255) NOT NULL,
    headers_data JSON NOT NULL,
    payload BLOB NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempts INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    lease_owner CHAR(32),
    lease_expires_at DATETIME,
    next_attempt_at DATETIME NOT NULL,
    last_error TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    completed_at DATETIME,
    CONSTRAINT uq_channel_webhook_job_external_event UNIQUE (connection_id, external_event_id)
)
"""


async def _session_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.execute(sa.text(_CREATE_JOB_TABLE))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def test_durable_webhook_job_enqueue_claim_complete_and_cleanup(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_COMPLETED_RETENTION_DAYS", "1")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_FAILED_RETENTION_DAYS", "1")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_CLEANUP_BATCH_SIZE", "10")
    engine, factory = await _session_factory()
    connection_id = uuid4()
    first_worker = uuid4()
    second_worker = uuid4()

    try:
        async with factory() as session:
            inserted = await enqueue_provider_webhook_job(
                session,
                connection_id=connection_id,
                channel_type="telegram",
                external_event_id="event-1",
                headers={"content-type": "application/json"},
                payload=b"{}",
            )
        assert inserted is True

        async with factory() as session:
            duplicate = await enqueue_provider_webhook_job(
                session,
                connection_id=connection_id,
                channel_type="telegram",
                external_event_id="event-1",
                headers={"content-type": "application/json"},
                payload=b"{}",
            )
        assert duplicate is False

        async with factory() as session:
            claimed = await claim_provider_webhook_job(session, worker_id=first_worker)
        assert claimed is not None
        assert claimed.status == ChannelWebhookJobStatus.PROCESSING.value
        assert claimed.attempts == 1
        assert claimed.lease_owner == first_worker

        async with factory() as session:
            unavailable = await claim_provider_webhook_job(session, worker_id=second_worker)
        assert unavailable is None

        async with factory() as session:
            completed = await complete_provider_webhook_job(
                session,
                job_id=claimed.id,
                worker_id=first_worker,
            )
        assert completed is True

        async with factory() as session:
            depths = await durable_webhook_job_depths(session)
        assert depths == {
            ChannelWebhookJobStatus.PENDING.value: 0,
            ChannelWebhookJobStatus.PROCESSING.value: 0,
            ChannelWebhookJobStatus.COMPLETED.value: 1,
            ChannelWebhookJobStatus.FAILED.value: 0,
        }

        old = utc_now() - timedelta(days=2)
        async with factory() as session:
            await session.exec(
                sa.update(ChannelWebhookJob)
                .where(ChannelWebhookJob.id == claimed.id)
                .values(completed_at=old, updated_at=old)
            )
            await session.commit()

        async with factory() as session:
            deleted = await cleanup_durable_webhook_jobs(session)
        assert deleted == 1

        async with factory() as session:
            depths = await durable_webhook_job_depths(session)
        assert all(value == 0 for value in depths.values())
    finally:
        await engine.dispose()


async def test_expired_durable_webhook_lease_can_be_reclaimed() -> None:
    engine, factory = await _session_factory()
    connection_id = uuid4()
    first_worker = uuid4()
    second_worker = uuid4()

    try:
        async with factory() as session:
            await enqueue_provider_webhook_job(
                session,
                connection_id=connection_id,
                channel_type="telegram",
                external_event_id="event-expired",
                headers={},
                payload=b"{}",
            )

        async with factory() as session:
            first_claim = await claim_provider_webhook_job(session, worker_id=first_worker)
        assert first_claim is not None

        async with factory() as session:
            await session.exec(
                sa.update(ChannelWebhookJob)
                .where(ChannelWebhookJob.id == first_claim.id)
                .values(lease_expires_at=utc_now() - timedelta(seconds=1))
            )
            await session.commit()

        async with factory() as session:
            second_claim = await claim_provider_webhook_job(session, worker_id=second_worker)
        assert second_claim is not None
        assert second_claim.id == first_claim.id
        assert second_claim.lease_owner == second_worker
        assert second_claim.attempts == 2
    finally:
        await engine.dispose()
