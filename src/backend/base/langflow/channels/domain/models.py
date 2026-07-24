from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChannelType(str, Enum):
    TELEGRAM = "telegram"
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    WECOM = "wecom"
    MOCK = "mock"


class ChannelEventType(str, Enum):
    TEXT = "message.text"
    FILE = "message.file"
    IMAGE = "message.image"
    AUDIO = "message.audio"
    COMMAND = "message.command"
    ACTION = "message.action"
    UNKNOWN = "unknown"


class ChannelMessageType(str, Enum):
    TEXT = "text"
    MARKDOWN = "markdown"
    CARD = "card"
    FILE = "file"


class ChannelUser(BaseModel):
    external_user_id: str
    display_name: str | None = None
    openxflow_user_id: UUID | None = None
    tenant_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelConversation(BaseModel):
    external_conversation_id: str
    conversation_type: str = "private"
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelAttachment(BaseModel):
    external_file_id: str | None = None
    filename: str
    mime_type: str | None = None
    size_bytes: int | None = None
    download_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelIncomingMessage(BaseModel):
    external_message_id: str
    message_type: ChannelEventType
    text: str | None = None
    mentions: list[str] = Field(default_factory=list)
    attachments: list[ChannelAttachment] = Field(default_factory=list)
    reply_to_message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelEvent(BaseModel):
    event_id: str
    channel: ChannelType
    connection_id: UUID
    event_type: ChannelEventType
    user: ChannelUser
    conversation: ChannelConversation
    message: ChannelIncomingMessage
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_payload: dict[str, Any] = Field(default_factory=dict, exclude=True)


class ChannelAction(BaseModel):
    action_id: str
    label: str
    style: str = "default"
    value: str | None = None


class ChannelMessage(BaseModel):
    message_type: ChannelMessageType = ChannelMessageType.TEXT
    text: str | None = None
    title: str | None = None
    markdown: str | None = None
    actions: list[ChannelAction] = Field(default_factory=list)
    attachments: list[ChannelAttachment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
