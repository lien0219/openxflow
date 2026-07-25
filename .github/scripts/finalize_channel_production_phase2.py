from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from textwrap import dedent, indent

ROOT = Path(__file__).resolve().parents[2]
PHASE2_SCRIPT = ROOT / ".github/scripts/apply_channel_production_phase2.py"


def patch_generator() -> None:
    content = PHASE2_SCRIPT.read_text(encoding="utf-8")
    replacements = {
        '"    def _resolve_default_flow_id(\\n"': '"    def _resolve_default_flow_id("',
        '"    async def _send_processing_message(\\n"': '"    async def _send_processing_message("',
    }
    for old, new in replacements.items():
        if old not in content:
            raise RuntimeError(f"Missing generator boundary marker: {old}")
        content = content.replace(old, new, 1)

    generated_blocks = (
        "access_control",
        "context_service",
        "binding",
        "workflow",
        "execution_logs",
        "handle_block",
        "custom_block",
        "commands_block",
        "unknown_block",
        "execute_block",
        "context_block",
        "policy_test",
    )
    for name in generated_blocks:
        for quote in ("'''", '"""'):
            old = f"{name} = {quote}"
            if old in content:
                content = content.replace(old, f"{name} = r{quote}", 1)
                break
    PHASE2_SCRIPT.write_text(content, encoding="utf-8")


def replace_block(path: Path, pattern: str, replacement: str, label: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, content, count=1)
    if count != 1:
        raise RuntimeError(f"Unable to replace {label} in {path}")
    path.write_text(updated, encoding="utf-8")


def harden_access_control() -> None:
    path = ROOT / "src/backend/base/langflow/channels/services/access_control.py"
    replacement = dedent(
        """\
        def effective_access_policy(
            connection: ChannelConnection,
            binding: ChannelConversationBinding | None,
        ) -> str:
            binding_policy = getattr(binding, "access_policy", ChannelAccessPolicy.INHERIT.value)
            if binding is not None and binding_policy != ChannelAccessPolicy.INHERIT.value:
                return binding_policy
            return getattr(connection, "access_policy", ChannelAccessPolicy.HYBRID.value)


        def effective_context_mode(
            connection: ChannelConnection,
            binding: ChannelConversationBinding | None,
        ) -> str:
            binding_mode = getattr(binding, "context_mode", ChannelContextMode.INHERIT.value)
            if binding is not None and binding_mode != ChannelContextMode.INHERIT.value:
                return binding_mode
            return getattr(connection, "default_context_mode", ChannelContextMode.ISOLATED.value)


        """
    )
    replace_block(
        path,
        r"def effective_access_policy\([\s\S]*?(?=async def bound_identity_user)",
        replacement,
        "effective access/context policy functions",
    )


def harden_dispatch() -> None:
    path = ROOT / "src/backend/base/langflow/channels/services/dispatch.py"
    content = path.read_text(encoding="utf-8")
    if "import inspect\n" not in content:
        content = content.replace("import asyncio\n", "import asyncio\nimport inspect\n", 1)
    path.write_text(content, encoding="utf-8")

    method = dedent(
        """\
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
        ) -> ChannelMessage | None:
            context_mode = effective_context_mode(self.connection, binding)
            session_id = build_channel_session_id(event, context_mode)
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
                        openxflow_user_id=principal.user.id,
                        external_user_id=event.user.external_user_id,
                        session_id=session_id,
                        execution_identity_type=principal.identity_type,
                        flow_id=flow_id,
                        external_event_id=event.event_id,
                        trigger_type=trigger_type,
                        command_name=command_name,
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
                        "execution_identity_type": principal.identity_type,
                    }
                )
                if command_name:
                    channel_context["command_name"] = command_name

                executor_kwargs: dict[str, Any] = {
                    "event": event,
                    "user": principal.user,
                    "flow_identifier": flow_identifier,
                    "input_value": prepared_input,
                    "channel_context": channel_context,
                }
                executor_parameters = inspect.signature(self.workflow_executor.execute).parameters
                if "session_id" in executor_parameters:
                    executor_kwargs["session_id"] = session_id
                if "execution_identity_type" in executor_parameters:
                    executor_kwargs["execution_identity_type"] = principal.identity_type
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

        """
    )
    replace_block(
        path,
        r"    async def _execute_workflow\([\s\S]*?(?=    async def _send_processing_message\()",
        indent(method, "    "),
        "workflow execution method",
    )


def main() -> None:
    patch_generator()
    subprocess.run([sys.executable, str(PHASE2_SCRIPT)], cwd=ROOT, check=True)
    harden_access_control()
    harden_dispatch()
    print("Phase 2 runtime generated and hardened successfully")


if __name__ == "__main__":
    main()
