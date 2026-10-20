"""Implicit ORM writes must participate in the SQLite writer queue."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from lfx.services.deps import session_scope
from lfx.services.sqlite_runtime import release_sqlite_process_safety
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import registry
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture
async def guarded_database(tmp_path):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'autoflush.db'}"
    engine = create_async_engine(database_url, poolclass=NullPool, connect_args={"timeout": 0.1})
    mapper = registry()
    table = sa.Table(
        "item",
        mapper.metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("value", sa.Integer, nullable=False),
    )

    class Item:
        pass

    mapper.map_imperatively(Item, table)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def with_session():
        async with sessions() as session:
            yield session

    service = SimpleNamespace(
        database_url=database_url,
        settings_service=SimpleNamespace(settings=SimpleNamespace(workers=1, db_connect_timeout=1)),
        _with_session=with_session,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(mapper.metadata.create_all)
            await connection.execute(table.insert().values(id=1, value=10))
        yield service, Item
    finally:
        await engine.dispose()
        release_sqlite_process_safety(database_url, owner=service)
        mapper.dispose()


@pytest.mark.parametrize("method", ["get", "get_one", "scalar", "scalars", "stream", "stream_scalars"])
async def test_autoflush_cannot_bypass_the_writer_queue(guarded_database, method):
    """A query's autoflush and a later explicit commit must have the same writer owner."""
    service, item = guarded_database
    started = asyncio.Event()
    competing = None

    async def competing_write():
        async with session_scope(service) as session:
            started.set()
            await session.execute(sa.insert(item).values(id=3, value=30))

    try:
        async with session_scope(service) as session:
            session.add(item(id=2, value=20))
            if method in {"get", "get_one"}:
                await getattr(session, method)(item, 1)
            else:
                result = await getattr(session, method)(sa.select(item).where(item.id == 1))
                if method.startswith("stream"):
                    await result.close()
            # The query above flushed id=2. A second pending write mirrors the
            # resume fixture deleting a job, fetching its flow, then deleting it.
            session.add(item(id=4, value=40))
            competing = asyncio.create_task(competing_write())
            await asyncio.wait_for(started.wait(), timeout=5)
        await asyncio.wait_for(competing, timeout=5)
        async with session_scope(service) as session:
            rows = (await session.execute(sa.select(item.id).order_by(item.id))).scalars().all()
        assert rows == [1, 2, 3, 4]
    finally:
        if competing is not None:
            if not competing.done():
                competing.cancel()
            await asyncio.gather(competing, return_exceptions=True)
