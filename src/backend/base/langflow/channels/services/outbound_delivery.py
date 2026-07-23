"""Persistent at-most-once guards for durable channel provider deliveries."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from langflow.channels.domain.models import ChannelEvent, ChannelMessage
from langflow.channels.services.outbound_delivery_metrics import (
    record_outbound_delivery_failed,
    record_outbound_delivery_reserved,
    record_outbound_delivery_sent,
    record_outbound_delivery_state_error,
    record_outbound_delivery_suppressed,
)
from langflow.services.database.models.channel.model import utc_now
from langflow.services.database.models.channel.outbound_delivery_model import (
    ChannelOutboundDelivery,
    ChannelOutboundDeliveryKind,
    ChannelOutboundDeliveryStatus,
)
from langflow.services.deps import session_scope

_ACKNOWLEDGEMENT_DIGEST = hashlib.sha256(b"acknowledgement").hexdigest()


@dataclass(frozen=True)
class OutboundDeliveryDecision:
    should_send: bool
    delivery_id: UUID | None


def channel_response_digest(message: ChannelMessage) -> str:
    serialized = json.dumps(
        message.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


async def _reserve_outbound_delivery(
    event: ChannelEvent,
    *,
    delivery_kind: ChannelOutboundDeliveryKind,
    response_digest: str,
) -> OutboundDeliveryDecision:
    async with session_scope() as session:
        existing = (
            await session.exec(
                select(ChannelOutboundDelivery).where(
                    ChannelOutboundDelivery.connection_id == event.connection_id,
                    ChannelOutboundDelivery.external_event_id == event.event_id,
                    ChannelOutboundDelivery.delivery_kind == delivery_kind.value,
                )
            )
        ).first()
        if existing is not None:
            if existing.status != ChannelOutboundDeliveryStatus.FAILED.value:
                record_outbound_delivery_suppressed()
                return OutboundDeliveryDecision(should_send=False, delivery_id=existing.id)
            result = await session.exec(
                sa.update(ChannelOutboundDelivery)
                .where(
                    ChannelOutboundDelivery.id == existing.id,
                    ChannelOutboundDelivery.status == ChannelOutboundDeliveryStatus.FAILED.value,
                )
                .values(
                    status=ChannelOutboundDeliveryStatus.RESERVED.value,
                    response_digest=response_digest,
                    attempts=ChannelOutboundDelivery.attempts + 1,
                    last_error=None,
                    updated_at=utc_now(),
                )
            )
            if result.rowcount != 1:
                await session.rollback()
                record_outbound_delivery_suppressed()
                return OutboundDeliveryDecision(should_send=False, delivery_id=existing.id)
            await session.commit()
            record_outbound_delivery_reserved()
            return OutboundDeliveryDecision(should_send=True, delivery_id=existing.id)

        delivery = ChannelOutboundDelivery(
            connection_id=event.connection_id,
            external_event_id=event.event_id,
            delivery_kind=delivery_kind.value,
            response_digest=response_digest,
        )
        session.add(delivery)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            concurrent = (
                await session.exec(
                    select(ChannelOutboundDelivery.id).where(
                        ChannelOutboundDelivery.connection_id == event.connection_id,
                        ChannelOutboundDelivery.external_event_id == event.event_id,
                        ChannelOutboundDelivery.delivery_kind == delivery_kind.value,
                    )
                )
            ).first()
            if concurrent is None:
                record_outbound_delivery_state_error()
                raise
            record_outbound_delivery_suppressed()
            return OutboundDeliveryDecision(should_send=False, delivery_id=concurrent)
        record_outbound_delivery_reserved()
        return OutboundDeliveryDecision(should_send=True, delivery_id=delivery.id)


async def reserve_outbound_delivery(event: ChannelEvent, message: ChannelMessage) -> OutboundDeliveryDecision:
    return await _reserve_outbound_delivery(
        event,
        delivery_kind=ChannelOutboundDeliveryKind.RESPONSE,
        response_digest=channel_response_digest(message),
    )


async def reserve_outbound_acknowledgement(event: ChannelEvent) -> OutboundDeliveryDecision:
    return await _reserve_outbound_delivery(
        event,
        delivery_kind=ChannelOutboundDeliveryKind.ACKNOWLEDGEMENT,
        response_digest=_ACKNOWLEDGEMENT_DIGEST,
    )


async def mark_outbound_delivery_sent(delivery_id: UUID, provider_message_id: str | None) -> None:
    now = utc_now()
    try:
        async with session_scope() as session:
            result = await session.exec(
                sa.update(ChannelOutboundDelivery)
                .where(
                    ChannelOutboundDelivery.id == delivery_id,
                    ChannelOutboundDelivery.status == ChannelOutboundDeliveryStatus.RESERVED.value,
                )
                .values(
                    status=ChannelOutboundDeliveryStatus.SENT.value,
                    provider_message_id=provider_message_id,
                    last_error=None,
                    sent_at=now,
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                await session.rollback()
                raise RuntimeError("Outbound delivery reservation is no longer active")
            await session.commit()
    except Exception:
        record_outbound_delivery_state_error()
        raise
    record_outbound_delivery_sent()


async def mark_outbound_delivery_failed(delivery_id: UUID, error: Exception) -> None:
    try:
        async with session_scope() as session:
            result = await session.exec(
                sa.update(ChannelOutboundDelivery)
                .where(
                    ChannelOutboundDelivery.id == delivery_id,
                    ChannelOutboundDelivery.status == ChannelOutboundDeliveryStatus.RESERVED.value,
                )
                .values(
                    status=ChannelOutboundDeliveryStatus.FAILED.value,
                    last_error=str(error)[:2000],
                    updated_at=utc_now(),
                )
            )
            if result.rowcount != 1:
                await session.rollback()
                raise RuntimeError("Outbound delivery reservation is no longer active")
            await session.commit()
    except Exception:
        record_outbound_delivery_state_error()
        raise
    record_outbound_delivery_failed()


async def send_outbound_acknowledgement_once(
    event: ChannelEvent,
    sender: Callable[[], Awaitable[None]],
) -> bool:
    decision = await reserve_outbound_acknowledgement(event)
    if not decision.should_send or decision.delivery_id is None:
        return False
    try:
        await sender()
    except Exception as exc:
        await mark_outbound_delivery_failed(decision.delivery_id, exc)
        raise
    await mark_outbound_delivery_sent(decision.delivery_id, None)
    return True


async def send_outbound_response_once(
    event: ChannelEvent,
    message: ChannelMessage,
    sender: Callable[[], Awaitable[str]],
) -> str | None:
    decision = await reserve_outbound_delivery(event, message)
    if not decision.should_send or decision.delivery_id is None:
        return None
    try:
        provider_message_id = await sender()
    except Exception as exc:
        await mark_outbound_delivery_failed(decision.delivery_id, exc)
        raise
    await mark_outbound_delivery_sent(decision.delivery_id, provider_message_id)
    return provider_message_id
