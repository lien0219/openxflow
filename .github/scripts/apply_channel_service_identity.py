from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str, *, label: str) -> None:
    content = read(path)
    if new in content:
        return
    if old not in content:
        raise RuntimeError(f"Missing service identity target for {label}")
    write(path, content.replace(old, new, 1))


service_identity = '''"""Lifecycle for least-privileged channel service accounts."""

from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.initial_setup.setup import get_or_create_default_folder
from langflow.services.database.models.channel.model import ChannelConnection
from langflow.services.database.models.user.model import User
from langflow.services.deps import get_auth_service

_MARKER = "channel_service_identity"
_CONNECTION_MARKER = "channel_connection_id"


def managed_service_username(connection_id: UUID) -> str:
    return f"channel-service-{connection_id.hex}@openxflow.internal"


def is_managed_channel_service_user(user: User | None, connection_id: UUID) -> bool:
    if user is None or not isinstance(user.optins, dict):
        return False
    return bool(user.optins.get(_MARKER)) and user.optins.get(_CONNECTION_MARKER) == str(connection_id)


async def ensure_channel_service_identity(
    session: AsyncSession,
    connection: ChannelConnection,
) -> User:
    """Return the dedicated service user, replacing unsafe legacy owner fallbacks."""
    current = await session.get(User, connection.service_user_id) if connection.service_user_id else None
    if is_managed_channel_service_user(current, connection.id):
        return current

    username = managed_service_username(connection.id)
    service_user = (await session.exec(select(User).where(User.username == username))).first()
    if service_user is None:
        service_user = User(
            username=username,
            password=get_auth_service().get_password_hash(secrets.token_urlsafe(48)),
            is_active=True,
            is_superuser=False,
            optins={
                _MARKER: True,
                _CONNECTION_MARKER: str(connection.id),
                "channel_provider": connection.channel_type,
            },
        )
        try:
            async with session.begin_nested():
                session.add(service_user)
                await session.flush()
        except IntegrityError:
            service_user = (await session.exec(select(User).where(User.username == username))).first()
            if service_user is None:
                raise

    if not is_managed_channel_service_user(service_user, connection.id):
        raise RuntimeError("Reserved channel service username is already in use")
    if service_user.is_superuser:
        raise RuntimeError("Channel service identity must never be a superuser")

    await get_or_create_default_folder(session, service_user.id)
    connection.service_user_id = service_user.id
    session.add(connection)
    await session.flush()
    return service_user


async def remove_channel_service_identity(
    session: AsyncSession,
    connection: ChannelConnection,
) -> None:
    service_user = await session.get(User, connection.service_user_id) if connection.service_user_id else None
    if not is_managed_channel_service_user(service_user, connection.id):
        return
    connection.service_user_id = None
    session.add(connection)
    await session.flush()
    await session.delete(service_user)
    await session.flush()
'''
write("src/backend/base/langflow/channels/services/service_identity.py", service_identity)

CRUD = "src/backend/base/langflow/services/database/models/channel/crud.py"
replace_once(
    CRUD,
    "from langflow.channels.security.credentials import decrypt_credentials, encrypt_credentials, list_credential_keys\n",
    "from langflow.channels.security.credentials import decrypt_credentials, encrypt_credentials, list_credential_keys\nfrom langflow.channels.services.service_identity import (\n    ensure_channel_service_identity,\n    remove_channel_service_identity,\n)\n",
    label="CRUD imports",
)
replace_once(
    CRUD,
    "        service_user_id=payload.service_user_id or user_id,\n",
    "        service_user_id=None,\n",
    label="connection owner fallback",
)
replace_once(
    CRUD,
    """    session.add(connection)
    await session.flush()
    await session.refresh(connection)
    return _connection_read(connection)
""",
    """    session.add(connection)
    await session.flush()
    await ensure_channel_service_identity(session, connection)
    await session.refresh(connection)
    return _connection_read(connection)
""",
    label="create managed service user",
)
replace_once(
    CRUD,
    """    rows = (await session.exec(statement)).all()
    return [_connection_read(row) for row in rows]
""",
    """    rows = (await session.exec(statement)).all()
    for row in rows:
        await ensure_channel_service_identity(session, row)
    return [_connection_read(row) for row in rows]
""",
    label="repair listed connections",
)
replace_once(
    CRUD,
    """    return (await session.exec(statement)).first()


async def update_channel_connection(
""",
    """    connection = (await session.exec(statement)).first()
    if connection is not None:
        await ensure_channel_service_identity(session, connection)
    return connection


async def update_channel_connection(
""",
    label="repair fetched connection",
)
replace_once(
    CRUD,
    """    changes = payload.model_dump(exclude_unset=True, exclude={"credentials"})
""",
    """    changes = payload.model_dump(exclude_unset=True, exclude={"credentials", "service_user_id"})
""",
    label="service identity read only",
)
replace_once(
    CRUD,
    """    connection.updated_at = _utc_now()
    session.add(connection)

    if "default_flow_id" in changes:
""",
    """    connection.updated_at = _utc_now()
    session.add(connection)
    await ensure_channel_service_identity(session, connection)

    if "default_flow_id" in changes:
""",
    label="repair updated connection",
)
replace_once(
    CRUD,
    """async def delete_channel_connection(session: AsyncSession, connection: ChannelConnection) -> None:
    await session.delete(connection)
""",
    """async def delete_channel_connection(session: AsyncSession, connection: ChannelConnection) -> None:
    await remove_channel_service_identity(session, connection)
    await session.delete(connection)
""",
    label="delete managed service user",
)

ACCESS = "src/backend/base/langflow/channels/services/access_control.py"
replace_once(
    ACCESS,
    "from langflow.services.database.models.user.model import User\n",
    "from langflow.channels.services.service_identity import ensure_channel_service_identity\nfrom langflow.services.database.models.user.model import User\n",
    label="access imports",
)
replace_once(
    ACCESS,
    """    service_user_id = connection.service_user_id
    if service_user_id is None:
        raise ChannelServiceIdentityUnavailableError
    service_user = await session.get(User, service_user_id)
""",
    """    try:
        service_user = await ensure_channel_service_identity(session, connection)
    except Exception as exc:  # noqa: BLE001
        raise ChannelServiceIdentityUnavailableError from exc
""",
    label="runtime managed identity",
)
replace_once(
    ACCESS,
    """    if service_user is None or not service_user.is_active:
""",
    """    if not service_user.is_active:
""",
    label="managed identity active check",
)

DISPATCH = "src/backend/base/langflow/channels/services/dispatch.py"
replace_once(
    DISPATCH,
    """                    "execution_identity_type": execution_identity_type,
                }
""",
    """                    "execution_identity_type": execution_identity_type,
                    "granted_flow_id": str(flow_id) if flow_id is not None else None,
                }
""",
    label="explicit flow grant",
)

WORKFLOW = "src/backend/base/langflow/channels/services/workflow.py"
replace_once(
    WORKFLOW,
    "from typing import TYPE_CHECKING, Any\n",
    "from typing import TYPE_CHECKING, Any\nfrom uuid import UUID\n\nfrom fastapi import HTTPException, status\n",
    label="workflow grant imports",
)
replace_once(
    WORKFLOW,
    "from langflow.services.database.models.channel.model import ChannelContextMode\n",
    "from langflow.services.database.models.channel.execution_model import ChannelExecutionIdentityType\nfrom langflow.services.database.models.channel.model import ChannelContextMode\nfrom langflow.services.database.models.flow.model import Flow\nfrom langflow.services.deps import session_scope\n",
    label="workflow service imports",
)
replace_once(
    WORKFLOW,
    """        flow = await get_flow_by_id_or_endpoint_name(flow_identifier, user.id, widen_for_shares=True)
        await ensure_flow_permission(
            user,
            FlowAction.EXECUTE,
            flow_id=flow.id,
            flow_user_id=flow.user_id,
            workspace_id=getattr(flow, "workspace_id", None),
            folder_id=getattr(flow, "folder_id", None),
        )
""",
    """        if execution_identity_type == ChannelExecutionIdentityType.SERVICE.value:
            granted_flow_id = str((channel_context or {}).get("granted_flow_id") or "")
            if not granted_flow_id or granted_flow_id != flow_identifier:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="The channel service identity is not granted this workflow",
                )
            try:
                flow_id = UUID(granted_flow_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Shared channel routes require an explicit workflow ID grant",
                ) from exc
            async with session_scope() as session:
                flow = await session.get(Flow, flow_id)
            if flow is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
        else:
            flow = await get_flow_by_id_or_endpoint_name(flow_identifier, user.id, widen_for_shares=True)
            await ensure_flow_permission(
                user,
                FlowAction.EXECUTE,
                flow_id=flow.id,
                flow_user_id=flow.user_id,
                workspace_id=getattr(flow, "workspace_id", None),
                folder_id=getattr(flow, "folder_id", None),
            )
""",
    label="service workflow grant",
)

tests = """from types import SimpleNamespace
from uuid import uuid4

from langflow.channels.services.service_identity import (
    is_managed_channel_service_user,
    managed_service_username,
)


def test_managed_service_username_is_deterministic_and_isolated() -> None:
    first = uuid4()
    second = uuid4()
    assert managed_service_username(first) == managed_service_username(first)
    assert managed_service_username(first) != managed_service_username(second)
    assert managed_service_username(first).endswith("@openxflow.internal")


def test_service_identity_marker_is_connection_scoped() -> None:
    connection_id = uuid4()
    user = SimpleNamespace(
        optins={
            "channel_service_identity": True,
            "channel_connection_id": str(connection_id),
        }
    )
    assert is_managed_channel_service_user(user, connection_id)
    assert not is_managed_channel_service_user(user, uuid4())
    assert not is_managed_channel_service_user(SimpleNamespace(optins=None), connection_id)
"""
write("src/backend/tests/unit/channels/test_channel_service_identity.py", tests)

print("Applied managed channel service identity runtime")
