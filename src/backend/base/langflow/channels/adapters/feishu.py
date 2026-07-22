"""Feishu Open Platform adapter for OpenXFlow channels."""

from __future__ import annotations

import hmac
import json
from typing import Any
from uuid import UUID

import httpx

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


class FeishuAPIError(RuntimeError):
    """Raised when Feishu returns a non-zero business code."""


class FeishuChannelAdapter(ChannelAdapter):
    channel_type = ChannelType.FEISHU

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

    async def _tenant_access_token(self) -> str:
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
            event = body["event"]
            message = event["message"]
            sender = event.get("sender") or {}
            sender_id = sender.get("sender_id") or {}
            content = json.loads(message.get("content") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError("Invalid Feishu event payload") from exc

        message_type = str(message.get("message_type") or "text")
        text = self._extract_text(message_type, content)
        attachments = self._extract_attachments(message_type, content, str(message.get("message_id") or ""))
        event_type = self._event_type(message_type, text)
        mentions = [
            str(item.get("id", {}).get("open_id") or item.get("key") or "")
            for item in message.get("mentions") or []
            if item
        ]
        chat_type = str(message.get("chat_type") or "p2p")
        return ChannelEvent(
            event_id=str(header.get("event_id") or message.get("message_id")),
            channel=self.channel_type,
            connection_id=self.connection_id,
            event_type=event_type,
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
                message_type=event_type,
                text=text,
                mentions=[item for item in mentions if item],
                attachments=attachments,
                reply_to_message_id=message.get("parent_id") or message.get("root_id"),
                metadata={"feishu_message_type": message_type},
            ),
            raw_payload=body,
        )

    async def send_message(self, target_id: str, message: ChannelMessage) -> str:
        text = message.markdown or message.text or ""
        if message.title:
            text = f"{message.title}\n\n{text}" if text else message.title
        data = await self._request(
            "POST",
            "im/v1/messages",
            params={"receive_id_type": "chat_id"},
            payload={
                "receive_id": target_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
        return str((data or {}).get("message_id") or "")

    async def update_message(self, external_message_id: str, message: ChannelMessage) -> None:
        text = message.markdown or message.text or ""
        if message.title:
            text = f"{message.title}\n\n{text}" if text else message.title
        await self._request(
            "PATCH",
            f"im/v1/messages/{external_message_id}",
            payload={
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )

    async def download_file(self, external_file_id: str) -> tuple[bytes, dict[str, Any]]:
        message_id, separator, file_key = external_file_id.partition(":")
        if not separator or not message_id or not file_key:
            raise ValueError("Invalid Feishu file identifier")
        token = await self._tenant_access_token()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                f"{self.api_base_url}/im/v1/messages/{message_id}/resources/{file_key}",
                params={"type": "file"},
                headers={"Authorization": f"Bearer {token}"},
            )
        response.raise_for_status()
        return response.content, {
            "content_type": response.headers.get("content-type"),
            "provider": "feishu",
        }

    async def healthcheck(self) -> dict[str, Any]:
        await self._tenant_access_token()
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
    def _extract_text(message_type: str, content: dict[str, Any]) -> str | None:
        if message_type == "text":
            value = content.get("text")
            return str(value) if value is not None else None
        return None

    @staticmethod
    def _event_type(message_type: str, text: str | None) -> ChannelEventType:
        if message_type == "text":
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
        filename = str(content.get("file_name") or content.get("name") or f"feishu-{message_type}")
        return [
            ChannelAttachment(
                external_file_id=f"{message_id}:{file_key}",
                filename=filename,
                metadata={"file_key": file_key, "message_type": message_type},
            )
        ]
