"""Periodic lifecycle maintenance for channel workflow selections."""

from __future__ import annotations

import asyncio
import os

from lfx.log.logger import logger

from langflow.channels.services.flow_selection import cleanup_expired_workflow_selections_batch
from langflow.services.deps import session_scope

_DEFAULT_INTERVAL_SECONDS = 60 * 60
_DEFAULT_BATCH_SIZE = 500
_DEFAULT_MAX_BATCHES = 20


def _positive_int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


async def maintain_flow_selections_once() -> int:
    batch_size = _positive_int_env(
        "LANGFLOW_CHANNEL_FLOW_SELECTION_CLEANUP_BATCH_SIZE",
        _DEFAULT_BATCH_SIZE,
        minimum=1,
        maximum=1000,
    )
    max_batches = _positive_int_env(
        "LANGFLOW_CHANNEL_FLOW_SELECTION_CLEANUP_MAX_BATCHES",
        _DEFAULT_MAX_BATCHES,
        minimum=1,
        maximum=100,
    )
    removed = 0
    for _ in range(max_batches):
        async with session_scope() as session:
            batch_removed = await cleanup_expired_workflow_selections_batch(
                session,
                batch_size=batch_size,
                action="expire",
            )
            await session.commit()
        removed += batch_removed
        if batch_removed < batch_size:
            break
    if removed:
        await logger.ainfo("Cleaned up %s expired channel workflow selections", removed)
    return removed


async def run_flow_selection_maintenance() -> None:
    interval_seconds = _positive_int_env(
        "LANGFLOW_CHANNEL_FLOW_SELECTION_CLEANUP_INTERVAL_SECONDS",
        _DEFAULT_INTERVAL_SECONDS,
        minimum=60,
        maximum=7 * 24 * 60 * 60,
    )
    while True:
        try:
            await maintain_flow_selections_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            await logger.aexception("Unable to maintain channel workflow selections")
        await asyncio.sleep(interval_seconds)
