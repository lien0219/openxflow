"""Resolve identities and dispatch normalized channel events to OpenXFlow features."""

from __future__ import annotations

from fastapi import HTTPException
from lfx.log.logger import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.domain.models import ChannelEvent, ChannelEventType, ChannelMessage
from langflow.channels.services.binding import issue_channel_binding_code, resolve_channel_identity
from langflow.channels.services.workflow import ChannelWorkflowExecutor
from langflow.services.database.models.channel.model import ChannelConnection, ChannelConversationBinding
from langflow.services.database.models.user.model import User


class ChannelDispatchService:
    """Application-level handler shared by provider webhook transports."""

    def __init__(
        self,
        session: AsyncSession,
        connection: ChannelConnection,
        *,
        workflow_executor: ChannelWorkflowExecutor | None = None,
    ) -> None:
        self.session = session
        self.connection = connection
        self.workflow_executor = workflow_executor or ChannelWorkflowExecutor()

    async def handle(self, event: ChannelEvent) -> ChannelMessage | None:
        if self._should_ignore_group_event(event):
            return None

        identity = await resolve_channel_identity(self.session, event)
        if identity is None:
            return await self._binding_required_message(event)

        event.user.openxflow_user_id = identity.openxflow_user_id
        user = await self.session.get(User, identity.openxflow_user_id)
        if user is None or not user.is_active:
            return ChannelMessage(text="绑定的 OpenXFlow 账号不存在或已停用，请联系管理员。")

        command, argument = self._parse_command(event.message.text)
        if command in {"/start", "/help"}:
            return self._help_message(bound=True)
        if command in {"/bind", "/whoami"}:
            return ChannelMessage(
                title="账号已绑定",
                text=f"当前渠道账号已绑定 OpenXFlow 用户：{user.username}",
            )

        binding = await self._get_conversation_binding(event)
        if event.message.attachments:
            return ChannelMessage(
                title="文件已收到",
                text=(
                    "当前会话尚未配置文件分析入口。请在 OpenXFlow 渠道中心为该会话绑定知识库或文件处理工作流。"
                ),
            )

        if command == "/flow":
            flow_identifier, _, input_value = argument.partition(" ")
            if not flow_identifier:
                return ChannelMessage(text="用法：/flow <工作流 ID 或 endpoint_name> [输入内容]")
            return await self._execute_workflow(event, user, flow_identifier, input_value or None)

        if command == "/run":
            if binding is None or binding.default_flow_id is None:
                return ChannelMessage(text="当前会话尚未绑定默认工作流。可使用 /flow <工作流 ID> [输入内容]。")
            return await self._execute_workflow(event, user, str(binding.default_flow_id), argument or None)

        if command is not None:
            return ChannelMessage(text="未知命令。发送 /help 查看可用操作。")

        text = (event.message.text or "").strip()
        if not text:
            return None
        if binding is None or binding.default_flow_id is None:
            return ChannelMessage(
                text=(
                    "当前会话尚未绑定默认工作流。管理员可在 OpenXFlow 渠道中心完成绑定，"
                    "或使用 /flow <工作流 ID> <问题> 临时运行。"
                )
            )
        return await self._execute_workflow(event, user, str(binding.default_flow_id), text)

    async def _execute_workflow(
        self,
        event: ChannelEvent,
        user: User,
        flow_identifier: str,
        input_value: str | None,
    ) -> ChannelMessage:
        try:
            return await self.workflow_executor.execute(
                event=event,
                user=user,
                flow_identifier=flow_identifier,
                input_value=input_value,
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

    @staticmethod
    def _parse_command(text: str | None) -> tuple[str | None, str]:
        normalized = (text or "").strip()
        if not normalized.startswith("/"):
            return None, normalized
        token, _, argument = normalized.partition(" ")
        command = token.split("@", 1)[0].lower()
        return command, argument.strip()

    @staticmethod
    def _should_ignore_group_event(event: ChannelEvent) -> bool:
        return (
            event.conversation.conversation_type != "private"
            and event.event_type == ChannelEventType.TEXT
            and not event.message.mentions
        )

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
                "/whoami — 查看当前绑定账号\n"
                "/help — 查看帮助"
            ),
        )
