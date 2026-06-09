# Async PostgreSQL helpers using asyncpg.
# All tool files import from here.

import os
import asyncio
import datetime as _dt
import threading
import asyncpg
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True, encoding="utf-8-sig")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ecommerce_ops"
)

# Connection Pool Variable _pool = None means no database connection exist yet.)
_pool: asyncpg.Pool | None = None

# Returns a postgresql Pool
async def get_pool() -> asyncpg.Pool:
    global _pool # Read the global variable

    # Creating the connection pool if it doesn't exist
    if _pool is None:

        # Creates a connection Pool that keeps at least 2 connections open and at max 10.
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)

    return _pool # Return the pool

# Used for fetching a single row from the database.
async def fetchone(query: str, *args) -> dict | None:
    pool = await get_pool() # Retrieve existing Pool
    async with pool.acquire() as conn: # Acquire a connection from the pool
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None

# Used for fetching multiple rows from the database.
async def fetchall(query: str, *args) -> list[dict]:
    pool = await get_pool() # Retrieve existing Pool
    async with pool.acquire() as conn: # Acquire a connection from the pool
        rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]

# Used for INSERT , UPDATE, DELETE queries that don't return rows.
async def execute(query: str, *args) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(query, *args)


# ── Sync wrappers for @tool functions ────────────────────────────────────────
# LangGraph's ToolNode calls tools synchronously (tool.invoke → _run).
# We keep ONE background event loop thread (_sync_loop) with its OWN pool
# (_sync_pool). The FastAPI pool (_pool) lives in uvicorn's event loop.
# asyncpg connections CANNOT be shared across event loops — separate pools
# is the only safe approach.

_sync_loop: asyncio.AbstractEventLoop | None = None
_sync_loop_lock = threading.Lock()
_sync_pool: asyncpg.Pool | None = None  # lives exclusively in _sync_loop


def _get_sync_loop() -> asyncio.AbstractEventLoop:
    global _sync_loop
    with _sync_loop_lock:
        if _sync_loop is None or _sync_loop.is_closed():
            _sync_loop = asyncio.new_event_loop()
            threading.Thread(
                target=_sync_loop.run_forever,
                daemon=True,
                name="db-sync-loop",
            ).start()
    return _sync_loop


async def _get_sync_pool() -> asyncpg.Pool:
    """Creates/returns the pool that lives in _sync_loop. Never call from FastAPI."""
    global _sync_pool
    if _sync_pool is None:
        _sync_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _sync_pool


def _coerce_dates(args: tuple) -> list:
    """Convert YYYY-MM-DD strings to datetime.date — asyncpg requires date objects."""
    result = []
    for a in args:
        if isinstance(a, str) and len(a) == 10 and a[4:5] == "-" and a[7:8] == "-":
            try:
                result.append(_dt.date.fromisoformat(a))
                continue
            except ValueError:
                pass
        result.append(a)
    return result


def fetchone_sync(query: str, *args) -> dict | None:
    coerced = _coerce_dates(args)

    async def _run():
        pool = await _get_sync_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, *coerced)
            return dict(row) if row else None

    return asyncio.run_coroutine_threadsafe(_run(), _get_sync_loop()).result(timeout=30)


def fetchall_sync(query: str, *args) -> list[dict]:
    coerced = _coerce_dates(args)

    async def _run():
        pool = await _get_sync_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *coerced)
            return [dict(r) for r in rows]

    return asyncio.run_coroutine_threadsafe(_run(), _get_sync_loop()).result(timeout=30)


def execute_sync(query: str, *args) -> None:
    coerced = _coerce_dates(args)

    async def _run():
        pool = await _get_sync_pool()
        async with pool.acquire() as conn:
            await conn.execute(query, *coerced)

    asyncio.run_coroutine_threadsafe(_run(), _get_sync_loop()).result(timeout=30)

