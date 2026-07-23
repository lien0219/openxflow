"""Persistent at-most-once guards for durable channel provider deliveries."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import sqlalchemy as sa
from lfx.log.logger import logger
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.domain.models import ChannelEvent, ChannelMessage
from langflow.channels.services.outbound_delivery_metrics import (
    record_outbound_delivery_cleaned,
    record_outbound_delivery_failed,
    record_outbound_delivery_reserved,
    record_outbound_delivery_sent,
    record_outbound_delivery_state_error,
    record_outbound_delivery_suppressed,
)
from langflow.channels.services.runtime_config import durable_webhook_job_config
from langflow.services.database.models.channel.model import utc_now
from langflow.services.database.models.channel.outbound_delivery_model import (
    ChannelOutboundDelivery,
    ChannelOutboundDeliveryKind,
    ChannelOutboundDeliveryStatus,
)
from langflow.services.deps import session_scope

_ACKNOWLEDGEMENT_DIGEST = hashlib.sha256(b"acknowledgement").hexdigest()
_TERMINAL_STATUSES = (
    ChannelOutboundDeliveryStatus.SENT.value,
    ChannelOutboundDeliveryStatus.FAILED.value,
)


@dataclass(frozen=True)
class OutboundDeliveryDecision:
    should_send: bool
    delivery_id: UUID | None
    delivery_kind: ChannelOutboundDeliveryKind


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
                record_outbound_delivery_suppressed(delivery_kind)
                return OutboundDeliveryDecision(False, existing.id, delivery_kind)
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
                record_outbound_delivery_suppressed(delivery_kind)
                return OutboundDeliveryDecision(False, existing.id, delivery_kind)
            await session.commit()
            record_outbound_delivery_reserved(delivery_kind)
            return OutboundDeliveryDecision(True, existing.id, delivery_kind)

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
                record_outbound_delivery_state_error(delivery_kind)
                raise
            record_outbound_delivery_suppressed(delivery_kind)
            return OutboundDeliveryDecision(False, concurrent, delivery_kind)
        record_outbound_delivery_reserved(delivery_kind)
        return OutboundDeliveryDecision(True, delivery.id, delivery_kind)


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


async def mark_outbound_delivery_sent(
    delivery_id: UUID,
    delivery_kind: ChannelOutboundDeliveryKind,
    provider_message_id: str | None,
) -> None:
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
        record_outbound_delivery_state_error(delivery_kind)
        raise
    record_outbound_delivery_sent(delivery_kind)


async def mark_outbound_delivery_failed(
    delivery_id: UUID,
    delivery_kind: ChannelOutboundDeliveryKind,
    error: Exception,
) -> None:
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
        record_outbound_delivery_state_error(delivery_kind)
        raise
    record_outbound_delivery_failed(delivery_kind)


async def cleanup_outbound_deliveries(session: AsyncSession) -> dict[str, int]:
    """Delete one oldest-first batch of expired terminal delivery receipts."""
    config = durable_webhook_job_config()
    cutoff = utc_now() - timedelta(days=config.outbound_delivery_retention_days)
    rows = list(
        (
            await session.exec(
                select(ChannelOutboundDelivery.id, ChannelOutboundDelivery.delivery_kind)
                .where(
                    ChannelOutboundDelivery.status.in_(_TERMINAL_STATUSES),
                    ChannelOutboundDelivery.updated_at <= cutoff,
                )
                .order_by(ChannelOutboundDelivery.updated_at, ChannelOutboundDelivery.created_at)
                .limit(config.cleanup_batch_size)
            )
        ).all()
    )
    counts = {kind.value: 0 for kind in ChannelOutboundDeliveryKind}
    if not rows:
        await session.rollback()
        return counts
    ids = [delivery_id for delivery_id, _kind in rows]
    await session.exec(sa.delete(ChannelOutboundDelivery).where(ChannelOutboundDelivery.id.in_(ids)))
    await session.commit()
    for _delivery_id, kind in rows:
        counts[str(kind)] += 1
    for kind, count in counts.items():
        record_outbound_delivery_cleaned(kind, count)
    return counts


async def send_outbound_acknowledgement_once(
    event: ChannelEvent,
    sender: Callable[[], Awaitable[None]],
) -> bool:
    decision = await reserve_outbound_acknowledgement(event)
    if not decision.should_send or decision.delivery_id is None:
        return False
    try:
        await sender()
    except Exception as provider_error:
        try:
            await mark_outbound_delivery_failed(
                decision.delivery_id,
                decision.delivery_kind,
                provider_error,
            )
        except Exception:
            await logger.aexception(
                "Unable to persist failed outbound acknowledgement for event %s",
                event.event_id,
            )
        raise
    await mark_outbound_delivery_sent(decision.delivery_id, decision.delivery_kind, None)
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
    except Exception as provider_error:
        try:
            await mark_outbound_delivery_failed(
                decision.delivery_id,
                decision.delivery_kind,
                provider_error,
            )
        except Exception:
            await logger.aexception(
                "Unable to persist failed outbound response for event %s",
                event.event_id,
            )
        raise
    await mark_outbound_delivery_sent(
        decision.delivery_id,
        decision.delivery_kind,
        provider_message_id,
    )
    return provider_message_id


async def _run_outbound_delivery_cleanup(stop_event: asyncio.Event) -> None:
    config = durable_webhook_job_config()
    while not stop_event.is_set():
        try:
            async with session_scope() as session:
                await cleanup_outbound_deliveries(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            await logger.aexception("Unable to clean durable outbound delivery receipts")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=config.cleanup_interval_seconds)
        except TimeoutError:
            pass


@asynccontextmanager
async def outbound_delivery_lifespan(_app):  # type: ignore[no-untyped-def]
    config = durable_webhook_job_config()
    if not config.enabled:
        yield
        return
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        _run_outbound_delivery_cleanup(stop_event),
        name="channel-outbound-delivery-cleanup",
    )
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
