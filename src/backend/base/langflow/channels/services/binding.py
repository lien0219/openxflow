"""Secure account-binding challenges for external communication channels."""

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
    if identity is not None and identity.openxflow_user_id != openxflow_user_id:
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
        )
    else:
        identity.status = ChannelIdentityStatus.BOUND.value
        identity.display_name = challenge.display_name or identity.display_name
        identity.profile_data = challenge.profile_data
        identity.updated_at = now

    challenge.used_at = now
    session.add(identity)
    session.add(challenge)
    await session.flush()
    await session.refresh(identity)
    return ChannelIdentityRead.model_validate(identity, from_attributes=True)
