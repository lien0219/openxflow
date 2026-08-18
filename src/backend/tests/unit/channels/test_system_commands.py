from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from langflow.channels.services.dispatch import ChannelDispatchService
from langflow.channels.services.system_commands import (
    RESERVED_COMMAND_NAMES,
    resolve_system_command,
    visible_system_commands,
)


def test_system_command_aliases_resolve_to_one_canonical_command() -> None:
    assert resolve_system_command("/start").command == "/help"
    assert resolve_system_command("/帮助").command == "/help"
    assert resolve_system_command("/指令").command == "/commands"
    assert resolve_system_command("/我的账号").command == "/whoami"
    assert resolve_system_command("/知识库").command == "/knowledge"
    assert resolve_system_command("/状态").command == "/status"
    assert resolve_system_command("/切换工作流").command == "/use-flow"
    assert resolve_system_command("/当前工作流").command == "/current-flow"
    assert resolve_system_command("/run") is None


def test_reserved_names_include_canonical_commands_and_localized_aliases() -> None:
    assert {
        "/help",
        "/帮助",
        "/flow",
        "/工作流",
        "/status",
        "/状态",
        "/use-flow",
        "/current-flow",
    } <= RESERVED_COMMAND_NAMES
    assert "/run" not in RESERVED_COMMAND_NAMES


def test_visible_commands_respect_group_context_and_permissions() -> None:
    public_group = visible_system_commands(
        is_bound=False,
        is_admin=False,
        conversation_type="group",
        shared_access=True,
    )
    public_names = {item.command for item in public_group}
    assert "/bind" not in public_names
    assert {
        "/commands",
        "/whoami",
        "/files",
        "/knowledge",
        "/use-flow",
        "/current-flow",
    } <= public_names
    assert {"/flow", "/use-kb", "/status"}.isdisjoint(public_names)

    admin_private = visible_system_commands(
        is_bound=True,
        is_admin=True,
        conversation_type="private",
        shared_access=True,
    )
    admin_names = {item.command for item in admin_private}
    assert {"/bind", "/flow", "/use-kb", "/status"} <= admin_names


def test_help_message_is_dynamic_for_member_and_admin() -> None:
    member = ChannelDispatchService._help_message(
        bound_user=None,
        is_admin=False,
        access_policy="shared",
        conversation_type="group",
    )
    assert "账号状态：未绑定" in member.text
    assert "/files" in member.text
    assert "/flow" not in member.text
    assert "/bind" not in member.text

    admin = ChannelDispatchService._help_message(
        bound_user=SimpleNamespace(username="admin"),
        is_admin=True,
        access_policy="hybrid",
        conversation_type="private",
    )
    assert "已绑定（admin）" in admin.text
    assert "/flow" in admin.text
    assert "/use-kb" in admin.text
    assert "/status" in admin.text


def test_whoami_does_not_expose_internal_identifiers() -> None:
    service = object.__new__(ChannelDispatchService)
    owner_id = uuid4()
    service.connection = SimpleNamespace(channel_type="feishu", user_id=owner_id)
    event = SimpleNamespace(
        conversation=SimpleNamespace(conversation_type="group"),
        user=SimpleNamespace(display_name="群成员", external_user_id="ou_secret_external_id"),
    )
    response = service._whoami_message(
        event,
        bound_user=None,
        access_policy="shared",
        is_admin=False,
    )
    assert "渠道共享服务身份" in response.text
    assert "ou_secret_external_id" not in response.text
    assert str(owner_id) not in response.text


@pytest.mark.asyncio
async def test_admin_system_command_returns_explicit_permission_error() -> None:
    service = object.__new__(ChannelDispatchService)
    service.connection = SimpleNamespace(user_id=uuid4(), channel_type="feishu")
    definition = resolve_system_command("/status")
    event = SimpleNamespace(conversation=SimpleNamespace(conversation_type="group"))

    response = await service._execute_system_command(
        definition,
        event=event,
        identity=None,
        bound_user=None,
        binding=None,
        argument="",
        access_policy="shared",
        personal_user_id=None,
    )

    assert response.text == "指令 /status 仅限渠道管理员使用。"


def test_command_parser_supports_bot_suffix_and_chinese_alias() -> None:
    assert ChannelDispatchService._parse_command("/帮助@openxflow_bot 说明") == ("/帮助", "说明")
