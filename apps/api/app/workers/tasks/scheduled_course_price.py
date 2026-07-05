"""
One-shot task to revert a course/workshop price at a specific time.

Submitted via `apply_async(eta=...)` for time-limited promo pricing.
"""
import asyncio

from app.core.logging import logger
from app.db.session import get_tenant_db
from app.core.tenant_context import set_tenant_context_from_schema, clear_tenant_context
from app.workers.celery_app import app


async def _do_revert(schema: str, course_id: str, target_price_cents: int) -> dict:
    await set_tenant_context_from_schema(schema)
    try:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "UPDATE courses SET price_cents = $1, updated_at = NOW() "
                "WHERE id = $2 RETURNING id, title, price_cents",
                target_price_cents, course_id,
            )
        return {"id": str(row["id"]), "title": row["title"], "price_cents": row["price_cents"]} if row else {}
    finally:
        clear_tenant_context()


@app.task(name="app.workers.tasks.scheduled_course_price.revert_course_price")
def revert_course_price(schema: str, course_id: str, target_price_cents: int):
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_do_revert(schema, course_id, target_price_cents))
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
    logger.info("Course price reverted", **result)
    return result
