import asyncio

import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:  # re-check: another task may have won the race
                # Explicit, small bounds — confirmed live: asyncpg's default
                # min_size=10 opens 10 connections immediately on startup,
                # which alone eats most of Supabase's session-mode pooler
                # limit (15 total concurrent clients on this project's
                # tier), and crashed the app on deploy (EMAXCONNSESSION)
                # the moment any other client also held a connection. A
                # single-instance FastAPI process (WEB_CONCURRENCY=1) has no
                # need for 10 idle connections at once.
                _pool = await asyncpg.create_pool(
                    settings.database_url, min_size=1, max_size=5
                )
    return _pool
