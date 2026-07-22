"""Unauthenticated provider callbacks protected by provider-level signatures."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from langflow.api.utils import DbSession
from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.domain.exceptions import DuplicateChannelEventError
from langflow.channels.domain.models import ChannelEvent, ChannelMessage
from langflow.channels.services.deduplication import ChannelEventDeduplicator
from langflow.channels.services.gateway import ChannelGateway
from langflow.services.database.models.channel.model import ChannelConnection

router = APIRouter(prefix="/channel-webhooks", tags=["Channel Webhooks"])


async def _default_channel_handler(event: ChannelEvent) -> ChannelMessage | None:
    """Temporary transport-level handler until workflow dispatch is wired."""
    if event.event_type.value == "message.command" and event.message.text in {"/start", "/help"}:
        return ChannelMessage(
            title="OpenXFlow",
            text=(
                "渠道连接成功。下一阶段将启用账号绑定、工作流运行、知识库文件上传与问答。"
            ),
        )
    return None


@router.post("/telegram/{connection_id}", status_code=status.HTTP_200_OK)
async def receive_telegram_webhook(
    connection_id: UUID,
    request: Request,
    db: DbSession,
) -> dict[str, bool]:
    connection = await db.get(ChannelConnection, connection_id)
    if connection is None or connection.channel_type != "telegram" or not connection.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")

    payload = await request.body()
    adapter = build_channel_adapter(connection)
    gateway = ChannelGateway()
    gateway.register_adapter(connection_id, adapter)
    deduplicator = ChannelEventDeduplicator(db)

    try:
        await gateway.receive(
            connection_id,
            {key.lower(): value for key, value in request.headers.items()},
            payload,
            _default_channel_handler,
            deduplicator=deduplicator,
        )
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Telegram webhook signature") from exc
    except DuplicateChannelEventError:
        await db.rollback()
        return {"ok": True}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()
    return {"ok": True}
