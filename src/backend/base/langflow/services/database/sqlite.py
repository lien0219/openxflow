"""SQLite pools that keep connection initialization safe from task cancellation."""

import asyncio

from sqlalchemy.pool import NullPool, Pool, PoolProxiedConnection, StaticPool
from sqlalchemy.util.concurrency import await_only, greenlet_spawn


async def _checkout(pool: Pool) -> PoolProxiedConnection:
    # A cancellation during aiosqlite.connect() or a SQLAlchemy connect listener
    # can leave a worker running before a session owns the connection. Shield
    # only checkout, including its listeners; statements and commits still run
    # in the caller's task with their usual cancellation/transaction semantics.
    checkout_task = asyncio.create_task(greenlet_spawn(Pool.connect, pool))
    try:
        return await asyncio.shield(checkout_task)
    except asyncio.CancelledError:

        async def return_connection() -> None:
            connection = await checkout_task
            await greenlet_spawn(connection.close)

        cleanup_task = asyncio.create_task(return_connection())
        # A second shutdown cancellation must not abandon the worker either.
        # Keep a reference and join cleanup before letting the caller unwind.
        while not cleanup_task.done():
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError:
                continue
        cleanup_task.result()
        raise


class SQLiteNullPool(NullPool):
    """Retain per-checkout connections and reuse across event loops for files."""

    def connect(self) -> PoolProxiedConnection:
        return await_only(_checkout(self))


class SQLiteStaticPool(StaticPool):
    """Retain the shared connection needed by an in-memory SQLite database."""

    def connect(self) -> PoolProxiedConnection:
        return await_only(_checkout(self))
