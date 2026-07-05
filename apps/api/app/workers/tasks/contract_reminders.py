"""Celery task: send a one-time reminder for unsigned contracts older than 7d.

Mirrors the pattern of other celery tasks in apps/api/app/workers/tasks/.
"""
import asyncio

from app.core.logging import logger
from app.workers.celery_app import app as celery_app


def _run_async(coro):
    """Same pattern other Celery tasks use — fresh loop per tick."""
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


@celery_app.task(name="contracts.send_reminders", bind=True, max_retries=2)
def send_contract_reminders(self):
    return _run_async(_send_all())


async def _send_all() -> dict:
    from app.core.tenant_context import set_tenant_context, clear_tenant_context
    from app.db.session import get_global_db
    from app.services.contracts import contract_service
    from app.services.email.email_service import EmailService

    email_svc = EmailService()
    stats = {"orgs_scanned": 0, "reminders_sent": 0, "failed": 0}

    async with get_global_db() as gdb:
        orgs = await gdb.fetch(
            "SELECT id, slug, schema_name FROM af_global.organizations WHERE status = 'active'"
        )

    for org in orgs:
        stats["orgs_scanned"] += 1
        set_tenant_context(
            organization_id=str(org["id"]),
            schema_name=org["schema_name"],
            slug=org["slug"],
        )
        try:
            pending = await contract_service.list_pending_reminders(min_age_days=7)
            for c in pending:
                try:
                    g_email = (c.get("prefilled_data") or {}).get("guest_known_contact", {}).get("email")
                    g_name = (c.get("prefilled_data") or {}).get("guest_known_contact", {}).get("name") or "Instructor"
                    workshop_title = (c.get("prefilled_data") or {}).get("workshop", {}).get("title") or "your workshop"
                    if not g_email:
                        continue
                    url = contract_service.signing_url(c["signing_token"])
                    html = f"""
                    <h2>Friendly reminder: contract still waiting on your signature</h2>
                    <p>Hi {g_name.split()[0] if g_name else 'there'},</p>
                    <p>We sent you the contract for <strong>{workshop_title}</strong> a week ago.
                    Just a gentle nudge in case it slipped past your inbox.</p>
                    <p style="margin: 24px 0;">
                      <a href="{url}" style="background:#2d6a4f;color:white;padding:12px 24px;
                         border-radius:6px;text-decoration:none;font-weight:600;">
                         Review &amp; Sign Contract
                      </a>
                    </p>
                    <p>Questions? Just reply or call us at (559) 915-3967.</p>
                    <p>— the studio team</p>
                    """
                    await email_svc.send_email(
                        to_email=g_email,
                        subject=f"Reminder: contract for {workshop_title}",
                        html_content=html,
                        email_type="contract_signing_reminder",
                    )
                    await contract_service.mark_reminder_sent(c["id"])
                    stats["reminders_sent"] += 1
                except Exception as e:
                    logger.error("contract.reminder_failed", contract_id=c["id"], error=str(e))
                    stats["failed"] += 1
        finally:
            clear_tenant_context()

    logger.info("contract.reminder_run_complete", **stats)
    return stats
