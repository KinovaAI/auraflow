"""AuraFlow — Studio Social Media Celery Tasks

Periodic tasks for per-tenant social media:
- Daily AI post generation and publishing (9am UTC)
- Message/comment sync + AI processing (every 5 min)
- Scheduled post publishing (every 5 min)
"""
import asyncio

from app.core.logging import logger
from app.workers.celery_app import app as celery_app


def _run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# ── Daily AI Social Post (9am UTC) ──────────────────────────────────────

async def _daily_ai_post() -> dict:
    """For each tenant with active social accounts, generate and publish
    an AI post about today's schedule/events."""
    from app.services.social.studio_social_service import StudioSocialService

    svc = StudioSocialService()
    active = await svc.get_all_active_accounts()

    generated = 0
    published = 0
    errors = []

    for entry in active:
        schema = entry["schema"]
        try:
            # Generate AI content
            ai_result = await svc.generate_ai_post(schema)
            content = ai_result.get("content", "")
            if not content or content.startswith("[AI not configured]"):
                continue

            # Determine which platform to post to (prefer Facebook)
            platforms = [a["platform"] for a in entry["accounts"]]
            target_platform = "facebook" if "facebook" in platforms else platforms[0]

            # Create and publish
            post = await svc.create_post(schema, content, target_platform)
            generated += 1

            if post.get("id"):
                try:
                    await svc.publish_post(schema, str(post["id"]))
                    published += 1
                except Exception as e:
                    logger.warning(
                        "AI post created but publish failed",
                        schema=schema,
                        error=str(e),
                    )

        except Exception as e:
            logger.error(
                "Failed daily AI post",
                schema=schema,
                error=str(e),
            )
            errors.append({"schema": schema, "error": str(e)})

    return {
        "tenants_checked": len(active),
        "generated": generated,
        "published": published,
        "errors": errors,
    }


@celery_app.task(name="studio.daily_ai_social_post", bind=True, max_retries=2)
def daily_ai_social_post(self):
    """Celery task: generate and publish AI social posts for all tenants."""
    try:
        result = _run_async(_daily_ai_post())
        if result["generated"]:
            logger.info(
                "Daily AI social posts complete",
                tenants=result["tenants_checked"],
                generated=result["generated"],
                published=result["published"],
                errors=len(result["errors"]),
            )
        return result
    except Exception as e:
        logger.error(f"daily_ai_social_post failed: {e}")
        raise self.retry(exc=e, countdown=300)


# ── Sync Social Messages (every 5 min) ──────────────────────────────────

async def _sync_messages() -> dict:
    """Fetch new messages/comments for all tenants and process with AI."""
    from app.services.social.studio_social_service import StudioSocialService
    from app.db.session import get_tenant_db

    svc = StudioSocialService()
    active = await svc.get_all_active_accounts()

    total_fetched = 0
    total_processed = 0
    errors = []

    for entry in active:
        schema = entry["schema"]
        try:
            count = await svc.fetch_messages(schema)
            total_fetched += count

            if count:
                # Process new messages through AI
                async with get_tenant_db(schema_override=schema) as db:
                    pending = await db.fetch("""
                        SELECT id FROM studio_social_messages
                        WHERE ai_status = 'pending'
                        ORDER BY received_at ASC NULLS LAST
                        LIMIT 20
                    """)

                for msg_row in pending:
                    try:
                        await svc.handle_message_with_ai(schema, str(msg_row["id"]))
                        total_processed += 1
                    except Exception as e:
                        logger.error(
                            "Failed to AI-process social message",
                            schema=schema,
                            message_id=str(msg_row["id"]),
                            error=str(e),
                        )
                        errors.append({
                            "schema": schema,
                            "message_id": str(msg_row["id"]),
                            "error": str(e),
                        })

        except Exception as e:
            logger.error(
                "Social message sync failed for tenant",
                schema=schema,
                error=str(e),
            )
            errors.append({"schema": schema, "error": str(e)})

    return {
        "accounts_checked": len(active),
        "total_fetched": total_fetched,
        "total_processed": total_processed,
        "errors": errors,
    }


@celery_app.task(name="studio.sync_social_messages", bind=True, max_retries=2)
def sync_social_messages(self):
    """Celery task: fetch and AI-process social messages for all tenants."""
    try:
        result = _run_async(_sync_messages())
        if result["total_fetched"] or result["total_processed"]:
            logger.info(
                "Social message sync complete",
                accounts=result["accounts_checked"],
                fetched=result["total_fetched"],
                processed=result["total_processed"],
                errors=len(result["errors"]),
            )
        return result
    except Exception as e:
        logger.error(f"sync_social_messages failed: {e}")
        raise self.retry(exc=e, countdown=60)


# ── Publish Scheduled Posts (every 5 min) ────────────────────────────────

async def _publish_scheduled() -> dict:
    """Find and publish posts that are past their scheduled_at time."""
    from app.services.social.studio_social_service import StudioSocialService
    from app.db.session import get_tenant_db

    svc = StudioSocialService()
    active = await svc.get_all_active_accounts()

    published = 0
    errors = []

    for entry in active:
        schema = entry["schema"]
        try:
            async with get_tenant_db(schema_override=schema) as db:
                posts = await db.fetch("""
                    SELECT id FROM studio_social_posts
                    WHERE status = 'scheduled' AND scheduled_at <= NOW()
                    ORDER BY scheduled_at ASC LIMIT 10
                """)

            for post in posts:
                try:
                    await svc.publish_post(schema, str(post["id"]))
                    published += 1
                except Exception as e:
                    logger.error(
                        f"Failed to publish scheduled post {post['id']}: {e}",
                        schema=schema,
                    )
                    errors.append({
                        "schema": schema,
                        "post_id": str(post["id"]),
                        "error": str(e),
                    })

        except Exception as e:
            logger.error(
                "Scheduled post check failed",
                schema=schema,
                error=str(e),
            )

    return {"published": published, "errors": errors}


@celery_app.task(name="studio.publish_scheduled_social_posts", bind=True, max_retries=2)
def publish_scheduled_social_posts(self):
    """Celery task: publish social posts past their scheduled time."""
    try:
        result = _run_async(_publish_scheduled())
        if result["published"]:
            logger.info(
                "Published scheduled social posts",
                count=result["published"],
                errors=len(result["errors"]),
            )
        return result
    except Exception as e:
        logger.error(f"publish_scheduled_social_posts failed: {e}")
        raise self.retry(exc=e, countdown=60)
