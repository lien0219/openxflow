import base64
from uuid import uuid4

import pytest
from langflow.channels.adapters.wecom_resilient import ResilientWeComChannelAdapter

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


def test_wecom_internal_app_callback_remains_private() -> None:
    event = _adapter()._normalize_message(
        {
            "ToUserName": "ww-openxflow",
            "FromUserName": "zhangsan",
            "CreateTime": "1710000000",
            "MsgType": "text",
            "Content": "大家好",
            "MsgId": "msg-1",
            "AgentID": "1000002",
        }
    )

    assert event.conversation.external_conversation_id == "user:zhangsan"
    assert event.conversation.conversation_type == "private"


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
