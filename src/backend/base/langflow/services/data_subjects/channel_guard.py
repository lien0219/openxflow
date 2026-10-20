"""Refuse a builder erase while channel data still needs an operator's cleanup.

Channel identities use provider-specific IDs and shared conversations. The generic
flow/session eraser cannot safely infer which other participants' rows to remove.
Do not report an account erased while those records can still identify it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import or_, select

from langflow.services.data_subjects.errors import ChannelDataError
from langflow.services.database.models.channel import (
    ChannelConfigurationAudit,
    ChannelConnection,
    ChannelExecutionLog,
    ChannelFileAsset,
    ChannelIdentity,
    ChannelWorkflowCommand,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession


async def ensure_no_channel_data(session: AsyncSession, user_id: UUID) -> None:
    checks = (
        (ChannelConnection, or_(ChannelConnection.user_id == user_id, ChannelConnection.service_user_id == user_id)),
        (ChannelIdentity, ChannelIdentity.openxflow_user_id == user_id),
        (ChannelExecutionLog, ChannelExecutionLog.openxflow_user_id == user_id),
        (ChannelFileAsset, ChannelFileAsset.openxflow_user_id == user_id),
        (
            ChannelWorkflowCommand,
            or_(ChannelWorkflowCommand.owner_user_id == user_id, ChannelWorkflowCommand.created_by == user_id),
        ),
        (ChannelConfigurationAudit, ChannelConfigurationAudit.actor_user_id == user_id),
    )
    for model, predicate in checks:
        if (await session.exec(select(model.id).where(predicate).limit(1))).first() is not None:
            message = (
                "Channel data still references this account. Complete the channel data cleanup before approving "
                "erasure; shared conversations and channel audit records require separate review."
            )
            raise ChannelDataError(message, details={"table": model.__tablename__})
