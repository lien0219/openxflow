"""Persistent idempotency guard for inbound channel events."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from langflow.services.database.models.channel.crud import claim_channel_event, mark_channel_event
from langflow.services.database.models.channel.model import ChannelEventReceipt, ChannelReceiptStatus

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from langflow.channels.domain.models import ChannelEvent


class ChannelEventDeduplicator:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def claim(self, event: ChannelEvent, payload: bytes) -> ChannelEventReceipt | None:
        payload_digest = hashlib.sha256(payload).hexdigest()
        return await claim_channel_event(
            self.session,
            connection_id=event.connection_id,
            external_event_id=event.event_id,
            event_type=event.event_type.value,
            payload_digest=payload_digest,
        )

    async def complete(self, receipt: ChannelEventReceipt) -> None:
        await mark_channel_event(
            self.session,
            receipt,
            status=ChannelReceiptStatus.PROCESSED,
        )

    async def fail(self, receipt: ChannelEventReceipt, error: Exception) -> None:
        await mark_channel_event(
            self.session,
            receipt,
            status=ChannelReceiptStatus.FAILED,
            error_message=str(error)[:2000],
        )
