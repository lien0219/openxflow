"""Persistent operational views for channel messages, metrics, audit, and retries."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.channels.services.authorization import authorize_channel_connection
from langflow.channels.services.configuration_audit import (
    list_channel_configuration_audits,
    record_channel_configuration_audit,
)
from langflow.channels.services.message_records import list_channel_messages
from langflow.channels.services.observability import (
    ChannelConnectionOverview,
    ChannelOutboundDeliveryPage,
    ChannelRetryDeliveryResult,
    list_outbound_deliveries,
    read_connection_overview,
    retry_failed_outbound_delivery,
)
from langflow.services.authorization import ChannelAction
from langflow.services.database.models.channel.audit_model import (
    ChannelConfigurationAuditPage,
)
from langflow.services.database.models.channel.message_model import (
    ChannelMessageRecordPage,
)

router = APIRouter(prefix="/channels", tags=["Channel Observability"])


@router.get("/{connection_id}/overview", response_model=ChannelConnectionOverview)
async def read_channel_connection_overview(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
    window_hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24,
) -> ChannelConnectionOverview:
    await authorize_channel_connection(db, current_user, connection_id, ChannelAction.READ)
    return await read_connection_overview(db, connection_id, window_hours=window_hours)


@router.get("/{connection_id}/messages", response_model=ChannelMessageRecordPage)
async def read_channel_messages(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    query: Annotated[str | None, Query(max_length=255)] = None,
    direction: Annotated[str | None, Query(max_length=16)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    conversation_binding_id: Annotated[UUID | None, Query()] = None,
    external_conversation_id: Annotated[str | None, Query(max_length=255)] = None,
    external_user_id: Annotated[str | None, Query(max_length=255)] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> ChannelMessageRecordPage:
    await authorize_channel_connection(db, current_user, connection_id, ChannelAction.READ)
    return await list_channel_messages(
        db,
        connection_id,
        page=page,
        page_size=page_size,
        query=query,
        direction=direction,
        status=status_filter,
        conversation_binding_id=conversation_binding_id,
        external_conversation_id=external_conversation_id,
        external_user_id=external_user_id,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/{connection_id}/deliveries", response_model=ChannelOutboundDeliveryPage)
async def read_channel_deliveries(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    query: Annotated[str | None, Query(max_length=255)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    delivery_kind: Annotated[str | None, Query(max_length=32)] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> ChannelOutboundDeliveryPage:
    await authorize_channel_connection(db, current_user, connection_id, ChannelAction.READ)
    return await list_outbound_deliveries(
        db,
        connection_id,
        page=page,
        page_size=page_size,
        query=query,
        status=status_filter,
        delivery_kind=delivery_kind,
        created_from=created_from,
        created_to=created_to,
    )


@router.post("/{connection_id}/deliveries/{delivery_id}/retry", response_model=ChannelRetryDeliveryResult)
async def retry_channel_delivery(
    connection_id: UUID,
    delivery_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> ChannelRetryDeliveryResult:
    await authorize_channel_connection(db, current_user, connection_id, ChannelAction.EXECUTE)
    try:
        result = await retry_failed_outbound_delivery(
            db,
            connection_id=connection_id,
            delivery_id=delivery_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await record_channel_configuration_audit(
        db,
        connection_id=connection_id,
        actor_user_id=current_user.id,
        action="retry",
        resource_type="outbound_delivery",
        resource_id=delivery_id,
        before={"status": "failed"},
        after={"status": result.status, "webhook_job_id": result.webhook_job_id},
    )
    await db.commit()
    return result


@router.get("/{connection_id}/audits", response_model=ChannelConfigurationAuditPage)
async def read_channel_configuration_audits(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    action: Annotated[str | None, Query(max_length=64)] = None,
    resource_type: Annotated[str | None, Query(max_length=64)] = None,
    actor_user_id: Annotated[UUID | None, Query()] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> ChannelConfigurationAuditPage:
    await authorize_channel_connection(db, current_user, connection_id, ChannelAction.AUDIT)
    return await list_channel_configuration_audits(
        db,
        connection_id,
        page=page,
        page_size=page_size,
        action=action,
        resource_type=resource_type,
        actor_user_id=actor_user_id,
        created_from=created_from,
        created_to=created_to,
    )
