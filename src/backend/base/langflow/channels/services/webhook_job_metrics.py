"""Process-local runtime metrics for durable provider webhook workers."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class DurableWebhookJobMetricSnapshot:
    running_managers: int
    consumer_tasks: int
    claimed_total: int
    completed_total: int
    retried_total: int
    failed_total: int
    claim_errors_total: int


class DurableWebhookJobMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._running_managers = 0
        self._consumer_tasks = 0
        self._claimed_total = 0
        self._completed_total = 0
        self._retried_total = 0
        self._failed_total = 0
        self._claim_errors_total = 0

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

    def snapshot(self) -> DurableWebhookJobMetricSnapshot:
        with self._lock:
            return DurableWebhookJobMetricSnapshot(
                running_managers=self._running_managers,
                consumer_tasks=self._consumer_tasks,
                claimed_total=self._claimed_total,
                completed_total=self._completed_total,
                retried_total=self._retried_total,
                failed_total=self._failed_total,
                claim_errors_total=self._claim_errors_total,
            )

    def reset(self) -> None:
        with self._lock:
            self._running_managers = 0
            self._consumer_tasks = 0
            self._claimed_total = 0
            self._completed_total = 0
            self._retried_total = 0
            self._failed_total = 0
            self._claim_errors_total = 0


_metrics = DurableWebhookJobMetrics()


def durable_webhook_job_metrics_snapshot() -> DurableWebhookJobMetricSnapshot:
    return _metrics.snapshot()


def reset_durable_webhook_job_metrics_for_testing() -> None:
    _metrics.reset()


def record_durable_webhook_manager_started(consumer_tasks: int) -> None:
    _metrics.manager_started(consumer_tasks)


def record_durable_webhook_manager_stopped(consumer_tasks: int) -> None:
    _metrics.manager_stopped(consumer_tasks)


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
