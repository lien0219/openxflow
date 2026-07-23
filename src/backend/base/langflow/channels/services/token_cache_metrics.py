"""Process-local metrics for provider access-token cache behavior."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from prometheus_client.core import CounterMetricFamily


@dataclass(frozen=True)
class TokenCacheMetricSnapshot:
    hits: dict[str, int]
    misses: dict[str, int]
    forced_refreshes: dict[str, int]
    coalesced_refreshes: dict[str, int]
    refresh_succeeded: dict[str, int]
    refresh_failed: dict[str, int]


class ChannelTokenCacheMetrics:
    """Thread-safe bounded-label counters for token-cache outcomes."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._hits: dict[str, int] = {}
        self._misses: dict[str, int] = {}
        self._forced_refreshes: dict[str, int] = {}
        self._coalesced_refreshes: dict[str, int] = {}
        self._refresh_succeeded: dict[str, int] = {}
        self._refresh_failed: dict[str, int] = {}

    def record_hit(self, provider: str) -> None:
        self._increment(self._hits, provider)

    def record_miss(self, provider: str) -> None:
        self._increment(self._misses, provider)

    def record_forced_refresh(self, provider: str) -> None:
        self._increment(self._forced_refreshes, provider)

    def record_coalesced_refresh(self, provider: str) -> None:
        self._increment(self._coalesced_refreshes, provider)

    def record_refresh_success(self, provider: str) -> None:
        self._increment(self._refresh_succeeded, provider)

    def record_refresh_failure(self, provider: str) -> None:
        self._increment(self._refresh_failed, provider)

    def snapshot(self) -> TokenCacheMetricSnapshot:
        with self._lock:
            return TokenCacheMetricSnapshot(
                hits=dict(self._hits),
                misses=dict(self._misses),
                forced_refreshes=dict(self._forced_refreshes),
                coalesced_refreshes=dict(self._coalesced_refreshes),
                refresh_succeeded=dict(self._refresh_succeeded),
                refresh_failed=dict(self._refresh_failed),
            )

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._misses.clear()
            self._forced_refreshes.clear()
            self._coalesced_refreshes.clear()
            self._refresh_succeeded.clear()
            self._refresh_failed.clear()

    def _increment(self, target: dict[str, int], provider: str) -> None:
        normalized = provider.strip().lower() or "unknown"
        with self._lock:
            target[normalized] = target.get(normalized, 0) + 1


_token_cache_metrics = ChannelTokenCacheMetrics()


def record_token_cache_hit(provider: str) -> None:
    _token_cache_metrics.record_hit(provider)


def record_token_cache_miss(provider: str) -> None:
    _token_cache_metrics.record_miss(provider)


def record_token_cache_forced_refresh(provider: str) -> None:
    _token_cache_metrics.record_forced_refresh(provider)


def record_token_cache_coalesced_refresh(provider: str) -> None:
    _token_cache_metrics.record_coalesced_refresh(provider)


def record_token_cache_refresh_success(provider: str) -> None:
    _token_cache_metrics.record_refresh_success(provider)


def record_token_cache_refresh_failure(provider: str) -> None:
    _token_cache_metrics.record_refresh_failure(provider)


def token_cache_metrics_snapshot() -> TokenCacheMetricSnapshot:
    return _token_cache_metrics.snapshot()


def reset_token_cache_metrics_for_testing() -> None:
    _token_cache_metrics.reset()


class TokenCacheMetricsCollector:
    """Expose token-cache counters through the Prometheus collector protocol."""

    def collect(self):  # type: ignore[no-untyped-def]
        snapshot = token_cache_metrics_snapshot()
        for name, description, values in (
            (
                "openxflow_channel_token_cache_hits",
                "Valid provider access tokens served directly from the process cache",
                snapshot.hits,
            ),
            (
                "openxflow_channel_token_cache_misses",
                "Provider token requests that did not find a valid initial cache entry",
                snapshot.misses,
            ),
            (
                "openxflow_channel_token_cache_forced_refreshes",
                "Explicit provider token refresh requests",
                snapshot.forced_refreshes,
            ),
            (
                "openxflow_channel_token_cache_coalesced_refreshes",
                "Token refresh requests satisfied by another concurrent refresh",
                snapshot.coalesced_refreshes,
            ),
            (
                "openxflow_channel_token_cache_refresh_succeeded",
                "Provider token endpoint requests that refreshed the cache successfully",
                snapshot.refresh_succeeded,
            ),
            (
                "openxflow_channel_token_cache_refresh_failed",
                "Provider token endpoint requests that failed while refreshing the cache",
                snapshot.refresh_failed,
            ),
        ):
            metric = CounterMetricFamily(name, description, labels=["provider"])
            for provider, value in sorted(values.items()):
                metric.add_metric([provider], value)
            yield metric
