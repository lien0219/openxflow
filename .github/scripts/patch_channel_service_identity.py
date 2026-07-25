from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def patch(path: str, old: str, new: str, *, label: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    if new and new in content:
        return
    if old not in content:
        raise RuntimeError(f"Missing service identity hardening target for {label}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8")


patch(
    "src/backend/base/langflow/api/v1/channels.py",
    "from langflow.services.database.models.user.model import User\n",
    "",
    label="unused user model import",
)
patch(
    "src/backend/base/langflow/api/v1/channels.py",
    """    service_user_id = payload.service_user_id or current_user.id
    if service_user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign another service user")
    service_user = await db.get(User, service_user_id)
    if service_user is None or not service_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Service user is missing or inactive"
        )
    payload.service_user_id = service_user_id
""",
    """    if payload.service_user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Channel service identities are provisioned automatically",
        )
""",
    label="managed create identity",
)
patch(
    "src/backend/base/langflow/api/v1/channels.py",
    """    if payload.service_user_id is not None:
        if payload.service_user_id != current_user.id and not current_user.is_superuser:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign another service user")
        service_user = await db.get(User, payload.service_user_id)
        if service_user is None or not service_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Service user is missing or inactive"
            )
""",
    """    if payload.service_user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Channel service identities are managed automatically and cannot be reassigned",
        )
""",
    label="managed update identity",
)

# The request models retain the optional field for one release so older clients
# receive a precise validation error instead of silently mutating privileges.
