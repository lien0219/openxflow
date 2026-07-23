"""Management API for OpenXFlow communication channels."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import AnyHttpUrl, BaseModel
from sqlalchemy.exc import IntegrityError

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.adapters.telegram import TelegramChannelAdapter
from langflow.channels.services.conversation_validation import validate_conversation_binding_resources
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
    ChannelConnectionStatus,
    ChannelConnectionUpdate,
    ChannelConversationBindingRead,
    ChannelConversationBindingUpsert,
    ChannelIdentityCreate,
    ChannelIdentityRead,
)

router = APIRouter(prefix="/channels", tags=["Channels"])


class TelegramWebhookConfigureRequest(BaseModel):
    public_base_url: AnyHttpUrl
    drop_pending_updates: bool = False


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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A channel connection with this name already exists",
        ) from exc


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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A channel connection with this name already exists",
        ) from exc


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
        result = await build_channel_adapter(connection).healthcheck()
        if (
            connection.channel_type == "dingtalk"
            and connection.connection_mode == "stream"
            and result.get("stream_sdk_available") is False
        ):
            raise RuntimeError(
                "DingTalk credentials are valid, but the Stream runtime is unavailable. "
                "Install dingtalk-stream>=0.24.3 on the OpenXFlow server."
            )
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    except Exception as exc:
        connection.status = ChannelConnectionStatus.ERROR.value
        connection.last_error = str(exc)[:2000]
        connection.updated_at = datetime.now(timezone.utc)
        db.add(connection)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    connection.status = ChannelConnectionStatus.CONNECTED.value
    connection.last_error = None
    connection.last_connected_at = datetime.now(timezone.utc)
    connection.updated_at = datetime.now(timezone.utc)
    db.add(connection)
    await db.commit()
    return result


@router.post("/{connection_id}/telegram/webhook")
async def configure_telegram_webhook(
    connection_id: UUID,
    payload: TelegramWebhookConfigureRequest,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> dict[str, Any]:
    connection = await _owned_connection_or_404(db, current_user.id, connection_id)
    adapter = build_channel_adapter(connection)
    if not isinstance(adapter, TelegramChannelAdapter):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection is not a Telegram channel")

    webhook_url = f"{str(payload.public_base_url).rstrip('/')}/api/v1/channel-webhooks/telegram/{connection_id}"
    try:
        configured = await adapter.set_webhook(
            webhook_url,
            drop_pending_updates=payload.drop_pending_updates,
        )
    except Exception as exc:
        connection.status = ChannelConnectionStatus.ERROR.value
        connection.last_error = str(exc)[:2000]
        connection.updated_at = datetime.now(timezone.utc)
        db.add(connection)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Telegram webhook configuration failed"
        ) from exc

    connection.status = ChannelConnectionStatus.CONNECTED.value
    connection.last_error = None
    connection.last_connected_at = datetime.now(timezone.utc)
    connection.updated_at = datetime.now(timezone.utc)
    db.add(connection)
    await db.commit()
    return {"ok": configured, "webhook_url": webhook_url}


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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot bind this channel identity to another user",
        )
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
    await validate_conversation_binding_resources(db, current_user, payload)
    result = await upsert_channel_conversation_binding(db, connection_id, payload)
    await db.commit()
    return result
