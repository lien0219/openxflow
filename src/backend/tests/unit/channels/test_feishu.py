import json
from uuid import uuid4

import pytest

from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.domain.models import (
    ChannelAction,
    ChannelEventType,
    ChannelMessage,
    ChannelMessageType,
)


def _adapter() -> FeishuChannelAdapter:
    return FeishuChannelAdapter(
        uuid4(),
        app_id="cli_test",
        app_secret="secret",
        verification_token="verify-token",
    )


def _message_event(*, message_type: str = "text", content: dict | None = None, mentions: list | None = None) -> bytes:
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
                "mentions": mentions or [],
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
async def test_feishu_mention_placeholder_is_removed_before_command_detection() -> None:
    event = await _adapter().parse_event(
        {},
        _message_event(
            content={"text": "@_user_1 /help"},
            mentions=[{"key": "@_user_1", "id": {"open_id": "ou_bot"}}],
        ),
    )
    assert event.message.text == "/help"
    assert event.event_type == ChannelEventType.COMMAND


@pytest.mark.asyncio
async def test_feishu_post_message_is_flattened() -> None:
    event = await _adapter().parse_event(
        {},
        _message_event(
            message_type="post",
            content={
                "title": "日报",
                "content": [[{"tag": "text", "text": "销售额增长 12%"}]],
            },
        ),
    )
    assert event.event_type == ChannelEventType.TEXT
    assert event.message.text == "日报\n销售额增长 12%"


@pytest.mark.asyncio
async def test_feishu_file_identifier_contains_resource_type() -> None:
    event = await _adapter().parse_event(
        {},
        _message_event(
            message_type="file",
            content={"file_key": "file-key", "file_name": "report.pdf"},
        ),
    )

    assert event.event_type == ChannelEventType.FILE
    assert event.message.attachments[0].external_file_id == "om_message:file-key:file"
    assert event.message.attachments[0].filename == "report.pdf"


@pytest.mark.asyncio
async def test_feishu_card_action_is_normalized() -> None:
    payload = json.dumps(
        {
            "schema": "2.0",
            "header": {
                "event_id": "card-event",
                "event_type": "card.action.trigger",
                "tenant_key": "tenant-1",
                "token": "verify-token",
            },
            "event": {
                "operator": {"open_id": "ou_user"},
                "context": {
                    "open_chat_id": "oc_chat",
                    "open_message_id": "om_card",
                },
                "action": {
                    "tag": "button",
                    "value": {"action_id": "approve", "value": "/run approve"},
                },
            },
        }
    ).encode()

    event = await _adapter().parse_event({}, payload)
    assert event.event_type == ChannelEventType.ACTION
    assert event.message.text == "/run approve"
    assert event.message.metadata["action_id"] == "approve"


@pytest.mark.asyncio
async def test_feishu_send_response_replies_to_original_message(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    captured: dict = {}

    async def fake_request(method, path, *, params=None, payload=None):
        captured.update({"method": method, "path": path, "params": params, "payload": payload})
        return {"message_id": "sent-message"}

    monkeypatch.setattr(adapter, "_request", fake_request)
    event = await adapter.parse_event({}, _message_event())
    message_id = await adapter.send_response(event, ChannelMessage(title="Result", text="Done"))

    assert message_id == "sent-message"
    assert captured["path"] == "im/v1/messages/om_message/reply"
    assert captured["payload"]["reply_in_thread"] is False


def test_feishu_card_renderer_builds_interactive_buttons() -> None:
    msg_type, content = FeishuChannelAdapter._render_message(
        ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="审批",
            markdown="是否继续？",
            actions=[ChannelAction(action_id="approve", label="通过", style="primary")],
        )
    )

    assert msg_type == "interactive"
    assert content["header"]["title"]["content"] == "审批"
    assert content["elements"][1]["actions"][0]["value"]["action_id"] == "approve"
