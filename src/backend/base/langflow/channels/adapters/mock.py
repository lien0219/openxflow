"""In-memory adapter used to validate the channel gateway without external services."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.domain.models import (
    ChannelConversation,
    ChannelEvent,
    ChannelEventType,
    ChannelIncomingMessage,
    ChannelMessage,
    ChannelType,
    ChannelUser,
)


class MockChannelAdapter(ChannelAdapter):
    channel_type = ChannelType.MOCK

    def __init__(self, connection_id: UUID, *, verification_token: str | None = None) -> None:
        self.connection_id = connection_id
        self.verification_token = verification_token
        self.sent_messages: list[dict[str, Any]] = []
        self.updated_messages: list[dict[str, Any]] = []
        self.files: dict[str, tuple[bytes, dict[str, Any]]] = {}

    async def verify_event(self, headers: dict[str, str], payload: bytes) -> bool:
        if self.verification_token is None:
            return True
        return headers.get("x-openxflow-mock-token") == self.verification_token

    async def parse_event(self, headers: dict[str, str], payload: bytes) -> ChannelEvent:
        del headers
        try:
            data = json.loads(payload.decode("utf-8"))
            event_id = str(data.get("event_id") or hashlib.sha256(payload).hexdigest())
            text = data.get("text")
            message_type = ChannelEventType(data.get("event_type", ChannelEventType.TEXT.value))
            return ChannelEvent(
                event_id=event_id,
                channel=self.channel_type,
                connection_id=self.connection_id,
                event_type=message_type,
                user=ChannelUser(
                    external_user_id=str(data.get("user_id", "mock-user")),
                    display_name=data.get("display_name"),
                    tenant_id=data.get("tenant_id"),
                ),
                conversation=ChannelConversation(
                    external_conversation_id=str(data.get("conversation_id", "mock-conversation")),
                    conversation_type=str(data.get("conversation_type", "private")),
                    title=data.get("conversation_title"),
                ),
                message=ChannelIncomingMessage(
                    external_message_id=str(data.get("message_id", event_id)),
                    message_type=message_type,
                    text=text,
                    reply_to_message_id=data.get("reply_to_message_id"),
                ),
                raw_payload=data,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
            raise ValueError("Invalid mock channel event payload") from exc

    async def send_message(self, target_id: str, message: ChannelMessage) -> str:
        external_message_id = f"mock-{len(self.sent_messages) + 1}"
        self.sent_messages.append(
            {
                "external_message_id": external_message_id,
                "target_id": target_id,
                "message": message,
            }
        )
        return external_message_id

    async def update_message(self, external_message_id: str, message: ChannelMessage) -> None:
        self.updated_messages.append({"external_message_id": external_message_id, "message": message})

    async def download_file(self, external_file_id: str) -> tuple[bytes, dict[str, Any]]:
        try:
            return self.files[external_file_id]
        except KeyError as exc:
            raise FileNotFoundError(external_file_id) from exc

    async def healthcheck(self) -> dict[str, Any]:
        return {
            "ok": True,
            "channel": self.channel_type.value,
            "connection_id": str(self.connection_id),
            "sent_messages": len(self.sent_messages),
        }
