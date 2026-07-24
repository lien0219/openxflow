import math

import pytest
from langflow.channels.services.timing_metrics import (
    ChannelTimingMetricsCollector,
    channel_timing_metrics_snapshot,
    record_stream_callback,
    record_webhook_execution,
    record_webhook_queue_wait,
    reset_channel_timing_metrics_for_testing,
)
from prometheus_client import CollectorRegistry, generate_latest


def setup_function() -> None:
    reset_channel_timing_metrics_for_testing()


def teardown_function() -> None:
    reset_channel_timing_metrics_for_testing()


def test_timing_snapshot_uses_cumulative_histogram_buckets() -> None:
    record_stream_callback(success=True, duration_seconds=0.1)
    record_stream_callback(success=False, duration_seconds=2.0)
    record_webhook_queue_wait(0.02)
    record_webhook_execution(3.0)

    snapshot = channel_timing_metrics_snapshot()

    assert snapshot.stream_callbacks_succeeded == 1
    assert snapshot.stream_callbacks_failed == 1
    assert snapshot.stream_callback_duration.count == 2
    assert snapshot.stream_callback_duration.sum_seconds == pytest.approx(2.1)
    assert dict(snapshot.stream_callback_duration.buckets)[0.1] == 1
    assert dict(snapshot.stream_callback_duration.buckets)[2.5] == 2
    assert snapshot.webhook_queue_wait_duration.count == 1
    assert snapshot.webhook_execution_duration.count == 1


@pytest.mark.parametrize("duration", [-1.0, math.nan, math.inf, -math.inf])
def test_timing_metrics_reject_invalid_durations(duration: float) -> None:
    with pytest.raises(ValueError, match="duration_seconds"):
        record_webhook_queue_wait(duration)


def test_timing_collector_exposes_counters_and_histograms() -> None:
    record_stream_callback(success=True, duration_seconds=0.25)
    record_stream_callback(success=False, duration_seconds=0.5)
    record_webhook_queue_wait(0.01)
    record_webhook_execution(1.5)

    registry = CollectorRegistry(auto_describe=True)
    registry.register(ChannelTimingMetricsCollector())
    rendered = generate_latest(registry).decode()

    assert "openxflow_channel_stream_callbacks_succeeded_total 1.0" in rendered
    assert "openxflow_channel_stream_callbacks_failed_total 1.0" in rendered
    assert 'openxflow_channel_stream_callback_duration_seconds_bucket{le="+Inf"} 2.0' in rendered
    assert "openxflow_channel_stream_callback_duration_seconds_count 2.0" in rendered
    assert "openxflow_channel_stream_callback_duration_seconds_sum 0.75" in rendered
    assert "openxflow_channel_webhook_queue_wait_duration_seconds_count 1.0" in rendered
    assert "openxflow_channel_webhook_execution_duration_seconds_count 1.0" in rendered
