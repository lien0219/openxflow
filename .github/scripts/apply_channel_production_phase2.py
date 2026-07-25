from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    if new in content:
        return
    if old not in content:
        raise RuntimeError(f"Missing patch target in {path}: {old[:140]!r}")
    write(path, content.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, new: str) -> None:
    content = read(path)
    start_index = content.find(start)
    end_index = content.find(end, start_index)
    if start_index < 0 or end_index < 0:
        raise RuntimeError(f"Unable to locate block in {path}: {start!r} -> {end!r}")
    write(path, content[:start_index] + new + content[end_index:])


access_control = '''"""Resolve effective channel policies and execution principals."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.services.database.models.channel.execution_model import ChannelExecutionIdentityType
from langflow.services.database.models.channel.model import (
    ChannelAccessPolicy,
    ChannelConnection,
    ChannelContextMode,
    ChannelConversationBinding,
    ChannelIdentity,
    ChannelIdentityStatus,
)
from langflow.services.database.models.user.model import User


class ChannelBindingRequiredError(PermissionError):
    """Raised when a route requires a bound OpenXFlow account."""


class ChannelServiceIdentityUnavailableError(PermissionError):
    """Raised when shared execution has no active service principal."""


@dataclass(frozen=True)
class ChannelExecutionPrincipal:
    user: User
    identity_type: str
    identity: ChannelIdentity | None = None


def effective_access_policy(
    connection: ChannelConnection,
    binding: ChannelConversationBinding | None,
) -> str:
    if binding is not None and binding.access_policy != ChannelAccessPolicy.INHERIT.value:
        return binding.access_policy
    return connection.access_policy


def effective_context_mode(
    connection: ChannelConnection,
    binding: ChannelConversationBinding | None,
) -> str:
    if binding is not None and binding.context_mode != ChannelContextMode.INHERIT.value:
        return binding.context_mode
    return connection.default_context_mode


async def bound_identity_user(
    session: AsyncSession,
    identity: ChannelIdentity | None,
) -> User | None:
    if (
        identity is None
        or identity.status != ChannelIdentityStatus.BOUND.value
        or identity.openxflow_user_id is None
    ):
        return None
    user = await session.get(User, identity.openxflow_user_id)
    if user is None or not user.is_active:
        return None
    return user


async def resolve_execution_principal(
    session: AsyncSession,
    connection: ChannelConnection,
    binding: ChannelConversationBinding | None,
    identity: ChannelIdentity | None,
    *,
    requires_personal: bool = False,
) -> ChannelExecutionPrincipal:
    policy = effective_access_policy(connection, binding)
    bound_user = await bound_identity_user(session, identity)

    if requires_personal or policy == ChannelAccessPolicy.BOUND_ONLY.value:
        if bound_user is None:
            raise ChannelBindingRequiredError
        return ChannelExecutionPrincipal(
            user=bound_user,
            identity_type=ChannelExecutionIdentityType.BOUND_USER.value,
            identity=identity,
        )

    if policy in {ChannelAccessPolicy.SHARED.value, ChannelAccessPolicy.HYBRID.value}:
        service_user_id = connection.service_user_id or connection.user_id
        service_user = await session.get(User, service_user_id)
        if service_user is None or not service_user.is_active:
            raise ChannelServiceIdentityUnavailableError
        return ChannelExecutionPrincipal(
            user=service_user,
            identity_type=ChannelExecutionIdentityType.SERVICE.value,
            identity=identity,
        )

    if bound_user is None:
        raise ChannelBindingRequiredError
    return ChannelExecutionPrincipal(
        user=bound_user,
        identity_type=ChannelExecutionIdentityType.BOUND_USER.value,
        identity=identity,
    )
'''
write("src/backend/base/langflow/channels/services/access_control.py", access_control)

context_service = '''"""Bounded group context for shared and hybrid channel conversations."""

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
    limit: int,
) -> list[ChannelConversationContextEntry]:
    if limit <= 0:
        return []
    rows = list(
        (
            await session.exec(
                select(ChannelConversationContextEntry)
                .where(ChannelConversationContextEntry.conversation_binding_id == binding.id)
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
    entries = await _recent_entries(session, binding, limit=connection.shared_context_window)
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
'''
write("src/backend/base/langflow/channels/services/context.py", context_service)

binding = '''"""Secure account-binding challenges and external identity discovery."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.domain.exceptions import (
    ChannelBindingCodeExpiredError,
    ChannelBindingCodeInvalidError,
    ChannelIdentityConflictError,
)
from langflow.channels.domain.models import ChannelEvent
from langflow.services.database.models.channel.binding_model import ChannelBindingCode
from langflow.services.database.models.channel.model import (
    ChannelIdentity,
    ChannelIdentityRead,
    ChannelIdentityStatus,
)

_BINDING_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_BINDING_CODE_LENGTH = 8
_BINDING_CODE_TTL = timedelta(minutes=10)


def normalize_binding_code(code: str) -> str:
    normalized = "".join(code.upper().split())
    if len(normalized) != _BINDING_CODE_LENGTH or any(char not in _BINDING_ALPHABET for char in normalized):
        raise ChannelBindingCodeInvalidError("Invalid channel binding code")
    return normalized


def hash_binding_code(code: str) -> str:
    return hashlib.sha256(normalize_binding_code(code).encode()).hexdigest()


def generate_binding_code() -> str:
    return "".join(secrets.choice(_BINDING_ALPHABET) for _ in range(_BINDING_CODE_LENGTH))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def discover_channel_identity(session: AsyncSession, event: ChannelEvent) -> ChannelIdentity:
    statement = select(ChannelIdentity).where(
        ChannelIdentity.connection_id == event.connection_id,
        ChannelIdentity.external_tenant_id == (event.user.tenant_id or ""),
        ChannelIdentity.external_user_id == event.user.external_user_id,
    )
    identity = (await session.exec(statement)).first()
    now = _utc_now()
    if identity is None:
        identity = ChannelIdentity(
            connection_id=event.connection_id,
            external_tenant_id=event.user.tenant_id or "",
            external_user_id=event.user.external_user_id,
            display_name=event.user.display_name,
            profile_data=dict(event.user.metadata),
            status=ChannelIdentityStatus.DISCOVERED.value,
            first_seen_at=now,
            last_seen_at=now,
            last_message_at=event.timestamp or now,
        )
        try:
            async with session.begin_nested():
                session.add(identity)
                await session.flush()
        except IntegrityError:
            identity = (await session.exec(statement)).first()
            if identity is None:
                raise
    identity.display_name = event.user.display_name or identity.display_name
    identity.profile_data = dict(event.user.metadata)
    identity.last_seen_at = now
    identity.last_message_at = event.timestamp or now
    identity.updated_at = now
    session.add(identity)
    await session.flush()
    await session.refresh(identity)
    return identity


async def resolve_channel_identity(session: AsyncSession, event: ChannelEvent) -> ChannelIdentity | None:
    statement = select(ChannelIdentity).where(
        ChannelIdentity.connection_id == event.connection_id,
        ChannelIdentity.external_tenant_id == (event.user.tenant_id or ""),
        ChannelIdentity.external_user_id == event.user.external_user_id,
        ChannelIdentity.status == ChannelIdentityStatus.BOUND.value,
    )
    return (await session.exec(statement)).first()


async def issue_channel_binding_code(
    session: AsyncSession,
    event: ChannelEvent,
    *,
    ttl: timedelta = _BINDING_CODE_TTL,
) -> str:
    now = _utc_now()
    pending_statement = select(ChannelBindingCode).where(
        ChannelBindingCode.connection_id == event.connection_id,
        ChannelBindingCode.external_tenant_id == (event.user.tenant_id or ""),
        ChannelBindingCode.external_user_id == event.user.external_user_id,
        ChannelBindingCode.used_at.is_(None),
    )
    for pending in (await session.exec(pending_statement)).all():
        pending.used_at = now
        session.add(pending)

    for _ in range(5):
        code = generate_binding_code()
        challenge = ChannelBindingCode(
            connection_id=event.connection_id,
            external_user_id=event.user.external_user_id,
            external_tenant_id=event.user.tenant_id or "",
            display_name=event.user.display_name,
            profile_data=dict(event.user.metadata),
            code_hash=hash_binding_code(code),
            expires_at=now + ttl,
        )
        try:
            async with session.begin_nested():
                session.add(challenge)
                await session.flush()
        except IntegrityError:
            continue
        return code
    raise RuntimeError("Unable to allocate a unique channel binding code")


async def redeem_channel_binding_code(
    session: AsyncSession,
    code: str,
    openxflow_user_id: UUID,
) -> ChannelIdentityRead:
    code_hash = hash_binding_code(code)
    statement = (
        select(ChannelBindingCode)
        .where(ChannelBindingCode.code_hash == code_hash, ChannelBindingCode.used_at.is_(None))
        .with_for_update()
    )
    challenge = (await session.exec(statement)).first()
    if challenge is None:
        raise ChannelBindingCodeInvalidError("Channel binding code is invalid or already used")

    now = _utc_now()
    if _as_utc(challenge.expires_at) <= now:
        challenge.used_at = now
        session.add(challenge)
        await session.flush()
        raise ChannelBindingCodeExpiredError("Channel binding code has expired")

    identity_statement = (
        select(ChannelIdentity)
        .where(
            ChannelIdentity.connection_id == challenge.connection_id,
            ChannelIdentity.external_tenant_id == challenge.external_tenant_id,
            ChannelIdentity.external_user_id == challenge.external_user_id,
        )
        .with_for_update()
    )
    identity = (await session.exec(identity_statement)).first()
    if (
        identity is not None
        and identity.openxflow_user_id is not None
        and identity.openxflow_user_id != openxflow_user_id
    ):
        raise ChannelIdentityConflictError("This channel account is already bound to another OpenXFlow user")

    if identity is None:
        identity = ChannelIdentity(
            connection_id=challenge.connection_id,
            openxflow_user_id=openxflow_user_id,
            external_user_id=challenge.external_user_id,
            external_tenant_id=challenge.external_tenant_id,
            display_name=challenge.display_name,
            profile_data=challenge.profile_data,
            status=ChannelIdentityStatus.BOUND.value,
            bound_at=now,
        )
    else:
        identity.openxflow_user_id = openxflow_user_id
        identity.status = ChannelIdentityStatus.BOUND.value
        identity.bound_at = now
        identity.display_name = challenge.display_name or identity.display_name
        identity.profile_data = challenge.profile_data
        identity.last_seen_at = now
        identity.updated_at = now

    challenge.used_at = now
    session.add(identity)
    session.add(challenge)
    await session.flush()
    await session.refresh(identity)
    return ChannelIdentityRead.model_validate(identity, from_attributes=True)
'''
write("src/backend/base/langflow/channels/services/binding.py", binding)

workflow = '''"""Execute OpenXFlow workflows from normalized channel messages."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from langflow.channels.domain.models import ChannelEvent, ChannelMessage, ChannelMessageType
from langflow.helpers.flow import get_flow_by_id_or_endpoint_name
from langflow.services.authorization import FlowAction, ensure_flow_permission
from langflow.services.database.models.channel.model import ChannelContextMode
from langflow.services.database.models.user.model import User

if TYPE_CHECKING:
    from langflow.api.v1.schemas import RunResponse

_TELEGRAM_SAFE_TEXT_LIMIT = 3900
_PREFERRED_OUTPUT_KEYS = ("text", "message", "content", "result", "results", "data")


def build_channel_session_id(event: ChannelEvent, context_mode: str = ChannelContextMode.ISOLATED.value) -> str:
    parts = [
        event.channel.value,
        str(event.connection_id),
        event.conversation.external_conversation_id,
    ]
    if context_mode != ChannelContextMode.SHARED.value or event.conversation.conversation_type == "private":
        parts.append(event.user.external_user_id)
    raw = ":".join(parts)
    return f"channel-{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


def _collect_text_candidates(value: Any, *, depth: int = 0) -> list[str]:
    if depth > 8 or value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        candidates: list[str] = []
        visited: set[str] = set()
        for key in _PREFERRED_OUTPUT_KEYS:
            if key in value:
                visited.add(key)
                candidates.extend(_collect_text_candidates(value[key], depth=depth + 1))
        for key, nested in value.items():
            if key not in visited:
                candidates.extend(_collect_text_candidates(nested, depth=depth + 1))
        return candidates
    if isinstance(value, (list, tuple)):
        candidates = []
        for nested in value:
            candidates.extend(_collect_text_candidates(nested, depth=depth + 1))
        return candidates
    return []


def _collect_chat_output_messages(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    candidates: list[str] = []
    for run_output in value:
        if hasattr(run_output, "model_dump"):
            run_output = run_output.model_dump(exclude_none=True)
        if not isinstance(run_output, dict):
            continue
        result_items = run_output.get("outputs")
        if not isinstance(result_items, (list, tuple)):
            continue
        for result_item in result_items:
            if hasattr(result_item, "model_dump"):
                result_item = result_item.model_dump(exclude_none=True)
            if not isinstance(result_item, dict):
                continue
            messages = result_item.get("messages")
            if not isinstance(messages, (list, tuple)):
                continue
            for message in messages:
                if hasattr(message, "model_dump"):
                    message = message.model_dump(exclude_none=True)
                if not isinstance(message, dict):
                    continue
                sender = str(message.get("sender") or "").strip().lower()
                if sender and sender not in {"machine", "ai", "assistant"}:
                    continue
                candidates.extend(_collect_text_candidates(message.get("message"), depth=1))
    return candidates


def render_run_response(response: RunResponse) -> str:
    payload = response.model_dump(exclude_none=True)
    outputs = payload.get("outputs")
    candidates = _collect_chat_output_messages(outputs) or _collect_text_candidates(outputs)
    deduplicated: list[str] = []
    for candidate in candidates:
        if candidate not in deduplicated:
            deduplicated.append(candidate)
    rendered = deduplicated[-1] if deduplicated else json.dumps(payload, ensure_ascii=False, default=str, indent=2)
    if len(rendered) > _TELEGRAM_SAFE_TEXT_LIMIT:
        rendered = f"{rendered[: _TELEGRAM_SAFE_TEXT_LIMIT - 24]}\n\n[结果已截断]"
    return rendered


class ChannelWorkflowExecutor:
    """Permission-aware bridge from a channel event to the existing workflow runtime."""

    async def execute(
        self,
        *,
        event: ChannelEvent,
        user: User,
        flow_identifier: str,
        input_value: str | None,
        session_id: str,
        execution_identity_type: str,
        channel_context: dict[str, Any] | None = None,
    ) -> ChannelMessage:
        from langflow.api.v1.endpoints import simple_run_flow
        from langflow.api.v1.schemas import SimplifiedAPIRequest

        flow = await get_flow_by_id_or_endpoint_name(flow_identifier, user.id, widen_for_shares=True)
        await ensure_flow_permission(
            user,
            FlowAction.EXECUTE,
            flow_id=flow.id,
            flow_user_id=flow.user_id,
            workspace_id=getattr(flow, "workspace_id", None),
            folder_id=getattr(flow, "folder_id", None),
        )
        normalized_attachments = [attachment.model_dump(exclude_none=True) for attachment in event.message.attachments]
        context_payload: dict[str, Any] = {
            "type": event.channel.value,
            "connection_id": str(event.connection_id),
            "conversation_id": event.conversation.external_conversation_id,
            "conversation_type": event.conversation.conversation_type,
            "message_id": event.message.external_message_id,
            "event_id": event.event_id,
            "external_user_id": event.user.external_user_id,
            "openxflow_user_id": str(user.id),
            "execution_identity_type": execution_identity_type,
            "attachments": normalized_attachments,
            "message_metadata": dict(event.message.metadata),
        }
        if channel_context:
            context_payload.update(channel_context)
        request = SimplifiedAPIRequest(
            input_value=input_value,
            input_type="chat",
            output_type="chat",
            session_id=session_id,
            user_id=f"{event.channel.value}:{event.user.external_user_id}",
        )
        response = await simple_run_flow(
            flow,
            request,
            api_key_user=user,
            context={"channel": context_payload},
        )
        return ChannelMessage(
            message_type=ChannelMessageType.MARKDOWN,
            title=flow.name,
            markdown=render_run_response(response),
            metadata={
                "flow_id": str(flow.id),
                "session_id": response.session_id,
                "execution_identity_type": execution_identity_type,
            },
        )
'''
write("src/backend/base/langflow/channels/services/workflow.py", workflow)

execution_logs = '''"""Persistence helpers for channel workflow execution audit records."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.services.runtime_config import webhook_task_timeout_seconds
from langflow.services.database.models.channel.execution_model import (
    ChannelExecutionLog,
    ChannelExecutionLogPage,
    ChannelExecutionLogRead,
    ChannelExecutionStatus,
)
from langflow.services.deps import session_scope


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def start_channel_execution(
    session: AsyncSession,
    *,
    connection_id: UUID,
    conversation_binding_id: UUID | None,
    openxflow_user_id: UUID | None,
    external_user_id: str | None,
    session_id: str | None,
    execution_identity_type: str,
    flow_id: UUID | None,
    external_event_id: str,
    trigger_type: str,
    command_name: str | None = None,
    queue_wait_ms: int | None = None,
) -> ChannelExecutionLog:
    now = _utc_now()
    execution = ChannelExecutionLog(
        connection_id=connection_id,
        conversation_binding_id=conversation_binding_id,
        openxflow_user_id=openxflow_user_id,
        external_user_id=external_user_id,
        session_id=session_id,
        execution_identity_type=execution_identity_type,
        flow_id=flow_id,
        external_event_id=external_event_id,
        trigger_type=trigger_type,
        command_name=command_name,
        status=ChannelExecutionStatus.RUNNING.value,
        queue_wait_ms=queue_wait_ms,
        started_at=now,
    )
    session.add(execution)
    await session.flush()
    await session.refresh(execution)
    return execution


async def finish_channel_execution(
    session: AsyncSession,
    execution: ChannelExecutionLog,
    *,
    status: str,
    error_message: str | None = None,
    error_code: str | None = None,
) -> None:
    completed_at = _utc_now()
    execution.status = status
    execution.completed_at = completed_at
    started_at = execution.started_at or execution.created_at
    execution.duration_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))
    execution.error_code = error_code[:128] if error_code else None
    execution.error_message = error_message[:4000] if error_message else None
    session.add(execution)
    await session.flush()


async def finalize_channel_execution(
    execution_id: UUID,
    *,
    status: str,
    error_message: str | None = None,
    error_code: str | None = None,
) -> None:
    async def persist() -> None:
        async with session_scope() as session:
            execution = await session.get(ChannelExecutionLog, execution_id)
            if execution is None:
                return
            await finish_channel_execution(
                session,
                execution,
                status=status,
                error_message=error_message,
                error_code=error_code,
            )
            await session.commit()

    task = asyncio.create_task(persist())
    await asyncio.shield(task)


async def _fail_stale_channel_executions(session: AsyncSession, connection_id: UUID) -> None:
    cutoff = _utc_now() - timedelta(seconds=webhook_task_timeout_seconds() + 60)
    statement = select(ChannelExecutionLog).where(
        ChannelExecutionLog.connection_id == connection_id,
        ChannelExecutionLog.status == ChannelExecutionStatus.RUNNING.value,
        ChannelExecutionLog.created_at <= cutoff,
    )
    stale_rows = (await session.exec(statement)).all()
    for execution in stale_rows:
        await finish_channel_execution(
            session,
            execution,
            status=ChannelExecutionStatus.TIMEOUT.value,
            error_code="execution_timeout",
            error_message="Channel workflow execution was interrupted or timed out",
        )
    if stale_rows:
        await session.commit()


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
    await _fail_stale_channel_executions(session, connection_id)
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

    total = int((await session.exec(select(func.count()).select_from(ChannelExecutionLog).where(*filters))).one())
    rows = (
        await session.exec(
            select(ChannelExecutionLog)
            .where(*filters)
            .order_by(ChannelExecutionLog.created_at.desc(), ChannelExecutionLog.id)
            .offset((normalized_page - 1) * normalized_page_size)
            .limit(normalized_page_size)
        )
    ).all()
    return ChannelExecutionLogPage(
        items=[ChannelExecutionLogRead.model_validate(row, from_attributes=True) for row in rows],
        page=normalized_page,
        page_size=normalized_page_size,
        total=total,
        total_pages=math.ceil(total / normalized_page_size) if total else 0,
    )
'''
write("src/backend/base/langflow/channels/services/execution_logs.py", execution_logs)

# Commands: allow unbound users to resolve shared commands only.
COMMANDS = "src/backend/base/langflow/channels/services/commands.py"
replace_once(COMMANDS, "    user_id: UUID,\n    conversation_binding_id: UUID,", "    user_id: UUID | None,\n    conversation_binding_id: UUID,")
replace_once(
    COMMANDS,
    '''    if (
        command.scope_type == ChannelCommandScope.IDENTITY_CONVERSATION.value
        and command.owner_user_id == user_id
''',
    '''    if (
        user_id is not None
        and command.scope_type == ChannelCommandScope.IDENTITY_CONVERSATION.value
        and command.owner_user_id == user_id
''',
)
replace_once(
    COMMANDS,
    '''    if command.scope_type == ChannelCommandScope.IDENTITY_CONNECTION.value and command.owner_user_id == user_id:
''',
    '''    if (
        user_id is not None
        and command.scope_type == ChannelCommandScope.IDENTITY_CONNECTION.value
        and command.owner_user_id == user_id
    ):
''',
)
replace_once(COMMANDS, "    user_id: UUID,\n    command_name: str,", "    user_id: UUID | None,\n    command_name: str,")
replace_once(
    COMMANDS,
    '''        sa.or_(
            ChannelWorkflowCommand.owner_user_id.is_(None),
            ChannelWorkflowCommand.owner_user_id == user_id,
        ),
''',
    '''        (
            ChannelWorkflowCommand.owner_user_id.is_(None)
            if user_id is None
            else sa.or_(
                ChannelWorkflowCommand.owner_user_id.is_(None),
                ChannelWorkflowCommand.owner_user_id == user_id,
            )
        ),
''',
)
replace_once(COMMANDS, "    user_id: UUID,\n) -> list[ChannelWorkflowCommand]:", "    user_id: UUID | None,\n) -> list[ChannelWorkflowCommand]:")
# Replace the second identical owner filter if it remains.
content = read(COMMANDS)
old_filter = '''        sa.or_(
            ChannelWorkflowCommand.owner_user_id.is_(None),
            ChannelWorkflowCommand.owner_user_id == user_id,
        ),
'''
new_filter = '''        (
            ChannelWorkflowCommand.owner_user_id.is_(None)
            if user_id is None
            else sa.or_(
                ChannelWorkflowCommand.owner_user_id.is_(None),
                ChannelWorkflowCommand.owner_user_id == user_id,
            )
        ),
'''
if old_filter in content:
    write(COMMANDS, content.replace(old_filter, new_filter, 1))

# CRUD: serialize and persist all production connection fields, and support discovered identities.
CRUD = "src/backend/base/langflow/services/database/models/channel/crud.py"
replace_once(
    CRUD,
    '''        connection_mode=connection.connection_mode,
        default_flow_id=connection.default_flow_id,
''',
    '''        connection_mode=connection.connection_mode,
        service_user_id=connection.service_user_id,
        default_flow_id=connection.default_flow_id,
''',
)
replace_once(
    CRUD,
    '''        default_allow_file_upload=connection.default_allow_file_upload,
        settings_data=connection.settings_data,
''',
    '''        default_allow_file_upload=connection.default_allow_file_upload,
        access_policy=connection.access_policy,
        default_context_mode=connection.default_context_mode,
        max_concurrency=connection.max_concurrency,
        per_user_concurrency=connection.per_user_concurrency,
        per_user_queue_limit=connection.per_user_queue_limit,
        rate_limit_per_minute=connection.rate_limit_per_minute,
        daily_quota=connection.daily_quota,
        task_timeout_seconds=connection.task_timeout_seconds,
        queue_timeout_seconds=connection.queue_timeout_seconds,
        shared_context_window=connection.shared_context_window,
        context_retention_days=connection.context_retention_days,
        settings_data=connection.settings_data,
''',
)
replace_once(
    CRUD,
    '''        connection_mode=payload.connection_mode,
        default_flow_id=payload.default_flow_id,
''',
    '''        connection_mode=payload.connection_mode,
        service_user_id=payload.service_user_id or user_id,
        default_flow_id=payload.default_flow_id,
''',
)
replace_once(
    CRUD,
    '''        default_allow_file_upload=payload.default_allow_file_upload,
        settings_data=payload.settings_data,
''',
    '''        default_allow_file_upload=payload.default_allow_file_upload,
        access_policy=payload.access_policy,
        default_context_mode=payload.default_context_mode,
        max_concurrency=payload.max_concurrency,
        per_user_concurrency=payload.per_user_concurrency,
        per_user_queue_limit=payload.per_user_queue_limit,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        daily_quota=payload.daily_quota,
        task_timeout_seconds=payload.task_timeout_seconds,
        queue_timeout_seconds=payload.queue_timeout_seconds,
        shared_context_window=payload.shared_context_window,
        context_retention_days=payload.context_retention_days,
        settings_data=payload.settings_data,
''',
)
replace_once(
    CRUD,
    '''        select(ChannelIdentity).where(ChannelIdentity.connection_id == connection_id).order_by(ChannelIdentity.bound_at)
''',
    '''        select(ChannelIdentity)
        .where(ChannelIdentity.connection_id == connection_id)
        .order_by(ChannelIdentity.last_seen_at.desc(), ChannelIdentity.id)
''',
)
replace_once(
    CRUD,
    '''    values = payload.model_dump()

    if identity is None:
''',
    '''    values = payload.model_dump()
    now = _utc_now()
    if values.get("openxflow_user_id") is not None:
        values["status"] = "bound"
        values["bound_at"] = now

    if identity is None:
''',
)
replace_once(
    CRUD,
    '''        for key, value in values.items():
            setattr(identity, key, value)
        identity.updated_at = _utc_now()
''',
    '''        for key, value in values.items():
            setattr(identity, key, value)
        identity.last_seen_at = now
        identity.updated_at = now
''',
)

# API: secure service principal selection and require a target for manual binding.
CHANNELS_API = "src/backend/base/langflow/api/v1/channels.py"
replace_once(
    CHANNELS_API,
    '''from langflow.services.database.models.channel.model import (
''',
    '''from langflow.services.database.models.channel.model import (
''',
)
replace_once(
    CHANNELS_API,
    '''    ChannelIdentityRead,
)
''',
    '''    ChannelIdentityRead,
)
from langflow.services.database.models.user.model import User
''',
)
replace_once(
    CHANNELS_API,
    '''    await validate_connection_routing_resources(db, current_user, payload)
    try:
''',
    '''    service_user_id = payload.service_user_id or current_user.id
    if service_user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign another service user")
    service_user = await db.get(User, service_user_id)
    if service_user is None or not service_user.is_active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Service user is missing or inactive")
    payload.service_user_id = service_user_id
    await validate_connection_routing_resources(db, current_user, payload)
    try:
''',
)
replace_once(
    CHANNELS_API,
    '''    connection = await _owned_connection_or_404(db, current_user.id, connection_id)
    await validate_connection_routing_resources(
''',
    '''    connection = await _owned_connection_or_404(db, current_user.id, connection_id)
    if payload.service_user_id is not None:
        if payload.service_user_id != current_user.id and not current_user.is_superuser:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign another service user")
        service_user = await db.get(User, payload.service_user_id)
        if service_user is None or not service_user.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Service user is missing or inactive")
    await validate_connection_routing_resources(
''',
)
replace_once(
    CHANNELS_API,
    '''    await _owned_connection_or_404(db, current_user.id, connection_id)
    if payload.openxflow_user_id != current_user.id and not current_user.is_superuser:
''',
    '''    await _owned_connection_or_404(db, current_user.id, connection_id)
    if payload.openxflow_user_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="openxflow_user_id is required")
    if payload.openxflow_user_id != current_user.id and not current_user.is_superuser:
''',
)

# Dispatch imports.
DISPATCH = "src/backend/base/langflow/channels/services/dispatch.py"
replace_once(
    DISPATCH,
    '''from langflow.channels.services.binding import issue_channel_binding_code, resolve_channel_identity
''',
    '''from langflow.channels.services.access_control import (
    ChannelBindingRequiredError,
    ChannelExecutionPrincipal,
    ChannelServiceIdentityUnavailableError,
    bound_identity_user,
    effective_access_policy,
    effective_context_mode,
    resolve_execution_principal,
)
from langflow.channels.services.binding import discover_channel_identity, issue_channel_binding_code
''',
)
replace_once(
    DISPATCH,
    '''from langflow.channels.services.execution_logs import finalize_channel_execution, start_channel_execution
''',
    '''from langflow.channels.services.context import prepare_channel_input, record_channel_response
from langflow.channels.services.execution_logs import finalize_channel_execution, start_channel_execution
''',
)
replace_once(
    DISPATCH,
    '''from langflow.channels.services.workflow import ChannelWorkflowExecutor
''',
    '''from langflow.channels.services.workflow import ChannelWorkflowExecutor, build_channel_session_id
''',
)
replace_once(
    DISPATCH,
    '''from langflow.services.database.models.channel.execution_model import ChannelExecutionTrigger
''',
    '''from langflow.services.database.models.channel.execution_model import ChannelExecutionStatus, ChannelExecutionTrigger
''',
)

handle_block = '''    async def handle(self, event: ChannelEvent) -> ChannelMessage | None:
        command, argument = self._parse_command(event.message.text)
        binding = await discover_channel_conversation(self.session, self.connection, event)
        if binding is None:
            binding = await self._get_conversation_binding(event)
        identity = await discover_channel_identity(self.session, event)
        bound_user = await bound_identity_user(self.session, identity)
        if bound_user is not None:
            event.user.openxflow_user_id = bound_user.id

        if binding is not None and binding.status in {
            ChannelConversationStatus.IGNORED.value,
            ChannelConversationStatus.DISABLED.value,
            ChannelConversationStatus.UNAVAILABLE.value,
        }:
            return None
        if self._should_ignore_group_event(event, binding=binding, command=command):
            return None

        if command in {"/start", "/help"}:
            return self._help_message(bound=bound_user is not None)
        if command == "/bind":
            if bound_user is not None:
                return ChannelMessage(
                    title="账号已绑定",
                    text=f"当前渠道账号已绑定 OpenXFlow 用户：{bound_user.username}",
                )
            return await self._binding_required_message(event)
        if command == "/commands":
            return await self._commands_message(bound_user.id if bound_user else None, binding)

        if command == "/flow":
            if bound_user is None or (
                bound_user.id != self.connection.user_id and not bound_user.is_superuser
            ):
                return ChannelMessage(text="未知命令。发送 /commands 查看当前可用指令。")
            flow_identifier, _, input_value = argument.partition(" ")
            if not flow_identifier:
                return ChannelMessage(text="管理员用法：/flow <工作流 ID 或 endpoint_name> [输入内容]")
            principal = ChannelExecutionPrincipal(
                user=bound_user,
                identity_type="bound_user",
                identity=identity,
            )
            return await self._execute_workflow(
                event,
                principal,
                flow_identifier,
                input_value or None,
                binding=binding,
                trigger_type=ChannelExecutionTrigger.ADMIN_FLOW.value,
                flow_id=self._try_uuid(flow_identifier),
            )

        if command is not None:
            custom_response = await self._execute_custom_command(
                event,
                identity,
                bound_user,
                binding,
                command,
                argument,
            )
            if custom_response is not None:
                return custom_response
            return await self._unknown_command_message(bound_user.id if bound_user else None, binding, command)

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
replace_between(DISPATCH, "    async def handle(self, event: ChannelEvent) -> ChannelMessage | None:\n", "    async def _execute_custom_command(\n", handle_block)

custom_block = '''    async def _execute_custom_command(
        self,
        event: ChannelEvent,
        identity,
        bound_user: User | None,
        binding: ChannelConversationBinding | None,
        command_name: str,
        argument: str,
    ) -> ChannelMessage | None:
        if binding is None:
            return None
        command = await resolve_workflow_command(
            self.session,
            connection_id=self.connection.id,
            conversation_binding_id=binding.id,
            user_id=bound_user.id if bound_user else None,
            command_name=command_name,
        )
        if command is None:
            return None
        if event.conversation.conversation_type != "private" and command.require_mention and not event.message.mentions:
            return None
        if event.message.attachments and not command.allow_attachments:
            return ChannelMessage(text=f"指令 {command.command} 不允许上传附件。")
        if command.input_required and not argument and not event.message.attachments:
            description = command.description or "请在指令后输入需要处理的内容。"
            return ChannelMessage(title=command.command, text=f"{description}\n\n用法：{command.command} <内容>")

        try:
            principal = await resolve_execution_principal(
                self.session,
                self.connection,
                binding,
                identity,
                requires_personal=command.owner_user_id is not None,
            )
        except ChannelBindingRequiredError:
            return await self._binding_required_message(event)
        except ChannelServiceIdentityUnavailableError:
            return ChannelMessage(text="当前渠道共享执行身份尚未配置或已停用，请联系管理员。")

        input_value = render_command_input(
            command,
            input_value=argument,
            sender_name=event.user.display_name,
            conversation_name=event.conversation.title or binding.display_name,
            conversation_type=event.conversation.conversation_type,
        )
        await mark_workflow_command_used(self.session, command)
        return await self._execute_workflow(
            event,
            principal,
            str(command.flow_id),
            input_value or None,
            binding=binding,
            trigger_type=ChannelExecutionTrigger.COMMAND.value,
            command_name=command.normalized_command,
            flow_id=command.flow_id,
        )

'''
replace_between(DISPATCH, "    async def _execute_custom_command(\n", "    async def _commands_message(\n", custom_block)

commands_block = '''    async def _commands_message(
        self,
        user_id: UUID | None,
        binding: ChannelConversationBinding | None,
    ) -> ChannelMessage:
        if binding is None:
            return ChannelMessage(title="可用指令", text="当前会话尚未完成自动发现。")
        commands = await list_available_workflow_commands(
            self.session,
            connection_id=self.connection.id,
            conversation_binding_id=binding.id,
            user_id=user_id,
        )
        if not commands:
            return ChannelMessage(title="可用指令", text="当前会话还没有配置自定义指令。")
        lines = []
        for item in commands[:50]:
            description = f" — {item.description}" if item.description else ""
            lines.append(f"{item.command}{description}")
        return ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="当前可用指令",
            text="\n".join(lines),
            actions=[
                ChannelAction(
                    action_id=f"command:{item.normalized_command}",
                    label=item.command,
                    value=item.command,
                )
                for item in commands[:6]
            ],
        )

'''
replace_between(DISPATCH, "    async def _commands_message(\n", "    async def _unknown_command_message(\n", commands_block)

unknown_block = '''    async def _unknown_command_message(
        self,
        user_id: UUID | None,
        binding: ChannelConversationBinding | None,
        command_name: str,
    ) -> ChannelMessage:
        commands: list[ChannelWorkflowCommand] = []
        if binding is not None:
            commands = await list_available_workflow_commands(
                self.session,
                connection_id=self.connection.id,
                conversation_binding_id=binding.id,
                user_id=user_id,
            )
        command_by_name = {name: item for item in commands for name in (item.normalized_command, *item.aliases)}
        suggestions = get_close_matches(command_name.lower(), list(command_by_name), n=3, cutoff=0.45)
        if not suggestions:
            return ChannelMessage(text=f"没有找到指令 {command_name}。发送 /commands 查看当前可用指令。")
        unique_commands: list[ChannelWorkflowCommand] = []
        seen_ids: set[UUID] = set()
        for suggestion in suggestions:
            item = command_by_name[suggestion]
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                unique_commands.append(item)
        suggested_text = "、".join(item.command for item in unique_commands)
        return ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="没有找到该指令",
            text=f"你是否想使用：{suggested_text}？\n\n发送 /commands 查看全部指令。",
            actions=[
                ChannelAction(
                    action_id=f"suggested:{item.normalized_command}",
                    label=item.command,
                    value=item.command,
                )
                for item in unique_commands
            ],
        )

'''
replace_between(DISPATCH, "    async def _unknown_command_message(\n", "    def _resolve_default_flow_id(\n", unknown_block)

execute_block = '''    async def _execute_workflow(
        self,
        event: ChannelEvent,
        principal: ChannelExecutionPrincipal,
        flow_identifier: str,
        input_value: str | None,
        *,
        binding: ChannelConversationBinding | None,
        trigger_type: str,
        command_name: str | None = None,
        flow_id: UUID | None = None,
    ) -> ChannelMessage | None:
        context_mode = effective_context_mode(self.connection, binding)
        session_id = build_channel_session_id(event, context_mode)
        prepared_input = await prepare_channel_input(
            self.session,
            connection=self.connection,
            binding=binding,
            event=event,
            session_id=session_id,
            input_value=input_value,
        )
        execution = None
        queue_wait_ms = event.message.metadata.get("queue_wait_ms")
        if not isinstance(queue_wait_ms, int):
            queue_wait_ms = None
        try:
            execution = await start_channel_execution(
                self.session,
                connection_id=self.connection.id,
                conversation_binding_id=binding.id if binding else None,
                openxflow_user_id=principal.user.id,
                external_user_id=event.user.external_user_id,
                session_id=session_id,
                execution_identity_type=principal.identity_type,
                flow_id=flow_id,
                external_event_id=event.event_id,
                trigger_type=trigger_type,
                command_name=command_name,
                queue_wait_ms=queue_wait_ms,
            )
        except Exception:  # noqa: BLE001
            await logger.aexception("Unable to create channel execution log")

        await self.session.commit()
        processing_message_id = await self._send_processing_message(event)
        final_status = ChannelExecutionStatus.FAILED.value
        error_message: str | None = None
        error_code: str | None = None
        try:
            channel_context = await self._build_bound_context(binding)
            channel_context.update(
                {
                    "access_policy": effective_access_policy(self.connection, binding),
                    "context_mode": context_mode,
                    "execution_identity_type": principal.identity_type,
                }
            )
            if command_name:
                channel_context["command_name"] = command_name
            response = await self.workflow_executor.execute(
                event=event,
                user=principal.user,
                flow_identifier=flow_identifier,
                input_value=prepared_input,
                session_id=session_id,
                execution_identity_type=principal.identity_type,
                channel_context=channel_context,
            )
            final_status = ChannelExecutionStatus.SUCCEEDED.value
            await record_channel_response(
                self.session,
                connection=self.connection,
                binding=binding,
                event=event,
                session_id=session_id,
                response=response,
            )
            await self.session.commit()
        except HTTPException as exc:
            error_message = str(exc.detail)
            error_code = f"http_{exc.status_code}"
            if exc.status_code in {403, 404}:
                response = ChannelMessage(text="工作流不存在，或当前执行身份没有执行权限。")
            else:
                await logger.aexception("Channel workflow HTTP error for flow %s", flow_identifier)
                response = ChannelMessage(text="工作流执行失败，请稍后重试。")
        except asyncio.CancelledError:
            error_message = "Channel workflow execution was cancelled or timed out"
            error_code = "execution_cancelled"
            final_status = ChannelExecutionStatus.TIMEOUT.value
            raise
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            error_code = type(exc).__name__[:128]
            await logger.aexception("Channel workflow execution failed for flow %s", flow_identifier)
            response = ChannelMessage(text="工作流执行失败，请在 OpenXFlow 运行记录中查看错误详情。")
        finally:
            if execution is not None:
                try:
                    await finalize_channel_execution(
                        execution.id,
                        status=final_status,
                        error_message=error_message,
                        error_code=error_code,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    await logger.aexception("Unable to finish channel execution log %s", execution.id)

        if processing_message_id is not None:
            try:
                await retry_channel_operation(
                    lambda: self.adapter.update_message(processing_message_id, response),
                    operation_name=f"{self.adapter.channel_type.value}.update_processing_message",
                )
                return None
            except Exception:  # noqa: BLE001
                await logger.aexception(
                    "Unable to update Feishu processing message %s; falling back to a new response",
                    processing_message_id,
                )
        return response

'''
replace_between(DISPATCH, "    async def _execute_workflow(\n", "    async def _send_processing_message(\n", execute_block)

context_block = '''    async def _build_bound_context(
        self,
        binding: ChannelConversationBinding | None,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "connection_id": str(self.connection.id),
            "channel_type": self.connection.channel_type,
        }
        if binding is not None:
            context.update(
                {
                    "conversation_binding_id": str(binding.id),
                    "response_mode": binding.response_mode,
                    "allow_file_upload": binding.allow_file_upload,
                    "conversation_route_mode": binding.route_mode,
                    "conversation_access_policy": binding.access_policy,
                    "conversation_context_mode": binding.context_mode,
                }
            )
        knowledge_base_id = (
            binding.knowledge_base_id
            if binding is not None and binding.knowledge_base_id is not None
            else self.connection.default_knowledge_base_id
        )
        if knowledge_base_id is not None:
            kb = await self.session.get(KnowledgeBaseRecord, knowledge_base_id)
            context["knowledge_base_id"] = str(knowledge_base_id)
            if kb is not None:
                context["knowledge_base_name"] = kb.name
        return context

'''
replace_between(DISPATCH, "    async def _build_bound_context(\n", "    @staticmethod\n    def _try_uuid", context_block)

# Tests for policy and context behavior.
policy_test = '''from types import SimpleNamespace
from uuid import uuid4

import pytest

from langflow.channels.services.access_control import (
    ChannelBindingRequiredError,
    effective_access_policy,
    effective_context_mode,
)
from langflow.channels.services.workflow import build_channel_session_id
from langflow.services.database.models.channel.model import (
    ChannelAccessPolicy,
    ChannelContextMode,
)


def _event(*, user_id: str = "user-1", conversation_type: str = "group"):
    return SimpleNamespace(
        channel=SimpleNamespace(value="feishu"),
        connection_id=uuid4(),
        conversation=SimpleNamespace(
            external_conversation_id="chat-1",
            conversation_type=conversation_type,
        ),
        user=SimpleNamespace(external_user_id=user_id),
    )


def test_effective_policy_and_context_inherit_from_connection() -> None:
    connection = SimpleNamespace(
        access_policy=ChannelAccessPolicy.HYBRID.value,
        default_context_mode=ChannelContextMode.ISOLATED.value,
    )
    binding = SimpleNamespace(
        access_policy=ChannelAccessPolicy.INHERIT.value,
        context_mode=ChannelContextMode.INHERIT.value,
    )
    assert effective_access_policy(connection, binding) == "hybrid"
    assert effective_context_mode(connection, binding) == "isolated"


def test_shared_group_session_is_common_but_isolated_session_is_per_user() -> None:
    first = _event(user_id="user-1")
    second = SimpleNamespace(**first.__dict__)
    second.user = SimpleNamespace(external_user_id="user-2")
    assert build_channel_session_id(first, "shared") == build_channel_session_id(second, "shared")
    assert build_channel_session_id(first, "isolated") != build_channel_session_id(second, "isolated")


def test_private_sessions_remain_user_scoped_in_shared_mode() -> None:
    first = _event(user_id="user-1", conversation_type="private")
    second = _event(user_id="user-2", conversation_type="private")
    second.connection_id = first.connection_id
    assert build_channel_session_id(first, "shared") != build_channel_session_id(second, "shared")


def test_binding_required_error_is_permission_error() -> None:
    assert issubclass(ChannelBindingRequiredError, PermissionError)
'''
write("src/backend/tests/unit/channels/test_production_access_context.py", policy_test)

print("Applied production channel phase 2 access and context runtime")
