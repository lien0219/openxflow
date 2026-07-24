"""Persistence helpers for channel workflow execution audit records."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.services.database.models.channel.execution_model import (
    ChannelExecutionLog,
    ChannelExecutionLogPage,
    ChannelExecutionLogRead,
    ChannelExecutionStatus,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def start_channel_execution(
    session: AsyncSession,
    *,
    connection_id: UUID,
    conversation_binding_id: UUID | None,
    openxflow_user_id: UUID | None,
    flow_id: UUID | None,
    external_event_id: str,
    trigger_type: str,
    command_name: str | None = None,
) -> ChannelExecutionLog:
    execution = ChannelExecutionLog(
        connection_id=connection_id,
        conversation_binding_id=conversation_binding_id,
        openxflow_user_id=openxflow_user_id,
        flow_id=flow_id,
        external_event_id=external_event_id,
        trigger_type=trigger_type,
        command_name=command_name,
        status=ChannelExecutionStatus.RUNNING.value,
    )
    session.add(execution)
    await session.flush()
    await session.refresh(execution)
    return execution


async def finish_channel_execution(
    session: AsyncSession,
    execution: ChannelExecutionLog,
    *,
    succeeded: bool,
    error_message: str | None = None,
) -> None:
    completed_at = _utc_now()
    execution.status = (
        ChannelExecutionStatus.SUCCEEDED.value if succeeded else ChannelExecutionStatus.FAILED.value
    )
    execution.completed_at = completed_at
    execution.duration_ms = max(0, int((completed_at - execution.created_at).total_seconds() * 1000))
    execution.error_message = error_message[:4000] if error_message else None
    session.add(execution)
    await session.flush()


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
) -> ChannelExecutionLogPage:
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

    total_statement = select(func.count()).select_from(ChannelExecutionLog).where(*filters)
    total = int((await session.exec(total_statement)).one())
    statement = (
        select(ChannelExecutionLog)
        .where(*filters)
        .order_by(ChannelExecutionLog.created_at.desc(), ChannelExecutionLog.id)
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    )
    rows = (await session.exec(statement)).all()
    return ChannelExecutionLogPage(
        items=[ChannelExecutionLogRead.model_validate(row, from_attributes=True) for row in rows],
        page=normalized_page,
        page_size=normalized_page_size,
        total=total,
        total_pages=math.ceil(total / normalized_page_size) if total else 0,
    )
