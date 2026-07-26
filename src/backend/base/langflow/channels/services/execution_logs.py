"""Persistence helpers for channel workflow execution audit records."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

import sqlalchemy as sa
from lfx.log.logger import logger
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.services.runtime_config import webhook_task_timeout_seconds
from langflow.services.database.models.channel.execution_model import (
    ChannelExecutionLog,
    ChannelExecutionLogPage,
    ChannelExecutionLogRead,
    ChannelExecutionStatus,
)
from langflow.services.deps import session_scope


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Normalize database datetimes before arithmetic.

    SQLite drops timezone information even when DateTime(timezone=True) is used,
    while PostgreSQL returns aware values. Normalizing here keeps the execution
    log API portable and prevents naive/aware subtraction failures.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def start_channel_execution(
    session: AsyncSession,
    *,
    connection_id: UUID,
    conversation_binding_id: UUID | None,
    openxflow_user_id: UUID | None,
    external_user_id: str | None,
    session_id: str | None,
    execution_identity_type: str,
    flow_id: UUID | None,
    external_event_id: str,
    trigger_type: str,
    command_name: str | None = None,
    queue_wait_ms: int | None = None,
) -> ChannelExecutionLog:
    now = _utc_now()
    execution = ChannelExecutionLog(
        connection_id=connection_id,
        conversation_binding_id=conversation_binding_id,
        openxflow_user_id=openxflow_user_id,
        external_user_id=external_user_id,
        session_id=session_id,
        execution_identity_type=execution_identity_type,
        flow_id=flow_id,
        external_event_id=external_event_id,
        trigger_type=trigger_type,
        command_name=command_name,
        status=ChannelExecutionStatus.RUNNING.value,
        queue_wait_ms=queue_wait_ms,
        started_at=now,
    )
    session.add(execution)
    await session.flush()
    await session.refresh(execution)
    return execution


async def finish_channel_execution(
    session: AsyncSession,
    execution: ChannelExecutionLog,
    *,
    status: str,
    error_message: str | None = None,
    error_code: str | None = None,
) -> None:
    completed_at = _utc_now()
    execution.status = status
    execution.completed_at = completed_at
    started_at = _as_utc(execution.started_at or execution.created_at)
    execution.duration_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))
    execution.error_code = error_code[:128] if error_code else None
    execution.error_message = error_message[:4000] if error_message else None
    session.add(execution)
    await session.flush()


async def finalize_channel_execution(
    execution_id: UUID,
    *,
    status: str,
    error_message: str | None = None,
    error_code: str | None = None,
) -> None:
    async def persist() -> None:
        async with session_scope() as session:
            execution = await session.get(ChannelExecutionLog, execution_id)
            if execution is None:
                return
            await finish_channel_execution(
                session,
                execution,
                status=status,
                error_message=error_message,
                error_code=error_code,
            )
            await session.commit()

    task = asyncio.create_task(persist())
    await asyncio.shield(task)


async def record_channel_delivery_outcome(
    *,
    connection_id: UUID,
    external_event_id: str,
    duration_ms: int,
    error: Exception | None = None,
) -> None:
    async with session_scope() as session:
        execution = (
            await session.exec(
                select(ChannelExecutionLog)
                .where(
                    ChannelExecutionLog.connection_id == connection_id,
                    ChannelExecutionLog.external_event_id == external_event_id,
                )
                .order_by(ChannelExecutionLog.created_at.desc())
                .limit(1)
            )
        ).first()
        if execution is None:
            return
        execution.delivery_duration_ms = max(0, duration_ms)
        if error is not None:
            execution.status = ChannelExecutionStatus.DELIVERY_FAILED.value
            execution.error_code = type(error).__name__[:128]
            execution.error_message = str(error)[:4000]
        session.add(execution)
        await session.commit()


async def safe_record_channel_delivery_outcome(
    *,
    connection_id: UUID,
    external_event_id: str,
    duration_ms: int,
    error: Exception | None = None,
) -> None:
    try:
        await record_channel_delivery_outcome(
            connection_id=connection_id,
            external_event_id=external_event_id,
            duration_ms=duration_ms,
            error=error,
        )
    except Exception:  # noqa: BLE001
        await logger.aexception("Unable to persist channel delivery outcome for %s", external_event_id)


async def _fail_stale_channel_executions(session: AsyncSession, connection_id: UUID) -> None:
    cutoff = _utc_now() - timedelta(seconds=webhook_task_timeout_seconds() + 60)
    statement = select(ChannelExecutionLog).where(
        ChannelExecutionLog.connection_id == connection_id,
        ChannelExecutionLog.status == ChannelExecutionStatus.RUNNING.value,
        ChannelExecutionLog.created_at <= cutoff,
    )
    stale_rows = (await session.exec(statement)).all()
    for execution in stale_rows:
        await finish_channel_execution(
            session,
            execution,
            status=ChannelExecutionStatus.TIMEOUT.value,
            error_code="execution_timeout",
            error_message="Channel workflow execution was interrupted or timed out",
        )
    if stale_rows:
        await session.commit()


async def list_channel_executions(
    session: AsyncSession,
    connection_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    conversation_binding_id: UUID | None = None,
    openxflow_user_id: UUID | None = None,
    status: str | None = None,
    trigger_type: str | None = None,
    query: str | None = None,
    external_user_id: str | None = None,
    session_id: str | None = None,
    execution_identity_type: str | None = None,
    flow_id: UUID | None = None,
    error_code: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> ChannelExecutionLogPage:
    await _fail_stale_channel_executions(session, connection_id)
    normalized_page = max(1, page)
    normalized_page_size = min(100, max(1, page_size))
    filters: list = [ChannelExecutionLog.connection_id == connection_id]
    if conversation_binding_id is not None:
        filters.append(ChannelExecutionLog.conversation_binding_id == conversation_binding_id)
    if openxflow_user_id is not None:
        filters.append(ChannelExecutionLog.openxflow_user_id == openxflow_user_id)
    if status:
        filters.append(ChannelExecutionLog.status == status)
    if trigger_type:
        filters.append(ChannelExecutionLog.trigger_type == trigger_type)
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        filters.append(
            sa.or_(
                ChannelExecutionLog.external_event_id.ilike(pattern),
                ChannelExecutionLog.external_user_id.ilike(pattern),
                ChannelExecutionLog.session_id.ilike(pattern),
                ChannelExecutionLog.command_name.ilike(pattern),
                ChannelExecutionLog.error_code.ilike(pattern),
                ChannelExecutionLog.error_message.ilike(pattern),
            )
        )
    if external_user_id:
        filters.append(ChannelExecutionLog.external_user_id == external_user_id)
    if session_id:
        filters.append(ChannelExecutionLog.session_id == session_id)
    if execution_identity_type:
        filters.append(ChannelExecutionLog.execution_identity_type == execution_identity_type)
    if flow_id is not None:
        filters.append(ChannelExecutionLog.flow_id == flow_id)
    if error_code:
        filters.append(ChannelExecutionLog.error_code == error_code)
    if created_from is not None:
        filters.append(ChannelExecutionLog.created_at >= created_from)
    if created_to is not None:
        filters.append(ChannelExecutionLog.created_at <= created_to)

    total = int((await session.exec(select(func.count()).select_from(ChannelExecutionLog).where(*filters))).one())
    rows = (
        await session.exec(
            select(ChannelExecutionLog)
            .where(*filters)
            .order_by(ChannelExecutionLog.created_at.desc(), ChannelExecutionLog.id)
            .offset((normalized_page - 1) * normalized_page_size)
            .limit(normalized_page_size)
        )
    ).all()
    return ChannelExecutionLogPage(
        items=[ChannelExecutionLogRead.model_validate(row, from_attributes=True) for row in rows],
        page=normalized_page,
        page_size=normalized_page_size,
        total=total,
        total_pages=math.ceil(total / normalized_page_size) if total else 0,
    )
