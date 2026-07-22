"""CRUD helpers for communication-channel persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.security.credentials import decrypt_credentials, encrypt_credentials, list_credential_keys
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConnectionCreate,
    ChannelConnectionRead,
    ChannelConnectionUpdate,
    ChannelConversationBinding,
    ChannelConversationBindingRead,
    ChannelConversationBindingUpsert,
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
        settings_data=connection.settings_data,
        status=connection.status,
        configured_credential_keys=list_credential_keys(connection.credentials_encrypted),
        last_connected_at=connection.last_connected_at,
        last_error=connection.last_error,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


async def create_channel_connection(
    session: AsyncSession,
    user_id: UUID,
    payload: ChannelConnectionCreate,
) -> ChannelConnectionRead:
    connection = ChannelConnection(
        user_id=user_id,
        name=payload.name,
        channel_type=payload.channel_type,
        enabled=payload.enabled,
        connection_mode=payload.connection_mode,
        settings_data=payload.settings_data,
        credentials_encrypted=encrypt_credentials(payload.credentials),
    )
    session.add(connection)
    await session.flush()
    await session.refresh(connection)
    return _connection_read(connection)


async def list_channel_connections(session: AsyncSession, user_id: UUID) -> list[ChannelConnectionRead]:
    statement = select(ChannelConnection).where(ChannelConnection.user_id == user_id).order_by(ChannelConnection.created_at)
    rows = (await session.exec(statement)).all()
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
    return (await session.exec(statement)).first()


async def update_channel_connection(
    session: AsyncSession,
    connection: ChannelConnection,
    payload: ChannelConnectionUpdate,
) -> ChannelConnectionRead:
    changes = payload.model_dump(exclude_unset=True, exclude={"credentials"})
    for key, value in changes.items():
        setattr(connection, key, value)

    if payload.credentials is not None:
        credentials = decrypt_credentials(connection.credentials_encrypted)
        credentials.update(payload.credentials)
        connection.credentials_encrypted = encrypt_credentials(credentials)

    connection.updated_at = _utc_now()
    session.add(connection)
    await session.flush()
    await session.refresh(connection)
    return _connection_read(connection)


async def delete_channel_connection(session: AsyncSession, connection: ChannelConnection) -> None:
    await session.delete(connection)
    await session.flush()


async def list_channel_identities(
    session: AsyncSession,
    connection_id: UUID,
) -> list[ChannelIdentityRead]:
    statement = select(ChannelIdentity).where(ChannelIdentity.connection_id == connection_id).order_by(ChannelIdentity.bound_at)
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

    if identity is None:
        identity = ChannelIdentity(connection_id=connection_id, **values)
    else:
        for key, value in values.items():
            setattr(identity, key, value)
        identity.updated_at = _utc_now()

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
) -> list[ChannelConversationBindingRead]:
    statement = (
        select(ChannelConversationBinding)
        .where(ChannelConversationBinding.connection_id == connection_id)
        .order_by(ChannelConversationBinding.created_at)
    )
    rows = (await session.exec(statement)).all()
    return [ChannelConversationBindingRead.model_validate(row, from_attributes=True) for row in rows]


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
        binding = ChannelConversationBinding(connection_id=connection_id, **values)
    else:
        for key, value in values.items():
            setattr(binding, key, value)
        binding.updated_at = _utc_now()

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
    receipt = ChannelEventReceipt(
        connection_id=connection_id,
        external_event_id=external_event_id,
        event_type=event_type,
        status=ChannelReceiptStatus.PROCESSING.value,
        payload_digest=payload_digest,
    )
    session.add(receipt)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
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
