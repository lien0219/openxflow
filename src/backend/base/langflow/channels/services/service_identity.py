"""Lifecycle for least-privileged channel service accounts."""

from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.initial_setup.setup import get_or_create_default_folder
from langflow.services.database.models.channel.model import ChannelConnection
from langflow.services.database.models.user.model import User
from langflow.services.deps import get_auth_service

_MARKER = "channel_service_identity"
_CONNECTION_MARKER = "channel_connection_id"


def managed_service_username(connection_id: UUID) -> str:
    return f"channel-service-{connection_id.hex}@openxflow.internal"


def is_managed_channel_service_user(user: User | None, connection_id: UUID) -> bool:
    if user is None or not isinstance(user.optins, dict):
        return False
    return bool(user.optins.get(_MARKER)) and user.optins.get(_CONNECTION_MARKER) == str(connection_id)


async def ensure_channel_service_identity(
    session: AsyncSession,
    connection: ChannelConnection,
) -> User:
    """Return the dedicated service user, replacing unsafe legacy owner fallbacks."""
    current = await session.get(User, connection.service_user_id) if connection.service_user_id else None
    if is_managed_channel_service_user(current, connection.id):
        return current

    username = managed_service_username(connection.id)
    service_user = (await session.exec(select(User).where(User.username == username))).first()
    if service_user is None:
        service_user = User(
            username=username,
            password=get_auth_service().get_password_hash(secrets.token_urlsafe(48)),
            is_active=True,
            is_superuser=False,
            optins={
                _MARKER: True,
                _CONNECTION_MARKER: str(connection.id),
                "channel_provider": connection.channel_type,
            },
        )
        try:
            async with session.begin_nested():
                session.add(service_user)
                await session.flush()
        except IntegrityError:
            service_user = (await session.exec(select(User).where(User.username == username))).first()
            if service_user is None:
                raise

    if not is_managed_channel_service_user(service_user, connection.id):
        raise RuntimeError("Reserved channel service username is already in use")
    if service_user.is_superuser:
        raise RuntimeError("Channel service identity must never be a superuser")

    await get_or_create_default_folder(session, service_user.id)
    connection.service_user_id = service_user.id
    session.add(connection)
    await session.flush()
    return service_user


async def remove_channel_service_identity(
    session: AsyncSession,
    connection: ChannelConnection,
) -> None:
    service_user = await session.get(User, connection.service_user_id) if connection.service_user_id else None
    if not is_managed_channel_service_user(service_user, connection.id):
        return
    connection.service_user_id = None
    session.add(connection)
    await session.flush()
    await session.delete(service_user)
    await session.flush()
