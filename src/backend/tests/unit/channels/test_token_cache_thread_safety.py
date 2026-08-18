from concurrent.futures import ThreadPoolExecutor

from langflow.channels.services.token_cache import prune_provider_token_cache
from langflow.channels.services.token_cache_metrics import (
    reset_token_cache_metrics_for_testing,
    token_cache_metrics_snapshot,
)


def test_provider_token_cache_pruning_is_thread_safe() -> None:
    reset_token_cache_metrics_for_testing()
    cache = {f"credential-{index}": (f"token-{index}", float(index + 1)) for index in range(1000)}

    def prune(index: int) -> tuple[int, int]:
        return prune_provider_token_cache(
            provider="feishu",
            cache=cache,
            protected_key=f"credential-{index}",
            now=500.0,
            max_entries=64,
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(prune, range(64)))

    assert len(cache) <= 64
    assert all(expired >= 0 and capacity >= 0 for expired, capacity in results)
    snapshot = token_cache_metrics_snapshot()
    assert snapshot.entries["feishu"] == len(cache)
    assert all(value >= 0 for value in snapshot.evictions.values())
