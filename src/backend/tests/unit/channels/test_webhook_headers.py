import pytest

from langflow.channels.security.webhook_headers import durable_webhook_headers


@pytest.mark.parametrize("channel_type", ["telegram", "feishu", "dingtalk", "wecom"])
def test_durable_headers_only_store_internal_preverified_marker(channel_type: str) -> None:
    result = durable_webhook_headers(
        channel_type,
        {
            "X-Telegram-Bot-Api-Secret-Token": "telegram-secret",
            "Timestamp": "1000",
            "Sign": "dingtalk-signature",
            "X-WeCom-Msg-Signature": "wecom-signature",
            "X-WeCom-Timestamp": "2000",
            "X-WeCom-Nonce": "nonce",
            "Authorization": "Bearer sensitive",
            "Cookie": "session=sensitive",
            "X-Forwarded-For": "192.0.2.1",
        },
    )

    assert result == {"x-openxflow-preverified": "1"}
    rendered = repr(result)
    assert "telegram-secret" not in rendered
    assert "dingtalk-signature" not in rendered
    assert "wecom-signature" not in rendered
    assert "Bearer sensitive" not in rendered
    assert "session=sensitive" not in rendered


def test_unknown_durable_webhook_channel_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported durable webhook channel type"):
        durable_webhook_headers("unknown", {"authorization": "sensitive"})
