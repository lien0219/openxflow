from langflow.channels.domain.models import ChannelAction, ChannelMessage, ChannelMessageType
from langflow.channels.services.message_planning import plan_channel_messages, split_channel_text


def test_split_channel_text_preserves_content_and_limits() -> None:
    value = "第一段。" * 100

    chunks = split_channel_text(value, 80)

    assert len(chunks) > 1
    assert all(len(chunk) <= 80 for chunk in chunks)
    assert "".join(chunks) == value


def test_long_telegram_card_is_split_and_actions_only_appear_on_last_part() -> None:
    message = ChannelMessage(
        message_type=ChannelMessageType.CARD,
        title="结果",
        markdown="段落内容。" * 1000,
        actions=[ChannelAction(action_id="continue", label="继续")],
    )

    planned = plan_channel_messages("telegram", message)

    assert len(planned) > 1
    assert planned[0].title == "结果"
    assert planned[0].actions == []
    assert planned[-1].actions[0].action_id == "continue"
    assert all(part.message_type is ChannelMessageType.MARKDOWN for part in planned)
    assert all(len(part.markdown or "") + len(part.title or "") + (2 if part.title else 0) <= 3900 for part in planned)


def test_title_and_body_are_counted_together() -> None:
    message = ChannelMessage(
        title="T" * 100,
        text="正文。" * 600,
    )

    planned = plan_channel_messages("wecom", message)

    assert len(planned) > 1
    assert all(len(part.text or "") + len(part.title or "") + (2 if part.title else 0) <= 1800 for part in planned)


def test_oversized_action_list_is_capped() -> None:
    message = ChannelMessage(
        text="选择",
        actions=[ChannelAction(action_id=f"action-{index}", label=str(index)) for index in range(10)],
    )

    planned = plan_channel_messages("wecom", message)

    assert len(planned[-1].actions) == 6


def test_short_message_keeps_original_shape() -> None:
    message = ChannelMessage(message_type=ChannelMessageType.CARD, title="标题", text="内容")

    planned = plan_channel_messages("wecom", message)

    assert planned == [message]
