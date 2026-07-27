"""Unauthenticated provider callbacks protected by provider-level signatures."""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from starlette.requests import ClientDisconnect

from langflow.api.utils import DbSession
from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.adapters.wecom import WeComChannelAdapter
from langflow.channels.adapters.wecom_ai import WeComAIBotChannelAdapter
from langflow.channels.security.webhook_headers import durable_webhook_headers
from langflow.channels.services.dingtalk_stream import channel_stream_lifespan
from langflow.channels.services.outbound_delivery_maintenance import (
    outbound_delivery_maintenance_lifespan,
)
from langflow.channels.services.provider_http import close_provider_http_clients
from langflow.channels.services.queueing import resolve_channel_queue_descriptor
from langflow.channels.services.runtime_config import durable_webhook_job_config, webhook_max_body_bytes
from langflow.channels.services.webhook_jobs import (
    durable_webhook_job_lifespan,
    enqueue_provider_webhook_job,
)
from langflow.channels.services.webhook_processing import (
    process_reserved_provider_webhook,
    record_provider_webhook_client_disconnect,
    release_provider_webhook_slot,
    reserve_provider_webhook_slot,
    webhook_limiter_snapshot,
)
from langflow.channels.services.wecom_ai_runtime import (
    process_wecom_ai_event,
    wecom_ai_response_runtime,
)
from langflow.services.database.models.channel.model import ChannelConnection

_SIGNATURE_VERIFICATION_FAILED = "Channel event signature verification failed"
_EVENT_CONNECTION_MISMATCH = "Parsed channel event does not match the configured connection"


@asynccontextmanager
async def channel_webhook_lifespan(app):  # type: ignore[no-untyped-def]
    """Run channel workers and close pooled provider clients on application shutdown."""
    try:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(channel_stream_lifespan(app))
            await stack.enter_async_context(durable_webhook_job_lifespan(app))
            await stack.enter_async_context(outbound_delivery_maintenance_lifespan(app))
            yield
    finally:
        await close_provider_http_clients()


router = APIRouter(
    prefix="/channel-webhooks",
    tags=["Channel Webhooks"],
    lifespan=channel_webhook_lifespan,
)


async def _read_limited_body(request: Request) -> bytes:
    """Read an ASGI request incrementally and stop as soon as the limit is exceeded."""
    max_body_bytes = webhook_max_body_bytes()
    raw_content_length = request.headers.get("content-length")
    if raw_content_length is not None:
        try:
            content_length = int(raw_content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length header",
            ) from exc
        if content_length < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length header",
            )
        if content_length > max_body_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Channel webhook body exceeds {max_body_bytes} bytes",
            )

    payload = bytearray()
    try:
        async for chunk in request.stream():
            if not chunk:
                continue
            if len(payload) + len(chunk) > max_body_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Channel webhook body exceeds {max_body_bytes} bytes",
                )
            payload.extend(chunk)
    except ClientDisconnect as exc:
        record_provider_webhook_client_disconnect()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client disconnected before the channel webhook body was fully received",
        ) from exc
    return bytes(payload)


def _request_headers(
    request: Request,
    provider_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = {key.lower(): value for key, value in request.headers.items()}
    headers.update({key.lower(): value for key, value in (provider_headers or {}).items()})
    return headers


async def _validate_and_schedule_provider_event(
    *,
    connection_id: UUID,
    request: Request,
    db: DbSession,
    background_tasks: BackgroundTasks,
    expected_channel_type: str,
    provider_headers: dict[str, str] | None = None,
    preloaded_payload: bytes | None = None,
) -> dict[str, bool]:
    connection = await db.get(ChannelConnection, connection_id)
    if connection is None or connection.channel_type != expected_channel_type or not connection.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")

    payload = preloaded_payload if preloaded_payload is not None else await _read_limited_body(request)
    headers = _request_headers(request, provider_headers)
    adapter = build_channel_adapter(connection)

    try:
        if not await adapter.verify_event(headers, payload):
            raise PermissionError(_SIGNATURE_VERIFICATION_FAILED)
        event = await adapter.parse_event(headers, payload)
        if event.connection_id != connection_id or event.channel.value != expected_channel_type:
            raise ValueError(_EVENT_CONNECTION_MISMATCH)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid channel webhook signature") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if durable_webhook_job_config().enabled:
        queue = await resolve_channel_queue_descriptor(db, connection, event)
        await enqueue_provider_webhook_job(
            db,
            connection_id=connection_id,
            channel_type=expected_channel_type,
            external_event_id=event.event_id,
            headers=durable_webhook_headers(expected_channel_type, headers),
            payload=payload,
            connection=connection,
            external_conversation_id=queue.external_conversation_id,
            external_user_id=queue.external_user_id,
            conversation_type=queue.conversation_type,
            queue_key=queue.queue_key,
        )
        return {"ok": True}

    reservation = reserve_provider_webhook_slot(len(payload))
    if reservation is None:
        snapshot = webhook_limiter_snapshot()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Channel webhook capacity is full "
                f"(jobs {snapshot.pending}/{snapshot.max_pending}, "
                f"bytes {snapshot.pending_bytes}/{snapshot.max_pending_bytes}); retry later"
            ),
            headers={"Retry-After": "1"},
        )

    try:
        background_tasks.add_task(
            process_reserved_provider_webhook,
            reservation=reservation,
            connection_id=connection_id,
            expected_channel_type=expected_channel_type,
            headers=headers,
            payload=payload,
        )
    except Exception:
        release_provider_webhook_slot(reservation)
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

    payload = await _read_limited_body(request)
    adapter = build_channel_adapter(connection)
    if not isinstance(adapter, FeishuChannelAdapter):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection is not a Feishu channel")

    headers = _request_headers(request)
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
        preloaded_payload=payload,
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
    msg_signature: Annotated[str, Query(alias="msg_signature")],
    timestamp: Annotated[str, Query()],
    nonce: Annotated[str, Query()],
    echo: Annotated[str, Query(alias="echostr")],
) -> PlainTextResponse:
    connection = await db.get(ChannelConnection, connection_id)
    if connection is None or connection.channel_type != "wecom" or not connection.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")
    adapter = build_channel_adapter(connection)
    if not isinstance(adapter, (WeComAIBotChannelAdapter, WeComChannelAdapter)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connection is not a WeCom channel",
        )
    try:
        plaintext = adapter.verify_url(
            signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
            echo=echo,
        )
    except (PermissionError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid WeCom callback verification",
        ) from exc
    return PlainTextResponse(plaintext)


async def _receive_wecom_ai_callback(
    *,
    connection: ChannelConnection,
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str,
    timestamp: str,
    nonce: str,
) -> PlainTextResponse:
    adapter = build_channel_adapter(connection)
    if not isinstance(adapter, WeComAIBotChannelAdapter):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection is not a WeCom AI Bot")
    payload = await _read_limited_body(request)
    headers = _request_headers(
        request,
        {
            "x-wecom-msg-signature": msg_signature,
            "x-wecom-timestamp": timestamp,
            "x-wecom-nonce": nonce,
        },
    )
    try:
        decrypted = adapter.decrypt_event(headers, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid WeCom AI Bot callback") from exc

    msg_type = str(decrypted.get("msgtype") or "").lower()
    runtime = wecom_ai_response_runtime()
    if msg_type == "stream":
        stream = decrypted.get("stream") if isinstance(decrypted.get("stream"), dict) else {}
        stream_id = str(stream.get("id") or "")
        state = await runtime.poll(stream_id) if stream_id else None
        response = adapter.encrypted_stream_response(
            stream_id=stream_id or "unknown",
            content=state.content if state is not None else "",
            finish=state.finished if state is not None else True,
            timestamp=timestamp,
            nonce=nonce,
        )
        return PlainTextResponse(response, media_type="application/json")

    if msg_type == "event":
        return PlainTextResponse("success")

    try:
        event = adapter.parse_decrypted_event(decrypted)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    state, is_new = await runtime.reserve(connection.id, event.event_id)
    if is_new:
        background_tasks.add_task(
            process_wecom_ai_event,
            connection_id=connection.id,
            event=event,
            stream_id=state.stream_id,
        )
    response = adapter.encrypted_stream_response(
        stream_id=state.stream_id,
        content=state.content,
        finish=state.finished,
        timestamp=timestamp,
        nonce=nonce,
    )
    return PlainTextResponse(response, media_type="application/json")


@router.post("/wecom/{connection_id}", response_class=PlainTextResponse)
async def receive_wecom_callback(
    connection_id: UUID,
    request: Request,
    db: DbSession,
    background_tasks: BackgroundTasks,
    msg_signature: Annotated[str, Query(alias="msg_signature")],
    timestamp: Annotated[str, Query()],
    nonce: Annotated[str, Query()],
) -> PlainTextResponse:
    connection = await db.get(ChannelConnection, connection_id)
    if connection is None or connection.channel_type != "wecom" or not connection.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")
    if connection.connection_mode == "ai_bot":
        return await _receive_wecom_ai_callback(
            connection=connection,
            request=request,
            background_tasks=background_tasks,
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
        )
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
