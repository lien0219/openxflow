from langflow.channels.services.runtime_config import (
    DEFAULT_CHANNEL_STREAMS_ENABLED,
    DEFAULT_WEBHOOK_MAX_BODY_BYTES,
    DEFAULT_WEBHOOK_MAX_CONCURRENCY,
    DEFAULT_WEBHOOK_MAX_PENDING,
    DEFAULT_WEBHOOK_MAX_PENDING_BYTES,
    DEFAULT_WEBHOOK_TASK_TIMEOUT_SECONDS,
    channel_streams_enabled,
    webhook_limiter_limits_from_env,
    webhook_max_body_bytes,
    webhook_task_timeout_seconds,
)


def test_channel_runtime_config_defaults(monkeypatch) -> None:
    for name in (
        "LANGFLOW_CHANNEL_STREAMS_ENABLED",
        "LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY",
        "LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING",
        "LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING_BYTES",
        "LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES",
        "LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    limits = webhook_limiter_limits_from_env()

    assert channel_streams_enabled() is DEFAULT_CHANNEL_STREAMS_ENABLED
    assert limits.max_concurrency == DEFAULT_WEBHOOK_MAX_CONCURRENCY
    assert limits.max_pending == DEFAULT_WEBHOOK_MAX_PENDING
    assert limits.max_pending_bytes == DEFAULT_WEBHOOK_MAX_PENDING_BYTES
    assert webhook_max_body_bytes() == DEFAULT_WEBHOOK_MAX_BODY_BYTES
    assert webhook_task_timeout_seconds() == DEFAULT_WEBHOOK_TASK_TIMEOUT_SECONDS


def test_channel_runtime_config_accepts_valid_overrides(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_STREAMS_ENABLED", "off")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY", "7")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING", "21")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING_BYTES", "4096")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES", "1024")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS", "12.5")

    limits = webhook_limiter_limits_from_env()

    assert channel_streams_enabled() is False
    assert limits.max_concurrency == 7
    assert limits.max_pending == 21
    assert limits.max_pending_bytes == 4096
    assert webhook_max_body_bytes() == 1024
    assert webhook_task_timeout_seconds() == 12.5


def test_channel_stream_boolean_values(monkeypatch) -> None:
    for value in ("1", "true", "TRUE", "yes", "on", " On "):
        monkeypatch.setenv("LANGFLOW_CHANNEL_STREAMS_ENABLED", value)
        assert channel_streams_enabled() is True

    for value in ("0", "false", "FALSE", "no", "off", " Off "):
        monkeypatch.setenv("LANGFLOW_CHANNEL_STREAMS_ENABLED", value)
        assert channel_streams_enabled() is False


def test_invalid_channel_stream_boolean_falls_back(monkeypatch) -> None:
    for value in ("", "enabled", "disabled", "2", "invalid"):
        monkeypatch.setenv("LANGFLOW_CHANNEL_STREAMS_ENABLED", value)
        assert channel_streams_enabled() is DEFAULT_CHANNEL_STREAMS_ENABLED


def test_webhook_runtime_config_clamps_pending_to_concurrency(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY", "8")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING", "2")

    limits = webhook_limiter_limits_from_env()

    assert limits.max_concurrency == 8
    assert limits.max_pending == 8


def test_webhook_runtime_config_invalid_integer_values_fall_back(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY", "invalid")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING", "0")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING_BYTES", "-1")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES", "")

    limits = webhook_limiter_limits_from_env()

    assert limits.max_concurrency == DEFAULT_WEBHOOK_MAX_CONCURRENCY
    assert limits.max_pending == DEFAULT_WEBHOOK_MAX_PENDING
    assert limits.max_pending_bytes == DEFAULT_WEBHOOK_MAX_PENDING_BYTES
    assert webhook_max_body_bytes() == DEFAULT_WEBHOOK_MAX_BODY_BYTES


def test_webhook_runtime_config_non_finite_timeout_falls_back(monkeypatch) -> None:
    for value in ("nan", "inf", "-inf", "0", "-1", "invalid"):
        monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS", value)
        assert webhook_task_timeout_seconds() == DEFAULT_WEBHOOK_TASK_TIMEOUT_SECONDS
