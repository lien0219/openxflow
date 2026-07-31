from inspect import getsource
from uuid import uuid4

from langflow.services.database.models.channel import crud
from langflow.services.database.models.channel.model import ChannelConnection


def test_connection_read_preserves_flow_selection_settings(monkeypatch):
    monkeypatch.setattr(crud, "list_credential_keys", lambda _value: [])
    connection = ChannelConnection(
        user_id=uuid4(),
        name="Feishu",
        channel_type="feishu",
        credentials_encrypted="ciphertext",
        user_flow_selection_enabled=True,
        flow_selection_ttl_hours=72,
    )

    result = crud._connection_read(connection)

    assert result.user_flow_selection_enabled is True
    assert result.flow_selection_ttl_hours == 72


def test_connection_create_forwards_flow_selection_settings():
    source = getsource(crud.create_channel_connection)

    assert "user_flow_selection_enabled=payload.user_flow_selection_enabled" in source
    assert "flow_selection_ttl_hours=payload.flow_selection_ttl_hours" in source
