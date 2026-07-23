"""Unauthenticated provider callbacks protected by provider-level signatures."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from langflow.api.utils import DbSession
from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.adapters.wecom import WeComChannelAdapter
from langflow.channels.services.dingtalk_stream import channel_stream_lifespan
from langflow.channels.services.webhook_processing import (
    process_reserved_provider_webhook,
    release_provider_webhook_slot,
    reserve_provider_webhook_slot,
    webhook_limiter_snapshot,
)
from langflow.services.database.models.channel.model import ChannelConnection

router = APIRouter(
    prefix="/channel-webhooks",
    tags=["Channel Webhooks"],
    lifespan=channel_stream_lifespan,
)


async def _validate_and_schedule_provider_event(
    *,
    connection_id: UUID,
    request: Request,
    db: DbSession,
    background_tasks: BackgroundTasks,
    expected_channel_type: str,
    provider_headers: dict[str, str] | None = None,
) -> dict[str, bool]:
    connection = await db.get(ChannelConnection, connection_id)
    if connection is None or connection.channel_type != expected_channel_type or not connection.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")

    payload = await request.body()
    headers = {key.lower(): value for key, value in request.headers.items()}
    headers.update({key.lower(): value for key, value in (provider_headers or {}).items()})
    adapter = build_channel_adapter(connection)

    try:
        if not await adapter.verify_event(headers, payload):
            raise PermissionError("Channel event signature verification failed")
        event = await adapter.parse_event(headers, payload)
        if event.connection_id != connection_id or event.channel.value != expected_channel_type:
            raise ValueError("Parsed channel event does not match the configured connection")
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid channel webhook signature") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not reserve_provider_webhook_slot():
        snapshot = webhook_limiter_snapshot()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Channel webhook queue is full "
                f"({snapshot.pending}/{snapshot.max_pending}); retry later"
            ),
            headers={"Retry-After": "1"},
        )

    try:
        background_tasks.add_task(
            process_reserved_provider_webhook,
            connection_id=connection_id,
            expected_channel_type=expected_channel_type,
            headers=headers,
            payload=payload,
        )
    except Exception:
        release_provider_webhook_slot()
        raise
    return {"ok": True}


@router.post("/telegram/{connection_id}", status_code=status.HTTP_200_OK)
async def receive_telegram_webhook(
    connection_id: UUID,
    request: Request,
    db: DbSession,
    background_tasks: BackgroundTasks,
) -> dict[str, bool]:
    return await _validate_and_schedule_provider_event(
        connection_id=connection_id,
        request=request,
        db=db,
        background_tasks=background_tasks,
        expected_channel_type="telegram",
    )


@router.post("/feishu/{connection_id}", status_code=status.HTTP_200_OK)
async def receive_feishu_webhook(
    connection_id: UUID,
    request: Request,
    db: DbSession,
    background_tasks: BackgroundTasks,
) -> dict[str, bool | str]:
    connection = await db.get(ChannelConnection, connection_id)
    if connection is None or connection.channel_type != "feishu" or not connection.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")

    payload = await request.body()
    adapter = build_channel_adapter(connection)
    if not isinstance(adapter, FeishuChannelAdapter):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection is not a Feishu channel")

    headers = {key.lower(): value for key, value in request.headers.items()}
    if adapter.is_url_verification(payload):
        if not await adapter.verify_event(headers, payload):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Feishu verification token")
        return {"challenge": adapter.get_url_verification_challenge(payload)}

    return await _validate_and_schedule_provider_event(
        connection_id=connection_id,
        request=request,
        db=db,
        background_tasks=background_tasks,
        expected_channel_type="feishu",
    )


@router.post("/dingtalk/{connection_id}", status_code=status.HTTP_200_OK)
async def receive_dingtalk_webhook(
    connection_id: UUID,
    request: Request,
    db: DbSession,
    background_tasks: BackgroundTasks,
) -> dict[str, bool]:
    """Compatibility callback for deployments choosing signed HTTP mode over Stream."""
    return await _validate_and_schedule_provider_event(
        connection_id=connection_id,
        request=request,
        db=db,
        background_tasks=background_tasks,
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
    background_tasks: BackgroundTasks,
    msg_signature: str = Query(alias="msg_signature"),
    timestamp: str = Query(),
    nonce: str = Query(),
) -> PlainTextResponse:
    await _validate_and_schedule_provider_event(
        connection_id=connection_id,
        request=request,
        db=db,
        background_tasks=background_tasks,
        expected_channel_type="wecom",
        provider_headers={
            "x-wecom-msg-signature": msg_signature,
            "x-wecom-timestamp": timestamp,
            "x-wecom-nonce": nonce,
        },
    )
    return PlainTextResponse("success")
