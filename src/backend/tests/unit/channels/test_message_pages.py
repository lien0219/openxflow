from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

_BACKEND_ROOT_PARENT_INDEX = 3
_MODULE_PATH = Path(__file__).resolve().parents[_BACKEND_ROOT_PARENT_INDEX] / "base/langflow/api/v1/message_pages.py"
_SPEC = importlib.util.spec_from_file_location("openxflow_message_pages", _MODULE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
get_messages_page = _MODULE.get_messages_page


@pytest.mark.asyncio
async def test_messages_page_returns_server_pagination_metadata() -> None:
    count_result = MagicMock()
    count_result.one.return_value = 0
    rows_result = MagicMock()
    rows_result.all.return_value = []
    session = MagicMock()
    session.exec = AsyncMock(side_effect=[count_result, rows_result])
    current_user = SimpleNamespace(id=uuid4(), is_active=True, is_superuser=False)

    response = await get_messages_page(
        session=session,
        current_user=current_user,
        page=3,
        page_size=20,
        flow_id=None,
        session_id=None,
        sender=None,
        sender_name=None,
        query=None,
        order_by="-timestamp",
    )

    assert response.page == 3
    assert response.page_size == 20
    assert response.total == 0
    assert response.total_pages == 0
    assert response.items == []
