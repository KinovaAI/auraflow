"""AuraFlow — Studio Email Monitor Celery Tasks

Polls studio email inboxes via IMAP every 2 minutes, fetches new emails,
and processes each through the AI first-responder pipeline.
"""
import asyncio

from app.core.logging import logger
from app.workers.celery_app import app as celery_app


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        asyncio.set_event_loop(None)
        loop.close()


# ── Poll All Studio Inboxes (every 2 min) ────────────────────────────────

async def _poll_all_studios() -> dict:
    """Iterate all tenants with active email accounts, fetch new emails,
    and process each through AI."""
    from app.services.email.studio_inbox_service import StudioInboxService

    svc = StudioInboxService()
    active = await svc.get_all_active_accounts()

    total_fetched = 0
    total_processed = 0
    errors = []

    for entry in active:
        schema = entry["schema"]
        account_id = entry["account_id"]
        try:
            count = await svc.fetch_new_emails(schema, account_id)
            total_fetched += count

            if count:
                # Process new emails through AI
                from app.db.session import get_tenant_db
                async with get_tenant_db(schema_override=schema) as db:
                    new_emails = await db.fetch("""
                        SELECT id FROM studio_inbox_messages
                        WHERE account_id = $1
                          AND status = 'new'
                          AND classification IS NULL
                        ORDER BY received_at ASC
                        LIMIT 20
                    """, account_id)

                for email_row in new_emails:
                    try:
                        await svc.process_new_email(schema, str(email_row["id"]))
                        total_processed += 1
                    except Exception as e:
                        logger.error(
                            "Failed to process studio email",
                            schema=schema,
                            message_id=str(email_row["id"]),
                            error=str(e),
                        )
                        errors.append({
                            "schema": schema,
                            "message_id": str(email_row["id"]),
                            "error": str(e),
                        })

        except Exception as e:
            logger.error(
                "IMAP fetch failed for studio account",
                schema=schema,
                account_id=account_id,
                error=str(e),
            )
            errors.append({
                "schema": schema,
                "account_id": account_id,
                "error": str(e),
            })

    return {
        "accounts_checked": len(active),
        "total_fetched": total_fetched,
        "total_processed": total_processed,
        "errors": errors,
    }


@celery_app.task(name="studio.poll_studio_inboxes", bind=True, max_retries=2)
def poll_studio_inboxes(self):
    """Celery task: poll all studio IMAP inboxes and process new emails."""
    try:
        result = _run_async(_poll_all_studios())
        if result["total_fetched"] or result["total_processed"]:
            logger.info(
                "Studio email poll complete",
                accounts=result["accounts_checked"],
                fetched=result["total_fetched"],
                processed=result["total_processed"],
                errors=len(result["errors"]),
            )
        return result
    except Exception as e:
        logger.error(f"poll_studio_inboxes failed: {e}")
        raise self.retry(exc=e, countdown=60)


# ── Process Single Email (on-demand async task) ──────────────────────────

async def _process_single(schema_name: str, message_id: str) -> dict:
    from app.services.email.studio_inbox_service import StudioInboxService
    svc = StudioInboxService()
    return await svc.process_new_email(schema_name, message_id)


@celery_app.task(name="studio.process_studio_email", bind=True, max_retries=2)
def process_studio_email(self, schema_name: str, message_id: str):
    """Celery task: process a single studio email through AI."""
    try:
        result = _run_async(_process_single(schema_name, message_id))
        logger.info(
            "Studio email processed",
            schema=schema_name,
            message_id=message_id,
            status=result.get("status"),
        )
        return result
    except Exception as e:
        logger.error(
            f"process_studio_email failed: {e}",
            schema=schema_name,
            message_id=message_id,
        )
        raise self.retry(exc=e, countdown=30)
