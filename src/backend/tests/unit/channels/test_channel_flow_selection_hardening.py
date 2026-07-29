from __future__ import annotations

from types import SimpleNamespace

from langflow.channels.services.dispatch import ChannelDispatchService
from langflow.channels.services.response_policy import ChannelResponseMode


def _group_event(*, mentions=None, text="/help"):
    return SimpleNamespace(
        conversation=SimpleNamespace(conversation_type="group"),
        event_type="message",
        message=SimpleNamespace(mentions=mentions or [], text=text),
    )


def test_group_system_command_can_require_explicit_bot_target() -> None:
    event = _group_event()
    assert ChannelDispatchService._should_ignore_group_event(
        event,
        command="/help",
        response_mode=ChannelResponseMode.MENTION_ONLY.value,
        require_command_mention=True,
        command_targeted=False,
    )
    assert not ChannelDispatchService._should_ignore_group_event(
        event,
        command="/help",
        response_mode=ChannelResponseMode.MENTION_ONLY.value,
        require_command_mention=True,
        command_targeted=True,
    )


def test_telegram_bot_suffix_counts_as_explicit_target() -> None:
    assert ChannelDispatchService._command_targets_bot(_group_event(text="/help@openxflow_bot"))
