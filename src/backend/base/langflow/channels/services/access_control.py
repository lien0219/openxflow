"""Resolve effective channel policies and execution principals."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.services.service_identity import ensure_channel_service_identity
from langflow.services.database.models.channel.execution_model import ChannelExecutionIdentityType
from langflow.services.database.models.channel.model import (
    ChannelAccessPolicy,
    ChannelConnection,
    ChannelContextMode,
    ChannelConversationBinding,
    ChannelIdentity,
    ChannelIdentityStatus,
)
from langflow.services.database.models.user.model import User


class ChannelBindingRequiredError(PermissionError):
    """Raised when a route requires a bound OpenXFlow account."""


class ChannelServiceIdentityUnavailableError(PermissionError):
    """Raised when shared execution has no active service principal."""


@dataclass(frozen=True)
class ChannelExecutionPrincipal:
    user: User
    identity_type: str
    identity: ChannelIdentity | None = None


def effective_access_policy(
    connection: ChannelConnection,
    binding: ChannelConversationBinding | None,
) -> str:
    if (
        binding is not None
        and getattr(binding, "access_policy", ChannelAccessPolicy.INHERIT.value) != ChannelAccessPolicy.INHERIT.value
    ):
        return getattr(binding, "access_policy", ChannelAccessPolicy.INHERIT.value)
    return getattr(connection, "access_policy", ChannelAccessPolicy.HYBRID.value)


def effective_context_mode(
    connection: ChannelConnection,
    binding: ChannelConversationBinding | None,
) -> str:
    if (
        binding is not None
        and getattr(binding, "context_mode", ChannelContextMode.INHERIT.value) != ChannelContextMode.INHERIT.value
    ):
        return getattr(binding, "context_mode", ChannelContextMode.INHERIT.value)
    return getattr(connection, "default_context_mode", ChannelContextMode.ISOLATED.value)


async def bound_identity_user(
    session: AsyncSession,
    identity: ChannelIdentity | None,
) -> User | None:
    if identity is None or identity.status != ChannelIdentityStatus.BOUND.value or identity.openxflow_user_id is None:
        return None
    user = await session.get(User, identity.openxflow_user_id)
    if user is None or not user.is_active:
        return None
    return user


async def resolve_execution_principal(
    session: AsyncSession,
    connection: ChannelConnection,
    binding: ChannelConversationBinding | None,
    identity: ChannelIdentity | None,
    *,
    requires_personal: bool = False,
) -> ChannelExecutionPrincipal:
    """Resolve the least-privileged principal for one channel route.

    Access policy decides whether binding is required. The route type decides
    which principal executes it: shared routes always use the configured service
    identity, while personal routes use the bound member identity.
    """
    policy = effective_access_policy(connection, binding)
    bound_user = await bound_identity_user(session, identity)

    if policy == ChannelAccessPolicy.BOUND_ONLY.value and bound_user is None:
        raise ChannelBindingRequiredError

    if requires_personal:
        if bound_user is None:
            raise ChannelBindingRequiredError
        return ChannelExecutionPrincipal(
            user=bound_user,
            identity_type=ChannelExecutionIdentityType.BOUND_USER.value,
            identity=identity,
        )

    try:
        service_user = await ensure_channel_service_identity(session, connection)
    except Exception as exc:  # noqa: BLE001
        raise ChannelServiceIdentityUnavailableError from exc
    if not service_user.is_active:
        raise ChannelServiceIdentityUnavailableError
    return ChannelExecutionPrincipal(
        user=service_user,
        identity_type=ChannelExecutionIdentityType.SERVICE.value,
        identity=identity,
    )
