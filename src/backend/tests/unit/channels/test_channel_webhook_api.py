from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException

from langflow.api.v1.channel_webhooks import _validate_and_schedule_provider_event
from langflow.channels.domain.models import ChannelEvent, ChannelEventType, ChannelType


class _FakeDB:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def get(self, _model, connection_id):
        return self.connection if self.connection.id == connection_id else None


class _FakeRequest:
    headers = {"content-type": "application/json"}

    def __init__(self, payload: bytes = b"{}") -> None:
        self.payload = payload

    async def body(self) -> bytes:
        return self.payload


class _FakeAdapter:
    channel_type = ChannelType.TELEGRAM

    async def verify_event(self, headers, payload):
        return True

    async def parse_event(self, headers, payload):
        del headers, payload
        connection_id = self.connection_id
        return ChannelEvent(
            event_id="event-1",
            channel=ChannelType.TELEGRAM,
            connection_id=connection_id,
            event_type=ChannelEventType.TEXT,
            user={"external_user_id": "user-1"},
            conversation={"external_conversation_id": "chat-1"},
            message={
                "external_message_id": "message-1",
                "message_type": ChannelEventType.TEXT,
                "text": "hello",
            },
        )


@pytest.mark.asyncio
async def test_webhook_validation_schedules_background_processing(monkeypatch) -> None:
    connection_id = uuid4()
    connection = SimpleNamespace(
        id=connection_id,
        channel_type="telegram",
        enabled=True,
    )
    adapter = _FakeAdapter()
    adapter.connection_id = connection_id

    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.build_channel_adapter",
        lambda _connection: adapter,
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.reserve_provider_webhook_slot",
        lambda: True,
    )

    background_tasks = BackgroundTasks()
    response = await _validate_and_schedule_provider_event(
        connection_id=connection_id,
        request=_FakeRequest(),
        db=_FakeDB(connection),
        background_tasks=background_tasks,
        expected_channel_type="telegram",
    )

    assert response == {"ok": True}
    assert len(background_tasks.tasks) == 1


@pytest.mark.asyncio
async def test_webhook_queue_full_returns_retryable_503(monkeypatch) -> None:
    connection_id = uuid4()
    connection = SimpleNamespace(
        id=connection_id,
        channel_type="telegram",
        enabled=True,
    )
    adapter = _FakeAdapter()
    adapter.connection_id = connection_id

    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.build_channel_adapter",
        lambda _connection: adapter,
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.reserve_provider_webhook_slot",
        lambda: False,
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.webhook_limiter_snapshot",
        lambda: SimpleNamespace(pending=128, max_pending=128),
    )

    with pytest.raises(HTTPException) as exc_info:
        await _validate_and_schedule_provider_event(
            connection_id=connection_id,
            request=_FakeRequest(),
            db=_FakeDB(connection),
            background_tasks=BackgroundTasks(),
            expected_channel_type="telegram",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers == {"Retry-After": "1"}
    assert "128/128" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_invalid_webhook_is_rejected_before_queue_reservation(monkeypatch) -> None:
    connection_id = uuid4()
    connection = SimpleNamespace(
        id=connection_id,
        channel_type="telegram",
        enabled=True,
    )
    adapter = _FakeAdapter()
    adapter.connection_id = connection_id

    async def reject(_headers, _payload):
        return False

    adapter.verify_event = reject
    reserved = False

    def reserve() -> bool:
        nonlocal reserved
        reserved = True
        return True

    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.build_channel_adapter",
        lambda _connection: adapter,
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.reserve_provider_webhook_slot",
        reserve,
    )

    with pytest.raises(HTTPException) as exc_info:
        await _validate_and_schedule_provider_event(
            connection_id=connection_id,
            request=_FakeRequest(),
            db=_FakeDB(connection),
            background_tasks=BackgroundTasks(),
            expected_channel_type="telegram",
        )

    assert exc_info.value.status_code == 403
    assert reserved is False
