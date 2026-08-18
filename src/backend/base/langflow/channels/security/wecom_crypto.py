"""Enterprise WeChat callback signature verification and AES message encryption."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_WECOM_PADDING_BLOCK_SIZE = 32


class WeComCryptoError(ValueError):
    """Raised when a WeCom callback cannot be verified or decrypted."""


@dataclass(frozen=True)
class WeComMessageCrypt:
    token: str
    encoding_aes_key: str
    receive_id: str

    def __post_init__(self) -> None:
        token = self.token.strip()
        encoding_aes_key = self.encoding_aes_key.strip()
        receive_id = self.receive_id.strip()
        if not token:
            raise ValueError("WeCom callback token is required")
        if len(encoding_aes_key) != 43:
            raise ValueError("WeCom EncodingAESKey must be 43 characters")
        try:
            aes_key = base64.b64decode(f"{encoding_aes_key}=", validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid WeCom EncodingAESKey") from exc
        if len(aes_key) != 32:
            raise ValueError("Invalid WeCom EncodingAESKey length")
        if not receive_id:
            raise ValueError("WeCom receive ID is required")
        object.__setattr__(self, "token", token)
        object.__setattr__(self, "encoding_aes_key", encoding_aes_key)
        object.__setattr__(self, "receive_id", receive_id)
        object.__setattr__(self, "_aes_key", aes_key)

    @property
    def aes_key(self) -> bytes:
        return self._aes_key  # type: ignore[attr-defined]

    def signature(self, timestamp: str, nonce: str, encrypted: str) -> str:
        values = sorted((self.token, str(timestamp), str(nonce), encrypted))
        return hashlib.sha1("".join(values).encode()).hexdigest()  # noqa: S324 - provider protocol requires SHA-1

    def verify_signature(
        self,
        signature: str,
        timestamp: str,
        nonce: str,
        encrypted: str,
    ) -> bool:
        expected = self.signature(timestamp, nonce, encrypted)
        return hmac.compare_digest(expected, signature.strip())

    def decrypt(self, encrypted: str) -> str:
        try:
            ciphertext = base64.b64decode(encrypted, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise WeComCryptoError("Invalid WeCom encrypted payload") from exc
        if not ciphertext or len(ciphertext) % 16 != 0:
            raise WeComCryptoError("Invalid WeCom encrypted payload length")

        decryptor = Cipher(
            algorithms.AES(self.aes_key),
            modes.CBC(self.aes_key[:16]),
        ).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        plaintext = self._unpad(padded)
        if len(plaintext) < 20:
            raise WeComCryptoError("WeCom decrypted payload is too short")

        message_length = struct.unpack("!I", plaintext[16:20])[0]
        message_end = 20 + message_length
        if message_end > len(plaintext):
            raise WeComCryptoError("Invalid WeCom message length")
        message = plaintext[20:message_end]
        receive_id = plaintext[message_end:].decode("utf-8", errors="strict")
        if receive_id != self.receive_id:
            raise WeComCryptoError("WeCom receive ID mismatch")
        try:
            return message.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WeComCryptoError("WeCom message is not valid UTF-8") from exc

    def encrypt(self, plaintext: str, *, random_prefix: bytes | None = None) -> str:
        """Encrypt a callback response using the official WeCom wire format."""
        prefix = random_prefix if random_prefix is not None else os.urandom(16)
        if len(prefix) != 16:
            raise ValueError("WeCom random prefix must be 16 bytes")
        message = plaintext.encode()
        raw = prefix + struct.pack("!I", len(message)) + message + self.receive_id.encode()
        padded = self._pad(raw)
        encryptor = Cipher(
            algorithms.AES(self.aes_key),
            modes.CBC(self.aes_key[:16]),
        ).encryptor()
        ciphertext = encryptor.update(padded) + encryptor.finalize()
        return base64.b64encode(ciphertext).decode()

    @staticmethod
    def _pad(value: bytes) -> bytes:
        padding_length = _WECOM_PADDING_BLOCK_SIZE - len(value) % _WECOM_PADDING_BLOCK_SIZE
        return value + bytes((padding_length,)) * padding_length

    @staticmethod
    def _unpad(value: bytes) -> bytes:
        if not value:
            raise WeComCryptoError("WeCom decrypted payload is empty")
        padding_length = value[-1]
        if padding_length < 1 or padding_length > _WECOM_PADDING_BLOCK_SIZE:
            raise WeComCryptoError("Invalid WeCom PKCS#7 padding")
        if value[-padding_length:] != bytes((padding_length,)) * padding_length:
            raise WeComCryptoError("Invalid WeCom PKCS#7 padding")
        return value[:-padding_length]
