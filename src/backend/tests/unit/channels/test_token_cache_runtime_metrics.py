import pytest

from langflow.api.v1.channel_runtime import read_channel_prometheus_metrics
from langflow.channels.services.token_cache_metrics import (
    record_token_cache_entries,
    reset_token_cache_metrics_for_testing,
)


@pytest.mark.asyncio
async def test_channel_metrics_expose_token_cache_entry_gauge() -> None:
    reset_token_cache_metrics_for_testing()
    record_token_cache_entries("feishu", 3)

    response = await read_channel_prometheus_metrics(object())

    assert b"openxflow_channel_token_cache_entries" in response.body
    assert b'openxflow_channel_token_cache_entries{provider="feishu"} 3.0' in response.body
