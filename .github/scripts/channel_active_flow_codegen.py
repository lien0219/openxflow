from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path.cwd()
BRANCH = "automation/channel-active-flow-selection"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:120]!r}")
    write(path, content.replace(old, new, 1))


def append_once(path: str, marker: str, content: str) -> None:
    current = read(path)
    if marker in current:
        return
    write(path, current.rstrip() + "\n\n" + content.rstrip() + "\n")


def run_command(command: str) -> None:
    print(f"+ {command}", flush=True)
    subprocess.run(command, cwd=ROOT, shell=True, check=True)


FLOW_SELECTION_MODEL = '''"""Durable per-member active workflow selections for communication channels."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint, func
from sqlmodel import Field, SQLModel

from langflow.services.database.models.channel.model import utc_now


class ChannelActiveWorkflowSelection(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "channel_active_workflow_selection"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "conversation_binding_id",
            "channel_identity_id",
            "conversation_scope_id",
            name="uq_channel_active_flow_selection_scope",
        ),
        sa.Index(
            "ix_channel_active_flow_selection_lookup",
            "connection_id",
            "conversation_binding_id",
            "channel_identity_id",
            "conversation_scope_id",
        ),
        sa.Index("ix_channel_active_flow_selection_connection_updated", "connection_id", "updated_at"),
        sa.Index("ix_channel_active_flow_selection_expires", "expires_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    connection_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("channel_connection.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    conversation_binding_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("channel_conversation_binding.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    channel_identity_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("channel_identity.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    conversation_scope_id: str = Field(default="", max_length=255)
    workflow_command_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("channel_workflow_command.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    selected_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    last_used_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ChannelActiveWorkflowSelectionRead(SQLModel):
    id: UUID
    connection_id: UUID
    conversation_binding_id: UUID
    channel_identity_id: UUID
    conversation_scope_id: str
    workflow_command_id: UUID
    selected_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ChannelActiveWorkflowSelectionPage(SQLModel):
    items: list[ChannelActiveWorkflowSelectionRead]
    page: int
    page_size: int
    total: int
    total_pages: int
'''


FLOW_SELECTION_SERVICE = '''"""Resolve and maintain durable per-member active workflow selections."""

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
'''


MIGRATION = '''"""add persistent channel workflow selections

Revision ID: a1f4c7e9d2b6
Revises: b5d8e1f3a6c9
Create Date: 2026-07-29 20:00:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from langflow.utils import migration

revision: str = "a1f4c7e9d2b6"  # pragma: allowlist secret
down_revision: str | None = "b5d8e1f3a6c9"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str, conn) -> set[str]:
    if not migration.table_exists(table_name, conn):
        return set()
    return {column["name"] for column in sa.inspect(conn).get_columns(table_name)}


def _indexes(table_name: str, conn) -> set[str]:
    if not migration.table_exists(table_name, conn):
        return set()
    return {index["name"] for index in sa.inspect(conn).get_indexes(table_name)}


def _recreate_mode(conn) -> str:
    return "always" if conn.dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    conn = op.get_bind()

    connection_columns = _columns("channel_connection", conn)
    if connection_columns:
        with op.batch_alter_table("channel_connection", recreate=_recreate_mode(conn)) as batch_op:
            if "user_flow_selection_enabled" not in connection_columns:
                batch_op.add_column(
                    sa.Column("user_flow_selection_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
                )
            if "flow_selection_ttl_hours" not in connection_columns:
                batch_op.add_column(
                    sa.Column("flow_selection_ttl_hours", sa.Integer(), nullable=False, server_default="24")
                )

    command_columns = _columns("channel_workflow_command", conn)
    if command_columns and "allow_persistent_selection" not in command_columns:
        with op.batch_alter_table("channel_workflow_command", recreate=_recreate_mode(conn)) as batch_op:
            batch_op.add_column(
                sa.Column("allow_persistent_selection", sa.Boolean(), nullable=False, server_default=sa.false())
            )

    if not migration.table_exists("channel_active_workflow_selection", conn):
        op.create_table(
            "channel_active_workflow_selection",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=False),
            sa.Column("conversation_binding_id", sa.Uuid(), nullable=False),
            sa.Column("channel_identity_id", sa.Uuid(), nullable=False),
            sa.Column("conversation_scope_id", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("workflow_command_id", sa.Uuid(), nullable=False),
            sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["conversation_binding_id"], ["channel_conversation_binding.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["channel_identity_id"], ["channel_identity.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["workflow_command_id"], ["channel_workflow_command.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "connection_id",
                "conversation_binding_id",
                "channel_identity_id",
                "conversation_scope_id",
                name="uq_channel_active_flow_selection_scope",
            ),
        )
        for name, columns in (
            ("ix_channel_active_workflow_selection_connection_id", ["connection_id"]),
            ("ix_channel_active_workflow_selection_conversation_binding_id", ["conversation_binding_id"]),
            ("ix_channel_active_workflow_selection_channel_identity_id", ["channel_identity_id"]),
            ("ix_channel_active_workflow_selection_workflow_command_id", ["workflow_command_id"]),
            (
                "ix_channel_active_flow_selection_lookup",
                ["connection_id", "conversation_binding_id", "channel_identity_id", "conversation_scope_id"],
            ),
            ("ix_channel_active_flow_selection_connection_updated", ["connection_id", "updated_at"]),
            ("ix_channel_active_flow_selection_expires", ["expires_at"]),
        ):
            op.create_index(name, "channel_active_workflow_selection", columns, unique=False)

    execution_columns = _columns("channel_execution_log", conn)
    if execution_columns:
        with op.batch_alter_table("channel_execution_log", recreate=_recreate_mode(conn)) as batch_op:
            if "workflow_command_id" not in execution_columns:
                batch_op.add_column(sa.Column("workflow_command_id", sa.Uuid(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_channel_execution_workflow_command",
                    "channel_workflow_command",
                    ["workflow_command_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
            if "active_selection_id" not in execution_columns:
                batch_op.add_column(sa.Column("active_selection_id", sa.Uuid(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_channel_execution_active_selection",
                    "channel_active_workflow_selection",
                    ["active_selection_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
            if "selection_scope" not in execution_columns:
                batch_op.add_column(sa.Column("selection_scope", sa.String(length=32), nullable=True))
        execution_indexes = _indexes("channel_execution_log", conn)
        if "ix_channel_execution_workflow_command_id" not in execution_indexes:
            op.create_index(
                "ix_channel_execution_workflow_command_id",
                "channel_execution_log",
                ["workflow_command_id"],
                unique=False,
            )
        if "ix_channel_execution_active_selection_id" not in execution_indexes:
            op.create_index(
                "ix_channel_execution_active_selection_id",
                "channel_execution_log",
                ["active_selection_id"],
                unique=False,
            )

    if migration.table_exists("channel_conversation_context_entry", conn):
        context_indexes = _indexes("channel_conversation_context_entry", conn)
        if "ix_channel_context_conversation_session_created" not in context_indexes:
            op.create_index(
                "ix_channel_context_conversation_session_created",
                "channel_conversation_context_entry",
                ["conversation_binding_id", "session_id", "created_at"],
                unique=False,
            )


def downgrade() -> None:
    conn = op.get_bind()

    if migration.table_exists("channel_conversation_context_entry", conn):
        if "ix_channel_context_conversation_session_created" in _indexes(
            "channel_conversation_context_entry", conn
        ):
            op.drop_index(
                "ix_channel_context_conversation_session_created",
                table_name="channel_conversation_context_entry",
            )

    execution_columns = _columns("channel_execution_log", conn)
    if execution_columns:
        for index_name in ("ix_channel_execution_active_selection_id", "ix_channel_execution_workflow_command_id"):
            if index_name in _indexes("channel_execution_log", conn):
                op.drop_index(index_name, table_name="channel_execution_log")
        with op.batch_alter_table("channel_execution_log", recreate=_recreate_mode(conn)) as batch_op:
            if "selection_scope" in execution_columns:
                batch_op.drop_column("selection_scope")
            if "active_selection_id" in execution_columns:
                batch_op.drop_constraint("fk_channel_execution_active_selection", type_="foreignkey")
                batch_op.drop_column("active_selection_id")
            if "workflow_command_id" in execution_columns:
                batch_op.drop_constraint("fk_channel_execution_workflow_command", type_="foreignkey")
                batch_op.drop_column("workflow_command_id")

    if migration.table_exists("channel_active_workflow_selection", conn):
        op.drop_table("channel_active_workflow_selection")

    command_columns = _columns("channel_workflow_command", conn)
    if "allow_persistent_selection" in command_columns:
        with op.batch_alter_table("channel_workflow_command", recreate=_recreate_mode(conn)) as batch_op:
            batch_op.drop_column("allow_persistent_selection")

    connection_columns = _columns("channel_connection", conn)
    if connection_columns:
        with op.batch_alter_table("channel_connection", recreate=_recreate_mode(conn)) as batch_op:
            if "flow_selection_ttl_hours" in connection_columns:
                batch_op.drop_column("flow_selection_ttl_hours")
            if "user_flow_selection_enabled" in connection_columns:
                batch_op.drop_column("user_flow_selection_enabled")
'''


FLOW_SELECTION_TEST = '''from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from langflow.channels.services.flow_selection import (
    clear_active_workflow_selection,
    resolve_active_workflow_selection,
    set_active_workflow_selection,
)
from langflow.services.database.models.channel.command_model import (
    ChannelCommandScope,
    ChannelWorkflowCommand,
)
from langflow.services.database.models.channel.flow_selection_model import ChannelActiveWorkflowSelection
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConversationBinding,
    ChannelIdentity,
)


@pytest.fixture
async def selection_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    tables = [
        ChannelConnection.__table__,
        ChannelConversationBinding.__table__,
        ChannelIdentity.__table__,
        ChannelWorkflowCommand.__table__,
        ChannelActiveWorkflowSelection.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: SQLModel.metadata.create_all(sync_connection, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(selection_session):
    connection = ChannelConnection(
        id=uuid4(),
        user_id=uuid4(),
        name="Feishu",
        channel_type="feishu",
        credentials_encrypted="encrypted",
        user_flow_selection_enabled=True,
        flow_selection_ttl_hours=24,
    )
    binding = ChannelConversationBinding(
        id=uuid4(),
        connection_id=connection.id,
        external_conversation_id="chat-1",
        conversation_type="group",
    )
    identity = ChannelIdentity(
        id=uuid4(),
        connection_id=connection.id,
        external_user_id="ou-user-1",
    )
    command = ChannelWorkflowCommand(
        id=uuid4(),
        connection_id=connection.id,
        created_by=connection.user_id,
        flow_id=uuid4(),
        command="/summary",
        normalized_command="/summary",
        scope_type=ChannelCommandScope.CONNECTION_SHARED.value,
        scope_key="connection",
        allow_persistent_selection=True,
    )
    selection_session.add_all([connection, binding, identity, command])
    await selection_session.flush()
    return connection, binding, identity, command


@pytest.mark.asyncio
async def test_selection_persists_and_resolves_for_unbound_shared_member(selection_session) -> None:
    connection, binding, identity, command = await _seed(selection_session)

    selection, selected_command = await set_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="thread-1",
        user_id=None,
        command_name="/summary",
    )
    assert selected_command.id == command.id
    assert selection.workflow_command_id == command.id
    assert selection.expires_at is not None

    resolution = await resolve_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="thread-1",
        user_id=None,
    )
    assert resolution.command.id == command.id
    assert resolution.selection.last_used_at is not None


@pytest.mark.asyncio
async def test_selection_isolated_by_member_and_thread(selection_session) -> None:
    connection, binding, identity, _ = await _seed(selection_session)
    await set_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="thread-a",
        user_id=None,
        command_name="/summary",
    )

    other_thread = await resolve_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="thread-b",
        user_id=None,
    )
    assert other_thread.command is None

    other_identity = ChannelIdentity(
        id=uuid4(),
        connection_id=connection.id,
        external_user_id="ou-user-2",
    )
    selection_session.add(other_identity)
    await selection_session.flush()
    other_member = await resolve_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=other_identity,
        conversation_scope_id="thread-a",
        user_id=None,
    )
    assert other_member.command is None


@pytest.mark.asyncio
async def test_expired_or_disabled_selection_is_removed(selection_session) -> None:
    connection, binding, identity, _ = await _seed(selection_session)
    selection, _ = await set_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="",
        user_id=None,
        command_name="/summary",
    )
    selection.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    selection_session.add(selection)
    await selection_session.flush()

    resolution = await resolve_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="",
        user_id=None,
    )
    assert resolution.command is None
    assert resolution.invalid_reason == "selection_expired"

    assert not await clear_active_workflow_selection(
        selection_session,
        connection_id=connection.id,
        conversation_binding_id=binding.id,
        channel_identity_id=identity.id,
        conversation_scope_id="",
    )
'''


def apply_backend_models() -> None:
    write(
        "src/backend/base/langflow/services/database/models/channel/flow_selection_model.py",
        FLOW_SELECTION_MODEL,
    )
    write(
        "src/backend/base/langflow/channels/services/flow_selection.py",
        FLOW_SELECTION_SERVICE,
    )
    write(
        "src/backend/base/langflow/alembic/versions/a1f4c7e9d2b6_add_channel_active_workflow_selection.py",
        MIGRATION,
    )
    write(
        "src/backend/tests/unit/channels/test_channel_flow_selection.py",
        FLOW_SELECTION_TEST,
    )

    replace_once(
        "src/backend/base/langflow/services/database/models/channel/model.py",
        "    personal_commands_enabled: bool = Field(default=True)\n    default_response_mode: str = Field(default=\"mention_only\", max_length=32)\n",
        "    personal_commands_enabled: bool = Field(default=True)\n"
        "    user_flow_selection_enabled: bool = Field(default=False)\n"
        "    flow_selection_ttl_hours: int = Field(default=24, ge=0, le=8760)\n"
        "    default_response_mode: str = Field(default=\"mention_only\", max_length=32)\n",
    )
    replace_once(
        "src/backend/base/langflow/services/database/models/channel/model.py",
        "    personal_commands_enabled: bool | None = None\n    default_response_mode: str | None = Field(default=None, max_length=32)\n",
        "    personal_commands_enabled: bool | None = None\n"
        "    user_flow_selection_enabled: bool | None = None\n"
        "    flow_selection_ttl_hours: int | None = Field(default=None, ge=0, le=8760)\n"
        "    default_response_mode: str | None = Field(default=None, max_length=32)\n",
    )

    replace_once(
        "src/backend/base/langflow/services/database/models/channel/command_model.py",
        "    allow_attachments: bool = Field(default=True)\n    require_mention: bool = Field(default=False)\n",
        "    allow_attachments: bool = Field(default=True)\n"
        "    allow_persistent_selection: bool = Field(default=False)\n"
        "    require_mention: bool = Field(default=False)\n",
    )
    replace_once(
        "src/backend/base/langflow/services/database/models/channel/command_model.py",
        "    allow_attachments: bool | None = None\n    require_mention: bool | None = None\n",
        "    allow_attachments: bool | None = None\n"
        "    allow_persistent_selection: bool | None = None\n"
        "    require_mention: bool | None = None\n",
    )

    replace_once(
        "src/backend/base/langflow/services/database/models/channel/context_model.py",
        "        sa.Index(\n            \"ix_channel_context_connection_created\",\n            \"connection_id\",\n            \"created_at\",\n        ),\n",
        "        sa.Index(\n            \"ix_channel_context_connection_created\",\n            \"connection_id\",\n            \"created_at\",\n        ),\n"
        "        sa.Index(\n            \"ix_channel_context_conversation_session_created\",\n            \"conversation_binding_id\",\n            \"session_id\",\n            \"created_at\",\n        ),\n",
    )

    replace_once(
        "src/backend/base/langflow/services/database/models/channel/execution_model.py",
        "    COMMAND = \"command\"\n    ADMIN_FLOW = \"admin_flow\"\n",
        "    COMMAND = \"command\"\n    SELECTED = \"selected\"\n    ADMIN_FLOW = \"admin_flow\"\n",
    )
    replace_once(
        "src/backend/base/langflow/services/database/models/channel/execution_model.py",
        "    command_name: str | None = Field(default=None, max_length=33)\n    status: str = Field(default=ChannelExecutionStatus.RUNNING.value, max_length=32, index=True)\n",
        "    command_name: str | None = Field(default=None, max_length=33)\n"
        "    workflow_command_id: UUID | None = Field(\n"
        "        default=None,\n"
        "        sa_column=Column(\n"
        "            sa.Uuid(),\n"
        "            ForeignKey(\"channel_workflow_command.id\", ondelete=\"SET NULL\"),\n"
        "            nullable=True,\n"
        "            index=True,\n"
        "        ),\n"
        "    )\n"
        "    active_selection_id: UUID | None = Field(\n"
        "        default=None,\n"
        "        sa_column=Column(\n"
        "            sa.Uuid(),\n"
        "            ForeignKey(\"channel_active_workflow_selection.id\", ondelete=\"SET NULL\"),\n"
        "            nullable=True,\n"
        "            index=True,\n"
        "        ),\n"
        "    )\n"
        "    selection_scope: str | None = Field(default=None, max_length=32)\n"
        "    status: str = Field(default=ChannelExecutionStatus.RUNNING.value, max_length=32, index=True)\n",
    )
    replace_once(
        "src/backend/base/langflow/services/database/models/channel/execution_model.py",
        "    command_name: str | None = None\n    status: str\n",
        "    command_name: str | None = None\n"
        "    workflow_command_id: UUID | None = None\n"
        "    active_selection_id: UUID | None = None\n"
        "    selection_scope: str | None = None\n"
        "    status: str\n",
    )

    replace_once(
        "src/backend/base/langflow/channels/services/execution_logs.py",
        "    command_name: str | None = None,\n    queue_wait_ms: int | None = None,\n",
        "    command_name: str | None = None,\n"
        "    workflow_command_id: UUID | None = None,\n"
        "    active_selection_id: UUID | None = None,\n"
        "    selection_scope: str | None = None,\n"
        "    queue_wait_ms: int | None = None,\n",
    )
    replace_once(
        "src/backend/base/langflow/channels/services/execution_logs.py",
        "        command_name=command_name,\n        status=ChannelExecutionStatus.RUNNING.value,\n",
        "        command_name=command_name,\n"
        "        workflow_command_id=workflow_command_id,\n"
        "        active_selection_id=active_selection_id,\n"
        "        selection_scope=selection_scope,\n"
        "        status=ChannelExecutionStatus.RUNNING.value,\n",
    )

    replace_once(
        "src/backend/base/langflow/channels/services/workflow.py",
        "def build_channel_session_id(event: ChannelEvent, context_mode: str = ChannelContextMode.ISOLATED.value) -> str:\n",
        "def build_channel_session_id(\n"
        "    event: ChannelEvent,\n"
        "    context_mode: str = ChannelContextMode.ISOLATED.value,\n"
        "    *,\n"
        "    flow_key: UUID | str | None = None,\n"
        ") -> str:\n",
    )
    replace_once(
        "src/backend/base/langflow/channels/services/workflow.py",
        "    if context_mode != ChannelContextMode.SHARED.value or event.conversation.conversation_type == \"private\":\n        parts.append(event.user.external_user_id)\n    raw = \":\".join(parts)\n",
        "    if context_mode != ChannelContextMode.SHARED.value or event.conversation.conversation_type == \"private\":\n"
        "        parts.append(event.user.external_user_id)\n"
        "    if flow_key is not None:\n"
        "        parts.append(str(flow_key))\n"
        "    raw = \":\".join(parts)\n",
    )

    replace_once(
        "src/backend/base/langflow/channels/services/context.py",
        "    *,\n    limit: int,\n) -> list[ChannelConversationContextEntry]:\n",
        "    *,\n    session_id: str,\n    limit: int,\n) -> list[ChannelConversationContextEntry]:\n",
    )
    replace_once(
        "src/backend/base/langflow/channels/services/context.py",
        "                select(ChannelConversationContextEntry)\n                .where(ChannelConversationContextEntry.conversation_binding_id == binding.id)\n",
        "                select(ChannelConversationContextEntry)\n"
        "                .where(\n"
        "                    ChannelConversationContextEntry.conversation_binding_id == binding.id,\n"
        "                    ChannelConversationContextEntry.session_id == session_id,\n"
        "                )\n",
    )
    replace_once(
        "src/backend/base/langflow/channels/services/context.py",
        "    entries = await _recent_entries(session, binding, limit=connection.shared_context_window)\n",
        "    entries = await _recent_entries(\n"
        "        session,\n"
        "        binding,\n"
        "        session_id=session_id,\n"
        "        limit=connection.shared_context_window,\n"
        "    )\n",
    )


def apply_model_exports() -> None:
    replace_once(
        "src/backend/base/langflow/services/database/models/channel/__init__.py",
        "from langflow.services.database.models.channel.file_model import (\n",
        "from langflow.services.database.models.channel.flow_selection_model import (\n"
        "    ChannelActiveWorkflowSelection,\n"
        "    ChannelActiveWorkflowSelectionPage,\n"
        "    ChannelActiveWorkflowSelectionRead,\n"
        ")\n"
        "from langflow.services.database.models.channel.file_model import (\n",
    )
    replace_once(
        "src/backend/base/langflow/services/database/models/channel/__init__.py",
        "    \"ChannelAccessPolicy\",\n",
        "    \"ChannelAccessPolicy\",\n"
        "    \"ChannelActiveWorkflowSelection\",\n"
        "    \"ChannelActiveWorkflowSelectionPage\",\n"
        "    \"ChannelActiveWorkflowSelectionRead\",\n",
    )
    replace_once(
        "src/backend/base/langflow/services/database/models/__init__.py",
        "    ChannelConfigurationAudit,\n",
        "    ChannelActiveWorkflowSelection,\n    ChannelConfigurationAudit,\n",
    )
    replace_once(
        "src/backend/base/langflow/services/database/models/__init__.py",
        "    \"ChannelConfigurationAudit\",\n",
        "    \"ChannelActiveWorkflowSelection\",\n    \"ChannelConfigurationAudit\",\n",
    )


def apply_system_commands() -> None:
    replace_once(
        "src/backend/base/langflow/channels/services/system_commands.py",
        "    SystemCommandDefinition(\n        command=\"/flow\",\n",
        "    SystemCommandDefinition(\n"
        "        command=\"/use-flow\",\n"
        "        aliases=(\"/切换工作流\",),\n"
        "        description=\"切换当前会话持续使用的工作流\",\n"
        "        permission=\"bound_or_shared\",\n"
        "    ),\n"
        "    SystemCommandDefinition(\n"
        "        command=\"/current-flow\",\n"
        "        aliases=(\"/当前工作流\",),\n"
        "        description=\"查看当前会话正在使用的工作流\",\n"
        "        permission=\"bound_or_shared\",\n"
        "    ),\n"
        "    SystemCommandDefinition(\n        command=\"/flow\",\n",
    )


def apply_dispatch() -> None:
    path = "src/backend/base/langflow/channels/services/dispatch.py"
    replace_once(
        path,
        "from langflow.channels.services.context import prepare_channel_input, record_channel_response\n",
        "from langflow.channels.services.context import prepare_channel_input, record_channel_response\n"
        "from langflow.channels.services.conversation_scope import conversation_scope_id\n"
        "from langflow.channels.services.flow_selection import (\n"
        "    ActiveWorkflowResolution,\n"
        "    FlowSelectionCommandUnavailableError,\n"
        "    FlowSelectionDisabledError,\n"
        "    FlowSelectionNotAllowedError,\n"
        "    clear_active_workflow_selection,\n"
        "    resolve_active_workflow_selection,\n"
        "    set_active_workflow_selection,\n"
        ")\n",
    )

    old_handle = '''        try:
            principal = await resolve_execution_principal(
                self.session,
                self.connection,
                binding,
                identity,
            )
        except ChannelBindingRequiredError:
            return await self._binding_required_message(event)
        except ChannelServiceIdentityUnavailableError:
            return ChannelMessage(text="当前渠道共享执行身份尚未配置或已停用，请联系管理员。")

        if event.message.attachments:
            binding = binding or await self._ensure_conversation_binding(event)
            if not binding.allow_file_upload:
                return ChannelMessage(text="当前会话已关闭文件上传，请在 OpenXFlow 渠道中心重新启用。")
            responses: list[str] = []
            title: str | None = None
            for attachment in event.message.attachments:
                response = await self.file_service.handle_attachment(
                    event=event,
                    user=principal.user,
                    binding=binding,
                    attachment=attachment,
                )
                title = title or response.title
                response_text = response.markdown or response.text
                if response_text:
                    responses.append(response_text)
            return ChannelMessage(title=title or "文件处理结果", text="\n\n".join(responses))

        text = (event.message.text or "").strip()
        if not text:
            return None
        flow_id = self._resolve_default_flow_id(binding)
        if flow_id is None:
            return await self._pending_route_message(binding)
        return await self._execute_workflow(
            event,
            principal,
            str(flow_id),
            text,
            binding=binding,
            trigger_type=ChannelExecutionTrigger.DEFAULT.value,
            flow_id=flow_id,
        )
'''
    new_handle = '''        if event.message.attachments:
            try:
                principal = await resolve_execution_principal(
                    self.session,
                    self.connection,
                    binding,
                    identity,
                )
            except ChannelBindingRequiredError:
                return await self._binding_required_message(event)
            except ChannelServiceIdentityUnavailableError:
                return ChannelMessage(text="当前渠道共享执行身份尚未配置或已停用，请联系管理员。")
            binding = binding or await self._ensure_conversation_binding(event)
            if not binding.allow_file_upload:
                return ChannelMessage(text="当前会话已关闭文件上传，请在 OpenXFlow 渠道中心重新启用。")
            responses: list[str] = []
            title: str | None = None
            for attachment in event.message.attachments:
                response = await self.file_service.handle_attachment(
                    event=event,
                    user=principal.user,
                    binding=binding,
                    attachment=attachment,
                )
                title = title or response.title
                response_text = response.markdown or response.text
                if response_text:
                    responses.append(response_text)
            return ChannelMessage(title=title or "文件处理结果", text="\n\n".join(responses))

        text = (event.message.text or "").strip()
        if not text:
            return None

        selection_resolution = ActiveWorkflowResolution()
        if binding is not None:
            selection_resolution = await resolve_active_workflow_selection(
                self.session,
                connection=self.connection,
                binding=binding,
                identity=identity,
                conversation_scope_id=conversation_scope_id(event),
                user_id=personal_user_id,
            )
        if selection_resolution.command is not None and selection_resolution.selection is not None:
            selected_command = selection_resolution.command
            try:
                principal = await resolve_execution_principal(
                    self.session,
                    self.connection,
                    binding,
                    identity,
                    requires_personal=selected_command.owner_user_id is not None,
                )
            except ChannelBindingRequiredError:
                return await self._binding_required_message(event)
            except ChannelServiceIdentityUnavailableError:
                return ChannelMessage(text="当前渠道共享执行身份尚未配置或已停用，请联系管理员。")
            selected_input = render_command_input(
                selected_command,
                input_value=text,
                sender_name=event.user.display_name,
                conversation_name=event.conversation.title or (binding.display_name if binding else None),
                conversation_type=event.conversation.conversation_type,
            )
            return await self._execute_workflow(
                event,
                principal,
                str(selected_command.flow_id),
                selected_input or None,
                binding=binding,
                trigger_type=ChannelExecutionTrigger.SELECTED.value,
                command_name=selected_command.normalized_command,
                flow_id=selected_command.flow_id,
                workflow_command_id=selected_command.id,
                active_selection_id=selection_resolution.selection.id,
                selection_scope="identity_conversation",
            )

        try:
            principal = await resolve_execution_principal(
                self.session,
                self.connection,
                binding,
                identity,
            )
        except ChannelBindingRequiredError:
            return await self._binding_required_message(event)
        except ChannelServiceIdentityUnavailableError:
            return ChannelMessage(text="当前渠道共享执行身份尚未配置或已停用，请联系管理员。")
        flow_id = self._resolve_default_flow_id(binding)
        if flow_id is None:
            return await self._pending_route_message(binding)
        response = await self._execute_workflow(
            event,
            principal,
            str(flow_id),
            text,
            binding=binding,
            trigger_type=ChannelExecutionTrigger.DEFAULT.value,
            flow_id=flow_id,
        )
        if selection_resolution.invalid_reason and response is not None:
            return self._with_selection_fallback_notice(response)
        return response
'''
    replace_once(path, old_handle, new_handle)

    replace_once(
        path,
        "                conversation_type=event.conversation.conversation_type,\n            )\n        if command == \"/whoami\":\n",
        "                conversation_type=event.conversation.conversation_type,\n"
        "                event=event,\n"
        "                identity=identity,\n"
        "            )\n"
        "        if command == \"/whoami\":\n",
    )

    replace_once(
        path,
        "        if command == \"/flow\":\n",
        "        if command == \"/use-flow\":\n"
        "            return await self._use_flow_message(\n"
        "                event=event,\n"
        "                identity=identity,\n"
        "                bound_user=bound_user,\n"
        "                binding=binding,\n"
        "                argument=argument,\n"
        "                personal_user_id=personal_user_id,\n"
        "            )\n"
        "        if command == \"/current-flow\":\n"
        "            return await self._current_flow_message(\n"
        "                event=event,\n"
        "                identity=identity,\n"
        "                binding=binding,\n"
        "                personal_user_id=personal_user_id,\n"
        "            )\n"
        "        if command == \"/flow\":\n",
    )

    methods = '''    async def _use_flow_message(
        self,
        *,
        event: ChannelEvent,
        identity,
        bound_user: User | None,
        binding: ChannelConversationBinding | None,
        argument: str,
        personal_user_id: UUID | None,
    ) -> ChannelMessage:
        if not self.connection.user_flow_selection_enabled:
            return ChannelMessage(text="当前渠道未开启用户工作流切换，请联系管理员在默认路由中启用。")
        binding = binding or await self._ensure_conversation_binding(event)
        requested = argument.strip().split(maxsplit=1)[0] if argument.strip() else ""
        if not requested:
            return ChannelMessage(
                text="用法：/use-flow <业务指令>\n恢复默认：/use-flow default\n发送 /commands 查看可用业务指令。"
            )
        if requested.lower() in {"default", "/default", "默认"}:
            cleared = await clear_active_workflow_selection(
                self.session,
                connection_id=self.connection.id,
                conversation_binding_id=binding.id,
                channel_identity_id=identity.id,
                conversation_scope_id=conversation_scope_id(event),
            )
            await self.session.commit()
            default_flow_id = self._resolve_default_flow_id(binding)
            text = "已恢复当前会话的默认工作流。" if cleared else "当前已经在使用默认工作流。"
            if default_flow_id is None:
                text += " 当前会话尚未配置默认工作流。"
            return ChannelMessage(title="工作流已恢复", text=text)

        try:
            selection, command = await set_active_workflow_selection(
                self.session,
                connection=self.connection,
                binding=binding,
                identity=identity,
                conversation_scope_id=conversation_scope_id(event),
                user_id=personal_user_id,
                command_name=requested,
            )
        except FlowSelectionDisabledError:
            return ChannelMessage(text="当前渠道未开启用户工作流切换。")
        except FlowSelectionCommandUnavailableError:
            return ChannelMessage(text=f"当前会话没有可切换的业务指令 {requested}。发送 /commands 查看可用指令。")
        except FlowSelectionNotAllowedError:
            return ChannelMessage(text=f"指令 {requested} 仅支持单次执行，管理员未允许将其设为当前工作流。")
        await self.session.commit()
        expires = "永久有效" if selection.expires_at is None else f"有效期 {self.connection.flow_selection_ttl_hours} 小时"
        account = f"绑定账号：{bound_user.username}\n" if bound_user is not None else ""
        return ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="工作流已切换",
            text=(
                f"当前工作流：{command.command}\n"
                f"{account}"
                f"范围：当前用户 + 当前会话/线程\n"
                f"{expires}\n\n"
                "后续普通消息将持续使用该工作流。发送 /use-flow default 恢复默认。"
            ),
            actions=[
                ChannelAction(
                    action_id="system:current-flow",
                    label="/current-flow",
                    value="/current-flow",
                    style="primary",
                ),
                ChannelAction(action_id="system:use-flow-default", label="恢复默认", value="/use-flow default"),
            ],
        )

    async def _current_flow_message(
        self,
        *,
        event: ChannelEvent,
        identity,
        binding: ChannelConversationBinding | None,
        personal_user_id: UUID | None,
    ) -> ChannelMessage:
        if binding is not None:
            resolution = await resolve_active_workflow_selection(
                self.session,
                connection=self.connection,
                binding=binding,
                identity=identity,
                conversation_scope_id=conversation_scope_id(event),
                user_id=personal_user_id,
                touch=False,
            )
            if resolution.command is not None and resolution.selection is not None:
                expires = (
                    "永久有效"
                    if resolution.selection.expires_at is None
                    else resolution.selection.expires_at.isoformat()
                )
                return ChannelMessage(
                    title="当前工作流",
                    text=(
                        f"业务指令：{resolution.command.command}\n"
                        f"工作流 ID：{str(resolution.command.flow_id)[:8]}…\n"
                        "来源：个人会话选择\n"
                        f"有效期至：{expires}"
                    ),
                )
        default_flow_id = self._resolve_default_flow_id(binding)
        if default_flow_id is None:
            return ChannelMessage(title="当前工作流", text="当前没有个人选择，也没有可用默认工作流。")
        return ChannelMessage(
            title="当前工作流",
            text=f"当前使用会话或连接默认工作流：{str(default_flow_id)[:8]}…",
        )

'''
    replace_once(path, "    async def _execute_custom_command(\n", methods + "    async def _execute_custom_command(\n")

    replace_once(
        path,
        "            command_name=command.normalized_command,\n            flow_id=command.flow_id,\n",
        "            command_name=command.normalized_command,\n"
        "            flow_id=command.flow_id,\n"
        "            workflow_command_id=command.id,\n",
    )

    replace_once(
        path,
        "        conversation_type: str,\n    ) -> ChannelMessage:\n",
        "        conversation_type: str,\n"
        "        event: ChannelEvent,\n"
        "        identity,\n"
        "    ) -> ChannelMessage:\n",
    )
    replace_once(
        path,
        "        sections = [\"系统指令\"]\n",
        "        current_command_id: UUID | None = None\n"
        "        if binding is not None and self.connection.user_flow_selection_enabled:\n"
        "            current_resolution = await resolve_active_workflow_selection(\n"
        "                self.session,\n"
        "                connection=self.connection,\n"
        "                binding=binding,\n"
        "                identity=identity,\n"
        "                conversation_scope_id=conversation_scope_id(event),\n"
        "                user_id=user_id,\n"
        "                touch=False,\n"
        "            )\n"
        "            if current_resolution.command is not None:\n"
        "                current_command_id = current_resolution.command.id\n\n"
        "        sections = [\"系统指令\"]\n",
    )
    replace_once(
        path,
        "                description = f\" — {item.description}\" if item.description else \"\"\n                sections.append(f\"{item.command}{description}\")\n",
        "                description = f\" — {item.description}\" if item.description else \"\"\n"
        "                flags: list[str] = []\n"
        "                if item.allow_persistent_selection:\n"
        "                    flags.append(\"可切换\")\n"
        "                if item.id == current_command_id:\n"
        "                    flags.append(\"当前\")\n"
        "                suffix = f\" [{', '.join(flags)}]\" if flags else \"\"\n"
        "                sections.append(f\"{item.command}{description}{suffix}\")\n",
    )
    replace_once(
        path,
        "            if item.command in {\"/commands\", \"/whoami\", \"/files\", \"/knowledge\", \"/status\"}\n",
        "            if item.command\n"
        "            in {\"/commands\", \"/current-flow\", \"/whoami\", \"/files\", \"/knowledge\", \"/status\"}\n",
    )

    replace_once(
        path,
        "    def _resolve_default_flow_id(self, binding: ChannelConversationBinding | None) -> UUID | None:\n",
        "    @staticmethod\n"
        "    def _with_selection_fallback_notice(response: ChannelMessage) -> ChannelMessage:\n"
        "        notice = \"你之前选择的工作流已失效，当前已恢复默认工作流。\"\n"
        "        if response.markdown:\n"
        "            response.markdown = f\"{notice}\\n\\n{response.markdown}\"\n"
        "        else:\n"
        "            response.text = f\"{notice}\\n\\n{response.text or ''}\"\n"
        "        return response\n\n"
        "    def _resolve_default_flow_id(self, binding: ChannelConversationBinding | None) -> UUID | None:\n",
    )

    replace_once(
        path,
        "        command_name: str | None = None,\n        flow_id: UUID | None = None,\n    ) -> ChannelMessage | None:\n",
        "        command_name: str | None = None,\n"
        "        flow_id: UUID | None = None,\n"
        "        workflow_command_id: UUID | None = None,\n"
        "        active_selection_id: UUID | None = None,\n"
        "        selection_scope: str | None = None,\n"
        "    ) -> ChannelMessage | None:\n",
    )
    replace_once(
        path,
        "        session_id = build_channel_session_id(event, context_mode)\n",
        "        session_id = build_channel_session_id(\n"
        "            event,\n"
        "            context_mode,\n"
        "            flow_key=flow_id or flow_identifier,\n"
        "        )\n",
    )
    replace_once(
        path,
        "                    command_name=command_name,\n                    queue_wait_ms=queue_wait_ms,\n",
        "                    command_name=command_name,\n"
        "                    workflow_command_id=workflow_command_id,\n"
        "                    active_selection_id=active_selection_id,\n"
        "                    selection_scope=selection_scope,\n"
        "                    queue_wait_ms=queue_wait_ms,\n",
    )
    replace_once(
        path,
        "            if command_name:\n                channel_context[\"command_name\"] = command_name\n",
        "            if command_name:\n"
        "                channel_context[\"command_name\"] = command_name\n"
        "            if workflow_command_id is not None:\n"
        "                channel_context[\"workflow_command_id\"] = str(workflow_command_id)\n"
        "            if active_selection_id is not None:\n"
        "                channel_context[\"active_selection_id\"] = str(active_selection_id)\n",
    )


def apply_management_api() -> None:
    path = "src/backend/base/langflow/api/v1/channel_management.py"
    replace_once(
        path,
        "from langflow.channels.services.execution_logs import list_channel_executions\n",
        "from langflow.channels.services.execution_logs import list_channel_executions\n"
        "from langflow.channels.services.flow_selection import (\n"
        "    cleanup_expired_workflow_selections,\n"
        "    delete_active_workflow_selection,\n"
        "    list_active_workflow_selections,\n"
        ")\n",
    )
    replace_once(
        path,
        "from langflow.services.database.models.channel.execution_model import ChannelExecutionLogPage\n",
        "from langflow.services.database.models.channel.execution_model import ChannelExecutionLogPage\n"
        "from langflow.services.database.models.channel.flow_selection_model import (\n"
        "    ChannelActiveWorkflowSelectionPage,\n"
        ")\n",
    )
    append_once(
        path,
        "async def read_channel_flow_selections(",
        '''@router.get(
    "/{connection_id}/flow-selections",
    response_model=ChannelActiveWorkflowSelectionPage,
)
async def read_channel_flow_selections(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    conversation_binding_id: Annotated[UUID | None, Query()] = None,
    channel_identity_id: Annotated[UUID | None, Query()] = None,
    workflow_command_id: Annotated[UUID | None, Query()] = None,
) -> ChannelActiveWorkflowSelectionPage:
    await _administrable_connection_or_404(db, current_user, connection_id, ChannelAction.AUDIT)
    return await list_active_workflow_selections(
        db,
        connection_id,
        page=page,
        page_size=page_size,
        conversation_binding_id=conversation_binding_id,
        channel_identity_id=channel_identity_id,
        workflow_command_id=workflow_command_id,
    )


@router.delete(
    "/{connection_id}/flow-selections/{selection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_channel_flow_selection(
    connection_id: UUID,
    selection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> Response:
    await _administrable_connection_or_404(db, current_user, connection_id, ChannelAction.WRITE)
    if not await delete_active_workflow_selection(
        db,
        connection_id=connection_id,
        selection_id=selection_id,
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active workflow selection not found")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{connection_id}/flow-selections/cleanup")
async def cleanup_channel_flow_selections(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> dict[str, int]:
    await _administrable_connection_or_404(db, current_user, connection_id, ChannelAction.WRITE)
    removed = await cleanup_expired_workflow_selections(db, connection_id=connection_id)
    await db.commit()
    return {"removed": removed}
''',
    )


def apply_frontend() -> None:
    path = "src/frontend/src/controllers/API/queries/channels/types.ts"
    replace_once(
        path,
        "  | \"command\"\n  | \"admin_flow\"\n",
        "  | \"command\"\n  | \"selected\"\n  | \"admin_flow\"\n",
    )
    replace_once(
        path,
        "  personal_commands_enabled: boolean;\n  default_response_mode: ChannelResponseMode;\n",
        "  personal_commands_enabled: boolean;\n"
        "  user_flow_selection_enabled: boolean;\n"
        "  flow_selection_ttl_hours: number;\n"
        "  default_response_mode: ChannelResponseMode;\n",
    )
    replace_once(
        path,
        "  personal_commands_enabled?: boolean;\n  default_response_mode?: ChannelResponseMode;\n",
        "  personal_commands_enabled?: boolean;\n"
        "  user_flow_selection_enabled?: boolean;\n"
        "  flow_selection_ttl_hours?: number;\n"
        "  default_response_mode?: ChannelResponseMode;\n",
    )
    replace_once(
        path,
        "  personal_commands_enabled?: boolean;\n  default_response_mode?: ChannelResponseMode;\n",
        "  personal_commands_enabled?: boolean;\n"
        "  user_flow_selection_enabled?: boolean;\n"
        "  flow_selection_ttl_hours?: number;\n"
        "  default_response_mode?: ChannelResponseMode;\n",
    )
    replace_once(
        path,
        "  allow_attachments: boolean;\n  require_mention: boolean;\n",
        "  allow_attachments: boolean;\n"
        "  allow_persistent_selection: boolean;\n"
        "  require_mention: boolean;\n",
    )
    replace_once(
        path,
        "  allow_attachments: boolean;\n  require_mention: boolean;\n  enabled: boolean;\n  settings_data: Record<string, unknown>;\n}\n\nexport interface ChannelWorkflowCommandUpdate",
        "  allow_attachments: boolean;\n"
        "  allow_persistent_selection: boolean;\n"
        "  require_mention: boolean;\n"
        "  enabled: boolean;\n"
        "  settings_data: Record<string, unknown>;\n"
        "}\n\n"
        "export interface ChannelWorkflowCommandUpdate",
    )
    replace_once(
        path,
        "  allow_attachments?: boolean;\n  require_mention?: boolean;\n",
        "  allow_attachments?: boolean;\n"
        "  allow_persistent_selection?: boolean;\n"
        "  require_mention?: boolean;\n",
    )
    replace_once(
        path,
        "  command_name: string | null;\n  status: ChannelExecutionStatus;\n",
        "  command_name: string | null;\n"
        "  workflow_command_id: string | null;\n"
        "  active_selection_id: string | null;\n"
        "  selection_scope: string | null;\n"
        "  status: ChannelExecutionStatus;\n",
    )

    path = "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/CommandDialog.tsx"
    replace_once(
        path,
        "  allowAttachments: boolean;\n  requireMention: boolean;\n",
        "  allowAttachments: boolean;\n  allowPersistentSelection: boolean;\n  requireMention: boolean;\n",
    )
    replace_once(
        path,
        "  allowAttachments: true,\n  requireMention: false,\n",
        "  allowAttachments: true,\n  allowPersistentSelection: false,\n  requireMention: false,\n",
    )
    replace_once(
        path,
        "      allowAttachments: command.allow_attachments,\n      requireMention: command.require_mention,\n",
        "      allowAttachments: command.allow_attachments,\n"
        "      allowPersistentSelection: command.allow_persistent_selection,\n"
        "      requireMention: command.require_mention,\n",
    )
    replace_once(
        path,
        "      allow_attachments: form.allowAttachments,\n      require_mention: form.requireMention,\n",
        "      allow_attachments: form.allowAttachments,\n"
        "      allow_persistent_selection: form.allowPersistentSelection,\n"
        "      require_mention: form.requireMention,\n",
    )
    replace_once(
        path,
        "            <CommandSwitch\n              title={copy(\"群聊必须 @机器人\")}\n",
        "            <CommandSwitch\n"
        "              title={copy(\"允许设为当前工作流\")}\n"
        "              description={copy(\"用户可通过 /use-flow 持续切换到此工作流。\")}\n"
        "              checked={form.allowPersistentSelection}\n"
        "              onCheckedChange={(checked) =>\n"
        "                setField(\"allowPersistentSelection\", checked)\n"
        "              }\n"
        "            />\n"
        "            <CommandSwitch\n"
        "              title={copy(\"群聊必须 @机器人\")}\n",
    )

    path = "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/CommandsTab.tsx"
    replace_once(
        path,
        "              \"普通消息使用默认工作流；“/指令 内容”仅本次路由到指定工作流。\",\n",
        "              \"普通消息使用默认或当前工作流；显式“/指令 内容”只影响本次，/use-flow 可持续切换。\",\n",
    )
    replace_once(
        path,
        "                    {command.require_mention ? ` · ${copy(\"群聊需@\")}` : \"\"}\n",
        "                    {command.require_mention ? ` · ${copy(\"群聊需@\")}` : \"\"}\n"
        "                    {command.allow_persistent_selection\n"
        "                      ? ` · ${copy(\"可持续切换\")}`\n"
        "                      : \"\"}\n",
    )

    path = "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/DefaultRoutingTab.tsx"
    replace_once(path, "import { Button } from \"@/components/ui/button\";\n", "import { Button } from \"@/components/ui/button\";\nimport { Input } from \"@/components/ui/input\";\n")
    replace_once(
        path,
        "  personalCommandsEnabled: boolean;\n  defaultResponseMode: ChannelResponseMode;\n",
        "  personalCommandsEnabled: boolean;\n"
        "  userFlowSelectionEnabled: boolean;\n"
        "  flowSelectionTtlHours: string;\n"
        "  defaultResponseMode: ChannelResponseMode;\n",
    )
    replace_once(
        path,
        "          personal_commands_enabled: form.personalCommandsEnabled,\n          default_response_mode: form.defaultResponseMode,\n",
        "          personal_commands_enabled: form.personalCommandsEnabled,\n"
        "          user_flow_selection_enabled: form.userFlowSelectionEnabled,\n"
        "          flow_selection_ttl_hours: Math.min(\n"
        "            8760,\n"
        "            Math.max(0, Number(form.flowSelectionTtlHours) || 0),\n"
        "          ),\n"
        "          default_response_mode: form.defaultResponseMode,\n",
    )
    replace_once(
        path,
        "        <SettingSwitch\n          title={copy(\"允许个人指令\")}\n",
        "        <SettingSwitch\n"
        "          title={copy(\"允许用户切换工作流\")}\n"
        "          description={copy(\"用户可按成员、会话和线程持久选择管理员允许的业务工作流。\")}\n"
        "          checked={form.userFlowSelectionEnabled}\n"
        "          onCheckedChange={(checked) =>\n"
        "            setForm((current) => ({\n"
        "              ...current,\n"
        "              userFlowSelectionEnabled: checked,\n"
        "            }))\n"
        "          }\n"
        "        />\n"
        "        <SettingSwitch\n"
        "          title={copy(\"允许个人指令\")}\n",
    )
    replace_once(
        path,
        "      </div>\n\n      {capabilities?.supports_group_chat && capabilities.supports_mentions && (\n",
        "      </div>\n\n"
        "      {form.userFlowSelectionEnabled && (\n"
        "        <label className=\"flex flex-col gap-2 text-sm font-medium\">\n"
        "          {copy(\"工作流选择有效期（小时）\")}\n"
        "          <Input\n"
        "            type=\"number\"\n"
        "            min={0}\n"
        "            max={8760}\n"
        "            value={form.flowSelectionTtlHours}\n"
        "            onChange={(event) =>\n"
        "              setForm((current) => ({\n"
        "                ...current,\n"
        "                flowSelectionTtlHours: event.target.value,\n"
        "              }))\n"
        "            }\n"
        "          />\n"
        "          <span className=\"text-xs font-normal text-muted-foreground\">\n"
        "            {copy(\"设置为 0 表示永久有效，直到用户恢复默认或管理员撤销。\")}\n"
        "          </span>\n"
        "        </label>\n"
        "      )}\n\n"
        "      {capabilities?.supports_group_chat && capabilities.supports_mentions && (\n",
    )
    replace_once(
        path,
        "    personalCommandsEnabled: connection.personal_commands_enabled,\n    defaultResponseMode: connection.default_response_mode,\n",
        "    personalCommandsEnabled: connection.personal_commands_enabled,\n"
        "    userFlowSelectionEnabled: connection.user_flow_selection_enabled,\n"
        "    flowSelectionTtlHours: String(connection.flow_selection_ttl_hours),\n"
        "    defaultResponseMode: connection.default_response_mode,\n",
    )


def apply_migration_tests() -> None:
    path = "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py"
    replace_once(
        path,
        "from langflow.alembic.versions import (\n    a8e1c6d4f5b7_add_channel_outbound_delivery as outbound_delivery_migration,\n)\n",
        "from langflow.alembic.versions import (\n"
        "    a1f4c7e9d2b6_add_channel_active_workflow_selection as active_flow_selection_migration,\n"
        ")\n"
        "from langflow.alembic.versions import (\n"
        "    a8e1c6d4f5b7_add_channel_outbound_delivery as outbound_delivery_migration,\n"
        ")\n"
        "from langflow.alembic.versions import (\n"
        "    b5d8e1f3a6c9_key_channel_outbound_delivery_parts as outbound_delivery_key_migration,\n"
        ")\n",
    )
    replace_once(
        path,
        "    identity_user_fk_migration,\n)\n",
        "    identity_user_fk_migration,\n"
        "    outbound_delivery_key_migration,\n"
        "    active_flow_selection_migration,\n"
        ")\n",
    )
    replace_once(
        path,
        "        \"a4c7d0f3e5b9\",\n    ]\n",
        "        \"a4c7d0f3e5b9\",\n"
        "        \"b5d8e1f3a6c9\",\n"
        "        \"a1f4c7e9d2b6\",\n"
        "    ]\n",
    )
    replace_once(
        path,
        "        \"f3a6c9e2b4d7\",\n    ]\n",
        "        \"f3a6c9e2b4d7\",\n"
        "        \"a4c7d0f3e5b9\",\n"
        "        \"b5d8e1f3a6c9\",\n"
        "    ]\n",
    )
    replace_once(
        path,
        "            \"channel_configuration_audit\",\n        }\n",
        "            \"channel_configuration_audit\",\n"
        "            \"channel_active_workflow_selection\",\n"
        "        }\n",
    )
    replace_once(
        path,
        "        identity_columns = {column[\"name\"]: column for column in sa.inspect(connection).get_columns(\"channel_identity\")}\n        assert identity_columns[\"openxflow_user_id\"][\"nullable\"] is True\n",
        "        identity_columns = {column[\"name\"]: column for column in sa.inspect(connection).get_columns(\"channel_identity\")}\n"
        "        assert identity_columns[\"openxflow_user_id\"][\"nullable\"] is True\n\n"
        "        connection_columns = {\n"
        "            column[\"name\"] for column in sa.inspect(connection).get_columns(\"channel_connection\")\n"
        "        }\n"
        "        assert {\"user_flow_selection_enabled\", \"flow_selection_ttl_hours\"} <= connection_columns\n"
        "        command_columns = {\n"
        "            column[\"name\"] for column in sa.inspect(connection).get_columns(\"channel_workflow_command\")\n"
        "        }\n"
        "        assert \"allow_persistent_selection\" in command_columns\n"
        "        context_indexes = {\n"
        "            index[\"name\"]: tuple(index[\"column_names\"])\n"
        "            for index in sa.inspect(connection).get_indexes(\"channel_conversation_context_entry\")\n"
        "        }\n"
        "        assert context_indexes[\"ix_channel_context_conversation_session_created\"] == (\n"
        "            \"conversation_binding_id\",\n"
        "            \"session_id\",\n"
        "            \"created_at\",\n"
        "        )\n",
    )

    path = "src/backend/tests/unit/channels/test_system_commands.py"
    replace_once(
        path,
        "    assert resolve_system_command(\"/状态\").command == \"/status\"\n",
        "    assert resolve_system_command(\"/状态\").command == \"/status\"\n"
        "    assert resolve_system_command(\"/切换工作流\").command == \"/use-flow\"\n"
        "    assert resolve_system_command(\"/当前工作流\").command == \"/current-flow\"\n",
    )
    replace_once(
        path,
        "    assert {\"/help\", \"/帮助\", \"/flow\", \"/工作流\", \"/status\", \"/状态\"} <= RESERVED_COMMAND_NAMES\n",
        "    assert {\n"
        "        \"/help\",\n"
        "        \"/帮助\",\n"
        "        \"/flow\",\n"
        "        \"/工作流\",\n"
        "        \"/status\",\n"
        "        \"/状态\",\n"
        "        \"/use-flow\",\n"
        "        \"/current-flow\",\n"
        "    } <= RESERVED_COMMAND_NAMES\n",
    )
    replace_once(
        path,
        "    assert {\"/commands\", \"/whoami\", \"/files\", \"/knowledge\"} <= public_names\n",
        "    assert {\n"
        "        \"/commands\",\n"
        "        \"/whoami\",\n"
        "        \"/files\",\n"
        "        \"/knowledge\",\n"
        "        \"/use-flow\",\n"
        "        \"/current-flow\",\n"
        "    } <= public_names\n",
    )


def cleanup_bootstrap() -> None:
    updater = "scripts/ci/update_starter_projects.py"
    content = read(updater)
    content = content.replace("from pathlib import Path\n", "")
    block = '''
if os.environ.get("GITHUB_HEAD_REF") == "automation/channel-active-flow-selection":
    scope: dict[str, object] = {}
    exec(Path(".github/scripts/channel_active_flow_codegen.py").read_text(encoding="utf-8"), scope)
    scope["run"]()
    raise SystemExit(0)

'''
    if block not in content:
        raise RuntimeError("Bootstrap block missing from update_starter_projects.py")
    write(updater, content.replace(block, "", 1))
    (ROOT / ".github/scripts/channel_active_flow_codegen.py").unlink()


def run() -> None:
    if os.environ.get("GITHUB_HEAD_REF") != BRANCH:
        raise RuntimeError("Refusing to run active workflow codegen outside the temporary branch")

    apply_backend_models()
    apply_model_exports()
    apply_system_commands()
    apply_dispatch()
    apply_management_api()
    apply_frontend()
    apply_migration_tests()

    python_paths = [
        "src/backend/base/langflow/channels/services/flow_selection.py",
        "src/backend/base/langflow/channels/services/dispatch.py",
        "src/backend/base/langflow/channels/services/system_commands.py",
        "src/backend/base/langflow/channels/services/workflow.py",
        "src/backend/base/langflow/channels/services/context.py",
        "src/backend/base/langflow/channels/services/execution_logs.py",
        "src/backend/base/langflow/api/v1/channel_management.py",
        "src/backend/base/langflow/services/database/models/channel/flow_selection_model.py",
        "src/backend/base/langflow/services/database/models/channel/model.py",
        "src/backend/base/langflow/services/database/models/channel/command_model.py",
        "src/backend/base/langflow/services/database/models/channel/context_model.py",
        "src/backend/base/langflow/services/database/models/channel/execution_model.py",
        "src/backend/base/langflow/alembic/versions/a1f4c7e9d2b6_add_channel_active_workflow_selection.py",
        "src/backend/tests/unit/channels/test_channel_flow_selection.py",
        "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py",
        "src/backend/tests/unit/channels/test_system_commands.py",
    ]
    joined = " ".join(python_paths)
    run_command(f"uvx --quiet ruff check --fix --config pyproject.toml --extend-ignore EM101,TRY003 {joined}")
    run_command(f"uvx --quiet ruff format --config pyproject.toml {joined}")
    run_command("python -m compileall -q src/backend/base/langflow/channels src/backend/base/langflow/services/database/models/channel src/backend/base/langflow/api/v1/channel_management.py")
    run_command(
        "uv run --frozen --project src/backend/base --group dev pytest -q --tb=short "
        "--confcutdir=src/backend/tests/unit/channels "
        "src/backend/tests/unit/channels/test_channel_flow_selection.py "
        "src/backend/tests/unit/channels/test_system_commands.py "
        "src/backend/tests/unit/channels/test_command_routing.py "
        "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py"
    )

    cleanup_bootstrap()
    run_command("git config user.name 'github-actions[bot]'")
    run_command("git config user.email '41898282+github-actions[bot]@users.noreply.github.com'")
    run_command("git add -A")
    run_command("git commit -m 'feat(channels): add persistent workflow selection'")
    run_command(f"git push origin HEAD:{BRANCH}")
