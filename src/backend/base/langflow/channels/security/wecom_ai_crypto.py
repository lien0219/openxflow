"""WeCom AI Bot JSON callback signature and AES encryption support."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import struct
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_PADDING_BLOCK_SIZE = 32


class WeComAIBotCryptoError(ValueError):
    """Raised when a WeCom AI Bot callback cannot be verified or decrypted."""


@dataclass(frozen=True)
class WeComAIBotCrypt:
    """Implement the JSON variant of the official WeCom callback wire format."""

    token: str
    encoding_aes_key: str

    def __post_init__(self) -> None:
        token = self.token.strip()
        encoding_aes_key = self.encoding_aes_key.strip()
        if not token:
            raise ValueError("WeCom AI Bot token is required")
        if len(encoding_aes_key) != 43:
            raise ValueError("WeCom AI Bot EncodingAESKey must be 43 characters")
        try:
            aes_key = base64.b64decode(f"{encoding_aes_key}=", validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid WeCom AI Bot EncodingAESKey") from exc
        if len(aes_key) != 32:
            raise ValueError("Invalid WeCom AI Bot EncodingAESKey length")
        object.__setattr__(self, "token", token)
        object.__setattr__(self, "encoding_aes_key", encoding_aes_key)
        object.__setattr__(self, "_aes_key", aes_key)

    @property
    def aes_key(self) -> bytes:
        return self._aes_key  # type: ignore[attr-defined]

    def signature(self, timestamp: str, nonce: str, encrypted: str) -> str:
        values = sorted((self.token, str(timestamp), str(nonce), encrypted))
        return hashlib.sha1("".join(values).encode()).hexdigest()  # noqa: S324 - provider protocol requires SHA-1

    def verify_signature(self, signature: str, timestamp: str, nonce: str, encrypted: str) -> bool:
        return hmac.compare_digest(self.signature(timestamp, nonce, encrypted), signature.strip())

    def verify_url(self, *, signature: str, timestamp: str, nonce: str, echo: str) -> str:
        if not self.verify_signature(signature, timestamp, nonce, echo):
            raise WeComAIBotCryptoError("Invalid WeCom AI Bot callback signature")
        return self._decrypt_ciphertext(echo)

    def decrypt_payload(
        self,
        payload: bytes,
        *,
        signature: str,
        timestamp: str,
        nonce: str,
    ) -> dict[str, Any]:
        try:
            envelope = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WeComAIBotCryptoError("Invalid WeCom AI Bot JSON envelope") from exc
        if not isinstance(envelope, dict):
            raise WeComAIBotCryptoError("Invalid WeCom AI Bot JSON envelope")
        encrypted = envelope.get("encrypt")
        if not isinstance(encrypted, str) or not encrypted:
            raise WeComAIBotCryptoError("WeCom AI Bot encrypted payload is missing")
        if not self.verify_signature(signature, timestamp, nonce, encrypted):
            raise WeComAIBotCryptoError("Invalid WeCom AI Bot callback signature")
        plaintext = self._decrypt_ciphertext(encrypted)
        try:
            decoded = json.loads(plaintext)
        except json.JSONDecodeError as exc:
            raise WeComAIBotCryptoError("Invalid WeCom AI Bot decrypted JSON") from exc
        if not isinstance(decoded, dict):
            raise WeComAIBotCryptoError("Invalid WeCom AI Bot decrypted JSON")
        return decoded

    def encrypt_response(
        self,
        message: dict[str, Any],
        *,
        timestamp: str,
        nonce: str,
        random_prefix: bytes | None = None,
    ) -> str:
        plaintext = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        encrypted = self._encrypt_plaintext(plaintext, random_prefix=random_prefix)
        return json.dumps(
            {
                "encrypt": encrypted,
                "msgsignature": self.signature(timestamp, nonce, encrypted),
                "timestamp": str(timestamp),
                "nonce": str(nonce),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _decrypt_ciphertext(self, encrypted: str) -> str:
        try:
            ciphertext = base64.b64decode(encrypted, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise WeComAIBotCryptoError("Invalid WeCom AI Bot encrypted payload") from exc
        if not ciphertext or len(ciphertext) % 16 != 0:
            raise WeComAIBotCryptoError("Invalid WeCom AI Bot encrypted payload length")
        decryptor = Cipher(algorithms.AES(self.aes_key), modes.CBC(self.aes_key[:16])).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        plaintext = self._unpad(padded)
        if len(plaintext) < 20:
            raise WeComAIBotCryptoError("WeCom AI Bot decrypted payload is too short")
        message_length = struct.unpack("!I", plaintext[16:20])[0]
        message_end = 20 + message_length
        if message_end > len(plaintext):
            raise WeComAIBotCryptoError("Invalid WeCom AI Bot message length")
        if plaintext[message_end:]:
            raise WeComAIBotCryptoError("Unexpected WeCom AI Bot receive ID")
        try:
            return plaintext[20:message_end].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WeComAIBotCryptoError("WeCom AI Bot message is not valid UTF-8") from exc

    def _encrypt_plaintext(self, plaintext: str, *, random_prefix: bytes | None = None) -> str:
        prefix = random_prefix if random_prefix is not None else os.urandom(16)
        if len(prefix) != 16:
            raise ValueError("WeCom AI Bot random prefix must be 16 bytes")
        message = plaintext.encode("utf-8")
        raw = prefix + struct.pack("!I", len(message)) + message
        encryptor = Cipher(algorithms.AES(self.aes_key), modes.CBC(self.aes_key[:16])).encryptor()
        ciphertext = encryptor.update(self._pad(raw)) + encryptor.finalize()
        return base64.b64encode(ciphertext).decode()

    @staticmethod
    def _pad(value: bytes) -> bytes:
        padding_length = _PADDING_BLOCK_SIZE - len(value) % _PADDING_BLOCK_SIZE
        return value + bytes((padding_length,)) * padding_length

    @staticmethod
    def _unpad(value: bytes) -> bytes:
        if not value:
            raise WeComAIBotCryptoError("WeCom AI Bot decrypted payload is empty")
        padding_length = value[-1]
        if padding_length < 1 or padding_length > _PADDING_BLOCK_SIZE:
            raise WeComAIBotCryptoError("Invalid WeCom AI Bot PKCS#7 padding")
        if value[-padding_length:] != bytes((padding_length,)) * padding_length:
            raise WeComAIBotCryptoError("Invalid WeCom AI Bot PKCS#7 padding")
        return value[:-padding_length]
