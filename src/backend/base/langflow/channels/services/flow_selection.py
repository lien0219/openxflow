"""Resolve and maintain durable per-member active workflow selections."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.services.commands import resolve_workflow_command
from langflow.channels.services.configuration_audit import (
    channel_resource_snapshot,
    record_channel_configuration_audit,
)
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
from langflow.services.database.models.flow.model import Flow


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
    before = channel_resource_snapshot(selection)
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
    await record_channel_configuration_audit(
        session,
        connection_id=connection.id,
        actor_user_id=user_id,
        action="select",
        resource_type="flow_selection",
        resource_id=selection.id,
        before=before,
        after={
            **channel_resource_snapshot(selection),
            "channel_identity_id": identity.id,
            "command": command.command,
            "flow_id": command.flow_id,
            "operator_type": "user",
        },
    )
    return selection, command


async def clear_active_workflow_selection(
    session: AsyncSession,
    *,
    connection_id: UUID,
    conversation_binding_id: UUID,
    channel_identity_id: UUID,
    conversation_scope_id: str,
    actor_user_id: UUID | None = None,
    action: str = "clear",
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
    before = channel_resource_snapshot(selection)
    await session.delete(selection)
    await session.flush()
    await record_channel_configuration_audit(
        session,
        connection_id=connection_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type="flow_selection",
        resource_id=selection.id,
        before=before,
        after={"operator_type": "user" if actor_user_id is not None else "system", "removed": True},
    )
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
        before = channel_resource_snapshot(selection)
        await session.delete(selection)
        await session.flush()
        await record_channel_configuration_audit(
            session,
            connection_id=connection.id,
            actor_user_id=None,
            action=invalid_reason,
            resource_type="flow_selection",
            resource_id=selection.id,
            before=before,
            after={"operator_type": "system", "removed": True},
        )
        return ActiveWorkflowResolution(invalid_reason=invalid_reason)

    if touch:
        selection.last_used_at = now
        selection.updated_at = now
        session.add(selection)
        await session.flush()
    return ActiveWorkflowResolution(selection=selection, command=command)


def _selection_join_statement():
    return (
        select(
            ChannelActiveWorkflowSelection,
            ChannelIdentity,
            ChannelConversationBinding,
            ChannelWorkflowCommand,
            Flow,
        )
        .join(ChannelIdentity, ChannelIdentity.id == ChannelActiveWorkflowSelection.channel_identity_id)
        .join(
            ChannelConversationBinding,
            ChannelConversationBinding.id == ChannelActiveWorkflowSelection.conversation_binding_id,
        )
        .join(ChannelWorkflowCommand, ChannelWorkflowCommand.id == ChannelActiveWorkflowSelection.workflow_command_id)
        .join(Flow, Flow.id == ChannelWorkflowCommand.flow_id)
    )


def _selection_search_filter(query: str | None):
    normalized = (query or "").strip()
    if not normalized:
        return None
    pattern = f"%{normalized}%"
    return sa.or_(
        ChannelIdentity.display_name.ilike(pattern),
        ChannelIdentity.external_user_id.ilike(pattern),
        ChannelConversationBinding.display_name.ilike(pattern),
        ChannelConversationBinding.external_conversation_id.ilike(pattern),
        ChannelWorkflowCommand.command.ilike(pattern),
        Flow.name.ilike(pattern),
        Flow.endpoint_name.ilike(pattern),
    )


async def list_active_workflow_selections(
    session: AsyncSession,
    connection_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    conversation_binding_id: UUID | None = None,
    channel_identity_id: UUID | None = None,
    workflow_command_id: UUID | None = None,
    query: str | None = None,
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
    search_filter = _selection_search_filter(query)
    if search_filter is not None:
        filters.append(search_filter)

    joined = _selection_join_statement().where(*filters)
    count_statement = select(func.count()).select_from(joined.subquery())
    total = int((await session.exec(count_statement)).one())
    rows = (
        await session.exec(
            joined.order_by(ChannelActiveWorkflowSelection.updated_at.desc(), ChannelActiveWorkflowSelection.id)
            .offset((normalized_page - 1) * normalized_page_size)
            .limit(normalized_page_size)
        )
    ).all()
    items = []
    for selection, identity, binding, command, flow in rows:
        items.append(
            ChannelActiveWorkflowSelectionRead(
                **selection.model_dump(),
                identity_display_name=identity.display_name,
                external_user_id=identity.external_user_id,
                conversation_display_name=binding.display_name,
                external_conversation_id=binding.external_conversation_id,
                conversation_type=binding.conversation_type,
                command=command.command,
                flow_id=command.flow_id,
                flow_name=flow.name,
                flow_endpoint_name=flow.endpoint_name,
                execution_identity_type="bound_user" if command.owner_user_id is not None else "service",
            )
        )
    return ChannelActiveWorkflowSelectionPage(
        items=items,
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
    actor_user_id: UUID | None = None,
    action: str = "admin_revoke",
) -> bool:
    selection = await session.get(ChannelActiveWorkflowSelection, selection_id)
    if selection is None or selection.connection_id != connection_id:
        return False
    before = channel_resource_snapshot(selection)
    await session.delete(selection)
    await session.flush()
    await record_channel_configuration_audit(
        session,
        connection_id=connection_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type="flow_selection",
        resource_id=selection.id,
        before=before,
        after={"operator_type": "admin" if actor_user_id is not None else "system", "removed": True},
    )
    return True


async def cleanup_expired_workflow_selections_batch(
    session: AsyncSession,
    *,
    connection_id: UUID | None = None,
    batch_size: int = 500,
    actor_user_id: UUID | None = None,
    action: str = "expire",
) -> int:
    normalized_batch_size = min(1000, max(1, batch_size))
    filters = [
        ChannelActiveWorkflowSelection.expires_at.is_not(None),
        ChannelActiveWorkflowSelection.expires_at <= _utc_now(),
    ]
    if connection_id is not None:
        filters.append(ChannelActiveWorkflowSelection.connection_id == connection_id)
    statement = (
        select(ChannelActiveWorkflowSelection)
        .where(*filters)
        .order_by(ChannelActiveWorkflowSelection.expires_at, ChannelActiveWorkflowSelection.id)
        .limit(normalized_batch_size)
    )
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    rows = (await session.exec(statement)).all()
    if not rows:
        return 0

    grouped: dict[UUID, list[ChannelActiveWorkflowSelection]] = defaultdict(list)
    for row in rows:
        grouped[row.connection_id].append(row)
        await session.delete(row)
    await session.flush()
    for current_connection_id, connection_rows in grouped.items():
        await record_channel_configuration_audit(
            session,
            connection_id=current_connection_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type="flow_selection_cleanup",
            resource_id=None,
            before={
                "selection_ids": [str(row.id) for row in connection_rows],
                "removed_count": len(connection_rows),
            },
            after={
                "operator_type": "admin" if actor_user_id is not None else "system",
                "removed_count": len(connection_rows),
            },
        )
    return len(rows)


async def cleanup_expired_workflow_selections(
    session: AsyncSession,
    *,
    connection_id: UUID,
    actor_user_id: UUID | None = None,
    action: str = "cleanup_expired",
    batch_size: int = 500,
) -> int:
    removed = 0
    while True:
        batch_removed = await cleanup_expired_workflow_selections_batch(
            session,
            connection_id=connection_id,
            batch_size=batch_size,
            actor_user_id=actor_user_id,
            action=action,
        )
        removed += batch_removed
        if batch_removed < batch_size:
            return removed
