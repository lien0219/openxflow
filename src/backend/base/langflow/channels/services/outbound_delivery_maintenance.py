"""Lifecycle maintenance for durable outbound delivery receipts."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import sqlalchemy as sa
from lfx.log.logger import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.services.outbound_delivery import cleanup_outbound_deliveries
from langflow.channels.services.outbound_delivery_metrics import (
    set_outbound_delivery_retained_depths,
)
from langflow.channels.services.runtime_config import durable_webhook_job_config
from langflow.services.database.models.channel.outbound_delivery_model import (
    ChannelOutboundDelivery,
    ChannelOutboundDeliveryKind,
    ChannelOutboundDeliveryStatus,
)
from langflow.services.deps import session_scope


async def outbound_delivery_retained_depths(
    session: AsyncSession,
) -> dict[str, dict[str, int]]:
    """Return retained receipt counts grouped by delivery kind and status."""
    rows = (
        await session.exec(
            select(
                ChannelOutboundDelivery.delivery_kind,
                ChannelOutboundDelivery.status,
                sa.func.count(ChannelOutboundDelivery.id),
            ).group_by(
                ChannelOutboundDelivery.delivery_kind,
                ChannelOutboundDelivery.status,
            )
        )
    ).all()
    depths = {
        kind.value: {
            ChannelOutboundDeliveryStatus.RESERVED.value: 0,
            ChannelOutboundDeliveryStatus.SENT.value: 0,
            ChannelOutboundDeliveryStatus.FAILED.value: 0,
        }
        for kind in ChannelOutboundDeliveryKind
    }
    for raw_kind, raw_status, count in rows:
        kind = str(raw_kind)
        status = str(raw_status)
        if kind in depths and status in depths[kind]:
            depths[kind][status] = int(count)
    return depths


def publish_outbound_delivery_retained_depths(
    depths: dict[str, dict[str, int]],
) -> None:
    for kind in ChannelOutboundDeliveryKind:
        values = depths[kind.value]
        set_outbound_delivery_retained_depths(
            kind,
            reserved=values[ChannelOutboundDeliveryStatus.RESERVED.value],
            sent=values[ChannelOutboundDeliveryStatus.SENT.value],
            failed=values[ChannelOutboundDeliveryStatus.FAILED.value],
        )


async def maintain_outbound_deliveries_once() -> None:
    async with session_scope() as session:
        await cleanup_outbound_deliveries(session)
        depths = await outbound_delivery_retained_depths(session)
    publish_outbound_delivery_retained_depths(depths)


async def _run_outbound_delivery_maintenance(stop_event: asyncio.Event) -> None:
    config = durable_webhook_job_config()
    while not stop_event.is_set():
        try:
            await maintain_outbound_deliveries_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            await logger.aexception("Unable to maintain durable outbound delivery receipts")
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=config.cleanup_interval_seconds,
            )
        except TimeoutError:
            pass


@asynccontextmanager
async def outbound_delivery_maintenance_lifespan(_app):  # type: ignore[no-untyped-def]
    config = durable_webhook_job_config()
    if not config.enabled:
        yield
        return
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        _run_outbound_delivery_maintenance(stop_event),
        name="channel-outbound-delivery-maintenance",
    )
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
