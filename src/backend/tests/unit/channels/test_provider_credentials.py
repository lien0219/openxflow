from __future__ import annotations

import pytest
from langflow.channels.security.provider_credentials import (
    ChannelProviderCredentialError,
    validate_channel_provider_credentials,
)


def test_telegram_requires_a_strong_provider_compatible_webhook_secret() -> None:
    with pytest.raises(ChannelProviderCredentialError, match="webhook_secret"):
        validate_channel_provider_credentials(
            "telegram",
            "webhook",
            {"bot_token": "123:abc", "webhook_secret": "short"},
        )

    validate_channel_provider_credentials(
        "telegram",
        "webhook",
        {"bot_token": "123:abc", "webhook_secret": "secure_token-1234"},
    )


def test_feishu_requires_verification_token_even_with_encrypt_key() -> None:
    with pytest.raises(ChannelProviderCredentialError, match="verification_token"):
        validate_channel_provider_credentials(
            "feishu",
            "webhook",
            {"app_id": "cli_test", "app_secret": "secret", "encrypt_key": "encrypt"},
        )


def test_dingtalk_allows_stream_and_signed_webhook_modes() -> None:
    credentials = {"client_id": "ding-test", "client_secret": "secret"}
    validate_channel_provider_credentials("dingtalk", "stream", credentials)
    validate_channel_provider_credentials("dingtalk", "webhook", credentials)

    with pytest.raises(ChannelProviderCredentialError, match="Unsupported"):
        validate_channel_provider_credentials("dingtalk", "polling", credentials)


def test_wecom_requires_positive_agent_and_valid_encoding_key() -> None:
    credentials = {
        "corp_id": "ww-test",
        "corp_secret": "secret",
        "agent_id": "1000002",
        "callback_token": "callback-token",
        "encoding_aes_key": "A" * 43,
    }
    validate_channel_provider_credentials("wecom", "webhook", credentials)

    with pytest.raises(ChannelProviderCredentialError, match="positive integer"):
        validate_channel_provider_credentials(
            "wecom",
            "webhook",
            {**credentials, "agent_id": "0"},
        )


def test_mock_provider_remains_available_for_isolated_tests() -> None:
    validate_channel_provider_credentials("mock", "test", {})
