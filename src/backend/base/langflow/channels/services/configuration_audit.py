"""Credential-safe configuration auditing for channel administration."""

from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from pydantic import BaseModel
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.services.database.models.channel.audit_model import (
    ChannelConfigurationAudit,
    ChannelConfigurationAuditPage,
    ChannelConfigurationAuditRead,
)

_SENSITIVE_KEYS = {
    "credential",
    "credentials",
    "credentials_data",
    "credentials_encrypted",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "client_secret",
    "app_secret",
    "bot_token",
    "signing_secret",
    "webhook_secret",
    "api_key",
    "private_key",
}
_REDACTED = "[REDACTED]"


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return (
        normalized in _SENSITIVE_KEYS
        or normalized.endswith(("_password", "_secret", "_token", "_api_key", "_private_key"))
        or "credential" in normalized
    )


def sanitize_channel_audit_value(value: Any, *, key: str | None = None) -> Any:
    """Return a JSON-safe copy with credential-bearing fields removed."""
    if key is not None and _is_sensitive_key(key):
        return _REDACTED
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return sanitize_channel_audit_value(value.value)
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_channel_audit_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_channel_audit_value(item) for item in value]
    if isinstance(value, (BaseModel, SQLModel)):
        return sanitize_channel_audit_value(value.model_dump(mode="json", exclude_none=False))
    return str(value)[:2000]


def channel_resource_snapshot(resource: Any | None) -> dict[str, Any]:
    if resource is None:
        return {}
    if isinstance(resource, dict):
        dumped = resource
    elif isinstance(resource, (BaseModel, SQLModel)):
        dumped = resource.model_dump(mode="json", exclude_none=False)
    else:
        data = getattr(resource, "__dict__", {})
        dumped = {key: value for key, value in data.items() if not key.startswith("_")}
    sanitized = sanitize_channel_audit_value(dumped)
    return sanitized if isinstance(sanitized, dict) else {"value": sanitized}


def channel_resource_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        previous = before.get(key)
        current = after.get(key)
        if previous != current:
            changes[key] = {"before": previous, "after": current}
    return changes


async def record_channel_configuration_audit(
    session: AsyncSession,
    *,
    connection_id: UUID,
    actor_user_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: UUID | str | None,
    before: Any | None = None,
    after: Any | None = None,
) -> ChannelConfigurationAudit:
    before_data = channel_resource_snapshot(before)
    after_data = channel_resource_snapshot(after)
    audit = ChannelConfigurationAudit(
        connection_id=connection_id,
        connection_reference=connection_id,
        actor_user_id=actor_user_id,
        action=action[:64],
        resource_type=resource_type[:64],
        resource_id=str(resource_id)[:255] if resource_id is not None else None,
        before_data=before_data,
        after_data=after_data,
        changes_data=channel_resource_changes(before_data, after_data),
    )
    session.add(audit)
    await session.flush()
    return audit


async def list_channel_configuration_audits(
    session: AsyncSession,
    connection_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
    action: str | None = None,
    resource_type: str | None = None,
    actor_user_id: UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> ChannelConfigurationAuditPage:
    normalized_page = max(1, page)
    normalized_page_size = min(100, max(1, page_size))
    filters: list[Any] = [ChannelConfigurationAudit.connection_reference == connection_id]
    if action:
        filters.append(ChannelConfigurationAudit.action == action)
    if resource_type:
        filters.append(ChannelConfigurationAudit.resource_type == resource_type)
    if actor_user_id is not None:
        filters.append(ChannelConfigurationAudit.actor_user_id == actor_user_id)
    if created_from is not None:
        filters.append(ChannelConfigurationAudit.created_at >= created_from)
    if created_to is not None:
        filters.append(ChannelConfigurationAudit.created_at <= created_to)

    total = int(
        (
            await session.exec(
                select(sa.func.count())
                .select_from(ChannelConfigurationAudit)
                .where(*filters)
            )
        ).one()
    )
    rows = (
        await session.exec(
            select(ChannelConfigurationAudit)
            .where(*filters)
            .order_by(ChannelConfigurationAudit.created_at.desc(), ChannelConfigurationAudit.id.desc())
            .offset((normalized_page - 1) * normalized_page_size)
            .limit(normalized_page_size)
        )
    ).all()
    return ChannelConfigurationAuditPage(
        items=[ChannelConfigurationAuditRead.model_validate(row, from_attributes=True) for row in rows],
        page=normalized_page,
        page_size=normalized_page_size,
        total=total,
        total_pages=math.ceil(total / normalized_page_size) if total else 0,
    )
