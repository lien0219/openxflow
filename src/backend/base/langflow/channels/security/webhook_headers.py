"""Internal durable webhook replay markers."""

from __future__ import annotations

_SUPPORTED_DURABLE_CHANNELS = frozenset({"telegram", "feishu", "dingtalk", "wecom"})
_PREVERIFIED_HEADERS = {"x-openxflow-preverified": "1"}


def durable_webhook_headers(channel_type: str, headers: dict[str, str]) -> dict[str, str]:
    """Return a non-sensitive internal marker for an already-verified callback."""
    del headers
    if channel_type not in _SUPPORTED_DURABLE_CHANNELS:
        raise ValueError(f"Unsupported durable webhook channel type: {channel_type}")
    return dict(_PREVERIFIED_HEADERS)
