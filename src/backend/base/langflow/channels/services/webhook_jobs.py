"""Database-backed queue for provider callbacks acknowledged before workflow execution."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
from lfx.log.logger import logger
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.services.runtime_config import (
    durable_webhook_job_config,
    webhook_task_timeout_seconds,
)
from langflow.channels.services.timing_metrics import record_webhook_execution
from langflow.channels.services.webhook_job_metrics import (
    record_durable_webhook_claim_error,
    record_durable_webhook_claimed,
    record_durable_webhook_cleaned,
    record_durable_webhook_completed,
    record_durable_webhook_failed,
    record_durable_webhook_maintenance_error,
    record_durable_webhook_manager_started,
    record_durable_webhook_manager_stopped,
    record_durable_webhook_retried,
    set_durable_webhook_queue_depths,
)
from langflow.channels.services.webhook_processing import process_provider_webhook
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelEventReceipt,
    ChannelReceiptStatus,
    utc_now,
)
from langflow.services.database.models.channel.webhook_job_model import (
    ChannelWebhookJob,
    ChannelWebhookJobStatus,
)
from langflow.services.deps import session_scope


async def enqueue_provider_webhook_job(
    session: AsyncSession,
    *,
    connection_id: UUID,
    channel_type: str,
    external_event_id: str,
    headers: dict[str, str],
    payload: bytes,
    connection: ChannelConnection | None = None,
    external_conversation_id: str = "",
    external_user_id: str = "",
    conversation_type: str = "private",
    queue_key: str = "",
) -> bool:
    """Persist a validated callback and commit it before returning a successful provider ACK.

    Queue pressure is represented by a durable rejection job instead of dropping
    an already verified callback. The worker later sends the user-facing rejection
    through the same idempotent outbound path as a normal response.
    """
    config = durable_webhook_job_config()
    now = utc_now()
    normalized_queue_key = queue_key or f"{connection_id}:legacy:{external_event_id}"
    persisted_headers = dict(headers)
    rejection_reason: str | None = None
    queue_position = 0

    if connection is not None and queue_key:
        active_statuses = (
            ChannelWebhookJobStatus.PENDING.value,
            ChannelWebhookJobStatus.PROCESSING.value,
        )
        queue_position = int(
            (
                await session.exec(
                    select(sa.func.count(ChannelWebhookJob.id)).where(
                        ChannelWebhookJob.connection_id == connection_id,
                        ChannelWebhookJob.queue_key == queue_key,
                        ChannelWebhookJob.status.in_(active_statuses),
                    )
                )
            ).one()
        )
        pending_count = int(
            (
                await session.exec(
                    select(sa.func.count(ChannelWebhookJob.id)).where(
                        ChannelWebhookJob.connection_id == connection_id,
                        ChannelWebhookJob.queue_key == queue_key,
                        ChannelWebhookJob.status == ChannelWebhookJobStatus.PENDING.value,
                    )
                )
            ).one()
        )
        if pending_count >= connection.per_user_queue_limit:
            rejection_reason = "queue_limit"

        if rejection_reason is None and connection.rate_limit_per_minute > 0:
            rate_filters = [
                ChannelWebhookJob.connection_id == connection_id,
                ChannelWebhookJob.created_at >= now - timedelta(minutes=1),
            ]
            if external_user_id:
                rate_filters.append(ChannelWebhookJob.external_user_id == external_user_id)
            recent_count = int(
                (await session.exec(select(sa.func.count(ChannelWebhookJob.id)).where(*rate_filters))).one()
            )
            if recent_count >= connection.rate_limit_per_minute:
                rejection_reason = "rate_limit"

        if rejection_reason is None and connection.daily_quota > 0:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            daily_count = int(
                (
                    await session.exec(
                        select(sa.func.count(ChannelWebhookJob.id)).where(
                            ChannelWebhookJob.connection_id == connection_id,
                            ChannelWebhookJob.created_at >= day_start,
                        )
                    )
                ).one()
            )
            if daily_count >= connection.daily_quota:
                rejection_reason = "daily_quota"

    persisted_headers["x-openxflow-queue-position"] = str(queue_position)
    if rejection_reason is not None:
        persisted_headers["x-openxflow-queue-rejection"] = rejection_reason
        normalized_queue_key = f"{connection_id}:rejected:{external_event_id}"

    job = ChannelWebhookJob(
        connection_id=connection_id,
        channel_type=channel_type,
        external_event_id=external_event_id,
        external_conversation_id=external_conversation_id,
        external_user_id=external_user_id,
        conversation_type=conversation_type,
        queue_key=normalized_queue_key,
        headers_data=persisted_headers,
        payload=payload,
        max_attempts=config.max_attempts,
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        duplicate = (
            await session.exec(
                select(ChannelWebhookJob.id).where(
                    ChannelWebhookJob.connection_id == connection_id,
                    ChannelWebhookJob.external_event_id == external_event_id,
                )
            )
        ).first()
        if duplicate is not None:
            return False
        raise
    return True


def _claimable(now):  # type: ignore[no-untyped-def]
    return sa.or_(
        sa.and_(
            ChannelWebhookJob.status == ChannelWebhookJobStatus.PENDING.value,
            ChannelWebhookJob.next_attempt_at <= now,
        ),
        sa.and_(
            ChannelWebhookJob.status == ChannelWebhookJobStatus.PROCESSING.value,
            sa.or_(
                ChannelWebhookJob.lease_expires_at.is_(None),
                ChannelWebhookJob.lease_expires_at <= now,
            ),
        ),
    )


def retry_delay_seconds(attempts: int) -> float:
    """Return bounded exponential retry delay for a one-based attempt count."""
    if attempts <= 0:
        raise ValueError("attempts must be positive")
    config = durable_webhook_job_config()
    return min(
        config.retry_max_seconds,
        config.retry_base_seconds * (2 ** (attempts - 1)),
    )


async def recover_stale_event_receipt(session: AsyncSession, job: ChannelWebhookJob) -> bool:
    """Reset a crash-left processing receipt so the deduplicator can reclaim the event."""
    receipt = (
        await session.exec(
            select(ChannelEventReceipt).where(
                ChannelEventReceipt.connection_id == job.connection_id,
                ChannelEventReceipt.external_event_id == job.external_event_id,
            )
        )
    ).first()
    if receipt is None or receipt.status != ChannelReceiptStatus.PROCESSING.value:
        return False
    receipt.status = ChannelReceiptStatus.FAILED.value
    receipt.error_message = "Recovered after durable webhook job lease expiration"
    receipt.processed_at = utc_now()
    session.add(receipt)
    await session.commit()
    return True


async def claim_provider_webhook_job(
    session: AsyncSession,
    *,
    worker_id: UUID,
) -> ChannelWebhookJob | None:
    """Claim one ready job while preserving per-queue FIFO and connection limits.

    Claimers serialize on the connection row. PostgreSQL therefore cannot race
    past max_concurrency or claim two jobs for the same queue; SQLite retains its
    normal single-writer behavior for development and tests.
    """
    config = durable_webhook_job_config()
    now = utc_now()
    candidate_ids = list(
        (
            await session.exec(
                select(ChannelWebhookJob.id)
                .where(_claimable(now))
                .order_by(ChannelWebhookJob.next_attempt_at, ChannelWebhookJob.created_at, ChannelWebhookJob.id)
                .limit(32)
            )
        ).all()
    )
    active_processing = sa.and_(
        ChannelWebhookJob.status == ChannelWebhookJobStatus.PROCESSING.value,
        ChannelWebhookJob.lease_expires_at.is_not(None),
        ChannelWebhookJob.lease_expires_at > now,
    )

    for candidate_id in candidate_ids:
        candidate = await session.get(ChannelWebhookJob, candidate_id)
        if candidate is None:
            await session.rollback()
            continue

        limits = (
            await session.exec(
                select(
                    ChannelConnection.max_concurrency,
                    ChannelConnection.per_user_concurrency,
                )
                .where(ChannelConnection.id == candidate.connection_id)
                .with_for_update()
            )
        ).first()
        max_concurrency = int(limits[0]) if limits is not None else max(1, config.worker_count)

        connection_active = int(
            (
                await session.exec(
                    select(sa.func.count(ChannelWebhookJob.id)).where(
                        ChannelWebhookJob.connection_id == candidate.connection_id,
                        active_processing,
                    )
                )
            ).one()
        )
        if connection_active >= max_concurrency:
            await session.rollback()
            continue

        rejection_job = "x-openxflow-queue-rejection" in candidate.headers_data
        if not rejection_job:
            head_id = (
                await session.exec(
                    select(ChannelWebhookJob.id)
                    .where(
                        ChannelWebhookJob.queue_key == candidate.queue_key,
                        ChannelWebhookJob.status == ChannelWebhookJobStatus.PENDING.value,
                    )
                    .order_by(ChannelWebhookJob.created_at, ChannelWebhookJob.id)
                    .limit(1)
                )
            ).first()
            if candidate.status == ChannelWebhookJobStatus.PENDING.value and head_id != candidate.id:
                await session.rollback()
                continue

            queue_active = int(
                (
                    await session.exec(
                        select(sa.func.count(ChannelWebhookJob.id)).where(
                            ChannelWebhookJob.queue_key == candidate.queue_key,
                            active_processing,
                        )
                    )
                ).one()
            )
            # Every normalized context key is FIFO. Different members or
            # conversations still receive distinct keys and can run in parallel.
            queue_limit = 1
            if queue_active >= queue_limit:
                await session.rollback()
                continue

        result = await session.exec(
            sa.update(ChannelWebhookJob)
            .where(ChannelWebhookJob.id == candidate_id, _claimable(now))
            .execution_options(synchronize_session=False)
            .values(
                status=ChannelWebhookJobStatus.PROCESSING.value,
                attempts=ChannelWebhookJob.attempts + 1,
                lease_owner=worker_id,
                lease_expires_at=now + timedelta(seconds=config.lease_seconds),
                updated_at=now,
                last_error=None,
            )
        )
        if result.rowcount != 1:
            await session.rollback()
            continue
        await session.commit()
        await session.refresh(candidate)
        return candidate
    await session.rollback()
    return None


async def complete_provider_webhook_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: UUID,
) -> bool:
    now = utc_now()
    result = await session.exec(
        sa.update(ChannelWebhookJob)
        .where(
            ChannelWebhookJob.id == job_id,
            ChannelWebhookJob.status == ChannelWebhookJobStatus.PROCESSING.value,
            ChannelWebhookJob.lease_owner == worker_id,
        )
        .values(
            status=ChannelWebhookJobStatus.COMPLETED.value,
            lease_owner=None,
            lease_expires_at=None,
            completed_at=now,
            updated_at=now,
            last_error=None,
        )
    )
    await session.commit()
    return result.rowcount == 1


async def fail_provider_webhook_job(
    session: AsyncSession,
    *,
    job: ChannelWebhookJob,
    worker_id: UUID,
    error: str,
) -> bool:
    """Schedule retry or mark the leased job terminally failed."""
    now = utc_now()
    exhausted = job.attempts >= job.max_attempts
    if exhausted:
        status = ChannelWebhookJobStatus.FAILED.value
        next_attempt_at = job.next_attempt_at
    else:
        status = ChannelWebhookJobStatus.PENDING.value
        next_attempt_at = now + timedelta(seconds=retry_delay_seconds(job.attempts))

    result = await session.exec(
        sa.update(ChannelWebhookJob)
        .where(
            ChannelWebhookJob.id == job.id,
            ChannelWebhookJob.status == ChannelWebhookJobStatus.PROCESSING.value,
            ChannelWebhookJob.lease_owner == worker_id,
        )
        .values(
            status=status,
            lease_owner=None,
            lease_expires_at=None,
            next_attempt_at=next_attempt_at,
            updated_at=now,
            last_error=error[:2000],
        )
    )
    await session.commit()
    return result.rowcount == 1


async def durable_webhook_job_depths(session: AsyncSession) -> dict[str, int]:
    """Return shared durable queue depth grouped by lifecycle status."""
    rows = (
        await session.exec(
            select(ChannelWebhookJob.status, sa.func.count(ChannelWebhookJob.id)).group_by(ChannelWebhookJob.status)
        )
    ).all()
    depths = {status.value: 0 for status in ChannelWebhookJobStatus}
    for status, count in rows:
        depths[str(status)] = int(count)
    return depths


async def cleanup_durable_webhook_jobs(session: AsyncSession) -> int:
    """Delete one oldest-first batch across both terminal job statuses."""
    config = durable_webhook_job_config()
    now = utc_now()
    completed_cutoff = now - timedelta(days=config.completed_retention_days)
    failed_cutoff = now - timedelta(days=config.failed_retention_days)
    eligible = sa.or_(
        sa.and_(
            ChannelWebhookJob.status == ChannelWebhookJobStatus.COMPLETED.value,
            ChannelWebhookJob.updated_at <= completed_cutoff,
        ),
        sa.and_(
            ChannelWebhookJob.status == ChannelWebhookJobStatus.FAILED.value,
            ChannelWebhookJob.updated_at <= failed_cutoff,
        ),
    )
    ids = list(
        (
            await session.exec(
                select(ChannelWebhookJob.id)
                .where(eligible)
                .order_by(ChannelWebhookJob.updated_at, ChannelWebhookJob.created_at)
                .limit(config.cleanup_batch_size)
            )
        ).all()
    )
    if not ids:
        await session.rollback()
        return 0
    result = await session.exec(sa.delete(ChannelWebhookJob).where(ChannelWebhookJob.id.in_(ids)))
    await session.commit()
    return max(0, int(result.rowcount or 0))


class DurableWebhookJobWorker:
    """Run process-local consumers for the shared database webhook queue."""

    def __init__(self) -> None:
        self.worker_id = uuid4()
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._maintenance_task: asyncio.Task[None] | None = None

    async def run(self) -> None:
        config = durable_webhook_job_config()
        if not config.enabled:
            await logger.adebug("Durable channel webhook jobs are disabled")
            return
        worker_count = config.worker_count
        self._tasks = [
            asyncio.create_task(self._consume(index), name=f"channel-webhook-job-{index}")
            for index in range(worker_count)
        ]
        self._maintenance_task = asyncio.create_task(
            self._maintain(),
            name="channel-webhook-job-maintenance",
        )
        record_durable_webhook_manager_started(worker_count)
        try:
            await self._stop_event.wait()
        finally:
            tasks = [*self._tasks]
            if self._maintenance_task is not None:
                tasks.append(self._maintenance_task)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._tasks.clear()
            self._maintenance_task = None
            record_durable_webhook_manager_stopped(worker_count)

    async def stop(self) -> None:
        self._stop_event.set()

    async def _consume(self, _index: int) -> None:
        config = durable_webhook_job_config()
        while not self._stop_event.is_set():
            job = await self._claim_one()
            if job is None:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=config.poll_seconds)
                except TimeoutError:
                    pass
                continue
            try:
                await self._process(job)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                await logger.aexception(
                    "Durable channel webhook consumer failed while persisting job %s outcome",
                    job.id,
                )

    async def _maintain(self) -> None:
        config = durable_webhook_job_config()
        while not self._stop_event.is_set():
            try:
                async with session_scope() as session:
                    deleted = await cleanup_durable_webhook_jobs(session)
                    depths = await durable_webhook_job_depths(session)
                record_durable_webhook_cleaned(deleted)
                set_durable_webhook_queue_depths(
                    pending=depths[ChannelWebhookJobStatus.PENDING.value],
                    processing=depths[ChannelWebhookJobStatus.PROCESSING.value],
                    completed=depths[ChannelWebhookJobStatus.COMPLETED.value],
                    failed=depths[ChannelWebhookJobStatus.FAILED.value],
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                record_durable_webhook_maintenance_error()
                await logger.aexception("Unable to maintain durable channel webhook jobs")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=config.cleanup_interval_seconds,
                )
            except TimeoutError:
                pass

    async def _claim_one(self) -> ChannelWebhookJob | None:
        try:
            async with session_scope() as session:
                job = await claim_provider_webhook_job(session, worker_id=self.worker_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            record_durable_webhook_claim_error()
            await logger.aexception("Unable to claim a durable channel webhook job")
            return None
        if job is not None:
            record_durable_webhook_claimed()
        return job

    async def _execute(self, job: ChannelWebhookJob) -> bool:
        async with session_scope() as session:
            await recover_stale_event_receipt(session, job)
        created_at = job.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=utc_now().tzinfo)
        queue_wait_ms = max(0, int((utc_now() - created_at).total_seconds() * 1000))
        raw_position = job.headers_data.get("x-openxflow-queue-position", "0")
        try:
            queue_position = max(0, int(str(raw_position)))
        except ValueError:
            queue_position = 0
        rejection_reason = job.headers_data.get("x-openxflow-queue-rejection")
        return await process_provider_webhook(
            connection_id=job.connection_id,
            expected_channel_type=job.channel_type,
            headers={str(key): str(value) for key, value in job.headers_data.items()},
            payload=job.payload,
            preverified=True,
            queue_wait_ms=queue_wait_ms,
            queue_position=queue_position,
            queue_rejection_reason=str(rejection_reason) if rejection_reason else None,
        )

    async def _process(self, job: ChannelWebhookJob) -> None:
        error = "Channel webhook processing failed"
        started_at = time.perf_counter()
        try:
            try:
                success = await asyncio.wait_for(
                    self._execute(job),
                    timeout=webhook_task_timeout_seconds(),
                )
            except TimeoutError:
                success = False
                error = "Channel webhook processing timed out"
                await logger.aerror("Durable channel webhook job %s timed out", job.id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                success = False
                error = str(exc) or type(exc).__name__
                await logger.aexception("Durable channel webhook job %s crashed", job.id)
        finally:
            record_webhook_execution(time.perf_counter() - started_at)

        async with session_scope() as session:
            if success:
                updated = await complete_provider_webhook_job(
                    session,
                    job_id=job.id,
                    worker_id=self.worker_id,
                )
                if updated:
                    record_durable_webhook_completed()
            else:
                updated = await fail_provider_webhook_job(
                    session,
                    job=job,
                    worker_id=self.worker_id,
                    error=error,
                )
                if updated:
                    if job.attempts >= job.max_attempts:
                        record_durable_webhook_failed()
                    else:
                        record_durable_webhook_retried()


@asynccontextmanager
async def durable_webhook_job_lifespan(_app):  # type: ignore[no-untyped-def]
    worker = DurableWebhookJobWorker()
    task = asyncio.create_task(worker.run(), name="channel-webhook-job-worker")
    try:
        yield
    finally:
        await worker.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
