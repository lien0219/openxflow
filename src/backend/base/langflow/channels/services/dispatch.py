"""Resolve identities and dispatch normalized channel events to OpenXFlow features."""

from __future__ import annotations

import asyncio
import inspect
import time
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import HTTPException
from lfx.log.logger import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.domain.models import (
    ChannelAction,
    ChannelEvent,
    ChannelMessage,
    ChannelMessageType,
)
from langflow.channels.services.access_control import (
    ChannelBindingRequiredError,
    ChannelExecutionPrincipal,
    ChannelServiceIdentityUnavailableError,
    bound_identity_user,
    effective_access_policy,
    effective_context_mode,
    resolve_execution_principal,
)
from langflow.channels.services.binding import discover_channel_identity, issue_channel_binding_code
from langflow.channels.services.capabilities import get_provider_capability
from langflow.channels.services.commands import (
    list_available_workflow_commands,
    mark_workflow_command_used,
    render_command_input,
    resolve_workflow_command,
)
from langflow.channels.services.context import prepare_channel_input, record_channel_response
from langflow.channels.services.conversation_scope import conversation_scope_id
from langflow.channels.services.execution_logs import (
    finalize_channel_execution,
    safe_record_channel_delivery_outcome,
    start_channel_execution,
)
from langflow.channels.services.files import (
    ChannelFileService,
    resolve_owned_knowledge_base,
)
from langflow.channels.services.flow_selection import (
    ActiveWorkflowResolution,
    FlowSelectionCommandUnavailableError,
    FlowSelectionDisabledError,
    FlowSelectionNotAllowedError,
    clear_active_workflow_selection,
    resolve_active_workflow_selection,
    set_active_workflow_selection,
)
from langflow.channels.services.message_records import safe_record_outbound_message
from langflow.channels.services.outbound_delivery import send_outbound_processing_once
from langflow.channels.services.response_policy import normalize_response_mode, should_process_channel_event
from langflow.channels.services.retry import retry_channel_operation
from langflow.channels.services.system_commands import (
    SystemCommandDefinition,
    can_use_system_command,
    resolve_system_command,
    visible_system_commands,
)
from langflow.channels.services.workflow import ChannelWorkflowExecutor, build_channel_session_id
from langflow.services.authorization import KnowledgeBaseAction, ensure_knowledge_base_permission

if TYPE_CHECKING:
    from langflow.services.database.models.channel.command_model import ChannelWorkflowCommand

from langflow.services.database.models.channel.crud import discover_channel_conversation
from langflow.services.database.models.channel.execution_model import ChannelExecutionStatus, ChannelExecutionTrigger
from langflow.services.database.models.channel.message_model import ChannelMessageRecordStatus
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConversationBinding,
    ChannelConversationRouteMode,
    ChannelConversationStatus,
    ChannelUnconfiguredBehavior,
)
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.knowledge_base.model import KnowledgeBaseRecord
from langflow.services.database.models.user.model import User


class ChannelDispatchService:
    """Application-level handler shared by provider webhook transports."""

    def __init__(
        self,
        session: AsyncSession,
        connection: ChannelConnection,
        adapter: ChannelAdapter,
        *,
        workflow_executor: ChannelWorkflowExecutor | None = None,
    ) -> None:
        self.session = session
        self.connection = connection
        self.adapter = adapter
        self.workflow_executor = workflow_executor or ChannelWorkflowExecutor()
        self.file_service = ChannelFileService(session, connection, adapter)

    async def handle(self, event: ChannelEvent) -> ChannelMessage | None:
        raw_command, argument = self._parse_command(event.message.text)
        system_command = resolve_system_command(raw_command)
        command = system_command.command if system_command is not None else raw_command
        binding = await discover_channel_conversation(self.session, self.connection, event)
        if binding is None:
            binding = await self._get_conversation_binding(event)
        identity = await discover_channel_identity(self.session, event)
        bound_user = await bound_identity_user(self.session, identity)
        if bound_user is not None:
            event.user.openxflow_user_id = bound_user.id

        access_policy = effective_access_policy(self.connection, binding)
        personal_user_id = bound_user.id if bound_user is not None and access_policy != "shared" else None

        if binding is not None and binding.status in {
            ChannelConversationStatus.IGNORED.value,
            ChannelConversationStatus.DISABLED.value,
            ChannelConversationStatus.UNAVAILABLE.value,
        }:
            return None
        response_mode = binding.response_mode if binding is not None else self.connection.default_response_mode
        require_system_command_mention = bool(self.connection.settings_data.get("system_command_require_mention", True))
        if self._should_ignore_group_event(
            event,
            command=command,
            response_mode=response_mode,
            binding=binding,
            require_command_mention=system_command is not None and require_system_command_mention,
            command_targeted=self._command_targets_bot(event),
        ):
            return None

        if system_command is not None:
            return await self._execute_system_command(
                system_command,
                event=event,
                identity=identity,
                bound_user=bound_user,
                binding=binding,
                argument=argument,
                access_policy=access_policy,
                personal_user_id=personal_user_id,
            )

        if command is not None:
            custom_response = await self._execute_custom_command(
                event,
                identity,
                bound_user,
                binding,
                command,
                argument,
            )
            if custom_response is not None:
                return custom_response
            return await self._unknown_command_message(
                personal_user_id,
                binding,
                command,
                bound_user=bound_user,
                access_policy=access_policy,
                conversation_type=event.conversation.conversation_type,
            )

        if event.message.attachments:
            try:
                principal = await resolve_execution_principal(
                    self.session,
                    self.connection,
                    binding,
                    identity,
                )
            except ChannelBindingRequiredError:
                return await self._binding_required_message(event)
            except ChannelServiceIdentityUnavailableError:
                return ChannelMessage(text="当前渠道共享执行身份尚未配置或已停用，请联系管理员。")
            binding = binding or await self._ensure_conversation_binding(event)
            if not binding.allow_file_upload:
                return ChannelMessage(text="当前会话已关闭文件上传，请在 OpenXFlow 渠道中心重新启用。")
            responses: list[str] = []
            title: str | None = None
            for attachment in event.message.attachments:
                response = await self.file_service.handle_attachment(
                    event=event,
                    user=principal.user,
                    binding=binding,
                    attachment=attachment,
                )
                title = title or response.title
                response_text = response.markdown or response.text
                if response_text:
                    responses.append(response_text)
            return ChannelMessage(title=title or "文件处理结果", text="\n\n".join(responses))

        text = (event.message.text or "").strip()
        if not text:
            return None

        selection_resolution = ActiveWorkflowResolution()
        if binding is not None:
            selection_resolution = await resolve_active_workflow_selection(
                self.session,
                connection=self.connection,
                binding=binding,
                identity=identity,
                conversation_scope_id=conversation_scope_id(event),
                user_id=personal_user_id,
            )
        if selection_resolution.command is not None and selection_resolution.selection is not None:
            selected_command = selection_resolution.command
            try:
                principal = await resolve_execution_principal(
                    self.session,
                    self.connection,
                    binding,
                    identity,
                    requires_personal=selected_command.owner_user_id is not None,
                )
            except ChannelBindingRequiredError:
                return await self._binding_required_message(event)
            except ChannelServiceIdentityUnavailableError:
                return ChannelMessage(text="当前渠道共享执行身份尚未配置或已停用，请联系管理员。")
            selected_input = render_command_input(
                selected_command,
                input_value=text,
                sender_name=event.user.display_name,
                conversation_name=event.conversation.title or (binding.display_name if binding else None),
                conversation_type=event.conversation.conversation_type,
            )
            return await self._execute_workflow(
                event,
                principal,
                str(selected_command.flow_id),
                selected_input or None,
                binding=binding,
                trigger_type=ChannelExecutionTrigger.SELECTED.value,
                command_name=selected_command.normalized_command,
                flow_id=selected_command.flow_id,
                workflow_command_id=selected_command.id,
                active_selection_id=selection_resolution.selection.id,
                selection_scope="identity_conversation",
            )

        try:
            principal = await resolve_execution_principal(
                self.session,
                self.connection,
                binding,
                identity,
            )
        except ChannelBindingRequiredError:
            return await self._binding_required_message(event)
        except ChannelServiceIdentityUnavailableError:
            return ChannelMessage(text="当前渠道共享执行身份尚未配置或已停用，请联系管理员。")
        flow_id = self._resolve_default_flow_id(binding)
        if flow_id is None:
            return await self._pending_route_message(binding)
        response = await self._execute_workflow(
            event,
            principal,
            str(flow_id),
            text,
            binding=binding,
            trigger_type=ChannelExecutionTrigger.DEFAULT.value,
            flow_id=flow_id,
        )
        if selection_resolution.invalid_reason and response is not None:
            return self._with_selection_fallback_notice(response)
        return response

    async def _execute_system_command(
        self,
        definition: SystemCommandDefinition,
        *,
        event: ChannelEvent,
        identity,
        bound_user: User | None,
        binding: ChannelConversationBinding | None,
        argument: str,
        access_policy: str,
        personal_user_id: UUID | None,
    ) -> ChannelMessage | None:
        command = definition.command
        is_admin = self._is_channel_admin(bound_user)
        shared_access = access_policy != "bound_only"
        is_allowed = can_use_system_command(
            definition,
            is_bound=bound_user is not None,
            is_admin=is_admin,
            shared_access=shared_access,
        )
        if not is_allowed:
            if definition.permission == "admin":
                return ChannelMessage(text=f"指令 {command} 仅限渠道管理员使用。")
            return await self._binding_required_message(event)

        if command == "/help":
            return self._help_message(
                bound_user=bound_user,
                is_admin=is_admin,
                access_policy=access_policy,
                conversation_type=event.conversation.conversation_type,
            )
        if command == "/bind":
            if bound_user is not None:
                return ChannelMessage(
                    title="账号已绑定",
                    text=f"当前渠道账号已绑定 OpenXFlow 用户：{bound_user.username}",
                )
            return await self._binding_required_message(event)
        if command == "/commands":
            return await self._commands_message(
                personal_user_id,
                binding,
                bound_user=bound_user,
                is_admin=is_admin,
                access_policy=access_policy,
                conversation_type=event.conversation.conversation_type,
                event=event,
                identity=identity,
            )
        if command == "/whoami":
            return self._whoami_message(
                event,
                bound_user=bound_user,
                access_policy=access_policy,
                is_admin=is_admin,
            )
        if command in {"/files", "/knowledge"}:
            try:
                principal = await resolve_execution_principal(
                    self.session,
                    self.connection,
                    binding,
                    identity,
                )
            except ChannelBindingRequiredError:
                return await self._binding_required_message(event)
            except ChannelServiceIdentityUnavailableError:
                return ChannelMessage(text="当前渠道共享执行身份尚未配置或已停用，请联系管理员。")
            if command == "/files":
                return await self._recent_files_message(event, principal.user)
            return await self._knowledge_message(binding)
        if command == "/use-flow":
            return await self._use_flow_message(
                event=event,
                identity=identity,
                bound_user=bound_user,
                binding=binding,
                argument=argument,
                personal_user_id=personal_user_id,
            )
        if command == "/current-flow":
            return await self._current_flow_message(
                event=event,
                identity=identity,
                binding=binding,
                personal_user_id=personal_user_id,
            )
        if command == "/flow":
            if bound_user is None:
                return ChannelMessage(text="指令 /flow 仅限渠道管理员使用。")
            flow_identifier, _, input_value = argument.partition(" ")
            if not flow_identifier:
                return ChannelMessage(text="管理员用法：/flow <工作流 ID 或 endpoint_name> [输入内容]")
            principal = ChannelExecutionPrincipal(
                user=bound_user,
                identity_type="bound_user",
                identity=identity,
            )
            return await self._execute_workflow(
                event,
                principal,
                flow_identifier,
                input_value or None,
                binding=binding,
                trigger_type=ChannelExecutionTrigger.ADMIN_FLOW.value,
                flow_id=self._try_uuid(flow_identifier),
            )
        if command == "/use-kb":
            if bound_user is None:
                return ChannelMessage(text="指令 /use-kb 仅限渠道管理员使用。")
            return await self._bind_knowledge_base(event, bound_user, binding, argument)
        if command == "/status":
            return self._status_message(binding, access_policy=access_policy)
        return None

    async def _use_flow_message(
        self,
        *,
        event: ChannelEvent,
        identity,
        bound_user: User | None,
        binding: ChannelConversationBinding | None,
        argument: str,
        personal_user_id: UUID | None,
    ) -> ChannelMessage:
        if not self.connection.user_flow_selection_enabled:
            return ChannelMessage(text="当前渠道未开启用户工作流切换，请联系管理员在默认路由中启用。")
        binding = binding or await self._ensure_conversation_binding(event)
        requested = argument.strip().split(maxsplit=1)[0] if argument.strip() else ""
        if not requested:
            return ChannelMessage(
                text="用法：/use-flow <业务指令>\n恢复默认：/use-flow default\n发送 /commands 查看可用业务指令。"
            )
        if requested.lower() in {"default", "/default", "默认"}:
            cleared = await clear_active_workflow_selection(
                self.session,
                connection_id=self.connection.id,
                conversation_binding_id=binding.id,
                channel_identity_id=identity.id,
                conversation_scope_id=conversation_scope_id(event),
                actor_user_id=bound_user.id if bound_user is not None else None,
            )
            await self.session.commit()
            default_flow_id = self._resolve_default_flow_id(binding)
            text = "已恢复当前会话的默认工作流。" if cleared else "当前已经在使用默认工作流。"
            if default_flow_id is None:
                text += " 当前会话尚未配置默认工作流。"
            return ChannelMessage(title="工作流已恢复", text=text)

        try:
            selection, command = await set_active_workflow_selection(
                self.session,
                connection=self.connection,
                binding=binding,
                identity=identity,
                conversation_scope_id=conversation_scope_id(event),
                user_id=personal_user_id,
                command_name=requested,
            )
        except FlowSelectionDisabledError:
            return ChannelMessage(text="当前渠道未开启用户工作流切换。")
        except FlowSelectionCommandUnavailableError:
            return ChannelMessage(text=f"当前会话没有可切换的业务指令 {requested}。发送 /commands 查看可用指令。")
        except FlowSelectionNotAllowedError:
            return ChannelMessage(text=f"指令 {requested} 仅支持单次执行，管理员未允许将其设为当前工作流。")
        await self.session.commit()
        expires = (
            "永久有效" if selection.expires_at is None else f"有效期 {self.connection.flow_selection_ttl_hours} 小时"
        )
        account = f"绑定账号：{bound_user.username}\n" if bound_user is not None else ""
        return ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="工作流已切换",
            text=(
                f"当前工作流：{command.command}\n"
                f"{account}"
                f"范围：当前用户 + 当前会话/线程\n"
                f"{expires}\n\n"
                "后续普通消息将持续使用该工作流。发送 /use-flow default 恢复默认。"
            ),
            actions=[
                ChannelAction(
                    action_id="system:current-flow",
                    label="/current-flow",
                    value="/current-flow",
                    style="primary",
                ),
                ChannelAction(action_id="system:use-flow-default", label="恢复默认", value="/use-flow default"),
            ],
        )

    async def _current_flow_message(
        self,
        *,
        event: ChannelEvent,
        identity,
        binding: ChannelConversationBinding | None,
        personal_user_id: UUID | None,
    ) -> ChannelMessage:
        if binding is not None:
            resolution = await resolve_active_workflow_selection(
                self.session,
                connection=self.connection,
                binding=binding,
                identity=identity,
                conversation_scope_id=conversation_scope_id(event),
                user_id=personal_user_id,
                touch=False,
            )
            if resolution.command is not None and resolution.selection is not None:
                flow = await self.session.get(Flow, resolution.command.flow_id)
                if resolution.selection.expires_at is None:
                    expires = "永久有效"
                else:
                    remaining = max(
                        timedelta(0),
                        resolution.selection.expires_at - datetime.now(timezone.utc),
                    )
                    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                    minutes = remainder // 60
                    expires = f"剩余 {hours} 小时 {minutes} 分钟"
                execution_identity = "绑定用户" if resolution.command.owner_user_id is not None else "渠道共享服务身份"
                conversation_name = (
                    event.conversation.title or (binding.display_name if binding else None) or "当前会话"
                )
                flow_name = flow.name if flow is not None else str(resolution.command.flow_id)[:8] + "…"
                endpoint = f"\nEndpoint：{flow.endpoint_name}" if flow is not None and flow.endpoint_name else ""
                return ChannelMessage(
                    message_type=ChannelMessageType.CARD,
                    title="当前工作流",
                    text=(
                        f"名称：{flow_name}\n"
                        f"业务指令：{resolution.command.command}\n"
                        f"执行身份：{execution_identity}\n"
                        f"作用范围：当前成员 + {conversation_name}\n"
                        f"有效期：{expires}{endpoint}"
                    ),
                    actions=[
                        ChannelAction(
                            action_id="system:use-flow-default",
                            label="恢复默认",
                            value="/use-flow default",
                        )
                    ],
                )
        default_flow_id = self._resolve_default_flow_id(binding)
        if default_flow_id is None:
            return ChannelMessage(title="当前工作流", text="当前没有个人选择，也没有可用默认工作流。")
        default_flow = await self.session.get(Flow, default_flow_id)
        flow_name = default_flow.name if default_flow is not None else str(default_flow_id)[:8] + "…"
        source = "会话覆盖" if binding is not None and binding.default_flow_id == default_flow_id else "连接默认"
        return ChannelMessage(
            title="当前工作流",
            text=f"名称：{flow_name}\n来源：{source}\n执行身份：按当前访问策略动态解析",
        )

    async def _execute_custom_command(
        self,
        event: ChannelEvent,
        identity,
        bound_user: User | None,
        binding: ChannelConversationBinding | None,
        command_name: str,
        argument: str,
    ) -> ChannelMessage | None:
        if binding is None:
            return None
        command_user_id = (
            bound_user.id
            if bound_user is not None and effective_access_policy(self.connection, binding) != "shared"
            else None
        )
        command = await resolve_workflow_command(
            self.session,
            connection_id=self.connection.id,
            conversation_binding_id=binding.id,
            user_id=command_user_id,
            command_name=command_name,
        )
        if command is None:
            return None
        if (
            event.conversation.conversation_type != "private"
            and command.require_mention
            and not self._command_targets_bot(event)
        ):
            return None
        if event.message.attachments and not command.allow_attachments:
            return ChannelMessage(text=f"指令 {command.command} 不允许上传附件。")
        if command.input_required and not argument and not event.message.attachments:
            description = command.description or "请在指令后输入需要处理的内容。"
            return ChannelMessage(title=command.command, text=f"{description}\n\n用法：{command.command} <内容>")

        try:
            principal = await resolve_execution_principal(
                self.session,
                self.connection,
                binding,
                identity,
                requires_personal=command.owner_user_id is not None,
            )
        except ChannelBindingRequiredError:
            return await self._binding_required_message(event)
        except ChannelServiceIdentityUnavailableError:
            return ChannelMessage(text="当前渠道共享执行身份尚未配置或已停用，请联系管理员。")

        input_value = render_command_input(
            command,
            input_value=argument,
            sender_name=event.user.display_name,
            conversation_name=event.conversation.title or binding.display_name,
            conversation_type=event.conversation.conversation_type,
        )
        await mark_workflow_command_used(self.session, command)
        return await self._execute_workflow(
            event,
            principal,
            str(command.flow_id),
            input_value or None,
            binding=binding,
            trigger_type=ChannelExecutionTrigger.COMMAND.value,
            command_name=command.normalized_command,
            flow_id=command.flow_id,
            workflow_command_id=command.id,
        )

    async def _commands_message(
        self,
        user_id: UUID | None,
        binding: ChannelConversationBinding | None,
        *,
        bound_user: User | None,
        is_admin: bool,
        access_policy: str,
        conversation_type: str,
        event: ChannelEvent,
        identity,
    ) -> ChannelMessage:
        system_commands = visible_system_commands(
            is_bound=bound_user is not None,
            is_admin=is_admin,
            conversation_type=conversation_type,
            shared_access=access_policy != "bound_only",
        )
        custom_commands: list[ChannelWorkflowCommand] = []
        if binding is not None:
            custom_commands = await list_available_workflow_commands(
                self.session,
                connection_id=self.connection.id,
                conversation_binding_id=binding.id,
                user_id=user_id,
            )

        current_command_id: UUID | None = None
        if binding is not None and self.connection.user_flow_selection_enabled:
            current_resolution = await resolve_active_workflow_selection(
                self.session,
                connection=self.connection,
                binding=binding,
                identity=identity,
                conversation_scope_id=conversation_scope_id(event),
                user_id=user_id,
                touch=False,
            )
            if current_resolution.command is not None:
                current_command_id = current_resolution.command.id

        sections = ["系统指令"]
        sections.extend(f"{item.command} — {item.description}" for item in system_commands)
        if custom_commands:
            sections.append("\n业务指令")
            for item in custom_commands[:50]:
                description = f" — {item.description}" if item.description else ""
                flags: list[str] = []
                if item.allow_persistent_selection:
                    flags.append("可切换")
                if item.id == current_command_id:
                    flags.append("当前")
                suffix = f" [{', '.join(flags)}]" if flags else ""
                sections.append(f"{item.command}{description}{suffix}")
        elif binding is None:
            sections.append("\n业务指令\n当前会话尚未完成自动发现。")
        else:
            sections.append("\n业务指令\n当前会话还没有配置自定义指令。")

        action_items = [
            ChannelAction(
                action_id=f"system:{item.command.removeprefix('/')}",
                label=item.command,
                value=item.command,
                style="primary" if item.command == "/commands" else "default",
            )
            for item in system_commands
            if item.command in {"/commands", "/current-flow", "/whoami", "/files", "/knowledge", "/status"}
        ][:4]
        remaining = max(0, 6 - len(action_items))
        selectable_commands = [item for item in custom_commands if item.allow_persistent_selection]
        if self.connection.user_flow_selection_enabled:
            action_items.extend(
                ChannelAction(
                    action_id=f"use-flow:{item.normalized_command}",
                    label=f"切换 {item.command}",
                    value=f"/use-flow {item.command}",
                    style="primary" if item.id == current_command_id else "default",
                )
                for item in selectable_commands[:remaining]
            )
        remaining = max(0, 6 - len(action_items))
        action_items.extend(
            ChannelAction(
                action_id=f"command:{item.normalized_command}",
                label=item.command,
                value=item.command,
            )
            for item in custom_commands[:remaining]
        )
        return ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="当前可用指令",
            text="\n".join(sections),
            actions=action_items,
        )

    async def _unknown_command_message(
        self,
        user_id: UUID | None,
        binding: ChannelConversationBinding | None,
        command_name: str,
        *,
        bound_user: User | None,
        access_policy: str,
        conversation_type: str,
    ) -> ChannelMessage:
        is_admin = self._is_channel_admin(bound_user)
        system_commands = visible_system_commands(
            is_bound=bound_user is not None,
            is_admin=is_admin,
            conversation_type=conversation_type,
            shared_access=access_policy != "bound_only",
        )
        system_by_name = {name: item for item in system_commands for name in item.names}
        system_by_name["/help"] = resolve_system_command("/help")
        system_suggestions = get_close_matches(command_name.lower(), list(system_by_name), n=3, cutoff=0.45)
        if system_suggestions:
            suggested = []
            seen: set[str] = set()
            for name in system_suggestions:
                item = system_by_name[name]
                if item is not None and item.command not in seen:
                    seen.add(item.command)
                    suggested.append(item)
            if suggested:
                suggested_text = "、".join(item.command for item in suggested)
                return ChannelMessage(
                    message_type=ChannelMessageType.CARD,
                    title="没有找到该指令",
                    text=f"你是否想使用：{suggested_text}？\n\n发送 /commands 查看全部指令。",
                    actions=[
                        ChannelAction(
                            action_id=f"suggested:{item.command.removeprefix('/')}",
                            label=item.command,
                            value=item.command,
                        )
                        for item in suggested
                    ],
                )

        commands: list[ChannelWorkflowCommand] = []
        if binding is not None:
            commands = await list_available_workflow_commands(
                self.session,
                connection_id=self.connection.id,
                conversation_binding_id=binding.id,
                user_id=user_id,
            )
        command_by_name = {name: item for item in commands for name in (item.normalized_command, *item.aliases)}
        suggestions = get_close_matches(command_name.lower(), list(command_by_name), n=3, cutoff=0.45)
        if not suggestions:
            return ChannelMessage(text=f"没有找到指令 {command_name}。发送 /commands 查看当前可用指令。")
        unique_commands: list[ChannelWorkflowCommand] = []
        seen_ids: set[UUID] = set()
        for suggestion in suggestions:
            item = command_by_name[suggestion]
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                unique_commands.append(item)
        suggested_text = "、".join(item.command for item in unique_commands)
        return ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="没有找到该指令",
            text=f"你是否想使用：{suggested_text}？\n\n发送 /commands 查看全部指令。",
            actions=[
                ChannelAction(
                    action_id=f"suggested:{item.normalized_command}",
                    label=item.command,
                    value=item.command,
                )
                for item in unique_commands
            ],
        )

    @staticmethod
    def _with_selection_fallback_notice(response: ChannelMessage) -> ChannelMessage:
        notice = "你之前选择的工作流已失效，当前已恢复默认工作流。"
        if response.markdown:
            response.markdown = f"{notice}\n\n{response.markdown}"
        else:
            response.text = f"{notice}\n\n{response.text or ''}"
        return response

    def _resolve_default_flow_id(self, binding: ChannelConversationBinding | None) -> UUID | None:
        if binding is not None:
            if binding.route_mode == ChannelConversationRouteMode.DISABLED.value:
                return None
            if (
                binding.route_mode == ChannelConversationRouteMode.OVERRIDE.value
                and binding.default_flow_id is not None
            ):
                return binding.default_flow_id
        return self.connection.default_flow_id

    async def _pending_route_message(self, binding: ChannelConversationBinding | None) -> ChannelMessage | None:
        if self.connection.unconfigured_behavior == ChannelUnconfiguredBehavior.IGNORE.value:
            return None
        if not self.connection.pending_notice_enabled:
            return None
        if binding is not None and binding.pending_notice_sent_at is not None:
            return None
        if binding is not None:
            binding.pending_notice_sent_at = datetime.now(timezone.utc)
            binding.status = ChannelConversationStatus.PENDING.value
            binding.updated_at = datetime.now(timezone.utc)
            self.session.add(binding)
            await self.session.flush()
        return ChannelMessage(
            text=("当前会话已接入 OpenXFlow，但尚未配置默认工作流。管理员可在“设置 → 渠道中心 → 会话”中完成配置。")
        )

    async def _execute_workflow(
        self,
        event: ChannelEvent,
        principal: ChannelExecutionPrincipal,
        flow_identifier: str,
        input_value: str | None,
        *,
        binding: ChannelConversationBinding | None,
        trigger_type: str,
        command_name: str | None = None,
        flow_id: UUID | None = None,
        workflow_command_id: UUID | None = None,
        active_selection_id: UUID | None = None,
        selection_scope: str | None = None,
    ) -> ChannelMessage | None:
        if isinstance(principal, ChannelExecutionPrincipal):
            execution_user = principal.user
            execution_identity_type = principal.identity_type
        else:
            execution_user = principal
            execution_identity_type = "bound_user"
        context_mode = effective_context_mode(self.connection, binding)
        session_id = build_channel_session_id(
            event,
            context_mode,
            flow_key=flow_id or flow_identifier,
        )
        prepared_input = input_value
        if self.session is not None:
            prepared_input = await prepare_channel_input(
                self.session,
                connection=self.connection,
                binding=binding,
                event=event,
                session_id=session_id,
                input_value=input_value,
            )

        execution = None
        queue_wait_ms = event.message.metadata.get("queue_wait_ms")
        if not isinstance(queue_wait_ms, int):
            queue_wait_ms = None
        if self.session is not None:
            try:
                execution = await start_channel_execution(
                    self.session,
                    connection_id=self.connection.id,
                    conversation_binding_id=binding.id if binding else None,
                    openxflow_user_id=execution_user.id,
                    external_user_id=event.user.external_user_id,
                    session_id=session_id,
                    execution_identity_type=execution_identity_type,
                    flow_id=flow_id,
                    external_event_id=event.event_id,
                    trigger_type=trigger_type,
                    command_name=command_name,
                    workflow_command_id=workflow_command_id,
                    active_selection_id=active_selection_id,
                    selection_scope=selection_scope,
                    queue_wait_ms=queue_wait_ms,
                )
            except Exception:  # noqa: BLE001
                await logger.aexception("Unable to create channel execution log")
            await self.session.commit()

        processing_message_id = await self._send_processing_message(event)
        final_status = ChannelExecutionStatus.FAILED.value
        error_message: str | None = None
        error_code: str | None = None
        try:
            channel_context = await self._build_bound_context(binding)
            channel_context.update(
                {
                    "access_policy": effective_access_policy(self.connection, binding),
                    "context_mode": context_mode,
                    "execution_identity_type": execution_identity_type,
                    "granted_flow_id": str(flow_id) if flow_id is not None else None,
                }
            )
            if command_name:
                channel_context["command_name"] = command_name
            if workflow_command_id is not None:
                channel_context["workflow_command_id"] = str(workflow_command_id)
            if active_selection_id is not None:
                channel_context["active_selection_id"] = str(active_selection_id)
            executor_kwargs: dict[str, Any] = {
                "event": event,
                "user": execution_user,
                "flow_identifier": flow_identifier,
                "input_value": prepared_input,
                "channel_context": channel_context,
            }
            executor_parameters = inspect.signature(self.workflow_executor.execute).parameters
            if "session_id" in executor_parameters:
                executor_kwargs["session_id"] = session_id
            if "execution_identity_type" in executor_parameters:
                executor_kwargs["execution_identity_type"] = execution_identity_type
            response = await self.workflow_executor.execute(**executor_kwargs)
            final_status = ChannelExecutionStatus.SUCCEEDED.value
            if self.session is not None:
                await record_channel_response(
                    self.session,
                    connection=self.connection,
                    binding=binding,
                    event=event,
                    session_id=session_id,
                    response=response,
                )
                await self.session.commit()
        except HTTPException as exc:
            error_message = str(exc.detail)
            error_code = f"http_{exc.status_code}"
            if exc.status_code in {403, 404}:
                response = ChannelMessage(text="工作流不存在，或当前执行身份没有执行权限。")
            else:
                await logger.aexception("Channel workflow HTTP error for flow %s", flow_identifier)
                response = ChannelMessage(text="工作流执行失败，请稍后重试。")
        except asyncio.CancelledError:
            error_message = "Channel workflow execution was cancelled or timed out"
            error_code = "execution_cancelled"
            final_status = ChannelExecutionStatus.TIMEOUT.value
            raise
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            error_code = type(exc).__name__[:128]
            await logger.aexception("Channel workflow execution failed for flow %s", flow_identifier)
            response = ChannelMessage(text="工作流执行失败，请在 OpenXFlow 运行记录中查看错误详情。")
        finally:
            if execution is not None:
                try:
                    await finalize_channel_execution(
                        execution.id,
                        status=final_status,
                        error_message=error_message,
                        error_code=error_code,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    await logger.aexception("Unable to finish channel execution log %s", execution.id)

        if processing_message_id is not None:
            delivery_started = time.perf_counter()
            try:
                await retry_channel_operation(
                    lambda: self.adapter.update_message(processing_message_id, response),
                    operation_name=f"{self.adapter.channel_type.value}.update_processing_message",
                )
                duration_ms = max(0, int((time.perf_counter() - delivery_started) * 1000))
                await safe_record_outbound_message(
                    event,
                    response,
                    status=ChannelMessageRecordStatus.SENT.value,
                    provider_message_id=processing_message_id,
                )
                await safe_record_channel_delivery_outcome(
                    connection_id=event.connection_id,
                    external_event_id=event.event_id,
                    duration_ms=duration_ms,
                )
                return None
            except Exception:  # noqa: BLE001
                await logger.aexception(
                    "Unable to update processing message %s; falling back to a new response",
                    processing_message_id,
                )
        return response

    async def _send_processing_message(self, event: ChannelEvent) -> str | None:
        capabilities = get_provider_capability(event.channel.value)
        if (
            capabilities is None
            or not capabilities.supports_processing_message
            or not capabilities.supports_message_update
        ):
            return None
        processing_message = ChannelMessage(
            message_type=ChannelMessageType(capabilities.processing_message_type),
            text="⏳ 正在处理中，请稍候…",
            metadata=dict(capabilities.processing_message_metadata),
        )

        async def sender() -> str:
            return await retry_channel_operation(
                lambda: self.adapter.send_response(event, processing_message),
                operation_name=f"{event.channel.value}.send_processing_message",
            )

        try:
            if self.session is None:
                return await sender()
            return await send_outbound_processing_once(event, processing_message, sender)
        except Exception:  # noqa: BLE001
            await logger.aexception(
                "Unable to send %s processing message; continuing without it",
                event.channel.value,
            )
            return None

    async def _binding_required_message(self, event: ChannelEvent) -> ChannelMessage:
        if event.conversation.conversation_type != "private":
            return ChannelMessage(text="请先私聊机器人并发送 /bind，完成 OpenXFlow 账号绑定。")
        code = await issue_channel_binding_code(self.session, event)
        return ChannelMessage(
            title="绑定 OpenXFlow 账号",
            text=(
                f"绑定码：{code}\n\n"
                "请登录 OpenXFlow，进入“设置 → 渠道中心 → 账号绑定”，输入该绑定码。"
                "绑定码 10 分钟内有效且只能使用一次。"
            ),
        )

    async def _get_conversation_binding(self, event: ChannelEvent) -> ChannelConversationBinding | None:
        statement = select(ChannelConversationBinding).where(
            ChannelConversationBinding.connection_id == event.connection_id,
            ChannelConversationBinding.external_conversation_id == event.conversation.external_conversation_id,
        )
        return (await self.session.exec(statement)).first()

    async def _ensure_conversation_binding(self, event: ChannelEvent) -> ChannelConversationBinding:
        binding = await discover_channel_conversation(self.session, self.connection, event)
        if binding is not None:
            return binding
        binding = await self._get_conversation_binding(event)
        if binding is not None:
            return binding
        binding = ChannelConversationBinding(
            connection_id=event.connection_id,
            external_conversation_id=event.conversation.external_conversation_id,
            conversation_type=event.conversation.conversation_type,
            display_name=event.conversation.title,
            response_mode=self.connection.default_response_mode,
            allow_file_upload=self.connection.default_allow_file_upload,
        )
        self.session.add(binding)
        await self.session.flush()
        await self.session.refresh(binding)
        return binding

    async def _knowledge_message(self, binding: ChannelConversationBinding | None) -> ChannelMessage:
        knowledge_base_id = (
            binding.knowledge_base_id
            if binding is not None and binding.knowledge_base_id is not None
            else self.connection.default_knowledge_base_id
        )
        if knowledge_base_id is None:
            return ChannelMessage(
                title="当前知识库",
                text="当前会话尚未绑定知识库。管理员可在渠道中心配置，或使用 /use-kb 切换。",
            )
        knowledge_base = await self.session.get(KnowledgeBaseRecord, knowledge_base_id)
        if knowledge_base is None:
            return ChannelMessage(title="当前知识库", text="已配置的知识库不存在或已被删除，请联系管理员。")
        return ChannelMessage(
            title="当前知识库",
            text=f"{knowledge_base.name}\n状态：{knowledge_base.status}\n分块：{knowledge_base.chunks}",
        )

    async def _bind_knowledge_base(
        self,
        event: ChannelEvent,
        user: User,
        binding: ChannelConversationBinding | None,
        identifier: str,
    ) -> ChannelMessage:
        normalized = identifier.strip()
        if not normalized:
            return ChannelMessage(text="管理员用法：/use-kb <知识库名称或 ID>；使用 /use-kb clear 可解除绑定。")

        binding = binding or await self._ensure_conversation_binding(event)
        if normalized.lower() in {"none", "off", "clear"} or normalized in {"取消", "关闭", "解除"}:
            binding.knowledge_base_id = None
            self.session.add(binding)
            await self.session.flush()
            return ChannelMessage(title="知识库已解除", text="当前会话不再自动接收文件到知识库。")

        kb = await resolve_owned_knowledge_base(self.session, user.id, normalized)
        if kb is None:
            return ChannelMessage(text="没有找到该知识库，请前往 OpenXFlow 渠道中心选择。")
        try:
            await ensure_knowledge_base_permission(
                user,
                KnowledgeBaseAction.INGEST,
                kb_id=kb.id,
                kb_user_id=kb.user_id,
                kb_name=kb.name,
            )
        except HTTPException:
            return ChannelMessage(text="当前账号没有向该知识库写入文件的权限。")

        binding.knowledge_base_id = kb.id
        self.session.add(binding)
        await self.session.flush()
        return ChannelMessage(
            title="知识库绑定成功",
            text=(f"当前会话已绑定：{kb.name}\n之后上传的受支持文件会自动进入该知识库解析。"),
        )

    async def _recent_files_message(self, event: ChannelEvent, user: User) -> ChannelMessage:
        assets = await self.file_service.list_recent_assets(
            user_id=user.id,
            external_conversation_id=event.conversation.external_conversation_id,
        )
        if not assets:
            return ChannelMessage(title="最近文件", text="当前会话还没有上传过文件。")
        labels = {
            "received": "接收中",
            "stored": "已保存",
            "ingesting": "解析中",
            "ready": "已完成",
            "failed": "失败",
        }
        lines = [
            f"• {asset.filename}｜{labels.get(asset.status, asset.status)}｜{str(asset.id)[:8]}" for asset in assets
        ]
        return ChannelMessage(title="最近文件", text="\n".join(lines))

    def _whoami_message(
        self,
        event: ChannelEvent,
        *,
        bound_user: User | None,
        access_policy: str,
        is_admin: bool,
    ) -> ChannelMessage:
        account = bound_user.username if bound_user is not None else "未绑定"
        if access_policy == "shared":
            execution_mode = "渠道共享服务身份"
        elif bound_user is not None:
            execution_mode = "已绑定 OpenXFlow 账号"
        elif access_policy == "hybrid":
            execution_mode = "渠道共享服务身份"
        else:
            execution_mode = "等待账号绑定"
        role = "渠道管理员" if is_admin else "普通成员"
        display_name = event.user.display_name or "未提供"
        return ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="当前渠道身份",
            text=(
                f"渠道：{self.connection.channel_type}\n"
                f"会话：{event.conversation.conversation_type}\n"
                f"渠道昵称：{display_name}\n"
                f"OpenXFlow 账号：{account}\n"
                f"角色：{role}\n"
                f"默认执行方式：{execution_mode}"
            ),
        )

    def _status_message(
        self,
        binding: ChannelConversationBinding | None,
        *,
        access_policy: str,
    ) -> ChannelMessage:
        enabled = "已启用" if getattr(self.connection, "enabled", True) else "已停用"
        response_mode = binding.response_mode if binding is not None else self.connection.default_response_mode
        route_mode = binding.route_mode if binding is not None else "connection_default"
        context_mode = effective_context_mode(self.connection, binding)
        flow_id = self._resolve_default_flow_id(binding)
        conversation_status = binding.status if binding is not None else "discovering"
        return ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="渠道运行状态",
            text=(
                f"连接：{enabled}\n"
                f"渠道：{self.connection.channel_type}\n"
                f"会话状态：{conversation_status}\n"
                f"响应模式：{response_mode}\n"
                f"访问策略：{access_policy}\n"
                f"上下文模式：{context_mode}\n"
                f"路由模式：{route_mode}\n"
                f"默认工作流：{'已配置' if flow_id is not None else '未配置'}"
            ),
        )

    async def _build_bound_context(
        self,
        binding: ChannelConversationBinding | None,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "connection_id": str(self.connection.id),
            "channel_type": self.connection.channel_type,
        }
        if binding is not None:
            context.update(
                {
                    "conversation_binding_id": str(binding.id),
                    "response_mode": normalize_response_mode(binding.response_mode),
                    "allow_file_upload": binding.allow_file_upload,
                    "conversation_route_mode": binding.route_mode,
                    "conversation_access_policy": binding.access_policy,
                    "conversation_context_mode": binding.context_mode,
                }
            )
        knowledge_base_id = (
            binding.knowledge_base_id
            if binding is not None and binding.knowledge_base_id is not None
            else self.connection.default_knowledge_base_id
        )
        if knowledge_base_id is not None:
            kb = await self.session.get(KnowledgeBaseRecord, knowledge_base_id)
            context["knowledge_base_id"] = str(knowledge_base_id)
            if kb is not None:
                context["knowledge_base_name"] = kb.name
        return context

    def _is_channel_admin(self, user: User | None) -> bool:
        return bool(user is not None and (user.is_superuser or user.id == self.connection.user_id))

    @staticmethod
    def _try_uuid(value: str) -> UUID | None:
        try:
            return UUID(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_command(text: str | None) -> tuple[str | None, str]:
        normalized = (text or "").strip()
        if not normalized.startswith("/"):
            return None, normalized
        token, _, argument = normalized.partition(" ")
        command = token.split("@", 1)[0].lower()
        return command, argument.strip()

    @staticmethod
    def _command_targets_bot(event: ChannelEvent) -> bool:
        if event.message.mentions:
            return True
        token = (event.message.text or "").strip().partition(" ")[0]
        return token.startswith("/") and "@" in token

    @staticmethod
    def _should_ignore_group_event(
        event: ChannelEvent,
        *,
        command: str | None = None,
        response_mode: str | None = None,
        binding: ChannelConversationBinding | None = None,
        require_command_mention: bool = False,
        command_targeted: bool = False,
    ) -> bool:
        effective_mode = response_mode
        if effective_mode is None and binding is not None:
            effective_mode = binding.response_mode
        if (
            event.conversation.conversation_type != "private"
            and command is not None
            and require_command_mention
            and not command_targeted
        ):
            return True
        return not should_process_channel_event(
            event,
            command=command,
            response_mode=effective_mode,
        )

    @staticmethod
    def _help_message(
        *,
        bound_user: User | None,
        is_admin: bool,
        access_policy: str,
        conversation_type: str,
    ) -> ChannelMessage:
        account_line = (
            f"账号状态：已绑定（{bound_user.username}）。\n\n" if bound_user is not None else "账号状态：未绑定。\n\n"
        )
        commands = visible_system_commands(
            is_bound=bound_user is not None,
            is_admin=is_admin,
            conversation_type=conversation_type,
            shared_access=access_policy != "bound_only",
        )
        lines = ["/help — 查看使用帮助", *(f"{item.command} — {item.description}" for item in commands)]
        command_text = "\n".join(lines)
        action_values = [
            item.command
            for item in commands
            if item.command in {"/commands", "/whoami", "/files", "/knowledge", "/status"}
        ][:4]
        return ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="OpenXFlow 渠道助手",
            text=(
                f"{account_line}可用系统指令：\n{command_text}\n\n普通消息会自动运行当前会话或渠道连接的默认工作流。"
            ),
            actions=[
                ChannelAction(
                    action_id=f"help:{value.removeprefix('/')}",
                    label=value,
                    value=value,
                    style="primary" if value == "/commands" else "default",
                )
                for value in action_values
            ],
        )
