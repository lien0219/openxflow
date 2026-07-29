from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRANCH = os.environ.get("HEAD_REF", "automation/channel-final-hardening")


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


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(args), flush=True)
    return subprocess.run(args, cwd=ROOT, check=check, text=True)


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
        sa.Index("ix_channel_active_flow_selection_connection_expires", "connection_id", "expires_at"),
        sa.Index(
            "ix_channel_active_flow_selection_identity_updated",
            "connection_id",
            "channel_identity_id",
            "updated_at",
        ),
        sa.Index(
            "ix_channel_active_flow_selection_command_updated",
            "workflow_command_id",
            "updated_at",
        ),
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
    identity_display_name: str | None = None
    external_user_id: str | None = None
    conversation_display_name: str | None = None
    external_conversation_id: str | None = None
    conversation_type: str | None = None
    command: str | None = None
    flow_id: UUID | None = None
    flow_name: str | None = None
    flow_endpoint_name: str | None = None
    execution_identity_type: str | None = None


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
'''

MAINTENANCE_SERVICE = '''"""Periodic lifecycle maintenance for channel workflow selections."""

from __future__ import annotations

import asyncio
import os

from lfx.log.logger import logger

from langflow.channels.services.flow_selection import cleanup_expired_workflow_selections_batch
from langflow.services.deps import session_scope

_DEFAULT_INTERVAL_SECONDS = 60 * 60
_DEFAULT_BATCH_SIZE = 500
_DEFAULT_MAX_BATCHES = 20


def _positive_int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


async def maintain_flow_selections_once() -> int:
    batch_size = _positive_int_env(
        "LANGFLOW_CHANNEL_FLOW_SELECTION_CLEANUP_BATCH_SIZE",
        _DEFAULT_BATCH_SIZE,
        minimum=1,
        maximum=1000,
    )
    max_batches = _positive_int_env(
        "LANGFLOW_CHANNEL_FLOW_SELECTION_CLEANUP_MAX_BATCHES",
        _DEFAULT_MAX_BATCHES,
        minimum=1,
        maximum=100,
    )
    removed = 0
    for _ in range(max_batches):
        async with session_scope() as session:
            batch_removed = await cleanup_expired_workflow_selections_batch(
                session,
                batch_size=batch_size,
                action="expire",
            )
            await session.commit()
        removed += batch_removed
        if batch_removed < batch_size:
            break
    if removed:
        await logger.ainfo("Cleaned up %s expired channel workflow selections", removed)
    return removed


async def run_flow_selection_maintenance() -> None:
    interval_seconds = _positive_int_env(
        "LANGFLOW_CHANNEL_FLOW_SELECTION_CLEANUP_INTERVAL_SECONDS",
        _DEFAULT_INTERVAL_SECONDS,
        minimum=60,
        maximum=7 * 24 * 60 * 60,
    )
    while True:
        try:
            await maintain_flow_selections_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            await logger.aexception("Unable to maintain channel workflow selections")
        await asyncio.sleep(interval_seconds)
'''

MIGRATION = '''"""harden channel workflow selection lifecycle

Revision ID: c7e2f4a9b1d3
Revises: a1f4c7e9d2b6
Create Date: 2026-07-30 00:30:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from langflow.utils import migration

revision: str = "c7e2f4a9b1d3"  # pragma: allowlist secret
down_revision: str | None = "a1f4c7e9d2b6"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _indexes(table_name: str, conn) -> set[str]:
    if not migration.table_exists(table_name, conn):
        return set()
    return {index["name"] for index in sa.inspect(conn).get_indexes(table_name)}


def upgrade() -> None:
    conn = op.get_bind()
    table_name = "channel_active_workflow_selection"
    if not migration.table_exists(table_name, conn):
        return
    existing = _indexes(table_name, conn)
    for name, columns in (
        ("ix_channel_active_flow_selection_connection_expires", ["connection_id", "expires_at"]),
        (
            "ix_channel_active_flow_selection_identity_updated",
            ["connection_id", "channel_identity_id", "updated_at"],
        ),
        ("ix_channel_active_flow_selection_command_updated", ["workflow_command_id", "updated_at"]),
    ):
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    table_name = "channel_active_workflow_selection"
    if not migration.table_exists(table_name, conn):
        return
    existing = _indexes(table_name, conn)
    for name in (
        "ix_channel_active_flow_selection_command_updated",
        "ix_channel_active_flow_selection_identity_updated",
        "ix_channel_active_flow_selection_connection_expires",
    ):
        if name in existing:
            op.drop_index(name, table_name=table_name)
'''

FLOW_SELECTION_QUERY = '''import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export interface ChannelActiveWorkflowSelection {
  id: string;
  connection_id: string;
  conversation_binding_id: string;
  channel_identity_id: string;
  conversation_scope_id: string;
  workflow_command_id: string;
  selected_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
  identity_display_name: string | null;
  external_user_id: string | null;
  conversation_display_name: string | null;
  external_conversation_id: string | null;
  conversation_type: string | null;
  command: string | null;
  flow_id: string | null;
  flow_name: string | null;
  flow_endpoint_name: string | null;
  execution_identity_type: "service" | "bound_user" | null;
}

export interface ChannelActiveWorkflowSelectionPage {
  items: ChannelActiveWorkflowSelection[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ChannelActiveWorkflowSelectionQuery {
  connectionId: string;
  page?: number;
  pageSize?: number;
  query?: string;
  conversationBindingId?: string;
  channelIdentityId?: string;
  workflowCommandId?: string;
}

export const useGetChannelFlowSelections: useQueryFunctionType<
  ChannelActiveWorkflowSelectionQuery,
  ChannelActiveWorkflowSelectionPage
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getSelections =
    async (): Promise<ChannelActiveWorkflowSelectionPage> => {
      const response = await api.get<ChannelActiveWorkflowSelectionPage>(
        `${getURL("CHANNELS")}/${params.connectionId}/flow-selections`,
        {
          params: {
            page: params.page ?? 1,
            page_size: params.pageSize ?? 20,
            query: params.query || undefined,
            conversation_binding_id: params.conversationBindingId || undefined,
            channel_identity_id: params.channelIdentityId || undefined,
            workflow_command_id: params.workflowCommandId || undefined,
          },
        },
      );
      return response.data;
    };

  return query(
    [
      "useGetChannelFlowSelections",
      params.connectionId,
      params.page ?? 1,
      params.pageSize ?? 20,
      params.query ?? "",
      params.conversationBindingId ?? "",
      params.channelIdentityId ?? "",
      params.workflowCommandId ?? "",
    ],
    getSelections,
    {
      enabled: Boolean(params.connectionId),
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelActiveWorkflowSelectionPage, Error>;
};
'''

FLOW_SELECTION_PANEL = '''import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Loading from "@/components/ui/loading";
import {
  type ChannelActiveWorkflowSelection,
  useCleanupChannelFlowSelections,
  useDeleteChannelFlowSelection,
  useGetChannelFlowSelections,
} from "@/controllers/API/queries/channels";
import DeleteConfirmationModal from "@/modals/deleteConfirmationModal";
import useAlertStore from "@/stores/alertStore";
import useChannelCopy from "../use-channel-copy";

interface FlowSelectionsPanelProps {
  connectionId: string;
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

export default function FlowSelectionsPanel({
  connectionId,
}: FlowSelectionsPanelProps) {
  const copy = useChannelCopy();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState("");
  const [deleteTarget, setDeleteTarget] =
    useState<ChannelActiveWorkflowSelection | null>(null);

  useEffect(() => {
    setPage(1);
    setSearch("");
    setDeleteTarget(null);
  }, [connectionId]);

  const {
    data: selectionResult,
    isLoading,
    isFetching,
    isError,
    refetch,
  } = useGetChannelFlowSelections(
    { connectionId, page, pageSize, query: search.trim() },
    { enabled: Boolean(connectionId), retry: 1 },
  );

  const deleteSelection = useDeleteChannelFlowSelection();
  const cleanupSelections = useCleanupChannelFlowSelections();

  const showError = (title: string, error: unknown) =>
    setErrorData({
      title,
      list: [error instanceof Error ? error.message : String(error)],
    });

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteSelection.mutateAsync({
        connectionId,
        selectionId: deleteTarget.id,
      });
      setDeleteTarget(null);
      setSuccessData({ title: copy("当前工作流选择已撤销") });
    } catch (error) {
      showError(copy("撤销工作流选择失败"), error);
    }
  };

  const handleCleanup = async () => {
    try {
      const result = await cleanupSelections.mutateAsync({ connectionId });
      setPage(1);
      setSuccessData({
        title: copy("已清理 {{count}} 条过期选择", {
          count: result.removed,
        }),
      });
    } catch (error) {
      showError(copy("清理过期选择失败"), error);
    }
  };

  return (
    <section className="flex flex-col gap-4 border-t pt-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="font-semibold">{copy("活动工作流选择")}</h4>
          <p className="mt-1 text-sm text-muted-foreground">
            {copy(
              "查看成员在私聊、群聊和线程中持续使用的工作流，并按需撤销或清理过期状态。",
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isFetching}
            onClick={() => refetch()}
          >
            {copy("刷新")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            loading={cleanupSelections.isPending}
            onClick={handleCleanup}
          >
            {copy("清理过期选择")}
          </Button>
        </div>
      </div>

      <Input
        value={search}
        placeholder={copy("搜索成员、会话、指令或工作流")}
        onChange={(event) => {
          setSearch(event.target.value);
          setPage(1);
        }}
      />

      {isLoading ? (
        <div className="flex min-h-32 items-center justify-center">
          <Loading />
        </div>
      ) : isError ? (
        <div className="flex min-h-32 flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          <span>{copy("活动工作流选择加载失败")}</span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => refetch()}
          >
            {copy("重新加载")}
          </Button>
        </div>
      ) : (selectionResult?.items.length ?? 0) === 0 ? (
        <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          {copy("当前没有匹配的活动工作流选择。")}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] text-left text-sm">
            <thead className="border-b text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">{copy("成员")}</th>
                <th className="px-3 py-2">{copy("会话 / 线程")}</th>
                <th className="px-3 py-2">{copy("当前工作流")}</th>
                <th className="px-3 py-2">{copy("执行身份")}</th>
                <th className="px-3 py-2">{copy("选择时间")}</th>
                <th className="px-3 py-2">{copy("最近使用")}</th>
                <th className="px-3 py-2">{copy("有效期至")}</th>
                <th className="px-3 py-2 text-right">{copy("操作")}</th>
              </tr>
            </thead>
            <tbody>
              {(selectionResult?.items ?? []).map((selection) => (
                <tr key={selection.id} className="border-b last:border-0">
                  <td className="px-3 py-3">
                    <div className="font-medium">
                      {selection.identity_display_name ||
                        selection.external_user_id ||
                        selection.channel_identity_id.slice(0, 8)}
                    </div>
                    <div className="mt-1 font-mono text-xs text-muted-foreground">
                      {selection.external_user_id ||
                        selection.channel_identity_id.slice(0, 8)}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <div>
                      {selection.conversation_display_name ||
                        selection.external_conversation_id ||
                        selection.conversation_binding_id.slice(0, 8)}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {selection.conversation_type || copy("未知会话")}
                      {selection.conversation_scope_id
                        ? ` · ${copy("线程：{{value}}", {
                            value: selection.conversation_scope_id,
                          })}`
                        : ""}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="font-medium">
                      {selection.flow_name || selection.command || copy("工作流已删除")}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {selection.command || "-"}
                      {selection.flow_endpoint_name
                        ? ` · ${selection.flow_endpoint_name}`
                        : ""}
                    </div>
                  </td>
                  <td className="px-3 py-3 text-xs text-muted-foreground">
                    {selection.execution_identity_type === "bound_user"
                      ? copy("绑定用户")
                      : copy("渠道共享身份")}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">
                    {formatDate(selection.selected_at)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">
                    {formatDate(selection.last_used_at)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">
                    {selection.expires_at
                      ? formatDate(selection.expires_at)
                      : copy("永久")}
                  </td>
                  <td className="px-3 py-3 text-right">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="text-destructive"
                      onClick={() => setDeleteTarget(selection)}
                    >
                      {copy("撤销")}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <div className="text-muted-foreground">
          {copy("共 {{count}} 条活动选择", {
            count: selectionResult?.total ?? 0,
          })}
        </div>
        <div className="flex items-center gap-2">
          <select
            className="primary-input h-9 w-24"
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value));
              setPage(1);
            }}
          >
            {[20, 50, 100].map((size) => (
              <option key={size} value={size}>
                {copy("{{count}} 条", { count: size })}
              </option>
            ))}
          </select>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            {copy("上一页")}
          </Button>
          <span>
            {page} / {Math.max(1, selectionResult?.total_pages ?? 0)}
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={page >= (selectionResult?.total_pages ?? 0)}
            onClick={() => setPage((current) => current + 1)}
          >
            {copy("下一页")}
          </Button>
        </div>
      </div>

      <DeleteConfirmationModal
        open={Boolean(deleteTarget)}
        setOpen={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        description={copy("撤销该成员在当前会话中的持续工作流选择")}
        onConfirm={handleDelete}
      />
    </section>
  );
}
'''

HARDENING_TEST = '''from __future__ import annotations

from types import SimpleNamespace

from langflow.channels.services.dispatch import ChannelDispatchService
from langflow.channels.services.response_policy import ChannelResponseMode


def _group_event(*, mentions=None, text="/help"):
    return SimpleNamespace(
        conversation=SimpleNamespace(conversation_type="group"),
        event_type="message",
        message=SimpleNamespace(mentions=mentions or [], text=text),
    )


def test_group_system_command_can_require_explicit_bot_target() -> None:
    event = _group_event()
    assert ChannelDispatchService._should_ignore_group_event(
        event,
        command="/help",
        response_mode=ChannelResponseMode.MENTION_ONLY.value,
        require_command_mention=True,
        command_targeted=False,
    )
    assert not ChannelDispatchService._should_ignore_group_event(
        event,
        command="/help",
        response_mode=ChannelResponseMode.MENTION_ONLY.value,
        require_command_mention=True,
        command_targeted=True,
    )


def test_telegram_bot_suffix_counts_as_explicit_target() -> None:
    assert ChannelDispatchService._command_targets_bot(_group_event(text="/help@openxflow_bot"))
'''


def apply() -> None:
    write(
        "src/backend/base/langflow/services/database/models/channel/flow_selection_model.py",
        FLOW_SELECTION_MODEL,
    )
    write("src/backend/base/langflow/channels/services/flow_selection.py", FLOW_SELECTION_SERVICE)
    write(
        "src/backend/base/langflow/channels/services/flow_selection_maintenance.py",
        MAINTENANCE_SERVICE,
    )
    write(
        "src/backend/base/langflow/alembic/versions/c7e2f4a9b1d3_harden_channel_flow_selection.py",
        MIGRATION,
    )
    write(
        "src/frontend/src/controllers/API/queries/channels/use-get-channel-flow-selections.ts",
        FLOW_SELECTION_QUERY,
    )
    write(
        "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/FlowSelectionsPanel.tsx",
        FLOW_SELECTION_PANEL,
    )
    write(
        "src/backend/tests/unit/channels/test_channel_flow_selection_hardening.py",
        HARDENING_TEST,
    )

    replace_once(
        "src/backend/base/langflow/channels/services/dispatch.py",
        "from langflow.services.database.models.channel.model import (\n",
        "from langflow.services.database.models.channel.model import (\n",
    )
    replace_once(
        "src/backend/base/langflow/channels/services/dispatch.py",
        "from langflow.services.database.models.knowledge_base.model import KnowledgeBaseRecord\n",
        "from langflow.services.database.models.flow.model import Flow\n"
        "from langflow.services.database.models.knowledge_base.model import KnowledgeBaseRecord\n",
    )
    replace_once(
        "src/backend/base/langflow/channels/services/dispatch.py",
        "        if self._should_ignore_group_event(event, command=command, response_mode=response_mode):\n",
        "        require_system_command_mention = bool(\n"
        "            self.connection.settings_data.get(\"system_command_require_mention\", True)\n"
        "        )\n"
        "        if self._should_ignore_group_event(\n"
        "            event,\n"
        "            command=command,\n"
        "            response_mode=response_mode,\n"
        "            binding=binding,\n"
        "            require_command_mention=system_command is not None and require_system_command_mention,\n"
        "            command_targeted=self._command_targets_bot(event),\n"
        "        ):\n",
    )
    replace_once(
        "src/backend/base/langflow/channels/services/dispatch.py",
        "        if event.conversation.conversation_type != \"private\" and command.require_mention and not event.message.mentions:\n"
        "            return None\n",
        "        if (\n"
        "            event.conversation.conversation_type != \"private\"\n"
        "            and command.require_mention\n"
        "            and not self._command_targets_bot(event)\n"
        "        ):\n"
        "            return None\n",
    )
    replace_once(
        "src/backend/base/langflow/channels/services/dispatch.py",
        "                conversation_scope_id=conversation_scope_id(event),\n"
        "            )\n"
        "            await self.session.commit()\n",
        "                conversation_scope_id=conversation_scope_id(event),\n"
        "                actor_user_id=bound_user.id if bound_user is not None else None,\n"
        "            )\n"
        "            await self.session.commit()\n",
    )

    old_current = '''            if resolution.command is not None and resolution.selection is not None:
                expires = (
                    "永久有效"
                    if resolution.selection.expires_at is None
                    else resolution.selection.expires_at.isoformat()
                )
                return ChannelMessage(
                    title="当前工作流",
                    text=(
                        f"业务指令：{resolution.command.command}\\n"
                        f"工作流 ID：{str(resolution.command.flow_id)[:8]}…\\n"
                        "来源：个人会话选择\\n"
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
    new_current = '''            if resolution.command is not None and resolution.selection is not None:
                flow = await self.session.get(Flow, resolution.command.flow_id)
                if resolution.selection.expires_at is None:
                    expires = "永久有效"
                else:
                    remaining = max(
                        timedelta(0),
                        resolution.selection.expires_at - datetime.now(timezone.utc),
                    )
                    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                    minutes = remainder // 60
                    expires = f"剩余 {hours} 小时 {minutes} 分钟"
                execution_identity = (
                    "绑定用户" if resolution.command.owner_user_id is not None else "渠道共享服务身份"
                )
                conversation_name = event.conversation.title or (binding.display_name if binding else None) or "当前会话"
                flow_name = flow.name if flow is not None else str(resolution.command.flow_id)[:8] + "…"
                endpoint = f"\\nEndpoint：{flow.endpoint_name}" if flow is not None and flow.endpoint_name else ""
                return ChannelMessage(
                    message_type=ChannelMessageType.CARD,
                    title="当前工作流",
                    text=(
                        f"名称：{flow_name}\\n"
                        f"业务指令：{resolution.command.command}\\n"
                        f"执行身份：{execution_identity}\\n"
                        f"作用范围：当前成员 + {conversation_name}\\n"
                        f"有效期：{expires}{endpoint}"
                    ),
                    actions=[
                        ChannelAction(
                            action_id="system:use-flow-default",
                            label="恢复默认",
                            value="/use-flow default",
                        )
                    ],
                )
        default_flow_id = self._resolve_default_flow_id(binding)
        if default_flow_id is None:
            return ChannelMessage(title="当前工作流", text="当前没有个人选择，也没有可用默认工作流。")
        default_flow = await self.session.get(Flow, default_flow_id)
        flow_name = default_flow.name if default_flow is not None else str(default_flow_id)[:8] + "…"
        source = "会话覆盖" if binding is not None and binding.default_flow_id == default_flow_id else "连接默认"
        return ChannelMessage(
            title="当前工作流",
            text=f"名称：{flow_name}\\n来源：{source}\\n执行身份：按当前访问策略动态解析",
        )
'''
    replace_once("src/backend/base/langflow/channels/services/dispatch.py", old_current, new_current)

    old_actions = '''        remaining = max(0, 6 - len(action_items))
        action_items.extend(
            ChannelAction(
                action_id=f"command:{item.normalized_command}",
                label=item.command,
                value=item.command,
            )
            for item in custom_commands[:remaining]
        )
'''
    new_actions = '''        remaining = max(0, 6 - len(action_items))
        selectable_commands = [
            item for item in custom_commands if item.allow_persistent_selection
        ]
        if self.connection.user_flow_selection_enabled:
            action_items.extend(
                ChannelAction(
                    action_id=f"use-flow:{item.normalized_command}",
                    label=f"切换 {item.command}",
                    value=f"/use-flow {item.command}",
                    style="primary" if item.id == current_command_id else "default",
                )
                for item in selectable_commands[:remaining]
            )
        remaining = max(0, 6 - len(action_items))
        action_items.extend(
            ChannelAction(
                action_id=f"command:{item.normalized_command}",
                label=item.command,
                value=item.command,
            )
            for item in custom_commands[:remaining]
        )
'''
    replace_once("src/backend/base/langflow/channels/services/dispatch.py", old_actions, new_actions)

    old_policy = '''    @staticmethod
    def _should_ignore_group_event(
        event: ChannelEvent,
        *,
        command: str | None = None,
        response_mode: str | None = None,
        binding: ChannelConversationBinding | None = None,
    ) -> bool:
        effective_mode = response_mode
        if effective_mode is None and binding is not None:
            effective_mode = binding.response_mode
        return not should_process_channel_event(
            event,
            command=command,
            response_mode=effective_mode,
        )
'''
    new_policy = '''    @staticmethod
    def _command_targets_bot(event: ChannelEvent) -> bool:
        if event.message.mentions:
            return True
        token = (event.message.text or "").strip().partition(" ")[0]
        return token.startswith("/") and "@" in token

    @staticmethod
    def _should_ignore_group_event(
        event: ChannelEvent,
        *,
        command: str | None = None,
        response_mode: str | None = None,
        binding: ChannelConversationBinding | None = None,
        require_command_mention: bool = False,
        command_targeted: bool = False,
    ) -> bool:
        effective_mode = response_mode
        if effective_mode is None and binding is not None:
            effective_mode = binding.response_mode
        if (
            event.conversation.conversation_type != "private"
            and command is not None
            and require_command_mention
            and not command_targeted
        ):
            return True
        return not should_process_channel_event(
            event,
            command=command,
            response_mode=effective_mode,
        )
'''
    replace_once("src/backend/base/langflow/channels/services/dispatch.py", old_policy, new_policy)

    replace_once(
        "src/backend/base/langflow/channels/services/dispatch.py",
        "from datetime import datetime, timezone\n",
        "from datetime import datetime, timedelta, timezone\n",
    )

    replace_once(
        "src/backend/base/langflow/api/v1/channel_management.py",
        "    workflow_command_id: Annotated[UUID | None, Query()] = None,\n",
        "    workflow_command_id: Annotated[UUID | None, Query()] = None,\n"
        "    query: Annotated[str | None, Query(max_length=255)] = None,\n",
    )
    replace_once(
        "src/backend/base/langflow/api/v1/channel_management.py",
        "        workflow_command_id=workflow_command_id,\n"
        "    )\n\n\n@router.delete(\n",
        "        workflow_command_id=workflow_command_id,\n"
        "        query=query,\n"
        "    )\n\n\n@router.delete(\n",
    )
    replace_once(
        "src/backend/base/langflow/api/v1/channel_management.py",
        "        selection_id=selection_id,\n"
        "    ):\n",
        "        selection_id=selection_id,\n"
        "        actor_user_id=current_user.id,\n"
        "        action=\"admin_revoke\",\n"
        "    ):\n",
    )
    replace_once(
        "src/backend/base/langflow/api/v1/channel_management.py",
        "    removed = await cleanup_expired_workflow_selections(db, connection_id=connection_id)\n",
        "    removed = await cleanup_expired_workflow_selections(\n"
        "        db,\n"
        "        connection_id=connection_id,\n"
        "        actor_user_id=current_user.id,\n"
        "        action=\"admin_cleanup_expired\",\n"
        "    )\n",
    )

    replace_once(
        "src/backend/base/langflow/main.py",
        "        models_dev_refresh_task = None\n",
        "        models_dev_refresh_task = None\n        flow_selection_maintenance_task = None\n",
    )
    replace_once(
        "src/backend/base/langflow/main.py",
        "            if not queue_service.is_started():\n                queue_service.start()\n\n            total_time =",
        "            if not queue_service.is_started():\n"
        "                queue_service.start()\n\n"
        "            from langflow.channels.services.flow_selection_maintenance import (\n"
        "                run_flow_selection_maintenance,\n"
        "            )\n\n"
        "            flow_selection_maintenance_task = asyncio.create_task(\n"
        "                run_flow_selection_maintenance(),\n"
        "                name=\"channel-flow-selection-maintenance\",\n"
        "            )\n\n"
        "            total_time =",
    )
    replace_once(
        "src/backend/base/langflow/main.py",
        "                    if models_dev_refresh_task and not models_dev_refresh_task.done():\n"
        "                        models_dev_refresh_task.cancel()\n"
        "                        tasks_to_cancel.append(models_dev_refresh_task)\n",
        "                    if models_dev_refresh_task and not models_dev_refresh_task.done():\n"
        "                        models_dev_refresh_task.cancel()\n"
        "                        tasks_to_cancel.append(models_dev_refresh_task)\n"
        "                    if flow_selection_maintenance_task and not flow_selection_maintenance_task.done():\n"
        "                        flow_selection_maintenance_task.cancel()\n"
        "                        tasks_to_cancel.append(flow_selection_maintenance_task)\n",
    )

    routing_path = "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/DefaultRoutingTab.tsx"
    replace_once(
        routing_path,
        "  flowSelectionTtlHours: string;\n  defaultResponseMode: ChannelResponseMode;\n",
        "  flowSelectionTtlHours: string;\n  systemCommandRequireMention: boolean;\n  defaultResponseMode: ChannelResponseMode;\n",
    )
    replace_once(
        routing_path,
        "          flow_selection_ttl_hours: Math.min(\n"
        "            8760,\n"
        "            Math.max(0, Number(form.flowSelectionTtlHours) || 0),\n"
        "          ),\n"
        "          default_response_mode: form.defaultResponseMode,\n",
        "          flow_selection_ttl_hours: Math.min(\n"
        "            8760,\n"
        "            Math.max(0, Number(form.flowSelectionTtlHours) || 0),\n"
        "          ),\n"
        "          settings_data: {\n"
        "            ...connection.settings_data,\n"
        "            system_command_require_mention:\n"
        "              form.systemCommandRequireMention,\n"
        "          },\n"
        "          default_response_mode: form.defaultResponseMode,\n",
    )
    replace_once(
        routing_path,
        "        {capabilities?.supports_file_upload && (\n",
        "        {capabilities?.supports_group_chat && capabilities.supports_mentions && (\n"
        "          <SettingSwitch\n"
        "            title={copy(\"群聊系统指令必须 @机器人\")}\n"
        "            description={copy(\n"
        "              \"避免群内多个机器人同时响应 /help、/commands 等系统指令；Telegram 的 /command@bot_name 视为已明确指定。\",\n"
        "            )}\n"
        "            checked={form.systemCommandRequireMention}\n"
        "            onCheckedChange={(checked) =>\n"
        "              setForm((current) => ({\n"
        "                ...current,\n"
        "                systemCommandRequireMention: checked,\n"
        "              }))\n"
        "            }\n"
        "          />\n"
        "        )}\n"
        "        {capabilities?.supports_file_upload && (\n",
    )
    replace_once(
        routing_path,
        "    flowSelectionTtlHours: String(connection.flow_selection_ttl_hours),\n"
        "    defaultResponseMode: connection.default_response_mode,\n",
        "    flowSelectionTtlHours: String(connection.flow_selection_ttl_hours),\n"
        "    systemCommandRequireMention:\n"
        "      connection.settings_data.system_command_require_mention !== false,\n"
        "    defaultResponseMode: connection.default_response_mode,\n",
    )

    test_path = "src/backend/tests/unit/channels/test_channel_flow_selection.py"
    replace_once(
        test_path,
        "from langflow.services.database.models.channel.flow_selection_model import ChannelActiveWorkflowSelection\n",
        "from langflow.services.database.models.channel.audit_model import ChannelConfigurationAudit\n"
        "from langflow.services.database.models.channel.flow_selection_model import ChannelActiveWorkflowSelection\n",
    )
    replace_once(
        test_path,
        "        ChannelActiveWorkflowSelection.__table__,\n",
        "        ChannelActiveWorkflowSelection.__table__,\n        ChannelConfigurationAudit.__table__,\n",
    )

    migration_test = "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py"
    content = read(migration_test)
    if "c7e2f4a9b1d3" not in content:
        content = content.replace(
            '"a1f4c7e9d2b6",\n',
            '"a1f4c7e9d2b6",\n        "c7e2f4a9b1d3",\n',
        )
        write(migration_test, content)

    docs_path = "docs/channel-gateway-routing.md"
    docs = read(docs_path)
    marker = "## 持久工作流选择"
    if marker not in docs:
        docs += '''\n\n## 持久工作流选择\n\n- 管理员可开启群聊系统指令必须 `@机器人`，Telegram 的 `/command@bot_name` 视为明确指定。\n- 活动选择接口直接返回成员、会话、指令与工作流展示信息，避免前端额外拼接请求。\n- 过期选择由后台任务按批次自动清理，也可由管理员立即清理。\n- 用户选择、恢复默认、自动失效、管理员撤销和批量清理都会写入渠道配置审计。\n- 活动选择按连接、成员、工作流和过期时间建立组合索引。\n'''
        write(docs_path, docs)


def validate_and_commit() -> None:
    run("uvx", "ruff", "format", "src/backend/base/langflow/channels", "src/backend/base/langflow/services/database/models/channel", "src/backend/tests/unit/channels")
    run("uvx", "ruff", "check", "--fix", "--config", "src/backend/base/langflow/channels/ruff.toml", "src/backend/base/langflow/channels")
    run("uvx", "ruff", "check", "--fix", "--config", "src/backend/tests/unit/channels/ruff.toml", "src/backend/tests/unit/channels")
    run("python", "-m", "compileall", "-q", "src/backend/base/langflow/channels", "src/backend/base/langflow/api/v1/channel_management.py", "src/backend/base/langflow/services/database/models/channel", "src/backend/tests/unit/channels")
    run(
        "uv",
        "run",
        "--frozen",
        "--project",
        "src/backend/base",
        "--group",
        "dev",
        "pytest",
        "-q",
        "--tb=short",
        "--confcutdir=src/backend/tests/unit/channels",
        "src/backend/tests/unit/channels/test_channel_flow_selection.py",
        "src/backend/tests/unit/channels/test_channel_flow_selection_hardening.py",
        "src/backend/tests/unit/channels/test_system_commands.py",
        "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py",
    )
    run("npm", "exec", "--prefix", "src/frontend", "biome", "check", "--", "src/controllers/API/queries/channels/use-get-channel-flow-selections.ts", "src/pages/SettingsPage/pages/ChannelsPage/components/FlowSelectionsPanel.tsx", "src/pages/SettingsPage/pages/ChannelsPage/components/DefaultRoutingTab.tsx")
    run("npm", "exec", "--prefix", "src/frontend", "tsc", "--", "-p", "tsconfig.channels.json", "--noEmit")

    run("git", "checkout", "origin/feature/channel-gateway", "--", "scripts/ci/update_starter_projects.py")
    generator_path = ROOT / ".github/scripts/channel_final_hardening.py"
    generator_path.unlink(missing_ok=True)
    run("git", "add", "-A")
    run("git", "commit", "-m", "feat(channels): harden persistent workflow selection")
    run("git", "push", "origin", f"HEAD:{BRANCH}")


if __name__ == "__main__":
    apply()
    validate_and_commit()
