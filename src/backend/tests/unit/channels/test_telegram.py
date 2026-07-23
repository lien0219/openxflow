import json
from uuid import uuid4

import pytest
from langflow.channels.adapters.telegram import TelegramChannelAdapter
from langflow.channels.domain.models import ChannelAction, ChannelEventType, ChannelMessage


def build_adapter() -> TelegramChannelAdapter:
    return TelegramChannelAdapter(uuid4(), bot_token="token", webhook_secret="secret")


async def test_telegram_webhook_secret_is_verified():
    adapter = build_adapter()

    assert await adapter.verify_event({"x-telegram-bot-api-secret-token": "secret"}, b"{}") is True
    assert await adapter.verify_event({"x-telegram-bot-api-secret-token": "wrong"}, b"{}") is False


async def test_telegram_text_message_is_normalized_without_acknowledgement():
    adapter = build_adapter()
    payload = json.dumps(
        {
            "update_id": 100,
            "message": {
                "message_id": 5,
                "from": {"id": 10, "first_name": "Li", "username": "li"},
                "chat": {"id": -20, "type": "group", "title": "Team"},
                "text": "/help",
            },
        }
    ).encode()

    event = await adapter.parse_event({}, payload)

    assert event.event_id == "100"
    assert event.event_type is ChannelEventType.COMMAND
    assert event.user.external_user_id == "10"
    assert event.conversation.external_conversation_id == "-20"
    assert event.message.text == "/help"
    assert adapter.requires_event_acknowledgement(event) is False


async def test_telegram_document_is_normalized_without_acknowledgement():
    adapter = build_adapter()
    payload = json.dumps(
        {
            "update_id": 101,
            "message": {
                "message_id": 6,
                "from": {"id": 10, "first_name": "Li"},
                "chat": {"id": 10, "type": "private"},
                "caption": "分析这个文件",
                "document": {
                    "file_id": "file-1",
                    "file_unique_id": "unique-1",
                    "file_name": "report.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 128,
                },
            },
        }
    ).encode()

    event = await adapter.parse_event({}, payload)

    assert event.event_type is ChannelEventType.FILE
    assert event.message.attachments[0].filename == "report.pdf"
    assert event.message.attachments[0].external_file_id == "file-1"
    assert adapter.requires_event_acknowledgement(event) is False


async def test_telegram_callback_query_requires_acknowledgement():
    adapter = build_adapter()
    payload = json.dumps(
        {
            "update_id": 102,
            "callback_query": {
                "id": "callback-1",
                "from": {"id": 10, "first_name": "Li"},
                "data": "approve",
                "message": {"message_id": 7, "chat": {"id": 10, "type": "private"}},
            },
        }
    ).encode()

    event = await adapter.parse_event({}, payload)

    assert event.event_type is ChannelEventType.ACTION
    assert event.message.text == "approve"
    assert event.message.metadata["callback_query_id"] == "callback-1"
    assert adapter.requires_event_acknowledgement(event) is True


async def test_telegram_acknowledges_callback_query(monkeypatch):
    adapter = build_adapter()
    captured = {}
    event = await adapter.parse_event(
        {},
        json.dumps(
            {
                "update_id": 103,
                "callback_query": {
                    "id": "callback-2",
                    "from": {"id": 10, "first_name": "Li"},
                    "data": "approve",
                    "message": {"message_id": 8, "chat": {"id": 10, "type": "private"}},
                },
            }
        ).encode(),
    )

    async def fake_request(method, *, payload=None):
        captured["method"] = method
        captured["payload"] = payload
        return True

    monkeypatch.setattr(adapter, "_request", fake_request)

    await adapter.acknowledge_event(event)

    assert captured == {
        "method": "answerCallbackQuery",
        "payload": {"callback_query_id": "callback-2"},
    }


async def test_telegram_send_message_builds_inline_keyboard(monkeypatch):
    adapter = build_adapter()
    captured = {}

    async def fake_request(method, *, payload=None):
        captured["method"] = method
        captured["payload"] = payload
        return {"message_id": 9, "chat": {"id": 10}}

    monkeypatch.setattr(adapter, "_request", fake_request)

    external_id = await adapter.send_message(
        "10",
        ChannelMessage(
            title="Confirm",
            text="Run workflow?",
            actions=[ChannelAction(action_id="approve", label="Approve")],
        ),
    )

    assert external_id == "10:9"
    assert captured["method"] == "sendMessage"
    assert captured["payload"]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "approve"


async def test_telegram_invalid_update_is_rejected():
    adapter = build_adapter()

    with pytest.raises(ValueError, match="Invalid Telegram update payload"):
        await adapter.parse_event({}, b'{"update_id":1}')
