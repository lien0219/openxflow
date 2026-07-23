"""Process-local runtime metrics for durable provider webhook workers."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily


@dataclass(frozen=True)
class DurableWebhookJobMetricSnapshot:
    running_managers: int
    consumer_tasks: int
    pending_jobs: int
    processing_jobs: int
    completed_jobs: int
    failed_jobs: int
    claimed_total: int
    completed_total: int
    retried_total: int
    failed_total: int
    claim_errors_total: int
    cleaned_total: int
    maintenance_errors_total: int


class DurableWebhookJobMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._running_managers = 0
        self._consumer_tasks = 0
        self._pending_jobs = 0
        self._processing_jobs = 0
        self._completed_jobs = 0
        self._failed_jobs = 0
        self._claimed_total = 0
        self._completed_total = 0
        self._retried_total = 0
        self._failed_total = 0
        self._claim_errors_total = 0
        self._cleaned_total = 0
        self._maintenance_errors_total = 0

    def manager_started(self, consumer_tasks: int) -> None:
        if consumer_tasks < 0:
            raise ValueError("consumer_tasks must be non-negative")
        with self._lock:
            self._running_managers += 1
            self._consumer_tasks += consumer_tasks

    def manager_stopped(self, consumer_tasks: int) -> None:
        if consumer_tasks < 0:
            raise ValueError("consumer_tasks must be non-negative")
        with self._lock:
            self._running_managers = max(0, self._running_managers - 1)
            self._consumer_tasks = max(0, self._consumer_tasks - consumer_tasks)

    def set_queue_depths(self, *, pending: int, processing: int, completed: int, failed: int) -> None:
        values = (pending, processing, completed, failed)
        if any(value < 0 for value in values):
            raise ValueError("queue depths must be non-negative")
        with self._lock:
            self._pending_jobs = pending
            self._processing_jobs = processing
            self._completed_jobs = completed
            self._failed_jobs = failed

    def record_claimed(self) -> None:
        with self._lock:
            self._claimed_total += 1

    def record_completed(self) -> None:
        with self._lock:
            self._completed_total += 1

    def record_retried(self) -> None:
        with self._lock:
            self._retried_total += 1

    def record_failed(self) -> None:
        with self._lock:
            self._failed_total += 1

    def record_claim_error(self) -> None:
        with self._lock:
            self._claim_errors_total += 1

    def record_cleaned(self, count: int) -> None:
        if count < 0:
            raise ValueError("count must be non-negative")
        with self._lock:
            self._cleaned_total += count

    def record_maintenance_error(self) -> None:
        with self._lock:
            self._maintenance_errors_total += 1

    def snapshot(self) -> DurableWebhookJobMetricSnapshot:
        with self._lock:
            return DurableWebhookJobMetricSnapshot(
                running_managers=self._running_managers,
                consumer_tasks=self._consumer_tasks,
                pending_jobs=self._pending_jobs,
                processing_jobs=self._processing_jobs,
                completed_jobs=self._completed_jobs,
                failed_jobs=self._failed_jobs,
                claimed_total=self._claimed_total,
                completed_total=self._completed_total,
                retried_total=self._retried_total,
                failed_total=self._failed_total,
                claim_errors_total=self._claim_errors_total,
                cleaned_total=self._cleaned_total,
                maintenance_errors_total=self._maintenance_errors_total,
            )

    def reset(self) -> None:
        with self._lock:
            self._running_managers = 0
            self._consumer_tasks = 0
            self._pending_jobs = 0
            self._processing_jobs = 0
            self._completed_jobs = 0
            self._failed_jobs = 0
            self._claimed_total = 0
            self._completed_total = 0
            self._retried_total = 0
            self._failed_total = 0
            self._claim_errors_total = 0
            self._cleaned_total = 0
            self._maintenance_errors_total = 0


_metrics = DurableWebhookJobMetrics()


def durable_webhook_job_metrics_snapshot() -> DurableWebhookJobMetricSnapshot:
    return _metrics.snapshot()


def reset_durable_webhook_job_metrics_for_testing() -> None:
    _metrics.reset()


def record_durable_webhook_manager_started(consumer_tasks: int) -> None:
    _metrics.manager_started(consumer_tasks)


def record_durable_webhook_manager_stopped(consumer_tasks: int) -> None:
    _metrics.manager_stopped(consumer_tasks)


def set_durable_webhook_queue_depths(*, pending: int, processing: int, completed: int, failed: int) -> None:
    _metrics.set_queue_depths(
        pending=pending,
        processing=processing,
        completed=completed,
        failed=failed,
    )


def record_durable_webhook_claimed() -> None:
    _metrics.record_claimed()


def record_durable_webhook_completed() -> None:
    _metrics.record_completed()


def record_durable_webhook_retried() -> None:
    _metrics.record_retried()


def record_durable_webhook_failed() -> None:
    _metrics.record_failed()


def record_durable_webhook_claim_error() -> None:
    _metrics.record_claim_error()


def record_durable_webhook_cleaned(count: int) -> None:
    _metrics.record_cleaned(count)


def record_durable_webhook_maintenance_error() -> None:
    _metrics.record_maintenance_error()


class DurableWebhookJobMetricsCollector:
    """Expose process-local durable queue worker state through Prometheus."""

    def collect(self):  # type: ignore[no-untyped-def]
        snapshot = durable_webhook_job_metrics_snapshot()
        for name, description, value in (
            (
                "openxflow_channel_webhook_job_running_managers",
                "Durable channel webhook job managers running in this process",
                snapshot.running_managers,
            ),
            (
                "openxflow_channel_webhook_job_consumer_tasks",
                "Durable channel webhook consumer tasks running in this process",
                snapshot.consumer_tasks,
            ),
            (
                "openxflow_channel_webhook_job_pending",
                "Last observed pending durable channel webhook jobs",
                snapshot.pending_jobs,
            ),
            (
                "openxflow_channel_webhook_job_processing",
                "Last observed processing durable channel webhook jobs",
                snapshot.processing_jobs,
            ),
            (
                "openxflow_channel_webhook_job_completed",
                "Last observed retained completed durable channel webhook jobs",
                snapshot.completed_jobs,
            ),
            (
                "openxflow_channel_webhook_job_failed",
                "Last observed retained terminally failed durable channel webhook jobs",
                snapshot.failed_jobs,
            ),
        ):
            metric = GaugeMetricFamily(name, description)
            metric.add_metric([], value)
            yield metric

        for name, description, value in (
            (
                "openxflow_channel_webhook_job_claimed",
                "Durable channel webhook jobs claimed by this process",
                snapshot.claimed_total,
            ),
            (
                "openxflow_channel_webhook_job_completed_total",
                "Durable channel webhook jobs completed by this process",
                snapshot.completed_total,
            ),
            (
                "openxflow_channel_webhook_job_retried",
                "Durable channel webhook jobs returned to pending retry by this process",
                snapshot.retried_total,
            ),
            (
                "openxflow_channel_webhook_job_failed_total",
                "Durable channel webhook jobs marked terminally failed by this process",
                snapshot.failed_total,
            ),
            (
                "openxflow_channel_webhook_job_claim_errors",
                "Durable channel webhook job claim errors in this process",
                snapshot.claim_errors_total,
            ),
            (
                "openxflow_channel_webhook_job_cleaned",
                "Retained durable channel webhook jobs deleted by this process",
                snapshot.cleaned_total,
            ),
            (
                "openxflow_channel_webhook_job_maintenance_errors",
                "Durable channel webhook maintenance errors in this process",
                snapshot.maintenance_errors_total,
            ),
        ):
            metric = CounterMetricFamily(name, description)
            metric.add_metric([], value)
            yield metric
