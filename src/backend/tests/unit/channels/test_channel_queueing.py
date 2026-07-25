from types import SimpleNamespace
from uuid import uuid4

from langflow.channels.services.queueing import resolve_channel_queue_descriptor


class FakeResult:
    def first(self):
        return None


class FakeSession:
    async def exec(self, _statement):
        return FakeResult()


def _event(*, user_id: str, conversation_id: str = "chat-1", conversation_type: str = "group"):
    return SimpleNamespace(
        conversation=SimpleNamespace(
            external_conversation_id=conversation_id,
            conversation_type=conversation_type,
            metadata={},
        ),
        message=SimpleNamespace(metadata={}),
        user=SimpleNamespace(external_user_id=user_id),
    )


async def test_isolated_group_queue_is_member_scoped() -> None:
    connection = SimpleNamespace(id=uuid4(), default_context_mode="isolated")
    first = await resolve_channel_queue_descriptor(FakeSession(), connection, _event(user_id="a"))
    second = await resolve_channel_queue_descriptor(FakeSession(), connection, _event(user_id="b"))
    assert first.queue_key != second.queue_key
    assert first.serialized_by_conversation is False


async def test_shared_group_queue_is_conversation_scoped() -> None:
    connection = SimpleNamespace(id=uuid4(), default_context_mode="shared")
    first = await resolve_channel_queue_descriptor(FakeSession(), connection, _event(user_id="a"))
    second = await resolve_channel_queue_descriptor(FakeSession(), connection, _event(user_id="b"))
    assert first.queue_key == second.queue_key
    assert first.serialized_by_conversation is True


async def test_private_queue_remains_member_scoped_in_shared_default() -> None:
    connection = SimpleNamespace(id=uuid4(), default_context_mode="shared")
    first = await resolve_channel_queue_descriptor(
        FakeSession(),
        connection,
        _event(user_id="a", conversation_type="private"),
    )
    second = await resolve_channel_queue_descriptor(
        FakeSession(),
        connection,
        _event(user_id="b", conversation_type="private"),
    )
    assert first.queue_key != second.queue_key
