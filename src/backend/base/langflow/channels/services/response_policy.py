"""Provider-neutral channel response mode policy."""

from __future__ import annotations

from enum import Enum

from langflow.channels.domain.models import ChannelEvent, ChannelEventType


class ChannelResponseMode(str, Enum):
    MENTION_ONLY = "mention_only"
    ALL_MESSAGES = "all_messages"
    COMMANDS_ONLY = "commands_only"
    DISABLED = "disabled"


_LEGACY_ALIASES = {
    "mentions_only": ChannelResponseMode.MENTION_ONLY.value,
    "mention": ChannelResponseMode.MENTION_ONLY.value,
}


def normalize_response_mode(value: str | None) -> str:
    normalized = (value or ChannelResponseMode.MENTION_ONLY.value).strip().lower()
    normalized = _LEGACY_ALIASES.get(normalized, normalized)
    allowed = {mode.value for mode in ChannelResponseMode}
    return normalized if normalized in allowed else ChannelResponseMode.MENTION_ONLY.value


def should_process_channel_event(
    event: ChannelEvent,
    *,
    command: str | None,
    response_mode: str | None,
) -> bool:
    """Apply group response policy consistently to text, files and actions."""
    if event.conversation.conversation_type == "private":
        return True

    mode = normalize_response_mode(response_mode)
    if mode == ChannelResponseMode.DISABLED.value:
        return False
    if event.event_type == ChannelEventType.ACTION:
        return True
    if command is not None:
        return True
    if mode == ChannelResponseMode.ALL_MESSAGES.value:
        return True
    if mode == ChannelResponseMode.COMMANDS_ONLY.value:
        return False
    return bool(event.message.mentions)
