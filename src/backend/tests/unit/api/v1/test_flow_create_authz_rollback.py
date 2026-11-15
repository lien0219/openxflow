"""Destination races must not expire the authenticated caller used by CREATE."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from langflow.api.v1 import authz_route_dependencies as dependencies
from langflow.services.database.models.flow.model import FlowCreate
from langflow.services.database.models.folder.model import Folder
from langflow.services.database.models.user.model import User


@pytest.mark.parametrize("deny", [False, True])
async def test_create_authorizes_caller_after_destination_rollback(async_session, monkeypatch, deny):
    """A competing default-folder insert rolls back the shared request session."""
    user = User(username="create-authz-rollback", password=uuid4().hex, is_active=True)
    async_session.add(user)
    await async_session.commit()
    user_id = user.id
    folder = Folder(name="Existing project", user_id=user_id)
    async_session.add(folder)
    await async_session.commit()
    folder_id = folder.id
    # Authentication loads the user in the same still-active transaction.
    await async_session.refresh(user)

    async def canonicalize(session, flow, caller_id, **_kwargs):
        assert caller_id == user_id
        # This is the real ORM expiration caused when another request wins
        # get_or_create_default_folder's unique insert race.
        await session.rollback()
        destination = await session.get(Folder, folder_id)
        flow.folder_id = destination.id
        flow.workspace_id = destination.workspace_id
        return flow.workspace_id, flow.folder_id

    async def authorize(caller, _action, **kwargs):
        assert caller.id == user_id
        assert caller.is_active
        assert not caller.is_superuser
        assert kwargs["folder_user_id"] == user_id
        assert kwargs["folder_id"] == folder_id
        if deny:
            raise HTTPException(status_code=403, detail="Denied by authorization plugin")

    guard = AsyncMock(side_effect=authorize)
    monkeypatch.setattr(dependencies, "_canonicalize_flow_destination", canonicalize)
    monkeypatch.setattr(dependencies, "ensure_flow_permission", guard)
    flow = FlowCreate(name="New flow", data={})

    if deny:
        with pytest.raises(HTTPException) as exc:
            await dependencies.require_flow_create_permission(user, flow, async_session)
        assert exc.value.status_code == 403
    else:
        assert await dependencies.require_flow_create_permission(user, flow, async_session) == (None, folder_id)
        # FastAPI passes this same object into the route handler afterwards.
        assert user.id == user_id
    guard.assert_awaited_once()
