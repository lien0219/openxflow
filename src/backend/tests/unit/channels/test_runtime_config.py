from langflow.channels.services.runtime_config import (
    DEFAULT_CHANNEL_STREAMS_ENABLED,
    DEFAULT_WEBHOOK_DURABLE_ENABLED,
    DEFAULT_WEBHOOK_JOB_LEASE_SECONDS,
    DEFAULT_WEBHOOK_JOB_MAX_ATTEMPTS,
    DEFAULT_WEBHOOK_JOB_POLL_SECONDS,
    DEFAULT_WEBHOOK_JOB_RETRY_BASE_SECONDS,
    DEFAULT_WEBHOOK_JOB_RETRY_MAX_SECONDS,
    DEFAULT_WEBHOOK_JOB_WORKERS,
    DEFAULT_WEBHOOK_MAX_BODY_BYTES,
    DEFAULT_WEBHOOK_MAX_CONCURRENCY,
    DEFAULT_WEBHOOK_MAX_PENDING,
    DEFAULT_WEBHOOK_MAX_PENDING_BYTES,
    DEFAULT_WEBHOOK_QUEUE_TIMEOUT_SECONDS,
    DEFAULT_WEBHOOK_TASK_TIMEOUT_SECONDS,
    channel_streams_enabled,
    durable_webhook_job_config,
    webhook_limiter_limits_from_env,
    webhook_max_body_bytes,
    webhook_queue_timeout_seconds,
    webhook_task_timeout_seconds,
)


def test_channel_runtime_config_defaults(monkeypatch) -> None:
    for name in (
        "LANGFLOW_CHANNEL_STREAMS_ENABLED",
        "LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY",
        "LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING",
        "LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING_BYTES",
        "LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES",
        "LANGFLOW_CHANNEL_WEBHOOK_QUEUE_TIMEOUT_SECONDS",
        "LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS",
        "LANGFLOW_CHANNEL_WEBHOOK_DURABLE_ENABLED",
        "LANGFLOW_CHANNEL_WEBHOOK_JOB_WORKERS",
        "LANGFLOW_CHANNEL_WEBHOOK_JOB_POLL_SECONDS",
        "LANGFLOW_CHANNEL_WEBHOOK_JOB_LEASE_SECONDS",
        "LANGFLOW_CHANNEL_WEBHOOK_JOB_MAX_ATTEMPTS",
        "LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_BASE_SECONDS",
        "LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_MAX_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    limits = webhook_limiter_limits_from_env()
    durable = durable_webhook_job_config()

    assert channel_streams_enabled() is DEFAULT_CHANNEL_STREAMS_ENABLED
    assert limits.max_concurrency == DEFAULT_WEBHOOK_MAX_CONCURRENCY
    assert limits.max_pending == DEFAULT_WEBHOOK_MAX_PENDING
    assert limits.max_pending_bytes == DEFAULT_WEBHOOK_MAX_PENDING_BYTES
    assert webhook_max_body_bytes() == DEFAULT_WEBHOOK_MAX_BODY_BYTES
    assert webhook_queue_timeout_seconds() == DEFAULT_WEBHOOK_QUEUE_TIMEOUT_SECONDS
    assert webhook_task_timeout_seconds() == DEFAULT_WEBHOOK_TASK_TIMEOUT_SECONDS
    assert durable.enabled is DEFAULT_WEBHOOK_DURABLE_ENABLED
    assert durable.worker_count == DEFAULT_WEBHOOK_JOB_WORKERS
    assert durable.poll_seconds == DEFAULT_WEBHOOK_JOB_POLL_SECONDS
    assert durable.lease_seconds == DEFAULT_WEBHOOK_JOB_LEASE_SECONDS
    assert durable.max_attempts == DEFAULT_WEBHOOK_JOB_MAX_ATTEMPTS
    assert durable.retry_base_seconds == DEFAULT_WEBHOOK_JOB_RETRY_BASE_SECONDS
    assert durable.retry_max_seconds == DEFAULT_WEBHOOK_JOB_RETRY_MAX_SECONDS


def test_channel_runtime_config_accepts_valid_overrides(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_STREAMS_ENABLED", "off")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY", "7")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING", "21")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING_BYTES", "4096")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES", "1024")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_QUEUE_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_DURABLE_ENABLED", "false")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_WORKERS", "3")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_POLL_SECONDS", "0.25")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_LEASE_SECONDS", "45")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_MAX_ATTEMPTS", "9")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_BASE_SECONDS", "3")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_MAX_SECONDS", "90")

    limits = webhook_limiter_limits_from_env()
    durable = durable_webhook_job_config()

    assert channel_streams_enabled() is False
    assert limits.max_concurrency == 7
    assert limits.max_pending == 21
    assert limits.max_pending_bytes == 4096
    assert webhook_max_body_bytes() == 1024
    assert webhook_queue_timeout_seconds() == 3.5
    assert webhook_task_timeout_seconds() == 12.5
    assert durable.enabled is False
    assert durable.worker_count == 3
    assert durable.poll_seconds == 0.25
    assert durable.lease_seconds == 45
    assert durable.max_attempts == 9
    assert durable.retry_base_seconds == 3
    assert durable.retry_max_seconds == 90


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


def test_durable_webhook_worker_count_is_clamped_to_concurrency(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY", "3")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_WORKERS", "99")

    durable = durable_webhook_job_config()

    assert durable.worker_count == 3


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


def test_webhook_queue_timeout_zero_disables_and_invalid_values_fall_back(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_QUEUE_TIMEOUT_SECONDS", "0")
    assert webhook_queue_timeout_seconds() == 0.0

    for value in ("nan", "inf", "-inf", "-1", "invalid"):
        monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_QUEUE_TIMEOUT_SECONDS", value)
        assert webhook_queue_timeout_seconds() == DEFAULT_WEBHOOK_QUEUE_TIMEOUT_SECONDS


def test_webhook_runtime_config_non_finite_execution_timeout_falls_back(monkeypatch) -> None:
    for value in ("nan", "inf", "-inf", "0", "-1", "invalid"):
        monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS", value)
        assert webhook_task_timeout_seconds() == DEFAULT_WEBHOOK_TASK_TIMEOUT_SECONDS


def test_durable_webhook_config_invalid_values_fall_back_and_clamp(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_DURABLE_ENABLED", "invalid")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_WORKERS", "0")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_POLL_SECONDS", "0")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_LEASE_SECONDS", "nan")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_MAX_ATTEMPTS", "-1")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_BASE_SECONDS", "10")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_MAX_SECONDS", "2")

    durable = durable_webhook_job_config()

    assert durable.enabled is DEFAULT_WEBHOOK_DURABLE_ENABLED
    assert durable.worker_count == DEFAULT_WEBHOOK_JOB_WORKERS
    assert durable.poll_seconds == DEFAULT_WEBHOOK_JOB_POLL_SECONDS
    assert durable.lease_seconds == DEFAULT_WEBHOOK_JOB_LEASE_SECONDS
    assert durable.max_attempts == DEFAULT_WEBHOOK_JOB_MAX_ATTEMPTS
    assert durable.retry_base_seconds == 10
    assert durable.retry_max_seconds == 10
