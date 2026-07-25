from langflow.channels.services.capabilities import get_provider_capability, validate_provider_conversation_type
from langflow.channels.services.response_policy import normalize_response_mode


def test_provider_capability_matrix_matches_implemented_transports() -> None:
    telegram = get_provider_capability("telegram")
    dingtalk = get_provider_capability("dingtalk")
    wecom = get_provider_capability("wecom")
    assert telegram is not None and telegram.supports_message_update and telegram.supports_threads
    assert dingtalk is not None and dingtalk.supports_streaming_connection
    assert wecom is not None and wecom.conversation_types == ("private",)
    assert validate_provider_conversation_type("wecom", "group") is False


def test_legacy_mentions_only_normalizes_without_database_migration() -> None:
    assert normalize_response_mode("mentions_only") == "mention_only"
    assert normalize_response_mode("mention_only") == "mention_only"
    assert normalize_response_mode("invalid") == "mention_only"
