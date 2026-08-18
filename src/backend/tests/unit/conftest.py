"""Shared isolation fixtures for backend unit tests."""

from __future__ import annotations

import time as _stdlib_time

import pytest


class _IsolatedTime:
    """Proxy ``time`` while keeping patched attributes local to one module."""

    sleep = staticmethod(_stdlib_time.sleep)

    def __getattr__(self, name: str) -> object:
        return getattr(_stdlib_time, name)


@pytest.fixture(autouse=True)
def isolate_kb_storage_time_sleep_patch(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep KB storage tests from patching process-global ``time.sleep``.

    ``kb_helpers`` imports the stdlib ``time`` module. Patching
    ``langflow.api.utils.kb_helpers.time.sleep`` therefore mutates the shared
    stdlib module object and can intercept sleeps from background threads in
    the same pytest worker. Give this test module a delegating proxy so its
    existing ``patch(...time.sleep)`` calls stay local to ``kb_helpers``.
    """
    if request.node.path.name == "test_kb_storage_deletion.py":
        from langflow.api.utils import kb_helpers

        monkeypatch.setattr(kb_helpers, "time", _IsolatedTime())
