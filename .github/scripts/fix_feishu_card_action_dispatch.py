from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DISPATCH = ROOT / "src/backend/base/langflow/channels/services/dispatch.py"
WEBHOOKS = ROOT / "src/backend/base/langflow/api/v1/channel_webhooks.py"
TEST_DISPATCH = ROOT / "src/backend/tests/unit/channels/test_dispatch.py"
TEST_WEBHOOKS = ROOT / "src/backend/tests/unit/channels/test_channel_webhook_api.py"
WORKFLOW = ROOT / ".github/workflows/fix-feishu-card-action-dispatch.yml"
SCRIPT = Path(__file__).resolve()


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} block, found {count}")
    return text.replace(old, new, 1)


dispatch = DISPATCH.read_text(encoding="utf-8")
dispatch = replace_once(
    dispatch,
    """        binding = await discover_channel_conversation(self.session, self.connection, event)\n        if binding is None:\n            binding = await self._get_conversation_binding(event)\n""",
    """        if event.event_type == ChannelEventType.ACTION:\n            binding = await self._get_conversation_binding(event)\n            if binding is not None:\n                event.conversation.conversation_type = binding.conversation_type\n                if not event.conversation.title and binding.display_name:\n                    event.conversation.title = binding.display_name\n            else:\n                binding = await discover_channel_conversation(self.session, self.connection, event)\n        else:\n            binding = await discover_channel_conversation(self.session, self.connection, event)\n            if binding is None:\n                binding = await self._get_conversation_binding(event)\n""",
    label="dispatch conversation resolution",
)
dispatch = replace_once(
    dispatch,
    """    def _command_targets_bot(event: ChannelEvent) -> bool:\n        if event.message.mentions:\n            return True\n""",
    """    def _command_targets_bot(event: ChannelEvent) -> bool:\n        if event.event_type == ChannelEventType.ACTION:\n            return True\n        if event.message.mentions:\n            return True\n""",
    label="command target detection",
)
DISPATCH.write_text(dispatch, encoding="utf-8")

webhooks = WEBHOOKS.read_text(encoding="utf-8")
webhooks = replace_once(
    webhooks,
    "from typing import Annotated\n",
    "from typing import Annotated, Any\n",
    label="typing import",
)
webhooks = replace_once(
    webhooks,
    "from langflow.channels.adapters.wecom_ai import WeComAIBotChannelAdapter\n",
    "from langflow.channels.adapters.wecom_ai import WeComAIBotChannelAdapter\nfrom langflow.channels.domain.models import ChannelEvent, ChannelEventType, ChannelType\n",
    label="channel domain import",
)
webhooks = replace_once(
    webhooks,
    """def _request_headers(\n    request: Request,\n    provider_headers: dict[str, str] | None = None,\n) -> dict[str, str]:\n    headers = {key.lower(): value for key, value in request.headers.items()}\n    headers.update({key.lower(): value for key, value in (provider_headers or {}).items()})\n    return headers\n\n\nasync def _validate_and_schedule_provider_event(\n""",
    """def _request_headers(\n    request: Request,\n    provider_headers: dict[str, str] | None = None,\n) -> dict[str, str]:\n    headers = {key.lower(): value for key, value in request.headers.items()}\n    headers.update({key.lower(): value for key, value in (provider_headers or {}).items()})\n    return headers\n\n\ndef _provider_callback_response(event: ChannelEvent) -> dict[str, Any]:\n    if event.channel == ChannelType.FEISHU and event.event_type == ChannelEventType.ACTION:\n        return {\n            \"toast\": {\n                \"type\": \"info\",\n                \"content\": \"操作已提交，请稍候…\",\n                \"i18n\": {\n                    \"zh_cn\": \"操作已提交，请稍候…\",\n                    \"en_us\": \"Action submitted. Please wait…\",\n                },\n            }\n        }\n    return {\"ok\": True}\n\n\nasync def _validate_and_schedule_provider_event(\n""",
    label="callback response helper insertion",
)
webhooks = webhooks.replace(
    ") -> dict[str, bool]:\n    connection = await db.get", ") -> dict[str, Any]:\n    connection = await db.get", 1
)
webhooks = replace_once(
    webhooks,
    """        return {\"ok\": True}\n\n    reservation = reserve_provider_webhook_slot(len(payload))\n""",
    """        return _provider_callback_response(event)\n\n    reservation = reserve_provider_webhook_slot(len(payload))\n""",
    label="durable callback response",
)
webhooks = replace_once(
    webhooks,
    """    return {\"ok\": True}\n\n\n@router.post(\"/telegram/{connection_id}\", status_code=status.HTTP_200_OK)\n""",
    """    return _provider_callback_response(event)\n\n\n@router.post(\"/telegram/{connection_id}\", status_code=status.HTTP_200_OK)\n""",
    label="background callback response",
)
webhooks = webhooks.replace(
    ") -> dict[str, bool | str]:\n    connection = await db.get",
    ") -> dict[str, Any]:\n    connection = await db.get",
    1,
)
WEBHOOKS.write_text(webhooks, encoding="utf-8")

test_dispatch = TEST_DISPATCH.read_text(encoding="utf-8")
anchor = """def test_group_command_is_never_filtered() -> None:\n    event = _event(text=\"/help\", conversation_type=\"group\")\n    command, _ = ChannelDispatchService._parse_command(event.message.text)\n    assert ChannelDispatchService._should_ignore_group_event(event, command=command) is False\n\n\n"""
addition = (
    anchor
    + """def test_card_action_command_is_explicitly_targeted_to_bot() -> None:\n    event = _event(\n        text=\"/use-flow /deepseek\",\n        conversation_type=\"group\",\n        event_type=ChannelEventType.ACTION,\n    )\n    command, _ = ChannelDispatchService._parse_command(event.message.text)\n    targeted = ChannelDispatchService._command_targets_bot(event)\n\n    assert targeted is True\n    assert (\n        ChannelDispatchService._should_ignore_group_event(\n            event,\n            command=command,\n            response_mode=\"mention_only\",\n            require_command_mention=True,\n            command_targeted=targeted,\n        )\n        is False\n    )\n\n\n"""
)
test_dispatch = replace_once(test_dispatch, anchor, addition, label="dispatch action test anchor")
TEST_DISPATCH.write_text(test_dispatch, encoding="utf-8")

test_webhooks = TEST_WEBHOOKS.read_text(encoding="utf-8")
test_webhooks = replace_once(
    test_webhooks,
    "from langflow.api.v1.channel_webhooks import _validate_and_schedule_provider_event\n",
    "from langflow.api.v1.channel_webhooks import _provider_callback_response, _validate_and_schedule_provider_event\n",
    label="webhook test import",
)
insert_before = (
    """@pytest.fixture(autouse=True)\ndef disable_durable_webhook_jobs(monkeypatch: pytest.MonkeyPatch) -> None:\n"""
)
new_test = (
    """def test_feishu_card_action_callback_returns_immediate_toast() -> None:\n    event = SimpleNamespace(channel=ChannelType.FEISHU, event_type=ChannelEventType.ACTION)\n\n    assert _provider_callback_response(event) == {\n        \"toast\": {\n            \"type\": \"info\",\n            \"content\": \"操作已提交，请稍候…\",\n            \"i18n\": {\n                \"zh_cn\": \"操作已提交，请稍候…\",\n                \"en_us\": \"Action submitted. Please wait…\",\n            },\n        }\n    }\n\n\n"""
    + insert_before
)
test_webhooks = replace_once(test_webhooks, insert_before, new_test, label="webhook toast test anchor")
TEST_WEBHOOKS.write_text(test_webhooks, encoding="utf-8")

WORKFLOW.unlink(missing_ok=True)
SCRIPT.unlink(missing_ok=True)
