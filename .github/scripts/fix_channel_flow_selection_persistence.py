from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CRUD = ROOT / "src/backend/base/langflow/services/database/models/channel/crud.py"
TEST = ROOT / "src/backend/tests/unit/channels/test_channel_connection_flow_selection_persistence.py"
WORKFLOW = ROOT / ".github/workflows/fix-channel-flow-selection-persistence.yml"
SCRIPT = Path(__file__).resolve()


def replace_once(content: str, old: str, new: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match, found {count}: {old!r}")
    return content.replace(old, new, 1)


content = CRUD.read_text(encoding="utf-8")
content = replace_once(
    content,
    """        pending_notice_enabled=connection.pending_notice_enabled,\n        personal_commands_enabled=connection.personal_commands_enabled,\n        default_response_mode=connection.default_response_mode,\n""",
    """        pending_notice_enabled=connection.pending_notice_enabled,\n        personal_commands_enabled=connection.personal_commands_enabled,\n        user_flow_selection_enabled=connection.user_flow_selection_enabled,\n        flow_selection_ttl_hours=connection.flow_selection_ttl_hours,\n        default_response_mode=connection.default_response_mode,\n""",
)
content = replace_once(
    content,
    """        pending_notice_enabled=payload.pending_notice_enabled,\n        personal_commands_enabled=payload.personal_commands_enabled,\n        default_response_mode=payload.default_response_mode,\n""",
    """        pending_notice_enabled=payload.pending_notice_enabled,\n        personal_commands_enabled=payload.personal_commands_enabled,\n        user_flow_selection_enabled=payload.user_flow_selection_enabled,\n        flow_selection_ttl_hours=payload.flow_selection_ttl_hours,\n        default_response_mode=payload.default_response_mode,\n""",
)
CRUD.write_text(content, encoding="utf-8")

TEST.write_text(
    '''from inspect import getsource\nfrom uuid import uuid4\n\nfrom langflow.services.database.models.channel import crud\nfrom langflow.services.database.models.channel.model import ChannelConnection\n\n\ndef test_connection_read_preserves_flow_selection_settings(monkeypatch):\n    monkeypatch.setattr(crud, "list_credential_keys", lambda _value: [])\n    connection = ChannelConnection(\n        user_id=uuid4(),\n        name="Feishu",\n        channel_type="feishu",\n        credentials_encrypted="ciphertext",\n        user_flow_selection_enabled=True,\n        flow_selection_ttl_hours=72,\n    )\n\n    result = crud._connection_read(connection)\n\n    assert result.user_flow_selection_enabled is True\n    assert result.flow_selection_ttl_hours == 72\n\n\ndef test_connection_create_forwards_flow_selection_settings():\n    source = getsource(crud.create_channel_connection)\n\n    assert "user_flow_selection_enabled=payload.user_flow_selection_enabled" in source\n    assert "flow_selection_ttl_hours=payload.flow_selection_ttl_hours" in source\n''',
    encoding="utf-8",
)

WORKFLOW.unlink(missing_ok=True)
SCRIPT.unlink(missing_ok=True)
