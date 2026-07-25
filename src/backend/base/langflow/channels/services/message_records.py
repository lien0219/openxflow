"""Best-effort persistence and querying for the unified channel message center."""

from __future__ import annotations

import inspect
import math
from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from lfx.log.logger import logger
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.domain.models import ChannelEvent, ChannelMessage
from langflow.channels.services.conversation_scope import conversation_scope_id
from langflow.services.database.models.channel.execution_model import ChannelExecutionLog
from langflow.services.database.models.channel.message_model import (
    ChannelMessageDirection,
    ChannelMessageRecord,
    ChannelMessageRecordKind,
    ChannelMessageRecordPage,
    ChannelMessageRecordRead,
    ChannelMessageRecordStatus,
)
from langflow.services.database.models.channel.model import ChannelConversationBinding, utc_now
from langflow.services.deps import session_scope

_MAX_RETAINED_TEXT = 16_000
_SAFE_METADATA_KEYS = {
    "queue_wait_ms",
    "queue_position",
    "conversation_scope_id",
    "thread_id",
    "message_thread_id",
    "topic_id",
    "message_thread_topic_id",
    "provider_message_type",
    "content_type",
}


async def _add_to_session(session: AsyncSession, value: Any) -> None:
    result = session.add(value)
    if inspect.isawaitable(result):
        await result


def _safe_scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)[:1000]


def _safe_event_metadata(event: ChannelEvent) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "channel": event.channel.value,
        "event_type": event.event_type.value,
        "conversation_type": event.conversation.conversation_type,
        "mentions_count": len(event.message.mentions),
    }
    for source in (event.conversation.metadata, event.message.metadata):
        for key in _SAFE_METADATA_KEYS:
            if key in source:
                metadata[key] = _safe_scalar(source[key])
    return metadata


def _inbound_text(event: ChannelEvent) -> str | None:
    text = (event.message.text or "").strip()
    if text:
        return text[:_MAX_RETAINED_TEXT]
    if event.message.attachments:
        names = "、".join(attachment.filename for attachment in event.message.attachments[:20])
        return f"[附件] {names}"[:_MAX_RETAINED_TEXT]
    return None


def _outbound_text(message: ChannelMessage) -> str | None:
    text = (message.markdown or message.text or "").strip()
    if message.title:
        text = f"{message.title}\n{text}".strip()
    return text[:_MAX_RETAINED_TEXT] or None


async def _related_ids(session: AsyncSession, event: ChannelEvent) -> tuple[UUID | None, UUID | None]:
    binding_id = (
        await session.exec(
            select(ChannelConversationBinding.id).where(
                ChannelConversationBinding.connection_id == event.connection_id,
                ChannelConversationBinding.external_conversation_id == event.conversation.external_conversation_id,
            )
        )
    ).first()
    execution_id = (
        await session.exec(
            select(ChannelExecutionLog.id)
            .where(
                ChannelExecutionLog.connection_id == event.connection_id,
                ChannelExecutionLog.external_event_id == event.event_id,
            )
            .order_by(ChannelExecutionLog.created_at.desc())
            .limit(1)
        )
    ).first()
    return binding_id, execution_id


async def record_inbound_message(event: ChannelEvent) -> None:
    async with session_scope() as session:
        binding_id, execution_id = await _related_ids(session, event)
        existing = (
            await session.exec(
                select(ChannelMessageRecord).where(
                    ChannelMessageRecord.connection_id == event.connection_id,
                    ChannelMessageRecord.external_event_id == event.event_id,
                    ChannelMessageRecord.direction == ChannelMessageDirection.INBOUND.value,
                    ChannelMessageRecord.message_kind == ChannelMessageRecordKind.INBOUND.value,
                )
            )
        ).first()
        now = utc_now()
        if existing is None:
            existing = ChannelMessageRecord(
                connection_id=event.connection_id,
                conversation_binding_id=binding_id,
                execution_id=execution_id,
                external_event_id=event.event_id,
                external_message_id=event.message.external_message_id,
                external_conversation_id=event.conversation.external_conversation_id,
                conversation_scope_id=conversation_scope_id(event),
                external_user_id=event.user.external_user_id,
                sender_name=event.user.display_name,
                direction=ChannelMessageDirection.INBOUND.value,
                message_kind=ChannelMessageRecordKind.INBOUND.value,
                message_type=event.message.message_type.value,
                status=ChannelMessageRecordStatus.RECEIVED.value,
                text=_inbound_text(event),
                has_attachments=bool(event.message.attachments),
                attachment_count=len(event.message.attachments),
                reply_to_message_id=event.message.reply_to_message_id,
                metadata_data=_safe_event_metadata(event),
            )
            await _add_to_session(session, existing)
        else:
            existing.conversation_binding_id = binding_id or existing.conversation_binding_id
            existing.execution_id = execution_id or existing.execution_id
            existing.status = ChannelMessageRecordStatus.RECEIVED.value
            existing.error_code = None
            existing.error_message = None
            existing.updated_at = now
            await _add_to_session(session, existing)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()


async def mark_inbound_message(
    event: ChannelEvent,
    *,
    status: str,
    error: Exception | None = None,
) -> None:
    async with session_scope() as session:
        execution_id = (
            await session.exec(
                select(ChannelExecutionLog.id)
                .where(
                    ChannelExecutionLog.connection_id == event.connection_id,
                    ChannelExecutionLog.external_event_id == event.event_id,
                )
                .order_by(ChannelExecutionLog.created_at.desc())
                .limit(1)
            )
        ).first()
        values: dict[str, Any] = {
            "status": status,
            "updated_at": utc_now(),
            "execution_id": execution_id,
        }
        if error is not None:
            values["error_code"] = type(error).__name__[:128]
            values["error_message"] = str(error)[:2000]
        else:
            values["error_code"] = None
            values["error_message"] = None
        await session.exec(
            sa.update(ChannelMessageRecord)
            .where(
                ChannelMessageRecord.connection_id == event.connection_id,
                ChannelMessageRecord.external_event_id == event.event_id,
                ChannelMessageRecord.direction == ChannelMessageDirection.INBOUND.value,
                ChannelMessageRecord.message_kind == ChannelMessageRecordKind.INBOUND.value,
            )
            .values(**values)
        )
        await session.commit()


async def record_outbound_message(
    event: ChannelEvent,
    message: ChannelMessage,
    *,
    status: str,
    provider_message_id: str | None = None,
    error: Exception | None = None,
    message_kind: str = ChannelMessageRecordKind.RESPONSE.value,
) -> None:
    async with session_scope() as session:
        binding_id, execution_id = await _related_ids(session, event)
        existing = (
            await session.exec(
                select(ChannelMessageRecord).where(
                    ChannelMessageRecord.connection_id == event.connection_id,
                    ChannelMessageRecord.external_event_id == event.event_id,
                    ChannelMessageRecord.direction == ChannelMessageDirection.OUTBOUND.value,
                    ChannelMessageRecord.message_kind == message_kind,
                )
            )
        ).first()
        now = utc_now()
        values = {
            "conversation_binding_id": binding_id,
            "execution_id": execution_id,
            "provider_message_id": provider_message_id,
            "message_type": message.message_type.value,
            "status": status,
            "text": _outbound_text(message),
            "has_attachments": bool(message.attachments),
            "attachment_count": len(message.attachments),
            "metadata_data": _safe_event_metadata(event),
            "updated_at": now,
            "delivered_at": now if status == ChannelMessageRecordStatus.SENT.value else None,
            "error_code": type(error).__name__[:128] if error else None,
            "error_message": str(error)[:2000] if error else None,
        }
        if existing is not None and provider_message_id is None:
            values.pop("provider_message_id", None)
        if existing is None:
            await _add_to_session(
                session,
                ChannelMessageRecord(
                    connection_id=event.connection_id,
                    external_event_id=event.event_id,
                    external_message_id=event.message.external_message_id,
                    external_conversation_id=event.conversation.external_conversation_id,
                    conversation_scope_id=conversation_scope_id(event),
                    external_user_id=event.user.external_user_id,
                    sender_name="OpenXFlow",
                    direction=ChannelMessageDirection.OUTBOUND.value,
                    message_kind=message_kind,
                    reply_to_message_id=event.message.external_message_id,
                    **values,
                ),
            )
        else:
            for key, value in values.items():
                setattr(existing, key, value)
            await _add_to_session(session, existing)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()


async def safe_record_inbound_message(event: ChannelEvent) -> None:
    try:
        await record_inbound_message(event)
    except Exception:  # noqa: BLE001
        await logger.aexception("Unable to persist inbound channel message %s", event.event_id)


async def safe_mark_inbound_message(
    event: ChannelEvent,
    *,
    status: str,
    error: Exception | None = None,
) -> None:
    try:
        await mark_inbound_message(event, status=status, error=error)
    except Exception:  # noqa: BLE001
        await logger.aexception("Unable to update inbound channel message %s", event.event_id)


async def safe_record_outbound_message(
    event: ChannelEvent,
    message: ChannelMessage,
    *,
    status: str,
    provider_message_id: str | None = None,
    error: Exception | None = None,
    message_kind: str = ChannelMessageRecordKind.RESPONSE.value,
) -> None:
    try:
        await record_outbound_message(
            event,
            message,
            status=status,
            provider_message_id=provider_message_id,
            error=error,
            message_kind=message_kind,
        )
    except Exception:  # noqa: BLE001
        await logger.aexception("Unable to persist outbound channel message %s", event.event_id)


async def list_channel_messages(
    session: AsyncSession,
    connection_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    query: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    conversation_binding_id: UUID | None = None,
    external_conversation_id: str | None = None,
    external_user_id: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> ChannelMessageRecordPage:
    normalized_page = max(1, page)
    normalized_page_size = min(100, max(1, page_size))
    filters: list[Any] = [ChannelMessageRecord.connection_id == connection_id]
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        filters.append(
            sa.or_(
                ChannelMessageRecord.text.ilike(pattern),
                ChannelMessageRecord.sender_name.ilike(pattern),
                ChannelMessageRecord.external_user_id.ilike(pattern),
                ChannelMessageRecord.external_conversation_id.ilike(pattern),
                ChannelMessageRecord.external_message_id.ilike(pattern),
            )
        )
    if direction:
        filters.append(ChannelMessageRecord.direction == direction)
    if status:
        filters.append(ChannelMessageRecord.status == status)
    if conversation_binding_id is not None:
        filters.append(ChannelMessageRecord.conversation_binding_id == conversation_binding_id)
    if external_conversation_id:
        filters.append(ChannelMessageRecord.external_conversation_id == external_conversation_id)
    if external_user_id:
        filters.append(ChannelMessageRecord.external_user_id == external_user_id)
    if created_from is not None:
        filters.append(ChannelMessageRecord.created_at >= created_from)
    if created_to is not None:
        filters.append(ChannelMessageRecord.created_at <= created_to)

    total = int((await session.exec(select(sa.func.count()).select_from(ChannelMessageRecord).where(*filters))).one())
    rows = (
        await session.exec(
            select(ChannelMessageRecord)
            .where(*filters)
            .order_by(ChannelMessageRecord.created_at.desc(), ChannelMessageRecord.id.desc())
            .offset((normalized_page - 1) * normalized_page_size)
            .limit(normalized_page_size)
        )
    ).all()
    return ChannelMessageRecordPage(
        items=[ChannelMessageRecordRead.model_validate(row, from_attributes=True) for row in rows],
        page=normalized_page,
        page_size=normalized_page_size,
        total=total,
        total_pages=math.ceil(total / normalized_page_size) if total else 0,
    )
