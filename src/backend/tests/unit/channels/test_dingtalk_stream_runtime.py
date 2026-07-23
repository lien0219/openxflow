import asyncio

import pytest

from langflow.channels.services import dingtalk_stream


@pytest.fixture(autouse=True)
def reset_runtime_registry():
    dingtalk_stream.reset_dingtalk_stream_runtime_for_testing()
    yield
    dingtalk_stream.reset_dingtalk_stream_runtime_for_testing()


def test_stream_runtime_registry_aggregates_manager_state() -> None:
    first = object()
    second = object()

    dingtalk_stream._stream_runtime_registry.register(first)
    dingtalk_stream._stream_runtime_registry.register(second)
    dingtalk_stream._stream_runtime_registry.update(first, leader=True, managed_clients=2)
    dingtalk_stream._stream_runtime_registry.update(second, leader=False, managed_clients=1)

    snapshot = dingtalk_stream.dingtalk_stream_runtime_snapshot()
    assert snapshot.running_managers == 2
    assert snapshot.leader_managers == 1
    assert snapshot.managed_clients == 3

    dingtalk_stream._stream_runtime_registry.unregister(first)
    snapshot = dingtalk_stream.dingtalk_stream_runtime_snapshot()
    assert snapshot.running_managers == 1
    assert snapshot.leader_managers == 0
    assert snapshot.managed_clients == 1


def test_stream_runtime_registry_tracks_health_counters_after_manager_exit() -> None:
    token = object()
    registry = dingtalk_stream._stream_runtime_registry
    registry.register(token)
    registry.record_connection_error()
    registry.record_connection_error()
    registry.record_reconnect_attempt()
    registry.record_successful_sync(1234.5)
    registry.unregister(token)

    snapshot = dingtalk_stream.dingtalk_stream_runtime_snapshot()
    assert snapshot.running_managers == 0
    assert snapshot.connection_errors_total == 2
    assert snapshot.reconnect_attempts_total == 1
    assert snapshot.successful_sync_total == 1
    assert snapshot.last_successful_sync_timestamp_seconds == 1234.5


def test_stream_runtime_registry_rejects_invalid_scalar_values() -> None:
    token = object()
    registry = dingtalk_stream._stream_runtime_registry
    registry.register(token)

    with pytest.raises(ValueError, match="managed_clients"):
        registry.update(token, leader=False, managed_clients=-1)
    with pytest.raises(ValueError, match="timestamp_seconds"):
        registry.record_successful_sync(-1)


@pytest.mark.asyncio
async def test_disabled_stream_manager_does_not_register(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dingtalk_stream, "channel_streams_enabled", lambda: False)
    manager = dingtalk_stream.DingTalkStreamManager()

    await manager.run()

    snapshot = dingtalk_stream.dingtalk_stream_runtime_snapshot()
    assert snapshot.running_managers == 0
    assert snapshot.successful_sync_total == 0


@pytest.mark.asyncio
async def test_stream_manager_registers_and_unregisters_for_run_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dingtalk_stream, "channel_streams_enabled", lambda: True)
    manager = dingtalk_stream.DingTalkStreamManager()
    entered = asyncio.Event()

    async def become_leader() -> None:
        manager._has_leader_lock = True
        manager._publish_runtime_state()
        entered.set()

    async def sync_connections() -> None:
        dingtalk_stream._stream_runtime_registry.record_successful_sync(100.0)
        await manager.stop()

    monkeypatch.setattr(manager, "_try_become_leader", become_leader)
    monkeypatch.setattr(manager, "_sync_connections", sync_connections)

    await manager.run()
    await entered.wait()

    snapshot = dingtalk_stream.dingtalk_stream_runtime_snapshot()
    assert snapshot.running_managers == 0
    assert snapshot.leader_managers == 0
    assert snapshot.managed_clients == 0
    assert snapshot.successful_sync_total == 1
    assert snapshot.last_successful_sync_timestamp_seconds == 100.0


@pytest.mark.asyncio
async def test_stream_connection_failure_records_error_and_next_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = dingtalk_stream.DingTalkStreamManager()
    connection_attempts = 0

    async def fail_then_stop(_connection_id) -> None:
        nonlocal connection_attempts
        connection_attempts += 1
        if connection_attempts == 1:
            raise RuntimeError("connection failed")
        await manager.stop()

    async def ignore_status(*_args, **_kwargs) -> None:
        return None

    async def immediate_wait_for(_awaitable, *, timeout):
        del timeout
        if hasattr(_awaitable, "close"):
            _awaitable.close()
        return None

    monkeypatch.setattr(manager, "_run_sdk_client", fail_then_stop)
    monkeypatch.setattr(manager, "_set_status", ignore_status)
    monkeypatch.setattr(dingtalk_stream.asyncio, "wait_for", immediate_wait_for)

    await manager._run_connection(object())  # type: ignore[arg-type]

    snapshot = dingtalk_stream.dingtalk_stream_runtime_snapshot()
    assert snapshot.connection_errors_total == 1
    assert snapshot.reconnect_attempts_total == 1
