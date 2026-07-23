"""Provider-specific header minimization for durable webhook persistence."""

from __future__ import annotations

_DURABLE_HEADER_ALLOWLISTS: dict[str, frozenset[str]] = {
    "telegram": frozenset({"x-telegram-bot-api-secret-token"}),
    "feishu": frozenset(),
    "dingtalk": frozenset(
        {
            "timestamp",
            "sign",
            "x-dingtalk-timestamp",
            "x-dingtalk-signature",
        }
    ),
    "wecom": frozenset(
        {
            "x-wecom-msg-signature",
            "x-wecom-timestamp",
            "x-wecom-nonce",
        }
    ),
}


def durable_webhook_headers(channel_type: str, headers: dict[str, str]) -> dict[str, str]:
    """Return only headers required to re-verify a persisted provider callback."""
    try:
        allowed = _DURABLE_HEADER_ALLOWLISTS[channel_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported durable webhook channel type: {channel_type}") from exc
    return {
        normalized: value
        for key, value in headers.items()
        if (normalized := key.lower()) in allowed
    }
