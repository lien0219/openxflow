import base64
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks
from langflow.api.v1.channel_webhooks import _receive_wecom_ai_callback
from langflow.channels.adapters.wecom_ai import WeComAIBotChannelAdapter
from langflow.channels.services.wecom_ai_runtime import wecom_ai_response_runtime

_KEY = base64.b64encode(bytes(range(32))).decode().rstrip("=")


class _Request:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.headers = {
            "content-type": "application/json",
            "content-length": str(len(payload)),
        }

    async def stream(self):
        yield self.payload


def _adapter(connection_id):
    return WeComAIBotChannelAdapter(
        connection_id,
        token="callback-token",
        encoding_aes_key=_KEY,
    )


def _encrypted_request(adapter, message, *, timestamp=None, nonce="nonce"):
    resolved_timestamp = timestamp or str(int(time.time()))
    envelope = json.loads(
        adapter.crypt.encrypt_response(
            message,
            timestamp=resolved_timestamp,
            nonce=nonce,
            random_prefix=b"0123456789abcdef",
        )
    )
    return (
        json.dumps({"encrypt": envelope["encrypt"]}).encode(),
        envelope["msgsignature"],
        resolved_timestamp,
        nonce,
    )


def _decrypt_response(adapter, response, *, timestamp, nonce="nonce"):
    envelope = json.loads(response.body)
    return adapter.crypt.decrypt_payload(
        response.body,
        signature=envelope["msgsignature"],
        timestamp=timestamp,
        nonce=nonce,
    )


@pytest.mark.asyncio
async def test_wecom_ai_initial_callback_returns_pending_stream(monkeypatch) -> None:
    connection_id = uuid4()
    connection = SimpleNamespace(id=connection_id, enabled=True, connection_mode="ai_bot")
    adapter = _adapter(connection_id)
    payload, signature, timestamp, nonce = _encrypted_request(
        adapter,
        {
            "msgid": "msg-1",
            "msgtype": "text",
            "chattype": "group",
            "chatid": "chat-1",
            "from": {"userid": "zhangsan"},
            "text": {"content": "问题"},
        },
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.build_channel_adapter",
        lambda _connection: adapter,
    )
    background_tasks = BackgroundTasks()

    response = await _receive_wecom_ai_callback(
        connection=connection,
        request=_Request(payload),
        background_tasks=background_tasks,
        msg_signature=signature,
        timestamp=timestamp,
        nonce=nonce,
    )
    decoded = _decrypt_response(adapter, response, timestamp=timestamp)

    assert decoded["msgtype"] == "stream"
    assert decoded["stream"]["finish"] is False
    assert decoded["stream"]["content"]
    assert len(background_tasks.tasks) == 1


@pytest.mark.asyncio
async def test_wecom_ai_stream_poll_returns_completed_content(monkeypatch) -> None:
    connection_id = uuid4()
    connection = SimpleNamespace(id=connection_id, enabled=True, connection_mode="ai_bot")
    adapter = _adapter(connection_id)
    runtime = wecom_ai_response_runtime()
    state, _ = await runtime.reserve(connection_id, "event-1")
    await runtime.complete(state.stream_id, "最终回答")
    payload, signature, timestamp, nonce = _encrypted_request(
        adapter,
        {
            "msgtype": "stream",
            "stream": {"id": state.stream_id},
        },
    )
    monkeypatch.setattr(
        "langflow.api.v1.channel_webhooks.build_channel_adapter",
        lambda _connection: adapter,
    )

    response = await _receive_wecom_ai_callback(
        connection=connection,
        request=_Request(payload),
        background_tasks=BackgroundTasks(),
        msg_signature=signature,
        timestamp=timestamp,
        nonce=nonce,
    )
    decoded = _decrypt_response(adapter, response, timestamp=timestamp)

    assert decoded["stream"] == {
        "id": state.stream_id,
        "finish": True,
        "content": "最终回答",
    }
