from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from lfx.log.logger import logger
from lfx.services.sqlite_runtime import is_sqlite_lock_error
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.services.database.models.user.model import User, UserUpdate


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    return (await db.exec(stmt)).first()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    if isinstance(user_id, str):
        user_id = UUID(user_id)
    stmt = select(User).where(User.id == user_id)
    return (await db.exec(stmt)).first()


async def update_user(user_db: User | None, user: UserUpdate, db: AsyncSession) -> User:
    if not user_db:
        raise HTTPException(status_code=404, detail="User not found")

    # user_db_by_username = get_user_by_username(db, user.username)
    # if user_db_by_username and user_db_by_username.id != user_id:
    #     raise HTTPException(status_code=409, detail="Username already exists")

    user_data = user.model_dump(exclude_unset=True)
    changed = False
    for attr, value in user_data.items():
        if hasattr(user_db, attr) and value is not None:
            setattr(user_db, attr, value)
            changed = True

    if not changed:
        raise HTTPException(status_code=status.HTTP_304_NOT_MODIFIED, detail="Nothing to update")

    user_db.updated_at = datetime.now(timezone.utc)
    flag_modified(user_db, "updated_at")

    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return user_db


async def update_user_last_login_at(user_id: UUID, db: AsyncSession) -> User | None:
    """Best-effort last-login update for transient SQLite lock contention only.

    The timestamp is auxiliary metadata. A temporary SQLite lock must not poison
    the request session or block login, but schema, disk, permission, and logic
    errors must still surface instead of being silently hidden.
    """
    try:
        user_data = UserUpdate(last_login_at=datetime.now(timezone.utc))
        user = await get_user_by_id(db, user_id)
        return await update_user(user, user_data, db)
    except OperationalError as error:
        if not is_sqlite_lock_error(error):
            raise
        try:
            await db.rollback()
        except Exception as rollback_error:  # noqa: BLE001
            await logger.aerror(f"Error rolling back failed last-login update: {rollback_error!s}")
            raise error from rollback_error
        await logger.awarning(f"Unable to update user last login time; continuing login: {error!s}")
        return None


async def get_all_superusers(db: AsyncSession) -> list[User]:
    """Get all superuser accounts from the database."""
    stmt = select(User).where(User.is_superuser == True)  # noqa: E712
    result = await db.exec(stmt)
    return list(result.all())
