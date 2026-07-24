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


@dataclass(frozen=True)
class TokenRecoveryMetricSnapshot:
    rejections: dict[str, int]
    refresh_succeeded: dict[str, int]
    refresh_failed: dict[str, int]
    replays: dict[str, int]


class ChannelOutboundMetrics:
    """Thread-safe counters for provider API calls and retry outcomes."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._attempts: dict[tuple[str, str], int] = {}
        self._succeeded: dict[tuple[str, str], int] = {}
        self._retries: dict[tuple[str, str, str], int] = {}
        self._failed: dict[tuple[str, str, str], int] = {}

    def record_attempt(self, operation_name: str) -> None:
        self._increment(self._attempts, split_operation_name(operation_name))

    def record_success(self, operation_name: str) -> None:
        self._increment(self._succeeded, split_operation_name(operation_name))

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


class ChannelTokenRecoveryMetrics:
    """Thread-safe counters for one-shot provider token recovery."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._rejections: dict[str, int] = {}
        self._refresh_succeeded: dict[str, int] = {}
        self._refresh_failed: dict[str, int] = {}
        self._replays: dict[str, int] = {}

    def record_rejection(self, provider: str) -> None:
        self._increment(self._rejections, provider)

    def record_refresh_success(self, provider: str) -> None:
        self._increment(self._refresh_succeeded, provider)

    def record_refresh_failure(self, provider: str) -> None:
        self._increment(self._refresh_failed, provider)

    def record_replay(self, provider: str) -> None:
        self._increment(self._replays, provider)

    def snapshot(self) -> TokenRecoveryMetricSnapshot:
        with self._lock:
            return TokenRecoveryMetricSnapshot(
                rejections=dict(self._rejections),
                refresh_succeeded=dict(self._refresh_succeeded),
                refresh_failed=dict(self._refresh_failed),
                replays=dict(self._replays),
            )

    def reset(self) -> None:
        with self._lock:
            self._rejections.clear()
            self._refresh_succeeded.clear()
            self._refresh_failed.clear()
            self._replays.clear()

    def _increment(self, target: dict[str, int], provider: str) -> None:
        normalized = provider.strip().lower() or "unknown"
        with self._lock:
            target[normalized] = target.get(normalized, 0) + 1


_outbound_metrics = ChannelOutboundMetrics()
_token_recovery_metrics = ChannelTokenRecoveryMetrics()


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


def record_token_rejection(provider: str) -> None:
    _token_recovery_metrics.record_rejection(provider)


def record_token_refresh_success(provider: str) -> None:
    _token_recovery_metrics.record_refresh_success(provider)


def record_token_refresh_failure(provider: str) -> None:
    _token_recovery_metrics.record_refresh_failure(provider)


def record_token_replay(provider: str) -> None:
    _token_recovery_metrics.record_replay(provider)


def token_recovery_metrics_snapshot() -> TokenRecoveryMetricSnapshot:
    return _token_recovery_metrics.snapshot()


def reset_token_recovery_metrics_for_testing() -> None:
    _token_recovery_metrics.reset()


class ChannelMetricsCollector:
    """Expose channel runtime state through the Prometheus collector protocol."""

    def collect(self):  # type: ignore[no-untyped-def]
        from langflow.channels.services.dingtalk_stream import dingtalk_stream_runtime_snapshot
        from langflow.channels.services.webhook_processing import webhook_limiter_snapshot

        stream_runtime = dingtalk_stream_runtime_snapshot()
        for name, description, value in (
            (
                "openxflow_channel_stream_running_managers",
                "Lifecycle-managed channel Stream managers running in this process",
                stream_runtime.running_managers,
            ),
            (
                "openxflow_channel_stream_leader_managers",
                "Channel Stream managers currently holding the process election lock",
                stream_runtime.leader_managers,
            ),
            (
                "openxflow_channel_stream_managed_clients",
                "DingTalk Stream clients currently managed by this process",
                stream_runtime.managed_clients,
            ),
            (
                "openxflow_channel_stream_last_successful_sync_timestamp_seconds",
                "Unix timestamp of the last successful DingTalk Stream connection synchronization",
                stream_runtime.last_successful_sync_timestamp_seconds,
            ),
        ):
            metric = GaugeMetricFamily(name, description)
            metric.add_metric([], value)
            yield metric

        for name, description, value in (
            (
                "openxflow_channel_stream_sync_errors",
                "DingTalk Stream database synchronization failures in this process",
                stream_runtime.sync_errors_total,
            ),
            (
                "openxflow_channel_stream_connection_errors",
                "DingTalk Stream client connection failures in this process",
                stream_runtime.connection_errors_total,
            ),
            (
                "openxflow_channel_stream_reconnect_attempts",
                "DingTalk Stream client attempts after the initial connection attempt",
                stream_runtime.reconnect_attempts_total,
            ),
            (
                "openxflow_channel_stream_successful_syncs",
                "Successful DingTalk Stream database synchronization cycles",
                stream_runtime.successful_sync_total,
            ),
        ):
            metric = CounterMetricFamily(name, description)
            metric.add_metric([], value)
            yield metric

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
            (
                "openxflow_channel_webhook_max_pending",
                "Configured channel webhook pending capacity",
                webhook.max_pending,
            ),
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
            (
                "openxflow_channel_webhook_rejected_pending",
                "Channel webhooks rejected only because the pending-job limit was full",
                webhook.rejected_pending_total,
            ),
            (
                "openxflow_channel_webhook_rejected_bytes",
                "Channel webhooks rejected only because retained payload-byte capacity was full",
                webhook.rejected_bytes_total,
            ),
            (
                "openxflow_channel_webhook_rejected_both",
                "Channel webhooks rejected because both pending-job and payload-byte limits were full",
                webhook.rejected_both_total,
            ),
            ("openxflow_channel_webhook_succeeded", "Successfully processed channel webhooks", webhook.succeeded_total),
            ("openxflow_channel_webhook_failed", "Failed channel webhook background executions", webhook.failed_total),
            (
                "openxflow_channel_webhook_queue_timed_out",
                "Reserved channel webhooks that timed out before obtaining an execution slot",
                webhook.queue_timed_out_total,
            ),
            (
                "openxflow_channel_webhook_cancelled",
                "Reserved channel webhook tasks cancelled by the application runtime",
                webhook.cancelled_total,
            ),
            (
                "openxflow_channel_webhook_client_disconnected",
                "Channel webhook uploads disconnected before the request body completed",
                webhook.client_disconnected_total,
            ),
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

        token_recovery = token_recovery_metrics_snapshot()
        for name, description, values in (
            (
                "openxflow_channel_token_rejections",
                "Provider API responses that explicitly rejected a cached access token",
                token_recovery.rejections,
            ),
            (
                "openxflow_channel_token_refresh_succeeded",
                "Successful provider access-token refreshes after rejection",
                token_recovery.refresh_succeeded,
            ),
            (
                "openxflow_channel_token_refresh_failed",
                "Failed provider access-token refreshes after rejection",
                token_recovery.refresh_failed,
            ),
            (
                "openxflow_channel_token_replays",
                "Provider API requests replayed once after token recovery",
                token_recovery.replays,
            ),
        ):
            metric = CounterMetricFamily(name, description, labels=["provider"])
            for provider, value in sorted(values.items()):
                metric.add_metric([provider], value)
            yield metric
