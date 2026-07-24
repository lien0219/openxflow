"""Internal durable webhook replay markers."""

from __future__ import annotations

_SUPPORTED_DURABLE_CHANNELS = frozenset({"telegram", "feishu", "dingtalk", "wecom"})
_PREVERIFIED_HEADER = "x-openxflow-preverified"
_CONTENT_TYPE_HEADER = "content-type"


def durable_webhook_headers(channel_type: str, headers: dict[str, str]) -> dict[str, str]:
    """Return only a non-sensitive replay marker and optional content type."""
    if channel_type not in _SUPPORTED_DURABLE_CHANNELS:
        raise ValueError(f"Unsupported durable webhook channel type: {channel_type}")
    result = {_PREVERIFIED_HEADER: "1"}
    content_type = next((value for key, value in headers.items() if key.lower() == _CONTENT_TYPE_HEADER), None)
    if content_type is not None:
        result[_CONTENT_TYPE_HEADER] = content_type
    return result
