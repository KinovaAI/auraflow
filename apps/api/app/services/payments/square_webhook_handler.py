"""AuraFlow — Square Webhook Handler

Mirror of webhook_handler.py for the Square side. Verifies the
signature using SQUARE_WEBHOOK_SIGNATURE_KEY (HMAC-SHA256 of
notification_url + raw body, base64-encoded), dedupes via the
existing af_global.processed_webhook_events table with
provider='square', and routes to per-event-type async handlers.

Events handled:

  payment.created                — Sync transactions row (mark
                                   completed), record actual settled
                                   fee_cents (Square may adjust).
  payment.updated                — Sync status changes (COMPLETED,
                                   FAILED, APPROVED→FAILED, etc.).
  refund.created / refund.updated
                                — Sync refund status; auto-cancel
                                   class-pack bookings on full refund
                                   (mirrors the Stripe charge.refunded
                                   behavior).
  subscription.created
  subscription.updated           — Sync member_memberships status
                                   (and the KinovaAI platform sub if
                                   it's a KinovaAI account event).
                                   Respects freeze-one-way.
  invoice.payment_made           — Mark platform_invoices.status='paid',
                                   set paid_at.
  invoice.canceled
  invoice.published              — Informational status updates.
  oauth.authorization.revoked    — Flip org.billing_provider back to
                                   'stripe', clear Square columns,
                                   audit log + email owner.

Handlers are idempotent — a duplicate webhook delivery for the same
event_id is a no-op thanks to processed_webhook_events.
"""
import base64
import hashlib
import hmac
import json
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db


def verify_signature(notification_url: str, body: bytes, signature_header: str) -> bool:
    """HMAC-SHA256 of (notification_url + body), base64. Square sends
    the signature in the x-square-hmacsha256-signature header (or the
    deprecated x-square-signature). The notification_url is the URL
    Square POSTs to — must match what's configured in the Developer
    Dashboard exactly (https://api.auraflow.fit/webhooks/square)."""
    key = settings.SQUARE_WEBHOOK_SIGNATURE_KEY
    if not key:
        logger.warning("SQUARE_WEBHOOK_SIGNATURE_KEY not configured — rejecting webhook")
        return False
    if not signature_header:
        return False
    payload = (notification_url.encode("utf-8") + body)
    expected = base64.b64encode(
        hmac.new(key.encode("utf-8"), payload, hashlib.sha256).digest()
    ).decode("utf-8")
    return hmac.compare_digest(expected, signature_header)


async def _mark_processed(event_id: str, event_type: str = "") -> bool:
    """Returns True if this is the first time we've seen the event,
    False if already processed (duplicate delivery — skip)."""
    async with get_global_db() as db:
        # ON CONFLICT DO NOTHING + RETURNING distinguishes "we just
        # inserted (fresh)" from "row already existed (dup)" without
        # masking unrelated DB errors as duplicates. The .fetchval is
        # None on conflict, event_id on insert.
        inserted = await db.fetchval(
            """
            INSERT INTO af_global.processed_webhook_events
                (provider, event_id, event_type)
            VALUES ('square', $1, $2)
            ON CONFLICT (provider, event_id) DO NOTHING
            RETURNING event_id
            """,
            event_id, (event_type or "unknown")[:100],
        )
        return inserted is not None


async def _resolve_org_by_merchant(merchant_id: str) -> Optional[dict]:
    """Find which AuraFlow org owns the Square merchant. Webhook
    payloads include merchant_id at the top level for merchant-scoped
    events."""
    async with get_global_db() as db:
        row = await db.fetchrow(
            """
            SELECT id, schema_name, name, billing_provider
            FROM af_global.organizations
            WHERE square_merchant_id = $1
            """,
            merchant_id,
        )
    return dict(row) if row else None


# ── Event handlers ──────────────────────────────────────────────────────


async def _handle_payment_event(event: dict) -> dict:
    """payment.created / payment.updated — sync transactions row.

    Two paths:
      1) Existing row (member portal Web Payments SDK direct charge,
         renewal task) — UPDATE status / fee_cents.
      2) NO existing row — Payment Link path (workshops, private
         sessions, retail POS-send-link). We never knew the payment_id
         at link-creation time, so there's nothing to UPDATE. Fetch the
         order via Square API, read `order.metadata.auraflow_*`, then
         INSERT the transactions row AND the matching fulfillment row
         (course_enrollments / private_bookings update / pos_transactions
         update). Without this, every Payment Link sale silently leaves
         the buyer charged-but-not-fulfilled (Helene's Sound Bath
         2026-06-10, Analicia Jesse 2026-06-11).
    """
    data = (event.get("data") or {}).get("object") or {}
    payment = data.get("payment") or {}
    payment_id = payment.get("id")
    status = payment.get("status")
    merchant_id = event.get("merchant_id")
    if not payment_id:
        return {"handled": False, "reason": "no payment_id"}
    org = await _resolve_org_by_merchant(merchant_id) if merchant_id else None
    if not org:
        return {"handled": False, "reason": "merchant not registered"}

    settled_fee = ((payment.get("app_fee_money") or {}).get("amount")) or 0
    amount = ((payment.get("amount_money") or {}).get("amount")) or 0
    order_id = payment.get("order_id")
    schema = org["schema_name"]

    async with get_tenant_db(schema_override=schema) as db:
        existing = await db.fetchval(
            "SELECT id FROM transactions WHERE square_payment_id = $1",
            payment_id,
        )

    if existing:
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                """
                UPDATE transactions
                SET status = CASE WHEN $2 = 'COMPLETED' THEN 'completed'
                                  WHEN $2 = 'FAILED' THEN 'failed'
                                  WHEN $2 = 'CANCELED' THEN 'voided'
                                  ELSE status END,
                    fee_cents = $3,
                    net_amount_cents = amount_cents - $3,
                    updated_at = NOW()
                WHERE square_payment_id = $1
                """,
                payment_id, status, settled_fee,
            )
        logger.info(
            "Square payment webhook synced (existing)",
            payment_id=payment_id, status=status, settled_fee=settled_fee,
            org=org["name"],
        )
        return {"handled": True, "payment_id": payment_id, "status": status, "path": "update"}

    # No existing row. Payment Link fulfillment path.
    if status != "COMPLETED" or not order_id:
        return {"handled": True, "payment_id": payment_id, "status": status, "path": "skipped_not_complete"}

    metadata = await _fetch_order_metadata(str(org["id"]), order_id)
    if not metadata:
        logger.warning(
            "Square Payment Link payment with no metadata — cannot fulfill",
            payment_id=payment_id, order_id=order_id, org=org["name"],
        )
        return {"handled": True, "payment_id": payment_id, "path": "no_metadata"}

    result = await _fulfill_payment_link(
        schema=schema,
        payment_id=payment_id,
        amount_cents=amount,
        fee_cents=settled_fee,
        metadata=metadata,
    )
    logger.info(
        "Square Payment Link fulfilled via webhook",
        payment_id=payment_id, org=org["name"], **result,
    )
    return {"handled": True, "payment_id": payment_id, "status": status, "path": "insert", **result}


async def _fetch_order_metadata(org_id: str, order_id: str) -> Optional[dict]:
    """Retrieve a Square Order to read its `metadata` field. We don't
    cache it locally because the order is created Square-side by the
    Payment Link API; we never see it until the webhook fires."""
    try:
        from app.services.payments.billing_dispatcher import _resolve_provider
        ctx = await _resolve_provider(org_id)
        token = ctx.get("merchant_access_token")
        if not token:
            return None
        import httpx
        async with httpx.AsyncClient(timeout=15) as c:
            resp = await c.get(
                f"https://connect.squareup.com/v2/orders/{order_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Square-Version": "2026-01-22",
                },
            )
        if resp.status_code != 200:
            logger.warning("Order fetch failed", order_id=order_id, code=resp.status_code)
            return None
        return ((resp.json() or {}).get("order") or {}).get("metadata") or {}
    except Exception as e:
        logger.error("Order metadata fetch error", order_id=order_id, error=str(e))
        return None


async def _insert_transaction_if_absent(
    db, member_id, amount_cents, txn_type, description, payment_id, fee_cents,
):
    """Idempotent insert. transactions has no UNIQUE on square_payment_id
    (only a partial index), so we SELECT then INSERT under the same db
    connection; the webhook is the only writer for these ids, so the race
    window is narrow enough to be acceptable."""
    existing = await db.fetchval(
        "SELECT id FROM transactions WHERE square_payment_id = $1",
        payment_id,
    )
    if existing:
        return existing
    row = await db.fetchrow(
        """
        INSERT INTO transactions
            (member_id, amount_cents, type, status, description,
             square_payment_id, fee_cents, net_amount_cents, created_at)
        VALUES ($1, $2, $3, 'completed', $4, $5, $6, $7, NOW())
        RETURNING id
        """,
        member_id, amount_cents, txn_type, description,
        payment_id, fee_cents, amount_cents - fee_cents,
    )
    return row["id"]


async def _fulfill_payment_link(
    schema: str,
    payment_id: str,
    amount_cents: int,
    fee_cents: int,
    metadata: dict,
) -> dict:
    """Branch on `auraflow_checkout_type` (or `auraflow_pos_transaction_id`
    for retail) and write the appropriate fulfillment rows."""
    checkout_type = metadata.get("auraflow_checkout_type")
    member_id = metadata.get("auraflow_member_id")

    # Workshop enrollment
    if checkout_type == "course_enrollment":
        course_id = metadata.get("auraflow_course_id")
        if not (course_id and member_id):
            return {"outcome": "missing_ids_course"}
        async with get_tenant_db(schema_override=schema) as db:
            txn_id = await _insert_transaction_if_absent(
                db, member_id, amount_cents, "course_enrollment",
                "Workshop enrollment", payment_id, fee_cents,
            )
            enr = await db.fetchrow(
                """
                INSERT INTO course_enrollments
                    (course_id, member_id, status, paid_price_cents, transaction_id, enrolled_at)
                VALUES ($1, $2, 'enrolled', $3, $4, NOW())
                ON CONFLICT (course_id, member_id) DO NOTHING
                RETURNING id
                """,
                course_id, member_id, amount_cents, txn_id,
            )
        return {"outcome": "course_enrolled", "enrollment_id": str(enr["id"]) if enr else None}

    # Private session payment
    if checkout_type == "private_session":
        booking_id = metadata.get("auraflow_booking_id")
        if not booking_id:
            return {"outcome": "missing_booking_id"}
        async with get_tenant_db(schema_override=schema) as db:
            booking_row = await db.fetchrow(
                "SELECT member_id FROM private_bookings WHERE id = $1",
                booking_id,
            )
            resolved_member_id = member_id or (booking_row and str(booking_row["member_id"]))
            txn_id = await _insert_transaction_if_absent(
                db, resolved_member_id, amount_cents, "private_session",
                "Private session payment", payment_id, fee_cents,
            )
            await db.execute(
                """
                UPDATE private_bookings
                SET payment_status = 'paid',
                    transaction_id = $2,
                    updated_at = NOW()
                WHERE id = $1
                """,
                booking_id, txn_id,
            )
        return {"outcome": "private_session_paid", "booking_id": booking_id}

    # Retail POS send-link
    pos_txn_id = metadata.get("auraflow_pos_transaction_id")
    if pos_txn_id:
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                """
                UPDATE pos_transactions
                SET status = 'completed',
                    square_payment_id = $2,
                    updated_at = NOW()
                WHERE id = $1
                """,
                pos_txn_id, payment_id,
            )
            member_row = await db.fetchrow(
                "SELECT member_id FROM pos_transactions WHERE id = $1",
                pos_txn_id,
            )
            resolved_member_id = (
                str(member_row["member_id"])
                if member_row and member_row.get("member_id")
                else None
            )
            await _insert_transaction_if_absent(
                db, resolved_member_id, amount_cents, "pos_sale",
                "POS sale (send-link)", payment_id, fee_cents,
            )
        return {"outcome": "pos_paid", "pos_transaction_id": pos_txn_id}

    return {"outcome": "unknown_checkout_type", "metadata_keys": list(metadata.keys())}


async def _handle_refund_event(event: dict) -> dict:
    data = (event.get("data") or {}).get("object") or {}
    refund = data.get("refund") or {}
    refund_id = refund.get("id")
    payment_id = refund.get("payment_id")
    amount = ((refund.get("amount_money") or {}).get("amount")) or 0
    status = refund.get("status")
    merchant_id = event.get("merchant_id")
    org = await _resolve_org_by_merchant(merchant_id) if merchant_id else None
    if not org or not refund_id:
        return {"handled": False, "reason": "merchant not registered" if not org else "no refund_id"}

    schema = org["schema_name"]
    # Idempotency on refund_id, not just event_id: Square sends multiple
    # events per refund (refund.created → refund.updated → completed).
    # Each event has a unique event_id → all pass dedup → all run this
    # handler. If we just ADDED $amount each time, a 3-event lifecycle
    # would triple-count the refund. Instead: if this refund_id is
    # already on the row, OVERWRITE the amount to $amount (idempotent).
    # If it's a NEW refund_id (rare — partial refund #2 on same payment),
    # we still get the additive behavior via the ELSE branch.
    async with get_tenant_db(schema_override=schema) as db:
        await db.execute(
            """
            UPDATE transactions
            SET square_refund_id = COALESCE(square_refund_id, $1),
                refund_amount_cents = CASE
                    WHEN $4 != 'COMPLETED' THEN COALESCE(refund_amount_cents, 0)
                    WHEN square_refund_id = $1 THEN $3
                    ELSE COALESCE(refund_amount_cents, 0) + $3
                END,
                refunded_at = CASE WHEN $4 = 'COMPLETED' THEN NOW() ELSE refunded_at END,
                status = CASE
                    WHEN $4 = 'COMPLETED' AND (
                        CASE WHEN square_refund_id = $1
                             THEN $3
                             ELSE COALESCE(refund_amount_cents, 0) + $3
                        END
                    ) >= amount_cents THEN 'refunded'
                    WHEN $4 = 'COMPLETED' THEN 'partially_refunded'
                    ELSE status END,
                updated_at = NOW()
            WHERE square_payment_id = $2
            """,
            refund_id, payment_id, amount, status,
        )
    logger.info(
        "Square refund webhook synced",
        refund_id=refund_id, payment_id=payment_id, amount=amount,
        status=status, org=org["name"],
    )
    return {"handled": True, "refund_id": refund_id, "status": status}


async def _handle_subscription_event(event: dict) -> dict:
    data = (event.get("data") or {}).get("object") or {}
    sub = data.get("subscription") or {}
    sub_id = sub.get("id")
    status = (sub.get("status") or "").upper()
    if not sub_id:
        return {"handled": False, "reason": "no subscription_id"}

    # First check: is this KinovaAI's own platform subscription for a
    # studio? (organizations.square_subscription_id match)
    async with get_global_db() as db:
        plat_row = await db.fetchrow(
            """
            SELECT id, name FROM af_global.organizations
            WHERE square_subscription_id = $1
            """,
            sub_id,
        )
    if plat_row:
        logger.info(
            "KinovaAI platform subscription event synced",
            org_id=str(plat_row["id"]), sub_id=sub_id, status=status,
        )
        # We don't mutate org status from a subscription event — that
        # would conflict with the studio's own org.status lifecycle
        # (trial/active/cancelling/cancelled). Just log; the monthly
        # invoice job is the source of truth for payment health.
        return {"handled": True, "scope": "platform", "sub_id": sub_id}

    # Otherwise, this is a member-side subscription on a studio's own
    # Square account. Map to member_memberships row.
    merchant_id = event.get("merchant_id")
    org = await _resolve_org_by_merchant(merchant_id) if merchant_id else None
    if not org:
        return {"handled": False, "reason": "merchant not registered"}

    mapped = {
        "ACTIVE": "active",
        "PENDING": "active",
        "PAUSED": "frozen",
        "DEACTIVATED": "cancelled",
        "CANCELED": "cancelled",
    }.get(status)
    if not mapped:
        return {"handled": False, "reason": f"unknown status {status}"}

    schema = org["schema_name"]
    async with get_tenant_db(schema_override=schema) as db:
        # Freeze-one-way enforced: only allow flipping to 'active' if
        # the current row is NOT 'frozen'. Otherwise leave alone.
        current = await db.fetchrow(
            "SELECT id, status FROM member_memberships WHERE square_subscription_id = $1",
            sub_id,
        )
        if not current:
            return {"handled": False, "reason": "no local membership row"}
        if current["status"] == "frozen" and mapped == "active":
            logger.warning(
                "Square subscription webhook reports ACTIVE for a locally-frozen membership — ignoring",
                schema=schema, membership_id=str(current["id"]), sub_id=sub_id,
            )
            return {"handled": True, "scope": "member", "freeze_protected": True}
        await db.execute(
            """
            UPDATE member_memberships
            SET status = $1, updated_at = NOW()
            WHERE square_subscription_id = $2
            """,
            mapped, sub_id,
        )
    logger.info(
        "Member subscription webhook synced",
        schema=schema, sub_id=sub_id, status=mapped,
    )
    return {"handled": True, "scope": "member", "sub_id": sub_id, "status": mapped}


async def _handle_invoice_event(event: dict) -> dict:
    """invoice.payment_made / canceled / published.
    Updates af_global.platform_invoices for KinovaAI's monthly bills."""
    data = (event.get("data") or {}).get("object") or {}
    inv = data.get("invoice") or {}
    inv_id = inv.get("id")
    status = (inv.get("status") or "").upper()
    event_type = event.get("type", "")
    if not inv_id:
        return {"handled": False, "reason": "no invoice_id"}

    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT id, organization_id FROM af_global.platform_invoices "
            "WHERE square_invoice_id = $1",
            inv_id,
        )
    if not row:
        return {"handled": False, "reason": "invoice not tracked"}

    if event_type == "invoice.payment_made" or status == "PAID":
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.platform_invoices
                SET status = 'paid', paid_at = NOW()
                WHERE id = $1
                """,
                row["id"],
            )
        logger.info(
            "Platform invoice marked paid",
            invoice_id=inv_id, platform_invoice_id=str(row["id"]),
        )
        return {"handled": True, "marked": "paid"}

    if event_type == "invoice.canceled" or status == "CANCELED":
        async with get_global_db() as db:
            await db.execute(
                "UPDATE af_global.platform_invoices SET status = 'canceled' "
                "WHERE id = $1",
                row["id"],
            )
        return {"handled": True, "marked": "canceled"}

    # Informational
    return {"handled": True, "status": status}


async def _handle_oauth_revoked(event: dict) -> dict:
    """oauth.authorization.revoked — studio disconnected via Square
    Dashboard or token revoke. Flip billing_provider back to 'stripe',
    clear Square columns, audit + email owner."""
    data = (event.get("data") or {}).get("object") or {}
    revocation = data.get("revocation") or {}
    merchant_id = revocation.get("merchant_id") or event.get("merchant_id")
    org = await _resolve_org_by_merchant(merchant_id) if merchant_id else None
    if not org:
        return {"handled": False, "reason": "merchant not registered"}

    async with get_global_db() as db:
        await db.execute(
            """
            UPDATE af_global.organizations
            SET square_access_token_encrypted = NULL,
                square_refresh_token_encrypted = NULL,
                square_token_expires_at = NULL,
                billing_provider = 'stripe',
                updated_at = NOW()
            WHERE id = $1
            """,
            org["id"],
        )
    logger.warning(
        "Square OAuth revoked — billing_provider reverted to stripe",
        org_id=str(org["id"]), name=org["name"], merchant_id=merchant_id,
    )
    # Audit + email left for Phase 11 (admin tooling). Logging the
    # event is enough for now; ops can follow up manually.
    return {"handled": True, "org_id": str(org["id"])}


# ── Public entrypoint ──────────────────────────────────────────────────


async def _handle_terminal_checkout_event(event: dict) -> dict:
    """Square POS Terminal API webhook handler.

    Lifecycle on the Square side:
      PENDING → IN_PROGRESS → COMPLETED | CANCELED | CANCEL_REQUESTED
    Each transition fires terminal.checkout.updated. We only care about
    the terminal states.

    On COMPLETED:
      1. Resolve the payment_id from the event payload
      2. ALWAYS save the card on file via post-payment Cards API call
         (no hardware prompt — feedback_always_save_card)
      3. Record a transactions row with square_payment_id
      4. If the checkout was tied to a membership_type_id, create the
         member_memberships row + (for recurring types) schedule the
         Square Subscription to start next cycle using the saved card.
    """
    data = (event.get("data") or {}).get("object") or {}
    checkout = data.get("checkout") or {}
    checkout_id = checkout.get("id")
    status = (checkout.get("status") or "").upper()
    reference_id = checkout.get("reference_id")  # our local pos_terminal_checkouts.id
    payment_ids = checkout.get("payment_ids") or []
    cancel_reason = checkout.get("cancel_reason")

    merchant_id = event.get("merchant_id")
    org = await _resolve_org_by_merchant(merchant_id) if merchant_id else None
    if not org:
        return {"handled": False, "reason": "merchant not registered"}
    if not checkout_id or not reference_id:
        return {"handled": False, "reason": "missing checkout_id or reference_id"}

    schema = org["schema_name"]

    # Fetch our local row by reference_id (UUID we passed in)
    async with get_tenant_db(schema_override=schema) as db:
        local = await db.fetchrow(
            """
            SELECT id, member_id, amount_cents, app_fee_cents, description,
                   square_customer_id, membership_type_id, status,
                   square_payment_id
            FROM pos_terminal_checkouts
            WHERE id::text = $1 OR square_checkout_id = $2
            """,
            reference_id, checkout_id,
        )
    if not local:
        logger.warning(
            "Square terminal.checkout for unknown local row",
            reference_id=reference_id, checkout_id=checkout_id,
        )
        return {"handled": False, "reason": "no local checkout row"}

    if status in ("CANCELED", "CANCEL_REQUESTED"):
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                """
                UPDATE pos_terminal_checkouts
                SET status='cancelled', completed_at=NOW(),
                    failure_reason=$2, square_checkout_id=$3
                WHERE id=$1 AND status IN ('pending','in_progress')
                """,
                local["id"], cancel_reason or "cancelled", checkout_id,
            )
        return {"handled": True, "checkout_id": checkout_id, "status": "cancelled"}

    if status != "COMPLETED":
        # PENDING / IN_PROGRESS — keep our row in_progress, sync the
        # square_checkout_id in case it wasn't set yet (race between
        # the create response and the first webhook).
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                """
                UPDATE pos_terminal_checkouts
                SET square_checkout_id = COALESCE(square_checkout_id, $2),
                    status = CASE WHEN status='pending' THEN 'in_progress' ELSE status END
                WHERE id=$1
                """,
                local["id"], checkout_id,
            )
        return {"handled": True, "checkout_id": checkout_id, "status": status.lower()}

    # ── COMPLETED path ─────────────────────────────────────────────────
    payment_id = payment_ids[0] if payment_ids else None
    if not payment_id:
        # COMPLETED with no payment_ids should not happen in practice —
        # Square's contract is that a successful checkout has at least
        # one payment_id. If it does happen we DON'T mark the row
        # completed: that would propagate NULL payment_id into the
        # membership creation and the saved-card row. Instead, mark
        # the row failed, log, and let staff resolve manually.
        logger.error(
            "terminal.checkout COMPLETED but no payment_ids — refusing to record",
            checkout_id=checkout_id, local_id=str(local["id"]),
        )
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                """
                UPDATE pos_terminal_checkouts
                SET status='failed', completed_at=NOW(),
                    failure_reason='completed_without_payment_id'
                WHERE id=$1 AND status IN ('pending','in_progress')
                """,
                local["id"],
            )
        return {
            "handled": False,
            "reason": "completed_without_payment_id",
            "checkout_id": checkout_id,
        }

    # Save card on file (no hardware prompt, no toggle)
    from app.services.payments.square_oauth_service import square_oauth_service
    from app.services.payments.square_pos_service import square_pos_service
    from app.services.payments.square_service import square_service

    access_token = await square_oauth_service.get_merchant_access_token(str(org["id"]))
    saved_card: Optional[dict] = None
    payment_details: Optional[dict] = None
    if access_token and payment_id and local["square_customer_id"]:
        # Pull the payment so we know the cardholder name + fee details
        payment_details = await square_service.get_payment(
            payment_id=payment_id, access_token=access_token,
        )
        # Save card via Cards API (source_id=payment_id, no prompt)
        saved_card = await square_pos_service.save_card_from_payment(
            merchant_access_token=access_token,
            payment_id=payment_id,
            customer_id=local["square_customer_id"],
        )

    async with get_tenant_db(schema_override=schema) as db:
        # Update the checkout row
        await db.execute(
            """
            UPDATE pos_terminal_checkouts
            SET status='completed', completed_at=NOW(),
                square_checkout_id=$2, square_payment_id=$3, square_card_id=$4
            WHERE id=$1
            """,
            local["id"], checkout_id, payment_id,
            saved_card.get("card_id") if saved_card else None,
        )

        # Stamp the card on the member row (so future renewals / saved-card
        # charges find it without re-querying Square).
        if saved_card and saved_card.get("card_id"):
            await db.execute(
                """
                UPDATE members
                SET square_card_on_file_id=$2,
                    square_card_on_file_brand=$3,
                    square_card_on_file_last4=$4,
                    square_card_on_file_exp_month=$5,
                    square_card_on_file_exp_year=$6,
                    square_card_on_file_saved_at=NOW()
                WHERE id=$1
                """,
                local["member_id"], saved_card["card_id"],
                saved_card.get("card_brand"), saved_card.get("last_4"),
                saved_card.get("exp_month"), saved_card.get("exp_year"),
            )

        # Record the transaction in our ledger (idempotent on square_payment_id)
        from app.services.payments.stripe_service import StripeService
        stripe_svc = StripeService()
    await stripe_svc.record_transaction({
        "member_id": str(local["member_id"]),
        "amount_cents": local["amount_cents"],
        "type": "pos_sale",
        "status": "completed",
        "description": local["description"] or "POS sale",
        "square_payment_id": payment_id,
        "fee_cents": local["app_fee_cents"],
        "net_amount_cents": local["amount_cents"] - local["app_fee_cents"],
    })

    # If this was a membership purchase, create the member_memberships
    # row + (for recurring types) schedule the Square Subscription.
    if local["membership_type_id"]:
        await _activate_pos_membership(
            schema=schema,
            org_id=str(org["id"]),
            access_token=access_token,
            member_id=str(local["member_id"]),
            membership_type_id=str(local["membership_type_id"]),
            square_customer_id=local["square_customer_id"],
            square_card_id=saved_card.get("card_id") if saved_card else None,
        )

    return {
        "handled": True,
        "checkout_id": checkout_id,
        "status": "completed",
        "payment_id": payment_id,
        "card_saved": bool(saved_card),
    }


async def _activate_pos_membership(
    schema: str,
    org_id: str,
    access_token: Optional[str],
    member_id: str,
    membership_type_id: str,
    square_customer_id: Optional[str],
    square_card_id: Optional[str],
) -> None:
    """Membership activation path for a POS-paid sale.

    For non-recurring (class_pack / day_pass / single_class): insert the
    row with classes_remaining + ends_at based on the type's duration.

    For recurring (unlimited monthly/annual): also schedule a Square
    Subscription with start_date = today + cycle so the next charge is
    automatic. The current cycle was paid in person at the POS.
    """
    async with get_tenant_db(schema_override=schema) as db:
        mt = await db.fetchrow(
            """
            SELECT id, name, type, price_cents, billing_period, duration_days,
                   class_count, square_plan_variation_id, trial_starts_on_first_class
            FROM membership_types WHERE id = $1
            """,
            membership_type_id,
        )
        if not mt:
            return

        is_recurring = mt["type"] == "unlimited" or mt["billing_period"] in (
            "monthly", "annual", "yearly", "weekly", "quarterly",
        )
        ends_at_sql = "NULL"
        if mt["duration_days"] and not mt["trial_starts_on_first_class"]:
            ends_at_sql = f"NOW() + INTERVAL '{int(mt['duration_days'])} days'"

        # Non-recurring (class pack / drop-in pack)
        if not is_recurring:
            await db.execute(
                f"""
                INSERT INTO member_memberships
                    (member_id, membership_type_id, status, starts_at, ends_at,
                     classes_remaining, billing_provider, created_at)
                VALUES ($1, $2, 'active', NOW(), {ends_at_sql}, $3, 'square', NOW())
                """,
                member_id, membership_type_id, mt["class_count"],
            )
            return

    # Recurring → schedule Square Subscription for next cycle
    if not access_token or not square_customer_id or not square_card_id:
        logger.warning(
            "Cannot schedule POS recurring sub — missing token/customer/card",
            member_id=member_id, membership_type_id=membership_type_id,
        )
        return

    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from app.services.payments.billing_dispatcher import resolve_square_cadence
    from app.services.payments.square_service import square_service

    cycle_days = {
        "monthly": 30, "weekly": 7, "annual": 365, "yearly": 365, "quarterly": 90,
    }.get(mt["billing_period"], 30)
    start_date = (
        datetime.now(ZoneInfo("America/Los_Angeles")) + timedelta(days=cycle_days)
    ).strftime("%Y-%m-%d")
    cadence = resolve_square_cadence(mt["billing_period"])

    # Ensure we have a plan variation cached
    plan_variation_id = mt["square_plan_variation_id"]
    if not plan_variation_id:
        plan = await square_service.create_subscription_plan(
            merchant_access_token=access_token,
            name=mt["name"], price_cents=mt["price_cents"], cadence=cadence,
        )
        plan_variation_id = plan["plan_variation_id"]
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                """
                UPDATE membership_types
                SET square_plan_id=$1, square_plan_variation_id=$2
                WHERE id=$3
                """,
                plan["plan_id"], plan_variation_id, membership_type_id,
            )

    # Fetch merchant location_id
    async with get_global_db() as gdb:
        loc_row = await gdb.fetchrow(
            "SELECT square_location_id FROM af_global.organizations WHERE id=$1",
            org_id,
        )
    if not loc_row or not loc_row["square_location_id"]:
        # POS sale completed and money already moved; the recurring
        # subscription wiring is the deferred piece. Log loud so ops
        # can repair the missing location and manually create the sub.
        logger.error(
            "Cannot create recurring sub after POS sale — square_location_id missing on org",
            org_id=org_id, member_id=member_id, membership_type_id=membership_type_id,
        )
        return
    sub = await square_service.create_subscription(
        merchant_access_token=access_token,
        merchant_location_id=loc_row["square_location_id"],
        plan_variation_id=plan_variation_id,
        customer_id=square_customer_id,
        card_id=square_card_id,
        start_date=start_date,
        reference_id=member_id,
    )
    async with get_tenant_db(schema_override=schema) as db:
        await db.execute(
            """
            INSERT INTO member_memberships
                (member_id, membership_type_id, status, starts_at,
                 square_subscription_id, billing_provider, created_at)
            VALUES ($1, $2, 'active', NOW(), $3, 'square', NOW())
            """,
            member_id, membership_type_id, sub["subscription_id"],
        )


_HANDLERS = {
    "payment.created": _handle_payment_event,
    "payment.updated": _handle_payment_event,
    "refund.created": _handle_refund_event,
    "refund.updated": _handle_refund_event,
    "subscription.created": _handle_subscription_event,
    "subscription.updated": _handle_subscription_event,
    "invoice.payment_made": _handle_invoice_event,
    "invoice.canceled": _handle_invoice_event,
    "invoice.published": _handle_invoice_event,
    "invoice.updated": _handle_invoice_event,
    "oauth.authorization.revoked": _handle_oauth_revoked,
    "terminal.checkout.created": _handle_terminal_checkout_event,
    "terminal.checkout.updated": _handle_terminal_checkout_event,
}


async def handle_event(event: dict) -> dict:
    """Route a verified, deduped Square event to the right handler."""
    event_type = event.get("type", "")
    event_id = event.get("event_id") or event.get("id")
    if not event_id:
        logger.warning("Square webhook missing event_id", event_type=event_type)
        return {"handled": False, "reason": "no event_id"}

    fresh = await _mark_processed(event_id, event_type)
    if not fresh:
        return {"handled": True, "duplicate": True, "event_id": event_id}

    handler = _HANDLERS.get(event_type)
    if not handler:
        logger.info("Square event type ignored", event_type=event_type)
        return {"handled": True, "event_type": event_type, "ignored": True}

    try:
        return await handler(event)
    except Exception as e:
        logger.exception(
            "Square webhook handler crashed",
            event_type=event_type, event_id=event_id, error=str(e),
        )
        # Roll back the dedup claim so Square's retry can actually
        # retry. Without this, a transient handler failure (DB blip,
        # rate limit, partial Cards-API outage) poisons the event for
        # good — every retry sees the dedup row and skips processing.
        try:
            async with get_global_db() as db:
                await db.execute(
                    "DELETE FROM af_global.processed_webhook_events "
                    "WHERE provider='square' AND event_id = $1",
                    event_id,
                )
        except Exception:
            pass  # don't mask the original error
        return {"handled": False, "error": str(e)}
