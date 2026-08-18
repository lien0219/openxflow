from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from uuid import uuid4

from langflow.channels.adapters.dingtalk import DingTalkChannelAdapter
from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.adapters.telegram import TelegramChannelAdapter
from langflow.channels.adapters.wecom import WeComChannelAdapter


async def test_telegram_rejects_callbacks_without_configured_secret() -> None:
    adapter = TelegramChannelAdapter(uuid4(), bot_token="123:abc")

    assert await adapter.verify_event({}, b"{}") is False


async def test_telegram_extracts_mentions_using_utf16_entity_offsets() -> None:
    adapter = TelegramChannelAdapter(
        uuid4(),
        bot_token="123:abc",
        webhook_secret="secure_token-1234",
    )
    text = "😀 hello @alice"
    prefix = "😀 hello "
    offset = len(prefix.encode("utf-16-le")) // 2
    mention_length = len("@alice".encode("utf-16-le")) // 2
    payload = {
        "update_id": 100,
        "message": {
            "message_id": 200,
            "date": int(time.time()),
            "chat": {"id": -1001, "type": "group", "title": "Security"},
            "from": {"id": 42, "first_name": "Alice"},
            "text": text,
            "entities": [
                {"type": "mention", "offset": offset, "length": mention_length},
            ],
        },
    }

    event = await adapter.parse_event({}, json.dumps(payload).encode())

    assert event.message.mentions == ["alice"]


async def test_feishu_rejects_unencrypted_callbacks_without_verification_token() -> None:
    adapter = FeishuChannelAdapter(
        uuid4(),
        app_id="cli_test",
        app_secret="secret",
        verification_token=None,
    )

    assert await adapter.verify_event({}, b'{"event": {}}') is False


async def test_dingtalk_rejects_correctly_signed_stale_callbacks() -> None:
    client_secret = "secret"
    adapter = DingTalkChannelAdapter(
        uuid4(),
        client_id="ding-test",
        client_secret=client_secret,
    )
    timestamp = str(int(time.time() * 1000) - 10 * 60 * 1000)
    digest = hmac.new(
        client_secret.encode(),
        timestamp.encode(),
        digestmod=hashlib.sha256,
    ).digest()
    signature = base64.b64encode(digest).decode()

    assert (
        await adapter.verify_event(
            {"timestamp": timestamp, "sign": signature},
            b"{}",
        )
        is False
    )


async def test_wecom_rejects_correctly_signed_stale_callbacks() -> None:
    adapter = WeComChannelAdapter(
        uuid4(),
        corp_id="ww-test",
        corp_secret="secret",
        agent_id="1000002",
        callback_token="callback-token",
        encoding_aes_key="A" * 43,
    )
    timestamp = str(int(time.time()) - 10 * 60)
    nonce = "nonce"
    encrypted = "not-decrypted-because-stale"
    signature = adapter.crypt.signature(timestamp, nonce, encrypted)
    payload = f"<xml><Encrypt>{encrypted}</Encrypt></xml>".encode()

    assert (
        await adapter.verify_event(
            {
                "x-wecom-msg-signature": signature,
                "x-wecom-timestamp": timestamp,
                "x-wecom-nonce": nonce,
            },
            payload,
        )
        is False
    )
