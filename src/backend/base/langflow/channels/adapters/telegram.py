"""Telegram Bot API adapter for OpenXFlow channels."""

from __future__ import annotations

import hmac
import json
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

import httpx
from pydantic import ValidationError

from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.domain.models import (
    ChannelAttachment,
    ChannelConversation,
    ChannelEvent,
    ChannelEventType,
    ChannelIncomingMessage,
    ChannelMessage,
    ChannelMessageType,
    ChannelType,
    ChannelUser,
)

_TELEGRAM_SECRET_HEADER = "x-telegram-bot-api-secret-token"


class TelegramAPIError(RuntimeError):
    """Raised when Telegram returns a failed Bot API response."""


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

    async def _request(self, method: str, *, payload: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.bot_api_url}/{method}", json=payload or {})
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            description = body.get("description", "Telegram API request failed")
            raise TelegramAPIError(description)
        return body.get("result")

    async def verify_event(self, headers: dict[str, str], payload: bytes) -> bool:
        del payload
        if self.webhook_secret is None:
            return True
        provided = headers.get(_TELEGRAM_SECRET_HEADER, "")
        return hmac.compare_digest(provided, self.webhook_secret)

    async def parse_event(self, headers: dict[str, str], payload: bytes) -> ChannelEvent:
        del headers
        try:
            update = json.loads(payload.decode("utf-8"))
            callback_query = update.get("callback_query")
            message = update.get("message") or update.get("edited_message")

            if callback_query is not None:
                return self._parse_callback_query(update, callback_query)
            if message is not None:
                return self._parse_message(update, message)
            raise ValueError("Unsupported Telegram update type")
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, TypeError, KeyError) as exc:
            raise ValueError("Invalid Telegram update payload") from exc

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
                metadata={"callback_query_id": str(callback["id"])},
            ),
            raw_payload=update,
        )

    def _parse_message(self, update: dict[str, Any], message: dict[str, Any]) -> ChannelEvent:
        chat = message["chat"]
        sender = message.get("from") or {}
        text = message.get("text") or message.get("caption")
        attachments, event_type = self._extract_attachments(message)
        if not attachments:
            event_type = ChannelEventType.COMMAND if isinstance(text, str) and text.startswith("/") else ChannelEventType.TEXT

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
                metadata={"message_thread_id": message.get("message_thread_id")},
            ),
            raw_payload=update,
        )

    @staticmethod
    def _build_user(sender: dict[str, Any]) -> ChannelUser:
        first_name = str(sender.get("first_name") or "").strip()
        last_name = str(sender.get("last_name") or "").strip()
        display_name = " ".join(part for part in (first_name, last_name) if part) or sender.get("username")
        return ChannelUser(
            external_user_id=str(sender.get("id", "unknown")),
            display_name=display_name,
            metadata={
                "username": sender.get("username"),
                "language_code": sender.get("language_code"),
                "is_bot": bool(sender.get("is_bot", False)),
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
    def _extract_mentions(message: dict[str, Any], text: str | None) -> list[str]:
        if not text:
            return []
        mentions: list[str] = []
        for entity in message.get("entities") or []:
            if entity.get("type") == "mention":
                offset = int(entity.get("offset", 0))
                length = int(entity.get("length", 0))
                mentions.append(text[offset : offset + length])
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

        return [], ChannelEventType.UNKNOWN

    @staticmethod
    def _message_text(message: ChannelMessage) -> str:
        parts = [part for part in (message.title, message.markdown, message.text) if part]
        return "\n\n".join(parts) or "OpenXFlow"

    @staticmethod
    def _callback_data(value: str) -> str:
        encoded = value.encode("utf-8")[:64]
        while True:
            try:
                return encoded.decode("utf-8")
            except UnicodeDecodeError:
                encoded = encoded[:-1]

    async def send_message(self, target_id: str, message: ChannelMessage) -> str:
        payload: dict[str, Any] = {
            "chat_id": target_id,
            "text": self._message_text(message),
        }
        if message.actions:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [
                        {
                            "text": action.label,
                            "callback_data": self._callback_data(action.value or action.action_id),
                        }
                    ]
                    for action in message.actions
                ]
            }
        result = await self._request("sendMessage", payload=payload)
        chat_id = result.get("chat", {}).get("id", target_id)
        return f"{chat_id}:{result['message_id']}"

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
        await self._request(
            "editMessageText",
            payload={
                "chat_id": chat_id,
                "message_id": int(message_id),
                "text": self._message_text(message),
            },
        )

    async def download_file(self, external_file_id: str) -> tuple[bytes, dict[str, Any]]:
        result = await self._request("getFile", payload={"file_id": external_file_id})
        file_path = result.get("file_path")
        if not file_path:
            raise FileNotFoundError(external_file_id)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(f"{self.api_base_url}/file/bot{self.bot_token}/{file_path}")
        response.raise_for_status()
        return response.content, {
            "file_path": file_path,
            "size_bytes": result.get("file_size"),
            "content_type": response.headers.get("content-type"),
        }

    async def healthcheck(self) -> dict[str, Any]:
        result = await self._request("getMe")
        return {
            "ok": True,
            "channel": self.channel_type.value,
            "connection_id": str(self.connection_id),
            "bot_id": str(result["id"]),
            "username": result.get("username"),
            "display_name": result.get("first_name"),
        }

    async def set_webhook(self, webhook_url: str, *, drop_pending_updates: bool = False) -> bool:
        payload: dict[str, Any] = {
            "url": webhook_url,
            "allowed_updates": ["message", "edited_message", "callback_query"],
            "drop_pending_updates": drop_pending_updates,
        }
        if self.webhook_secret:
            payload["secret_token"] = self.webhook_secret
        return bool(await self._request("setWebhook", payload=payload))
