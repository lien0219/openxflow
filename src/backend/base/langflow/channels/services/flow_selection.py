"""Resolve and maintain durable per-member active workflow selections."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.services.commands import resolve_workflow_command
from langflow.services.database.models.channel.command_model import ChannelWorkflowCommand
from langflow.services.database.models.channel.flow_selection_model import (
    ChannelActiveWorkflowSelection,
    ChannelActiveWorkflowSelectionPage,
    ChannelActiveWorkflowSelectionRead,
)
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConversationBinding,
    ChannelIdentity,
)


class FlowSelectionDisabledError(PermissionError):
    """Raised when the connection does not allow persistent user workflow selection."""


class FlowSelectionCommandUnavailableError(LookupError):
    """Raised when the requested command is not available in the current scope."""


class FlowSelectionNotAllowedError(PermissionError):
    """Raised when a command is intentionally single-use only."""


@dataclass(frozen=True, slots=True)
class ActiveWorkflowResolution:
    selection: ChannelActiveWorkflowSelection | None = None
    command: ChannelWorkflowCommand | None = None
    invalid_reason: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _selection_statement(
    *,
    connection_id: UUID,
    conversation_binding_id: UUID,
    channel_identity_id: UUID,
    conversation_scope_id: str,
):
    return select(ChannelActiveWorkflowSelection).where(
        ChannelActiveWorkflowSelection.connection_id == connection_id,
        ChannelActiveWorkflowSelection.conversation_binding_id == conversation_binding_id,
        ChannelActiveWorkflowSelection.channel_identity_id == channel_identity_id,
        ChannelActiveWorkflowSelection.conversation_scope_id == conversation_scope_id,
    )


async def get_active_workflow_selection(
    session: AsyncSession,
    *,
    connection_id: UUID,
    conversation_binding_id: UUID,
    channel_identity_id: UUID,
    conversation_scope_id: str,
) -> ChannelActiveWorkflowSelection | None:
    return (
        await session.exec(
            _selection_statement(
                connection_id=connection_id,
                conversation_binding_id=conversation_binding_id,
                channel_identity_id=channel_identity_id,
                conversation_scope_id=conversation_scope_id,
            )
        )
    ).first()


async def set_active_workflow_selection(
    session: AsyncSession,
    *,
    connection: ChannelConnection,
    binding: ChannelConversationBinding,
    identity: ChannelIdentity,
    conversation_scope_id: str,
    user_id: UUID | None,
    command_name: str,
) -> tuple[ChannelActiveWorkflowSelection, ChannelWorkflowCommand]:
    if not connection.user_flow_selection_enabled:
        raise FlowSelectionDisabledError

    command = await resolve_workflow_command(
        session,
        connection_id=connection.id,
        conversation_binding_id=binding.id,
        user_id=user_id,
        command_name=command_name,
    )
    if command is None:
        raise FlowSelectionCommandUnavailableError
    if not command.allow_persistent_selection:
        raise FlowSelectionNotAllowedError

    now = _utc_now()
    expires_at = None
    if connection.flow_selection_ttl_hours > 0:
        expires_at = now + timedelta(hours=connection.flow_selection_ttl_hours)

    selection = await get_active_workflow_selection(
        session,
        connection_id=connection.id,
        conversation_binding_id=binding.id,
        channel_identity_id=identity.id,
        conversation_scope_id=conversation_scope_id,
    )
    if selection is None:
        selection = ChannelActiveWorkflowSelection(
            connection_id=connection.id,
            conversation_binding_id=binding.id,
            channel_identity_id=identity.id,
            conversation_scope_id=conversation_scope_id,
            workflow_command_id=command.id,
            selected_at=now,
            expires_at=expires_at,
            updated_at=now,
        )
    else:
        selection.workflow_command_id = command.id
        selection.selected_at = now
        selection.last_used_at = None
        selection.expires_at = expires_at
        selection.updated_at = now
    session.add(selection)
    await session.flush()
    await session.refresh(selection)
    return selection, command


async def clear_active_workflow_selection(
    session: AsyncSession,
    *,
    connection_id: UUID,
    conversation_binding_id: UUID,
    channel_identity_id: UUID,
    conversation_scope_id: str,
) -> bool:
    selection = await get_active_workflow_selection(
        session,
        connection_id=connection_id,
        conversation_binding_id=conversation_binding_id,
        channel_identity_id=channel_identity_id,
        conversation_scope_id=conversation_scope_id,
    )
    if selection is None:
        return False
    await session.delete(selection)
    await session.flush()
    return True


async def resolve_active_workflow_selection(
    session: AsyncSession,
    *,
    connection: ChannelConnection,
    binding: ChannelConversationBinding,
    identity: ChannelIdentity,
    conversation_scope_id: str,
    user_id: UUID | None,
    touch: bool = True,
) -> ActiveWorkflowResolution:
    selection = await get_active_workflow_selection(
        session,
        connection_id=connection.id,
        conversation_binding_id=binding.id,
        channel_identity_id=identity.id,
        conversation_scope_id=conversation_scope_id,
    )
    if selection is None:
        return ActiveWorkflowResolution()

    invalid_reason = None
    now = _utc_now()
    if not connection.user_flow_selection_enabled:
        invalid_reason = "selection_disabled"
    elif selection.expires_at is not None and _as_utc(selection.expires_at) <= now:
        invalid_reason = "selection_expired"

    command = None if invalid_reason else await session.get(ChannelWorkflowCommand, selection.workflow_command_id)
    if command is None and invalid_reason is None:
        invalid_reason = "command_deleted"
    elif command is not None and (not command.enabled or not command.allow_persistent_selection):
        invalid_reason = "command_disabled"
    elif command is not None:
        effective_command = await resolve_workflow_command(
            session,
            connection_id=connection.id,
            conversation_binding_id=binding.id,
            user_id=user_id,
            command_name=command.normalized_command,
        )
        if effective_command is None or effective_command.id != command.id:
            invalid_reason = "permission_or_scope_changed"

    if invalid_reason is not None:
        await session.delete(selection)
        await session.flush()
        return ActiveWorkflowResolution(invalid_reason=invalid_reason)

    if touch:
        selection.last_used_at = now
        selection.updated_at = now
        session.add(selection)
        await session.flush()
    return ActiveWorkflowResolution(selection=selection, command=command)


async def list_active_workflow_selections(
    session: AsyncSession,
    connection_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    conversation_binding_id: UUID | None = None,
    channel_identity_id: UUID | None = None,
    workflow_command_id: UUID | None = None,
) -> ChannelActiveWorkflowSelectionPage:
    normalized_page = max(1, page)
    normalized_page_size = min(100, max(1, page_size))
    filters = [ChannelActiveWorkflowSelection.connection_id == connection_id]
    if conversation_binding_id is not None:
        filters.append(ChannelActiveWorkflowSelection.conversation_binding_id == conversation_binding_id)
    if channel_identity_id is not None:
        filters.append(ChannelActiveWorkflowSelection.channel_identity_id == channel_identity_id)
    if workflow_command_id is not None:
        filters.append(ChannelActiveWorkflowSelection.workflow_command_id == workflow_command_id)

    total = int(
        (await session.exec(select(func.count()).select_from(ChannelActiveWorkflowSelection).where(*filters))).one()
    )
    rows = (
        await session.exec(
            select(ChannelActiveWorkflowSelection)
            .where(*filters)
            .order_by(ChannelActiveWorkflowSelection.updated_at.desc(), ChannelActiveWorkflowSelection.id)
            .offset((normalized_page - 1) * normalized_page_size)
            .limit(normalized_page_size)
        )
    ).all()
    return ChannelActiveWorkflowSelectionPage(
        items=[ChannelActiveWorkflowSelectionRead.model_validate(row, from_attributes=True) for row in rows],
        page=normalized_page,
        page_size=normalized_page_size,
        total=total,
        total_pages=math.ceil(total / normalized_page_size) if total else 0,
    )


async def delete_active_workflow_selection(
    session: AsyncSession,
    *,
    connection_id: UUID,
    selection_id: UUID,
) -> bool:
    selection = await session.get(ChannelActiveWorkflowSelection, selection_id)
    if selection is None or selection.connection_id != connection_id:
        return False
    await session.delete(selection)
    await session.flush()
    return True


async def cleanup_expired_workflow_selections(
    session: AsyncSession,
    *,
    connection_id: UUID,
) -> int:
    now = _utc_now()
    rows = (
        await session.exec(
            select(ChannelActiveWorkflowSelection).where(
                ChannelActiveWorkflowSelection.connection_id == connection_id,
                ChannelActiveWorkflowSelection.expires_at.is_not(None),
                ChannelActiveWorkflowSelection.expires_at <= now,
            )
        )
    ).all()
    for row in rows:
        await session.delete(row)
    if rows:
        await session.flush()
    return len(rows)
