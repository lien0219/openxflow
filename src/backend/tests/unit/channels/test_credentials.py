import json

import pytest
from langflow.channels.security.credentials import (
    ChannelCredentialError,
    decrypt_credentials,
    encrypt_credentials,
    list_credential_keys,
)


def test_channel_credentials_are_encrypted(monkeypatch):
    monkeypatch.setattr(
        "langflow.channels.security.credentials.auth_utils.encrypt_api_key",
        lambda value: f"encrypted:{value}",
    )
    monkeypatch.setattr(
        "langflow.channels.security.credentials.auth_utils.decrypt_api_key",
        lambda value: value.removeprefix("encrypted:"),
    )

    encrypted = encrypt_credentials({"token": "abc", "secret": "xyz"})

    assert encrypted.startswith("encrypted:")
    assert decrypt_credentials(encrypted) == {"secret": "xyz", "token": "abc"}
    assert list_credential_keys(encrypted) == ["secret", "token"]


def test_invalid_stored_credentials_raise(monkeypatch):
    monkeypatch.setattr(
        "langflow.channels.security.credentials.auth_utils.decrypt_api_key",
        lambda value: json.dumps([value]),
    )

    with pytest.raises(ChannelCredentialError):
        decrypt_credentials("bad")


def test_non_string_credential_is_rejected():
    with pytest.raises(ChannelCredentialError):
        encrypt_credentials({"token": 123})  # type: ignore[dict-item]
