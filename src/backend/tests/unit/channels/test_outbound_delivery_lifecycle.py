import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from langflow.channels.services import outbound_delivery_maintenance


@pytest.mark.asyncio
async def test_outbound_delivery_lifespan_is_idle_when_durable_disabled(monkeypatch) -> None:
    created = False

    def create_task(*args, **kwargs):
        del args, kwargs
        nonlocal created
        created = True
        raise AssertionError("maintenance task should not start")

    monkeypatch.setattr(
        outbound_delivery_maintenance,
        "durable_webhook_job_config",
        lambda: SimpleNamespace(enabled=False),
    )
    monkeypatch.setattr(asyncio, "create_task", create_task)

    async with outbound_delivery_maintenance.outbound_delivery_maintenance_lifespan(object()):
        pass

    assert created is False


@pytest.mark.asyncio
async def test_outbound_delivery_lifespan_starts_and_stops_maintenance(monkeypatch) -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def maintenance_loop(stop_event: asyncio.Event) -> None:
        started.set()
        try:
            await stop_event.wait()
        finally:
            stopped.set()

    monkeypatch.setattr(
        outbound_delivery_maintenance,
        "durable_webhook_job_config",
        lambda: SimpleNamespace(enabled=True),
    )
    monkeypatch.setattr(
        outbound_delivery_maintenance,
        "_run_outbound_delivery_maintenance",
        maintenance_loop,
    )

    async with outbound_delivery_maintenance.outbound_delivery_maintenance_lifespan(object()):
        await started.wait()

    assert stopped.is_set()


@pytest.mark.asyncio
async def test_outbound_delivery_maintenance_recovers_after_database_error(monkeypatch) -> None:
    attempts = 0
    stop_event = asyncio.Event()

    async def maintain_once() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("database unavailable")
        stop_event.set()

    monkeypatch.setattr(
        outbound_delivery_maintenance,
        "durable_webhook_job_config",
        lambda: SimpleNamespace(cleanup_interval_seconds=0.001),
    )
    monkeypatch.setattr(
        outbound_delivery_maintenance,
        "maintain_outbound_deliveries_once",
        maintain_once,
    )

    await asyncio.wait_for(
        outbound_delivery_maintenance._run_outbound_delivery_maintenance(stop_event),
        timeout=1,
    )

    assert attempts == 2


@pytest.mark.asyncio
async def test_outbound_delivery_maintenance_publishes_retained_depths(monkeypatch) -> None:
    published = []

    @asynccontextmanager
    async def fake_session_scope():
        yield object()

    async def cleanup(_session):
        return {"acknowledgement": 0, "response": 1}

    async def depths(_session):
        return {
            "acknowledgement": {"reserved": 1, "sent": 2, "failed": 3},
            "response": {"reserved": 4, "sent": 5, "failed": 6},
        }

    def publish(values):
        published.append(values)

    monkeypatch.setattr(outbound_delivery_maintenance, "session_scope", fake_session_scope)
    monkeypatch.setattr(outbound_delivery_maintenance, "cleanup_outbound_deliveries", cleanup)
    monkeypatch.setattr(outbound_delivery_maintenance, "outbound_delivery_retained_depths", depths)
    monkeypatch.setattr(
        outbound_delivery_maintenance,
        "publish_outbound_delivery_retained_depths",
        publish,
    )

    await outbound_delivery_maintenance.maintain_outbound_deliveries_once()

    assert published == [
        {
            "acknowledgement": {"reserved": 1, "sent": 2, "failed": 3},
            "response": {"reserved": 4, "sent": 5, "failed": 6},
        }
    ]
