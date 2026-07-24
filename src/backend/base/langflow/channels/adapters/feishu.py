"""Feishu Open Platform adapter for OpenXFlow channels."""

from __future__ import annotations

import hmac
import json
import time
from typing import Any, ClassVar
from uuid import UUID

import httpx

from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.domain.models import (
    ChannelAction,
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
from langflow.channels.services.loop_lock import LoopLocalAsyncLock


class FeishuAPIError(RuntimeError):
    """Raised when Feishu returns a non-zero business code."""


class FeishuChannelAdapter(ChannelAdapter):
    channel_type = ChannelType.FEISHU
    _token_cache: ClassVar[dict[str, tuple[str, float]]] = {}
    _token_lock: ClassVar[LoopLocalAsyncLock] = LoopLocalAsyncLock()

    def __init__(
        self,
        connection_id: UUID,
        *,
        app_id: str,
        app_secret: str,
        verification_token: str | None = None,
        api_base_url: str = "https://open.feishu.cn/open-apis",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not app_id.strip() or not app_secret.strip():
            raise ValueError("Feishu app_id and app_secret are required")
        self.connection_id = connection_id
        self.app_id = app_id.strip()
        self.app_secret = app_secret.strip()
        self.verification_token = verification_token.strip() if verification_token else None
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @property
    def _token_cache_key(self) -> str:
        return f"{self.api_base_url}:{self.app_id}"

    async def _tenant_access_token(self, *, force_refresh: bool = False) -> str:
        now = time.monotonic()
        cached = self._token_cache.get(self._token_cache_key)
        if not force_refresh and cached is not None and cached[1] > now:
            return cached[0]

        async with self._token_lock:
            now = time.monotonic()
            cached = self._token_cache.get(self._token_cache_key)
            if not force_refresh and cached is not None and cached[1] > now:
                return cached[0]

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.api_base_url}/auth/v3/tenant_access_token/internal",
                    json={"app_id": self.app_id, "app_secret": self.app_secret},
                )
            response.raise_for_status()
            body = response.json()
            if body.get("code", 0) != 0:
                raise FeishuAPIError(body.get("msg", "Unable to obtain Feishu tenant access token"))
            token = body.get("tenant_access_token")
            if not token:
                raise FeishuAPIError("Feishu tenant access token is missing")
            expire_seconds = max(60, int(body.get("expire", 7200)))
            self._token_cache[self._token_cache_key] = (
                str(token),
                time.monotonic() + max(30, expire_seconds - 60),
            )
            return str(token)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        token = await self._tenant_access_token()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.request(
                method,
                f"{self.api_base_url}/{path.lstrip('/')}",
                params=params,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
        response.raise_for_status()
        body = response.json()
        if body.get("code", 0) != 0:
            raise FeishuAPIError(body.get("msg", "Feishu API request failed"))
        return body.get("data")

    async def verify_event(self, headers: dict[str, str], payload: bytes) -> bool:
        del headers
        try:
            body = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        if body.get("encrypt"):
            return False
        if self.verification_token is None:
            return True
        provided = str(body.get("token") or body.get("header", {}).get("token") or "")
        return hmac.compare_digest(provided, self.verification_token)

    async def parse_event(self, headers: dict[str, str], payload: bytes) -> ChannelEvent:
        del headers
        try:
            body = json.loads(payload.decode("utf-8"))
            header = body.get("header") or {}
            event_type = str(header.get("event_type") or "")
            event = body["event"]
            if event_type == "card.action.trigger" or ("action" in event and "message" not in event):
                return self._parse_card_action(body, header, event)
            return self._parse_message_event(body, header, event)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid Feishu event payload") from exc

    def _parse_message_event(
        self,
        body: dict[str, Any],
        header: dict[str, Any],
        event: dict[str, Any],
    ) -> ChannelEvent:
        message = event["message"]
        sender = event.get("sender") or {}
        sender_id = sender.get("sender_id") or {}
        content = json.loads(message.get("content") or "{}")
        message_type = str(message.get("message_type") or "text")
        mentions = [item for item in message.get("mentions") or [] if item]
        text = self._extract_text(message_type, content)
        text = self._strip_mention_placeholders(text, mentions)
        attachments = self._extract_attachments(message_type, content, str(message.get("message_id") or ""))
        normalized_event_type = self._event_type(message_type, text)
        mention_ids = [str(item.get("id", {}).get("open_id") or item.get("key") or "") for item in mentions]
        chat_type = str(message.get("chat_type") or "p2p")
        return ChannelEvent(
            event_id=str(header.get("event_id") or message.get("message_id")),
            channel=self.channel_type,
            connection_id=self.connection_id,
            event_type=normalized_event_type,
            user=ChannelUser(
                external_user_id=str(sender_id.get("open_id") or sender_id.get("user_id") or sender_id.get("union_id")),
                tenant_id=str(header.get("tenant_key") or "") or None,
                metadata={
                    "user_id": sender_id.get("user_id"),
                    "union_id": sender_id.get("union_id"),
                    "sender_type": sender.get("sender_type"),
                },
            ),
            conversation=ChannelConversation(
                external_conversation_id=str(message["chat_id"]),
                conversation_type="private" if chat_type == "p2p" else "group",
                metadata={"chat_type": chat_type},
            ),
            message=ChannelIncomingMessage(
                external_message_id=str(message["message_id"]),
                message_type=normalized_event_type,
                text=text,
                mentions=[item for item in mention_ids if item],
                attachments=attachments,
                reply_to_message_id=message.get("parent_id") or message.get("root_id"),
                metadata={
                    "feishu_message_type": message_type,
                    "feishu_event_type": str(header.get("event_type") or "im.message.receive_v1"),
                },
            ),
            raw_payload=body,
        )

    def _parse_card_action(
        self,
        body: dict[str, Any],
        header: dict[str, Any],
        event: dict[str, Any],
    ) -> ChannelEvent:
        action = event.get("action") or {}
        operator = event.get("operator") or {}
        context = event.get("context") or {}
        value = action.get("value")
        if isinstance(value, dict):
            action_id = str(value.get("action_id") or action.get("name") or action.get("tag") or "action")
            action_value = value.get("value") or value.get("command") or action_id
            text = str(action_value)
        else:
            action_id = str(action.get("name") or action.get("tag") or "action")
            text = str(value or action_id)
        open_id = str(
            operator.get("open_id")
            or (operator.get("operator_id") or {}).get("open_id")
            or event.get("open_id")
            or "unknown"
        )
        chat_id = str(context.get("open_chat_id") or event.get("open_chat_id") or "")
        message_id = str(context.get("open_message_id") or event.get("open_message_id") or header.get("event_id"))
        return ChannelEvent(
            event_id=str(header.get("event_id") or body.get("token") or message_id),
            channel=self.channel_type,
            connection_id=self.connection_id,
            event_type=ChannelEventType.ACTION,
            user=ChannelUser(
                external_user_id=open_id,
                tenant_id=str(header.get("tenant_key") or "") or None,
                metadata={"operator": operator},
            ),
            conversation=ChannelConversation(
                external_conversation_id=chat_id,
                conversation_type="group" if chat_id else "private",
            ),
            message=ChannelIncomingMessage(
                external_message_id=message_id,
                message_type=ChannelEventType.ACTION,
                text=text,
                metadata={
                    "action_id": action_id,
                    "action_value": value,
                    "feishu_event_type": "card.action.trigger",
                },
            ),
            raw_payload=body,
        )

    async def send_message(self, target_id: str, message: ChannelMessage) -> str:
        msg_type, content = self._render_message(message)
        data = await self._request(
            "POST",
            "im/v1/messages",
            params={"receive_id_type": "chat_id"},
            payload={
                "receive_id": target_id,
                "msg_type": msg_type,
                "content": json.dumps(content, ensure_ascii=False),
            },
        )
        return str((data or {}).get("message_id") or "")

    async def send_response(self, event: ChannelEvent, message: ChannelMessage) -> str:
        if event.message.metadata.get("feishu_event_type") == "card.action.trigger":
            return await self.send_message(event.conversation.external_conversation_id, message)
        msg_type, content = self._render_message(message)
        data = await self._request(
            "POST",
            f"im/v1/messages/{event.message.external_message_id}/reply",
            payload={
                "msg_type": msg_type,
                "content": json.dumps(content, ensure_ascii=False),
                "reply_in_thread": False,
            },
        )
        return str((data or {}).get("message_id") or "")

    async def update_message(self, external_message_id: str, message: ChannelMessage) -> None:
        updateable_message = message.model_copy(
            update={
                "message_type": ChannelMessageType.CARD,
                "metadata": {**message.metadata, "feishu_update_multi": True},
            }
        )
        _, content = self._render_message(updateable_message)
        await self._request(
            "PATCH",
            f"im/v1/messages/{external_message_id}",
            payload={"content": json.dumps(content, ensure_ascii=False)},
        )

    async def download_file(self, external_file_id: str) -> tuple[bytes, dict[str, Any]]:
        parts = external_file_id.split(":", 2)
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise ValueError("Invalid Feishu file identifier")
        message_id, file_key = parts[0], parts[1]
        resource_type = parts[2] if len(parts) == 3 else "file"
        token = await self._tenant_access_token()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                f"{self.api_base_url}/im/v1/messages/{message_id}/resources/{file_key}",
                params={"type": resource_type},
                headers={"Authorization": f"Bearer {token}"},
            )
        response.raise_for_status()
        return response.content, {
            "content_type": response.headers.get("content-type"),
            "provider": "feishu",
            "resource_type": resource_type,
        }

    async def healthcheck(self) -> dict[str, Any]:
        await self._tenant_access_token(force_refresh=True)
        return {
            "ok": True,
            "channel": self.channel_type.value,
            "connection_id": str(self.connection_id),
            "app_id": self.app_id,
        }

    @staticmethod
    def is_url_verification(payload: bytes) -> bool:
        try:
            body = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return body.get("type") == "url_verification" and bool(body.get("challenge"))

    @staticmethod
    def get_url_verification_challenge(payload: bytes) -> str:
        body = json.loads(payload.decode("utf-8"))
        return str(body["challenge"])

    @staticmethod
    def _strip_mention_placeholders(text: str | None, mentions: list[dict[str, Any]]) -> str | None:
        if text is None:
            return None
        cleaned = text
        for mention in mentions:
            key = mention.get("key")
            if isinstance(key, str) and key:
                cleaned = cleaned.replace(key, " ")
        normalized = " ".join(cleaned.split())
        return normalized or None

    @staticmethod
    def _extract_text(message_type: str, content: dict[str, Any]) -> str | None:
        if message_type == "text":
            value = content.get("text")
            return str(value) if value is not None else None
        if message_type == "post":
            fragments: list[str] = []
            title = content.get("title")
            if isinstance(title, str) and title.strip():
                fragments.append(title.strip())
            for paragraph in content.get("content") or []:
                paragraph_parts: list[str] = []
                for element in paragraph or []:
                    tag = element.get("tag")
                    if tag in {"text", "a", "code"}:
                        value = element.get("text") or element.get("href")
                    elif tag == "at":
                        value = element.get("user_name")
                    else:
                        value = None
                    if isinstance(value, str) and value.strip():
                        paragraph_parts.append(value.strip())
                if paragraph_parts:
                    fragments.append(" ".join(paragraph_parts))
            return "\n".join(fragments) or None
        return None

    @staticmethod
    def _event_type(message_type: str, text: str | None) -> ChannelEventType:
        if message_type in {"text", "post"}:
            return ChannelEventType.COMMAND if text and text.lstrip().startswith("/") else ChannelEventType.TEXT
        if message_type in {"file", "media"}:
            return ChannelEventType.FILE
        if message_type == "image":
            return ChannelEventType.IMAGE
        if message_type == "audio":
            return ChannelEventType.AUDIO
        return ChannelEventType.UNKNOWN

    @staticmethod
    def _extract_attachments(
        message_type: str,
        content: dict[str, Any],
        message_id: str,
    ) -> list[ChannelAttachment]:
        if message_type not in {"file", "media", "image", "audio"}:
            return []
        file_key = content.get("file_key") or content.get("image_key")
        if not file_key:
            return []
        resource_type = "image" if message_type == "image" else "file"
        default_extension = {"image": ".jpg", "audio": ".opus"}.get(message_type, "")
        filename = str(content.get("file_name") or content.get("name") or f"feishu-{message_type}{default_extension}")
        return [
            ChannelAttachment(
                external_file_id=f"{message_id}:{file_key}:{resource_type}",
                filename=filename,
                metadata={
                    "file_key": file_key,
                    "message_type": message_type,
                    "resource_type": resource_type,
                },
            )
        ]

    @classmethod
    def _render_message(cls, message: ChannelMessage) -> tuple[str, dict[str, Any]]:
        body = message.markdown or message.text or ""
        if message.actions or message.message_type == ChannelMessageType.CARD:
            elements: list[dict[str, Any]] = []
            if body:
                elements.append({"tag": "markdown", "content": body})
            if message.actions:
                elements.append(
                    {
                        "tag": "action",
                        "actions": [cls._render_action(action) for action in message.actions],
                    }
                )
            config: dict[str, Any] = {"wide_screen_mode": True}
            if message.metadata.get("feishu_update_multi"):
                config["update_multi"] = True
            card: dict[str, Any] = {
                "config": config,
                "elements": elements,
            }
            if message.title:
                card["header"] = {
                    "template": "blue",
                    "title": {"tag": "plain_text", "content": message.title},
                }
            return "interactive", card

        text = body
        if message.title:
            text = f"{message.title}\n\n{text}" if text else message.title
        return "text", {"text": text}

    @staticmethod
    def _render_action(action: ChannelAction) -> dict[str, Any]:
        button_type = {
            "primary": "primary",
            "danger": "danger",
            "destructive": "danger",
        }.get(action.style, "default")
        return {
            "tag": "button",
            "text": {"tag": "plain_text", "content": action.label},
            "type": button_type,
            "value": {
                "action_id": action.action_id,
                "value": action.value or action.action_id,
            },
        }
