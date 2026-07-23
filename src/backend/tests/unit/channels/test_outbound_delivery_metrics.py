from prometheus_client import CollectorRegistry, generate_latest

from langflow.channels.services.outbound_delivery_metrics import (
    OutboundDeliveryMetricsCollector,
    outbound_delivery_metrics_snapshot,
    record_outbound_delivery_failed,
    record_outbound_delivery_reserved,
    record_outbound_delivery_sent,
    record_outbound_delivery_state_error,
    record_outbound_delivery_suppressed,
    reset_outbound_delivery_metrics_for_testing,
)


def setup_function() -> None:
    reset_outbound_delivery_metrics_for_testing()


def teardown_function() -> None:
    reset_outbound_delivery_metrics_for_testing()


def test_outbound_delivery_metrics_track_guard_outcomes() -> None:
    record_outbound_delivery_reserved()
    record_outbound_delivery_reserved()
    record_outbound_delivery_suppressed()
    record_outbound_delivery_sent()
    record_outbound_delivery_failed()
    record_outbound_delivery_state_error()

    snapshot = outbound_delivery_metrics_snapshot()

    assert snapshot.reserved_total == 2
    assert snapshot.suppressed_total == 1
    assert snapshot.sent_total == 1
    assert snapshot.failed_total == 1
    assert snapshot.state_errors_total == 1


def test_outbound_delivery_metrics_collector_exposes_counters() -> None:
    record_outbound_delivery_reserved()
    record_outbound_delivery_suppressed()
    record_outbound_delivery_sent()

    registry = CollectorRegistry(auto_describe=True)
    registry.register(OutboundDeliveryMetricsCollector())
    rendered = generate_latest(registry).decode()

    assert "openxflow_channel_outbound_delivery_reserved_total 1.0" in rendered
    assert "openxflow_channel_outbound_delivery_suppressed_total 1.0" in rendered
    assert "openxflow_channel_outbound_delivery_sent_total 1.0" in rendered
    assert "openxflow_channel_outbound_delivery_failed_total 0.0" in rendered
    assert "openxflow_channel_outbound_delivery_state_errors_total 0.0" in rendered
