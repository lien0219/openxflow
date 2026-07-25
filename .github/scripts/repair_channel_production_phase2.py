from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE2_SCRIPT = ROOT / ".github/scripts/apply_channel_production_phase2.py"


def replace_once(content: str, old: str, new: str, *, label: str) -> str:
    if old not in content:
        raise RuntimeError(f"Missing repair target for {label}")
    return content.replace(old, new, 1)


def replace_between(content: str, start: str, end: str, replacement: str, *, label: str) -> str:
    start_index = content.find(start)
    end_index = content.find(end, start_index)
    if start_index < 0 or end_index < 0:
        raise RuntimeError(f"Unable to locate repair block for {label}")
    return content[:start_index] + replacement + content[end_index:]


def prepare_phase2_script() -> None:
    content = PHASE2_SCRIPT.read_text(encoding="utf-8")
    marker_replacements = {
        '"    def _resolve_default_flow_id(\\n"': '"    def _resolve_default_flow_id("',
        '"    async def _send_processing_message(\\n"': '"    async def _send_processing_message("',
    }
    for old, new in marker_replacements.items():
        if old in content:
            content = content.replace(old, new, 1)

    for name in (
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
    ):
        for quote in ("'''", '\"\"\"'):
            old = f"{name} = {quote}"
            new = f"{name} = r{quote}"
            if old in content:
                content = content.replace(old, new, 1)
                break

    PHASE2_SCRIPT.write_text(content, encoding="utf-8")


def apply_phase2_script() -> None:
    subprocess.run([sys.executable, str(PHASE2_SCRIPT)], cwd=ROOT, check=True)


def repair_access_control() -> None:
    path = ROOT / "src/backend/base/langflow/channels/services/access_control.py"
    content = path.read_text(encoding="utf-8")
    replacement = '''async def resolve_execution_principal(
    session: AsyncSession,
    connection: ChannelConnection,
    binding: ChannelConversationBinding | None,
    identity: ChannelIdentity | None,
    *,
    requires_personal: bool = False,
) -> ChannelExecutionPrincipal:
    """Resolve the least-privileged principal for one channel route.

    Access policy decides whether binding is required. The route type decides
    which principal executes it: shared routes always use the configured service
    identity, while personal routes use the bound member identity.
    """
    policy = effective_access_policy(connection, binding)
    bound_user = await bound_identity_user(session, identity)

    if policy == ChannelAccessPolicy.BOUND_ONLY.value and bound_user is None:
        raise ChannelBindingRequiredError

    if requires_personal:
        if bound_user is None:
            raise ChannelBindingRequiredError
        return ChannelExecutionPrincipal(
            user=bound_user,
            identity_type=ChannelExecutionIdentityType.BOUND_USER.value,
            identity=identity,
        )

    service_user_id = connection.service_user_id
    if service_user_id is None:
        raise ChannelServiceIdentityUnavailableError
    service_user = await session.get(User, service_user_id)
    if service_user is None or not service_user.is_active:
        raise ChannelServiceIdentityUnavailableError
    return ChannelExecutionPrincipal(
        user=service_user,
        identity_type=ChannelExecutionIdentityType.SERVICE.value,
        identity=identity,
    )
'''
    content = replace_between(
        content,
        "async def resolve_execution_principal(\n",
        "\n",
        replacement,
        label="access principal",
    ) if False else content
    start = content.find("async def resolve_execution_principal(\n")
    if start < 0:
        raise RuntimeError("Unable to locate access principal function")
    content = content[:start] + replacement
    path.write_text(content, encoding="utf-8")


def repair_dispatch() -> None:
    path = ROOT / "src/backend/base/langflow/channels/services/dispatch.py"
    content = path.read_text(encoding="utf-8")
    if "import inspect\n" not in content:
        content = replace_once(content, "import asyncio\n", "import asyncio\nimport inspect\n", label="inspect import")

    identity_block = '''        if bound_user is not None:
            event.user.openxflow_user_id = bound_user.id

        access_policy = effective_access_policy(self.connection, binding)
        personal_user_id = (
            bound_user.id
            if bound_user is not None and access_policy != "shared"
            else None
        )

'''
    content = replace_once(
        content,
        '''        if bound_user is not None:
            event.user.openxflow_user_id = bound_user.id

''',
        identity_block,
        label="dispatch access policy",
    )
    content = content.replace(
        "return await self._commands_message(bound_user.id if bound_user else None, binding)",
        '''if access_policy == "bound_only" and bound_user is None:
                return await self._binding_required_message(event)
            return await self._commands_message(personal_user_id, binding)''',
        1,
    )
    content = content.replace(
        "return await self._unknown_command_message(bound_user.id if bound_user else None, binding, command)",
        "return await self._unknown_command_message(personal_user_id, binding, command)",
        1,
    )

    content = replace_once(
        content,
        '''        command = await resolve_workflow_command(
            self.session,
''',
        '''        command_user_id = (
            bound_user.id
            if bound_user is not None and effective_access_policy(self.connection, binding) != "shared"
            else None
        )
        command = await resolve_workflow_command(
            self.session,
''',
        label="command policy",
    )
    content = content.replace(
        "            user_id=bound_user.id if bound_user else None,",
        "            user_id=command_user_id,",
        1,
    )

    execute_block = '''    async def _execute_workflow(
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
                    "Unable to update processing message %s; falling back to a new response",
                    processing_message_id,
                )
        return response

'''
    content = replace_between(
        content,
        "    async def _execute_workflow(\n",
        "    async def _send_processing_message(\n",
        execute_block,
        label="workflow execution",
    )
    path.write_text(content, encoding="utf-8")


def write_principal_tests() -> None:
    path = ROOT / "src/backend/tests/unit/channels/test_channel_access_principals.py"
    path.write_text(
        '''from types import SimpleNamespace
from uuid import uuid4

import pytest

from langflow.channels.services.access_control import (
    ChannelBindingRequiredError,
    ChannelServiceIdentityUnavailableError,
    resolve_execution_principal,
)
from langflow.services.database.models.channel.execution_model import ChannelExecutionIdentityType


class FakeSession:
    def __init__(self, users):
        self.users = users

    async def get(self, _model, user_id):
        return self.users.get(user_id)


def _user(user_id, *, active=True):
    return SimpleNamespace(id=user_id, is_active=active)


def _identity(user_id=None):
    return SimpleNamespace(
        status="bound" if user_id else "discovered",
        openxflow_user_id=user_id,
    )


async def test_shared_route_requires_explicit_service_identity() -> None:
    owner_id = uuid4()
    connection = SimpleNamespace(
        user_id=owner_id,
        service_user_id=None,
        access_policy="hybrid",
    )
    with pytest.raises(ChannelServiceIdentityUnavailableError):
        await resolve_execution_principal(FakeSession({owner_id: _user(owner_id)}), connection, None, None)


async def test_bound_only_gates_member_but_shared_route_uses_service_identity() -> None:
    service_id = uuid4()
    member_id = uuid4()
    connection = SimpleNamespace(
        user_id=uuid4(),
        service_user_id=service_id,
        access_policy="bound_only",
    )
    users = {service_id: _user(service_id), member_id: _user(member_id)}
    principal = await resolve_execution_principal(
        FakeSession(users),
        connection,
        None,
        _identity(member_id),
    )
    assert principal.user.id == service_id
    assert principal.identity_type == ChannelExecutionIdentityType.SERVICE.value


async def test_bound_only_rejects_unbound_member_before_shared_execution() -> None:
    service_id = uuid4()
    connection = SimpleNamespace(
        user_id=uuid4(),
        service_user_id=service_id,
        access_policy="bound_only",
    )
    with pytest.raises(ChannelBindingRequiredError):
        await resolve_execution_principal(
            FakeSession({service_id: _user(service_id)}),
            connection,
            None,
            _identity(),
        )


async def test_hybrid_personal_route_uses_bound_member_identity() -> None:
    service_id = uuid4()
    member_id = uuid4()
    connection = SimpleNamespace(
        user_id=uuid4(),
        service_user_id=service_id,
        access_policy="hybrid",
    )
    users = {service_id: _user(service_id), member_id: _user(member_id)}
    principal = await resolve_execution_principal(
        FakeSession(users),
        connection,
        None,
        _identity(member_id),
        requires_personal=True,
    )
    assert principal.user.id == member_id
    assert principal.identity_type == ChannelExecutionIdentityType.BOUND_USER.value
''',
        encoding="utf-8",
    )


def main() -> None:
    prepare_phase2_script()
    apply_phase2_script()
    repair_access_control()
    repair_dispatch()
    write_principal_tests()
    print("Repaired and applied channel production phase 2")


if __name__ == "__main__":
    main()
