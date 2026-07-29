from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.rstrip() + "\n", encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:120]!r}")
    write(path, content.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Database models and migration
# ---------------------------------------------------------------------------
replace_once(
    "src/backend/base/langflow/services/database/models/channel/model.py",
    '    flow_selection_ttl_hours: int = Field(default=24, ge=0, le=8760)\n    default_response_mode: str = Field(default="mention_only", max_length=32)',
    "    flow_selection_ttl_hours: int = Field(default=24, ge=0, le=8760)\n"
    "    system_commands_require_mention: bool = Field(default=True)\n"
    '    default_response_mode: str = Field(default="mention_only", max_length=32)',
)
replace_once(
    "src/backend/base/langflow/services/database/models/channel/model.py",
    "    flow_selection_ttl_hours: int | None = Field(default=None, ge=0, le=8760)\n    default_response_mode: str | None = Field(default=None, max_length=32)",
    "    flow_selection_ttl_hours: int | None = Field(default=None, ge=0, le=8760)\n"
    "    system_commands_require_mention: bool | None = None\n"
    "    default_response_mode: str | None = Field(default=None, max_length=32)",
)

write(
    "src/backend/base/langflow/services/database/models/channel/flow_selection_model.py",
    r'''"""Durable per-member active workflow selections for communication channels."""

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


class ChannelActiveWorkflowSelectionPage(SQLModel):
    items: list[ChannelActiveWorkflowSelectionRead]
    page: int
    page_size: int
    total: int
    total_pages: int
''',
)

write(
    "src/backend/base/langflow/alembic/versions/b2c5f8a1d4e7_harden_channel_flow_selections.py",
    r'''"""harden channel workflow selections

Revision ID: b2c5f8a1d4e7
Revises: a1f4c7e9d2b6
Create Date: 2026-07-29 22:40:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from langflow.utils import migration

revision: str = "b2c5f8a1d4e7"  # pragma: allowlist secret
down_revision: str | None = "a1f4c7e9d2b6"  # pragma: allowlist secret
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
    if connection_columns and "system_commands_require_mention" not in connection_columns:
        with op.batch_alter_table("channel_connection", recreate=_recreate_mode(conn)) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "system_commands_require_mention",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.true(),
                )
            )

    if migration.table_exists("channel_active_workflow_selection", conn):
        index_name = "ix_channel_active_flow_selection_connection_expires"
        if index_name not in _indexes("channel_active_workflow_selection", conn):
            op.create_index(
                index_name,
                "channel_active_workflow_selection",
                ["connection_id", "expires_at"],
                unique=False,
            )


def downgrade() -> None:
    conn = op.get_bind()
    if migration.table_exists("channel_active_workflow_selection", conn):
        index_name = "ix_channel_active_flow_selection_connection_expires"
        if index_name in _indexes("channel_active_workflow_selection", conn):
            op.drop_index(index_name, table_name="channel_active_workflow_selection")

    connection_columns = _columns("channel_connection", conn)
    if "system_commands_require_mention" in connection_columns:
        with op.batch_alter_table("channel_connection", recreate=_recreate_mode(conn)) as batch_op:
            batch_op.drop_column("system_commands_require_mention")
''',
)

# ---------------------------------------------------------------------------
# Runtime policy, metrics and maintenance
# ---------------------------------------------------------------------------
write(
    "src/backend/base/langflow/channels/services/response_policy.py",
    r'''"""Provider-neutral channel response mode policy."""

from __future__ import annotations

from enum import Enum

from langflow.channels.domain.models import ChannelEvent, ChannelEventType


class ChannelResponseMode(str, Enum):
    MENTION_ONLY = "mention_only"
    ALL_MESSAGES = "all_messages"
    COMMANDS_ONLY = "commands_only"
    DISABLED = "disabled"


_LEGACY_ALIASES = {
    "mentions_only": ChannelResponseMode.MENTION_ONLY.value,
    "mention": ChannelResponseMode.MENTION_ONLY.value,
}


def normalize_response_mode(value: str | None) -> str:
    normalized = (value or ChannelResponseMode.MENTION_ONLY.value).strip().lower()
    normalized = _LEGACY_ALIASES.get(normalized, normalized)
    allowed = {mode.value for mode in ChannelResponseMode}
    return normalized if normalized in allowed else ChannelResponseMode.MENTION_ONLY.value


def should_process_channel_event(
    event: ChannelEvent,
    *,
    command: str | None,
    response_mode: str | None,
    is_system_command: bool = False,
    system_commands_require_mention: bool = True,
    command_targeted: bool = False,
) -> bool:
    """Apply group response policy consistently to text, files and actions."""
    if event.conversation.conversation_type == "private":
        return True

    mode = normalize_response_mode(response_mode)
    if mode == ChannelResponseMode.DISABLED.value:
        return False
    if event.event_type == ChannelEventType.ACTION:
        return True
    if command is not None:
        if (
            mode == ChannelResponseMode.MENTION_ONLY.value
            and is_system_command
            and system_commands_require_mention
        ):
            return bool(event.message.mentions) or command_targeted
        return True
    if mode == ChannelResponseMode.ALL_MESSAGES.value:
        return True
    if mode == ChannelResponseMode.COMMANDS_ONLY.value:
        return False
    return bool(event.message.mentions)
''',
)

write(
    "src/backend/base/langflow/channels/services/flow_selection_metrics.py",
    r'''"""Process-local metrics for persistent channel workflow selections."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

_FALLBACK_REASONS = (
    "selection_disabled",
    "selection_expired",
    "command_deleted",
    "command_disabled",
    "permission_or_scope_changed",
)


@dataclass(frozen=True)
class FlowSelectionMetricSnapshot:
    selected_total: int
    cleared_total: int
    fallback_total: int
    cleaned_total: int
    maintenance_errors_total: int
    active: int
    fallback_by_reason: dict[str, int]


class FlowSelectionMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._selected_total = 0
            self._cleared_total = 0
            self._cleaned_total = 0
            self._maintenance_errors_total = 0
            self._active = 0
            self._fallback_by_reason = {reason: 0 for reason in _FALLBACK_REASONS}

    def increment(self, field: str, amount: int = 1) -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        with self._lock:
            setattr(self, field, getattr(self, field) + amount)

    def record_fallback(self, reason: str) -> None:
        with self._lock:
            self._fallback_by_reason.setdefault(reason, 0)
            self._fallback_by_reason[reason] += 1

    def set_active(self, value: int) -> None:
        if value < 0:
            raise ValueError("active selections must be non-negative")
        with self._lock:
            self._active = value

    def snapshot(self) -> FlowSelectionMetricSnapshot:
        with self._lock:
            reasons = dict(self._fallback_by_reason)
            return FlowSelectionMetricSnapshot(
                selected_total=self._selected_total,
                cleared_total=self._cleared_total,
                fallback_total=sum(reasons.values()),
                cleaned_total=self._cleaned_total,
                maintenance_errors_total=self._maintenance_errors_total,
                active=self._active,
                fallback_by_reason=reasons,
            )


_metrics = FlowSelectionMetrics()


def flow_selection_metrics_snapshot() -> FlowSelectionMetricSnapshot:
    return _metrics.snapshot()


def reset_flow_selection_metrics_for_testing() -> None:
    _metrics.reset()


def record_flow_selection_selected() -> None:
    _metrics.increment("_selected_total")


def record_flow_selection_cleared() -> None:
    _metrics.increment("_cleared_total")


def record_flow_selection_fallback(reason: str) -> None:
    _metrics.record_fallback(reason)


def record_flow_selection_cleaned(amount: int) -> None:
    _metrics.increment("_cleaned_total", amount)


def record_flow_selection_maintenance_error() -> None:
    _metrics.increment("_maintenance_errors_total")


def set_active_flow_selection_count(value: int) -> None:
    _metrics.set_active(value)


class FlowSelectionMetricsCollector:
    """Expose workflow-selection outcomes through Prometheus."""

    def collect(self):  # type: ignore[no-untyped-def]
        snapshot = flow_selection_metrics_snapshot()
        for name, description, value in (
            (
                "openxflow_channel_flow_selection_selected",
                "Persistent channel workflow selections created or replaced by this process",
                snapshot.selected_total,
            ),
            (
                "openxflow_channel_flow_selection_cleared",
                "Persistent channel workflow selections explicitly cleared by this process",
                snapshot.cleared_total,
            ),
            (
                "openxflow_channel_flow_selection_cleaned",
                "Expired persistent channel workflow selections removed by maintenance",
                snapshot.cleaned_total,
            ),
            (
                "openxflow_channel_flow_selection_maintenance_errors",
                "Persistent channel workflow selection maintenance errors",
                snapshot.maintenance_errors_total,
            ),
        ):
            metric = CounterMetricFamily(name, description)
            metric.add_metric([], value)
            yield metric

        fallback = CounterMetricFamily(
            "openxflow_channel_flow_selection_fallback",
            "Persistent channel workflow selections invalidated at execution time",
            labels=["reason"],
        )
        for reason, value in sorted(snapshot.fallback_by_reason.items()):
            fallback.add_metric([reason], value)
        yield fallback

        active = GaugeMetricFamily(
            "openxflow_channel_flow_selection_active",
            "Current persistent channel workflow selections in the shared database",
        )
        active.add_metric([], snapshot.active)
        yield active
''',
)

write(
    "src/backend/base/langflow/channels/services/flow_selection_maintenance.py",
    r'''"""Background lifecycle maintenance for persistent workflow selections."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass

from lfx.log.logger import logger

from langflow.channels.services.flow_selection import (
    cleanup_expired_workflow_selections,
    count_active_workflow_selections,
)
from langflow.channels.services.flow_selection_metrics import (
    record_flow_selection_maintenance_error,
    set_active_flow_selection_count,
)
from langflow.services.deps import session_scope


@dataclass(frozen=True, slots=True)
class FlowSelectionMaintenanceConfig:
    enabled: bool
    interval_seconds: float
    batch_size: int


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def flow_selection_maintenance_config() -> FlowSelectionMaintenanceConfig:
    interval = max(30.0, float(os.getenv("LANGFLOW_CHANNEL_FLOW_SELECTION_CLEANUP_INTERVAL_SECONDS", "300")))
    batch_size = min(5000, max(1, int(os.getenv("LANGFLOW_CHANNEL_FLOW_SELECTION_CLEANUP_BATCH_SIZE", "500"))))
    return FlowSelectionMaintenanceConfig(
        enabled=_env_bool("LANGFLOW_CHANNEL_FLOW_SELECTION_MAINTENANCE_ENABLED", True),
        interval_seconds=interval,
        batch_size=batch_size,
    )


async def maintain_flow_selections_once() -> int:
    config = flow_selection_maintenance_config()
    async with session_scope() as session:
        removed = await cleanup_expired_workflow_selections(
            session,
            connection_id=None,
            batch_size=config.batch_size,
        )
        active = await count_active_workflow_selections(session)
    set_active_flow_selection_count(active)
    return removed


async def _run_flow_selection_maintenance(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        config = flow_selection_maintenance_config()
        try:
            await maintain_flow_selections_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            record_flow_selection_maintenance_error()
            await logger.aexception("Unable to maintain persistent channel workflow selections")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=config.interval_seconds)
        except TimeoutError:
            pass


@asynccontextmanager
async def flow_selection_maintenance_lifespan(_app):  # type: ignore[no-untyped-def]
    config = flow_selection_maintenance_config()
    if not config.enabled:
        yield
        return
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        _run_flow_selection_maintenance(stop_event),
        name="channel-flow-selection-maintenance",
    )
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
''',
)

write(
    "src/backend/base/langflow/channels/services/flow_selection.py",
    r'''"""Resolve and maintain durable per-member active workflow selections."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.services.commands import resolve_workflow_command
from langflow.channels.services.flow_selection_metrics import (
    record_flow_selection_cleaned,
    record_flow_selection_cleared,
    record_flow_selection_fallback,
    record_flow_selection_selected,
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
    record_flow_selection_selected()
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
    record_flow_selection_cleared()
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
        record_flow_selection_fallback(invalid_reason)
        return ActiveWorkflowResolution(invalid_reason=invalid_reason)

    if touch:
        selection.last_used_at = now
        selection.updated_at = now
        session.add(selection)
        await session.flush()
    return ActiveWorkflowResolution(selection=selection, command=command)


def _selection_join(statement):  # type: ignore[no-untyped-def]
    return (
        statement.join(ChannelIdentity, ChannelIdentity.id == ChannelActiveWorkflowSelection.channel_identity_id)
        .join(
            ChannelConversationBinding,
            ChannelConversationBinding.id == ChannelActiveWorkflowSelection.conversation_binding_id,
        )
        .join(
            ChannelWorkflowCommand,
            ChannelWorkflowCommand.id == ChannelActiveWorkflowSelection.workflow_command_id,
        )
        .join(Flow, Flow.id == ChannelWorkflowCommand.flow_id, isouter=True)
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
    expires_before: datetime | None = None,
    permanent_only: bool = False,
) -> ChannelActiveWorkflowSelectionPage:
    normalized_page = max(1, page)
    normalized_page_size = min(100, max(1, page_size))
    filters: list[object] = [ChannelActiveWorkflowSelection.connection_id == connection_id]
    if conversation_binding_id is not None:
        filters.append(ChannelActiveWorkflowSelection.conversation_binding_id == conversation_binding_id)
    if channel_identity_id is not None:
        filters.append(ChannelActiveWorkflowSelection.channel_identity_id == channel_identity_id)
    if workflow_command_id is not None:
        filters.append(ChannelActiveWorkflowSelection.workflow_command_id == workflow_command_id)
    if expires_before is not None:
        filters.extend(
            [
                ChannelActiveWorkflowSelection.expires_at.is_not(None),
                ChannelActiveWorkflowSelection.expires_at <= expires_before,
            ]
        )
    if permanent_only:
        filters.append(ChannelActiveWorkflowSelection.expires_at.is_(None))
    normalized_query = (query or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        filters.append(
            sa.or_(
                ChannelIdentity.display_name.ilike(pattern),
                ChannelIdentity.external_user_id.ilike(pattern),
                ChannelConversationBinding.display_name.ilike(pattern),
                ChannelConversationBinding.external_conversation_id.ilike(pattern),
                ChannelWorkflowCommand.command.ilike(pattern),
                Flow.name.ilike(pattern),
                Flow.endpoint_name.ilike(pattern),
            )
        )

    count_statement = _selection_join(
        select(func.count(ChannelActiveWorkflowSelection.id)).select_from(ChannelActiveWorkflowSelection)
    ).where(*filters)
    total = int((await session.exec(count_statement)).one())

    statement = _selection_join(
        select(
            ChannelActiveWorkflowSelection,
            ChannelIdentity.display_name,
            ChannelIdentity.external_user_id,
            ChannelConversationBinding.display_name,
            ChannelConversationBinding.external_conversation_id,
            ChannelConversationBinding.conversation_type,
            ChannelWorkflowCommand.command,
            ChannelWorkflowCommand.flow_id,
            Flow.name,
            Flow.endpoint_name,
        )
    )
    rows = (
        await session.exec(
            statement.where(*filters)
            .order_by(ChannelActiveWorkflowSelection.updated_at.desc(), ChannelActiveWorkflowSelection.id)
            .offset((normalized_page - 1) * normalized_page_size)
            .limit(normalized_page_size)
        )
    ).all()

    items: list[ChannelActiveWorkflowSelectionRead] = []
    for row in rows:
        (
            selection,
            identity_display_name,
            external_user_id,
            conversation_display_name,
            external_conversation_id,
            conversation_type,
            command,
            flow_id,
            flow_name,
            flow_endpoint_name,
        ) = row
        items.append(
            ChannelActiveWorkflowSelectionRead.model_validate(selection, from_attributes=True).model_copy(
                update={
                    "identity_display_name": identity_display_name,
                    "external_user_id": external_user_id,
                    "conversation_display_name": conversation_display_name,
                    "external_conversation_id": external_conversation_id,
                    "conversation_type": conversation_type,
                    "command": command,
                    "flow_id": flow_id,
                    "flow_name": flow_name,
                    "flow_endpoint_name": flow_endpoint_name,
                }
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
) -> bool:
    selection = await session.get(ChannelActiveWorkflowSelection, selection_id)
    if selection is None or selection.connection_id != connection_id:
        return False
    await session.delete(selection)
    await session.flush()
    record_flow_selection_cleared()
    return True


async def cleanup_expired_workflow_selections(
    session: AsyncSession,
    *,
    connection_id: UUID | None,
    batch_size: int = 500,
) -> int:
    now = _utc_now()
    filters: list[object] = [
        ChannelActiveWorkflowSelection.expires_at.is_not(None),
        ChannelActiveWorkflowSelection.expires_at <= now,
    ]
    if connection_id is not None:
        filters.append(ChannelActiveWorkflowSelection.connection_id == connection_id)
    rows = (
        await session.exec(
            select(ChannelActiveWorkflowSelection)
            .where(*filters)
            .order_by(ChannelActiveWorkflowSelection.expires_at, ChannelActiveWorkflowSelection.id)
            .limit(min(5000, max(1, batch_size)))
        )
    ).all()
    for row in rows:
        await session.delete(row)
    if rows:
        await session.flush()
        record_flow_selection_cleaned(len(rows))
    return len(rows)


async def count_active_workflow_selections(session: AsyncSession) -> int:
    return int((await session.exec(select(func.count()).select_from(ChannelActiveWorkflowSelection))).one())
''',
)

# ---------------------------------------------------------------------------
# Backend API and dispatch integration
# ---------------------------------------------------------------------------
replace_once(
    "src/backend/base/langflow/api/v1/channel_webhooks.py",
    "from langflow.channels.services.outbound_delivery_maintenance import (\n    outbound_delivery_maintenance_lifespan,\n)\n",
    "from langflow.channels.services.flow_selection_maintenance import flow_selection_maintenance_lifespan\n"
    "from langflow.channels.services.outbound_delivery_maintenance import (\n    outbound_delivery_maintenance_lifespan,\n)\n",
)
replace_once(
    "src/backend/base/langflow/api/v1/channel_webhooks.py",
    "            await stack.enter_async_context(outbound_delivery_maintenance_lifespan(app))\n            yield",
    "            await stack.enter_async_context(outbound_delivery_maintenance_lifespan(app))\n"
    "            await stack.enter_async_context(flow_selection_maintenance_lifespan(app))\n"
    "            yield",
)

replace_once(
    "src/backend/base/langflow/api/v1/channel_management.py",
    "from langflow.services.database.models.channel.flow_selection_model import (\n    ChannelActiveWorkflowSelectionPage,\n)",
    "from langflow.services.database.models.channel.flow_selection_model import (\n"
    "    ChannelActiveWorkflowSelection,\n"
    "    ChannelActiveWorkflowSelectionPage,\n"
    ")",
)
replace_once(
    "src/backend/base/langflow/api/v1/channel_management.py",
    "    workflow_command_id: Annotated[UUID | None, Query()] = None,\n) -> ChannelActiveWorkflowSelectionPage:",
    "    workflow_command_id: Annotated[UUID | None, Query()] = None,\n"
    "    query: Annotated[str | None, Query(max_length=255)] = None,\n"
    "    expires_before: Annotated[datetime | None, Query()] = None,\n"
    "    permanent_only: Annotated[bool, Query()] = False,\n"
    ") -> ChannelActiveWorkflowSelectionPage:",
)
replace_once(
    "src/backend/base/langflow/api/v1/channel_management.py",
    '        workflow_command_id=workflow_command_id,\n    )\n\n\n@router.delete(\n    "/{connection_id}/flow-selections/{selection_id}"',
    "        workflow_command_id=workflow_command_id,\n"
    "        query=query,\n"
    "        expires_before=expires_before,\n"
    "        permanent_only=permanent_only,\n"
    '    )\n\n\n@router.delete(\n    "/{connection_id}/flow-selections/{selection_id}"',
)
replace_once(
    "src/backend/base/langflow/api/v1/channel_management.py",
    '    await _administrable_connection_or_404(db, current_user, connection_id, ChannelAction.WRITE)\n    if not await delete_active_workflow_selection(\n        db,\n        connection_id=connection_id,\n        selection_id=selection_id,\n    ):\n        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active workflow selection not found")\n    await db.commit()',
    "    await _administrable_connection_or_404(db, current_user, connection_id, ChannelAction.WRITE)\n"
    "    selection = await db.get(ChannelActiveWorkflowSelection, selection_id)\n"
    "    if selection is None or selection.connection_id != connection_id:\n"
    '        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active workflow selection not found")\n'
    "    before = channel_resource_snapshot(selection)\n"
    "    await delete_active_workflow_selection(\n"
    "        db,\n"
    "        connection_id=connection_id,\n"
    "        selection_id=selection_id,\n"
    "    )\n"
    "    await record_channel_configuration_audit(\n"
    "        db,\n"
    "        connection_id=connection_id,\n"
    "        actor_user_id=current_user.id,\n"
    '        action="revoke",\n'
    '        resource_type="flow_selection",\n'
    "        resource_id=selection_id,\n"
    "        before=before,\n"
    '        after={"reason": "administrator_revoked"},\n'
    "    )\n"
    "    await db.commit()",
)
replace_once(
    "src/backend/base/langflow/api/v1/channel_management.py",
    'async def cleanup_channel_flow_selections(\n    connection_id: UUID,\n    db: DbSession,\n    current_user: CurrentActiveUser,\n) -> dict[str, int]:\n    await _administrable_connection_or_404(db, current_user, connection_id, ChannelAction.WRITE)\n    removed = await cleanup_expired_workflow_selections(db, connection_id=connection_id)\n    await db.commit()\n    return {"removed": removed}',
    "async def cleanup_channel_flow_selections(\n"
    "    connection_id: UUID,\n"
    "    db: DbSession,\n"
    "    current_user: CurrentActiveUser,\n"
    "    batch_size: Annotated[int, Query(ge=1, le=5000)] = 500,\n"
    ") -> dict[str, int]:\n"
    "    await _administrable_connection_or_404(db, current_user, connection_id, ChannelAction.WRITE)\n"
    "    removed = await cleanup_expired_workflow_selections(\n"
    "        db,\n"
    "        connection_id=connection_id,\n"
    "        batch_size=batch_size,\n"
    "    )\n"
    "    await record_channel_configuration_audit(\n"
    "        db,\n"
    "        connection_id=connection_id,\n"
    "        actor_user_id=current_user.id,\n"
    '        action="cleanup",\n'
    '        resource_type="flow_selection",\n'
    "        resource_id=None,\n"
    '        after={"removed": removed, "batch_size": batch_size},\n'
    "    )\n"
    "    await db.commit()\n"
    '    return {"removed": removed, "batch_size": batch_size}',
)

# Runtime metrics endpoint
replace_once(
    "src/backend/base/langflow/api/v1/channel_runtime.py",
    "from langflow.channels.services.metrics import ChannelMetricsCollector\n",
    "from langflow.channels.services.flow_selection_maintenance import flow_selection_maintenance_config\n"
    "from langflow.channels.services.flow_selection_metrics import (\n"
    "    FlowSelectionMetricsCollector,\n"
    "    flow_selection_metrics_snapshot,\n"
    ")\n"
    "from langflow.channels.services.metrics import ChannelMetricsCollector\n",
)
replace_once(
    "src/backend/base/langflow/api/v1/channel_runtime.py",
    "class ChannelOutboundRetryRuntimeRead(BaseModel):",
    "class ChannelFlowSelectionRuntimeRead(BaseModel):\n"
    "    maintenance_enabled: bool\n"
    "    cleanup_interval_seconds: float\n"
    "    cleanup_batch_size: int\n"
    "    selected_total: int\n"
    "    cleared_total: int\n"
    "    fallback_total: int\n"
    "    cleaned_total: int\n"
    "    maintenance_errors_total: int\n"
    "    active: int\n"
    "    fallback_by_reason: dict[str, int]\n\n\n"
    "class ChannelOutboundRetryRuntimeRead(BaseModel):",
)
replace_once(
    "src/backend/base/langflow/api/v1/channel_runtime.py",
    "    outbound_delivery: OutboundDeliveryRuntimeRead\n    outbound_retry: ChannelOutboundRetryRuntimeRead",
    "    outbound_delivery: OutboundDeliveryRuntimeRead\n"
    "    flow_selections: ChannelFlowSelectionRuntimeRead\n"
    "    outbound_retry: ChannelOutboundRetryRuntimeRead",
)
replace_once(
    "src/backend/base/langflow/api/v1/channel_runtime.py",
    "    outbound_delivery = outbound_delivery_metrics_snapshot()\n    retry_policy = channel_retry_policy_from_env()",
    "    outbound_delivery = outbound_delivery_metrics_snapshot()\n"
    "    flow_selection_config = flow_selection_maintenance_config()\n"
    "    flow_selection_runtime = flow_selection_metrics_snapshot()\n"
    "    retry_policy = channel_retry_policy_from_env()",
)
replace_once(
    "src/backend/base/langflow/api/v1/channel_runtime.py",
    "        outbound_delivery=OutboundDeliveryRuntimeRead(**outbound_delivery_data),\n        outbound_retry=ChannelOutboundRetryRuntimeRead(",
    "        outbound_delivery=OutboundDeliveryRuntimeRead(**outbound_delivery_data),\n"
    "        flow_selections=ChannelFlowSelectionRuntimeRead(\n"
    "            maintenance_enabled=flow_selection_config.enabled,\n"
    "            cleanup_interval_seconds=flow_selection_config.interval_seconds,\n"
    "            cleanup_batch_size=flow_selection_config.batch_size,\n"
    "            **asdict(flow_selection_runtime),\n"
    "        ),\n"
    "        outbound_retry=ChannelOutboundRetryRuntimeRead(",
)
replace_once(
    "src/backend/base/langflow/api/v1/channel_runtime.py",
    "    registry.register(OutboundDeliveryMetricsCollector())\n    registry.register(TokenCacheMetricsCollector())",
    "    registry.register(OutboundDeliveryMetricsCollector())\n"
    "    registry.register(FlowSelectionMetricsCollector())\n"
    "    registry.register(TokenCacheMetricsCollector())",
)

# Dispatch imports and routing policy
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    "from langflow.channels.services.context import prepare_channel_input, record_channel_response\n",
    "from langflow.channels.services.configuration_audit import record_channel_configuration_audit\n"
    "from langflow.channels.services.context import prepare_channel_input, record_channel_response\n",
)
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    "    clear_active_workflow_selection,\n    resolve_active_workflow_selection,",
    "    clear_active_workflow_selection,\n    get_active_workflow_selection,\n    resolve_active_workflow_selection,",
)
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    "from langflow.services.database.models.knowledge_base.model import KnowledgeBaseRecord\n",
    "from langflow.services.database.models.flow.model import Flow\n"
    "from langflow.services.database.models.knowledge_base.model import KnowledgeBaseRecord\n",
)
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    "        raw_command, argument = self._parse_command(event.message.text)\n        system_command = resolve_system_command(raw_command)",
    "        raw_command, argument = self._parse_command(event.message.text)\n"
    "        command_targeted = self._command_has_explicit_target(event.message.text)\n"
    "        system_command = resolve_system_command(raw_command)",
)
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    "        if self._should_ignore_group_event(event, command=command, response_mode=response_mode):",
    "        if self._should_ignore_group_event(\n"
    "            event,\n"
    "            command=command,\n"
    "            response_mode=response_mode,\n"
    "            is_system_command=system_command is not None,\n"
    "            system_commands_require_mention=self.connection.system_commands_require_mention,\n"
    "            command_targeted=command_targeted,\n"
    "        ):",
)
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    '        if event.conversation.conversation_type != "private" and command.require_mention and not event.message.mentions:\n            return None',
    "        if (\n"
    '            event.conversation.conversation_type != "private"\n'
    "            and command.require_mention\n"
    "            and not event.message.mentions\n"
    "            and not self._command_has_explicit_target(event.message.text)\n"
    "        ):\n"
    "            return None",
)
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    '        if requested.lower() in {"default", "/default", "默认"}:\n            cleared = await clear_active_workflow_selection(',
    '        if requested.lower() in {"default", "/default", "默认"}:\n'
    "            scope_id = conversation_scope_id(event)\n"
    "            previous_selection = await get_active_workflow_selection(\n"
    "                self.session,\n"
    "                connection_id=self.connection.id,\n"
    "                conversation_binding_id=binding.id,\n"
    "                channel_identity_id=identity.id,\n"
    "                conversation_scope_id=scope_id,\n"
    "            )\n"
    "            cleared = await clear_active_workflow_selection(",
)
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    "                conversation_scope_id=conversation_scope_id(event),\n            )\n            await self.session.commit()\n            default_flow_id = self._resolve_default_flow_id(binding)",
    "                conversation_scope_id=scope_id,\n"
    "            )\n"
    "            if cleared and previous_selection is not None:\n"
    "                await record_channel_configuration_audit(\n"
    "                    self.session,\n"
    "                    connection_id=self.connection.id,\n"
    "                    actor_user_id=bound_user.id if bound_user is not None else None,\n"
    '                    action="clear",\n'
    '                    resource_type="flow_selection",\n'
    "                    resource_id=previous_selection.id,\n"
    "                    before=previous_selection,\n"
    '                    after={"reason": "user_restored_default", "channel_identity_id": identity.id},\n'
    "                )\n"
    "            await self.session.commit()\n"
    "            default_flow_id = self._resolve_default_flow_id(binding)",
)
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    '        await self.session.commit()\n        expires = (\n            "永久有效" if selection.expires_at is None else f"有效期 {self.connection.flow_selection_ttl_hours} 小时"\n        )',
    "        await record_channel_configuration_audit(\n"
    "            self.session,\n"
    "            connection_id=self.connection.id,\n"
    "            actor_user_id=bound_user.id if bound_user is not None else None,\n"
    '            action="select",\n'
    '            resource_type="flow_selection",\n'
    "            resource_id=selection.id,\n"
    "            after={\n"
    '                "selection": selection,\n'
    '                "command": command.command,\n'
    '                "flow_id": command.flow_id,\n'
    '                "channel_identity_id": identity.id,\n'
    "            },\n"
    "        )\n"
    "        await self.session.commit()\n"
    "        flow = await self.session.get(Flow, command.flow_id)\n"
    '        flow_label = flow.name if flow is not None else f"{str(command.flow_id)[:8]}…"\n'
    "        expires = (\n"
    '            "永久有效" if selection.expires_at is None else f"有效期 {self.connection.flow_selection_ttl_hours} 小时"\n'
    "        )",
)
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    '                f"当前工作流：{command.command}\\n"',
    '                f"当前工作流：{flow_label}（{command.command}）\\n"',
)

old_current_flow = """        if binding is not None:\n            resolution = await resolve_active_workflow_selection(\n                self.session,\n                connection=self.connection,\n                binding=binding,\n                identity=identity,\n                conversation_scope_id=conversation_scope_id(event),\n                user_id=personal_user_id,\n                touch=False,\n            )\n            if resolution.command is not None and resolution.selection is not None:\n                expires = (\n                    \"永久有效\"\n                    if resolution.selection.expires_at is None\n                    else resolution.selection.expires_at.isoformat()\n                )\n                return ChannelMessage(\n                    title=\"当前工作流\",\n                    text=(\n                        f\"业务指令：{resolution.command.command}\\n\"\n                        f\"工作流 ID：{str(resolution.command.flow_id)[:8]}…\\n\"\n                        \"来源：个人会话选择\\n\"\n                        f\"有效期至：{expires}\"\n                    ),\n                )\n        default_flow_id = self._resolve_default_flow_id(binding)\n        if default_flow_id is None:\n            return ChannelMessage(title=\"当前工作流\", text=\"当前没有个人选择，也没有可用默认工作流。\")\n        return ChannelMessage(\n            title=\"当前工作流\",\n            text=f\"当前使用会话或连接默认工作流：{str(default_flow_id)[:8]}…\",\n        )"""
new_current_flow = """        if binding is not None:\n            resolution = await resolve_active_workflow_selection(\n                self.session,\n                connection=self.connection,\n                binding=binding,\n                identity=identity,\n                conversation_scope_id=conversation_scope_id(event),\n                user_id=personal_user_id,\n                touch=False,\n            )\n            if resolution.command is not None and resolution.selection is not None:\n                flow = await self.session.get(Flow, resolution.command.flow_id)\n                flow_name = flow.name if flow is not None else f\"{str(resolution.command.flow_id)[:8]}…\"\n                endpoint = f\"\\nEndpoint：{flow.endpoint_name}\" if flow is not None and flow.endpoint_name else \"\"\n                if resolution.selection.expires_at is None:\n                    expires = \"永久有效\"\n                else:\n                    remaining = max(0, int((resolution.selection.expires_at - datetime.now(timezone.utc)).total_seconds()))\n                    if remaining < 3600:\n                        expires = f\"约 {max(1, remaining // 60)} 分钟后到期\"\n                    else:\n                        expires = f\"约 {remaining // 3600} 小时后到期\"\n                execution_identity = (\n                    \"绑定 OpenXFlow 账号\"\n                    if resolution.command.owner_user_id is not None\n                    else \"渠道共享服务身份\"\n                )\n                scope = \"当前私聊\" if event.conversation.conversation_type == \"private\" else \"当前成员 + 当前群聊\"\n                if conversation_scope_id(event):\n                    scope += \" + 当前线程/主题\"\n                return ChannelMessage(\n                    title=\"当前工作流\",\n                    text=(\n                        f\"工作流：{flow_name}\\n\"\n                        f\"业务指令：{resolution.command.command}{endpoint}\\n\"\n                        f\"执行身份：{execution_identity}\\n\"\n                        f\"作用范围：{scope}\\n\"\n                        f\"有效期：{expires}\"\n                    ),\n                )\n        default_flow_id = self._resolve_default_flow_id(binding)\n        if default_flow_id is None:\n            return ChannelMessage(title=\"当前工作流\", text=\"当前没有个人选择，也没有可用默认工作流。\")\n        flow = await self.session.get(Flow, default_flow_id)\n        flow_name = flow.name if flow is not None else f\"{str(default_flow_id)[:8]}…\"\n        source = (\n            \"当前会话覆盖\"\n            if binding is not None\n            and binding.route_mode == ChannelConversationRouteMode.OVERRIDE.value\n            and binding.default_flow_id is not None\n            else \"渠道连接默认\"\n        )\n        endpoint = f\"\\nEndpoint：{flow.endpoint_name}\" if flow is not None and flow.endpoint_name else \"\"\n        return ChannelMessage(\n            title=\"当前工作流\",\n            text=f\"工作流：{flow_name}{endpoint}\\n来源：{source}\",\n        )"""
replace_once("src/backend/base/langflow/channels/services/dispatch.py", old_current_flow, new_current_flow)

replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    "    @staticmethod\n    def _should_ignore_group_event(\n        event: ChannelEvent,\n        *,\n        command: str | None = None,\n        response_mode: str | None = None,\n        binding: ChannelConversationBinding | None = None,\n    ) -> bool:",
    "    @staticmethod\n"
    "    def _should_ignore_group_event(\n"
    "        event: ChannelEvent,\n"
    "        *,\n"
    "        command: str | None = None,\n"
    "        response_mode: str | None = None,\n"
    "        binding: ChannelConversationBinding | None = None,\n"
    "        is_system_command: bool = False,\n"
    "        system_commands_require_mention: bool = True,\n"
    "        command_targeted: bool = False,\n"
    "    ) -> bool:",
)
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    "            command=command,\n            response_mode=effective_mode,\n        )",
    "            command=command,\n"
    "            response_mode=effective_mode,\n"
    "            is_system_command=is_system_command,\n"
    "            system_commands_require_mention=system_commands_require_mention,\n"
    "            command_targeted=command_targeted,\n"
    "        )",
)
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    "    @staticmethod\n    def _parse_command(text: str | None) -> tuple[str | None, str]:",
    "    @staticmethod\n"
    "    def _command_has_explicit_target(text: str | None) -> bool:\n"
    '        normalized = (text or "").strip()\n'
    '        if not normalized.startswith("/"):\n'
    "            return False\n"
    '        token = normalized.partition(" ")[0]\n'
    '        return "@" in token and bool(token.split("@", 1)[1])\n\n'
    "    @staticmethod\n"
    "    def _parse_command(text: str | None) -> tuple[str | None, str]:",
)
replace_once(
    "src/backend/base/langflow/channels/services/dispatch.py",
    "                f\"默认工作流：{'已配置' if flow_id is not None else '未配置'}\"",
    "                f\"默认工作流：{'已配置' if flow_id is not None else '未配置'}\\n\"\n"
    "                f\"群聊系统指令需@：{'是' if self.connection.system_commands_require_mention else '否'}\"",
)

# ---------------------------------------------------------------------------
# Frontend API and management UI
# ---------------------------------------------------------------------------
for old, new in (
    (
        "  flow_selection_ttl_hours: number;\n  default_response_mode: ChannelResponseMode;",
        "  flow_selection_ttl_hours: number;\n  system_commands_require_mention: boolean;\n  default_response_mode: ChannelResponseMode;",
    ),
    (
        "  flow_selection_ttl_hours?: number;\n  default_response_mode?: ChannelResponseMode;",
        "  flow_selection_ttl_hours?: number;\n  system_commands_require_mention?: boolean;\n  default_response_mode?: ChannelResponseMode;",
    ),
):
    replace_once("src/frontend/src/controllers/API/queries/channels/types.ts", old, new)

write(
    "src/frontend/src/controllers/API/queries/channels/use-get-channel-flow-selections.ts",
    r"""import type { UseQueryResult } from "@tanstack/react-query";
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
  conversationBindingId?: string;
  channelIdentityId?: string;
  workflowCommandId?: string;
  query?: string;
  expiresBefore?: string;
  permanentOnly?: boolean;
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
            conversation_binding_id: params.conversationBindingId || undefined,
            channel_identity_id: params.channelIdentityId || undefined,
            workflow_command_id: params.workflowCommandId || undefined,
            query: params.query || undefined,
            expires_before: params.expiresBefore || undefined,
            permanent_only: params.permanentOnly || undefined,
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
      params.conversationBindingId ?? "",
      params.channelIdentityId ?? "",
      params.workflowCommandId ?? "",
      params.query ?? "",
      params.expiresBefore ?? "",
      params.permanentOnly ?? false,
    ],
    getSelections,
    {
      enabled: Boolean(params.connectionId),
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelActiveWorkflowSelectionPage, Error>;
};
""",
)

write(
    "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/FlowSelectionsPanel.tsx",
    r"""import { useEffect, useMemo, useState } from "react";
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

type ExpirationFilter = "all" | "expiring" | "permanent";

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
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [expirationFilter, setExpirationFilter] =
    useState<ExpirationFilter>("all");
  const [deleteTarget, setDeleteTarget] =
    useState<ChannelActiveWorkflowSelection | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(queryInput.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [queryInput]);

  useEffect(() => {
    setPage(1);
    setDeleteTarget(null);
  }, [connectionId]);

  const expiresBefore = useMemo(
    () =>
      expirationFilter === "expiring"
        ? new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
        : undefined,
    [expirationFilter],
  );

  const {
    data: selectionResult,
    isLoading,
    isFetching,
    isError,
    refetch,
  } = useGetChannelFlowSelections(
    {
      connectionId,
      page,
      pageSize,
      query,
      expiresBefore,
      permanentOnly: expirationFilter === "permanent" || undefined,
    },
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

      <div className="grid gap-3 md:grid-cols-2">
        <Input
          value={queryInput}
          onChange={(event) => setQueryInput(event.target.value)}
          placeholder={copy("搜索成员、会话、指令或工作流")}
        />
        <select
          className="primary-input h-10"
          value={expirationFilter}
          onChange={(event) => {
            setExpirationFilter(event.target.value as ExpirationFilter);
            setPage(1);
          }}
        >
          <option value="all">{copy("全部有效期")}</option>
          <option value="expiring">{copy("24 小时内到期")}</option>
          <option value="permanent">{copy("永久有效")}</option>
        </select>
      </div>

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
          {copy("当前没有匹配的持续工作流选择。")}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] text-left text-sm">
            <thead className="border-b text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">{copy("成员")}</th>
                <th className="px-3 py-2">{copy("会话 / 线程")}</th>
                <th className="px-3 py-2">{copy("当前工作流")}</th>
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
                      {selection.conversation_type || copy("未知会话类型")}
                      {selection.conversation_scope_id
                        ? ` · ${copy("线程：{{value}}", {
                            value: selection.conversation_scope_id,
                          })}`
                        : ` · ${copy("主会话")}`}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="font-medium">
                      {selection.flow_name || copy("工作流已删除")}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {selection.command || copy("指令已删除")}
                      {selection.flow_endpoint_name
                        ? ` · ${selection.flow_endpoint_name}`
                        : ""}
                    </div>
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
""",
)

# Default routing form adds the group system-command mention policy.
replace_once(
    "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/DefaultRoutingTab.tsx",
    "  flowSelectionTtlHours: string;\n  defaultResponseMode: ChannelResponseMode;",
    "  flowSelectionTtlHours: string;\n  systemCommandsRequireMention: boolean;\n  defaultResponseMode: ChannelResponseMode;",
)
replace_once(
    "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/DefaultRoutingTab.tsx",
    "          flow_selection_ttl_hours: Math.min(\n            8760,\n            Math.max(0, Number(form.flowSelectionTtlHours) || 0),\n          ),\n          default_response_mode: form.defaultResponseMode,",
    "          flow_selection_ttl_hours: Math.min(\n"
    "            8760,\n"
    "            Math.max(0, Number(form.flowSelectionTtlHours) || 0),\n"
    "          ),\n"
    "          system_commands_require_mention:\n"
    "            form.systemCommandsRequireMention,\n"
    "          default_response_mode: form.defaultResponseMode,",
)
replace_once(
    "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/DefaultRoutingTab.tsx",
    '      {capabilities?.supports_group_chat && capabilities.supports_mentions && (\n        <label className="flex flex-col gap-2 text-sm font-medium">',
    "      {capabilities?.supports_group_chat && capabilities.supports_mentions && (\n"
    "        <SettingSwitch\n"
    '          title={copy("群聊系统指令必须 @机器人")}\n'
    '          description={copy("在仅 @机器人模式下，/help、/commands、/use-flow 等系统指令也必须明确 @机器人。")}\n'
    "          checked={form.systemCommandsRequireMention}\n"
    "          onCheckedChange={(checked) =>\n"
    "            setForm((current) => ({\n"
    "              ...current,\n"
    "              systemCommandsRequireMention: checked,\n"
    "            }))\n"
    "          }\n"
    "        />\n"
    "      )}\n\n"
    "      {capabilities?.supports_group_chat && capabilities.supports_mentions && (\n"
    '        <label className="flex flex-col gap-2 text-sm font-medium">',
)
replace_once(
    "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/DefaultRoutingTab.tsx",
    "    flowSelectionTtlHours: String(connection.flow_selection_ttl_hours),\n    defaultResponseMode: connection.default_response_mode,",
    "    flowSelectionTtlHours: String(connection.flow_selection_ttl_hours),\n"
    "    systemCommandsRequireMention:\n"
    "      connection.system_commands_require_mention,\n"
    "    defaultResponseMode: connection.default_response_mode,",
)

# ---------------------------------------------------------------------------
# Tests and permanent CI coverage
# ---------------------------------------------------------------------------
write(
    "src/backend/tests/unit/channels/test_channel_flow_hardening.py",
    r"""from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from langflow.channels.domain.models import (
    ChannelConversation,
    ChannelEvent,
    ChannelEventType,
    ChannelIncomingMessage,
    ChannelType,
    ChannelUser,
)
from langflow.channels.services.flow_selection import (
    cleanup_expired_workflow_selections,
    count_active_workflow_selections,
    list_active_workflow_selections,
    set_active_workflow_selection,
)
from langflow.channels.services.flow_selection_metrics import (
    flow_selection_metrics_snapshot,
    reset_flow_selection_metrics_for_testing,
)
from langflow.channels.services.response_policy import should_process_channel_event
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
from langflow.services.database.models.flow.model import Flow
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture
async def hardening_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    tables = [
        Flow.__table__,
        ChannelConnection.__table__,
        ChannelConversationBinding.__table__,
        ChannelIdentity.__table__,
        ChannelWorkflowCommand.__table__,
        ChannelActiveWorkflowSelection.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: SQLModel.metadata.create_all(sync_connection, tables=tables))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(session: AsyncSession):
    owner_id = uuid4()
    flow = Flow(id=uuid4(), name="会议总结工作流", endpoint_name="meeting-summary", user_id=None)
    connection = ChannelConnection(
        id=uuid4(),
        user_id=owner_id,
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
        display_name="研发群",
    )
    identity = ChannelIdentity(
        id=uuid4(),
        connection_id=connection.id,
        external_user_id="ou-user-1",
        display_name="张三",
    )
    command = ChannelWorkflowCommand(
        id=uuid4(),
        connection_id=connection.id,
        created_by=owner_id,
        flow_id=flow.id,
        command="/summary",
        normalized_command="/summary",
        scope_type=ChannelCommandScope.CONNECTION_SHARED.value,
        scope_key="connection",
        allow_persistent_selection=True,
    )
    session.add_all([flow, connection, binding, identity, command])
    await session.flush()
    return connection, binding, identity, command


def _event(*, mentions: list[str] | None = None, text: str = "/help") -> ChannelEvent:
    return ChannelEvent(
        event_id="event-1",
        channel=ChannelType.FEISHU,
        connection_id=uuid4(),
        event_type=ChannelEventType.COMMAND,
        user=ChannelUser(external_user_id="ou-user"),
        conversation=ChannelConversation(external_conversation_id="chat", conversation_type="group"),
        message=ChannelIncomingMessage(
            external_message_id="message-1",
            message_type=ChannelEventType.COMMAND,
            text=text,
            mentions=mentions or [],
        ),
    )


def test_system_commands_follow_group_mention_policy() -> None:
    event = _event()
    assert not should_process_channel_event(
        event,
        command="/help",
        response_mode="mention_only",
        is_system_command=True,
        system_commands_require_mention=True,
    )
    assert should_process_channel_event(
        event,
        command="/help",
        response_mode="mention_only",
        is_system_command=True,
        system_commands_require_mention=False,
    )
    assert should_process_channel_event(
        event,
        command="/help",
        response_mode="mention_only",
        is_system_command=True,
        system_commands_require_mention=True,
        command_targeted=True,
    )


@pytest.mark.asyncio
async def test_selection_page_returns_joined_display_fields(hardening_session: AsyncSession) -> None:
    reset_flow_selection_metrics_for_testing()
    connection, binding, identity, command = await _seed(hardening_session)
    await set_active_workflow_selection(
        hardening_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="thread-1",
        user_id=None,
        command_name="/summary",
    )

    page = await list_active_workflow_selections(
        hardening_session,
        connection.id,
        query="研发",
    )
    assert page.total == 1
    item = page.items[0]
    assert item.identity_display_name == "张三"
    assert item.conversation_display_name == "研发群"
    assert item.command == "/summary"
    assert item.flow_id == command.flow_id
    assert item.flow_name == "会议总结工作流"
    assert item.flow_endpoint_name == "meeting-summary"
    assert flow_selection_metrics_snapshot().selected_total == 1


@pytest.mark.asyncio
async def test_expired_selection_cleanup_is_bounded(hardening_session: AsyncSession) -> None:
    reset_flow_selection_metrics_for_testing()
    connection, binding, identity, command = await _seed(hardening_session)
    expired_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    hardening_session.add(
        ChannelActiveWorkflowSelection(
            connection_id=connection.id,
            conversation_binding_id=binding.id,
            channel_identity_id=identity.id,
            conversation_scope_id="one",
            workflow_command_id=command.id,
            expires_at=expired_at,
        )
    )
    for index in range(2):
        other_identity = ChannelIdentity(
            id=uuid4(),
            connection_id=connection.id,
            external_user_id=f"ou-user-{index + 2}",
        )
        hardening_session.add(other_identity)
        await hardening_session.flush()
        hardening_session.add(
            ChannelActiveWorkflowSelection(
                connection_id=connection.id,
                conversation_binding_id=binding.id,
                channel_identity_id=other_identity.id,
                conversation_scope_id="",
                workflow_command_id=command.id,
                expires_at=expired_at,
            )
        )
    await hardening_session.flush()

    removed = await cleanup_expired_workflow_selections(
        hardening_session,
        connection_id=connection.id,
        batch_size=2,
    )
    assert removed == 2
    assert await count_active_workflow_selections(hardening_session) == 1
    assert flow_selection_metrics_snapshot().cleaned_total == 2
""",
)

# Migration chain and assertions.
replace_once(
    "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py",
    "from langflow.alembic.versions import (\n    b5d8e1f3a6c9_key_channel_outbound_delivery_parts as outbound_delivery_key_migration,\n)",
    "from langflow.alembic.versions import (\n"
    "    b2c5f8a1d4e7_harden_channel_flow_selections as flow_selection_hardening_migration,\n"
    ")\n"
    "from langflow.alembic.versions import (\n"
    "    b5d8e1f3a6c9_key_channel_outbound_delivery_parts as outbound_delivery_key_migration,\n"
    ")",
)
replace_once(
    "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py",
    "    active_flow_selection_migration,\n)",
    "    active_flow_selection_migration,\n    flow_selection_hardening_migration,\n)",
)
replace_once(
    "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py",
    '        "a1f4c7e9d2b6",\n    ]',
    '        "a1f4c7e9d2b6",\n        "b2c5f8a1d4e7",\n    ]',
)
replace_once(
    "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py",
    '        "b5d8e1f3a6c9",\n    ]',
    '        "b5d8e1f3a6c9",\n        "a1f4c7e9d2b6",\n    ]',
)
replace_once(
    "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py",
    '        assert {"user_flow_selection_enabled", "flow_selection_ttl_hours"} <= connection_columns',
    "        assert {\n"
    '            "user_flow_selection_enabled",\n'
    '            "flow_selection_ttl_hours",\n'
    '            "system_commands_require_mention",\n'
    "        } <= connection_columns",
)
replace_once(
    "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py",
    '        assert context_indexes["ix_channel_context_conversation_session_created"] == (\n            "conversation_binding_id",\n            "session_id",\n            "created_at",\n        )',
    '        assert context_indexes["ix_channel_context_conversation_session_created"] == (\n'
    '            "conversation_binding_id",\n'
    '            "session_id",\n'
    '            "created_at",\n'
    "        )\n"
    "        selection_indexes = {\n"
    '            index["name"]: tuple(index["column_names"])\n'
    '            for index in sa.inspect(connection).get_indexes("channel_active_workflow_selection")\n'
    "        }\n"
    '        assert selection_indexes["ix_channel_active_flow_selection_connection_expires"] == (\n'
    '            "connection_id",\n'
    '            "expires_at",\n'
    "        )",
)

# Runtime metrics assertions.
replace_once(
    "src/backend/tests/unit/channels/test_channel_runtime.py",
    "    assert result.outbound_delivery.retained_failed >= 0\n    assert result.outbound_retry.max_attempts == 5",
    "    assert result.outbound_delivery.retained_failed >= 0\n"
    "    assert result.flow_selections.cleanup_interval_seconds >= 30\n"
    "    assert result.flow_selections.cleanup_batch_size >= 1\n"
    "    assert result.flow_selections.selected_total >= 0\n"
    "    assert result.flow_selections.cleared_total >= 0\n"
    "    assert result.flow_selections.fallback_total >= 0\n"
    "    assert result.flow_selections.cleaned_total >= 0\n"
    "    assert result.flow_selections.maintenance_errors_total >= 0\n"
    "    assert result.flow_selections.active >= 0\n"
    "    assert result.outbound_retry.max_attempts == 5",
)
replace_once(
    "src/backend/tests/unit/channels/test_channel_runtime.py",
    '    assert b"openxflow_channel_outbound_delivery_retained_failed" in response.body',
    '    assert b"openxflow_channel_outbound_delivery_retained_failed" in response.body\n'
    '    assert b"openxflow_channel_flow_selection_selected" in response.body\n'
    '    assert b"openxflow_channel_flow_selection_cleared" in response.body\n'
    '    assert b"openxflow_channel_flow_selection_fallback" in response.body\n'
    '    assert b"openxflow_channel_flow_selection_cleaned" in response.body\n'
    '    assert b"openxflow_channel_flow_selection_active" in response.body',
)

# Keep focused channel CI permanently covering the feature.
replace_once(
    ".github/workflows/channel-gateway-core.yml",
    "            src/backend/tests/unit/channels/test_channel_knowledge_base_delegation.py \\\n            src/backend/tests/unit/channels/test_channel_model_provider_delegation.py \\",
    "            src/backend/tests/unit/channels/test_channel_knowledge_base_delegation.py \\\n"
    "            src/backend/tests/unit/channels/test_channel_flow_selection.py \\\n"
    "            src/backend/tests/unit/channels/test_channel_flow_hardening.py \\\n"
    "            src/backend/tests/unit/channels/test_channel_runtime.py \\\n"
    "            src/backend/tests/unit/channels/test_channel_model_provider_delegation.py \\",
)

# Documentation contract.
replace_once(
    "docs/channel-gateway-routing.md",
    "- whether bound users may create personal commands.",
    "- whether bound users may create personal commands;\n"
    "- whether group system commands must explicitly mention the robot;\n"
    "- whether users may persistently select an approved workflow and how long the choice remains valid.",
)
replace_once(
    "docs/channel-gateway-routing.md",
    "The final migration adds persistent member workflow selections, execution linkage, and workflow-specific context indexing.",
    "The persistent-selection migration adds member workflow selections, execution linkage, and workflow-specific context indexing. "
    "The hardening migration adds the group system-command mention policy and an expiration cleanup index. "
    "Expired selections are removed in bounded background batches, while execution-time permission validation still fails closed and immediately falls back to the default route.",
)

print("Channel flow hardening changes applied.")
