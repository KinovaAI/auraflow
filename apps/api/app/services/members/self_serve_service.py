"""AuraFlow — Self-serve online-membership enrollment.

Organization-independent: every step keys off the org's `slug` and reads the
plan's own config (`trial_days`, price, billing period, standing Zoom link) from
that tenant's `membership_types` row. Nothing is hardcoded to any one studio, so
any Square-billing studio can drop in their signup link and use this as-is.

Flow (one call):
  1. Resolve org by slug, create-or-link the user + member record (same logic as
     POST /auth/member-register) and seed default portal permissions.
  2. Save the customer's card on file via the billing dispatcher (Square).
  3. Create the membership in 'active' status with `trial_period_end` =
     now + trial_days. NO charge happens at signup — the membership's
     `current_period_end` is set to the trial end, so the existing
     `recurring_membership_renewals` scheduler charges the saved card on that
     date and rolls the period forward. That one scheduler is the ONLY thing
     that charges Square cards, so there is no double-charge path.
  4. Email the welcome with trial terms + standing Zoom link + week's schedule.

If a plan is configured with trial_days = 0 the first period is charged
immediately (mirrors the authenticated Square purchase path), so the same
endpoint serves both "free trial" and "pay now" online plans.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.logging import logger
from app.core.security import hash_password, verify_password
from app.db.session import get_global_db, get_tenant_db
from app.services.email.email_service import EmailService
from app.services.payments import billing_dispatcher

_PERIOD_SQL = {
    "weekly": "INTERVAL '7 days'",
    "monthly": "INTERVAL '1 month'",
    "annual": "INTERVAL '1 year'",
    "yearly": "INTERVAL '1 year'",
}
_PERIOD_LABEL = {
    "weekly": "week",
    "monthly": "month",
    "annual": "year",
    "yearly": "year",
}


class SignupError(Exception):
    """Raised for caller-fixable signup problems. `status` maps to HTTP."""

    def __init__(self, message: str, status: int = 422, code: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.code = code


async def _upcoming_virtual_schedule(schema_name: str, tz_name: str) -> list[dict]:
    """Next 7 days of virtual/hybrid classes, formatted in the studio's tz."""
    try:
        async with get_tenant_db(schema_override=schema_name) as db:
            rows = await db.fetch(
                """
                SELECT title, starts_at
                FROM class_sessions
                WHERE modality IN ('virtual', 'hybrid')
                  AND status = 'scheduled'
                  AND starts_at BETWEEN NOW() AND NOW() + INTERVAL '7 days'
                ORDER BY starts_at
                LIMIT 25
                """
            )
    except Exception as e:  # schedule is a nicety — never block signup on it
        logger.warning("Could not load welcome schedule", schema=schema_name, error=str(e))
        return []

    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name or "America/Los_Angeles")
    except Exception:
        tz = timezone.utc

    out: list[dict] = []
    for r in rows:
        when = r["starts_at"]
        try:
            local = when.astimezone(tz)
            when_str = local.strftime("%a %b %d, %I:%M %p").replace(" 0", " ")
        except Exception:
            when_str = str(when)
        out.append({"when": when_str, "title": r["title"]})
    return out


async def enroll_online_membership(
    *,
    org_slug: str,
    membership_type_id: str,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
    source_id: str,
    cardholder_name: Optional[str] = None,
    phone: Optional[str] = None,
    facility_name: Optional[str] = None,
) -> dict:
    email = email.lower().strip()

    # ── 1. Resolve organization ──────────────────────────────────────────
    async with get_global_db() as db:
        org = await db.fetchrow(
            """
            SELECT id, slug, schema_name, status, billing_provider, name, timezone
            FROM af_global.organizations WHERE slug = $1
            """,
            org_slug,
        )
    if not org:
        raise SignupError("Studio not found", status=404, code="ORG_NOT_FOUND")
    if org["status"] in ("suspended", "cancelled"):
        raise SignupError("This studio is not accepting signups", status=403)
    org_id = str(org["id"])
    schema_name = org["schema_name"]
    if org["billing_provider"] != "square":
        raise SignupError(
            "Self-serve online-membership signup is available for Square-billing studios only.",
            status=400,
            code="WRONG_PROVIDER",
        )

    # ── 2. Create or link the user (mirrors POST /auth/member-register) ───
    async with get_global_db() as db:
        existing_user = await db.fetchrow(
            "SELECT id, password_hash FROM af_global.users WHERE email = $1", email,
        )
    if existing_user:
        # Anti-hijack: linking an existing account requires its password.
        if not existing_user["password_hash"] or not verify_password(
            password, existing_user["password_hash"]
        ):
            raise SignupError(
                "An account with this email already exists — the password is incorrect.",
                status=401, code="EMAIL_EXISTS",
            )
        user_id = str(existing_user["id"])
        async with get_global_db() as db:
            link = await db.fetchrow(
                "SELECT id FROM af_global.organization_users WHERE user_id = $1 AND organization_id = $2",
                user_id, org_id,
            )
            if not link:
                await db.execute(
                    "INSERT INTO af_global.organization_users (id, user_id, organization_id, role) "
                    "VALUES ($1, $2, $3, 'member')",
                    str(uuid.uuid4()), user_id, org_id,
                )
    else:
        user_id = str(uuid.uuid4())
        async with get_global_db() as db:
            await db.execute(
                "INSERT INTO af_global.users (id, email, password_hash, first_name, last_name) "
                "VALUES ($1, $2, $3, $4, $5)",
                user_id, email, hash_password(password), first_name, last_name,
            )
            await db.execute(
                "INSERT INTO af_global.organization_users (id, user_id, organization_id, role) "
                "VALUES ($1, $2, $3, 'member')",
                str(uuid.uuid4()), user_id, org_id,
            )

    # ── 3. Member record in the tenant schema ────────────────────────────
    async with get_tenant_db(schema_override=schema_name) as db:
        member = await db.fetchrow(
            "SELECT id, square_customer_id FROM members WHERE email = $1", email,
        )
        if member:
            member_id = str(member["id"])
            existing_square_customer_id = member["square_customer_id"]
            await db.execute(
                "UPDATE members SET user_id = $1, facility_name = COALESCE($2, facility_name), "
                "updated_at = NOW() WHERE id = $3",
                user_id, facility_name, member_id,
            )
        else:
            member_id = str(uuid.uuid4())
            existing_square_customer_id = None
            await db.execute(
                "INSERT INTO members (id, user_id, first_name, last_name, email, facility_name, source) "
                "VALUES ($1, $2, $3, $4, $5, $6, 'facility_signup')",
                member_id, user_id, first_name, last_name, email, facility_name,
            )

    # Seed portal permissions (without this, every /portal/* call 403s).
    try:
        from app.services.permissions import permission_service
        await permission_service.initialize_default_permissions(org_id, user_id, "member")
    except Exception as e:
        logger.warning("Failed to seed member permissions on self-serve signup",
                       user_id=user_id, error=str(e))

    # ── 4. Load the plan (its own config drives everything) ───────────────
    async with get_tenant_db(schema_override=schema_name) as db:
        mt = await db.fetchrow(
            """
            SELECT id, name, type, price_cents, billing_period, trial_days,
                   is_online, standing_zoom_url, standing_zoom_meeting_id,
                   standing_zoom_password
            FROM membership_types WHERE id = $1 AND is_active = TRUE
            """,
            membership_type_id,
        )
    if not mt:
        raise SignupError("Membership plan not found", status=404, code="PLAN_NOT_FOUND")
    price_cents = int(mt["price_cents"])
    if price_cents <= 0:
        raise SignupError(
            "This plan has no price configured — self-serve signup needs a paid plan.",
            status=400, code="PLAN_NOT_PAID",
        )
    trial_days = int(mt["trial_days"] or 0)
    period = (mt["billing_period"] or "monthly").lower()
    period_sql = _PERIOD_SQL.get(period, "INTERVAL '1 month'")
    period_label = _PERIOD_LABEL.get(period, "month")

    # ── 5. Save card on file (Square) ─────────────────────────────────────
    customer = await billing_dispatcher.ensure_customer(
        organization_id=org_id, member_id=member_id, email=email,
        first_name=first_name, last_name=last_name, phone=phone,
        existing_square_customer_id=existing_square_customer_id,
    )
    customer_id = customer["customer_id"]
    if customer["created"]:
        async with get_tenant_db(schema_override=schema_name) as db:
            await db.execute(
                "UPDATE members SET square_customer_id = $2 WHERE id = $1",
                member_id, customer_id,
            )
    card = await billing_dispatcher.save_card_on_file(
        organization_id=org_id, customer_id=customer_id, source_id=source_id,
        cardholder_name=cardholder_name or f"{first_name} {last_name}".strip(),
    )
    card_id = card.get("card_id")
    if not card_id:
        raise SignupError("We couldn't save that card — please check the details and try again.",
                          status=400, code="CARD_SAVE_FAILED")

    # ── 6. Create the membership ──────────────────────────────────────────
    charged_now = False
    payment_id = None
    if trial_days > 0:
        # FREE TRIAL: no charge now. current_period_end = trial end, so the
        # renewal scheduler makes the first charge on that date (the conversion).
        async with get_tenant_db(schema_override=schema_name) as db:
            row = await db.fetchrow(
                f"""
                INSERT INTO member_memberships
                    (member_id, membership_type_id, status, starts_at, ends_at,
                     current_period_end, trial_period_end, square_card_id,
                     billing_provider, created_at)
                VALUES ($1, $2, 'active', NOW(),
                        NOW() + INTERVAL '{trial_days} days',
                        NOW() + INTERVAL '{trial_days} days',
                        NOW() + INTERVAL '{trial_days} days',
                        $3, 'square', NOW())
                RETURNING id, ends_at, trial_period_end
                """,
                member_id, str(mt["id"]), card_id,
            )
        membership_id = str(row["id"])
        trial_end = row["trial_period_end"]
    else:
        # PAY NOW: charge the first period immediately, same path as the
        # authenticated Square purchase.
        payment = await billing_dispatcher.create_payment(
            organization_id=org_id, amount_cents=price_cents, source_id=card_id,
            description=f"{mt['name']} — first period", member_id=member_id,
            member_square_customer_id=customer_id,
        )
        payment_id = payment["payment_id"]
        charged_now = True
        async with get_tenant_db(schema_override=schema_name) as db:
            row = await db.fetchrow(
                f"""
                INSERT INTO member_memberships
                    (member_id, membership_type_id, status, starts_at, ends_at,
                     current_period_end, square_card_id, billing_provider, created_at)
                VALUES ($1, $2, 'active', NOW(), NOW() + {period_sql},
                        NOW() + {period_sql}, $3, 'square', NOW())
                RETURNING id, ends_at
                """,
                member_id, str(mt["id"]), card_id,
            )
            await db.execute(
                """
                INSERT INTO transactions
                    (member_id, amount_cents, type, status, description,
                     square_payment_id, fee_cents, net_amount_cents, created_at)
                VALUES ($1, $2, 'subscription', 'completed', $3, $4, $5, $6, NOW())
                """,
                member_id, price_cents, mt["name"], payment_id,
                payment["fee_cents"], price_cents - payment["fee_cents"],
            )
        membership_id = str(row["id"])
        trial_end = None

    # ── 7. Welcome email (trial terms + standing Zoom + schedule) ─────────
    price_display = f"${price_cents / 100:.2f}/{period_label}"
    trial_end_display = None
    if trial_end:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(org["timezone"] or "America/Los_Angeles")
            trial_end_display = trial_end.astimezone(tz).strftime("%B %d, %Y").replace(" 0", " ")
        except Exception:
            trial_end_display = trial_end.strftime("%B %d, %Y")
    schedule = await _upcoming_virtual_schedule(schema_name, org["timezone"])

    try:
        from app.core.tenant_context import set_tenant_context, clear_tenant_context
        set_tenant_context(organization_id=org_id, schema_name=schema_name, slug=org["slug"])
        try:
            await EmailService().send_online_membership_welcome(
                member_id=member_id, to_email=email,
                member_name=first_name, membership_name=mt["name"],
                studio_name=org["name"],
                trial_end_display=trial_end_display, price_display=price_display,
                zoom_url=mt["standing_zoom_url"],
                zoom_meeting_id=mt["standing_zoom_meeting_id"],
                zoom_password=mt["standing_zoom_password"],
                schedule=schedule,
            )
        finally:
            clear_tenant_context()
    except Exception as e:  # email must not fail the signup
        logger.warning("Self-serve welcome email failed", member_id=member_id, error=str(e))

    logger.info(
        "Self-serve online membership enrolled",
        org=org_slug, member_id=member_id, membership_id=membership_id,
        trial_days=trial_days, charged_now=charged_now,
    )
    return {
        "membership_id": membership_id,
        "member_id": member_id,
        "user_id": user_id,
        "org_slug": org["slug"],
        "membership_name": mt["name"],
        "status": "trialing" if trial_days > 0 else "active",
        "trial_end": trial_end.isoformat() if trial_end else None,
        "price_display": price_display,
        "charged_now": charged_now,
        "payment_id": payment_id,
    }
