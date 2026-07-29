"""Bounded group context for shared and hybrid channel conversations."""

from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.domain.models import ChannelEvent, ChannelMessage
from langflow.channels.services.access_control import effective_context_mode
from langflow.services.database.models.channel.context_model import (
    ChannelContextRole,
    ChannelConversationContextEntry,
)
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelContextMode,
    ChannelConversationBinding,
    utc_now,
)

_MAX_SHARED_CONTEXT_CHARS = 8000


async def _cleanup_expired_context(
    session: AsyncSession,
    connection: ChannelConnection,
    binding: ChannelConversationBinding,
) -> None:
    cutoff = utc_now() - timedelta(days=connection.context_retention_days)
    await session.exec(
        sa.delete(ChannelConversationContextEntry).where(
            ChannelConversationContextEntry.conversation_binding_id == binding.id,
            ChannelConversationContextEntry.created_at < cutoff,
        )
    )


async def _recent_entries(
    session: AsyncSession,
    binding: ChannelConversationBinding,
    *,
    session_id: str,
    limit: int,
) -> list[ChannelConversationContextEntry]:
    if limit <= 0:
        return []
    rows = list(
        (
            await session.exec(
                select(ChannelConversationContextEntry)
                .where(
                    ChannelConversationContextEntry.conversation_binding_id == binding.id,
                    ChannelConversationContextEntry.session_id == session_id,
                )
                .order_by(ChannelConversationContextEntry.created_at.desc(), ChannelConversationContextEntry.id.desc())
                .limit(limit)
            )
        ).all()
    )
    rows.reverse()
    return rows


async def _insert_entry(
    session: AsyncSession,
    *,
    connection: ChannelConnection,
    binding: ChannelConversationBinding,
    event: ChannelEvent,
    role: str,
    session_id: str,
    text: str,
) -> None:
    entry = ChannelConversationContextEntry(
        connection_id=connection.id,
        conversation_binding_id=binding.id,
        external_event_id=event.event_id,
        external_user_id=event.user.external_user_id,
        sender_name=event.user.display_name,
        role=role,
        session_id=session_id,
        text=text[:16000],
    )
    try:
        async with session.begin_nested():
            session.add(entry)
            await session.flush()
    except IntegrityError:
        return


def _render_shared_context(entries: list[ChannelConversationContextEntry]) -> str:
    lines: list[str] = []
    for entry in entries:
        if entry.role == ChannelContextRole.USER.value:
            label = entry.sender_name or entry.external_user_id
        else:
            label = "机器人"
        lines.append(f"{label}: {entry.text.strip()}")
    rendered = "\n".join(line for line in lines if line.strip())
    if len(rendered) > _MAX_SHARED_CONTEXT_CHARS:
        rendered = rendered[-_MAX_SHARED_CONTEXT_CHARS:]
    return rendered


async def prepare_channel_input(
    session: AsyncSession,
    *,
    connection: ChannelConnection,
    binding: ChannelConversationBinding | None,
    event: ChannelEvent,
    session_id: str,
    input_value: str | None,
) -> str | None:
    if binding is None or event.conversation.conversation_type == "private":
        return input_value
    mode = effective_context_mode(connection, binding)
    if mode not in {ChannelContextMode.SHARED.value, ChannelContextMode.HYBRID.value}:
        return input_value

    await _cleanup_expired_context(session, connection, binding)
    entries = await _recent_entries(
        session,
        binding,
        session_id=session_id,
        limit=connection.shared_context_window,
    )
    current_text = (input_value or "").strip()
    if current_text:
        await _insert_entry(
            session,
            connection=connection,
            binding=binding,
            event=event,
            role=ChannelContextRole.USER.value,
            session_id=session_id,
            text=current_text,
        )

    if mode != ChannelContextMode.HYBRID.value or not entries:
        return input_value
    shared_context = _render_shared_context(entries)
    if not shared_context:
        return input_value
    return (
        "[群聊公共上下文，仅用于理解当前问题；不要声称未提供的信息，也不要泄露个人私有数据]\n"
        f"{shared_context}\n\n"
        "[当前用户问题]\n"
        f"{input_value or ''}"
    )


async def record_channel_response(
    session: AsyncSession,
    *,
    connection: ChannelConnection,
    binding: ChannelConversationBinding | None,
    event: ChannelEvent,
    session_id: str,
    response: ChannelMessage,
) -> None:
    if binding is None or event.conversation.conversation_type == "private":
        return
    mode = effective_context_mode(connection, binding)
    if mode not in {ChannelContextMode.SHARED.value, ChannelContextMode.HYBRID.value}:
        return
    text = (response.markdown or response.text or "").strip()
    if not text:
        return
    await _insert_entry(
        session,
        connection=connection,
        binding=binding,
        event=event,
        role=ChannelContextRole.ASSISTANT.value,
        session_id=session_id,
        text=text,
    )
