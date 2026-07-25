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
    '''    service_user_id = payload.service_user_id or current_user.id
    if service_user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign another service user")
    service_user = await db.get(User, service_user_id)
    if service_user is None or not service_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Service user is missing or inactive"
        )
    payload.service_user_id = service_user_id
''',
    '''    if payload.service_user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Channel service identities are provisioned automatically",
        )
''',
    label="managed create identity",
)
patch(
    "src/backend/base/langflow/api/v1/channels.py",
    '''    if payload.service_user_id is not None:
        if payload.service_user_id != current_user.id and not current_user.is_superuser:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign another service user")
        service_user = await db.get(User, payload.service_user_id)
        if service_user is None or not service_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Service user is missing or inactive"
            )
''',
    '''    if payload.service_user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Channel service identities are managed automatically and cannot be reassigned",
        )
''',
    label="managed update identity",
)

test_path = ROOT / "src/backend/tests/unit/channels/test_channel_access_principals.py"
test_content = test_path.read_text(encoding="utf-8")
old_fixture = "connection = SimpleNamespace(\n        user_id="
new_fixture = "connection = SimpleNamespace(\n        id=uuid4(),\n        user_id="
if new_fixture not in test_content:
    if old_fixture not in test_content:
        raise RuntimeError("Missing principal connection fixture")
    test_content = test_content.replace(old_fixture, new_fixture)

old_user_helper = '''def _user(user_id, *, active=True):
    return SimpleNamespace(id=user_id, is_active=active)
'''
new_user_helper = '''def _user(user_id, *, active=True, connection_id=None):
    optins = {}
    if connection_id is not None:
        optins = {
            "channel_service_identity": True,
            "channel_connection_id": str(connection_id),
        }
    return SimpleNamespace(id=user_id, is_active=active, optins=optins)
'''
if new_user_helper not in test_content:
    if old_user_helper not in test_content:
        raise RuntimeError("Missing principal user helper")
    test_content = test_content.replace(old_user_helper, new_user_helper, 1)

old_service_users = "users = {service_id: _user(service_id), member_id: _user(member_id)}"
new_service_users = (
    "users = {service_id: _user(service_id, connection_id=connection.id), member_id: _user(member_id)}"
)
if new_service_users not in test_content:
    if old_service_users not in test_content:
        raise RuntimeError("Missing service principal fixture")
    test_content = test_content.replace(old_service_users, new_service_users, 1)

test_path.write_text(test_content, encoding="utf-8")

# The request models retain the optional field for one release so older clients
# receive a precise validation error instead of silently mutating privileges.
