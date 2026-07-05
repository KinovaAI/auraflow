"""AuraFlow — Database session management."""
import asyncio
import re
from contextlib import asynccontextmanager

import asyncpg

from app.core.config import settings

_SAFE_SCHEMA_RE = re.compile(r"^(af_tenant_[a-z0-9_]+|af_global|public)$")


def _validate_schema(name: str) -> str:
    """Validate schema name to prevent SQL injection."""
    if not _SAFE_SCHEMA_RE.match(name):
        raise ValueError(f"Invalid schema name: {name}")
    return name

_pool = None
_pool_loop = None


async def init_db():
    global _pool, _pool_loop
    current_loop = asyncio.get_running_loop()

    # Reuse existing pool if it's on the same event loop and not closed
    if _pool is not None and _pool_loop is current_loop:
        try:
            # Test if pool is still alive
            async with _pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return  # Pool is fine, reuse it
        except Exception:
            pass  # Pool is dead, recreate

    # Close old pool if it exists
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:
            pass
        _pool = None

    _pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=1,
        max_size=10,
        max_inactive_connection_lifetime=60,  # Recycle idle after 1 min
        command_timeout=60,
    )
    _pool_loop = current_loop


@asynccontextmanager
async def get_global_db():
    global _pool, _pool_loop
    current_loop = asyncio.get_running_loop()
    if _pool is None or _pool_loop is not current_loop:
        await init_db()
    async with _pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def get_tenant_db(schema_override: str | None = None):
    """
    Acquire a connection scoped to a tenant's schema.
    Sets search_path so all unqualified table references resolve to the tenant schema.

    If schema_override is provided, uses that directly (for Celery workers outside
    request context). Otherwise, reads from TenantMiddleware context.
    """
    if schema_override:
        schema_name = schema_override
    else:
        from app.core.tenant_context import require_tenant_context
        ctx = require_tenant_context()
        schema_name = ctx.schema_name

    global _pool, _pool_loop
    current_loop = asyncio.get_running_loop()
    if _pool is None or _pool_loop is not current_loop:
        await init_db()
    async with _pool.acquire() as conn:
        schema_name = _validate_schema(schema_name)
        await conn.execute(
            f'SET search_path TO "{schema_name}", public'
        )
        try:
            yield conn
        finally:
            await conn.execute("RESET search_path")


async def get_db_status() -> bool:
    try:
        async with get_global_db() as db:
            await db.fetchval("SELECT 1")
        return True
    except Exception:
        return False
