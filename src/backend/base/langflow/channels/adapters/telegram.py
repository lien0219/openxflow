"""Telegram Bot API adapter for OpenXFlow channels."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from pydantic import ValidationError

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
from langflow.channels.services.provider_http import (
    ChannelDownloadTooLargeError,
    channel_download_limit_bytes,
    download_provider_file,
    provider_http_client,
)

_TELEGRAM_SECRET_HEADER = "x-telegram-bot-api-secret-token"  # pragma: allowlist secret
_TELEGRAM_ALLOWED_UPDATES = (
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
    "callback_query",
)


class TelegramAPIError(RuntimeError):
    """Raised when Telegram returns a failed Bot API response."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after
        self.retryable = code == 429 or bool(code and code >= 500)


class TelegramChannelAdapter(ChannelAdapter):
    channel_type = ChannelType.TELEGRAM

    def __init__(
        self,
        connection_id: UUID,
        *,
        bot_token: str,
        webhook_secret: str | None = None,
        api_base_url: str = "https://api.telegram.org",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not bot_token.strip():
            msg = "Telegram bot_token is required"
            raise ValueError(msg)
        self.connection_id = connection_id
        self.bot_token = bot_token.strip()
        self.webhook_secret = webhook_secret
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @property
    def bot_api_url(self) -> str:
        return f"{self.api_base_url}/bot{self.bot_token}"

    @property
    def _http_client(self):  # type: ignore[no-untyped-def]
        return provider_http_client("telegram", self.api_base_url, self.timeout_seconds)

    async def _request(self, method: str, *, payload: dict[str, Any] | None = None) -> Any:
        response = await self._http_client.post(f"{self.bot_api_url}/{method}", json=payload or {})
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise TelegramAPIError("Invalid Telegram API response")
        if not body.get("ok"):
            description = str(body.get("description") or "Telegram API request failed")
            parameters = body.get("parameters") if isinstance(body.get("parameters"), dict) else {}
            retry_after_value = parameters.get("retry_after")
            try:
                retry_after = float(retry_after_value) if retry_after_value is not None else None
            except (TypeError, ValueError):
                retry_after = None
            error_code = body.get("error_code")
            raise TelegramAPIError(
                description,
                code=int(error_code) if isinstance(error_code, int) else None,
                retry_after=retry_after,
            )
        return body.get("result")

    async def verify_event(self, headers: dict[str, str], payload: bytes) -> bool:
        del payload
        if self.webhook_secret is None:
            return False
        provided = headers.get(_TELEGRAM_SECRET_HEADER, "")
        return hmac.compare_digest(provided, self.webhook_secret)

    async def parse_event(self, headers: dict[str, str], payload: bytes) -> ChannelEvent:
        del headers
        try:
            update = json.loads(payload.decode("utf-8"))
            callback_query = update.get("callback_query")
            update_type, message = self._message_update(update)

            if callback_query is not None:
                return self._parse_callback_query(update, callback_query)
            if message is not None:
                return self._parse_message(update, message, update_type=update_type)
            raise ValueError("Unsupported Telegram update type")
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, TypeError, KeyError) as exc:
            raise ValueError("Invalid Telegram update payload") from exc

    @staticmethod
    def _message_update(update: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        for update_type in ("message", "edited_message", "channel_post", "edited_channel_post"):
            value = update.get(update_type)
            if isinstance(value, dict):
                return update_type, value
        return "", None

    def _parse_callback_query(self, update: dict[str, Any], callback: dict[str, Any]) -> ChannelEvent:
        source_message = callback.get("message") or {}
        chat = source_message.get("chat") or {}
        sender = callback.get("from") or {}
        external_message_id = str(source_message.get("message_id") or callback["id"])
        return ChannelEvent(
            event_id=str(update.get("update_id", callback["id"])),
            channel=self.channel_type,
            connection_id=self.connection_id,
            event_type=ChannelEventType.ACTION,
            user=self._build_user(sender),
            conversation=self._build_conversation(chat),
            message=ChannelIncomingMessage(
                external_message_id=external_message_id,
                message_type=ChannelEventType.ACTION,
                text=str(callback.get("data") or ""),
                metadata={
                    "callback_query_id": str(callback["id"]),
                    "message_thread_id": source_message.get("message_thread_id"),
                },
            ),
            raw_payload=update,
        )

    def _parse_message(
        self,
        update: dict[str, Any],
        message: dict[str, Any],
        *,
        update_type: str,
    ) -> ChannelEvent:
        chat = message["chat"]
        sender = message.get("from") or message.get("sender_chat") or chat
        text = message.get("text") or message.get("caption")
        attachments, event_type = self._extract_attachments(message)
        if not attachments:
            event_type = (
                ChannelEventType.COMMAND if isinstance(text, str) and text.startswith("/") else ChannelEventType.TEXT
            )

        reply = message.get("reply_to_message") or {}
        return ChannelEvent(
            event_id=str(update.get("update_id", message["message_id"])),
            channel=self.channel_type,
            connection_id=self.connection_id,
            event_type=event_type,
            user=self._build_user(sender),
            conversation=self._build_conversation(chat),
            message=ChannelIncomingMessage(
                external_message_id=str(message["message_id"]),
                message_type=event_type,
                text=text,
                mentions=self._extract_mentions(message, text),
                attachments=attachments,
                reply_to_message_id=str(reply["message_id"]) if reply.get("message_id") is not None else None,
                metadata={
                    "message_thread_id": message.get("message_thread_id"),
                    "media_group_id": message.get("media_group_id"),
                    "is_topic_message": bool(message.get("is_topic_message", False)),
                    "telegram_update_type": update_type,
                },
            ),
            raw_payload=update,
        )

    @staticmethod
    def _build_user(sender: dict[str, Any]) -> ChannelUser:
        first_name = str(sender.get("first_name") or "").strip()
        last_name = str(sender.get("last_name") or "").strip()
        display_name = (
            " ".join(part for part in (first_name, last_name) if part) or sender.get("title") or sender.get("username")
        )
        sender_id = sender.get("id")
        return ChannelUser(
            external_user_id=str(sender_id if sender_id is not None else "unknown"),
            display_name=str(display_name) if display_name else None,
            metadata={
                "username": sender.get("username"),
                "language_code": sender.get("language_code"),
                "is_bot": bool(sender.get("is_bot", False)),
                "sender_chat_type": sender.get("type"),
            },
        )

    @staticmethod
    def _build_conversation(chat: dict[str, Any]) -> ChannelConversation:
        chat_type = str(chat.get("type") or "private")
        title = chat.get("title") or chat.get("username")
        return ChannelConversation(
            external_conversation_id=str(chat.get("id", "unknown")),
            conversation_type=chat_type,
            title=title,
            metadata={"username": chat.get("username")},
        )

    @staticmethod
    def _utf16_slice(text: str, offset: int, length: int) -> str:
        if offset < 0 or length < 0:
            raise ValueError("Telegram entity offsets cannot be negative")
        encoded = text.encode("utf-16-le")
        start = offset * 2
        end = start + length * 2
        if end > len(encoded):
            raise ValueError("Telegram entity offset exceeds message text")
        try:
            return encoded[start:end].decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise ValueError("Telegram entity splits a UTF-16 code point") from exc

    @staticmethod
    def _extract_mentions(message: dict[str, Any], text: str | None) -> list[str]:
        if not text:
            return []
        mentions: list[str] = []
        entities = message.get("entities") or message.get("caption_entities") or []
        for entity in entities:
            if entity.get("type") == "mention":
                offset = int(entity.get("offset", 0))
                length = int(entity.get("length", 0))
                mention = TelegramChannelAdapter._utf16_slice(text, offset, length)
                mentions.append(mention.removeprefix("@"))
            elif entity.get("type") == "text_mention" and entity.get("user", {}).get("id") is not None:
                mentions.append(str(entity["user"]["id"]))
        return mentions

    @staticmethod
    def _extract_attachments(message: dict[str, Any]) -> tuple[list[ChannelAttachment], ChannelEventType]:
        document = message.get("document")
        if document:
            filename = document.get("file_name") or f"telegram-document-{document.get('file_unique_id', 'file')}"
            return [
                ChannelAttachment(
                    external_file_id=str(document["file_id"]),
                    filename=filename,
                    mime_type=document.get("mime_type"),
                    size_bytes=document.get("file_size"),
                    metadata={"file_unique_id": document.get("file_unique_id")},
                )
            ], ChannelEventType.FILE

        photos = message.get("photo") or []
        if photos:
            photo = photos[-1]
            unique_id = photo.get("file_unique_id", "image")
            return [
                ChannelAttachment(
                    external_file_id=str(photo["file_id"]),
                    filename=f"telegram-photo-{unique_id}.jpg",
                    mime_type="image/jpeg",
                    size_bytes=photo.get("file_size"),
                    metadata={"width": photo.get("width"), "height": photo.get("height")},
                )
            ], ChannelEventType.IMAGE

        media = message.get("audio") or message.get("voice")
        if media:
            extension = PurePosixPath(media.get("file_name") or "").suffix or ".ogg"
            unique_id = media.get("file_unique_id", "audio")
            return [
                ChannelAttachment(
                    external_file_id=str(media["file_id"]),
                    filename=media.get("file_name") or f"telegram-audio-{unique_id}{extension}",
                    mime_type=media.get("mime_type") or "audio/ogg",
                    size_bytes=media.get("file_size"),
                    metadata={"duration": media.get("duration")},
                )
            ], ChannelEventType.AUDIO

        video = message.get("video") or message.get("animation")
        if video:
            unique_id = video.get("file_unique_id", "video")
            extension = PurePosixPath(video.get("file_name") or "").suffix or ".mp4"
            return [
                ChannelAttachment(
                    external_file_id=str(video["file_id"]),
                    filename=video.get("file_name") or f"telegram-video-{unique_id}{extension}",
                    mime_type=video.get("mime_type") or "video/mp4",
                    size_bytes=video.get("file_size"),
                    metadata={"duration": video.get("duration")},
                )
            ], ChannelEventType.FILE

        return [], ChannelEventType.UNKNOWN

    @staticmethod
    def _message_text(message: ChannelMessage) -> str:
        parts = [part for part in (message.title, message.markdown, message.text) if part]
        return "\n\n".join(parts) or "OpenXFlow"

    @staticmethod
    def _callback_data(value: str, fallback: str) -> str:
        for candidate in (value, fallback):
            encoded = candidate.encode("utf-8")
            if len(encoded) <= 64:
                return candidate
        return f"oxf:{hashlib.sha256(fallback.encode()).hexdigest()[:32]}"

    @classmethod
    def _reply_markup(cls, message: ChannelMessage) -> dict[str, Any] | None:
        if not message.actions:
            return None
        return {
            "inline_keyboard": [
                [
                    {
                        "text": action.label,
                        "callback_data": cls._callback_data(action.value or action.action_id, action.action_id),
                    }
                ]
                for action in message.actions
            ]
        }

    async def _send_message(
        self,
        target_id: str,
        message: ChannelMessage,
        *,
        reply_to_message_id: str | None = None,
        message_thread_id: int | str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "chat_id": target_id,
            "text": self._message_text(message),
        }
        if reply_to_message_id:
            try:
                payload["reply_parameters"] = {"message_id": int(reply_to_message_id)}
            except ValueError:
                pass
        if message_thread_id not in {None, ""}:
            try:
                payload["message_thread_id"] = int(message_thread_id)
            except (TypeError, ValueError):
                pass
        reply_markup = self._reply_markup(message)
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = await self._request("sendMessage", payload=payload)
        chat_id = result.get("chat", {}).get("id", target_id)
        return f"{chat_id}:{result['message_id']}"

    async def send_message(self, target_id: str, message: ChannelMessage) -> str:
        return await self._send_message(target_id, message)

    async def send_response(self, event: ChannelEvent, message: ChannelMessage) -> str:
        return await self._send_message(
            event.conversation.external_conversation_id,
            message,
            reply_to_message_id=event.message.external_message_id,
            message_thread_id=event.message.metadata.get("message_thread_id"),
        )

    def requires_event_acknowledgement(self, event: ChannelEvent) -> bool:
        return bool(event.message.metadata.get("callback_query_id"))

    async def acknowledge_event(self, event: ChannelEvent) -> None:
        callback_query_id = event.message.metadata.get("callback_query_id")
        if callback_query_id:
            await self._request("answerCallbackQuery", payload={"callback_query_id": callback_query_id})

    async def update_message(self, external_message_id: str, message: ChannelMessage) -> None:
        try:
            chat_id, message_id = external_message_id.rsplit(":", 1)
        except ValueError as exc:
            raise ValueError("Telegram message identifier must use '<chat_id>:<message_id>'") from exc
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": int(message_id),
            "text": self._message_text(message),
        }
        reply_markup = self._reply_markup(message)
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        await self._request("editMessageText", payload=payload)

    async def download_file(self, external_file_id: str) -> tuple[bytes, dict[str, Any]]:
        result = await self._request("getFile", payload={"file_id": external_file_id})
        file_path = result.get("file_path")
        if not file_path:
            raise FileNotFoundError(external_file_id)
        limit = channel_download_limit_bytes()
        reported_size = result.get("file_size")
        if isinstance(reported_size, int) and reported_size > limit:
            raise ChannelDownloadTooLargeError(limit_bytes=limit, actual_bytes=reported_size)
        downloaded = await download_provider_file(
            self._http_client,
            f"{self.api_base_url}/file/bot{self.bot_token}/{file_path}",
            max_bytes=limit,
        )
        return downloaded.content, {
            "file_path": file_path,
            "size_bytes": reported_size or len(downloaded.content),
            "content_type": downloaded.headers.get("content-type"),
        }

    async def healthcheck(self) -> dict[str, Any]:
        identity = await self._request("getMe")
        webhook = await self._request("getWebhookInfo")
        webhook = webhook if isinstance(webhook, dict) else {}
        return {
            "ok": True,
            "channel": self.channel_type.value,
            "connection_id": str(self.connection_id),
            "bot_id": str(identity["id"]),
            "username": identity.get("username"),
            "display_name": identity.get("first_name"),
            "webhook_url": webhook.get("url"),
            "pending_update_count": webhook.get("pending_update_count", 0),
            "last_webhook_error": webhook.get("last_error_message"),
        }

    async def set_webhook(self, webhook_url: str, *, drop_pending_updates: bool = False) -> bool:
        payload: dict[str, Any] = {
            "url": webhook_url,
            "allowed_updates": list(_TELEGRAM_ALLOWED_UPDATES),
            "drop_pending_updates": drop_pending_updates,
        }
        if not self.webhook_secret:
            raise ValueError("Telegram webhook_secret is required before configuring a webhook")
        payload["secret_token"] = self.webhook_secret
        return bool(await self._request("setWebhook", payload=payload))

    async def delete_webhook(self, *, drop_pending_updates: bool = False) -> bool:
        return bool(
            await self._request(
                "deleteWebhook",
                payload={"drop_pending_updates": drop_pending_updates},
            )
        )
