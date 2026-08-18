"""Provider-aware planning for long outbound channel messages."""

from __future__ import annotations

from langflow.channels.domain.models import ChannelMessage, ChannelMessageType
from langflow.channels.services.capabilities import get_provider_capability

_MIN_BOUNDARY_RATIO = 0.45
_BOUNDARY_MARKERS = ("\n\n", "\n", "。", "！", "？", ". ", "! ", "? ", "；", "; ", "，", ", ", " ")
_TITLE_SEPARATOR = "\n\n"


def _find_split_index(value: str, limit: int) -> int:
    if len(value) <= limit:
        return len(value)
    lower_bound = max(1, int(limit * _MIN_BOUNDARY_RATIO))
    window = value[: limit + 1]
    for marker in _BOUNDARY_MARKERS:
        index = window.rfind(marker, lower_bound, limit + 1)
        if index >= lower_bound:
            return index + len(marker)
    return limit


def split_channel_text(value: str, limit: int) -> list[str]:
    """Split Unicode text on semantic boundaries without producing oversized chunks."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    remaining = value.strip()
    if not remaining:
        return [""]

    chunks: list[str] = []
    while len(remaining) > limit:
        split_index = _find_split_index(remaining, limit)
        chunk = remaining[:split_index].rstrip()
        if not chunk:
            chunk = remaining[:limit]
            split_index = limit
        chunks.append(chunk)
        remaining = remaining[split_index:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _split_with_first_limit(value: str, first_limit: int, next_limit: int) -> list[str]:
    if first_limit <= 0 or next_limit <= 0:
        raise ValueError("message limits must be positive")
    if len(value) <= first_limit:
        return [value]
    first_index = _find_split_index(value, first_limit)
    first = value[:first_index].rstrip()
    if not first:
        first = value[:first_limit]
        first_index = first_limit
    remaining = value[first_index:].lstrip()
    return [first, *split_channel_text(remaining, next_limit)] if remaining else [first]


def _content_source(message: ChannelMessage) -> tuple[str, str]:
    if message.markdown:
        return "markdown", message.markdown
    if message.text:
        return "text", message.text
    if message.title:
        return "title", message.title
    return "text", ""


def plan_channel_messages(channel_type: str, message: ChannelMessage) -> list[ChannelMessage]:
    """Convert one logical response into one or more provider-safe messages."""
    capabilities = get_provider_capability(channel_type)
    if capabilities is None:
        return [message]

    source_field, source = _content_source(message)
    title = message.title if source_field != "title" else None
    maximum = capabilities.max_text_length

    if title and len(title) + len(_TITLE_SEPARATOR) >= maximum:
        source = f"{title}{_TITLE_SEPARATOR}{source}" if source else title
        title = None
        source_field = "markdown" if message.markdown else "text"

    rendered_length = len(source) + (len(title) + len(_TITLE_SEPARATOR) if title else 0)
    actions_fit = len(message.actions) <= capabilities.max_actions
    if rendered_length <= maximum and actions_fit:
        return [message]

    first_limit = maximum - (len(title) + len(_TITLE_SEPARATOR) if title else 0)
    chunks = _split_with_first_limit(source, max(1, first_limit), maximum)
    planned: list[ChannelMessage] = []
    total = len(chunks)
    for index, chunk in enumerate(chunks):
        update = {
            "title": title if index == 0 else None,
            "text": chunk if source_field in {"text", "title"} else None,
            "markdown": chunk if source_field == "markdown" else None,
            "actions": message.actions[: capabilities.max_actions] if index == total - 1 else [],
            "attachments": message.attachments if index == 0 else [],
            "metadata": {
                **message.metadata,
                "openxflow_chunk_index": index + 1,
                "openxflow_chunk_total": total,
            },
        }
        if total > 1 and message.message_type is ChannelMessageType.CARD:
            update["message_type"] = (
                ChannelMessageType.MARKDOWN if source_field == "markdown" else ChannelMessageType.TEXT
            )
        planned.append(message.model_copy(update=update))
    return planned
