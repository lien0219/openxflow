import math

import pytest

from langflow.channels.services.token_cache import (
    InvalidProviderTokenResponseError,
    provider_token_cache_key,
    provider_token_lifetime_seconds,
)


def test_provider_token_cache_key_fingerprints_secret() -> None:
    first = provider_token_cache_key(
        provider="Feishu",
        api_base_url="https://open.feishu.test/open-apis/",
        public_id=" cli-test ",
        secret="secret-one",
    )
    same = provider_token_cache_key(
        provider="feishu",
        api_base_url="https://open.feishu.test/open-apis",
        public_id="cli-test",
        secret="secret-one",
    )
    rotated = provider_token_cache_key(
        provider="feishu",
        api_base_url="https://open.feishu.test/open-apis",
        public_id="cli-test",
        secret="secret-two",
    )

    assert first == same
    assert first != rotated
    assert "secret-one" not in first
    assert "secret-two" not in rotated
    assert len(first.rsplit(":", 1)[-1]) == 64


def test_provider_token_lifetime_accepts_numeric_values() -> None:
    assert provider_token_lifetime_seconds({"expire": 7200}, "expire", provider="Feishu") == 7200
    assert provider_token_lifetime_seconds({"expire": "120"}, "expire", provider="Feishu") == 120
    assert provider_token_lifetime_seconds({"expire": 1}, "expire", provider="Feishu") == 60
    assert provider_token_lifetime_seconds({}, "expire", provider="Feishu") == 7200


@pytest.mark.parametrize(
    "value",
    [None, True, False, "invalid", "nan", "inf", "-inf", 0, -1, math.nan, math.inf],
)
def test_provider_token_lifetime_rejects_invalid_values(value) -> None:
    with pytest.raises(InvalidProviderTokenResponseError, match="Feishu"):
        provider_token_lifetime_seconds({"expire": value}, "expire", provider="Feishu")
