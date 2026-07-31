"""Prevent channel command switches from being dropped during create or update."""

from inspect import getsource
from uuid import uuid4

from langflow.channels.services import commands
from langflow.services.database.models.channel.command_model import (
    ChannelWorkflowCommandCreate,
    ChannelWorkflowCommandUpdate,
)


def test_command_create_forwards_all_switch_settings():
    payload = ChannelWorkflowCommandCreate(
        command="/deepseek",
        aliases=["/ds"],
        flow_id=uuid4(),
        input_required=True,
        allow_attachments=False,
        allow_persistent_selection=True,
        require_mention=True,
        enabled=False,
        settings_data={"mode": "strict"},
    )
    values = payload.model_dump(
        exclude={"command", "aliases", "flow_id", "conversation_binding_id"}
    )
    source = getsource(commands.create_workflow_command)

    assert "payload.model_dump" in source
    assert values["input_required"] is True
    assert values["allow_attachments"] is False
    assert values["allow_persistent_selection"] is True
    assert values["require_mention"] is True
    assert values["enabled"] is False
    assert values["settings_data"] == {"mode": "strict"}


def test_command_update_preserves_explicit_boolean_values():
    enabled_changes = ChannelWorkflowCommandUpdate(
        allow_persistent_selection=True,
        allow_attachments=True,
        input_required=True,
        require_mention=True,
        enabled=True,
    ).model_dump(exclude_unset=True)
    disabled_changes = ChannelWorkflowCommandUpdate(
        allow_persistent_selection=False,
        allow_attachments=False,
        input_required=False,
        require_mention=False,
        enabled=False,
    ).model_dump(exclude_unset=True)

    assert enabled_changes == {
        "input_required": True,
        "allow_attachments": True,
        "allow_persistent_selection": True,
        "require_mention": True,
        "enabled": True,
    }
    assert disabled_changes == {
        "input_required": False,
        "allow_attachments": False,
        "allow_persistent_selection": False,
        "require_mention": False,
        "enabled": False,
    }
