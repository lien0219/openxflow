"""Process-local metrics for durable outbound delivery idempotency."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from langflow.services.database.models.channel.outbound_delivery_model import ChannelOutboundDeliveryKind

_KINDS = tuple(kind.value for kind in ChannelOutboundDeliveryKind)


@dataclass(frozen=True)
class OutboundDeliveryKindMetricSnapshot:
    reserved_total: int
    suppressed_total: int
    sent_total: int
    failed_total: int
    state_errors_total: int
    cleaned_total: int
    retained_reserved: int
    retained_sent: int
    retained_failed: int


@dataclass(frozen=True)
class OutboundDeliveryMetricSnapshot:
    reserved_total: int
    suppressed_total: int
    sent_total: int
    failed_total: int
    state_errors_total: int
    cleaned_total: int
    retained_reserved: int
    retained_sent: int
    retained_failed: int
    by_kind: dict[str, OutboundDeliveryKindMetricSnapshot]


class OutboundDeliveryMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._values = self._new_values()

    @staticmethod
    def _new_values() -> dict[str, dict[str, int]]:
        return {
            kind: {
                "reserved_total": 0,
                "suppressed_total": 0,
                "sent_total": 0,
                "failed_total": 0,
                "state_errors_total": 0,
                "cleaned_total": 0,
                "retained_reserved": 0,
                "retained_sent": 0,
                "retained_failed": 0,
            }
            for kind in _KINDS
        }

    @staticmethod
    def _normalize_kind(delivery_kind: ChannelOutboundDeliveryKind | str) -> str:
        value = (
            delivery_kind.value
            if isinstance(delivery_kind, ChannelOutboundDeliveryKind)
            else delivery_kind
        )
        if value not in _KINDS:
            raise ValueError(f"Unsupported outbound delivery kind: {value}")
        return value

    def record(
        self,
        delivery_kind: ChannelOutboundDeliveryKind | str,
        field: str,
        amount: int = 1,
    ) -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        kind = self._normalize_kind(delivery_kind)
        with self._lock:
            self._values[kind][field] += amount

    def set_retained(
        self,
        delivery_kind: ChannelOutboundDeliveryKind | str,
        *,
        reserved: int,
        sent: int,
        failed: int,
    ) -> None:
        if min(reserved, sent, failed) < 0:
            raise ValueError("retained delivery depths must be non-negative")
        kind = self._normalize_kind(delivery_kind)
        with self._lock:
            self._values[kind]["retained_reserved"] = reserved
            self._values[kind]["retained_sent"] = sent
            self._values[kind]["retained_failed"] = failed

    def snapshot(self) -> OutboundDeliveryMetricSnapshot:
        with self._lock:
            copied = {kind: dict(values) for kind, values in self._values.items()}
        by_kind = {
            kind: OutboundDeliveryKindMetricSnapshot(**values)
            for kind, values in copied.items()
        }
        return OutboundDeliveryMetricSnapshot(
            reserved_total=sum(item.reserved_total for item in by_kind.values()),
            suppressed_total=sum(item.suppressed_total for item in by_kind.values()),
            sent_total=sum(item.sent_total for item in by_kind.values()),
            failed_total=sum(item.failed_total for item in by_kind.values()),
            state_errors_total=sum(item.state_errors_total for item in by_kind.values()),
            cleaned_total=sum(item.cleaned_total for item in by_kind.values()),
            retained_reserved=sum(item.retained_reserved for item in by_kind.values()),
            retained_sent=sum(item.retained_sent for item in by_kind.values()),
            retained_failed=sum(item.retained_failed for item in by_kind.values()),
            by_kind=by_kind,
        )

    def reset(self) -> None:
        with self._lock:
            self._values = self._new_values()


_metrics = OutboundDeliveryMetrics()


def outbound_delivery_metrics_snapshot() -> OutboundDeliveryMetricSnapshot:
    return _metrics.snapshot()


def reset_outbound_delivery_metrics_for_testing() -> None:
    _metrics.reset()


def record_outbound_delivery_reserved(delivery_kind: ChannelOutboundDeliveryKind | str) -> None:
    _metrics.record(delivery_kind, "reserved_total")


def record_outbound_delivery_suppressed(delivery_kind: ChannelOutboundDeliveryKind | str) -> None:
    _metrics.record(delivery_kind, "suppressed_total")


def record_outbound_delivery_sent(delivery_kind: ChannelOutboundDeliveryKind | str) -> None:
    _metrics.record(delivery_kind, "sent_total")


def record_outbound_delivery_failed(delivery_kind: ChannelOutboundDeliveryKind | str) -> None:
    _metrics.record(delivery_kind, "failed_total")


def record_outbound_delivery_state_error(
    delivery_kind: ChannelOutboundDeliveryKind | str,
) -> None:
    _metrics.record(delivery_kind, "state_errors_total")


def record_outbound_delivery_cleaned(
    delivery_kind: ChannelOutboundDeliveryKind | str,
    amount: int,
) -> None:
    _metrics.record(delivery_kind, "cleaned_total", amount)


def set_outbound_delivery_retained_depths(
    delivery_kind: ChannelOutboundDeliveryKind | str,
    *,
    reserved: int,
    sent: int,
    failed: int,
) -> None:
    _metrics.set_retained(
        delivery_kind,
        reserved=reserved,
        sent=sent,
        failed=failed,
    )


class OutboundDeliveryMetricsCollector:
    """Expose durable outbound delivery outcomes through Prometheus."""

    def collect(self):  # type: ignore[no-untyped-def]
        snapshot = outbound_delivery_metrics_snapshot()
        for name, description, field in (
            (
                "openxflow_channel_outbound_delivery_reserved",
                "Durable channel deliveries reserved for provider delivery by this process",
                "reserved_total",
            ),
            (
                "openxflow_channel_outbound_delivery_suppressed",
                "Duplicate durable channel deliveries suppressed by this process",
                "suppressed_total",
            ),
            (
                "openxflow_channel_outbound_delivery_sent",
                "Durable channel deliveries confirmed sent by this process",
                "sent_total",
            ),
            (
                "openxflow_channel_outbound_delivery_failed",
                "Durable channel deliveries with an explicit provider failure in this process",
                "failed_total",
            ),
            (
                "openxflow_channel_outbound_delivery_state_errors",
                "Durable channel delivery receipt state transition errors in this process",
                "state_errors_total",
            ),
            (
                "openxflow_channel_outbound_delivery_cleaned",
                "Expired terminal durable channel delivery receipts removed by this process",
                "cleaned_total",
            ),
        ):
            metric = CounterMetricFamily(name, description, labels=["delivery_kind"])
            for kind in _KINDS:
                metric.add_metric([kind], getattr(snapshot.by_kind[kind], field))
            yield metric

        for name, description, field in (
            (
                "openxflow_channel_outbound_delivery_retained_reserved",
                "Current ambiguous reserved durable delivery receipts in the shared database",
                "retained_reserved",
            ),
            (
                "openxflow_channel_outbound_delivery_retained_sent",
                "Current retained successful durable delivery receipts in the shared database",
                "retained_sent",
            ),
            (
                "openxflow_channel_outbound_delivery_retained_failed",
                "Current retained failed durable delivery receipts in the shared database",
                "retained_failed",
            ),
        ):
            metric = GaugeMetricFamily(name, description, labels=["delivery_kind"])
            for kind in _KINDS:
                metric.add_metric([kind], getattr(snapshot.by_kind[kind], field))
            yield metric
