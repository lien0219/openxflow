"""WeCom AI Bot webhook adapter for private and internal group conversations."""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import time
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.domain.models import (
    ChannelAttachment,
    ChannelConversation,
    ChannelEvent,
    ChannelEventType,
    ChannelIncomingMessage,
    ChannelMessage,
    ChannelType,
    ChannelUser,
)
from langflow.channels.security.wecom_ai_crypto import WeComAIBotCrypt, WeComAIBotCryptoError
from langflow.channels.services.provider_http import (
    channel_download_limit_bytes,
    download_provider_file,
    provider_http_client_for_url,
)

_CALLBACK_MAX_AGE_SECONDS = 5 * 60
_ALLOWED_MEDIA_HOST_SUFFIXES = (
    ".qq.com",
    ".qpic.cn",
    ".weixin.qq.com",
    ".work.weixin.qq.com",
)


class WeComAIBotAPIError(RuntimeError):
    """Raised when a WeCom AI Bot provider operation fails."""


class WeComAIBotChannelAdapter(ChannelAdapter):
    """Normalize the encrypted JSON protocol used by WeCom API-mode AI bots."""

    channel_type = ChannelType.WECOM

    def __init__(
        self,
        connection_id: UUID,
        *,
        token: str,
        encoding_aes_key: str,
        bot_name: str | None = None,
        message_push_webhook_url: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.connection_id = connection_id
        self.crypt = WeComAIBotCrypt(token, encoding_aes_key)
        self.bot_name = bot_name.strip() if bot_name else None
        self.message_push_webhook_url = message_push_webhook_url.strip() if message_push_webhook_url else None
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        if self.message_push_webhook_url:
            self._validate_push_webhook_url(self.message_push_webhook_url)

    @staticmethod
    def _timestamp_is_fresh(timestamp: str) -> bool:
        try:
            parsed = int(timestamp)
        except (TypeError, ValueError):
            return False
        return abs(int(time.time()) - parsed) <= _CALLBACK_MAX_AGE_SECONDS

    def verify_url(self, *, signature: str, timestamp: str, nonce: str, echo: str) -> str:
        if not self._timestamp_is_fresh(timestamp):
            raise PermissionError("Expired WeCom AI Bot callback timestamp")
        try:
            return self.crypt.verify_url(
                signature=signature,
                timestamp=timestamp,
                nonce=nonce,
                echo=echo,
            )
        except WeComAIBotCryptoError as exc:
            raise PermissionError(str(exc)) from exc

    def decrypt_event(self, headers: dict[str, str], payload: bytes) -> dict[str, Any]:
        timestamp = headers.get("x-wecom-timestamp", "")
        nonce = headers.get("x-wecom-nonce", "")
        signature = headers.get("x-wecom-msg-signature", "")
        if not timestamp or not nonce or not signature or not self._timestamp_is_fresh(timestamp):
            raise PermissionError("Invalid or expired WeCom AI Bot callback parameters")
        try:
            return self.crypt.decrypt_payload(
                payload,
                signature=signature,
                timestamp=timestamp,
                nonce=nonce,
            )
        except WeComAIBotCryptoError as exc:
            raise PermissionError(str(exc)) from exc

    async def verify_event(self, headers: dict[str, str], payload: bytes) -> bool:
        try:
            self.decrypt_event(headers, payload)
        except PermissionError:
            return False
        return True

    async def parse_event(self, headers: dict[str, str], payload: bytes) -> ChannelEvent:
        return self.parse_decrypted_event(self.decrypt_event(headers, payload))

    def parse_decrypted_event(self, message: dict[str, Any]) -> ChannelEvent:
        msg_type = str(message.get("msgtype") or "").strip().lower()
        if msg_type not in {"text", "image", "mixed"}:
            raise ValueError(f"Unsupported WeCom AI Bot message type: {msg_type or 'unknown'}")

        sender = message.get("from") if isinstance(message.get("from"), dict) else {}
        user_id = str(sender.get("userid") or "").strip()
        if not user_id:
            raise ValueError("WeCom AI Bot sender ID is missing")
        chat_type = str(message.get("chattype") or "single").strip().lower()
        is_group = chat_type == "group"
        chat_id = str(message.get("chatid") or "").strip()
        if is_group and not chat_id:
            raise ValueError("WeCom AI Bot group chat ID is missing")

        text, attachments, event_type = self._extract_content(message, msg_type)
        message_id = self._message_id(message)
        conversation_id = f"group:{chat_id}" if is_group else f"user:{user_id}"
        mentions = ["__bot__"] if is_group else []
        return ChannelEvent(
            event_id=message_id,
            channel=self.channel_type,
            connection_id=self.connection_id,
            event_type=event_type,
            user=ChannelUser(
                external_user_id=user_id,
                display_name=str(sender.get("name") or sender.get("alias") or "") or None,
                metadata={"wecom_ai_bot": True},
            ),
            conversation=ChannelConversation(
                external_conversation_id=conversation_id,
                conversation_type="group" if is_group else "private",
                title=str(message.get("chatname") or "") or None,
                metadata={"chat_id": chat_id or None, "chat_type": chat_type},
            ),
            message=ChannelIncomingMessage(
                external_message_id=message_id,
                message_type=event_type,
                text=text,
                mentions=mentions,
                attachments=attachments,
                metadata={"wecom_ai_bot": True, "raw_msgtype": msg_type},
            ),
            raw_payload=message,
        )

    @staticmethod
    def _message_id(message: dict[str, Any]) -> str:
        for key in ("msgid", "msg_id", "message_id", "request_id"):
            value = message.get(key)
            if value not in {None, ""}:
                return str(value)
        canonical = json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"wecom-ai-{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"

    def _extract_content(
        self,
        message: dict[str, Any],
        msg_type: str,
    ) -> tuple[str | None, list[ChannelAttachment], ChannelEventType]:
        if msg_type == "text":
            text_block = message.get("text") if isinstance(message.get("text"), dict) else {}
            text = str(text_block.get("content") or "").strip()
            return text or None, [], ChannelEventType.COMMAND if text.startswith("/") else ChannelEventType.TEXT

        if msg_type == "image":
            image = message.get("image") if isinstance(message.get("image"), dict) else {}
            attachment = self._image_attachment(image, 0)
            return None, [attachment] if attachment else [], ChannelEventType.IMAGE

        mixed = message.get("mixed") if isinstance(message.get("mixed"), dict) else {}
        items = mixed.get("msg_item") if isinstance(mixed.get("msg_item"), list) else []
        text_parts: list[str] = []
        attachments: list[ChannelAttachment] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("msgtype") or "").lower()
            if item_type == "text" and isinstance(item.get("text"), dict):
                content = str(item["text"].get("content") or "").strip()
                if content:
                    text_parts.append(content)
            elif item_type == "image" and isinstance(item.get("image"), dict):
                attachment = self._image_attachment(item["image"], index)
                if attachment:
                    attachments.append(attachment)
        text = "\n".join(text_parts) or None
        if attachments and not text:
            event_type = ChannelEventType.IMAGE
        elif text and text.startswith("/"):
            event_type = ChannelEventType.COMMAND
        else:
            event_type = ChannelEventType.TEXT
        return text, attachments, event_type

    def _image_attachment(self, image: dict[str, Any], index: int) -> ChannelAttachment | None:
        url = str(image.get("url") or "").strip()
        if not url:
            return None
        aes_key = str(image.get("aeskey") or self.crypt.encoding_aes_key).strip()
        filename = str(image.get("filename") or f"wecom-ai-image-{index}.jpg")
        identifier = self._encode_media_identifier({"url": url, "aes_key": aes_key, "filename": filename})
        return ChannelAttachment(
            external_file_id=identifier,
            filename=filename,
            mime_type="image/jpeg",
            metadata={"kind": "image", "encrypted": True},
        )

    @staticmethod
    def _encode_media_identifier(value: dict[str, str]) -> str:
        encoded = base64.urlsafe_b64encode(json.dumps(value, ensure_ascii=False).encode()).decode().rstrip("=")
        return f"wecom-ai:{encoded}"

    @staticmethod
    def _decode_media_identifier(value: str) -> dict[str, str]:
        prefix, separator, encoded = value.partition(":")
        if prefix != "wecom-ai" or not separator or not encoded:
            raise ValueError("Invalid WeCom AI Bot media identifier")
        try:
            decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            payload = json.loads(decoded.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
            raise ValueError("Invalid WeCom AI Bot media identifier") from exc
        if not isinstance(payload, dict) or not payload.get("url"):
            raise ValueError("Invalid WeCom AI Bot media identifier")
        return {str(key): str(item) for key, item in payload.items()}

    @staticmethod
    def _validate_media_url(url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("WeCom AI Bot media URL must be provider HTTPS")
        host = parsed.hostname.lower().rstrip(".")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and (address.is_private or address.is_loopback or address.is_link_local):
            raise ValueError("WeCom AI Bot media URL cannot target a private address")
        if address is None and not any(host == suffix[1:] or host.endswith(suffix) for suffix in _ALLOWED_MEDIA_HOST_SUFFIXES):
            raise ValueError("Untrusted WeCom AI Bot media host")

    async def download_file(self, external_file_id: str) -> tuple[bytes, dict[str, Any]]:
        identifier = self._decode_media_identifier(external_file_id)
        url = identifier["url"]
        self._validate_media_url(url)
        client = provider_http_client_for_url("wecom-ai-media", url, self.timeout_seconds)
        downloaded = await download_provider_file(
            client,
            url,
            max_bytes=channel_download_limit_bytes(),
        )
        decrypted = self._decrypt_media(downloaded.content, identifier.get("aes_key") or self.crypt.encoding_aes_key)
        return decrypted, {
            "provider": "wecom-ai",
            "content_type": downloaded.headers.get("content-type") or "image/jpeg",
            "filename": identifier.get("filename"),
            "size_bytes": len(decrypted),
        }

    @staticmethod
    def _decrypt_media(encrypted: bytes, encoding_aes_key: str) -> bytes:
        try:
            aes_key = base64.b64decode(encoding_aes_key + "=" * (-len(encoding_aes_key) % 4), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid WeCom AI Bot media AES key") from exc
        if len(aes_key) != 32 or not encrypted or len(encrypted) % 16 != 0:
            raise ValueError("Invalid WeCom AI Bot encrypted media")
        decryptor = Cipher(algorithms.AES(aes_key), modes.CBC(aes_key[:16])).decryptor()
        padded = decryptor.update(encrypted) + decryptor.finalize()
        padding_length = padded[-1]
        if padding_length < 1 or padding_length > 32:
            raise ValueError("Invalid WeCom AI Bot media padding")
        if padded[-padding_length:] != bytes((padding_length,)) * padding_length:
            raise ValueError("Invalid WeCom AI Bot media padding")
        return padded[:-padding_length]

    @staticmethod
    def _validate_push_webhook_url(url: str) -> None:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "qyapi.weixin.qq.com"
            or parsed.path != "/cgi-bin/webhook/send"
            or "key=" not in parsed.query
        ):
            raise ValueError("WeCom AI Bot message push URL must be an official group webhook URL")

    async def send_message(self, target_id: str, message: ChannelMessage) -> str:
        del target_id
        if not self.message_push_webhook_url:
            raise NotImplementedError(
                "WeCom AI Bot proactive delivery requires a message_push_webhook_url credential"
            )
        content = self.render_message_text(message)
        client = provider_http_client_for_url(
            "wecom-ai-push",
            self.message_push_webhook_url,
            self.timeout_seconds,
        )
        response = await client.post(
            self.message_push_webhook_url,
            json={"msgtype": "text", "text": {"content": self.truncate_utf8(content, 2048)}},
        )
        response.raise_for_status()
        body = response.json() if response.content else {}
        if not isinstance(body, dict) or body.get("errcode") not in {0, "0", None}:
            raise WeComAIBotAPIError(str(body.get("errmsg") if isinstance(body, dict) else "Invalid response"))
        return str(body.get("msgid") or "wecom-ai-push")

    @staticmethod
    def render_message_text(message: ChannelMessage) -> str:
        parts = [part for part in (message.title, message.markdown, message.text) if part]
        if message.actions:
            parts.append("\n".join(f"{action.label}：{action.value or action.action_id}" for action in message.actions))
        return "\n\n".join(parts) or "OpenXFlow"

    @staticmethod
    def truncate_utf8(value: str, max_bytes: int) -> str:
        encoded = value.encode("utf-8")
        if len(encoded) <= max_bytes:
            return value
        suffix = "…"
        budget = max(0, max_bytes - len(suffix.encode("utf-8")))
        clipped = encoded[:budget]
        while clipped:
            try:
                return clipped.decode("utf-8") + suffix
            except UnicodeDecodeError:
                clipped = clipped[:-1]
        return suffix if max_bytes >= len(suffix.encode("utf-8")) else ""

    def encrypted_stream_response(
        self,
        *,
        stream_id: str,
        content: str,
        finish: bool,
        timestamp: str,
        nonce: str,
    ) -> str:
        return self.crypt.encrypt_response(
            {
                "msgtype": "stream",
                "stream": {
                    "id": stream_id,
                    "finish": finish,
                    "content": self.truncate_utf8(content, 2048),
                },
            },
            timestamp=timestamp,
            nonce=nonce,
        )

    async def healthcheck(self) -> dict[str, Any]:
        return {
            "ok": True,
            "channel": self.channel_type.value,
            "mode": "ai_bot",
            "connection_id": str(self.connection_id),
            "proactive_push_configured": bool(self.message_push_webhook_url),
        }
