"""System command registry shared by all channel providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SystemCommandPermission = Literal["public", "bound_or_shared", "admin"]


@dataclass(frozen=True, slots=True)
class SystemCommandDefinition:
    command: str
    description: str
    aliases: tuple[str, ...] = ()
    permission: SystemCommandPermission = "public"
    private_only: bool = False
    show_in_help: bool = True

    @property
    def names(self) -> tuple[str, ...]:
        return (self.command, *self.aliases)


SYSTEM_COMMANDS: tuple[SystemCommandDefinition, ...] = (
    SystemCommandDefinition(
        command="/help",
        aliases=("/start", "/帮助"),
        description="查看使用帮助",
    ),
    SystemCommandDefinition(
        command="/commands",
        aliases=("/指令", "/命令"),
        description="查看当前可用指令",
    ),
    SystemCommandDefinition(
        command="/bind",
        aliases=("/绑定",),
        description="绑定或查看 OpenXFlow 账号",
        private_only=True,
    ),
    SystemCommandDefinition(
        command="/whoami",
        aliases=("/我的账号", "/身份"),
        description="查看当前渠道身份与执行模式",
    ),
    SystemCommandDefinition(
        command="/files",
        aliases=("/文件",),
        description="查看当前会话最近文件",
        permission="bound_or_shared",
    ),
    SystemCommandDefinition(
        command="/knowledge",
        aliases=("/知识库",),
        description="查看当前会话知识库",
        permission="bound_or_shared",
    ),
    SystemCommandDefinition(
        command="/flow",
        aliases=("/工作流",),
        description="临时运行指定工作流",
        permission="admin",
    ),
    SystemCommandDefinition(
        command="/use-kb",
        aliases=("/切换知识库",),
        description="切换当前会话知识库",
        permission="admin",
    ),
    SystemCommandDefinition(
        command="/status",
        aliases=("/状态",),
        description="查看渠道连接与当前会话状态",
        permission="admin",
    ),
)

_COMMAND_BY_NAME = {name.lower(): definition for definition in SYSTEM_COMMANDS for name in definition.names}
RESERVED_COMMAND_NAMES = frozenset(_COMMAND_BY_NAME)


def resolve_system_command(value: str | None) -> SystemCommandDefinition | None:
    if not value:
        return None
    return _COMMAND_BY_NAME.get(value.strip().lower())


def can_use_system_command(
    definition: SystemCommandDefinition,
    *,
    is_bound: bool,
    is_admin: bool,
    shared_access: bool,
) -> bool:
    if definition.permission == "admin":
        return is_admin
    if definition.permission == "bound_or_shared":
        return is_bound or is_admin or shared_access
    return True


def visible_system_commands(
    *,
    is_bound: bool,
    is_admin: bool,
    conversation_type: str,
    shared_access: bool,
) -> tuple[SystemCommandDefinition, ...]:
    visible: list[SystemCommandDefinition] = []
    for definition in SYSTEM_COMMANDS:
        if not definition.show_in_help:
            continue
        if definition.command == "/help":
            continue
        if definition.private_only and conversation_type != "private":
            continue
        if can_use_system_command(
            definition,
            is_bound=is_bound,
            is_admin=is_admin,
            shared_access=shared_access,
        ):
            visible.append(definition)
    return tuple(visible)
