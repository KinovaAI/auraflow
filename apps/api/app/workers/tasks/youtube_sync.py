"""AuraFlow — YouTube Video Sync Task

Runs hourly via Celery Beat. Syncs YouTube videos for all orgs
with YouTube connected (youtube_connected_at IS NOT NULL).
"""
import asyncio

from app.core.logging import logger
from app.core.tenant_context import set_tenant_context, clear_tenant_context
from app.db.session import get_global_db
from app.workers.celery_app import app


async def _sync_all_orgs() -> dict:
    """Sync YouTube videos for every org with YouTube connected."""
    synced_orgs = 0
    total_new = 0
    total_updated = 0
    errors = 0

    async with get_global_db() as db:
        orgs = await db.fetch(
            """
            SELECT id, schema_name, slug
            FROM af_global.organizations
            WHERE status IN ('active', 'trial')
              AND youtube_connected_at IS NOT NULL
            """
        )

    for org in orgs:
        try:
            # Set tenant context so get_tenant_db() resolves correctly
            set_tenant_context(
                organization_id=str(org["id"]),
                schema_name=org["schema_name"],
                slug=org["slug"],
            )

            from app.services.video.youtube_service import YouTubeService
            svc = YouTubeService()
            result = await svc.sync_videos(str(org["id"]))

            total_new += result.get("new", 0)
            total_updated += result.get("updated", 0)
            synced_orgs += 1

        except Exception as e:
            errors += 1
            logger.error(
                "YouTube sync failed for org",
                org_id=str(org["id"]),
                schema=org["schema_name"],
                error=str(e),
            )
        finally:
            clear_tenant_context()

    return {
        "orgs_synced": synced_orgs,
        "new_videos": total_new,
        "updated_videos": total_updated,
        "errors": errors,
    }


@app.task(name="app.workers.tasks.youtube_sync.sync_youtube_videos_all_orgs")
def sync_youtube_videos_all_orgs():
    """Celery task: sync YouTube videos for all connected orgs."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_sync_all_orgs())
        logger.info("YouTube sync complete (all orgs)", **result)
        return result
    finally:
        loop.close()
