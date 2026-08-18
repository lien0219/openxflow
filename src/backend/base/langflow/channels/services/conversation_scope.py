"""Provider-neutral conversation thread and topic scope helpers."""

from __future__ import annotations

from langflow.channels.domain.models import ChannelEvent

_SCOPE_METADATA_KEYS = (
    "conversation_scope_id",
    "thread_id",
    "message_thread_id",
    "topic_id",
    "message_thread_topic_id",
)


def conversation_scope_id(event: ChannelEvent) -> str:
    """Return a stable thread/topic identifier without knowing the provider."""
    conversation_metadata = getattr(event.conversation, "metadata", {}) or {}
    message = getattr(event, "message", None)
    message_metadata = getattr(message, "metadata", {}) or {}
    for key in _SCOPE_METADATA_KEYS:
        value = conversation_metadata.get(key)
        if value is None:
            value = message_metadata.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""
