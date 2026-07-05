"""AuraFlow — Email Preferences (CAN-SPAM Unsubscribe)

Public endpoints for one-click email unsubscribe.
No authentication required — links are HMAC-signed.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.services.email.email_service import verify_unsubscribe_token

router = APIRouter()

_UNSUB_SUCCESS_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Unsubscribed</title>
<style>
  body { font-family: -apple-system, sans-serif; display: flex;
         justify-content: center; align-items: center; min-height: 100vh;
         margin: 0; background: #f9fafb; color: #333; }
  .card { background: #fff; border-radius: 12px; padding: 48px;
          box-shadow: 0 2px 8px rgba(0,0,0,.08); text-align: center;
          max-width: 440px; }
  h1 { font-size: 24px; margin-bottom: 12px; }
  p  { color: #666; line-height: 1.6; }
</style></head>
<body><div class="card">
  <h1>You have been unsubscribed</h1>
  <p>You will no longer receive marketing emails from us.
     If this was a mistake you can re-subscribe from your member portal.</p>
</div></body></html>"""

_UNSUB_ERROR_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Invalid Link</title>
<style>
  body { font-family: -apple-system, sans-serif; display: flex;
         justify-content: center; align-items: center; min-height: 100vh;
         margin: 0; background: #f9fafb; color: #333; }
  .card { background: #fff; border-radius: 12px; padding: 48px;
          box-shadow: 0 2px 8px rgba(0,0,0,.08); text-align: center;
          max-width: 440px; }
  h1 { font-size: 24px; margin-bottom: 12px; color: #c0392b; }
  p  { color: #666; line-height: 1.6; }
</style></head>
<body><div class="card">
  <h1>Invalid or expired link</h1>
  <p>This unsubscribe link is not valid. Please contact us directly
     if you would like to update your email preferences.</p>
</div></body></html>"""


@router.get("/unsubscribe/{member_id}/{token}", response_class=HTMLResponse)
async def unsubscribe(member_id: str, token: str):
    """
    CAN-SPAM one-click unsubscribe.
    Validates HMAC token and sets the member's email_opt_in to false.
    Scans all tenant schemas since we don't know which org the member belongs to.
    """
    if not verify_unsubscribe_token(member_id, token):
        logger.warning("Invalid unsubscribe token", member_id=member_id)
        return HTMLResponse(content=_UNSUB_ERROR_HTML, status_code=400)

    # Find the member across tenant schemas and opt them out
    updated = False
    async with get_global_db() as db:
        rows = await db.fetch(
            "SELECT schema_name FROM af_global.organizations "
            "WHERE status IN ('active', 'trial')"
        )

    for row in rows:
        schema = row["schema_name"]
        try:
            async with get_tenant_db(schema_override=schema) as db:
                result = await db.execute(
                    """
                    UPDATE members
                    SET email_opt_in = FALSE,
                        email_opt_out_at = NOW()
                    WHERE id = $1 AND email_opt_in = TRUE
                    """,
                    member_id,
                )
                # asyncpg returns "UPDATE N" — check if any rows were affected
                if result and result.split()[-1] != "0":
                    updated = True
                    logger.info(
                        "Member unsubscribed via CAN-SPAM link",
                        member_id=member_id,
                        schema=schema,
                    )
                    break
        except Exception as e:
            logger.warning(
                "Unsubscribe schema scan error",
                schema=schema,
                error=str(e),
            )
            continue

    if not updated:
        # Member may already be unsubscribed or ID is invalid.
        # Still return success page to avoid information leakage.
        logger.info(
            "Unsubscribe link used but no update needed",
            member_id=member_id,
        )

    return HTMLResponse(content=_UNSUB_SUCCESS_HTML)
