"""AuraFlow — Token Cleanup Task

Runs daily via Celery Beat. Removes expired and revoked refresh tokens
to prevent database bloat.
"""
import asyncio

from app.core.logging import logger
from app.db.session import get_global_db
from app.workers.celery_app import app


async def _cleanup_tokens() -> int:
    """Delete all expired and revoked refresh tokens."""
    async with get_global_db() as db:
        result = await db.execute(
            """DELETE FROM af_global.refresh_tokens
               WHERE revoked_at IS NOT NULL OR expires_at < NOW()"""
        )
        # result is like "DELETE 123"
        count = int(result.split()[-1]) if result else 0
    return count


@app.task(name="app.workers.tasks.token_cleanup.cleanup_tokens")
def cleanup_tokens():
    """Celery task: clean up expired/revoked refresh tokens."""
    loop = asyncio.new_event_loop()
    try:
        count = loop.run_until_complete(_cleanup_tokens())
        if count:
            logger.info("Token cleanup complete", deleted=count)
        return {"deleted": count}
    finally:
        loop.close()
