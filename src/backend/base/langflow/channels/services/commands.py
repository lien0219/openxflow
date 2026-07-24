"""Custom workflow command routing for provider-neutral channel conversations."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.services.database.models.channel.command_model import (
    ChannelCommandScope,
    ChannelWorkflowCommand,
    ChannelWorkflowCommandCreate,
    ChannelWorkflowCommandPage,
    ChannelWorkflowCommandRead,
    ChannelWorkflowCommandUpdate,
)
from langflow.services.database.models.channel.model import ChannelConnection, ChannelConversationBinding
from langflow.services.database.models.user.model import User

_COMMAND_PATTERN = re.compile(r"^/[A-Za-z0-9_\-\u4e00-\u9fff]{1,32}$")
_RESERVED_COMMANDS = {
    "/start",
    "/help",
    "/bind",
    "/commands",
    "/flow",
    "/run",
    "/whoami",
    "/knowledge",
    "/use-kb",
    "/files",
}


def normalize_command(value: str) -> str:
    normalized = value.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    normalized = normalized.lower()
    if not _COMMAND_PATTERN.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Command must contain 1-32 Chinese, English, numeric, dash, or underscore characters",
        )
    if normalized in _RESERVED_COMMANDS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Command {normalized} is reserved by OpenXFlow",
        )
    return normalized


def normalize_aliases(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        alias = normalize_command(value)
        if alias not in normalized:
            normalized.append(alias)
    return normalized[:5]


def build_scope_key(
    scope_type: str,
    *,
    conversation_binding_id: UUID | None,
    owner_user_id: UUID | None,
) -> str:
    if scope_type == ChannelCommandScope.CONNECTION_SHARED.value:
        return "connection"
    if scope_type == ChannelCommandScope.CONVERSATION_SHARED.value:
        if conversation_binding_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="conversation_binding_id is required for conversation shared commands",
            )
        return f"conversation:{conversation_binding_id}"
    if scope_type == ChannelCommandScope.IDENTITY_CONNECTION.value:
        if owner_user_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Command owner is required")
        return f"identity:{owner_user_id}"
    if scope_type == ChannelCommandScope.IDENTITY_CONVERSATION.value:
        if owner_user_id is None or conversation_binding_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Command owner and conversation are required",
            )
        return f"identity-conversation:{owner_user_id}:{conversation_binding_id}"
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported command scope")


async def _validate_conversation(
    session: AsyncSession,
    connection_id: UUID,
    conversation_binding_id: UUID | None,
) -> ChannelConversationBinding | None:
    if conversation_binding_id is None:
        return None
    statement = select(ChannelConversationBinding).where(
        ChannelConversationBinding.id == conversation_binding_id,
        ChannelConversationBinding.connection_id == connection_id,
    )
    conversation = (await session.exec(statement)).first()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel conversation not found")
    return conversation


def _can_manage_shared(connection: ChannelConnection, user: User) -> bool:
    return user.is_superuser or connection.user_id == user.id


def _assert_scope_permission(connection: ChannelConnection, user: User, scope_type: str) -> UUID | None:
    if scope_type in {
        ChannelCommandScope.CONNECTION_SHARED.value,
        ChannelCommandScope.CONVERSATION_SHARED.value,
    }:
        if not _can_manage_shared(connection, user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the channel administrator can manage shared commands",
            )
        return None
    if not connection.personal_commands_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Personal commands are disabled for this channel connection",
        )
    return user.id


async def _assert_command_names_available(
    session: AsyncSession,
    *,
    connection_id: UUID,
    scope_key: str,
    names: set[str],
    exclude_command_id: UUID | None = None,
) -> None:
    statement = select(ChannelWorkflowCommand).where(
        ChannelWorkflowCommand.connection_id == connection_id,
        ChannelWorkflowCommand.scope_key == scope_key,
    )
    if exclude_command_id is not None:
        statement = statement.where(ChannelWorkflowCommand.id != exclude_command_id)
    rows = (await session.exec(statement)).all()
    for row in rows:
        existing_names = {row.normalized_command, *row.aliases}
        conflict = names.intersection(existing_names)
        if conflict:
            command = sorted(conflict)[0]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Command or alias {command} already exists in this scope",
            )


async def create_workflow_command(
    session: AsyncSession,
    connection: ChannelConnection,
    user: User,
    payload: ChannelWorkflowCommandCreate,
) -> ChannelWorkflowCommandRead:
    owner_user_id = _assert_scope_permission(connection, user, payload.scope_type)
    await _validate_conversation(session, connection.id, payload.conversation_binding_id)
    normalized_command = normalize_command(payload.command)
    aliases = normalize_aliases(payload.aliases)
    if normalized_command in aliases:
        aliases.remove(normalized_command)
    scope_key = build_scope_key(
        payload.scope_type,
        conversation_binding_id=payload.conversation_binding_id,
        owner_user_id=owner_user_id,
    )
    await _assert_command_names_available(
        session,
        connection_id=connection.id,
        scope_key=scope_key,
        names={normalized_command, *aliases},
    )
    command = ChannelWorkflowCommand(
        connection_id=connection.id,
        conversation_binding_id=payload.conversation_binding_id,
        owner_user_id=owner_user_id,
        created_by=user.id,
        flow_id=payload.flow_id,
        command=normalized_command,
        normalized_command=normalized_command,
        aliases=aliases,
        description=payload.description,
        scope_type=payload.scope_type,
        scope_key=scope_key,
        prompt_template=payload.prompt_template,
        input_required=payload.input_required,
        allow_attachments=payload.allow_attachments,
        require_mention=payload.require_mention,
        enabled=payload.enabled,
        settings_data=payload.settings_data,
    )
    session.add(command)
    await session.flush()
    await session.refresh(command)
    return ChannelWorkflowCommandRead.model_validate(command, from_attributes=True)


async def list_workflow_commands(
    session: AsyncSession,
    connection: ChannelConnection,
    user: User,
    *,
    page: int = 1,
    page_size: int = 20,
    query: str | None = None,
    scope_type: str | None = None,
    enabled: bool | None = None,
) -> ChannelWorkflowCommandPage:
    normalized_page = max(1, page)
    normalized_page_size = min(100, max(1, page_size))
    filters: list = [ChannelWorkflowCommand.connection_id == connection.id]
    if not _can_manage_shared(connection, user):
        filters.append(
            sa.or_(
                ChannelWorkflowCommand.owner_user_id == user.id,
                ChannelWorkflowCommand.scope_type.in_(
                    [
                        ChannelCommandScope.CONNECTION_SHARED.value,
                        ChannelCommandScope.CONVERSATION_SHARED.value,
                    ]
                ),
            )
        )
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        filters.append(
            sa.or_(
                ChannelWorkflowCommand.command.ilike(pattern),
                ChannelWorkflowCommand.description.ilike(pattern),
            )
        )
    if scope_type:
        filters.append(ChannelWorkflowCommand.scope_type == scope_type)
    if enabled is not None:
        filters.append(ChannelWorkflowCommand.enabled == enabled)

    total_statement = select(func.count()).select_from(ChannelWorkflowCommand).where(*filters)
    total = int((await session.exec(total_statement)).one())
    statement = (
        select(ChannelWorkflowCommand)
        .where(*filters)
        .order_by(ChannelWorkflowCommand.updated_at.desc(), ChannelWorkflowCommand.id)
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    )
    rows = (await session.exec(statement)).all()
    return ChannelWorkflowCommandPage(
        items=[ChannelWorkflowCommandRead.model_validate(row, from_attributes=True) for row in rows],
        page=normalized_page,
        page_size=normalized_page_size,
        total=total,
        total_pages=math.ceil(total / normalized_page_size) if total else 0,
    )


async def get_workflow_command(
    session: AsyncSession,
    connection_id: UUID,
    command_id: UUID,
) -> ChannelWorkflowCommand | None:
    statement = select(ChannelWorkflowCommand).where(
        ChannelWorkflowCommand.id == command_id,
        ChannelWorkflowCommand.connection_id == connection_id,
    )
    return (await session.exec(statement)).first()


def _assert_command_edit_permission(connection: ChannelConnection, user: User, command: ChannelWorkflowCommand) -> None:
    if command.owner_user_id is not None:
        if command.owner_user_id != user.id and not user.is_superuser:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit another user's command")
        return
    if not _can_manage_shared(connection, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit shared command")


async def update_workflow_command(
    session: AsyncSession,
    connection: ChannelConnection,
    user: User,
    command: ChannelWorkflowCommand,
    payload: ChannelWorkflowCommandUpdate,
) -> ChannelWorkflowCommandRead:
    _assert_command_edit_permission(connection, user, command)
    changes = payload.model_dump(exclude_unset=True)
    normalized_command = normalize_command(changes.get("command", command.command))
    aliases = normalize_aliases(changes.get("aliases", command.aliases))
    if normalized_command in aliases:
        aliases.remove(normalized_command)
    await _assert_command_names_available(
        session,
        connection_id=connection.id,
        scope_key=command.scope_key,
        names={normalized_command, *aliases},
        exclude_command_id=command.id,
    )
    for key, value in changes.items():
        if key not in {"command", "aliases"}:
            setattr(command, key, value)
    command.command = normalized_command
    command.normalized_command = normalized_command
    command.aliases = aliases
    command.updated_at = datetime.now(timezone.utc)
    session.add(command)
    await session.flush()
    await session.refresh(command)
    return ChannelWorkflowCommandRead.model_validate(command, from_attributes=True)


async def delete_workflow_command(
    session: AsyncSession,
    connection: ChannelConnection,
    user: User,
    command: ChannelWorkflowCommand,
) -> None:
    _assert_command_edit_permission(connection, user, command)
    await session.delete(command)
    await session.flush()


def _scope_priority(
    command: ChannelWorkflowCommand,
    *,
    user_id: UUID,
    conversation_binding_id: UUID,
) -> int | None:
    if (
        command.scope_type == ChannelCommandScope.IDENTITY_CONVERSATION.value
        and command.owner_user_id == user_id
        and command.conversation_binding_id == conversation_binding_id
    ):
        return 0
    if (
        command.scope_type == ChannelCommandScope.CONVERSATION_SHARED.value
        and command.conversation_binding_id == conversation_binding_id
    ):
        return 1
    if command.scope_type == ChannelCommandScope.IDENTITY_CONNECTION.value and command.owner_user_id == user_id:
        return 2
    if command.scope_type == ChannelCommandScope.CONNECTION_SHARED.value:
        return 3
    return None


async def resolve_workflow_command(
    session: AsyncSession,
    *,
    connection_id: UUID,
    conversation_binding_id: UUID,
    user_id: UUID,
    command_name: str,
) -> ChannelWorkflowCommand | None:
    normalized = command_name.lower()
    statement = select(ChannelWorkflowCommand).where(
        ChannelWorkflowCommand.connection_id == connection_id,
        ChannelWorkflowCommand.enabled.is_(True),
        sa.or_(
            ChannelWorkflowCommand.conversation_binding_id.is_(None),
            ChannelWorkflowCommand.conversation_binding_id == conversation_binding_id,
        ),
        sa.or_(
            ChannelWorkflowCommand.owner_user_id.is_(None),
            ChannelWorkflowCommand.owner_user_id == user_id,
        ),
    )
    rows = (await session.exec(statement)).all()
    matches: list[tuple[int, ChannelWorkflowCommand]] = []
    for row in rows:
        if normalized != row.normalized_command and normalized not in row.aliases:
            continue
        priority = _scope_priority(
            row,
            user_id=user_id,
            conversation_binding_id=conversation_binding_id,
        )
        if priority is not None:
            matches.append((priority, row))
    if not matches:
        return None
    matches.sort(key=lambda item: (item[0], str(item[1].id)))
    return matches[0][1]


async def list_available_workflow_commands(
    session: AsyncSession,
    *,
    connection_id: UUID,
    conversation_binding_id: UUID,
    user_id: UUID,
) -> list[ChannelWorkflowCommand]:
    statement = select(ChannelWorkflowCommand).where(
        ChannelWorkflowCommand.connection_id == connection_id,
        ChannelWorkflowCommand.enabled.is_(True),
        sa.or_(
            ChannelWorkflowCommand.conversation_binding_id.is_(None),
            ChannelWorkflowCommand.conversation_binding_id == conversation_binding_id,
        ),
        sa.or_(
            ChannelWorkflowCommand.owner_user_id.is_(None),
            ChannelWorkflowCommand.owner_user_id == user_id,
        ),
    )
    rows = (await session.exec(statement)).all()
    best_by_name: dict[str, tuple[int, ChannelWorkflowCommand]] = {}
    for row in rows:
        priority = _scope_priority(
            row,
            user_id=user_id,
            conversation_binding_id=conversation_binding_id,
        )
        if priority is None:
            continue
        current = best_by_name.get(row.normalized_command)
        if current is None or priority < current[0]:
            best_by_name[row.normalized_command] = (priority, row)
    return [item[1] for item in sorted(best_by_name.values(), key=lambda value: value[1].normalized_command)]


def render_command_input(
    command: ChannelWorkflowCommand,
    *,
    input_value: str,
    sender_name: str | None,
    conversation_name: str | None,
    conversation_type: str,
) -> str:
    template = command.prompt_template
    if not template:
        return input_value
    replacements = {
        "{{input}}": input_value,
        "{{sender_name}}": sender_name or "",
        "{{conversation_name}}": conversation_name or "",
        "{{conversation_type}}": conversation_type,
    }
    rendered = template
    for token, value in replacements.items():
        rendered = rendered.replace(token, value)
    return rendered


async def mark_workflow_command_used(session: AsyncSession, command: ChannelWorkflowCommand) -> None:
    command.last_used_at = datetime.now(timezone.utc)
    command.updated_at = datetime.now(timezone.utc)
    session.add(command)
    await session.flush()
