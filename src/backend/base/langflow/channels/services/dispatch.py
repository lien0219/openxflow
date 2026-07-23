"""Resolve identities and dispatch normalized channel events to OpenXFlow features."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from lfx.log.logger import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.domain.models import ChannelEvent, ChannelEventType, ChannelMessage
from langflow.channels.services.binding import issue_channel_binding_code, resolve_channel_identity
from langflow.channels.services.files import (
    ChannelFileService,
    list_owned_knowledge_bases,
    resolve_owned_knowledge_base,
)
from langflow.channels.services.workflow import ChannelWorkflowExecutor
from langflow.services.authorization import KnowledgeBaseAction, ensure_knowledge_base_permission
from langflow.services.database.models.channel.model import ChannelConnection, ChannelConversationBinding
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
        binding = await self._get_conversation_binding(event)
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
        if command in {"/bind", "/whoami"}:
            return ChannelMessage(
                title="账号已绑定",
                text=f"当前渠道账号已绑定 OpenXFlow 用户：{user.username}",
            )
        if command == "/knowledge":
            return await self._knowledge_message(user, binding)
        if command == "/use-kb":
            return await self._bind_knowledge_base(event, user, binding, argument)
        if command == "/files":
            return await self._recent_files_message(event, user)
        if command == "/flow":
            flow_identifier, _, input_value = argument.partition(" ")
            if not flow_identifier:
                return ChannelMessage(text="用法：/flow <工作流 ID 或 endpoint_name> [输入内容]")
            return await self._execute_workflow(
                event,
                user,
                flow_identifier,
                input_value or None,
                binding=binding,
            )
        if command == "/run":
            if binding is None or binding.default_flow_id is None:
                return ChannelMessage(text="当前会话尚未绑定默认工作流。可使用 /flow <工作流 ID> [输入内容]。")
            return await self._execute_workflow(
                event,
                user,
                str(binding.default_flow_id),
                argument or None,
                binding=binding,
            )
        if command is not None:
            return ChannelMessage(text="未知命令。发送 /help 查看可用操作。")

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
        if binding is None or binding.default_flow_id is None:
            if binding is not None and binding.knowledge_base_id is not None:
                return ChannelMessage(
                    text=(
                        "当前会话已绑定知识库，但尚未绑定默认问答工作流。"
                        "管理员可在渠道中心绑定工作流，或使用 /flow <工作流 ID> <问题>。"
                    )
                )
            return ChannelMessage(
                text=(
                    "当前会话尚未绑定默认工作流。管理员可在 OpenXFlow 渠道中心完成绑定，"
                    "或使用 /flow <工作流 ID> <问题> 临时运行。"
                )
            )
        return await self._execute_workflow(
            event,
            user,
            str(binding.default_flow_id),
            text,
            binding=binding,
        )

    async def _execute_workflow(
        self,
        event: ChannelEvent,
        user: User,
        flow_identifier: str,
        input_value: str | None,
        *,
        binding: ChannelConversationBinding | None,
    ) -> ChannelMessage:
        try:
            channel_context = await self._build_bound_context(binding)
            return await self.workflow_executor.execute(
                event=event,
                user=user,
                flow_identifier=flow_identifier,
                input_value=input_value,
                channel_context=channel_context,
            )
        except HTTPException as exc:
            if exc.status_code in {403, 404}:
                return ChannelMessage(text="工作流不存在，或当前绑定账号没有执行权限。")
            await logger.aexception("Channel workflow HTTP error for flow %s", flow_identifier)
            return ChannelMessage(text="工作流执行失败，请稍后重试。")
        except Exception:  # noqa: BLE001
            await logger.aexception("Channel workflow execution failed for flow %s", flow_identifier)
            return ChannelMessage(text="工作流执行失败，请在 OpenXFlow 运行记录中查看错误详情。")

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
        binding = await self._get_conversation_binding(event)
        if binding is not None:
            return binding
        binding = ChannelConversationBinding(
            connection_id=event.connection_id,
            external_conversation_id=event.conversation.external_conversation_id,
            conversation_type=event.conversation.conversation_type,
            display_name=event.conversation.title,
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
        current_id = binding.knowledge_base_id if binding else None
        lines = []
        for kb in knowledge_bases[:20]:
            marker = "✅" if kb.id == current_id else "•"
            lines.append(f"{marker} {kb.name}（{kb.status}，{kb.chunks} 个分块）")
        return ChannelMessage(
            title="可用知识库",
            text=("\n".join(lines) + "\n\n使用 /use-kb <知识库名称> 绑定当前会话；使用 /use-kb none 解除绑定。"),
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
            return ChannelMessage(text="用法：/use-kb <知识库名称或 ID>；解除绑定：/use-kb none")

        binding = binding or await self._ensure_conversation_binding(event)
        if normalized.lower() in {"none", "off", "clear"} or normalized in {"取消", "关闭", "解除"}:
            binding.knowledge_base_id = None
            self.session.add(binding)
            await self.session.flush()
            return ChannelMessage(title="知识库已解除", text="当前会话不再自动接收文件到知识库。")

        kb = await resolve_owned_knowledge_base(self.session, user.id, normalized)
        if kb is None:
            return ChannelMessage(text="没有找到该知识库。发送 /knowledge 查看可用名称。")
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
        if binding is None:
            return {}
        context: dict[str, Any] = {
            "conversation_binding_id": str(binding.id),
            "response_mode": binding.response_mode,
            "allow_file_upload": binding.allow_file_upload,
        }
        if binding.knowledge_base_id is not None:
            kb = await self.session.get(KnowledgeBaseRecord, binding.knowledge_base_id)
            context["knowledge_base_id"] = str(binding.knowledge_base_id)
            if kb is not None:
                context["knowledge_base_name"] = kb.name
        return context

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
            title="OpenXFlow 手机操作",
            text=(
                f"{binding_line}"
                "可用命令：\n"
                "/bind — 绑定或查看账号状态\n"
                "/run [内容] — 运行当前会话的默认工作流\n"
                "/flow <工作流 ID 或 endpoint_name> [内容] — 运行指定工作流\n"
                "/knowledge — 查看知识库\n"
                "/use-kb <名称或 ID> — 绑定当前会话知识库\n"
                "/files — 查看当前会话最近文件\n"
                "/whoami — 查看当前绑定账号\n"
                "/help — 查看帮助"
            ),
        )
