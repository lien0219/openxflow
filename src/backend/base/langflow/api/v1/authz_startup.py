"""Application lifespan hook for idempotent RBAC catalog reconciliation."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from langflow.services.authorization.bootstrap import ensure_authorization_bootstrap
from langflow.services.deps import session_scope


@asynccontextmanager
async def authorization_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Reconcile roles after the main lifespan initializes migrations/services."""
    async with session_scope() as session:
        await ensure_authorization_bootstrap(session)
    yield


router = APIRouter(lifespan=authorization_lifespan)

__all__ = ["authorization_lifespan", "router"]
