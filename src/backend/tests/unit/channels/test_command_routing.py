from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from langflow.channels.services.capabilities import (
    get_channel_provider_capabilities,
    validate_provider_conversation_type,
)
from langflow.channels.services.commands import (
    build_scope_key,
    normalize_aliases,
    normalize_command,
    render_command_input,
)
from langflow.services.database.models.channel.command_model import (
    ChannelCommandScope,
    ChannelWorkflowCommand,
)


def test_normalize_command_supports_chinese_and_adds_prefix() -> None:
    assert normalize_command("代码审查") == "/代码审查"
    assert normalize_command("/Review_Code") == "/review_code"


def test_normalize_command_rejects_reserved_and_invalid_commands() -> None:
    with pytest.raises(HTTPException) as reserved_error:
        normalize_command("/help")
    assert reserved_error.value.status_code == 409

    with pytest.raises(HTTPException) as invalid_error:
        normalize_command("/bad command")
    assert invalid_error.value.status_code == 422


def test_normalize_aliases_deduplicates_and_limits_values() -> None:
    aliases = normalize_aliases(
        ["/one", "/ONE", "/two", "/three", "/four", "/five", "/six"]
    )
    assert aliases == ["/one", "/two", "/three", "/four", "/five"]


def test_build_scope_key_requires_scope_references() -> None:
    conversation_id = uuid4()
    user_id = uuid4()

    assert (
        build_scope_key(
            ChannelCommandScope.CONNECTION_SHARED.value,
            conversation_binding_id=None,
            owner_user_id=None,
        )
        == "connection"
    )
    assert (
        build_scope_key(
            ChannelCommandScope.CONVERSATION_SHARED.value,
            conversation_binding_id=conversation_id,
            owner_user_id=None,
        )
        == f"conversation:{conversation_id}"
    )
    assert (
        build_scope_key(
            ChannelCommandScope.IDENTITY_CONVERSATION.value,
            conversation_binding_id=conversation_id,
            owner_user_id=user_id,
        )
        == f"identity-conversation:{user_id}:{conversation_id}"
    )

    with pytest.raises(HTTPException):
        build_scope_key(
            ChannelCommandScope.CONVERSATION_SHARED.value,
            conversation_binding_id=None,
            owner_user_id=None,
        )


def test_render_command_input_replaces_supported_variables() -> None:
    command = ChannelWorkflowCommand(
        connection_id=uuid4(),
        created_by=uuid4(),
        flow_id=uuid4(),
        command="/review",
        normalized_command="/review",
        scope_type=ChannelCommandScope.CONNECTION_SHARED.value,
        scope_key="connection",
        prompt_template=(
            "Input={{input}}; sender={{sender_name}}; "
            "conversation={{conversation_name}}; type={{conversation_type}}"
        ),
    )

    rendered = render_command_input(
        command,
        input_value="hello",
        sender_name="Liam",
        conversation_name="Research",
        conversation_type="group",
    )

    assert rendered == "Input=hello; sender=Liam; conversation=Research; type=group"


def test_provider_capabilities_expose_provider_specific_conversation_types() -> None:
    capabilities = get_channel_provider_capabilities()

    assert capabilities["telegram"].conversation_types == [
        "private",
        "group",
        "supergroup",
        "channel",
    ]
    assert capabilities["feishu"].conversation_types == ["private", "group"]
    assert capabilities["dingtalk"].conversation_types == ["private", "group"]
    assert capabilities["wecom"].conversation_types == ["private"]


def test_provider_conversation_type_validation_rejects_unsupported_type() -> None:
    assert validate_provider_conversation_type("feishu", "group") == "group"
    with pytest.raises(ValueError):
        validate_provider_conversation_type("wecom", "group")
