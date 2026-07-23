"""Unauthenticated provider callbacks protected by provider-level signatures."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from langflow.api.utils import DbSession
from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.adapters.wecom import WeComChannelAdapter
from langflow.channels.domain.exceptions import DuplicateChannelEventError
from langflow.channels.services.deduplication import ChannelEventDeduplicator
from langflow.channels.services.dingtalk_stream import channel_stream_lifespan
from langflow.channels.services.dispatch import ChannelDispatchService
from langflow.channels.services.gateway import ChannelGateway
from langflow.services.database.models.channel.model import ChannelConnection

router = APIRouter(
    prefix="/channel-webhooks",
    tags=["Channel Webhooks"],
    lifespan=channel_stream_lifespan,
)


async def _receive_provider_event(
    *,
    connection_id: UUID,
    request: Request,
    db: DbSession,
    expected_channel_type: str,
    provider_headers: dict[str, str] | None = None,
) -> dict[str, bool]:
    connection = await db.get(ChannelConnection, connection_id)
    if connection is None or connection.channel_type != expected_channel_type or not connection.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")

    payload = await request.body()
    adapter = build_channel_adapter(connection)
    gateway = ChannelGateway()
    gateway.register_adapter(connection_id, adapter)
    deduplicator = ChannelEventDeduplicator(db)
    dispatcher = ChannelDispatchService(db, connection, adapter)
    normalized_headers = {key.lower(): value for key, value in request.headers.items()}
    normalized_headers.update({key.lower(): value for key, value in (provider_headers or {}).items()})

    try:
        await gateway.receive(
            connection_id,
            normalized_headers,
            payload,
            dispatcher.handle,
            deduplicator=deduplicator,
        )
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid channel webhook signature") from exc
    except DuplicateChannelEventError:
        await db.rollback()
        return {"ok": True}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Channel event processing failed") from exc

    await db.commit()
    return {"ok": True}


@router.post("/telegram/{connection_id}", status_code=status.HTTP_200_OK)
async def receive_telegram_webhook(
    connection_id: UUID,
    request: Request,
    db: DbSession,
) -> dict[str, bool]:
    return await _receive_provider_event(
        connection_id=connection_id,
        request=request,
        db=db,
        expected_channel_type="telegram",
    )


@router.post("/feishu/{connection_id}", status_code=status.HTTP_200_OK)
async def receive_feishu_webhook(
    connection_id: UUID,
    request: Request,
    db: DbSession,
) -> dict[str, bool | str]:
    connection = await db.get(ChannelConnection, connection_id)
    if connection is None or connection.channel_type != "feishu" or not connection.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")

    payload = await request.body()
    adapter = build_channel_adapter(connection)
    if not isinstance(adapter, FeishuChannelAdapter):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection is not a Feishu channel")

    headers = {key.lower(): value for key, value in request.headers.items()}
    if FeishuChannelAdapter.is_url_verification(payload):
        if not await adapter.verify_event(headers, payload):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Feishu verification token")
        return {"challenge": FeishuChannelAdapter.get_url_verification_challenge(payload)}

    return await _receive_provider_event(
        connection_id=connection_id,
        request=request,
        db=db,
        expected_channel_type="feishu",
    )


@router.post("/dingtalk/{connection_id}", status_code=status.HTTP_200_OK)
async def receive_dingtalk_webhook(
    connection_id: UUID,
    request: Request,
    db: DbSession,
) -> dict[str, bool]:
    """Compatibility callback for deployments choosing signed HTTP mode over Stream."""
    return await _receive_provider_event(
        connection_id=connection_id,
        request=request,
        db=db,
        expected_channel_type="dingtalk",
    )


@router.get("/wecom/{connection_id}", response_class=PlainTextResponse)
async def verify_wecom_callback(
    connection_id: UUID,
    db: DbSession,
    msg_signature: str = Query(alias="msg_signature"),
    timestamp: str = Query(),
    nonce: str = Query(),
    echo: str = Query(alias="echostr"),
) -> PlainTextResponse:
    connection = await db.get(ChannelConnection, connection_id)
    if connection is None or connection.channel_type != "wecom" or not connection.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")
    adapter = build_channel_adapter(connection)
    if not isinstance(adapter, WeComChannelAdapter):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection is not a WeCom channel")
    try:
        plaintext = adapter.verify_url(
            signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
            echo=echo,
        )
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid WeCom callback verification") from exc
    return PlainTextResponse(plaintext)


@router.post("/wecom/{connection_id}", response_class=PlainTextResponse)
async def receive_wecom_callback(
    connection_id: UUID,
    request: Request,
    db: DbSession,
    msg_signature: str = Query(alias="msg_signature"),
    timestamp: str = Query(),
    nonce: str = Query(),
) -> PlainTextResponse:
    await _receive_provider_event(
        connection_id=connection_id,
        request=request,
        db=db,
        expected_channel_type="wecom",
        provider_headers={
            "x-wecom-msg-signature": msg_signature,
            "x-wecom-timestamp": timestamp,
            "x-wecom-nonce": nonce,
        },
    )
    return PlainTextResponse("success")
