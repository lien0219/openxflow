import base64
from uuid import uuid4

import pytest
from langflow.channels.adapters.wecom import WeComChannelAdapter
from langflow.channels.domain.models import (
    ChannelAction,
    ChannelEventType,
    ChannelMessage,
    ChannelMessageType,
)
from langflow.channels.security.wecom_crypto import WeComCryptoError, WeComMessageCrypt

TOKEN = "callback-token"
AES_KEY_BYTES = bytes(range(32))
ENCODING_AES_KEY = base64.b64encode(AES_KEY_BYTES).decode().rstrip("=")
CORP_ID = "ww-openxflow"


def _adapter() -> WeComChannelAdapter:
    return WeComChannelAdapter(
        uuid4(),
        corp_id=CORP_ID,
        corp_secret="corp-secret",
        agent_id="1000002",
        callback_token=TOKEN,
        encoding_aes_key=ENCODING_AES_KEY,
    )


def _encrypted_payload(inner_xml: str, *, timestamp: str = "1710000000", nonce: str = "nonce"):
    crypt = WeComMessageCrypt(TOKEN, ENCODING_AES_KEY, CORP_ID)
    encrypted = crypt.encrypt(inner_xml, random_prefix=b"0123456789abcdef")
    signature = crypt.signature(timestamp, nonce, encrypted)
    outer = f"<xml><ToUserName>{CORP_ID}</ToUserName><Encrypt>{encrypted}</Encrypt></xml>".encode()
    headers = {
        "x-wecom-msg-signature": signature,
        "x-wecom-timestamp": timestamp,
        "x-wecom-nonce": nonce,
    }
    return outer, headers, encrypted, signature


def test_wecom_crypto_roundtrip_and_receive_id_validation() -> None:
    crypt = WeComMessageCrypt(TOKEN, ENCODING_AES_KEY, CORP_ID)
    encrypted = crypt.encrypt("<xml><Content>hello</Content></xml>", random_prefix=b"0123456789abcdef")
    assert crypt.decrypt(encrypted) == "<xml><Content>hello</Content></xml>"

    wrong_crypt = WeComMessageCrypt(TOKEN, ENCODING_AES_KEY, "wrong-corp")
    with pytest.raises(WeComCryptoError, match="receive ID mismatch"):
        wrong_crypt.decrypt(encrypted)


def test_wecom_url_verification() -> None:
    adapter = _adapter()
    crypt = WeComMessageCrypt(TOKEN, ENCODING_AES_KEY, CORP_ID)
    encrypted = crypt.encrypt("verified-echo", random_prefix=b"0123456789abcdef")
    signature = crypt.signature("1710000000", "nonce", encrypted)
    assert (
        adapter.verify_url(
            signature=signature,
            timestamp="1710000000",
            nonce="nonce",
            echo=encrypted,
        )
        == "verified-echo"
    )


@pytest.mark.asyncio
async def test_wecom_encrypted_text_message_is_normalized() -> None:
    inner = """<xml>
<ToUserName>ww-openxflow</ToUserName>
<FromUserName>zhangsan</FromUserName>
<CreateTime>1710000000</CreateTime>
<MsgType>text</MsgType>
<Content>/help</Content>
<MsgId>msg-1</MsgId>
<AgentID>1000002</AgentID>
</xml>"""
    payload, headers, _, _ = _encrypted_payload(inner)
    adapter = _adapter()

    assert await adapter.verify_event(headers, payload) is True
    event = await adapter.parse_event(headers, payload)
    assert event.channel.value == "wecom"
    assert event.event_type == ChannelEventType.COMMAND
    assert event.user.external_user_id == "zhangsan"
    assert event.conversation.external_conversation_id == "user:zhangsan"
    assert event.message.text == "/help"


@pytest.mark.asyncio
async def test_wecom_template_card_event_becomes_action() -> None:
    inner = """<xml>
<ToUserName>ww-openxflow</ToUserName>
<FromUserName>zhangsan</FromUserName>
<CreateTime>1710000001</CreateTime>
<MsgType>event</MsgType>
<Event>template_card_event</Event>
<EventKey>/run approve</EventKey>
<TaskId>task-1</TaskId>
<ResponseCode>response-1</ResponseCode>
<AgentID>1000002</AgentID>
</xml>"""
    payload, headers, _, _ = _encrypted_payload(inner)
    event = await _adapter().parse_event(headers, payload)
    assert event.event_type == ChannelEventType.ACTION
    assert event.message.text == "/run approve"
    assert event.message.metadata["response_code"] == "response-1"


@pytest.mark.asyncio
async def test_wecom_file_message_uses_media_identifier() -> None:
    inner = """<xml>
<ToUserName>ww-openxflow</ToUserName>
<FromUserName>zhangsan</FromUserName>
<CreateTime>1710000002</CreateTime>
<MsgType>file</MsgType>
<MediaId>media-123</MediaId>
<FileName>report.pdf</FileName>
<MsgId>msg-file</MsgId>
<AgentID>1000002</AgentID>
</xml>"""
    payload, headers, _, _ = _encrypted_payload(inner)
    event = await _adapter().parse_event(headers, payload)
    assert event.event_type == ChannelEventType.FILE
    assert event.message.attachments[0].external_file_id == "wecom:media-123"
    assert event.message.attachments[0].filename == "report.pdf"


@pytest.mark.asyncio
async def test_wecom_button_card_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    captured = {}

    async def fake_request(method, path, *, params=None, payload=None):
        captured.update({"method": method, "path": path, "params": params, "payload": payload})
        return {"errcode": 0, "msgid": "wecom-msg-1"}

    monkeypatch.setattr(adapter, "_api_request", fake_request)
    message_id = await adapter.send_message(
        "user:zhangsan",
        ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="执行确认",
            markdown="是否继续运行工作流？",
            actions=[
                ChannelAction(action_id="approve", label="确认", style="primary", value="/run approve"),
                ChannelAction(action_id="cancel", label="取消", style="danger", value="/cancel"),
            ],
        ),
    )

    assert message_id == "wecom-msg-1"
    assert captured["path"] == "/cgi-bin/message/send"
    assert captured["payload"]["touser"] == "zhangsan"
    assert captured["payload"]["msgtype"] == "template_card"
    card = captured["payload"]["template_card"]
    assert card["card_type"] == "button_interaction"
    assert card["button_list"][0]["key"] == "/run approve"
