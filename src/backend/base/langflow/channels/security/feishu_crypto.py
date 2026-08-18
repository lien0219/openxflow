"""Feishu event subscription payload decryption."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class FeishuCryptoError(ValueError):
    """Raised when an encrypted Feishu event cannot be decoded safely."""


def decrypt_feishu_event(encrypted: str, encrypt_key: str) -> dict[str, Any]:
    """Decrypt a Feishu ``encrypt`` envelope into its original JSON object.

    Feishu derives a 256-bit AES key from the configured Encrypt Key. The
    decoded payload stores the CBC IV in the first 16 bytes, followed by the
    encrypted JSON body using PKCS#7 padding.
    """
    normalized_key = encrypt_key.strip()
    if not normalized_key:
        raise FeishuCryptoError("Feishu Encrypt Key is not configured")
    try:
        raw = base64.b64decode(encrypted, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise FeishuCryptoError("Invalid Feishu encrypted payload encoding") from exc
    if len(raw) <= 16 or (len(raw) - 16) % 16 != 0:
        raise FeishuCryptoError("Invalid Feishu encrypted payload length")

    key = hashlib.sha256(normalized_key.encode()).digest()
    iv, ciphertext = raw[:16], raw[16:]
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    plaintext = _unpad_pkcs7(padded)
    try:
        body = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeishuCryptoError("Invalid Feishu decrypted event JSON") from exc
    if not isinstance(body, dict):
        raise FeishuCryptoError("Feishu decrypted event must be a JSON object")
    return body


def unwrap_feishu_event_payload(payload: bytes, encrypt_key: str | None) -> bytes:
    """Return plaintext JSON bytes for encrypted events and preserve normal events."""
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeishuCryptoError("Invalid Feishu event JSON") from exc
    if not isinstance(body, dict):
        raise FeishuCryptoError("Feishu event must be a JSON object")
    encrypted = body.get("encrypt")
    if encrypted is None:
        return payload
    if not isinstance(encrypted, str) or not encrypted:
        raise FeishuCryptoError("Invalid Feishu encrypted event envelope")
    decrypted = decrypt_feishu_event(encrypted, encrypt_key or "")
    return json.dumps(decrypted, ensure_ascii=False, separators=(",", ":")).encode()


def _unpad_pkcs7(value: bytes) -> bytes:
    if not value:
        raise FeishuCryptoError("Feishu decrypted payload is empty")
    padding_length = value[-1]
    if padding_length < 1 or padding_length > 16:
        raise FeishuCryptoError("Invalid Feishu PKCS#7 padding")
    if value[-padding_length:] != bytes((padding_length,)) * padding_length:
        raise FeishuCryptoError("Invalid Feishu PKCS#7 padding")
    return value[:-padding_length]
