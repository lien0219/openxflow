import base64
from uuid import uuid4

import pytest
from langflow.channels.adapters.wecom_resilient import ResilientWeComChannelAdapter
from langflow.channels.domain.models import ChannelMessage

_ENCODING_AES_KEY = base64.b64encode(bytes(range(32))).decode().rstrip("=")


def _adapter() -> ResilientWeComChannelAdapter:
    return ResilientWeComChannelAdapter(
        uuid4(),
        corp_id="ww-openxflow",
        corp_secret="corp-secret",
        agent_id="1000002",
        callback_token="callback-token",
        encoding_aes_key=_ENCODING_AES_KEY,
    )


def test_wecom_app_chat_callback_is_normalized_as_group() -> None:
    event = _adapter()._normalize_message(
        {
            "ToUserName": "ww-openxflow",
            "FromUserName": "zhangsan",
            "CreateTime": "1710000000",
            "MsgType": "text",
            "Content": "大家好",
            "MsgId": "msg-group-1",
            "AgentID": "1000002",
            "ChatId": "app-chat-1",
        }
    )

    assert event.conversation.external_conversation_id == "group:app-chat-1"
    assert event.conversation.conversation_type == "group"
    assert event.conversation.metadata["chat_id"] == "app-chat-1"


@pytest.mark.asyncio
async def test_wecom_app_chat_response_uses_appchat_api(monkeypatch) -> None:
    adapter = _adapter()
    captured = {}

    async def fake_request(method, path, *, params=None, payload=None):
        captured.update({"method": method, "path": path, "params": params, "payload": payload})
        return {"errcode": 0, "msgid": "group-message-1"}

    monkeypatch.setattr(adapter, "_api_request", fake_request)

    message_id = await adapter.send_message("group:app-chat-1", ChannelMessage(text="群回复"))

    assert message_id == "group-message-1"
    assert captured["path"] == "/cgi-bin/appchat/send"
    assert captured["payload"]["chatid"] == "app-chat-1"
    assert captured["payload"]["text"]["content"] == "群回复"


def test_wecom_callback_rejects_wrong_agent_id() -> None:
    with pytest.raises(ValueError, match="does not match"):
        _adapter()._normalize_message(
            {
                "ToUserName": "ww-openxflow",
                "FromUserName": "zhangsan",
                "CreateTime": "1710000000",
                "MsgType": "text",
                "Content": "hello",
                "MsgId": "msg-1",
                "AgentID": "1000003",
            }
        )
