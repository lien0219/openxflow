"""Thread-safe timing metrics for inbound channel processing."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from threading import Lock

from prometheus_client.core import CounterMetricFamily, HistogramMetricFamily

_DURATION_BUCKETS_SECONDS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
    300.0,
)


@dataclass(frozen=True)
class DurationHistogramSnapshot:
    """Immutable cumulative histogram data suitable for Prometheus exposition."""

    buckets: tuple[tuple[float, int], ...]
    count: int
    sum_seconds: float


@dataclass(frozen=True)
class ChannelTimingMetricSnapshot:
    stream_callbacks_succeeded: int
    stream_callbacks_failed: int
    stream_callback_duration: DurationHistogramSnapshot
    webhook_queue_wait_duration: DurationHistogramSnapshot
    webhook_execution_duration: DurationHistogramSnapshot


@dataclass
class _DurationHistogramState:
    bucket_counts: list[int]
    count: int = 0
    sum_seconds: float = 0.0


class ChannelTimingMetrics:
    """Record bounded-label counters and cumulative duration histograms."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._stream_callbacks_succeeded = 0
        self._stream_callbacks_failed = 0
        self._stream_callback_duration = self._new_histogram()
        self._webhook_queue_wait_duration = self._new_histogram()
        self._webhook_execution_duration = self._new_histogram()

    def record_stream_callback(self, *, success: bool, duration_seconds: float) -> None:
        self._validate_duration(duration_seconds)
        with self._lock:
            if success:
                self._stream_callbacks_succeeded += 1
            else:
                self._stream_callbacks_failed += 1
            self._observe_locked(self._stream_callback_duration, duration_seconds)

    def record_webhook_queue_wait(self, duration_seconds: float) -> None:
        self._validate_duration(duration_seconds)
        with self._lock:
            self._observe_locked(self._webhook_queue_wait_duration, duration_seconds)

    def record_webhook_execution(self, duration_seconds: float) -> None:
        self._validate_duration(duration_seconds)
        with self._lock:
            self._observe_locked(self._webhook_execution_duration, duration_seconds)

    def snapshot(self) -> ChannelTimingMetricSnapshot:
        with self._lock:
            return ChannelTimingMetricSnapshot(
                stream_callbacks_succeeded=self._stream_callbacks_succeeded,
                stream_callbacks_failed=self._stream_callbacks_failed,
                stream_callback_duration=self._snapshot_histogram_locked(self._stream_callback_duration),
                webhook_queue_wait_duration=self._snapshot_histogram_locked(self._webhook_queue_wait_duration),
                webhook_execution_duration=self._snapshot_histogram_locked(self._webhook_execution_duration),
            )

    def reset(self) -> None:
        with self._lock:
            self._stream_callbacks_succeeded = 0
            self._stream_callbacks_failed = 0
            self._stream_callback_duration = self._new_histogram()
            self._webhook_queue_wait_duration = self._new_histogram()
            self._webhook_execution_duration = self._new_histogram()

    @staticmethod
    def _new_histogram() -> _DurationHistogramState:
        return _DurationHistogramState(bucket_counts=[0] * len(_DURATION_BUCKETS_SECONDS))

    @staticmethod
    def _validate_duration(duration_seconds: float) -> None:
        if not math.isfinite(duration_seconds) or duration_seconds < 0:
            raise ValueError("duration_seconds must be finite and non-negative")

    @staticmethod
    def _observe_locked(histogram: _DurationHistogramState, duration_seconds: float) -> None:
        histogram.count += 1
        histogram.sum_seconds += duration_seconds
        for index, upper_bound in enumerate(_DURATION_BUCKETS_SECONDS):
            if duration_seconds <= upper_bound:
                histogram.bucket_counts[index] += 1

    @staticmethod
    def _snapshot_histogram_locked(histogram: _DurationHistogramState) -> DurationHistogramSnapshot:
        return DurationHistogramSnapshot(
            buckets=tuple(zip(_DURATION_BUCKETS_SECONDS, histogram.bucket_counts, strict=True)),
            count=histogram.count,
            sum_seconds=histogram.sum_seconds,
        )


_timing_metrics = ChannelTimingMetrics()


def record_stream_callback(*, success: bool, duration_seconds: float) -> None:
    """Record a completed callback while excluding application-level task cancellation."""
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    if task is not None and task.cancelling():
        return
    _timing_metrics.record_stream_callback(success=success, duration_seconds=duration_seconds)


def record_webhook_queue_wait(duration_seconds: float) -> None:
    _timing_metrics.record_webhook_queue_wait(duration_seconds)


def record_webhook_execution(duration_seconds: float) -> None:
    _timing_metrics.record_webhook_execution(duration_seconds)


def channel_timing_metrics_snapshot() -> ChannelTimingMetricSnapshot:
    return _timing_metrics.snapshot()


def reset_channel_timing_metrics_for_testing() -> None:
    _timing_metrics.reset()


class ChannelTimingMetricsCollector:
    """Expose inbound callback counters and cumulative timing histograms."""

    def collect(self):  # type: ignore[no-untyped-def]
        snapshot = channel_timing_metrics_snapshot()
        for name, description, value in (
            (
                "openxflow_channel_stream_callbacks_succeeded",
                "Successfully processed DingTalk Stream callbacks",
                snapshot.stream_callbacks_succeeded,
            ),
            (
                "openxflow_channel_stream_callbacks_failed",
                "DingTalk Stream callbacks that returned provider-visible errors",
                snapshot.stream_callbacks_failed,
            ),
        ):
            metric = CounterMetricFamily(name, description)
            metric.add_metric([], value)
            yield metric

        yield self._histogram(
            "openxflow_channel_stream_callback_duration_seconds",
            "DingTalk Stream callback processing duration in seconds",
            snapshot.stream_callback_duration,
        )
        yield self._histogram(
            "openxflow_channel_webhook_queue_wait_duration_seconds",
            "HTTP channel webhook wait time before obtaining an execution slot",
            snapshot.webhook_queue_wait_duration,
        )
        yield self._histogram(
            "openxflow_channel_webhook_execution_duration_seconds",
            "HTTP channel webhook execution duration after obtaining a slot",
            snapshot.webhook_execution_duration,
        )

    @staticmethod
    def _histogram(
        name: str,
        description: str,
        snapshot: DurationHistogramSnapshot,
    ) -> HistogramMetricFamily:
        buckets = [(str(upper_bound), count) for upper_bound, count in snapshot.buckets]
        buckets.append(("+Inf", snapshot.count))
        return HistogramMetricFamily(
            name,
            description,
            buckets=buckets,
            sum_value=snapshot.sum_seconds,
        )
