"""Process-local metrics for durable outbound reply idempotency."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from prometheus_client.core import CounterMetricFamily


@dataclass(frozen=True)
class OutboundDeliveryMetricSnapshot:
    reserved_total: int
    suppressed_total: int
    sent_total: int
    failed_total: int
    state_errors_total: int


class OutboundDeliveryMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._reserved_total = 0
        self._suppressed_total = 0
        self._sent_total = 0
        self._failed_total = 0
        self._state_errors_total = 0

    def record_reserved(self) -> None:
        with self._lock:
            self._reserved_total += 1

    def record_suppressed(self) -> None:
        with self._lock:
            self._suppressed_total += 1

    def record_sent(self) -> None:
        with self._lock:
            self._sent_total += 1

    def record_failed(self) -> None:
        with self._lock:
            self._failed_total += 1

    def record_state_error(self) -> None:
        with self._lock:
            self._state_errors_total += 1

    def snapshot(self) -> OutboundDeliveryMetricSnapshot:
        with self._lock:
            return OutboundDeliveryMetricSnapshot(
                reserved_total=self._reserved_total,
                suppressed_total=self._suppressed_total,
                sent_total=self._sent_total,
                failed_total=self._failed_total,
                state_errors_total=self._state_errors_total,
            )

    def reset(self) -> None:
        with self._lock:
            self._reserved_total = 0
            self._suppressed_total = 0
            self._sent_total = 0
            self._failed_total = 0
            self._state_errors_total = 0


_metrics = OutboundDeliveryMetrics()


def outbound_delivery_metrics_snapshot() -> OutboundDeliveryMetricSnapshot:
    return _metrics.snapshot()


def reset_outbound_delivery_metrics_for_testing() -> None:
    _metrics.reset()


def record_outbound_delivery_reserved() -> None:
    _metrics.record_reserved()


def record_outbound_delivery_suppressed() -> None:
    _metrics.record_suppressed()


def record_outbound_delivery_sent() -> None:
    _metrics.record_sent()


def record_outbound_delivery_failed() -> None:
    _metrics.record_failed()


def record_outbound_delivery_state_error() -> None:
    _metrics.record_state_error()


class OutboundDeliveryMetricsCollector:
    """Expose durable outbound delivery outcomes through Prometheus."""

    def collect(self):  # type: ignore[no-untyped-def]
        snapshot = outbound_delivery_metrics_snapshot()
        for name, description, value in (
            (
                "openxflow_channel_outbound_delivery_reserved",
                "Durable channel replies reserved for provider delivery by this process",
                snapshot.reserved_total,
            ),
            (
                "openxflow_channel_outbound_delivery_suppressed",
                "Duplicate durable channel replies suppressed by this process",
                snapshot.suppressed_total,
            ),
            (
                "openxflow_channel_outbound_delivery_sent",
                "Durable channel replies confirmed sent by this process",
                snapshot.sent_total,
            ),
            (
                "openxflow_channel_outbound_delivery_failed",
                "Durable channel replies with an explicit provider failure in this process",
                snapshot.failed_total,
            ),
            (
                "openxflow_channel_outbound_delivery_state_errors",
                "Durable channel reply receipt state transition errors in this process",
                snapshot.state_errors_total,
            ),
        ):
            metric = CounterMetricFamily(name, description)
            metric.add_metric([], value)
            yield metric
