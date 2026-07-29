from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from langflow.api.v1 import authz_startup


@pytest.mark.asyncio
async def test_authorization_lifespan_reconciles_catalog_before_serving(monkeypatch) -> None:
    events: list[object] = []
    fake_session = object()

    @asynccontextmanager
    async def fake_session_scope():
        events.append("session-open")
        yield fake_session
        events.append("session-close")

    async def fake_bootstrap(session) -> None:
        assert session is fake_session
        events.append("bootstrap")

    monkeypatch.setattr(authz_startup, "session_scope", fake_session_scope)
    monkeypatch.setattr(authz_startup, "ensure_authorization_bootstrap", fake_bootstrap)

    async with authz_startup.authorization_lifespan(None):
        events.append("serving")

    assert events == ["session-open", "bootstrap", "serving", "session-close"]
