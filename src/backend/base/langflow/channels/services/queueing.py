"""Resolve durable FIFO queue scopes for normalized channel events."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.domain.models import ChannelEvent
from langflow.channels.services.access_control import effective_context_mode
from langflow.channels.services.conversation_scope import conversation_scope_id
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelContextMode,
    ChannelConversationBinding,
)


@dataclass(frozen=True)
class ChannelQueueDescriptor:
    queue_key: str
    external_conversation_id: str
    external_user_id: str
    conversation_type: str
    conversation_scope_id: str
    context_mode: str
    serialized_by_conversation: bool


def _bounded_queue_key(connection_id: str, scope_type: str, components: tuple[str, ...]) -> str:
    canonical = "\x1f".join(components)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"channel:{connection_id}:{scope_type}:{digest}"


async def resolve_channel_queue_descriptor(
    session: AsyncSession,
    connection: ChannelConnection,
    event: ChannelEvent,
) -> ChannelQueueDescriptor:
    statement = select(ChannelConversationBinding).where(
        ChannelConversationBinding.connection_id == connection.id,
        ChannelConversationBinding.external_conversation_id == event.conversation.external_conversation_id,
    )
    binding = (await session.exec(statement)).first()
    context_mode = effective_context_mode(connection, binding)
    conversation_type = event.conversation.conversation_type
    scope_id = conversation_scope_id(event)
    serialized_by_conversation = conversation_type != "private" and context_mode in {
        ChannelContextMode.SHARED.value,
        ChannelContextMode.HYBRID.value,
    }
    components = (
        str(connection.id),
        event.conversation.external_conversation_id,
        scope_id,
    )
    if serialized_by_conversation:
        scope_type = "conversation"
    else:
        scope_type = "member"
        components = (*components, event.user.external_user_id)
    return ChannelQueueDescriptor(
        queue_key=_bounded_queue_key(str(connection.id), scope_type, components),
        external_conversation_id=event.conversation.external_conversation_id,
        external_user_id=event.user.external_user_id,
        conversation_type=conversation_type,
        conversation_scope_id=scope_id,
        context_mode=context_mode,
        serialized_by_conversation=serialized_by_conversation,
    )
