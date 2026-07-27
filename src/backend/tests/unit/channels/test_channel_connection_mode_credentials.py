from types import SimpleNamespace

import pytest
from langflow.channels.security.provider_credentials import ChannelProviderCredentialError
from langflow.services.database.models.channel import crud
from langflow.services.database.models.channel.model import ChannelConnectionUpdate


def test_mode_change_requires_complete_replacement_credentials() -> None:
    connection = SimpleNamespace(connection_mode="webhook", credentials_encrypted="encrypted")
    payload = ChannelConnectionUpdate(connection_mode="ai_bot")

    with pytest.raises(ChannelProviderCredentialError, match="required when changing"):
        crud._next_connection_credentials(connection, payload)


def test_mode_change_drops_credentials_from_previous_mode() -> None:
    connection = SimpleNamespace(connection_mode="webhook", credentials_encrypted="encrypted")
    payload = ChannelConnectionUpdate(
        connection_mode="ai_bot",
        credentials={
            "token": "ai-token",
            "encoding_aes_key": "A" * 43,
        },
    )

    credentials, mode, should_store = crud._next_connection_credentials(connection, payload)

    assert credentials == {
        "token": "ai-token",
        "encoding_aes_key": "A" * 43,
    }
    assert mode == "ai_bot"
    assert should_store is True


def test_same_mode_patch_merges_with_existing_credentials(monkeypatch) -> None:
    connection = SimpleNamespace(connection_mode="webhook", credentials_encrypted="encrypted")
    monkeypatch.setattr(
        crud,
        "decrypt_credentials",
        lambda _value: {"corp_id": "ww-test", "corp_secret": "old-secret"},
    )
    payload = ChannelConnectionUpdate(credentials={"corp_secret": "new-secret"})

    credentials, mode, should_store = crud._next_connection_credentials(connection, payload)

    assert credentials == {"corp_id": "ww-test", "corp_secret": "new-secret"}
    assert mode == "webhook"
    assert should_store is True
