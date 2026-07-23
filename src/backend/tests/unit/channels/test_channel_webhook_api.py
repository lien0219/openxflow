from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.requests import ClientDisconnect

from langflow.api.v1.channel_webhooks import _validate_and_schedule_provider_event
from langflow.channels.domain.models import ChannelEvent, ChannelEventType, ChannelType


class _FakeDB:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def get(self, _model, connection_id):
        return self.connection if self.connection.id == connection_id else None


class _FakeRequest:
    def __init__(
        self,
        payload: bytes = b"{}",
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
    ) -> None:
        self.payload = payload
        self.chunks = chunks or [payload]
        self.headers = headers or {
            "content-type": "application/json",
            "content-length": str(len(payload)),
        }

    async def body(self) -> bytes:
        return self.payload

    async def stream(self):
        for chunk in self.chunks:
            yield chunk


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


def _connection(connection_id):
    return SimpleNamespace(
        id=connection_id,
        channel_type="telegram",
        enabled=True,
    )


def _adapter(connection_id):
    adapter = _FakeAdapter()
    adapter.connection_id = connection_id
    return adapter


@pytest.fixture(autouse=True)
def disable_durable_webhook_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.durable_webhook_job_config",
        lambda: SimpleNamespace(enabled=False),
    )


@pytest.mark.asyncio
async def test_durable_webhook_is_committed_without_background_task(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)
    adapter = _adapter(connection_id)
    captured = {}

    async def enqueue(session, **kwargs) -> bool:
        captured["session"] = session
        captured.update(kwargs)
        return True

    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.durable_webhook_job_config",
        lambda: SimpleNamespace(enabled=True),
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.build_channel_adapter",
        lambda _connection: adapter,
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.enqueue_provider_webhook_job",
        enqueue,
    )

    db = _FakeDB(connection)
    background_tasks = BackgroundTasks()
    response = await _validate_and_schedule_provider_event(
        connection_id=connection_id,
        request=_FakeRequest(payload=b'{"message":"hello"}'),
        db=db,
        background_tasks=background_tasks,
        expected_channel_type="telegram",
    )

    assert response == {"ok": True}
    assert captured["session"] is db
    assert captured["connection_id"] == connection_id
    assert captured["channel_type"] == "telegram"
    assert captured["external_event_id"] == "event-1"
    assert captured["payload"] == b'{"message":"hello"}'
    assert captured["headers"]["content-type"] == "application/json"
    assert background_tasks.tasks == []


@pytest.mark.asyncio
async def test_webhook_validation_schedules_background_processing(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)
    adapter = _adapter(connection_id)
    reservation = object()
    reserved_payload_sizes: list[int] = []

    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.build_channel_adapter",
        lambda _connection: adapter,
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.reserve_provider_webhook_slot",
        lambda payload_size: reserved_payload_sizes.append(payload_size) or reservation,
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
    assert reserved_payload_sizes == [2]
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].kwargs["reservation"] is reservation


@pytest.mark.asyncio
async def test_webhook_queue_full_returns_retryable_503(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)
    adapter = _adapter(connection_id)

    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.build_channel_adapter",
        lambda _connection: adapter,
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.reserve_provider_webhook_slot",
        lambda _payload_size: None,
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.webhook_limiter_snapshot",
        lambda: SimpleNamespace(
            pending=128,
            max_pending=128,
            pending_bytes=67108864,
            max_pending_bytes=67108864,
        ),
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
    assert "jobs 128/128" in str(exc_info.value.detail)
    assert "bytes 67108864/67108864" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_invalid_webhook_is_rejected_before_queue_reservation(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)
    adapter = _adapter(connection_id)

    async def reject(_headers, _payload):
        return False

    adapter.verify_event = reject
    reserved = False

    def reserve(_payload_size: int):
        nonlocal reserved
        reserved = True
        return object()

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


@pytest.mark.asyncio
async def test_declared_oversized_webhook_is_rejected_before_adapter_build(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)
    adapter_built = False

    def build(_connection):
        nonlocal adapter_built
        adapter_built = True
        return _adapter(connection_id)

    monkeypatch.setattr("langflow.api.v1.channel_webhooks.webhook_max_body_bytes", lambda: 4)
    monkeypatch.setattr("langflow.api.v1.channel_webhooks.build_channel_adapter", build)

    with pytest.raises(HTTPException) as exc_info:
        await _validate_and_schedule_provider_event(
            connection_id=connection_id,
            request=_FakeRequest(payload=b"{}", headers={"content-length": "5"}),
            db=_FakeDB(connection),
            background_tasks=BackgroundTasks(),
            expected_channel_type="telegram",
        )

    assert exc_info.value.status_code == 413
    assert adapter_built is False


@pytest.mark.asyncio
async def test_actual_oversized_webhook_is_rejected_without_content_length(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)

    monkeypatch.setattr("langflow.api.v1.channel_webhooks.webhook_max_body_bytes", lambda: 4)

    with pytest.raises(HTTPException) as exc_info:
        await _validate_and_schedule_provider_event(
            connection_id=connection_id,
            request=_FakeRequest(
                payload=b"12345",
                headers={"content-type": "application/json"},
                chunks=[b"12", b"345"],
            ),
            db=_FakeDB(connection),
            background_tasks=BackgroundTasks(),
            expected_channel_type="telegram",
        )

    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_streamed_webhook_stops_before_reading_later_chunks(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)
    chunks_read = 0

    class StreamingRequest(_FakeRequest):
        async def stream(self):
            nonlocal chunks_read
            for chunk in [b"123", b"45", b"should-not-be-read"]:
                chunks_read += 1
                yield chunk

    monkeypatch.setattr("langflow.api.v1.channel_webhooks.webhook_max_body_bytes", lambda: 4)

    with pytest.raises(HTTPException) as exc_info:
        await _validate_and_schedule_provider_event(
            connection_id=connection_id,
            request=StreamingRequest(headers={"content-type": "application/json"}),
            db=_FakeDB(connection),
            background_tasks=BackgroundTasks(),
            expected_channel_type="telegram",
        )

    assert exc_info.value.status_code == 413
    assert chunks_read == 2


@pytest.mark.asyncio
async def test_disconnected_webhook_is_rejected_before_adapter_and_queue(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)
    adapter_built = False
    reserved = False

    class DisconnectedRequest(_FakeRequest):
        async def stream(self):
            yield b"partial"
            raise ClientDisconnect

    def build(_connection):
        nonlocal adapter_built
        adapter_built = True
        return _adapter(connection_id)

    def reserve(_payload_size: int):
        nonlocal reserved
        reserved = True
        return object()

    monkeypatch.setattr("langflow.api.v1.channel_webhooks.build_channel_adapter", build)
    monkeypatch.setattr("langflow.api.v1.channel_webhooks.reserve_provider_webhook_slot", reserve)

    with pytest.raises(HTTPException) as exc_info:
        await _validate_and_schedule_provider_event(
            connection_id=connection_id,
            request=DisconnectedRequest(headers={"content-type": "application/json"}),
            db=_FakeDB(connection),
            background_tasks=BackgroundTasks(),
            expected_channel_type="telegram",
        )

    assert exc_info.value.status_code == 400
    assert "disconnected" in str(exc_info.value.detail).lower()
    assert adapter_built is False
    assert reserved is False


@pytest.mark.asyncio
async def test_background_task_registration_failure_releases_reservation(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)
    adapter = _adapter(connection_id)
    reservation = object()
    released_reservations: list[object] = []

    class FailingBackgroundTasks:
        def add_task(self, *_args, **_kwargs) -> None:
            raise RuntimeError("task registration failed")

    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.build_channel_adapter",
        lambda _connection: adapter,
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.reserve_provider_webhook_slot",
        lambda _payload_size: reservation,
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.release_provider_webhook_slot",
        released_reservations.append,
    )

    with pytest.raises(RuntimeError, match="task registration failed"):
        await _validate_and_schedule_provider_event(
            connection_id=connection_id,
            request=_FakeRequest(),
            db=_FakeDB(connection),
            background_tasks=FailingBackgroundTasks(),
            expected_channel_type="telegram",
        )

    assert released_reservations == [reservation]
