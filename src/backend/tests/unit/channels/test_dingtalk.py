import base64
import hashlib
import hmac
import json
import time
from uuid import uuid4

import pytest

from langflow.channels.adapters.dingtalk import DingTalkChannelAdapter
from langflow.channels.domain.models import ChannelEventType, ChannelMessage


def _adapter(*, stream_authenticated: bool = True) -> DingTalkChannelAdapter:
    return DingTalkChannelAdapter(
        uuid4(),
        client_id="ding-client",
        client_secret="ding-secret",
        robot_code="robot-code",
        stream_authenticated=stream_authenticated,
    )


def _payload(**overrides) -> bytes:
    body = {
        "msgId": "msg-1",
        "senderNick": "张三",
        "senderId": "sender-id",
        "senderStaffId": "user-1",
        "senderCorpId": "corp-1",
        "conversationId": "cid-group",
        "conversationType": "2",
        "conversationTitle": "项目群",
        "robotCode": "robot-code",
        "sessionWebhook": "https://oapi.dingtalk.com/robot/sendBySession?session=abc",
        "sessionWebhookExpiredTime": int(time.time() * 1000) + 60000,
        "isInAtList": True,
        "chatbotUserId": "bot-user",
        "msgtype": "text",
        "text": {"content": "/help"},
        "createAt": int(time.time() * 1000),
    }
    body.update(overrides)
    return json.dumps(body, ensure_ascii=False).encode()


@pytest.mark.asyncio
async def test_dingtalk_signed_webhook_verification() -> None:
    adapter = _adapter(stream_authenticated=False)
    timestamp = str(int(time.time() * 1000))
    digest = hmac.new(
        b"ding-secret",
        f"{timestamp}\nding-secret".encode(),
        hashlib.sha256,
    ).digest()
    sign = base64.b64encode(digest).decode()

    assert await adapter.verify_event({"timestamp": timestamp, "sign": sign}, b"{}") is True
    assert await adapter.verify_event({"timestamp": timestamp, "sign": "wrong"}, b"{}") is False


@pytest.mark.asyncio
async def test_dingtalk_group_command_is_normalized() -> None:
    event = await _adapter().parse_event({}, _payload())

    assert event.event_type == ChannelEventType.COMMAND
    assert event.user.external_user_id == "user-1"
    assert event.user.display_name == "张三"
    assert event.conversation.external_conversation_id == "group:cid-group"
    assert event.conversation.conversation_type == "group"
    assert event.message.text == "/help"
    assert event.message.mentions == ["bot-user"]
    assert event.message.metadata["session_webhook"].startswith("https://oapi.dingtalk.com")


@pytest.mark.asyncio
async def test_dingtalk_private_conversation_targets_sender() -> None:
    event = await _adapter().parse_event(
        {},
        _payload(conversationType="1", conversationId="private-cid", isInAtList=False),
    )
    assert event.conversation.external_conversation_id == "user:user-1"
    assert event.conversation.conversation_type == "private"


@pytest.mark.asyncio
async def test_dingtalk_file_is_encoded_for_secure_download() -> None:
    event = await _adapter().parse_event(
        {},
        _payload(
            msgtype="file",
            text=None,
            content={"downloadCode": "download-code", "fileName": "report.pdf"},
        ),
    )

    assert event.event_type == ChannelEventType.FILE
    attachment = event.message.attachments[0]
    assert attachment.filename == "report.pdf"
    decoded = DingTalkChannelAdapter._decode_file_identifier(attachment.external_file_id or "")
    assert decoded["download_code"] == "download-code"
    assert decoded["robot_code"] == "robot-code"


@pytest.mark.asyncio
async def test_dingtalk_rich_text_collects_text_and_images() -> None:
    event = await _adapter().parse_event(
        {},
        _payload(
            msgtype="richText",
            text=None,
            content={
                "richText": [
                    {"text": "请分析附件"},
                    {"downloadCode": "image-code"},
                ]
            },
        ),
    )

    assert event.message.text == "请分析附件"
    assert len(event.message.attachments) == 1


@pytest.mark.asyncio
async def test_dingtalk_reply_prefers_session_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    event = await adapter.parse_event({}, _payload())
    captured = {}

    async def fake_post(url, payload):
        captured["url"] = url
        captured["payload"] = payload

    monkeypatch.setattr(adapter, "_post_session_webhook", fake_post)
    await adapter.send_response(event, ChannelMessage(title="完成", markdown="结果内容"))

    assert captured["url"].startswith("https://oapi.dingtalk.com")
    assert captured["payload"]["msgtype"] == "markdown"
    assert captured["payload"]["markdown"]["title"] == "完成"


@pytest.mark.asyncio
async def test_dingtalk_proactive_group_message_uses_open_conversation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter()
    captured = {}

    async def fake_request(method, path, *, payload=None):
        captured.update({"method": method, "path": path, "payload": payload})
        return {"processQueryKey": "query-1"}

    monkeypatch.setattr(adapter, "_api_request", fake_request)
    message_id = await adapter.send_message("group:cid-group", ChannelMessage(text="hello"))

    assert message_id == "query-1"
    assert captured["path"] == "/v1.0/robot/groupMessages/send"
    assert captured["payload"]["openConversationId"] == "cid-group"
