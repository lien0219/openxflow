"""Application startup hook for idempotent RBAC catalog reconciliation."""

from fastapi import APIRouter

from langflow.services.authorization.bootstrap import ensure_authorization_bootstrap
from langflow.services.deps import session_scope

router = APIRouter()


@router.on_event("startup")
async def bootstrap_authorization_catalog() -> None:
    """Create system roles and reconcile legacy users before serving requests."""
    async with session_scope() as session:
        await ensure_authorization_bootstrap(session)


__all__ = ["bootstrap_authorization_catalog", "router"]
