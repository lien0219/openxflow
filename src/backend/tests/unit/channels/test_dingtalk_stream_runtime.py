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


def test_stream_runtime_registry_rejects_negative_client_count() -> None:
    token = object()
    dingtalk_stream._stream_runtime_registry.register(token)

    with pytest.raises(ValueError, match="managed_clients"):
        dingtalk_stream._stream_runtime_registry.update(token, leader=False, managed_clients=-1)


@pytest.mark.asyncio
async def test_disabled_stream_manager_does_not_register(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dingtalk_stream, "channel_streams_enabled", lambda: False)
    manager = dingtalk_stream.DingTalkStreamManager()

    await manager.run()

    assert dingtalk_stream.dingtalk_stream_runtime_snapshot().running_managers == 0


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
        await manager.stop()

    monkeypatch.setattr(manager, "_try_become_leader", become_leader)
    monkeypatch.setattr(manager, "_sync_connections", sync_connections)

    await manager.run()
    await entered.wait()

    snapshot = dingtalk_stream.dingtalk_stream_runtime_snapshot()
    assert snapshot.running_managers == 0
    assert snapshot.leader_managers == 0
    assert snapshot.managed_clients == 0
