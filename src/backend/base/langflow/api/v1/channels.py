"""Management API for OpenXFlow communication channels."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.channels.adapters.factory import build_channel_adapter
from langflow.services.database.models.channel.crud import (
    create_channel_connection,
    delete_channel_connection,
    delete_channel_identity,
    get_owned_channel_connection,
    list_channel_connections,
    list_channel_identities,
    list_conversation_bindings,
    update_channel_connection,
    upsert_channel_conversation_binding,
    upsert_channel_identity,
)
from langflow.services.database.models.channel.model import (
    ChannelConnectionCreate,
    ChannelConnectionRead,
    ChannelConnectionUpdate,
    ChannelConversationBindingRead,
    ChannelConversationBindingUpsert,
    ChannelIdentityCreate,
    ChannelIdentityRead,
)

router = APIRouter(prefix="/channels", tags=["Channels"])


async def _owned_connection_or_404(db: DbSession, user_id: UUID, connection_id: UUID):
    connection = await get_owned_channel_connection(db, user_id, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")
    return connection


@router.get("/", response_model=list[ChannelConnectionRead])
async def read_channel_connections(
    db: DbSession,
    current_user: CurrentActiveUser,
) -> list[ChannelConnectionRead]:
    return await list_channel_connections(db, current_user.id)


@router.post("/", response_model=ChannelConnectionRead, status_code=status.HTTP_201_CREATED)
async def create_channel_connection_route(
    payload: ChannelConnectionCreate,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> ChannelConnectionRead:
    try:
        result = await create_channel_connection(db, current_user.id, payload)
        await db.commit()
        return result
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A channel connection with this name already exists") from exc


@router.patch("/{connection_id}", response_model=ChannelConnectionRead)
async def update_channel_connection_route(
    connection_id: UUID,
    payload: ChannelConnectionUpdate,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> ChannelConnectionRead:
    connection = await _owned_connection_or_404(db, current_user.id, connection_id)
    try:
        result = await update_channel_connection(db, connection, payload)
        await db.commit()
        return result
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A channel connection with this name already exists") from exc


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel_connection_route(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> Response:
    connection = await _owned_connection_or_404(db, current_user.id, connection_id)
    await delete_channel_connection(db, connection)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{connection_id}/test")
async def test_channel_connection_route(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> dict[str, Any]:
    connection = await _owned_connection_or_404(db, current_user.id, connection_id)
    try:
        return await build_channel_adapter(connection).healthcheck()
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc


@router.get("/{connection_id}/identities", response_model=list[ChannelIdentityRead])
async def read_channel_identities(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> list[ChannelIdentityRead]:
    await _owned_connection_or_404(db, current_user.id, connection_id)
    return await list_channel_identities(db, connection_id)


@router.put("/{connection_id}/identities", response_model=ChannelIdentityRead)
async def put_channel_identity(
    connection_id: UUID,
    payload: ChannelIdentityCreate,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> ChannelIdentityRead:
    await _owned_connection_or_404(db, current_user.id, connection_id)
    if payload.openxflow_user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot bind this channel identity to another user")
    result = await upsert_channel_identity(db, connection_id, payload)
    await db.commit()
    return result


@router.delete("/{connection_id}/identities/{identity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_channel_identity(
    connection_id: UUID,
    identity_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> Response:
    await _owned_connection_or_404(db, current_user.id, connection_id)
    if not await delete_channel_identity(db, connection_id, identity_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel identity not found")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{connection_id}/conversations", response_model=list[ChannelConversationBindingRead])
async def read_channel_conversations(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> list[ChannelConversationBindingRead]:
    await _owned_connection_or_404(db, current_user.id, connection_id)
    return await list_conversation_bindings(db, connection_id)


@router.put("/{connection_id}/conversations", response_model=ChannelConversationBindingRead)
async def put_channel_conversation(
    connection_id: UUID,
    payload: ChannelConversationBindingUpsert,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> ChannelConversationBindingRead:
    await _owned_connection_or_404(db, current_user.id, connection_id)
    result = await upsert_channel_conversation_binding(db, connection_id, payload)
    await db.commit()
    return result
