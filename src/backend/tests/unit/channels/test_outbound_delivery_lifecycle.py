import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from langflow.channels.services import outbound_delivery


@pytest.mark.asyncio
async def test_outbound_delivery_lifespan_is_idle_when_durable_disabled(monkeypatch) -> None:
    created = False

    def create_task(*args, **kwargs):
        del args, kwargs
        nonlocal created
        created = True
        raise AssertionError("cleanup task should not start")

    monkeypatch.setattr(
        outbound_delivery,
        "durable_webhook_job_config",
        lambda: SimpleNamespace(enabled=False),
    )
    monkeypatch.setattr(asyncio, "create_task", create_task)

    async with outbound_delivery.outbound_delivery_lifespan(object()):
        pass

    assert created is False


@pytest.mark.asyncio
async def test_outbound_delivery_lifespan_starts_and_stops_cleanup(monkeypatch) -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def cleanup_loop(stop_event: asyncio.Event) -> None:
        started.set()
        try:
            await stop_event.wait()
        finally:
            stopped.set()

    monkeypatch.setattr(
        outbound_delivery,
        "durable_webhook_job_config",
        lambda: SimpleNamespace(enabled=True),
    )
    monkeypatch.setattr(outbound_delivery, "_run_outbound_delivery_cleanup", cleanup_loop)

    async with outbound_delivery.outbound_delivery_lifespan(object()):
        await started.wait()

    assert stopped.is_set()


@pytest.mark.asyncio
async def test_outbound_delivery_cleanup_recovers_after_database_error(monkeypatch) -> None:
    attempts = 0
    stop_event = asyncio.Event()

    @asynccontextmanager
    async def fake_session_scope():
        yield object()

    async def cleanup(_session):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("database unavailable")
        stop_event.set()
        return {"acknowledgement": 0, "response": 0}

    monkeypatch.setattr(
        outbound_delivery,
        "durable_webhook_job_config",
        lambda: SimpleNamespace(cleanup_interval_seconds=0.001),
    )
    monkeypatch.setattr(outbound_delivery, "session_scope", fake_session_scope)
    monkeypatch.setattr(outbound_delivery, "cleanup_outbound_deliveries", cleanup)

    await asyncio.wait_for(
        outbound_delivery._run_outbound_delivery_cleanup(stop_event),
        timeout=1,
    )

    assert attempts == 2
