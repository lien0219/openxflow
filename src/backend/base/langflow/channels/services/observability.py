"""Persistent channel operations views, statistics, and controlled retries."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.services.database.models.channel.execution_model import (
    ChannelExecutionLog,
    ChannelExecutionStatus,
)
from langflow.services.database.models.channel.message_model import (
    ChannelMessageDirection,
    ChannelMessageRecord,
    ChannelMessageRecordStatus,
)
from langflow.services.database.models.channel.model import (
    ChannelEventReceipt,
    ChannelReceiptStatus,
    utc_now,
)
from langflow.services.database.models.channel.outbound_delivery_model import (
    ChannelOutboundDelivery,
    ChannelOutboundDeliveryStatus,
)
from langflow.services.database.models.channel.webhook_job_model import (
    ChannelWebhookJob,
    ChannelWebhookJobStatus,
)


class ChannelOutboundDeliveryRead(BaseModel):
    id: UUID
    connection_id: UUID
    external_event_id: str
    delivery_kind: str
    response_digest: str
    status: str
    attempts: int
    provider_message_id: str | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None = None


class ChannelOutboundDeliveryPage(BaseModel):
    items: list[ChannelOutboundDeliveryRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class ChannelConnectionOverview(BaseModel):
    window_hours: int
    started_at: datetime
    ended_at: datetime
    active_conversations: int = 0
    unique_external_users: int = 0
    inbound_messages: int = 0
    outbound_messages: int = 0
    failed_messages: int = 0
    queued_jobs: int = 0
    processing_jobs: int = 0
    failed_jobs: int = 0
    sent_deliveries: int = 0
    failed_deliveries: int = 0
    reserved_deliveries: int = 0
    execution_counts: dict[str, int] = Field(default_factory=dict)
    execution_success_rate: float = 0.0
    average_execution_duration_ms: float | None = None
    p95_execution_duration_ms: int | None = None
    average_queue_wait_ms: float | None = None
    p95_queue_wait_ms: int | None = None


class ChannelRetryDeliveryResult(BaseModel):
    delivery_id: UUID
    webhook_job_id: UUID
    status: str
    already_queued: bool = False


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


async def read_connection_overview(
    session: AsyncSession,
    connection_id: UUID,
    *,
    window_hours: int = 24,
) -> ChannelConnectionOverview:
    normalized_window = min(24 * 90, max(1, window_hours))
    ended_at = utc_now()
    started_at = ended_at - timedelta(hours=normalized_window)

    message_rows = (
        await session.exec(
            select(
                ChannelMessageRecord.direction,
                ChannelMessageRecord.status,
                sa.func.count(ChannelMessageRecord.id),
            )
            .where(
                ChannelMessageRecord.connection_id == connection_id,
                ChannelMessageRecord.created_at >= started_at,
            )
            .group_by(ChannelMessageRecord.direction, ChannelMessageRecord.status)
        )
    ).all()
    inbound_messages = 0
    outbound_messages = 0
    failed_messages = 0
    for direction, status, count in message_rows:
        if direction == ChannelMessageDirection.INBOUND.value:
            inbound_messages += int(count)
        elif direction == ChannelMessageDirection.OUTBOUND.value:
            outbound_messages += int(count)
        if status == ChannelMessageRecordStatus.FAILED.value:
            failed_messages += int(count)

    execution_rows = (
        await session.exec(
            select(ChannelExecutionLog.status, sa.func.count(ChannelExecutionLog.id))
            .where(
                ChannelExecutionLog.connection_id == connection_id,
                ChannelExecutionLog.created_at >= started_at,
            )
            .group_by(ChannelExecutionLog.status)
        )
    ).all()
    execution_counts = {status.value: 0 for status in ChannelExecutionStatus}
    for execution_status, count in execution_rows:
        execution_counts[str(execution_status)] = int(count)
    terminal_total = sum(
        execution_counts.get(status.value, 0)
        for status in (
            ChannelExecutionStatus.SUCCEEDED,
            ChannelExecutionStatus.FAILED,
            ChannelExecutionStatus.TIMEOUT,
            ChannelExecutionStatus.CANCELLED,
            ChannelExecutionStatus.DELIVERY_FAILED,
        )
    )
    success_rate = execution_counts[ChannelExecutionStatus.SUCCEEDED.value] / terminal_total if terminal_total else 0.0

    duration_rows = (
        await session.exec(
            select(ChannelExecutionLog.duration_ms, ChannelExecutionLog.queue_wait_ms).where(
                ChannelExecutionLog.connection_id == connection_id,
                ChannelExecutionLog.created_at >= started_at,
            )
        )
    ).all()
    durations = [int(duration) for duration, _queue_wait in duration_rows if duration is not None]
    queue_waits = [int(queue_wait) for _duration, queue_wait in duration_rows if queue_wait is not None]

    job_rows = (
        await session.exec(
            select(ChannelWebhookJob.status, sa.func.count(ChannelWebhookJob.id))
            .where(
                ChannelWebhookJob.connection_id == connection_id,
                ChannelWebhookJob.created_at >= started_at,
            )
            .group_by(ChannelWebhookJob.status)
        )
    ).all()
    job_counts = {status.value: 0 for status in ChannelWebhookJobStatus}
    for job_status, count in job_rows:
        job_counts[str(job_status)] = int(count)

    delivery_rows = (
        await session.exec(
            select(ChannelOutboundDelivery.status, sa.func.count(ChannelOutboundDelivery.id))
            .where(
                ChannelOutboundDelivery.connection_id == connection_id,
                ChannelOutboundDelivery.created_at >= started_at,
            )
            .group_by(ChannelOutboundDelivery.status)
        )
    ).all()
    delivery_counts = {status.value: 0 for status in ChannelOutboundDeliveryStatus}
    for delivery_status, count in delivery_rows:
        delivery_counts[str(delivery_status)] = int(count)

    active_conversations = int(
        (
            await session.exec(
                select(sa.func.count(sa.distinct(ChannelMessageRecord.external_conversation_id))).where(
                    ChannelMessageRecord.connection_id == connection_id,
                    ChannelMessageRecord.created_at >= started_at,
                )
            )
        ).one()
    )
    unique_external_users = int(
        (
            await session.exec(
                select(sa.func.count(sa.distinct(ChannelMessageRecord.external_user_id))).where(
                    ChannelMessageRecord.connection_id == connection_id,
                    ChannelMessageRecord.created_at >= started_at,
                    ChannelMessageRecord.external_user_id.is_not(None),
                )
            )
        ).one()
    )

    return ChannelConnectionOverview(
        window_hours=normalized_window,
        started_at=started_at,
        ended_at=ended_at,
        active_conversations=active_conversations,
        unique_external_users=unique_external_users,
        inbound_messages=inbound_messages,
        outbound_messages=outbound_messages,
        failed_messages=failed_messages,
        queued_jobs=job_counts[ChannelWebhookJobStatus.PENDING.value],
        processing_jobs=job_counts[ChannelWebhookJobStatus.PROCESSING.value],
        failed_jobs=job_counts[ChannelWebhookJobStatus.FAILED.value],
        sent_deliveries=delivery_counts[ChannelOutboundDeliveryStatus.SENT.value],
        failed_deliveries=delivery_counts[ChannelOutboundDeliveryStatus.FAILED.value],
        reserved_deliveries=delivery_counts[ChannelOutboundDeliveryStatus.RESERVED.value],
        execution_counts=execution_counts,
        execution_success_rate=round(success_rate, 4),
        average_execution_duration_ms=round(sum(durations) / len(durations), 2) if durations else None,
        p95_execution_duration_ms=_percentile(durations, 0.95),
        average_queue_wait_ms=round(sum(queue_waits) / len(queue_waits), 2) if queue_waits else None,
        p95_queue_wait_ms=_percentile(queue_waits, 0.95),
    )


async def list_outbound_deliveries(
    session: AsyncSession,
    connection_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    delivery_kind: str | None = None,
    query: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> ChannelOutboundDeliveryPage:
    normalized_page = max(1, page)
    normalized_page_size = min(100, max(1, page_size))
    filters: list[Any] = [ChannelOutboundDelivery.connection_id == connection_id]
    if status:
        filters.append(ChannelOutboundDelivery.status == status)
    if delivery_kind:
        filters.append(ChannelOutboundDelivery.delivery_kind == delivery_kind)
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        filters.append(
            sa.or_(
                ChannelOutboundDelivery.external_event_id.ilike(pattern),
                ChannelOutboundDelivery.provider_message_id.ilike(pattern),
                ChannelOutboundDelivery.last_error.ilike(pattern),
            )
        )
    if created_from is not None:
        filters.append(ChannelOutboundDelivery.created_at >= created_from)
    if created_to is not None:
        filters.append(ChannelOutboundDelivery.created_at <= created_to)

    total = int(
        (await session.exec(select(sa.func.count()).select_from(ChannelOutboundDelivery).where(*filters))).one()
    )
    rows = (
        await session.exec(
            select(ChannelOutboundDelivery)
            .where(*filters)
            .order_by(ChannelOutboundDelivery.created_at.desc(), ChannelOutboundDelivery.id.desc())
            .offset((normalized_page - 1) * normalized_page_size)
            .limit(normalized_page_size)
        )
    ).all()
    return ChannelOutboundDeliveryPage(
        items=[ChannelOutboundDeliveryRead.model_validate(row, from_attributes=True) for row in rows],
        page=normalized_page,
        page_size=normalized_page_size,
        total=total,
        total_pages=math.ceil(total / normalized_page_size) if total else 0,
    )


async def retry_failed_outbound_delivery(
    session: AsyncSession,
    *,
    connection_id: UUID,
    delivery_id: UUID,
) -> ChannelRetryDeliveryResult:
    delivery = await session.get(ChannelOutboundDelivery, delivery_id)
    if delivery is None or delivery.connection_id != connection_id:
        raise LookupError("Outbound delivery not found")
    if delivery.status != ChannelOutboundDeliveryStatus.FAILED.value:
        raise ValueError("Only failed outbound deliveries can be retried")

    job = (
        await session.exec(
            select(ChannelWebhookJob).where(
                ChannelWebhookJob.connection_id == connection_id,
                ChannelWebhookJob.external_event_id == delivery.external_event_id,
            )
        )
    ).first()
    if job is None:
        raise ValueError("The original durable webhook job is no longer available")
    if job.status in {
        ChannelWebhookJobStatus.PENDING.value,
        ChannelWebhookJobStatus.PROCESSING.value,
    }:
        return ChannelRetryDeliveryResult(
            delivery_id=delivery.id,
            webhook_job_id=job.id,
            status=job.status,
            already_queued=True,
        )

    receipt = (
        await session.exec(
            select(ChannelEventReceipt).where(
                ChannelEventReceipt.connection_id == connection_id,
                ChannelEventReceipt.external_event_id == delivery.external_event_id,
            )
        )
    ).first()
    if receipt is not None:
        receipt.status = ChannelReceiptStatus.FAILED.value
        receipt.error_message = "Manual delivery retry requested"
        receipt.processed_at = utc_now()
        session.add(receipt)

    job.status = ChannelWebhookJobStatus.PENDING.value
    job.attempts = 0
    job.lease_owner = None
    job.lease_expires_at = None
    job.next_attempt_at = utc_now()
    job.completed_at = None
    job.last_error = "Manual delivery retry requested"
    job.updated_at = utc_now()
    session.add(job)
    await session.flush()
    return ChannelRetryDeliveryResult(
        delivery_id=delivery.id,
        webhook_job_id=job.id,
        status=job.status,
    )
