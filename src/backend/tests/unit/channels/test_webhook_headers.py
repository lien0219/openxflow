import pytest

from langflow.channels.security.webhook_headers import durable_webhook_headers


def test_telegram_durable_headers_keep_only_secret_token() -> None:
    result = durable_webhook_headers(
        "telegram",
        {
            "X-Telegram-Bot-Api-Secret-Token": "secret",
            "Authorization": "Bearer sensitive",
            "Cookie": "session=sensitive",
            "Content-Type": "application/json",
        },
    )

    assert result == {"x-telegram-bot-api-secret-token": "secret"}


def test_feishu_durable_headers_are_empty() -> None:
    assert durable_webhook_headers(
        "feishu",
        {
            "authorization": "Bearer sensitive",
            "x-forwarded-for": "192.0.2.1",
        },
    ) == {}


def test_dingtalk_durable_headers_keep_supported_signature_variants() -> None:
    result = durable_webhook_headers(
        "dingtalk",
        {
            "Timestamp": "1000",
            "Sign": "legacy",
            "X-DingTalk-Timestamp": "2000",
            "X-DingTalk-Signature": "modern",
            "Cookie": "sensitive",
        },
    )

    assert result == {
        "timestamp": "1000",
        "sign": "legacy",
        "x-dingtalk-timestamp": "2000",
        "x-dingtalk-signature": "modern",
    }


def test_wecom_durable_headers_keep_synthesized_signature_values() -> None:
    result = durable_webhook_headers(
        "wecom",
        {
            "x-wecom-msg-signature": "signature",
            "x-wecom-timestamp": "timestamp",
            "x-wecom-nonce": "nonce",
            "authorization": "sensitive",
        },
    )

    assert result == {
        "x-wecom-msg-signature": "signature",
        "x-wecom-timestamp": "timestamp",
        "x-wecom-nonce": "nonce",
    }


def test_unknown_durable_webhook_channel_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported durable webhook channel type"):
        durable_webhook_headers("unknown", {"authorization": "sensitive"})
