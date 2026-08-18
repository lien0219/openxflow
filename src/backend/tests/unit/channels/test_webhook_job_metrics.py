from langflow.channels.services.webhook_job_metrics import (
    DurableWebhookJobMetricsCollector,
    durable_webhook_job_metrics_snapshot,
    record_durable_webhook_claim_error,
    record_durable_webhook_claimed,
    record_durable_webhook_cleaned,
    record_durable_webhook_completed,
    record_durable_webhook_failed,
    record_durable_webhook_maintenance_error,
    record_durable_webhook_manager_started,
    record_durable_webhook_manager_stopped,
    record_durable_webhook_retried,
    reset_durable_webhook_job_metrics_for_testing,
    set_durable_webhook_queue_depths,
)
from prometheus_client import CollectorRegistry, generate_latest


def setup_function() -> None:
    reset_durable_webhook_job_metrics_for_testing()


def teardown_function() -> None:
    reset_durable_webhook_job_metrics_for_testing()


def test_durable_webhook_job_metrics_track_lifecycle_and_outcomes() -> None:
    record_durable_webhook_manager_started(4)
    set_durable_webhook_queue_depths(pending=5, processing=2, completed=10, failed=3)
    record_durable_webhook_claimed()
    record_durable_webhook_completed()
    record_durable_webhook_retried()
    record_durable_webhook_failed()
    record_durable_webhook_claim_error()
    record_durable_webhook_cleaned(7)
    record_durable_webhook_maintenance_error()

    running = durable_webhook_job_metrics_snapshot()
    assert running.running_managers == 1
    assert running.consumer_tasks == 4
    assert running.pending_jobs == 5
    assert running.processing_jobs == 2
    assert running.completed_jobs == 10
    assert running.failed_jobs == 3
    assert running.claimed_total == 1
    assert running.completed_total == 1
    assert running.retried_total == 1
    assert running.failed_total == 1
    assert running.claim_errors_total == 1
    assert running.cleaned_total == 7
    assert running.maintenance_errors_total == 1

    record_durable_webhook_manager_stopped(4)
    stopped = durable_webhook_job_metrics_snapshot()
    assert stopped.running_managers == 0
    assert stopped.consumer_tasks == 0
    assert stopped.completed_total == 1
    assert stopped.pending_jobs == 5


def test_durable_webhook_job_metrics_collector_exposes_gauges_and_counters() -> None:
    record_durable_webhook_manager_started(2)
    set_durable_webhook_queue_depths(pending=4, processing=1, completed=8, failed=2)
    record_durable_webhook_claimed()
    record_durable_webhook_completed()
    record_durable_webhook_cleaned(3)

    registry = CollectorRegistry(auto_describe=True)
    registry.register(DurableWebhookJobMetricsCollector())
    rendered = generate_latest(registry).decode()

    assert "openxflow_channel_webhook_job_running_managers 1.0" in rendered
    assert "openxflow_channel_webhook_job_consumer_tasks 2.0" in rendered
    assert "openxflow_channel_webhook_job_pending 4.0" in rendered
    assert "openxflow_channel_webhook_job_processing 1.0" in rendered
    assert "openxflow_channel_webhook_job_completed_retained 8.0" in rendered
    assert "openxflow_channel_webhook_job_failed_retained 2.0" in rendered
    assert "openxflow_channel_webhook_job_claimed_total 1.0" in rendered
    assert "openxflow_channel_webhook_job_completed_total 1.0" in rendered
    assert "openxflow_channel_webhook_job_retried_total 0.0" in rendered
    assert "openxflow_channel_webhook_job_failed_total 0.0" in rendered
    assert "openxflow_channel_webhook_job_claim_errors_total 0.0" in rendered
    assert "openxflow_channel_webhook_job_cleaned_total 3.0" in rendered
    assert "openxflow_channel_webhook_job_maintenance_errors_total 0.0" in rendered
