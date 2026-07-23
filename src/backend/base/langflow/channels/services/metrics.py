"""In-process metrics for the unified channel gateway."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily


@dataclass(frozen=True)
class OutboundMetricSnapshot:
    attempts: dict[tuple[str, str], int]
    succeeded: dict[tuple[str, str], int]
    retries: dict[tuple[str, str, str], int]
    failed: dict[tuple[str, str, str], int]


class ChannelOutboundMetrics:
    """Thread-safe counters for provider API calls and retry outcomes."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._attempts: dict[tuple[str, str], int] = {}
        self._succeeded: dict[tuple[str, str], int] = {}
        self._retries: dict[tuple[str, str, str], int] = {}
        self._failed: dict[tuple[str, str, str], int] = {}

    def record_attempt(self, operation_name: str) -> None:
        key = split_operation_name(operation_name)
        self._increment(self._attempts, key)

    def record_success(self, operation_name: str) -> None:
        key = split_operation_name(operation_name)
        self._increment(self._succeeded, key)

    def record_retry(self, operation_name: str, reason: str) -> None:
        channel, operation = split_operation_name(operation_name)
        self._increment(self._retries, (channel, operation, reason))

    def record_failure(self, operation_name: str, reason: str) -> None:
        channel, operation = split_operation_name(operation_name)
        self._increment(self._failed, (channel, operation, reason))

    def snapshot(self) -> OutboundMetricSnapshot:
        with self._lock:
            return OutboundMetricSnapshot(
                attempts=dict(self._attempts),
                succeeded=dict(self._succeeded),
                retries=dict(self._retries),
                failed=dict(self._failed),
            )

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()
            self._succeeded.clear()
            self._retries.clear()
            self._failed.clear()

    def _increment(self, target: dict, key: tuple[str, ...]) -> None:
        with self._lock:
            target[key] = target.get(key, 0) + 1


_outbound_metrics = ChannelOutboundMetrics()


def split_operation_name(operation_name: str) -> tuple[str, str]:
    channel, separator, operation = operation_name.partition(".")
    if not separator:
        return "unknown", operation_name or "unknown"
    return channel or "unknown", operation or "unknown"


def record_outbound_attempt(operation_name: str) -> None:
    _outbound_metrics.record_attempt(operation_name)


def record_outbound_success(operation_name: str) -> None:
    _outbound_metrics.record_success(operation_name)


def record_outbound_retry(operation_name: str, reason: str) -> None:
    _outbound_metrics.record_retry(operation_name, reason)


def record_outbound_failure(operation_name: str, reason: str) -> None:
    _outbound_metrics.record_failure(operation_name, reason)


def outbound_metrics_snapshot() -> OutboundMetricSnapshot:
    return _outbound_metrics.snapshot()


def reset_outbound_metrics_for_testing() -> None:
    _outbound_metrics.reset()


class ChannelMetricsCollector:
    """Expose channel runtime state through the Prometheus collector protocol."""

    def collect(self):  # type: ignore[no-untyped-def]
        from langflow.channels.services.webhook_processing import webhook_limiter_snapshot

        webhook = webhook_limiter_snapshot()
        for name, description, value in (
            ("openxflow_channel_webhook_pending", "Accepted channel webhooks not yet completed", webhook.pending),
            ("openxflow_channel_webhook_active", "Channel webhooks currently executing", webhook.active),
            ("openxflow_channel_webhook_queued", "Channel webhooks waiting for execution", webhook.queued),
            (
                "openxflow_channel_webhook_pending_bytes",
                "Retained payload bytes for accepted channel webhooks",
                webhook.pending_bytes,
            ),
            ("openxflow_channel_webhook_max_pending", "Configured channel webhook pending capacity", webhook.max_pending),
            (
                "openxflow_channel_webhook_max_pending_bytes",
                "Configured retained channel webhook payload-byte capacity",
                webhook.max_pending_bytes,
            ),
            (
                "openxflow_channel_webhook_max_concurrency",
                "Configured channel webhook execution concurrency",
                webhook.max_concurrency,
            ),
        ):
            metric = GaugeMetricFamily(name, description)
            metric.add_metric([], value)
            yield metric
        for name, description, value in (
            ("openxflow_channel_webhook_accepted", "Accepted channel webhook callbacks", webhook.accepted_total),
            ("openxflow_channel_webhook_rejected", "Rejected channel webhook callbacks", webhook.rejected_total),
            ("openxflow_channel_webhook_succeeded", "Successfully processed channel webhooks", webhook.succeeded_total),
            ("openxflow_channel_webhook_failed", "Failed channel webhook background executions", webhook.failed_total),
        ):
            metric = CounterMetricFamily(name, description)
            metric.add_metric([], value)
            yield metric

        outbound = outbound_metrics_snapshot()
        attempts = CounterMetricFamily(
            "openxflow_channel_outbound_attempts",
            "Channel provider API call attempts",
            labels=["channel", "operation"],
        )
        for (channel, operation), value in sorted(outbound.attempts.items()):
            attempts.add_metric([channel, operation], value)
        yield attempts

        succeeded = CounterMetricFamily(
            "openxflow_channel_outbound_succeeded",
            "Successful channel provider operations",
            labels=["channel", "operation"],
        )
        for (channel, operation), value in sorted(outbound.succeeded.items()):
            succeeded.add_metric([channel, operation], value)
        yield succeeded

        retries = CounterMetricFamily(
            "openxflow_channel_outbound_retries",
            "Retried channel provider operations",
            labels=["channel", "operation", "reason"],
        )
        for (channel, operation, reason), value in sorted(outbound.retries.items()):
            retries.add_metric([channel, operation, reason], value)
        yield retries

        failed = CounterMetricFamily(
            "openxflow_channel_outbound_failed",
            "Channel provider operations that exhausted retries or failed permanently",
            labels=["channel", "operation", "reason"],
        )
        for (channel, operation, reason), value in sorted(outbound.failed.items()):
            failed.add_metric([channel, operation, reason], value)
        yield failed
