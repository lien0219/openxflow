from inspect import getsource
from uuid import uuid4

from langflow.services.database.models.channel import crud
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConnectionCreate,
)


def test_connection_read_preserves_all_runtime_settings(monkeypatch):
    monkeypatch.setattr(crud, "list_credential_keys", lambda _value: ["bot_token"])
    connection = ChannelConnection(
        user_id=uuid4(),
        name="Feishu",
        channel_type="feishu",
        credentials_encrypted="ciphertext",
        auto_discover_conversations=False,
        pending_notice_enabled=False,
        personal_commands_enabled=False,
        user_flow_selection_enabled=True,
        flow_selection_ttl_hours=72,
        default_allow_file_upload=False,
        max_concurrency=7,
        daily_quota=99,
        settings_data={"system_command_require_mention": False},
    )

    result = crud._connection_read(connection)

    assert result.auto_discover_conversations is False
    assert result.pending_notice_enabled is False
    assert result.personal_commands_enabled is False
    assert result.user_flow_selection_enabled is True
    assert result.flow_selection_ttl_hours == 72
    assert result.default_allow_file_upload is False
    assert result.max_concurrency == 7
    assert result.daily_quota == 99
    assert result.settings_data == {"system_command_require_mention": False}
    assert result.configured_credential_keys == ["bot_token"]


def test_connection_create_uses_model_dump_for_all_settings():
    source = getsource(crud.create_channel_connection)
    payload = ChannelConnectionCreate(
        name="Feishu",
        channel_type="feishu",
        credentials={"app_id": "id", "app_secret": "secret", "verification_token": "token"},
        user_flow_selection_enabled=True,
        flow_selection_ttl_hours=48,
        pending_notice_enabled=False,
    )
    values = payload.model_dump(exclude={"credentials", "service_user_id"})

    assert "payload.model_dump" in source
    assert values["user_flow_selection_enabled"] is True
    assert values["flow_selection_ttl_hours"] == 48
    assert values["pending_notice_enabled"] is False
