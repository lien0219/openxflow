"""CRUD helpers for communication-channel persistence."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from langflow.channels.security.credentials import (
    decrypt_credentials,
    encrypt_credentials,
    list_credential_keys,
)
from langflow.channels.security.provider_credentials import (
    ChannelProviderCredentialError,
    validate_channel_provider_credentials,
)
from langflow.channels.services.service_identity import (
    ensure_channel_service_identity,
    remove_channel_service_identity,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from langflow.channels.domain.models import ChannelEvent

from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConnectionCreate,
    ChannelConnectionRead,
    ChannelConnectionUpdate,
    ChannelConversationBinding,
    ChannelConversationBindingPage,
    ChannelConversationBindingRead,
    ChannelConversationBindingUpdate,
    ChannelConversationBindingUpsert,
    ChannelConversationRouteMode,
    ChannelConversationSource,
    ChannelConversationStatus,
    ChannelEventReceipt,
    ChannelIdentity,
    ChannelIdentityCreate,
    ChannelIdentityRead,
    ChannelReceiptStatus,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _connection_read(connection: ChannelConnection) -> ChannelConnectionRead:
    return ChannelConnectionRead(
        id=connection.id,
        user_id=connection.user_id,
        name=connection.name,
        channel_type=connection.channel_type,
        enabled=connection.enabled,
        connection_mode=connection.connection_mode,
        service_user_id=connection.service_user_id,
        default_flow_id=connection.default_flow_id,
        default_knowledge_base_id=connection.default_knowledge_base_id,
        auto_discover_conversations=connection.auto_discover_conversations,
        unconfigured_behavior=connection.unconfigured_behavior,
        pending_notice_enabled=connection.pending_notice_enabled,
        personal_commands_enabled=connection.personal_commands_enabled,
        default_response_mode=connection.default_response_mode,
        default_allow_file_upload=connection.default_allow_file_upload,
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
        status=connection.status,
        configured_credential_keys=list_credential_keys(connection.credentials_encrypted),
        last_connected_at=connection.last_connected_at,
        last_error=connection.last_error,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


def _derive_conversation_status(
    connection: ChannelConnection,
    binding: ChannelConversationBinding,
) -> str:
    if binding.status in {
        ChannelConversationStatus.IGNORED.value,
        ChannelConversationStatus.UNAVAILABLE.value,
    }:
        return binding.status
    if binding.route_mode == ChannelConversationRouteMode.DISABLED.value:
        return ChannelConversationStatus.DISABLED.value
    if binding.route_mode == ChannelConversationRouteMode.OVERRIDE.value and binding.default_flow_id is not None:
        return ChannelConversationStatus.OVERRIDDEN.value
    if connection.default_flow_id is not None:
        return ChannelConversationStatus.INHERITED.value
    return ChannelConversationStatus.PENDING.value


def _next_connection_credentials(
    connection: ChannelConnection,
    payload: ChannelConnectionUpdate,
) -> tuple[dict[str, str], str, bool]:
    """Merge same-mode patches but replace credentials when the provider mode changes."""
    next_mode = payload.connection_mode or connection.connection_mode
    mode_changed = next_mode != connection.connection_mode
    if mode_changed:
        if payload.credentials is None:
            message = "Channel credentials are required when changing the connection mode"
            raise ChannelProviderCredentialError(message)
        return dict(payload.credentials), next_mode, True

    existing = decrypt_credentials(connection.credentials_encrypted)
    merged = dict(existing)
    if payload.credentials is not None:
        merged.update(payload.credentials)
    return merged, next_mode, payload.credentials is not None


async def create_channel_connection(
    session: AsyncSession,
    user_id: UUID,
    payload: ChannelConnectionCreate,
) -> ChannelConnectionRead:
    validate_channel_provider_credentials(
        payload.channel_type,
        payload.connection_mode,
        payload.credentials,
    )
    connection = ChannelConnection(
        user_id=user_id,
        name=payload.name,
        channel_type=payload.channel_type,
        enabled=payload.enabled,
        connection_mode=payload.connection_mode,
        service_user_id=None,
        default_flow_id=payload.default_flow_id,
        default_knowledge_base_id=payload.default_knowledge_base_id,
        auto_discover_conversations=payload.auto_discover_conversations,
        unconfigured_behavior=payload.unconfigured_behavior,
        pending_notice_enabled=payload.pending_notice_enabled,
        personal_commands_enabled=payload.personal_commands_enabled,
        default_response_mode=payload.default_response_mode,
        default_allow_file_upload=payload.default_allow_file_upload,
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
        credentials_encrypted=encrypt_credentials(payload.credentials),
    )
    session.add(connection)
    await session.flush()
    await ensure_channel_service_identity(session, connection)
    await session.refresh(connection)
    return _connection_read(connection)


async def list_channel_connections(session: AsyncSession, user_id: UUID) -> list[ChannelConnectionRead]:
    statement = (
        select(ChannelConnection).where(ChannelConnection.user_id == user_id).order_by(ChannelConnection.created_at)
    )
    rows = (await session.exec(statement)).all()
    for row in rows:
        await ensure_channel_service_identity(session, row)
    return [_connection_read(row) for row in rows]


async def get_owned_channel_connection(
    session: AsyncSession,
    user_id: UUID,
    connection_id: UUID,
) -> ChannelConnection | None:
    statement = select(ChannelConnection).where(
        ChannelConnection.id == connection_id,
        ChannelConnection.user_id == user_id,
    )
    connection = (await session.exec(statement)).first()
    if connection is not None:
        await ensure_channel_service_identity(session, connection)
    return connection


async def update_channel_connection(
    session: AsyncSession,
    connection: ChannelConnection,
    payload: ChannelConnectionUpdate,
) -> ChannelConnectionRead:
    next_credentials, next_connection_mode, should_store_credentials = _next_connection_credentials(
        connection,
        payload,
    )
    validate_channel_provider_credentials(
        connection.channel_type,
        next_connection_mode,
        next_credentials,
    )

    changes = payload.model_dump(exclude_unset=True, exclude={"credentials", "service_user_id"})
    for key, value in changes.items():
        setattr(connection, key, value)

    if should_store_credentials:
        connection.credentials_encrypted = encrypt_credentials(next_credentials)

    connection.updated_at = _utc_now()
    session.add(connection)
    await ensure_channel_service_identity(session, connection)

    if "default_flow_id" in changes:
        inherited_statement = select(ChannelConversationBinding).where(
            ChannelConversationBinding.connection_id == connection.id,
            ChannelConversationBinding.route_mode == ChannelConversationRouteMode.INHERIT.value,
            ChannelConversationBinding.status.notin_(
                [ChannelConversationStatus.IGNORED.value, ChannelConversationStatus.UNAVAILABLE.value]
            ),
        )
        inherited_rows = (await session.exec(inherited_statement)).all()
        for binding in inherited_rows:
            binding.status = _derive_conversation_status(connection, binding)
            binding.updated_at = _utc_now()
            session.add(binding)

    await session.flush()
    await session.refresh(connection)
    return _connection_read(connection)


async def delete_channel_connection(session: AsyncSession, connection: ChannelConnection) -> None:
    await remove_channel_service_identity(session, connection)
    await session.delete(connection)
    await session.flush()


async def list_channel_identities(
    session: AsyncSession,
    connection_id: UUID,
) -> list[ChannelIdentityRead]:
    statement = (
        select(ChannelIdentity)
        .where(ChannelIdentity.connection_id == connection_id)
        .order_by(ChannelIdentity.last_seen_at.desc(), ChannelIdentity.id)
    )
    rows = (await session.exec(statement)).all()
    return [ChannelIdentityRead.model_validate(row, from_attributes=True) for row in rows]


async def upsert_channel_identity(
    session: AsyncSession,
    connection_id: UUID,
    payload: ChannelIdentityCreate,
) -> ChannelIdentityRead:
    statement = select(ChannelIdentity).where(
        ChannelIdentity.connection_id == connection_id,
        ChannelIdentity.external_tenant_id == payload.external_tenant_id,
        ChannelIdentity.external_user_id == payload.external_user_id,
    )
    identity = (await session.exec(statement)).first()
    values = payload.model_dump()
    now = _utc_now()
    if values.get("openxflow_user_id") is not None:
        values["status"] = "bound"
        values["bound_at"] = now

    if identity is None:
        identity = ChannelIdentity(connection_id=connection_id, **values)
    else:
        for key, value in values.items():
            setattr(identity, key, value)
        identity.last_seen_at = now
        identity.updated_at = now

    session.add(identity)
    await session.flush()
    await session.refresh(identity)
    return ChannelIdentityRead.model_validate(identity, from_attributes=True)


async def delete_channel_identity(
    session: AsyncSession,
    connection_id: UUID,
    identity_id: UUID,
) -> bool:
    statement = select(ChannelIdentity).where(
        ChannelIdentity.id == identity_id,
        ChannelIdentity.connection_id == connection_id,
    )
    identity = (await session.exec(statement)).first()
    if identity is None:
        return False
    await session.delete(identity)
    await session.flush()
    return True


async def list_conversation_bindings(
    session: AsyncSession,
    connection_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    query: str | None = None,
    conversation_type: str | None = None,
    status: str | None = None,
    route_mode: str | None = None,
    sort: str = "-last_message_at",
) -> ChannelConversationBindingPage:
    normalized_page = max(1, page)
    normalized_page_size = min(100, max(1, page_size))
    filters: list[Any] = [ChannelConversationBinding.connection_id == connection_id]

    if query and query.strip():
        pattern = f"%{query.strip()}%"
        filters.append(
            sa.or_(
                ChannelConversationBinding.display_name.ilike(pattern),
                ChannelConversationBinding.external_conversation_id.ilike(pattern),
            )
        )
    if conversation_type:
        filters.append(ChannelConversationBinding.conversation_type == conversation_type)
    if status:
        filters.append(ChannelConversationBinding.status == status)
    if route_mode:
        filters.append(ChannelConversationBinding.route_mode == route_mode)

    count_statement = select(func.count()).select_from(ChannelConversationBinding).where(*filters)
    total = int((await session.exec(count_statement)).one())

    sort_descending = sort.startswith("-")
    sort_key = sort.removeprefix("-")
    sort_columns = {
        "last_message_at": ChannelConversationBinding.last_message_at,
        "first_seen_at": ChannelConversationBinding.first_seen_at,
        "created_at": ChannelConversationBinding.created_at,
        "display_name": ChannelConversationBinding.display_name,
    }
    sort_column = sort_columns.get(sort_key, ChannelConversationBinding.last_message_at)
    ordering = sort_column.desc() if sort_descending else sort_column.asc()

    statement = (
        select(ChannelConversationBinding)
        .where(*filters)
        .order_by(ordering, ChannelConversationBinding.id)
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    )
    rows = (await session.exec(statement)).all()
    return ChannelConversationBindingPage(
        items=[ChannelConversationBindingRead.model_validate(row, from_attributes=True) for row in rows],
        page=normalized_page,
        page_size=normalized_page_size,
        total=total,
        total_pages=math.ceil(total / normalized_page_size) if total else 0,
    )


async def get_channel_conversation_binding(
    session: AsyncSession,
    connection_id: UUID,
    binding_id: UUID,
) -> ChannelConversationBinding | None:
    statement = select(ChannelConversationBinding).where(
        ChannelConversationBinding.id == binding_id,
        ChannelConversationBinding.connection_id == connection_id,
    )
    return (await session.exec(statement)).first()


async def delete_legacy_channel_conversation_binding(
    session: AsyncSession,
    connection_id: UUID,
    binding_id: UUID,
) -> bool:
    binding = await get_channel_conversation_binding(session, connection_id, binding_id)
    if binding is None:
        return False
    if binding.source != ChannelConversationSource.LEGACY_MANUAL.value:
        msg = "Only legacy manual channel conversations can be deleted"
        raise ValueError(msg)
    await session.delete(binding)
    await session.flush()
    return True


async def discover_channel_conversation(
    session: AsyncSession,
    connection: ChannelConnection,
    event: ChannelEvent,
) -> ChannelConversationBinding | None:
    statement = select(ChannelConversationBinding).where(
        ChannelConversationBinding.connection_id == connection.id,
        ChannelConversationBinding.external_conversation_id == event.conversation.external_conversation_id,
    )
    if not connection.auto_discover_conversations:
        return (await session.exec(statement)).first()

    binding = (await session.exec(statement)).first()
    now = _utc_now()

    if binding is None:
        binding = ChannelConversationBinding(
            connection_id=connection.id,
            external_conversation_id=event.conversation.external_conversation_id,
            conversation_type=event.conversation.conversation_type,
            display_name=event.conversation.title,
            response_mode=connection.default_response_mode,
            allow_file_upload=connection.default_allow_file_upload,
            route_mode=ChannelConversationRouteMode.INHERIT.value,
            status=(
                ChannelConversationStatus.INHERITED.value
                if connection.default_flow_id is not None
                else ChannelConversationStatus.PENDING.value
            ),
            source=ChannelConversationSource.AUTO_DISCOVERED.value,
            provider_metadata=dict(event.conversation.metadata),
            first_seen_at=now,
            last_seen_at=now,
            last_message_at=event.timestamp or now,
        )
        try:
            async with session.begin_nested():
                session.add(binding)
                await session.flush()
        except IntegrityError:
            binding = (await session.exec(statement)).first()
            if binding is None:
                raise
    if binding is None:
        return None

    binding.conversation_type = event.conversation.conversation_type
    if event.conversation.title:
        binding.display_name = event.conversation.title
    binding.provider_metadata = dict(event.conversation.metadata)
    binding.source = ChannelConversationSource.AUTO_DISCOVERED.value
    binding.last_seen_at = now
    binding.last_message_at = event.timestamp or now
    binding.updated_at = now
    binding.status = _derive_conversation_status(connection, binding)
    session.add(binding)
    await session.flush()
    await session.refresh(binding)
    return binding


async def upsert_channel_conversation_binding(
    session: AsyncSession,
    connection_id: UUID,
    payload: ChannelConversationBindingUpsert,
) -> ChannelConversationBindingRead:
    statement = select(ChannelConversationBinding).where(
        ChannelConversationBinding.connection_id == connection_id,
        ChannelConversationBinding.external_conversation_id == payload.external_conversation_id,
    )
    binding = (await session.exec(statement)).first()
    values = payload.model_dump()

    if binding is None:
        if payload.default_flow_id is not None and payload.route_mode == ChannelConversationRouteMode.INHERIT.value:
            values["route_mode"] = ChannelConversationRouteMode.OVERRIDE.value
            values["status"] = ChannelConversationStatus.OVERRIDDEN.value
        binding = ChannelConversationBinding(connection_id=connection_id, **values)
    else:
        for key, value in values.items():
            setattr(binding, key, value)
        if binding.default_flow_id is not None and binding.route_mode == ChannelConversationRouteMode.INHERIT.value:
            binding.route_mode = ChannelConversationRouteMode.OVERRIDE.value
            binding.status = ChannelConversationStatus.OVERRIDDEN.value
        binding.updated_at = _utc_now()

    session.add(binding)
    await session.flush()
    await session.refresh(binding)
    return ChannelConversationBindingRead.model_validate(binding, from_attributes=True)


async def update_channel_conversation_binding(
    session: AsyncSession,
    connection: ChannelConnection,
    binding: ChannelConversationBinding,
    payload: ChannelConversationBindingUpdate,
) -> ChannelConversationBindingRead:
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(binding, key, value)

    now = _utc_now()
    if binding.status == ChannelConversationStatus.IGNORED.value:
        binding.ignored_at = binding.ignored_at or now
    else:
        binding.ignored_at = None
    if binding.route_mode == ChannelConversationRouteMode.DISABLED.value:
        binding.disabled_at = binding.disabled_at or now
    else:
        binding.disabled_at = None
    binding.status = _derive_conversation_status(connection, binding)
    binding.updated_at = now
    session.add(binding)
    await session.flush()
    await session.refresh(binding)
    return ChannelConversationBindingRead.model_validate(binding, from_attributes=True)


async def claim_channel_event(
    session: AsyncSession,
    *,
    connection_id: UUID,
    external_event_id: str,
    event_type: str,
    payload_digest: str | None,
) -> ChannelEventReceipt | None:
    existing_statement = select(ChannelEventReceipt.id).where(
        ChannelEventReceipt.connection_id == connection_id,
        ChannelEventReceipt.external_event_id == external_event_id,
    )
    if (await session.exec(existing_statement)).first() is not None:
        return None

    receipt = ChannelEventReceipt(
        connection_id=connection_id,
        external_event_id=external_event_id,
        event_type=event_type,
        status=ChannelReceiptStatus.PROCESSING.value,
        payload_digest=payload_digest,
    )
    try:
        async with session.begin_nested():
            session.add(receipt)
            await session.flush()
    except IntegrityError:
        return None
    await session.refresh(receipt)
    return receipt


async def mark_channel_event(
    session: AsyncSession,
    receipt: ChannelEventReceipt,
    *,
    status: ChannelReceiptStatus,
    error_message: str | None = None,
) -> None:
    receipt.status = status.value
    receipt.error_message = error_message
    if status in {ChannelReceiptStatus.PROCESSED, ChannelReceiptStatus.FAILED}:
        receipt.processed_at = _utc_now()
    session.add(receipt)
    await session.flush()


async def delete_channel_event_receipts(
    session: AsyncSession,
    *,
    before: datetime,
    limit: int,
) -> int:
    if limit < 1:
        message = "limit must be positive"
        raise ValueError(message)
    statement = (
        select(ChannelEventReceipt.id)
        .where(ChannelEventReceipt.received_at < before)
        .order_by(ChannelEventReceipt.received_at, ChannelEventReceipt.id)
        .limit(limit)
    )
    receipt_ids = list((await session.exec(statement)).all())
    if not receipt_ids:
        await session.rollback()
        return 0
    await session.exec(sa.delete(ChannelEventReceipt).where(ChannelEventReceipt.id.in_(receipt_ids)))
    await session.commit()
    return len(receipt_ids)
