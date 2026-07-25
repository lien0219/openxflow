"""Provider credential validation for production channel connections."""

from __future__ import annotations

import re
from collections.abc import Mapping

_TELEGRAM_WEBHOOK_SECRET = re.compile(r"^[A-Za-z0-9_-]{16,256}$")
_WECOM_ENCODING_AES_KEY = re.compile(r"^[A-Za-z0-9+/]{43}$")


class ChannelProviderCredentialError(ValueError):
    """Raised when a channel connection cannot authenticate provider traffic safely."""


def _required(credentials: Mapping[str, str], key: str, *, provider: str) -> str:
    value = credentials.get(key, "")
    if not isinstance(value, str) or not value.strip():
        raise ChannelProviderCredentialError(f"{provider} credential '{key}' is required")
    return value.strip()


def validate_channel_provider_credentials(
    channel_type: str,
    connection_mode: str,
    credentials: Mapping[str, str],
) -> None:
    """Reject incomplete or unsafe provider authentication configuration."""
    normalized_channel = channel_type.strip().lower()
    normalized_mode = connection_mode.strip().lower()

    if normalized_channel == "mock":
        return

    allowed_modes = {"stream", "webhook"} if normalized_channel == "dingtalk" else {"webhook"}
    if normalized_mode not in allowed_modes:
        allowed = ", ".join(sorted(allowed_modes))
        raise ChannelProviderCredentialError(
            f"Unsupported {normalized_channel} connection mode '{connection_mode}'; expected {allowed}"
        )

    if normalized_channel == "telegram":
        _required(credentials, "bot_token", provider="Telegram")
        webhook_secret = _required(credentials, "webhook_secret", provider="Telegram")
        if not _TELEGRAM_WEBHOOK_SECRET.fullmatch(webhook_secret):
            raise ChannelProviderCredentialError(
                "Telegram credential 'webhook_secret' must be 16-256 characters using letters, digits, '_' or '-'"
            )
        return

    if normalized_channel == "feishu":
        _required(credentials, "app_id", provider="Feishu")
        _required(credentials, "app_secret", provider="Feishu")
        _required(credentials, "verification_token", provider="Feishu")
        return

    if normalized_channel == "dingtalk":
        _required(credentials, "client_id", provider="DingTalk")
        _required(credentials, "client_secret", provider="DingTalk")
        return

    if normalized_channel == "wecom":
        _required(credentials, "corp_id", provider="WeCom")
        _required(credentials, "corp_secret", provider="WeCom")
        agent_id = _required(credentials, "agent_id", provider="WeCom")
        if not agent_id.isdigit() or int(agent_id) <= 0:
            raise ChannelProviderCredentialError("WeCom credential 'agent_id' must be a positive integer")
        _required(credentials, "callback_token", provider="WeCom")
        encoding_key = _required(credentials, "encoding_aes_key", provider="WeCom")
        if not _WECOM_ENCODING_AES_KEY.fullmatch(encoding_key):
            raise ChannelProviderCredentialError(
                "WeCom credential 'encoding_aes_key' must be a 43-character EncodingAESKey"
            )
        return

    raise ChannelProviderCredentialError(f"Unsupported channel provider '{channel_type}'")
