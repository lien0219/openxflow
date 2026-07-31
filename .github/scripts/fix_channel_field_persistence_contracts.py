from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CRUD = ROOT / "src/backend/base/langflow/services/database/models/channel/crud.py"
COMMANDS = ROOT / "src/backend/base/langflow/channels/services/commands.py"
CONNECTION_TEST = ROOT / "src/backend/tests/unit/channels/test_channel_connection_flow_selection_persistence.py"
COMMAND_TEST = ROOT / "src/backend/tests/unit/channels/test_channel_command_field_persistence.py"
WORKFLOW = ROOT / ".github/workflows/fix-channel-field-persistence-contracts.yml"
SCRIPT = Path(__file__).resolve()


def replace_between(content: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = content.index(start_marker)
    end = content.index(end_marker, start)
    return content[:start] + replacement + content[end:]


crud = CRUD.read_text(encoding="utf-8")
crud = replace_between(
    crud,
    "def _connection_read(connection: ChannelConnection) -> ChannelConnectionRead:\n",
    "\n\ndef _derive_conversation_status(",
    """def _connection_read(connection: ChannelConnection) -> ChannelConnectionRead:\n    result = ChannelConnectionRead.model_validate(connection, from_attributes=True)\n    return result.model_copy(\n        update={\n            "configured_credential_keys": list_credential_keys(connection.credentials_encrypted),\n        }\n    )\n""",
)
create_start = "    connection = ChannelConnection(\n"
create_end = "    session.add(connection)\n"
create_replacement = """    connection_values = payload.model_dump(exclude={"credentials", "service_user_id"})\n    connection = ChannelConnection(\n        user_id=user_id,\n        service_user_id=None,\n        credentials_encrypted=encrypt_credentials(payload.credentials),\n        **connection_values,\n    )\n"""
create_function_start = crud.index("async def create_channel_connection(")
start = crud.index(create_start, create_function_start)
end = crud.index(create_end, start)
crud = crud[:start] + create_replacement + crud[end:]
CRUD.write_text(crud, encoding="utf-8")

commands = COMMANDS.read_text(encoding="utf-8")
function_start = commands.index("async def create_workflow_command(")
start = commands.index("    command = ChannelWorkflowCommand(\n", function_start)
end = commands.index("    session.add(command)\n", start)
replacement = """    command_values = payload.model_dump(\n        exclude={"command", "aliases", "flow_id", "conversation_binding_id"}\n    )\n    command = ChannelWorkflowCommand(\n        connection_id=connection.id,\n        conversation_binding_id=payload.conversation_binding_id,\n        owner_user_id=owner_user_id,\n        created_by=user.id,\n        flow_id=payload.flow_id,\n        command=normalized_command,\n        normalized_command=normalized_command,\n        aliases=aliases,\n        scope_key=scope_key,\n        **command_values,\n    )\n"""
commands = commands[:start] + replacement + commands[end:]
COMMANDS.write_text(commands, encoding="utf-8")

CONNECTION_TEST.write_text(
    """from inspect import getsource\nfrom uuid import uuid4\n\nfrom langflow.services.database.models.channel import crud\nfrom langflow.services.database.models.channel.model import (\n    ChannelConnection,\n    ChannelConnectionCreate,\n)\n\n\ndef test_connection_read_preserves_all_runtime_settings(monkeypatch):\n    monkeypatch.setattr(crud, "list_credential_keys", lambda _value: ["bot_token"])\n    connection = ChannelConnection(\n        user_id=uuid4(),\n        name="Feishu",\n        channel_type="feishu",\n        credentials_encrypted="ciphertext",\n        auto_discover_conversations=False,\n        pending_notice_enabled=False,\n        personal_commands_enabled=False,\n        user_flow_selection_enabled=True,\n        flow_selection_ttl_hours=72,\n        default_allow_file_upload=False,\n        max_concurrency=7,\n        daily_quota=99,\n        settings_data={"system_command_require_mention": False},\n    )\n\n    result = crud._connection_read(connection)\n\n    assert result.auto_discover_conversations is False\n    assert result.pending_notice_enabled is False\n    assert result.personal_commands_enabled is False\n    assert result.user_flow_selection_enabled is True\n    assert result.flow_selection_ttl_hours == 72\n    assert result.default_allow_file_upload is False\n    assert result.max_concurrency == 7\n    assert result.daily_quota == 99\n    assert result.settings_data == {"system_command_require_mention": False}\n    assert result.configured_credential_keys == ["bot_token"]\n\n\ndef test_connection_create_uses_model_dump_for_all_settings():\n    source = getsource(crud.create_channel_connection)\n    payload = ChannelConnectionCreate(\n        name="Feishu",\n        channel_type="feishu",\n        credentials={"app_id": "id", "app_secret": "secret", "verification_token": "token"},\n        user_flow_selection_enabled=True,\n        flow_selection_ttl_hours=48,\n        pending_notice_enabled=False,\n    )\n    values = payload.model_dump(exclude={"credentials", "service_user_id"})\n\n    assert "payload.model_dump" in source\n    assert values["user_flow_selection_enabled"] is True\n    assert values["flow_selection_ttl_hours"] == 48\n    assert values["pending_notice_enabled"] is False\n""",
    encoding="utf-8",
)

COMMAND_TEST.write_text(
    """from inspect import getsource\nfrom uuid import uuid4\n\nfrom langflow.channels.services import commands\nfrom langflow.services.database.models.channel.command_model import (\n    ChannelWorkflowCommandCreate,\n    ChannelWorkflowCommandUpdate,\n)\n\n\ndef test_command_create_forwards_all_switch_settings():\n    payload = ChannelWorkflowCommandCreate(\n        command="/deepseek",\n        aliases=["/ds"],\n        flow_id=uuid4(),\n        input_required=True,\n        allow_attachments=False,\n        allow_persistent_selection=True,\n        require_mention=True,\n        enabled=False,\n        settings_data={"mode": "strict"},\n    )\n    values = payload.model_dump(\n        exclude={"command", "aliases", "flow_id", "conversation_binding_id"}\n    )\n    source = getsource(commands.create_workflow_command)\n\n    assert "payload.model_dump" in source\n    assert values["input_required"] is True\n    assert values["allow_attachments"] is False\n    assert values["allow_persistent_selection"] is True\n    assert values["require_mention"] is True\n    assert values["enabled"] is False\n    assert values["settings_data"] == {"mode": "strict"}\n\n\ndef test_command_update_preserves_explicit_boolean_values():\n    enabled_changes = ChannelWorkflowCommandUpdate(\n        allow_persistent_selection=True,\n        allow_attachments=True,\n        input_required=True,\n        require_mention=True,\n        enabled=True,\n    ).model_dump(exclude_unset=True)\n    disabled_changes = ChannelWorkflowCommandUpdate(\n        allow_persistent_selection=False,\n        allow_attachments=False,\n        input_required=False,\n        require_mention=False,\n        enabled=False,\n    ).model_dump(exclude_unset=True)\n\n    assert enabled_changes == {\n        "input_required": True,\n        "allow_attachments": True,\n        "allow_persistent_selection": True,\n        "require_mention": True,\n        "enabled": True,\n    }\n    assert disabled_changes == {\n        "input_required": False,\n        "allow_attachments": False,\n        "allow_persistent_selection": False,\n        "require_mention": False,\n        "enabled": False,\n    }\n""",
    encoding="utf-8",
)

WORKFLOW.unlink(missing_ok=True)
SCRIPT.unlink(missing_ok=True)
