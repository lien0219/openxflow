import json
from uuid import uuid4

import pytest

from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.domain.models import ChannelEventType, ChannelMessage


def _adapter() -> FeishuChannelAdapter:
    return FeishuChannelAdapter(
        uuid4(),
        app_id="cli_test",
        app_secret="secret",
        verification_token="verify-token",
    )


def _message_event(*, message_type: str = "text", content: dict | None = None) -> bytes:
    payload = {
        "schema": "2.0",
        "header": {
            "event_id": "event-1",
            "event_type": "im.message.receive_v1",
            "tenant_key": "tenant-1",
            "token": "verify-token",
        },
        "event": {
            "sender": {
                "sender_id": {
                    "open_id": "ou_user",
                    "user_id": "user-1",
                    "union_id": "union-1",
                },
                "sender_type": "user",
            },
            "message": {
                "message_id": "om_message",
                "chat_id": "oc_chat",
                "chat_type": "p2p",
                "message_type": message_type,
                "content": json.dumps(content or {"text": "hello"}),
                "mentions": [],
            },
        },
    }
    return json.dumps(payload).encode()


@pytest.mark.asyncio
async def test_feishu_url_verification_checks_token() -> None:
    adapter = _adapter()
    payload = json.dumps(
        {
            "type": "url_verification",
            "token": "verify-token",
            "challenge": "challenge-value",
        }
    ).encode()

    assert FeishuChannelAdapter.is_url_verification(payload) is True
    assert FeishuChannelAdapter.get_url_verification_challenge(payload) == "challenge-value"
    assert await adapter.verify_event({}, payload) is True


@pytest.mark.asyncio
async def test_feishu_rejects_wrong_verification_token() -> None:
    adapter = _adapter()
    payload = json.dumps(
        {
            "type": "url_verification",
            "token": "wrong",
            "challenge": "challenge-value",
        }
    ).encode()

    assert await adapter.verify_event({}, payload) is False


@pytest.mark.asyncio
async def test_feishu_text_event_is_normalized() -> None:
    event = await _adapter().parse_event({}, _message_event())

    assert event.event_id == "event-1"
    assert event.event_type == ChannelEventType.TEXT
    assert event.user.external_user_id == "ou_user"
    assert event.user.tenant_id == "tenant-1"
    assert event.conversation.external_conversation_id == "oc_chat"
    assert event.conversation.conversation_type == "private"
    assert event.message.text == "hello"


@pytest.mark.asyncio
async def test_feishu_command_is_detected() -> None:
    event = await _adapter().parse_event(
        {},
        _message_event(content={"text": "/help"}),
    )
    assert event.event_type == ChannelEventType.COMMAND


@pytest.mark.asyncio
async def test_feishu_file_identifier_contains_message_and_file_key() -> None:
    event = await _adapter().parse_event(
        {},
        _message_event(
            message_type="file",
            content={"file_key": "file-key", "file_name": "report.pdf"},
        ),
    )

    assert event.event_type == ChannelEventType.FILE
    assert len(event.message.attachments) == 1
    assert event.message.attachments[0].external_file_id == "om_message:file-key"
    assert event.message.attachments[0].filename == "report.pdf"


@pytest.mark.asyncio
async def test_feishu_send_message_uses_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    captured: dict = {}

    async def fake_request(method, path, *, params=None, payload=None):
        captured.update(
            {
                "method": method,
                "path": path,
                "params": params,
                "payload": payload,
            }
        )
        return {"message_id": "sent-message"}

    monkeypatch.setattr(adapter, "_request", fake_request)
    message_id = await adapter.send_message(
        "oc_chat",
        ChannelMessage(title="Result", text="Done"),
    )

    assert message_id == "sent-message"
    assert captured["method"] == "POST"
    assert captured["path"] == "im/v1/messages"
    assert captured["params"] == {"receive_id_type": "chat_id"}
    assert captured["payload"]["receive_id"] == "oc_chat"
    assert "Result" in captured["payload"]["content"]
