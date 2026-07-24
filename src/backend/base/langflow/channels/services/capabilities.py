"""Provider capability metadata for the channel-management UI."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ChannelProviderCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversation_types: tuple[str, ...]
    supports_private_chat: bool = True
    supports_group_chat: bool = False
    supports_channel_chat: bool = False
    supports_mentions: bool = False
    supports_file_upload: bool = False
    supports_message_update: bool = False
    supports_interactive_card: bool = False
    supports_processing_message: bool = False


PROVIDER_CAPABILITIES: dict[str, ChannelProviderCapabilities] = {
    "telegram": ChannelProviderCapabilities(
        conversation_types=("private", "group", "supergroup", "channel"),
        supports_group_chat=True,
        supports_channel_chat=True,
        supports_mentions=True,
        supports_file_upload=True,
        supports_interactive_card=True,
    ),
    "feishu": ChannelProviderCapabilities(
        conversation_types=("private", "group"),
        supports_group_chat=True,
        supports_mentions=True,
        supports_file_upload=True,
        supports_message_update=True,
        supports_interactive_card=True,
        supports_processing_message=True,
    ),
    "dingtalk": ChannelProviderCapabilities(
        conversation_types=("private", "group"),
        supports_group_chat=True,
        supports_mentions=True,
        supports_file_upload=True,
        supports_interactive_card=True,
    ),
    "wecom": ChannelProviderCapabilities(
        conversation_types=("private",),
        supports_file_upload=True,
        supports_interactive_card=True,
    ),
    "mock": ChannelProviderCapabilities(
        conversation_types=("private", "group"),
        supports_group_chat=True,
        supports_mentions=True,
        supports_file_upload=True,
    ),
}


def get_provider_capabilities() -> dict[str, ChannelProviderCapabilities]:
    return PROVIDER_CAPABILITIES.copy()


def validate_provider_conversation_type(channel_type: str, conversation_type: str) -> bool:
    capabilities = PROVIDER_CAPABILITIES.get(channel_type)
    return capabilities is not None and conversation_type in capabilities.conversation_types
