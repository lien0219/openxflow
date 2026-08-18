"""Unified authorization helpers for every channel management API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from fastapi import HTTPException, status
from sqlmodel import select

from langflow.channels.services.service_identity import (
    ensure_channel_service_identity,
    is_managed_channel_service_user,
)
from langflow.services.authorization import ChannelAction
from langflow.services.authorization.guards import ensure_permission
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConnectionRead,
    ChannelIdentity,
    ChannelIdentityStatus,
)
from langflow.services.deps import get_authorization_service, get_settings_service

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from langflow.services.database.models.user.model import User

_NOT_FOUND = "Channel connection not found"


async def authorize_channel_connection(
    session: AsyncSession,
    current_user: User,
    connection_id: UUID,
    action: ChannelAction | str,
    *,
    allow_bound_read: bool = False,
) -> ChannelConnection:
    """Load a connection and enforce one consistent owner/RBAC rule.

    Owners and active superusers are allowed. Bound members can optionally read
    the connection. Non-owner RBAC access is evaluated only when AUTHZ is
    enabled; this preserves secure owner-only behaviour in legacy deployments.
    Denials are returned as 404 so connection IDs cannot be enumerated.
    """
    connection = await session.get(ChannelConnection, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    if not current_user.is_active or is_managed_channel_service_user(current_user, connection_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    if current_user.is_superuser or connection.user_id == current_user.id:
        return connection

    normalized_action = action.value if isinstance(action, ChannelAction) else str(action).strip().lower()
    if allow_bound_read and normalized_action == ChannelAction.READ.value:
        identity_statement = select(ChannelIdentity.id).where(
            ChannelIdentity.connection_id == connection_id,
            ChannelIdentity.openxflow_user_id == current_user.id,
            ChannelIdentity.status == ChannelIdentityStatus.BOUND.value,
        )
        if (await session.exec(identity_statement)).first() is not None:
            return connection

    if not get_settings_service().auth_settings.AUTHZ_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    try:
        await ensure_permission(
            current_user,
            domain=f"channel:{connection.id}",
            obj=f"channel:{connection.id}",
            act=normalized_action,
            context={
                "channel_user_id": connection.user_id,
                "channel_connection_id": connection.id,
                "connection_id": connection.id,
            },
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
        raise
    return connection


async def list_authorized_channel_connections(
    session: AsyncSession,
    current_user: User,
) -> list[ChannelConnectionRead]:
    """List owned and RBAC/share-visible connections with stable ordering."""
    from langflow.services.database.models.channel.crud import _connection_read

    statement = select(ChannelConnection)
    if not current_user.is_superuser:
        settings = get_settings_service()
        if not settings.auth_settings.AUTHZ_ENABLED:
            statement = statement.where(ChannelConnection.user_id == current_user.id)
        else:
            visible_ids = await get_authorization_service().list_visible_resource_ids(
                user_id=current_user.id,
                resource_type="channel",
                act=ChannelAction.READ.value,
                context={"is_superuser": current_user.is_superuser},
            )
            if visible_ids is not None:
                visibility = ChannelConnection.user_id == current_user.id
                if visible_ids:
                    visibility = sa.or_(visibility, ChannelConnection.id.in_(visible_ids))
                statement = statement.where(visibility)

    rows = (await session.exec(statement.order_by(ChannelConnection.created_at, ChannelConnection.id))).all()
    for row in rows:
        await ensure_channel_service_identity(session, row)
    return [_connection_read(row) for row in rows]
