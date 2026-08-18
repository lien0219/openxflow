import base64
import hashlib
import json
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from langflow.channels.adapters.feishu_encrypted import EncryptedFeishuChannelAdapter
from langflow.channels.domain.models import ChannelEventType


def _encrypt(body: dict, encrypt_key: str) -> str:
    key = hashlib.sha256(encrypt_key.encode()).digest()
    iv = bytes(range(16))
    plaintext = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    padding_length = 16 - len(plaintext) % 16
    padded = plaintext + bytes((padding_length,)) * padding_length
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return base64.b64encode(iv + encryptor.update(padded) + encryptor.finalize()).decode()


def _adapter() -> EncryptedFeishuChannelAdapter:
    return EncryptedFeishuChannelAdapter(
        uuid4(),
        app_id="cli-test",
        app_secret="secret",
        verification_token="verify-token",
        encrypt_key="encrypt-key",
    )


@pytest.mark.asyncio
async def test_encrypted_url_verification_is_verified_and_unwrapped() -> None:
    adapter = _adapter()
    plaintext = {
        "type": "url_verification",
        "challenge": "challenge-value",
        "token": "verify-token",
    }
    payload = json.dumps({"encrypt": _encrypt(plaintext, "encrypt-key")}).encode()

    assert adapter.is_url_verification(payload) is True
    assert adapter.get_url_verification_challenge(payload) == "challenge-value"
    assert await adapter.verify_event({}, payload) is True


@pytest.mark.asyncio
async def test_encrypted_message_event_is_normalized() -> None:
    adapter = _adapter()
    plaintext = {
        "schema": "2.0",
        "header": {
            "event_id": "evt-encrypted",
            "event_type": "im.message.receive_v1",
            "tenant_key": "tenant-1",
            "token": "verify-token",
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou-user"},
                "sender_type": "user",
            },
            "message": {
                "message_id": "om-message",
                "chat_id": "oc-chat",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": "/help"}),
            },
        },
    }
    payload = json.dumps({"encrypt": _encrypt(plaintext, "encrypt-key")}).encode()

    assert await adapter.verify_event({}, payload) is True
    event = await adapter.parse_event({}, payload)
    assert event.event_id == "evt-encrypted"
    assert event.event_type == ChannelEventType.COMMAND
    assert event.user.external_user_id == "ou-user"
    assert event.message.text == "/help"


@pytest.mark.asyncio
async def test_encrypted_event_rejects_wrong_verification_token() -> None:
    adapter = _adapter()
    payload = json.dumps(
        {
            "encrypt": _encrypt(
                {
                    "schema": "2.0",
                    "header": {"token": "wrong-token"},
                    "event": {},
                },
                "encrypt-key",
            )
        }
    ).encode()
    assert await adapter.verify_event({}, payload) is False
