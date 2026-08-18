"""Persistent idempotency guard for inbound channel events."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from sqlmodel import select

from langflow.services.database.models.channel.crud import claim_channel_event, mark_channel_event
from langflow.services.database.models.channel.model import ChannelEventReceipt, ChannelReceiptStatus

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from langflow.channels.domain.models import ChannelEvent


class ChannelEventDeduplicator:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def claim(self, event: ChannelEvent, payload: bytes) -> ChannelEventReceipt | None:
        """Claim an event and release SQLite's writer transaction immediately.

        The gateway persists message records through independent short-lived
        sessions after this method returns. Keeping the receipt insert uncommitted
        would make those sessions compete with the same event task for SQLite's
        single writer lock. Committing the claim here preserves idempotency while
        ensuring the callback does not carry a write transaction across network
        calls or workflow execution.
        """
        payload_digest = hashlib.sha256(payload).hexdigest()
        statement = select(ChannelEventReceipt).where(
            ChannelEventReceipt.connection_id == event.connection_id,
            ChannelEventReceipt.external_event_id == event.event_id,
        )
        existing = (await self.session.exec(statement)).first()
        if existing is not None:
            if existing.status != ChannelReceiptStatus.FAILED.value:
                return None
            existing.status = ChannelReceiptStatus.PROCESSING.value
            existing.event_type = event.event_type.value
            existing.payload_digest = payload_digest
            existing.error_message = None
            existing.processed_at = None
            self.session.add(existing)
            await self.session.flush()
            await self.session.commit()
            return existing

        receipt = await claim_channel_event(
            self.session,
            connection_id=event.connection_id,
            external_event_id=event.event_id,
            event_type=event.event_type.value,
            payload_digest=payload_digest,
        )
        await self.session.commit()
        return receipt

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
