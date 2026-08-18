import base64
from uuid import uuid4

from langflow.channels.adapters.wecom_ai import WeComAIBotChannelAdapter
from langflow.channels.domain.models import ChannelEventType, ChannelMessage

_KEY = base64.b64encode(bytes(range(32))).decode().rstrip("=")


def _adapter() -> WeComAIBotChannelAdapter:
    return WeComAIBotChannelAdapter(
        uuid4(),
        token="callback-token",
        encoding_aes_key=_KEY,
        bot_name="OpenXFlow",
    )


def test_wecom_ai_group_text_is_normalized() -> None:
    event = _adapter().parse_decrypted_event(
        {
            "msgid": "msg-group-1",
            "msgtype": "text",
            "chattype": "group",
            "chatid": "chat-1",
            "chatname": "研发群",
            "from": {"userid": "zhangsan", "name": "张三"},
            "text": {"content": "@OpenXFlow 帮我总结"},
        }
    )

    assert event.event_type is ChannelEventType.TEXT
    assert event.user.external_user_id == "zhangsan"
    assert event.conversation.external_conversation_id == "group:chat-1"
    assert event.conversation.conversation_type == "group"
    assert event.message.mentions == ["__bot__"]


def test_wecom_ai_private_command_is_normalized() -> None:
    event = _adapter().parse_decrypted_event(
        {
            "msgid": "msg-private-1",
            "msgtype": "text",
            "chattype": "single",
            "from": {"userid": "lisi"},
            "text": {"content": "/help"},
        }
    )

    assert event.event_type is ChannelEventType.COMMAND
    assert event.conversation.external_conversation_id == "user:lisi"
    assert event.conversation.conversation_type == "private"


def test_wecom_ai_mixed_message_preserves_text_and_image() -> None:
    event = _adapter().parse_decrypted_event(
        {
            "msgid": "msg-mixed-1",
            "msgtype": "mixed",
            "chattype": "group",
            "chatid": "chat-2",
            "from": {"userid": "wangwu"},
            "mixed": {
                "msg_item": [
                    {"msgtype": "text", "text": {"content": "分析图片"}},
                    {
                        "msgtype": "image",
                        "image": {
                            "url": "https://work.weixin.qq.com/media/image",
                            "aeskey": _KEY,
                        },
                    },
                ]
            },
        }
    )

    assert event.message.text == "分析图片"
    assert len(event.message.attachments) == 1
    assert event.message.attachments[0].external_file_id.startswith("wecom-ai:")


def test_wecom_ai_utf8_truncation_respects_byte_limit() -> None:
    truncated = _adapter().truncate_utf8("你" * 1000, 100)

    assert len(truncated.encode("utf-8")) <= 100
    assert truncated.endswith("…")


def test_wecom_ai_stream_response_is_encrypted() -> None:
    adapter = _adapter()
    response = adapter.encrypted_stream_response(
        stream_id="stream-1",
        content="处理完成",
        finish=True,
        timestamp="1710000000",
        nonce="nonce",
    )

    assert '"encrypt"' in response
    assert '"msgsignature"' in response


def test_wecom_ai_render_message_includes_actions() -> None:
    message = ChannelMessage(text="请选择")

    assert _adapter().render_message_text(message) == "请选择"
