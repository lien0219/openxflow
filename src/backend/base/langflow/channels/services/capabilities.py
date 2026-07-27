"""Provider capability metadata shared by runtime and channel-management UI."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChannelProviderCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversation_types: tuple[str, ...]
    supports_private_chat: bool = True
    supports_group_chat: bool = False
    supports_channel_chat: bool = False
    supports_mentions: bool = False
    supports_reply_reference: bool = False
    supports_message_update: bool = False
    supports_processing_indicator: bool = False
    supports_processing_message: bool = False
    supports_interactive_card: bool = False
    supports_file_upload: bool = False
    supports_threads: bool = False
    supports_streaming_connection: bool = False
    processing_message_type: str = "text"
    processing_message_metadata: dict[str, Any] = Field(default_factory=dict)
    max_text_length: int = Field(default=4000, ge=256)
    max_actions: int = Field(default=6, ge=0)


PROVIDER_CAPABILITIES: dict[str, ChannelProviderCapabilities] = {
    "telegram": ChannelProviderCapabilities(
        conversation_types=("private", "group", "supergroup", "channel"),
        supports_group_chat=True,
        supports_channel_chat=True,
        supports_mentions=True,
        supports_reply_reference=True,
        supports_message_update=True,
        supports_processing_message=True,
        supports_interactive_card=True,
        supports_file_upload=True,
        supports_threads=True,
        max_text_length=3900,
        max_actions=50,
    ),
    "feishu": ChannelProviderCapabilities(
        conversation_types=("private", "group"),
        supports_group_chat=True,
        supports_mentions=True,
        supports_reply_reference=True,
        supports_message_update=True,
        supports_processing_message=True,
        supports_interactive_card=True,
        supports_file_upload=True,
        supports_threads=True,
        processing_message_type="card",
        processing_message_metadata={"feishu_update_multi": True},
        max_text_length=12000,
        max_actions=20,
    ),
    "dingtalk": ChannelProviderCapabilities(
        conversation_types=("private", "group"),
        supports_group_chat=True,
        supports_mentions=True,
        supports_interactive_card=True,
        supports_file_upload=True,
        supports_streaming_connection=True,
        max_text_length=18000,
        max_actions=20,
    ),
    "wecom": ChannelProviderCapabilities(
        conversation_types=("private",),
        supports_file_upload=True,
        supports_interactive_card=True,
        max_text_length=1800,
        max_actions=6,
    ),
    "mock": ChannelProviderCapabilities(
        conversation_types=("private", "group"),
        supports_group_chat=True,
        supports_mentions=True,
        supports_file_upload=True,
        max_text_length=20000,
        max_actions=20,
    ),
}


def get_provider_capabilities() -> dict[str, ChannelProviderCapabilities]:
    return PROVIDER_CAPABILITIES.copy()


def get_provider_capability(channel_type: str) -> ChannelProviderCapabilities | None:
    return PROVIDER_CAPABILITIES.get(channel_type.strip().lower())


def validate_provider_conversation_type(channel_type: str, conversation_type: str) -> bool:
    capabilities = get_provider_capability(channel_type)
    return capabilities is not None and conversation_type in capabilities.conversation_types
