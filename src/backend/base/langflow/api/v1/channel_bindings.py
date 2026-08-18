"""Authenticated API for binding external channel identities to OpenXFlow users."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.channels.domain.exceptions import (
    ChannelBindingCodeExpiredError,
    ChannelBindingCodeInvalidError,
    ChannelIdentityConflictError,
)
from langflow.channels.services.binding import redeem_channel_binding_code
from langflow.services.database.models.channel.model import ChannelIdentityRead

router = APIRouter(prefix="/channel-bindings", tags=["Channel Bindings"])


class ChannelBindingRedeemRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


@router.post("/redeem", response_model=ChannelIdentityRead)
async def redeem_channel_binding(
    payload: ChannelBindingRedeemRequest,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> ChannelIdentityRead:
    try:
        identity = await redeem_channel_binding_code(db, payload.code, current_user.id)
    except ChannelBindingCodeExpiredError as exc:
        await db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    except ChannelBindingCodeInvalidError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ChannelIdentityConflictError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Channel identity binding conflict") from exc
    else:
        await db.commit()
        return identity
