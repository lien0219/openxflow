from prometheus_client import CollectorRegistry, generate_latest

from langflow.channels.services.metrics import (
    ChannelMetricsCollector,
    outbound_metrics_snapshot,
    record_outbound_attempt,
    record_outbound_failure,
    record_outbound_retry,
    record_outbound_success,
    record_token_rejection,
    record_token_refresh_failure,
    record_token_refresh_success,
    record_token_replay,
    reset_outbound_metrics_for_testing,
    reset_token_recovery_metrics_for_testing,
    token_recovery_metrics_snapshot,
)


def setup_function() -> None:
    reset_outbound_metrics_for_testing()
    reset_token_recovery_metrics_for_testing()


def teardown_function() -> None:
    reset_outbound_metrics_for_testing()
    reset_token_recovery_metrics_for_testing()


def test_outbound_metric_snapshot_groups_by_channel_and_operation() -> None:
    record_outbound_attempt("telegram.send_message")
    record_outbound_attempt("telegram.send_message")
    record_outbound_retry("telegram.send_message", "http_429")
    record_outbound_success("telegram.send_message")
    record_outbound_failure("feishu.send_response", "http_503")

    snapshot = outbound_metrics_snapshot()
    assert snapshot.attempts[("telegram", "send_message")] == 2
    assert snapshot.retries[("telegram", "send_message", "http_429")] == 1
    assert snapshot.succeeded[("telegram", "send_message")] == 1
    assert snapshot.failed[("feishu", "send_response", "http_503")] == 1


def test_token_recovery_snapshot_groups_by_provider() -> None:
    record_token_rejection("WeCom")
    record_token_refresh_success("wecom")
    record_token_refresh_failure("feishu")
    record_token_replay("wecom")

    snapshot = token_recovery_metrics_snapshot()
    assert snapshot.rejections["wecom"] == 1
    assert snapshot.refresh_succeeded["wecom"] == 1
    assert snapshot.refresh_failed["feishu"] == 1
    assert snapshot.replays["wecom"] == 1


def test_channel_prometheus_collector_exposes_runtime_metrics() -> None:
    record_outbound_attempt("telegram.send_message")
    record_outbound_retry("telegram.send_message", "http_429")
    record_token_rejection("dingtalk")
    record_token_refresh_success("dingtalk")
    record_token_replay("dingtalk")

    registry = CollectorRegistry(auto_describe=True)
    registry.register(ChannelMetricsCollector())
    rendered = generate_latest(registry).decode()

    assert "openxflow_channel_webhook_pending" in rendered
    assert 'openxflow_channel_outbound_attempts_total{channel="telegram",operation="send_message"} 1.0' in rendered
    assert (
        'openxflow_channel_outbound_retries_total{channel="telegram",operation="send_message",reason="http_429"} 1.0'
        in rendered
    )
    assert 'openxflow_channel_token_rejections_total{provider="dingtalk"} 1.0' in rendered
    assert 'openxflow_channel_token_refresh_succeeded_total{provider="dingtalk"} 1.0' in rendered
    assert 'openxflow_channel_token_replays_total{provider="dingtalk"} 1.0' in rendered
