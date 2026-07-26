from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from lfx.services import deps
from lfx.services.settings.groups.database import DatabaseSettings

from langflow.channels.domain.models import ChannelMessage
from langflow.channels.services import deduplication, webhook_processing


def test_sqlite_settings_use_bounded_connection_pool(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LANGFLOW_DATABASE_URL", f"sqlite:///{tmp_path / 'openxflow.db'}")

    settings = DatabaseSettings(
        db_connection_settings={
            "pool_size": 20,
            "max_overflow": 30,
            "pool_timeout": 5,
            "pool_pre_ping": True,
        }
    )

    assert settings.db_connection_settings == {
        "pool_size": 5,
        "max_overflow": 0,
        "pool_timeout": 30,
        "pool_pre_ping": True,
    }


def test_postgres_settings_keep_configured_pool(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_DATABASE_URL", "postgresql://user:password@localhost/openxflow")
    configured = {
        "pool_size": 8,
        "max_overflow": 12,
        "pool_timeout": 15,
        "pool_pre_ping": True,
    }

    settings = DatabaseSettings(db_connection_settings=configured)

    assert settings.db_connection_settings == configured


class _FailedSession:
    is_active = False

    def __init__(self) -> None:
        self.rollback_calls = 0

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        self.rollback_calls += 1


class _FakeDBService:
    def __init__(self, session) -> None:
        self.session = session

    @asynccontextmanager
    async def _with_session(self):
        yield self.session


@pytest.mark.asyncio
async def test_session_scope_rolls_back_inactive_failed_session(monkeypatch) -> None:
    session = _FailedSession()
    monkeypatch.setattr(deps, "get_db_service", lambda: _FakeDBService(session))
    monkeypatch.setattr(deps.logger, "aexception", AsyncMock())

    with pytest.raises(RuntimeError, match="boom"):
        async with deps.session_scope():
            raise RuntimeError("boom")

    assert session.rollback_calls == 1


class _Result:
    def __init__(self, value) -> None:
        self.value = value

    def first(self):
        return self.value


class _DedupSession:
    def __init__(self) -> None:
        self.commit_calls = 0

    async def exec(self, _statement):
        return _Result(None)

    async def commit(self) -> None:
        self.commit_calls += 1


@pytest.mark.asyncio
async def test_deduplication_claim_commits_before_follow_up_writes(monkeypatch) -> None:
    session = _DedupSession()
    receipt = SimpleNamespace(id=uuid4())
    claim = AsyncMock(return_value=receipt)
    monkeypatch.setattr(deduplication, "claim_channel_event", claim)
    event = SimpleNamespace(
        connection_id=uuid4(),
        event_id="event-1",
        event_type=SimpleNamespace(value="text"),
    )

    result = await deduplication.ChannelEventDeduplicator(session).claim(event, b"payload")

    assert result is receipt
    assert session.commit_calls == 1


class _WebhookSession:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.commit_calls = 0
        self.rollback_calls = 0
        self.failure_marker = False
        self.committed_failure_marker = False

    async def get(self, _model, connection_id):
        return self.connection if self.connection.id == connection_id else None

    async def commit(self) -> None:
        self.commit_calls += 1
        if self.failure_marker:
            self.committed_failure_marker = True

    async def rollback(self) -> None:
        self.rollback_calls += 1


class _DispatchService:
    def __init__(self, _session, _connection, _adapter) -> None:
        pass

    async def handle(self, _event):
        return ChannelMessage(text="ok")


class _FailingDispatchService(_DispatchService):
    async def handle(self, _event):
        raise RuntimeError("dispatch failed")


def _connection(connection_id):
    return SimpleNamespace(
        id=connection_id,
        channel_type="telegram",
        enabled=True,
        queue_timeout_seconds=30,
        task_timeout_seconds=30,
    )


def _event():
    return SimpleNamespace(message=SimpleNamespace(metadata={}))


@pytest.mark.asyncio
async def test_webhook_dispatch_commits_before_gateway_delivery(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)
    session = _WebhookSession(connection)
    observed = {}

    @asynccontextmanager
    async def fake_session_scope():
        yield session

    class _Gateway:
        def register_adapter(self, _connection_id, _adapter) -> None:
            return None

        async def receive(self, _connection_id, _headers, _payload, handler, *, deduplicator):
            del deduplicator
            observed["response"] = await handler(_event())
            observed["commit_calls_after_handler"] = session.commit_calls

    monkeypatch.setattr(webhook_processing, "session_scope", fake_session_scope)
    monkeypatch.setattr(webhook_processing, "build_channel_adapter", lambda _connection: object())
    monkeypatch.setattr(webhook_processing, "ChannelGateway", _Gateway)
    monkeypatch.setattr(webhook_processing, "ChannelEventDeduplicator", lambda _session: object())
    monkeypatch.setattr(webhook_processing, "ChannelDispatchService", _DispatchService)

    result = await webhook_processing.process_provider_webhook(
        connection_id=connection_id,
        expected_channel_type="telegram",
        headers={},
        payload=b"{}",
    )

    assert result is True
    assert observed["response"].text == "ok"
    assert observed["commit_calls_after_handler"] == 1
    assert session.commit_calls == 2
    assert session.rollback_calls == 0


@pytest.mark.asyncio
async def test_webhook_failure_commits_receipt_failure_marker(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)
    session = _WebhookSession(connection)

    @asynccontextmanager
    async def fake_session_scope():
        yield session

    class _Gateway:
        def register_adapter(self, _connection_id, _adapter) -> None:
            return None

        async def receive(self, _connection_id, _headers, _payload, handler, *, deduplicator):
            del deduplicator
            try:
                await handler(_event())
            except RuntimeError:
                session.failure_marker = True
                raise

    monkeypatch.setattr(webhook_processing, "session_scope", fake_session_scope)
    monkeypatch.setattr(webhook_processing, "build_channel_adapter", lambda _connection: object())
    monkeypatch.setattr(webhook_processing, "ChannelGateway", _Gateway)
    monkeypatch.setattr(webhook_processing, "ChannelEventDeduplicator", lambda _session: object())
    monkeypatch.setattr(webhook_processing, "ChannelDispatchService", _FailingDispatchService)
    monkeypatch.setattr(webhook_processing.logger, "aexception", AsyncMock())

    result = await webhook_processing.process_provider_webhook(
        connection_id=connection_id,
        expected_channel_type="telegram",
        headers={},
        payload=b"{}",
    )

    assert result is False
    assert session.rollback_calls == 1
    assert session.commit_calls == 1
    assert session.committed_failure_marker is True
