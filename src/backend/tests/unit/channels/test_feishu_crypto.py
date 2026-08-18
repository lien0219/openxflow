import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from langflow.channels.security.feishu_crypto import (
    FeishuCryptoError,
    decrypt_feishu_event,
    unwrap_feishu_event_payload,
)


def _encrypt_event(body: dict, encrypt_key: str) -> str:
    key = hashlib.sha256(encrypt_key.encode()).digest()
    iv = bytes(range(16))
    plaintext = json.dumps(body, separators=(",", ":")).encode()
    padding = 16 - len(plaintext) % 16
    padded = plaintext + bytes((padding,)) * padding
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(iv + encrypted).decode()


def test_feishu_encrypt_key_roundtrip() -> None:
    body = {
        "schema": "2.0",
        "header": {"event_id": "evt-1", "event_type": "im.message.receive_v1"},
        "event": {"message": {"message_id": "msg-1"}},
    }
    encrypted = _encrypt_event(body, "encrypt-key")
    assert decrypt_feishu_event(encrypted, "encrypt-key") == body


def test_feishu_encrypted_envelope_unwraps_to_json() -> None:
    body = {"type": "url_verification", "challenge": "challenge-1", "token": "token"}
    payload = json.dumps({"encrypt": _encrypt_event(body, "encrypt-key")}).encode()
    assert json.loads(unwrap_feishu_event_payload(payload, "encrypt-key")) == body


def test_feishu_encrypted_event_requires_key() -> None:
    payload = json.dumps({"encrypt": _encrypt_event({"ok": True}, "encrypt-key")}).encode()
    with pytest.raises(FeishuCryptoError, match="not configured"):
        unwrap_feishu_event_payload(payload, None)
