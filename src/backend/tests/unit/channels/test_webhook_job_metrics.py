from prometheus_client import CollectorRegistry, generate_latest

from langflow.channels.services.webhook_job_metrics import (
    DurableWebhookJobMetricsCollector,
    durable_webhook_job_metrics_snapshot,
    record_durable_webhook_claim_error,
    record_durable_webhook_claimed,
    record_durable_webhook_completed,
    record_durable_webhook_failed,
    record_durable_webhook_manager_started,
    record_durable_webhook_manager_stopped,
    record_durable_webhook_retried,
    reset_durable_webhook_job_metrics_for_testing,
)


def setup_function() -> None:
    reset_durable_webhook_job_metrics_for_testing()


def teardown_function() -> None:
    reset_durable_webhook_job_metrics_for_testing()


def test_durable_webhook_job_metrics_track_lifecycle_and_outcomes() -> None:
    record_durable_webhook_manager_started(4)
    record_durable_webhook_claimed()
    record_durable_webhook_completed()
    record_durable_webhook_retried()
    record_durable_webhook_failed()
    record_durable_webhook_claim_error()

    running = durable_webhook_job_metrics_snapshot()
    assert running.running_managers == 1
    assert running.consumer_tasks == 4
    assert running.claimed_total == 1
    assert running.completed_total == 1
    assert running.retried_total == 1
    assert running.failed_total == 1
    assert running.claim_errors_total == 1

    record_durable_webhook_manager_stopped(4)
    stopped = durable_webhook_job_metrics_snapshot()
    assert stopped.running_managers == 0
    assert stopped.consumer_tasks == 0
    assert stopped.completed_total == 1


def test_durable_webhook_job_metrics_collector_exposes_gauges_and_counters() -> None:
    record_durable_webhook_manager_started(2)
    record_durable_webhook_claimed()
    record_durable_webhook_completed()

    registry = CollectorRegistry(auto_describe=True)
    registry.register(DurableWebhookJobMetricsCollector())
    rendered = generate_latest(registry).decode()

    assert "openxflow_channel_webhook_job_running_managers 1.0" in rendered
    assert "openxflow_channel_webhook_job_consumer_tasks 2.0" in rendered
    assert "openxflow_channel_webhook_job_claimed_total 1.0" in rendered
    assert "openxflow_channel_webhook_job_completed_total 1.0" in rendered
    assert "openxflow_channel_webhook_job_retried_total 0.0" in rendered
    assert "openxflow_channel_webhook_job_failed_total 0.0" in rendered
    assert "openxflow_channel_webhook_job_claim_errors_total 0.0" in rendered
