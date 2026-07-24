"""Resolve identities and dispatch normalized channel events to OpenXFlow features."""

from __future__ import annotations

from datetime import datetime, timezone
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
    ChannelEventType,
    ChannelMessage,
    ChannelMessageType,
    ChannelType,
)
from langflow.channels.services.binding import issue_channel_binding_code, resolve_channel_identity
from langflow.channels.services.commands import (
    list_available_workflow_commands,
    mark_workflow_command_used,
    render_command_input,
    resolve_workflow_command,
)
from langflow.channels.services.execution_logs import finish_channel_execution, start_channel_execution
from langflow.channels.services.files import (
    ChannelFileService,
    list_owned_knowledge_bases,
    resolve_owned_knowledge_base,
)
from langflow.channels.services.retry import retry_channel_operation
from langflow.channels.services.workflow import ChannelWorkflowExecutor
from langflow.services.authorization import KnowledgeBaseAction, ensure_knowledge_base_permission

if TYPE_CHECKING:
    from langflow.services.database.models.channel.command_model import ChannelWorkflowCommand

from langflow.services.database.models.channel.crud import discover_channel_conversation
from langflow.services.database.models.channel.execution_model import ChannelExecutionTrigger
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConversationBinding,
    ChannelConversationRouteMode,
    ChannelConversationStatus,
    ChannelUnconfiguredBehavior,
)
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
        command, argument = self._parse_command(event.message.text)
        binding = await discover_channel_conversation(self.session, self.connection, event)
        if binding is None:
            binding = await self._get_conversation_binding(event)

        if binding is not None and binding.status in {
            ChannelConversationStatus.IGNORED.value,
            ChannelConversationStatus.DISABLED.value,
            ChannelConversationStatus.UNAVAILABLE.value,
        }:
            return None
        if self._should_ignore_group_event(event, binding=binding, command=command):
            return None

        identity = await resolve_channel_identity(self.session, event)
        if identity is None:
            return await self._binding_required_message(event)

        event.user.openxflow_user_id = identity.openxflow_user_id
        user = await self.session.get(User, identity.openxflow_user_id)
        if user is None or not user.is_active:
            return ChannelMessage(text="绑定的 OpenXFlow 账号不存在或已停用，请联系管理员。")

        if command in {"/start", "/help"}:
            return self._help_message(bound=True)
        if command == "/bind":
            return ChannelMessage(
                title="账号已绑定",
                text=f"当前渠道账号已绑定 OpenXFlow 用户：{user.username}",
            )
        if command == "/commands":
            return await self._commands_message(user, binding)

        if command == "/flow":
            if user.id != self.connection.user_id and not user.is_superuser:
                return ChannelMessage(text="未知命令。发送 /commands 查看当前可用指令。")
            flow_identifier, _, input_value = argument.partition(" ")
            if not flow_identifier:
                return ChannelMessage(text="管理员用法：/flow <工作流 ID 或 endpoint_name> [输入内容]")
            return await self._execute_workflow(
                event,
                user,
                flow_identifier,
                input_value or None,
                binding=binding,
                trigger_type=ChannelExecutionTrigger.ADMIN_FLOW.value,
                flow_id=self._try_uuid(flow_identifier),
            )

        if command is not None:
            custom_response = await self._execute_custom_command(
                event,
                user,
                binding,
                command,
                argument,
            )
            if custom_response is not None:
                return custom_response
            return await self._unknown_command_message(user, binding, command)

        if event.message.attachments:
            binding = binding or await self._ensure_conversation_binding(event)
            if not binding.allow_file_upload:
                return ChannelMessage(text="当前会话已关闭文件上传，请在 OpenXFlow 渠道中心重新启用。")
            responses: list[str] = []
            title: str | None = None
            for attachment in event.message.attachments:
                response = await self.file_service.handle_attachment(
                    event=event,
                    user=user,
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

        flow_id = self._resolve_default_flow_id(binding)
        if flow_id is None:
            return await self._pending_route_message(binding)
        return await self._execute_workflow(
            event,
            user,
            str(flow_id),
            text,
            binding=binding,
            trigger_type=ChannelExecutionTrigger.DEFAULT.value,
            flow_id=flow_id,
        )

    async def _execute_custom_command(
        self,
        event: ChannelEvent,
        user: User,
        binding: ChannelConversationBinding | None,
        command_name: str,
        argument: str,
    ) -> ChannelMessage | None:
        if binding is None:
            return None
        command = await resolve_workflow_command(
            self.session,
            connection_id=self.connection.id,
            conversation_binding_id=binding.id,
            user_id=user.id,
            command_name=command_name,
        )
        if command is None:
            return None
        if event.conversation.conversation_type != "private" and command.require_mention and not event.message.mentions:
            return None
        if event.message.attachments and not command.allow_attachments:
            return ChannelMessage(text=f"指令 {command.command} 不允许上传附件。")
        if command.input_required and not argument and not event.message.attachments:
            description = command.description or "请在指令后输入需要处理的内容。"
            return ChannelMessage(
                title=command.command,
                text=f"{description}\n\n用法：{command.command} <内容>",
            )

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
            user,
            str(command.flow_id),
            input_value or None,
            binding=binding,
            trigger_type=ChannelExecutionTrigger.COMMAND.value,
            command_name=command.normalized_command,
            flow_id=command.flow_id,
        )

    async def _commands_message(
        self,
        user: User,
        binding: ChannelConversationBinding | None,
    ) -> ChannelMessage:
        if binding is None:
            return ChannelMessage(title="可用指令", text="当前会话尚未完成自动发现。")
        commands = await list_available_workflow_commands(
            self.session,
            connection_id=self.connection.id,
            conversation_binding_id=binding.id,
            user_id=user.id,
        )
        if not commands:
            return ChannelMessage(title="可用指令", text="当前会话还没有配置自定义指令。")
        lines = []
        for item in commands[:50]:
            description = f" — {item.description}" if item.description else ""
            lines.append(f"{item.command}{description}")
        return ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="当前可用指令",
            text="\n".join(lines),
            actions=[
                ChannelAction(
                    action_id=f"command:{item.normalized_command}",
                    label=item.command,
                    value=item.command,
                )
                for item in commands[:6]
            ],
        )

    async def _unknown_command_message(
        self,
        user: User,
        binding: ChannelConversationBinding | None,
        command_name: str,
    ) -> ChannelMessage:
        commands: list[ChannelWorkflowCommand] = []
        if binding is not None:
            commands = await list_available_workflow_commands(
                self.session,
                connection_id=self.connection.id,
                conversation_binding_id=binding.id,
                user_id=user.id,
            )
        command_by_name = {name: item for item in commands for name in (item.normalized_command, *item.aliases)}
        suggestions = get_close_matches(
            command_name.lower(),
            list(command_by_name),
            n=3,
            cutoff=0.45,
        )
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
        user: User,
        flow_identifier: str,
        input_value: str | None,
        *,
        binding: ChannelConversationBinding | None,
        trigger_type: str,
        command_name: str | None = None,
        flow_id: UUID | None = None,
    ) -> ChannelMessage | None:
        execution = None
        try:
            execution = await start_channel_execution(
                self.session,
                connection_id=self.connection.id,
                conversation_binding_id=binding.id if binding else None,
                openxflow_user_id=user.id,
                flow_id=flow_id,
                external_event_id=event.event_id,
                trigger_type=trigger_type,
                command_name=command_name,
            )
        except Exception:  # noqa: BLE001
            await logger.aexception("Unable to create channel execution log")

        processing_message_id = await self._send_processing_message(event)
        succeeded = False
        error_message: str | None = None
        try:
            channel_context = await self._build_bound_context(binding)
            if command_name:
                channel_context["command_name"] = command_name
            response = await self.workflow_executor.execute(
                event=event,
                user=user,
                flow_identifier=flow_identifier,
                input_value=input_value,
                channel_context=channel_context,
            )
            succeeded = True
        except HTTPException as exc:
            error_message = str(exc.detail)
            if exc.status_code in {403, 404}:
                response = ChannelMessage(text="工作流不存在，或当前绑定账号没有执行权限。")
            else:
                await logger.aexception("Channel workflow HTTP error for flow %s", flow_identifier)
                response = ChannelMessage(text="工作流执行失败，请稍后重试。")
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            await logger.aexception("Channel workflow execution failed for flow %s", flow_identifier)
            response = ChannelMessage(text="工作流执行失败，请在 OpenXFlow 运行记录中查看错误详情。")
        finally:
            if execution is not None:
                try:
                    await finish_channel_execution(
                        self.session,
                        execution,
                        succeeded=succeeded,
                        error_message=error_message,
                    )
                except Exception:  # noqa: BLE001
                    await logger.aexception("Unable to finish channel execution log %s", execution.id)

        if processing_message_id is not None:
            try:
                await retry_channel_operation(
                    lambda: self.adapter.update_message(processing_message_id, response),
                    operation_name=f"{self.adapter.channel_type.value}.update_processing_message",
                )
                return None
            except Exception:  # noqa: BLE001
                await logger.aexception(
                    "Unable to update Feishu processing message %s; falling back to a new response",
                    processing_message_id,
                )
        return response

    async def _send_processing_message(self, event: ChannelEvent) -> str | None:
        if event.channel != ChannelType.FEISHU:
            return None
        processing_message = ChannelMessage(
            message_type=ChannelMessageType.CARD,
            text="⏳ 正在处理中，请稍候…",
            metadata={"feishu_update_multi": True},
        )
        try:
            return await retry_channel_operation(
                lambda: self.adapter.send_response(event, processing_message),
                operation_name="feishu.send_processing_message",
            )
        except Exception:  # noqa: BLE001
            await logger.aexception("Unable to send Feishu processing message; continuing without it")
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

    async def _knowledge_message(
        self,
        user: User,
        binding: ChannelConversationBinding | None,
    ) -> ChannelMessage:
        knowledge_bases = await list_owned_knowledge_bases(self.session, user.id)
        if not knowledge_bases:
            return ChannelMessage(
                title="知识库",
                text="当前账号还没有知识库，请先在 OpenXFlow 网页端创建。",
            )
        current_id = binding.knowledge_base_id if binding else self.connection.default_knowledge_base_id
        lines = []
        for kb in knowledge_bases[:20]:
            marker = "✅" if kb.id == current_id else "•"
            lines.append(f"{marker} {kb.name}（{kb.status}，{kb.chunks} 个分块）")
        return ChannelMessage(
            title="可用知识库",
            text=("\n".join(lines) + "\n\n请在 OpenXFlow 渠道中心配置会话知识库。"),
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
            return ChannelMessage(text="请在 OpenXFlow 渠道中心配置当前会话知识库。")

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
                    "response_mode": binding.response_mode,
                    "allow_file_upload": binding.allow_file_upload,
                    "conversation_route_mode": binding.route_mode,
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
    def _should_ignore_group_event(
        event: ChannelEvent,
        *,
        binding: ChannelConversationBinding | None = None,
        command: str | None = None,
    ) -> bool:
        if event.conversation.conversation_type == "private":
            return False
        if event.event_type != ChannelEventType.TEXT:
            return False
        if command is not None or event.message.mentions:
            return False
        return binding is None or binding.response_mode != "all_messages"

    @staticmethod
    def _help_message(*, bound: bool) -> ChannelMessage:
        binding_line = "账号状态：已绑定。\n\n" if bound else "账号状态：未绑定。\n\n"
        return ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="OpenXFlow 渠道助手",
            text=(
                f"{binding_line}"
                "可用系统指令：\n"
                "/bind — 绑定或查看账号状态\n"
                "/commands — 查看当前可用的自定义指令\n"
                "/help — 查看帮助\n\n"
                "普通消息会自动运行当前会话或渠道连接的默认工作流。"
            ),
            actions=[
                ChannelAction(action_id="account", label="账号状态", value="/bind"),
                ChannelAction(
                    action_id="commands",
                    label="可用指令",
                    value="/commands",
                    style="primary",
                ),
            ],
        )
