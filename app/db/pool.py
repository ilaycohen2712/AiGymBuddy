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
                _pool = await asyncpg.create_pool(settings.database_url)
    return _pool
