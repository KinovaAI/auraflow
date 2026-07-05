"""AuraFlow — Stripe Webhook Handler

Processes Stripe webhook events: checkout completion, invoice payments,
subscription lifecycle, payment failures, and refunds.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe

from app.core.config import settings
from app.core.logging import logger
from app.core.tenant_context import set_tenant_context, clear_tenant_context
from app.db.session import get_tenant_db, get_global_db
from app.services.payments.stripe_service import StripeService
from app.services.email.email_service import EmailService


def _first_item_current_period_end(subscription: dict) -> Optional[int]:
    """Pull current_period_end from the first subscription item.

    Stripe API 2025-11-17.clover moved per-item billing periods OFF the
    subscription object and onto each subscription item. For our use
    case every sub has exactly one item so the first one carries the
    canonical period end. Returns the UNIX timestamp or None.
    """
    items = subscription.get("items") or {}
    if not isinstance(items, dict):
        return None
    data = items.get("data") or []
    if not data:
        return None
    return data[0].get("current_period_end")


class StripeWebhookHandler:

    def __init__(self):
        self.stripe_svc = StripeService()
        self.email_svc = EmailService()

    async def verify_signature(self, payload: bytes, sig_header: str) -> dict:
        """Verify the Stripe webhook signature. Tries platform secret first, then org secrets.

        Was a sync method that did `asyncio.run()` inside a ThreadPoolExecutor
        to fetch org-specific webhook secrets — that antipattern produced
        `RuntimeError: Event loop is closed` on every webhook (the thread's
        event loop closed while asyncpg's SSL transport had a pending
        cleanup). Now async; the caller awaits directly.
        """
        from app.db.session import get_global_db
        from app.utils.encryption import decrypt_credential

        secrets_to_try: list[str] = []
        if settings.STRIPE_WEBHOOK_SECRET:
            secrets_to_try.append(settings.STRIPE_WEBHOOK_SECRET)

        # Also try org-specific webhook secrets (for direct mode studios)
        async with get_global_db() as db:
            rows = await db.fetch(
                "SELECT stripe_webhook_secret_encrypted FROM af_global.organizations WHERE stripe_direct_mode = TRUE AND stripe_webhook_secret_encrypted IS NOT NULL"
            )
            for r in rows:
                try:
                    secret = await decrypt_credential(db, r["stripe_webhook_secret_encrypted"])
                    secrets_to_try.append(secret)
                except Exception:
                    pass

        if not secrets_to_try:
            raise ValueError("No Stripe webhook secrets configured")

        for secret in secrets_to_try:
            try:
                # tolerance=300 enforces Stripe's industry-standard 5-min
                # timestamp window. Stripe SDK default is 300s but being
                # explicit guards against a future SDK default change that
                # would open a replay window.
                event = stripe.Webhook.construct_event(
                    payload, sig_header, secret, tolerance=300
                )
                return event
            except stripe.error.SignatureVerificationError:
                continue

        raise ValueError("Stripe webhook signature verification failed with all known secrets")

    async def handle_event(self, event: dict) -> dict:
        """Route a Stripe event to the appropriate handler.

        Uses event ID deduplication to prevent processing the same webhook
        event more than once (Stripe may retry delivery).
        """
        event_type = event.get("type", "")
        event_id = event.get("id")
        logger.info("Stripe webhook received", event_type=event_type, event_id=event_id)

        # Idempotency: claim the event up front. The CONFLICT clause closes
        # the millisecond race where two simultaneous Stripe retries both
        # passed a SELECT-then-INSERT check before either had written. The
        # row is deleted on handler failure so Stripe's retry can succeed.
        #
        # Note: the unique constraint on processed_webhook_events is
        # (provider, event_id) since the Square migration — must include
        # both columns in the INSERT and target the same in ON CONFLICT.
        if event_id:
            async with get_global_db() as db:
                claimed = await db.fetchval(
                    """
                    INSERT INTO af_global.processed_webhook_events
                        (provider, event_id, event_type, processed_at)
                    VALUES ('stripe', $1, $2, NOW())
                    ON CONFLICT (provider, event_id) DO NOTHING
                    RETURNING event_id
                    """,
                    event_id, event_type,
                )
                if not claimed:
                    logger.info("Duplicate webhook event skipped", event_id=event_id)
                    return {"status": "duplicate", "event_id": event_id}

        handler_map = {
            "checkout.session.completed": self._handle_checkout_completed,
            "invoice.payment_succeeded": self._handle_invoice_paid,
            "invoice.payment_failed": self._handle_invoice_failed,
            "customer.subscription.updated": self._handle_subscription_updated,
            "customer.subscription.deleted": self._handle_subscription_deleted,
            "customer.subscription.paused": self._handle_subscription_paused,
            "customer.subscription.resumed": self._handle_subscription_resumed,
            "charge.refunded": self._handle_charge_refunded,
            "charge.dispute.created": self._handle_dispute_created,
            "account.updated": self._handle_account_updated,
        }

        handler = handler_map.get(event_type)
        if handler:
            # Resolve tenant schema from event metadata
            data_obj = event["data"]["object"]
            # Pass full event so _resolve_schema can also use event["account"]
            # for Connect-routed events (charges/refunds on a connected account
            # come with `account: "acct_xxx"` set on the event itself).
            schema = await self._resolve_schema(data_obj, event=event)
            # Set tenant context so downstream services (StripeService, etc.) work
            if schema:
                # Resolve the real organization_id so email service can find org credentials
                org_id = None
                async with get_global_db() as db:
                    org_row = await db.fetchrow(
                        "SELECT id FROM af_global.organizations WHERE schema_name = $1", schema
                    )
                    if org_row:
                        org_id = str(org_row["id"])
                set_tenant_context(
                    organization_id=org_id or "webhook",
                    schema_name=schema,
                    slug=schema.replace("af_tenant_", ""),
                )
            try:
                result = await handler(data_obj, schema)
                return result
            except Exception:
                # Release our idempotency claim so Stripe's retry can
                # actually retry. Without this, a transient handler
                # failure (DB blip, rate limit) would poison the
                # event for good — every retry would see it in the
                # dedup table and skip without processing.
                if event_id:
                    try:
                        async with get_global_db() as db:
                            await db.execute(
                                "DELETE FROM af_global.processed_webhook_events WHERE provider = 'stripe' AND event_id = $1",
                                event_id,
                            )
                    except Exception:
                        pass  # Don't mask the original error
                raise
            finally:
                if schema:
                    clear_tenant_context()

        logger.info("Unhandled webhook event type", event_type=event_type)
        return {"status": "ignored", "event_type": event_type}

    async def _resolve_schema(self, data_obj: dict, event: Optional[dict] = None) -> Optional[str]:
        """Resolve tenant schema from Stripe event metadata or customer lookup.

        Resolution order (first match wins):
          1. data_obj.metadata.auraflow_org_schema  (set by our own create flows)
          2. event.account                          (Connect events — event-level account ID)
          3. data_obj.customer                      (lookup tenant whose member has this customer)
          4. data_obj.id                            (account.* events — the account itself)
        """
        metadata = data_obj.get("metadata") or {}
        schema = metadata.get("auraflow_org_schema")
        if schema:
            return schema

        # Connect-event fast path: events on a connected account include the
        # account ID at the EVENT level (not on the data object). For a
        # `charge.refunded` on tenant-A's connected account, this lets us
        # route to tenant-A without a customer lookup or metadata round-trip.
        if event:
            connected_account = event.get("account")
            if connected_account:
                async with get_global_db() as db:
                    org = await db.fetchrow(
                        "SELECT schema_name FROM af_global.organizations WHERE stripe_account_id = $1",
                        connected_account,
                    )
                    if org:
                        return org["schema_name"]

        # Fallback: look up tenant by Stripe customer ID
        customer_id = data_obj.get("customer")
        if customer_id:
            async with get_global_db() as db:
                schemas = await db.fetch(
                    "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
                )
            for row in schemas:
                async with get_tenant_db(schema_override=row["schema_name"]) as db:
                    member = await db.fetchrow(
                        "SELECT id FROM members WHERE stripe_customer_id = $1", customer_id
                    )
                    if member:
                        return row["schema_name"]

        # Fallback: Connect account events — look up org by stripe_account_id
        obj_type = data_obj.get("object")
        if obj_type == "account":
            account_id = data_obj.get("id")
            if account_id:
                async with get_global_db() as db:
                    org = await db.fetchrow(
                        "SELECT schema_name FROM af_global.organizations WHERE stripe_account_id = $1",
                        account_id,
                    )
                    if org:
                        return org["schema_name"]

        return None

    # ── Checkout Session Completed ────────────────────────────────────────────

    async def _handle_checkout_completed(self, session: dict, schema: Optional[str] = None) -> dict:
        """Handle completed Checkout session — auto-assign membership to member."""
        metadata = session.get("metadata", {}) or {}
        member_id = metadata.get("auraflow_member_id")
        membership_type_id = metadata.get("auraflow_membership_type_id")
        type_name = metadata.get("type_name", "Membership")

        checkout_type = metadata.get("auraflow_checkout_type")
        amount_total = session.get("amount_total", 0)

        # ── Gift card purchase fulfillment ──
        # The buyer paid via Stripe; create the actual gift card row
        # now (it was deferred so we never insert until the money has
        # actually arrived). Metadata carries every detail needed —
        # amount, recipient, message, expiry, purchaser.
        if metadata.get("auraflow_gift_card") == "true" and schema:
            from app.services.payments.gift_card_service import GiftCardService
            gc_svc = GiftCardService()
            from datetime import datetime as _dt
            try:
                expires_at = (
                    _dt.fromisoformat(metadata["expires_at"])
                    if metadata.get("expires_at") else None
                )
            except (ValueError, TypeError):
                expires_at = None
            try:
                gc_row = await gc_svc.create_gift_card(
                    amount_cents=int(metadata.get("amount_cents", amount_total)),
                    purchaser_member_id=metadata.get("purchaser_member_id"),
                    recipient_email=metadata.get("recipient_email"),
                    recipient_name=metadata.get("recipient_name"),
                    message=metadata.get("message"),
                    purchased_by_name=metadata.get("purchased_by_name"),
                    expires_at=expires_at,
                )
            except Exception as e:
                logger.error(
                    "Gift-card webhook fulfillment failed",
                    session_id=session.get("id"), error=str(e),
                )
                raise
            # Record the transaction so the purchase shows up in
            # payments / reports
            fee_cents = int(amount_total * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
            await self.stripe_svc.record_transaction({
                "member_id": metadata.get("purchaser_member_id"),
                "amount_cents": amount_total,
                "type": "payment",
                "status": "completed",
                "description": f"Gift card purchase — {gc_row['code']}",
                "stripe_payment_intent_id": session.get("payment_intent"),
                "fee_cents": fee_cents,
                "net_amount_cents": amount_total - fee_cents,
            })
            logger.info(
                "Gift card created via Stripe webhook",
                gift_card_id=gc_row["id"], code=gc_row["code"],
                amount_cents=amount_total,
            )
            return {"status": "processed", "event": "checkout.session.completed",
                    "gift_card_id": str(gc_row["id"])}

        # ── POS transaction fulfillment ──
        pos_txn_id = metadata.get("auraflow_pos_transaction_id")
        if pos_txn_id and schema:
            async with get_tenant_db(schema_override=schema) as db:
                pos_row = await db.fetchrow(
                    """UPDATE pos_transactions
                       SET status = 'completed', stripe_payment_id = $2, updated_at = NOW()
                       WHERE id = $1 AND status = 'pending'
                       RETURNING member_id, total_cents""",
                    pos_txn_id, session.get("payment_intent"),
                )
                # Record in transactions table so it shows in payments
                if pos_row:
                    fee_cents = int(amount_total * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
                    await self.stripe_svc.record_transaction({
                        "member_id": str(pos_row["member_id"]) if pos_row["member_id"] else None,
                        "amount_cents": pos_row["total_cents"],
                        "type": "payment",
                        "status": "completed",
                        "description": "Retail purchase",
                        "stripe_payment_intent_id": session.get("payment_intent"),
                        "fee_cents": fee_cents,
                        "net_amount_cents": pos_row["total_cents"] - fee_cents,
                    })
            logger.info("POS transaction completed via checkout", txn_id=pos_txn_id)
            return {"status": "processed", "event": "checkout.session.completed", "pos_txn_id": pos_txn_id}

        # ── Course enrollment fulfillment ──
        if checkout_type == "course_enrollment":
            course_id = metadata.get("auraflow_course_id")
            if not member_id or not course_id:
                logger.warning("Course checkout missing metadata", session_id=session.get("id"))
                return {"status": "ignored", "reason": "missing course metadata"}

            from app.services.scheduling.course_service import CourseService
            course_svc = CourseService()
            try:
                enrollment = await course_svc.enroll_member(course_id, member_id)
                fee_cents = int(amount_total * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
                await self.stripe_svc.record_transaction({
                    "member_id": member_id,
                    "amount_cents": amount_total,
                    "type": "payment",
                    "status": "completed",
                    "description": f"Workshop enrollment: {metadata.get('item_name', 'Workshop')}",
                    "stripe_payment_intent_id": session.get("payment_intent"),
                    "fee_cents": fee_cents,
                    "net_amount_cents": amount_total - fee_cents,
                })
                member = await self._get_member(member_id, schema)
                if member:
                    await self.email_svc.send_payment_receipt(
                        member_id=member_id,
                        to_email=member["email"],
                        member_name=member["first_name"],
                        amount_display=f"${amount_total / 100:.2f}",
                        description=f"Workshop: {metadata.get('item_name', 'Workshop')}",
                    )
                logger.info("Course enrollment via checkout", course_id=course_id, member_id=member_id)
                return {"status": "processed", "event": "checkout.session.completed", "enrollment_id": str(enrollment["id"])}
            except ValueError as e:
                logger.error("Course enrollment failed", course_id=course_id, error=str(e))
                return {"status": "error", "reason": str(e)}

        # ── Private session payment fulfillment ──
        if checkout_type == "private_session":
            booking_id = metadata.get("auraflow_booking_id")
            if not booking_id:
                logger.warning("Private session checkout missing booking_id", session_id=session.get("id"))
                return {"status": "ignored", "reason": "missing booking metadata"}

            from app.services.scheduling.private_session_service import PrivateSessionService
            ps_svc = PrivateSessionService()

            # Try to confirm (pending→confirmed), but also handle already-confirmed bookings
            confirmed = await ps_svc.confirm_booking(booking_id)

            # Even if booking was already confirmed/completed (staff clicked confirm first),
            # still record payment and mark as paid
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute(
                    "UPDATE private_bookings SET payment_status = 'paid', updated_at = NOW() WHERE id = $1",
                    booking_id,
                )

                # If this is a package purchase, create membership with credits
                package_sessions = metadata.get("auraflow_package_sessions")
                package_service_id = metadata.get("auraflow_package_service_id")
                if package_sessions and member_id:
                    import uuid as _uuid
                    sessions_count = int(package_sessions)
                    # Find the membership type linked to this service
                    svc_row = await db.fetchrow(
                        "SELECT required_membership_type_id, name FROM private_services WHERE id = $1",
                        package_service_id,
                    ) if package_service_id else None

                    membership_type_id = svc_row["required_membership_type_id"] if svc_row and svc_row.get("required_membership_type_id") else None

                    if membership_type_id:
                        # Check for existing active pack and add credits
                        existing = await db.fetchrow(
                            "SELECT id, classes_remaining FROM member_memberships WHERE member_id = $1 AND membership_type_id = $2 AND status = 'active'",
                            member_id, str(membership_type_id),
                        )
                        if existing:
                            await db.execute(
                                "UPDATE member_memberships SET classes_remaining = classes_remaining + $1, updated_at = NOW() WHERE id = $2",
                                sessions_count - 1, str(existing["id"]),  # -1 because first session is this booking
                            )
                            logger.info("Package credits added to existing membership", member_id=member_id, added=sessions_count - 1)
                        else:
                            await db.execute(
                                """INSERT INTO member_memberships (id, member_id, membership_type_id, status, starts_at, classes_remaining)
                                   VALUES ($1, $2, $3, 'active', NOW(), $4)""",
                                str(_uuid.uuid4()), member_id, str(membership_type_id), sessions_count - 1,
                            )
                            logger.info("Package membership created", member_id=member_id, credits=sessions_count - 1)
                    else:
                        # No membership type linked — create a generic credit entry
                        # Use the service name as description
                        svc_name = svc_row["name"] if svc_row else "Private Session Package"
                        # Find or create a membership type for this package
                        mt_row = await db.fetchrow(
                            "SELECT id FROM membership_types WHERE name = $1", f"{svc_name} Credits",
                        )
                        if not mt_row:
                            mt_id = str(_uuid.uuid4())
                            await db.execute(
                                """INSERT INTO membership_types (id, name, membership_type, price_cents, class_count, billing_period, auto_renew, is_active, visibility)
                                   VALUES ($1, $2, 'class_pack', $3, $4, NULL, FALSE, TRUE, 'unlisted')""",
                                mt_id, f"{svc_name} Credits", amount_total, sessions_count,
                            )
                        else:
                            mt_id = str(mt_row["id"])
                        await db.execute(
                            """INSERT INTO member_memberships (id, member_id, membership_type_id, status, starts_at, classes_remaining)
                               VALUES ($1, $2, $3, 'active', NOW(), $4)""",
                            str(_uuid.uuid4()), member_id, mt_id, sessions_count - 1,
                        )
                        logger.info("Package credits created (new type)", member_id=member_id, credits=sessions_count - 1)

            fee_cents = int(amount_total * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
            await self.stripe_svc.record_transaction({
                "member_id": member_id,
                "amount_cents": amount_total,
                "type": "payment",
                "status": "completed",
                "description": f"Private session: {metadata.get('item_name', 'Private Session')}",
                "stripe_payment_intent_id": session.get("payment_intent"),
                "fee_cents": fee_cents,
                "net_amount_cents": amount_total - fee_cents,
            })
            member = await self._get_member(member_id, schema)
            if member:
                await self.email_svc.send_payment_receipt(
                    member_id=member_id,
                    to_email=member["email"],
                    member_name=member["first_name"],
                    amount_display=f"${amount_total / 100:.2f}",
                    description=f"Private session: {metadata.get('item_name', 'Private Session')}",
                )
            logger.info("Private session payment processed", booking_id=booking_id, confirmed=bool(confirmed))
            return {"status": "processed", "event": "checkout.session.completed", "booking_id": booking_id}

        # ── Membership purchase (default) ──
        stripe_subscription_id = session.get("subscription")
        amount_total = session.get("amount_total", 0)

        # Check for direct membership_id from migration checkout
        direct_membership_id = metadata.get("auraflow_membership_id")
        if direct_membership_id and stripe_subscription_id and schema:
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute(
                    """UPDATE member_memberships
                       SET stripe_subscription_id = $1, status = 'active', updated_at = NOW()
                       WHERE id = $2""",
                    stripe_subscription_id, direct_membership_id,
                )
                # Clear payment_setup_required flag
                if member_id:
                    await db.execute(
                        "UPDATE members SET payment_setup_required = FALSE WHERE id = $1",
                        member_id,
                    )
            logger.info("Linked subscription to membership via direct ID",
                        membership_id=direct_membership_id, subscription_id=stripe_subscription_id)
            return {"status": "linked", "membership_id": direct_membership_id}

        if not member_id or not membership_type_id:
            logger.warning("Checkout session missing metadata", session_id=session.get("id"))
            return {"status": "ignored", "reason": "missing metadata"}

        async with get_tenant_db(schema_override=schema) as db:
            # Get membership type details
            mt = await db.fetchrow(
                "SELECT * FROM membership_types WHERE id = $1", membership_type_id
            )
            if not mt:
                logger.warning("Membership type not found in checkout handler", type_id=membership_type_id)
                return {"status": "error", "reason": "membership type not found"}

            # Check if member already has this active membership
            existing = await db.fetchrow(
                """
                SELECT id FROM member_memberships
                WHERE member_id = $1 AND membership_type_id = $2 AND status = 'active'
                """,
                member_id, membership_type_id,
            )
            if existing:
                # Member already has this membership
                if stripe_subscription_id:
                    await db.execute(
                        "UPDATE member_memberships SET stripe_subscription_id = $1, updated_at = NOW() WHERE id = $2",
                        stripe_subscription_id, str(existing["id"]),
                    )
                    logger.info("Linked Stripe subscription to existing membership",
                                member_id=member_id, subscription_id=stripe_subscription_id)
                # For class packs / single class: add credits to existing
                # pack and extend its expiration if the type has a
                # duration. Shared helper guarantees the staff-side
                # assign_membership and the webhook can't drift apart.
                if mt.get("class_count") and mt["class_count"] > 0:
                    from app.services.memberships.membership_service import (
                        increment_pack_credits,
                    )
                    await increment_pack_credits(
                        db,
                        existing["id"],
                        mt["class_count"],
                        mt.get("duration_days"),
                    )
                    logger.info("Credits added to existing membership",
                                member_id=member_id, added=mt["class_count"],
                                duration_days=mt.get("duration_days"))
                # Always record the transaction for existing memberships
                fee_cents = int(amount_total * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
                await self.stripe_svc.record_transaction({
                    "member_id": member_id,
                    "amount_cents": amount_total,
                    "type": "payment",
                    "status": "completed",
                    "description": f"Purchased: {type_name}",
                    "stripe_payment_intent_id": session.get("payment_intent"),
                    "membership_id": str(existing["id"]),
                    "fee_cents": fee_cents,
                    "net_amount_cents": amount_total - fee_cents,
                })
                return {"status": "linked", "membership_id": str(existing["id"])}

            # Create membership assignment. Honor the type's duration_days
            # so packs / intro offers carry their built-in expiration into
            # the new row instead of living forever as NULL ends_at.
            mm_id = str(uuid.uuid4())
            classes_remaining = mt.get("class_count")
            duration_days = mt.get("duration_days")

            await db.execute(
                """
                INSERT INTO member_memberships
                    (id, member_id, membership_type_id, status, starts_at,
                     ends_at, classes_remaining, stripe_subscription_id)
                VALUES ($1, $2, $3, 'active', NOW(),
                        CASE WHEN $6::int IS NULL THEN NULL
                             ELSE NOW() + ($6::int || ' days')::interval
                        END,
                        $4, $5)
                """,
                mm_id, member_id, membership_type_id,
                classes_remaining, stripe_subscription_id, duration_days,
            )

            # Record transaction
            fee_cents = int(amount_total * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)
            await self.stripe_svc.record_transaction({
                "member_id": member_id,
                "amount_cents": amount_total,
                "type": "subscription" if stripe_subscription_id else "payment",
                "status": "completed",
                "description": f"Purchased: {type_name}",
                "stripe_payment_intent_id": session.get("payment_intent"),
                "membership_id": mm_id,
                "fee_cents": fee_cents,
                "net_amount_cents": amount_total - fee_cents,
            })

        # Send confirmation email
        member = await self._get_member(member_id, schema)
        if member:
            await self.email_svc.send_payment_receipt(
                member_id=member_id,
                to_email=member["email"],
                member_name=member["first_name"],
                amount_display=f"${amount_total / 100:.2f}",
                description=f"Membership: {type_name}",
            )

        logger.info(
            "Checkout completed — membership assigned",
            member_id=member_id,
            membership_type=type_name,
            membership_id=mm_id,
        )
        return {"status": "processed", "event": "checkout.session.completed", "membership_id": mm_id}

    # ── Invoice Payment Succeeded ─────────────────────────────────────────────

    async def _handle_invoice_paid(self, invoice: dict, schema: Optional[str] = None) -> dict:
        """Handle successful invoice payment — record transaction, update membership
        period, and send receipt email.

        Critical for imported subscriptions: when a Stripe subscription renews,
        this handler finds the member_membership by stripe_subscription_id and
        updates current_period_end so the membership stays seamlessly active.

        Handles the credit-paid-invoice case (2026-04-24 fix): Stripe marks
        invoices paid with amount_paid=0 when customer credit balance covers
        the total. This handler must advance the period regardless of whether
        cash actually moved.
        """
        metadata = invoice.get("metadata", {}) or {}
        member_id = metadata.get("auraflow_member_id")
        membership_id = metadata.get("auraflow_membership_id")

        if not member_id:
            # Try to find member by Stripe customer ID
            member_id = await self._find_member_by_stripe_customer(
                invoice.get("customer"), schema
            )

        # ── Update membership period for subscription renewals ──
        # Stripe API 2025-11-17.clover removed `invoice.subscription` at the
        # top level. It now lives at `invoice.parent.subscription_details.subscription`.
        # Fall back to the old location for pre-2025-11-17 payloads and for
        # any SDK-pinned retrieves that still use the old schema.
        stripe_subscription_id = (
            invoice.get("subscription")
            or ((invoice.get("parent") or {}).get("subscription_details") or {}).get("subscription")
        )
        if stripe_subscription_id:
            # Fallback: if schema didn't resolve via customer lookup, try
            # directly by stripe_subscription_id across tenants. This
            # recovers the case where a member.stripe_customer_id was
            # never populated but the subscription ID lives on
            # member_memberships.
            if not schema:
                async with get_global_db() as gdb:
                    orgs = await gdb.fetch(
                        "SELECT schema_name FROM af_global.organizations "
                        "WHERE status IN ('active', 'trial')"
                    )
                for org in orgs:
                    async with get_tenant_db(schema_override=org["schema_name"]) as db:
                        found = await db.fetchval(
                            "SELECT 1 FROM member_memberships "
                            "WHERE stripe_subscription_id = $1 LIMIT 1",
                            stripe_subscription_id,
                        )
                        if found:
                            schema = org["schema_name"]
                            logger.info(
                                "Resolved webhook tenant via subscription fallback",
                                stripe_subscription_id=stripe_subscription_id,
                                schema=schema,
                            )
                            break

        if stripe_subscription_id and schema:
            # Extract the new period end from the invoice's subscription lines
            period_end = None
            lines = invoice.get("lines", {})
            line_data = lines.get("data", []) if isinstance(lines, dict) else []
            for line in line_data:
                period = line.get("period", {})
                if period.get("end"):
                    period_end = period["end"]
                    break

            if period_end:
                # Use tz-aware datetime so Postgres TIMESTAMPTZ compares cleanly.
                period_end_dt = datetime.fromtimestamp(period_end, tz=timezone.utc)
                async with get_tenant_db(schema_override=schema) as db:
                    # Accept any non-cancelled/deleted status so a brief bad
                    # state transition doesn't block renewal accounting.
                    # MembershipService.check_eligibility uses ends_at, not
                    # current_period_end, so we MUST advance both columns
                    # here. Forgetting ends_at strands the member after one
                    # billing cycle even though Stripe is renewing fine
                    # — this caused Melodee Morse, Holly Maddox, and Joan
                    # Claassen to be unable to book on 2026-04-28 despite
                    # active Stripe subs.
                    updated_mm = await db.fetchrow(
                        """
                        UPDATE member_memberships
                        SET current_period_end = $1,
                            ends_at = $1,
                            status = 'active',
                            updated_at = NOW()
                        WHERE stripe_subscription_id = $2
                          AND status NOT IN ('cancelled', 'deleted')
                        RETURNING id
                        """,
                        period_end_dt, stripe_subscription_id,
                    )
                    if updated_mm and not membership_id:
                        membership_id = str(updated_mm["id"])

                    if updated_mm:
                        logger.info(
                            "Membership period updated from invoice",
                            stripe_subscription_id=stripe_subscription_id,
                            current_period_end=period_end_dt.isoformat(),
                            membership_id=membership_id,
                            invoice_id=invoice.get("id"),
                            amount_paid_cents=invoice.get("amount_paid", 0),
                        )
                    else:
                        # Loud failure — the renewal fired but no row matched.
                        # Almost always means the member_memberships row
                        # doesn't have stripe_subscription_id populated.
                        logger.warning(
                            "Invoice paid but no membership row matched "
                            "stripe_subscription_id — period NOT advanced",
                            stripe_subscription_id=stripe_subscription_id,
                            invoice_id=invoice.get("id"),
                            schema=schema,
                        )
            else:
                logger.warning(
                    "Invoice paid but no period.end found on any line — "
                    "period NOT advanced",
                    stripe_subscription_id=stripe_subscription_id,
                    invoice_id=invoice.get("id"),
                )

        if member_id:
            amount_cents = invoice.get("amount_paid", 0)
            fee_cents = int(amount_cents * settings.STRIPE_PLATFORM_FEE_PERCENT / 100)

            await self.stripe_svc.record_transaction({
                "member_id": member_id,
                "amount_cents": amount_cents,
                "type": "subscription" if stripe_subscription_id else "payment",
                "status": "completed",
                "description": invoice.get("description") or "Subscription payment",
                "stripe_payment_intent_id": invoice.get("payment_intent"),
                "stripe_invoice_id": invoice.get("id"),
                "membership_id": membership_id,
                "fee_cents": fee_cents,
                "net_amount_cents": amount_cents - fee_cents,
            })

            # Resolve any prior open failed-payment attempts for this member.
            # Without this, a recovered payment leaves stale unresolved rows in
            # failed_payment_attempts, and the daily escalation task keeps
            # dunning the member even though they've paid. We match the same
            # membership when known, plus any membership_id-NULL orphan rows
            # (signup-time card declines that later succeeded — these never
            # link to a membership and otherwise never auto-clear).
            try:
                async with (
                    get_tenant_db(schema_override=schema) if schema else get_tenant_db()
                ) as db:
                    resolved = await db.execute(
                        """
                        UPDATE failed_payment_attempts
                        SET resolved = TRUE, resolved_at = NOW()
                        WHERE member_id = $1
                          AND resolved_at IS NULL
                          AND ($2::uuid IS NULL OR membership_id = $2 OR membership_id IS NULL)
                        """,
                        member_id, membership_id,
                    )
                if resolved and resolved != "UPDATE 0":
                    logger.info(
                        "Resolved prior failed-payment attempts on successful payment",
                        member_id=member_id, membership_id=membership_id, result=resolved,
                    )
            except Exception as e:  # never fail a successful-payment webhook on cleanup
                logger.warning(
                    "Failed to resolve prior failed_payment_attempts",
                    member_id=member_id, error=str(e),
                )

            # Send receipt
            member = await self._get_member(member_id, schema)
            if member:
                await self.email_svc.send_payment_receipt(
                    member_id=member_id,
                    to_email=member["email"],
                    member_name=member["first_name"],
                    amount_display=f"${amount_cents / 100:.2f}",
                    description=invoice.get("description") or "Subscription payment",
                )

        logger.info("Invoice payment processed", invoice_id=invoice.get("id"))
        return {"status": "processed", "event": "invoice.payment_succeeded"}

    # ── Invoice Payment Failed ────────────────────────────────────────────────

    async def _handle_invoice_failed(self, invoice: dict, schema: Optional[str] = None) -> dict:
        """Handle failed invoice — record failure + dunning email."""
        metadata = invoice.get("metadata", {}) or {}
        member_id = metadata.get("auraflow_member_id")
        membership_id = metadata.get("auraflow_membership_id")

        if not member_id:
            member_id = await self._find_member_by_stripe_customer(
                invoice.get("customer"), schema
            )

        if member_id:
            await self.stripe_svc.record_failed_payment({
                "member_id": member_id,
                "membership_id": membership_id,
                "stripe_payment_intent_id": invoice.get("payment_intent"),
                "stripe_invoice_id": invoice.get("id"),
                "amount_cents": invoice.get("amount_due", 0),
                "failure_reason": (invoice.get("last_finalization_error") or {}).get("message", "Unknown"),
                "attempt_number": invoice.get("attempt_count", 1),
            })

            # Send dunning email
            member = await self._get_member(member_id, schema)
            if member:
                await self.email_svc.send_payment_failed(
                    member_id=member_id,
                    to_email=member["email"],
                    member_name=member["first_name"],
                    membership_name=metadata.get("type_name", "your membership"),
                    amount_display=f"${invoice.get('amount_due', 0) / 100:.2f}",
                )

        logger.info("Invoice payment failure processed", invoice_id=invoice.get("id"))
        return {"status": "processed", "event": "invoice.payment_failed"}

    # ── Subscription Updated ──────────────────────────────────────────────────

    async def _handle_subscription_updated(self, subscription: dict, schema: Optional[str] = None) -> dict:
        """Handle subscription status changes (e.g., active, past_due, canceled).

        Looks up the membership by metadata first, then falls back to
        stripe_subscription_id so imported subscriptions are also handled.
        Also syncs current_period_end from the subscription object.
        """
        metadata = subscription.get("metadata", {}) or {}
        membership_id = metadata.get("auraflow_membership_id")
        stripe_sub_id = subscription.get("id")
        stripe_status = subscription.get("status")
        pause_collection = subscription.get("pause_collection")

        # Map Stripe status to our membership status. Stripe reports
        # status='active' even when pause_collection is set (billing is
        # suppressed but the sub is technically live) — detect that and
        # treat it as 'frozen' so a member-on-hold doesn't get flipped
        # back to active by the webhook that fires after we set
        # pause_collection. Anna Marie got billed an unwarranted $140
        # on 2026-05-10 because this handler clobbered her freeze.
        status_map = {
            "active": "active",
            "past_due": "past_due",
            "canceled": "cancelled",
            "unpaid": "frozen",
            "incomplete_expired": "cancelled",
        }
        if pause_collection:
            our_status = "frozen"
        else:
            our_status = status_map.get(stripe_status)

        # Extract period end from subscription.
        # Stripe API 2025-11-17.clover removed `subscription.current_period_end`
        # at the top level — it now lives on each subscription item at
        # `subscription.items.data[0].current_period_end`. For mono-item subs
        # (everything we use) the first item carries the canonical period.
        period_end_ts = (
            subscription.get("current_period_end")
            or _first_item_current_period_end(subscription)
        )
        period_end_dt = datetime.fromtimestamp(period_end_ts, tz=timezone.utc) if period_end_ts else None

        # Never auto-unfreeze. If the local row is 'frozen', leave the
        # status alone — Stripe sometimes reports active for a paused
        # sub between modify and webhook delivery, and we don't want
        # that race to silently undo a deliberate freeze. The
        # unfreeze_membership service path is the only way out.
        if our_status == "active":
            async with get_tenant_db(schema_override=schema) as db:
                current = await db.fetchrow(
                    """
                    SELECT status FROM member_memberships
                    WHERE ($1::uuid IS NOT NULL AND id = $1)
                       OR ($2::text IS NOT NULL AND stripe_subscription_id = $2)
                    LIMIT 1
                    """,
                    membership_id, stripe_sub_id,
                )
                if current and current["status"] == "frozen":
                    logger.warning(
                        "Subscription updated webhook: Stripe reports active for a frozen local row — refusing to auto-unfreeze",
                        subscription_id=stripe_sub_id,
                    )
                    return {"status": "ignored", "event": "customer.subscription.updated",
                            "reason": "local_frozen_no_auto_unfreeze"}

        if our_status and schema:
            async with get_tenant_db(schema_override=schema) as db:
                if membership_id:
                    # Update by known membership ID. Advance both columns;
                    # see invoice.payment_succeeded handler for full rationale.
                    await db.execute(
                        """
                        UPDATE member_memberships
                        SET status = $1,
                            current_period_end = COALESCE($2, current_period_end),
                            ends_at = COALESCE($2, ends_at),
                            updated_at = NOW()
                        WHERE id = $3
                        """,
                        our_status, period_end_dt, membership_id,
                    )
                elif stripe_sub_id:
                    # Fallback: look up by stripe_subscription_id (imported subscriptions)
                    await db.execute(
                        """
                        UPDATE member_memberships
                        SET status = $1,
                            current_period_end = COALESCE($2, current_period_end),
                            ends_at = COALESCE($2, ends_at),
                            updated_at = NOW()
                        WHERE stripe_subscription_id = $3
                        """,
                        our_status, period_end_dt, stripe_sub_id,
                    )

        logger.info(
            "Subscription updated",
            subscription_id=stripe_sub_id,
            status=stripe_status,
            our_status=our_status,
        )
        return {"status": "processed", "event": "customer.subscription.updated"}

    # ── Subscription Deleted ──────────────────────────────────────────────────

    async def _handle_subscription_deleted(self, subscription: dict, schema: Optional[str] = None) -> dict:
        """Handle subscription cancellation from Stripe side.

        Looks up by metadata first, then falls back to stripe_subscription_id
        so imported subscriptions are also handled.

        Stripe → Square migration carve-out:
        if the local row ALSO has square_subscription_id set, this Stripe
        deletion is the natural period-end of a member who switched to
        Square. Don't mark the row cancelled — instead clear
        stripe_subscription_id and flip billing_provider='square' so
        the Square sub takes over seamlessly. The member sees no break
        in coverage.
        """
        metadata = subscription.get("metadata", {}) or {}
        membership_id = metadata.get("auraflow_membership_id")
        stripe_sub_id = subscription.get("id")

        if schema:
            async with get_tenant_db(schema_override=schema) as db:
                # Identify the row first so we can detect a transition.
                row = None
                if membership_id:
                    row = await db.fetchrow(
                        """
                        SELECT id, status, square_subscription_id
                        FROM member_memberships WHERE id = $1
                        """,
                        membership_id,
                    )
                elif stripe_sub_id:
                    row = await db.fetchrow(
                        """
                        SELECT id, status, square_subscription_id
                        FROM member_memberships WHERE stripe_subscription_id = $1
                        """,
                        stripe_sub_id,
                    )

                if not row:
                    logger.info(
                        "Subscription deleted — no local row found",
                        subscription_id=stripe_sub_id,
                    )
                    return {"status": "processed", "event": "customer.subscription.deleted"}

                # Detect "this deletion is our scheduled cutover" vs
                # "this deletion is a user-initiated mid-cycle cancel."
                # We set cancel_at_period_end=true when migrating; Stripe
                # echoes that flag on the subscription.deleted payload.
                cancel_at_period_end = bool(subscription.get("cancel_at_period_end"))

                if row["square_subscription_id"] and cancel_at_period_end:
                    # Stripe → Square migration: Stripe period has ended,
                    # Square sub takes over. Drop the Stripe pointer +
                    # flip provider; row stays 'active'.
                    await db.execute(
                        """
                        UPDATE member_memberships
                        SET stripe_subscription_id = NULL,
                            billing_provider = 'square',
                            updated_at = NOW()
                        WHERE id = $1
                        """,
                        row["id"],
                    )
                    logger.info(
                        "Stripe → Square cutover: provider flipped at period end",
                        membership_id=str(row["id"]),
                        stripe_sub_id=stripe_sub_id,
                    )
                elif row["square_subscription_id"]:
                    # User cancelled mid-transition (after Switch, before
                    # period_end). Honor the cancel — and ALSO cancel the
                    # scheduled Square successor so the member isn't hit
                    # with a Square charge after asking to cancel.
                    logger.warning(
                        "Mid-transition manual cancel — cancelling scheduled Square sub too",
                        membership_id=str(row["id"]),
                        stripe_sub_id=stripe_sub_id,
                        square_sub_id=row["square_subscription_id"],
                    )
                    await db.execute(
                        """
                        UPDATE member_memberships
                        SET status = 'cancelled', cancelled_at = NOW(), updated_at = NOW()
                        WHERE id = $1 AND status IN ('active', 'frozen', 'past_due')
                        """,
                        row["id"],
                    )
                    try:
                        async with get_global_db() as gdb:
                            org_row = await gdb.fetchrow(
                                "SELECT id FROM af_global.organizations WHERE schema_name = $1",
                                schema,
                            )
                        if org_row:
                            from app.services.payments.square_oauth_service import square_oauth_service
                            from app.services.payments.square_service import square_service
                            tok = await square_oauth_service.get_merchant_access_token(str(org_row["id"]))
                            if tok:
                                await square_service.cancel_subscription(
                                    merchant_access_token=tok,
                                    subscription_id=row["square_subscription_id"],
                                )
                    except Exception as e:
                        logger.error(
                            "Failed to cancel scheduled Square sub during mid-transition cancel",
                            membership_id=str(row["id"]),
                            error=str(e),
                        )
                else:
                    await db.execute(
                        """
                        UPDATE member_memberships
                        SET status = 'cancelled', cancelled_at = NOW(), updated_at = NOW()
                        WHERE id = $1 AND status IN ('active', 'frozen', 'past_due')
                        """,
                        row["id"],
                    )

        logger.info("Subscription deleted", subscription_id=stripe_sub_id)
        return {"status": "processed", "event": "customer.subscription.deleted"}

    # ── Charge Refunded ───────────────────────────────────────────────────────

    async def _handle_charge_refunded(self, charge: dict, schema: Optional[str] = None) -> dict:
        """Handle a charge refund from Stripe.

        On a FULL refund of a transaction tied to a class-pack / intro-offer
        membership, also cancels the membership row and any future bookings
        that were paid for from those credits — otherwise the member keeps
        free access after their money went back.

        Partial refunds only record the refund amount; staff must manually
        decide whether to claw back credits/bookings (a $20 partial on a
        10-class pack shouldn't void the whole pack).
        """
        payment_intent_id = charge.get("payment_intent")
        charge_id = charge.get("id")
        invoice_id = charge.get("invoice")
        refund_amount = charge.get("amount_refunded", 0)

        async with get_tenant_db(schema_override=schema) as db:
            # Update the original transaction row. Try payment_intent
            # first (modern Stripe), then fall back to charge_id and
            # invoice_id — legacy subscriptions imported from MindBody
            # and direct-mode subs from before Stripe started exposing
            # PI on invoice events have NULL stripe_payment_intent_id,
            # so the original lookup misses them entirely.
            txn = None
            if payment_intent_id:
                txn = await db.fetchrow(
                    """
                    UPDATE transactions
                    SET refund_amount_cents = $1, refunded_at = NOW(),
                        status = CASE WHEN $1 >= amount_cents THEN 'refunded' ELSE 'partially_refunded' END,
                        updated_at = NOW()
                    WHERE stripe_payment_intent_id = $2
                    RETURNING id, member_id, membership_id, amount_cents, status
                    """,
                    refund_amount, payment_intent_id,
                )
            if not txn and charge_id:
                txn = await db.fetchrow(
                    """
                    UPDATE transactions
                    SET refund_amount_cents = $1, refunded_at = NOW(),
                        status = CASE WHEN $1 >= amount_cents THEN 'refunded' ELSE 'partially_refunded' END,
                        updated_at = NOW()
                    WHERE stripe_charge_id = $2
                    RETURNING id, member_id, membership_id, amount_cents, status
                    """,
                    refund_amount, charge_id,
                )
            if not txn and invoice_id:
                txn = await db.fetchrow(
                    """
                    UPDATE transactions
                    SET refund_amount_cents = $1, refunded_at = NOW(),
                        status = CASE WHEN $1 >= amount_cents THEN 'refunded' ELSE 'partially_refunded' END,
                        updated_at = NOW()
                    WHERE stripe_invoice_id = $2
                    RETURNING id, member_id, membership_id, amount_cents, status
                    """,
                    refund_amount, invoice_id,
                )

            # Insert a separate refund-type transaction row regardless of
            # whether the original was found. The payments-page list
            # renders rows from the transactions table, so without this
            # the refund is invisible — even when we did update the
            # original's refund_amount_cents, the original row still
            # shows its original positive amount and isn't clearly
            # marked as "refunded" in a list context.
            #
            # We DO write a stripe_payment_intent_id-style dedup using
            # the refund's charge id so duplicate webhook deliveries
            # don't insert two refund rows.
            refund_member_id = txn.get("member_id") if txn else None
            refund_membership_id = txn.get("membership_id") if txn else None
            refund_dedup_key = f"refund:{charge_id}" if charge_id else f"refund:{payment_intent_id}"

            existing_refund = await db.fetchrow(
                "SELECT id FROM transactions WHERE metadata->>'refund_dedup_key' = $1",
                refund_dedup_key,
            )
            if not existing_refund and refund_amount > 0:
                import json as _json
                await db.execute(
                    """
                    INSERT INTO transactions
                        (id, member_id, type, amount_cents, status, description,
                         stripe_payment_intent_id, stripe_charge_id, stripe_invoice_id,
                         membership_id, fee_cents, net_amount_cents, metadata,
                         refunded_at)
                    VALUES ($1, $2, 'refund', $3, 'completed', $4,
                            $5, $6, $7, $8, 0, $3,
                            $9::jsonb, NOW())
                    """,
                    str(uuid.uuid4()),
                    refund_member_id,
                    -refund_amount,  # negative so reports / sums net out correctly
                    f"Refund: ${refund_amount/100:.2f}"
                    + (f" (charge {charge_id})" if charge_id else ""),
                    payment_intent_id,
                    charge_id,
                    invoice_id,
                    refund_membership_id,
                    _json.dumps({
                        "refund_dedup_key": refund_dedup_key,
                        "original_transaction_id": str(txn["id"]) if txn else None,
                    }),
                )

            if not txn:
                logger.warning(
                    "Charge refund: no matching local transaction — refund row written without parent link",
                    payment_intent_id=payment_intent_id,
                    charge_id=charge_id,
                    invoice_id=invoice_id,
                )
                return {"status": "processed", "event": "charge.refunded"}

            full_refund = txn["status"] == "refunded"
            mm_id = txn.get("membership_id")

            if not full_refund or not mm_id:
                logger.info(
                    "Charge refund recorded — no auto-cleanup",
                    txn_id=str(txn["id"]),
                    full_refund=full_refund,
                    has_membership=bool(mm_id),
                )
                return {"status": "processed", "event": "charge.refunded"}

            # Full refund + linked membership — claw back the value.
            mm = await db.fetchrow(
                """
                SELECT mm.id, mm.classes_remaining, mt.type AS plan_type
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE mm.id = $1
                """,
                str(mm_id),
            )
            if not mm:
                logger.warning("Charge refund: membership row missing",
                               membership_id=str(mm_id))
                return {"status": "processed", "event": "charge.refunded"}

            # Cancel future bookings tied to this membership and refund
            # their credits to the (now-cancelled) pack only if they
            # were active. Future bookings of a refunded pack
            # shouldn't survive the refund.
            cancelled = await db.fetch(
                """
                UPDATE bookings b
                SET status = 'cancelled',
                    cancelled_at = NOW(),
                    cancellation_reason = 'membership refunded'
                FROM class_sessions cs
                WHERE b.class_session_id = cs.id
                  AND b.membership_id = $1
                  AND b.status IN ('confirmed', 'waitlisted')
                  AND cs.starts_at >= NOW()
                RETURNING b.id, b.class_session_id
                """,
                str(mm_id),
            )

            # Mark the membership cancelled. For countable packs, zero
            # out remaining credits so the row can't be re-used.
            await db.execute(
                """
                UPDATE member_memberships
                SET status = 'cancelled',
                    cancelled_at = NOW(),
                    cancellation_reason = COALESCE(cancellation_reason, 'refunded'),
                    classes_remaining = CASE
                        WHEN classes_remaining IS NOT NULL THEN 0
                        ELSE classes_remaining
                    END,
                    updated_at = NOW()
                WHERE id = $1
                """,
                str(mm_id),
            )

            logger.info(
                "Charge refund: membership cancelled and future bookings voided",
                txn_id=str(txn["id"]),
                membership_id=str(mm_id),
                bookings_cancelled=len(cancelled),
                plan_type=mm["plan_type"],
            )

        return {"status": "processed", "event": "charge.refunded"}

    # ── Dispute Created ────────────────────────────────────────────────────────

    async def _handle_dispute_created(self, dispute: dict, schema: Optional[str] = None) -> dict:
        """Handle a charge dispute — log it and mark the transaction as disputed."""
        charge_id = dispute.get("charge")
        payment_intent_id = dispute.get("payment_intent")
        amount = dispute.get("amount", 0)
        reason = dispute.get("reason", "unknown")

        logger.warning(
            "Dispute created",
            dispute_id=dispute.get("id"),
            charge_id=charge_id,
            amount=amount,
            reason=reason,
        )

        # Try to update the local transaction to 'disputed' status
        if payment_intent_id and schema:
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute(
                    """
                    UPDATE transactions
                    SET status = 'disputed', updated_at = NOW()
                    WHERE stripe_payment_intent_id = $1
                    """,
                    payment_intent_id,
                )

        return {"status": "processed", "event": "charge.dispute.created"}

    # ── Stripe Connect Account Updated ───────────────────────────────────────

    async def _handle_account_updated(self, account: dict, schema: Optional[str] = None) -> dict:
        """Handle Stripe Connect account.updated — detect when onboarding completes.

        When charges_enabled flips to true, update the organization record and
        send a confirmation email to the org owner.
        """
        account_id = account.get("id")
        charges_enabled = account.get("charges_enabled", False)
        payouts_enabled = account.get("payouts_enabled", False)

        if not account_id:
            return {"status": "ignored", "reason": "no account id"}

        # Look up the organization by stripe_account_id
        async with get_global_db() as db:
            org = await db.fetchrow(
                """
                SELECT id, name, schema_name, stripe_charges_enabled
                FROM af_global.organizations
                WHERE stripe_account_id = $1
                """,
                account_id,
            )

        if not org:
            logger.info("account.updated for unknown Connect account", account_id=account_id)
            return {"status": "ignored", "reason": "unknown connect account"}

        previously_enabled = org.get("stripe_charges_enabled", False)

        # Update org record with current Connect status
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET stripe_charges_enabled = $1,
                    stripe_payouts_enabled = $2,
                    updated_at = NOW()
                WHERE id = $3
                """,
                charges_enabled, payouts_enabled, org["id"],
            )

        # Invalidate the connect_account cache for this tenant so the next
        # /external/connect/status read (and the next charge attempt) sees
        # the new state immediately, rather than waiting up to 60s for the
        # cache TTL. Critical for the "Stripe just blocked us" case where
        # we need to flip charges_enabled false fast to stop accepting
        # payments that will fail.
        from app.services.payments.connect_account import invalidate_cache
        invalidate_cache(org["id"])

        # If charges flipped from enabled → disabled, log a SECURITY-grade
        # audit event so the operator knows ASAP (Slack alert wiring lands
        # alongside other observability — for now journalctl-grep is the
        # discovery path).
        if not charges_enabled and previously_enabled:
            logger.warning(
                "Stripe Connect charges DISABLED for tenant",
                org_id=org["id"],
                org_name=org["name"],
                account_id=account_id,
                requirements=account.get("requirements", {}).get("disabled_reason"),
            )

        # If charges just became enabled (onboarding complete), notify the owner
        if charges_enabled and not previously_enabled:
            logger.info(
                "Stripe Connect onboarding complete — charges enabled",
                org_id=org["id"],
                org_name=org["name"],
                account_id=account_id,
            )

            # Send confirmation email to org owner
            async with get_global_db() as db:
                owner = await db.fetchrow(
                    """
                    SELECT u.email, u.display_name
                    FROM af_global.organization_users ou
                    JOIN af_global.users u ON u.id = ou.user_id
                    WHERE ou.organization_id = $1 AND ou.role = 'owner' AND ou.is_active = TRUE
                    LIMIT 1
                    """,
                    org["id"],
                )
            if owner:
                try:
                    owner_name = owner["display_name"] or "there"
                    org_name = org["name"]
                    await self.email_svc.send_email(
                        to_email=owner["email"],
                        subject="Your payment processing is now active!",
                        html_content=(
                            f"<p>Hi {owner_name},</p>"
                            f"<p>Great news! Stripe payment processing for <strong>{org_name}</strong> "
                            "is now fully active. Your members can now purchase memberships, class packs, "
                            "and workshops directly through AuraFlow.</p>"
                            "<p>You can manage your payment settings in the AuraFlow dashboard under "
                            "<strong>Settings &gt; Payments</strong>.</p>"
                            "<p>— The AuraFlow Team</p>"
                        ),
                        email_type="transactional",
                    )
                    logger.info(
                        "Connect onboarding confirmation email sent",
                        org_id=org["id"],
                        owner_email=owner["email"],
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to send Connect onboarding email",
                        error=str(e),
                        org_id=org["id"],
                    )

            # Audit trail (global audit_log)
            try:
                import json as _json
                async with get_global_db() as db:
                    await db.execute(
                        """
                        INSERT INTO af_global.audit_log
                            (id, organization_id, action, resource_type, resource_id, metadata, created_at)
                        VALUES ($1, $2, 'stripe_connect_activated', 'organization', $2,
                                $3::jsonb, NOW())
                        """,
                        str(uuid.uuid4()),
                        org["id"],
                        _json.dumps({
                            "event": "account.updated",
                            "charges_enabled": True,
                            "stripe_account_id": account_id,
                        }),
                    )
            except Exception as e:
                logger.warning("Failed to write audit log for Connect activation", error=str(e))

        return {"status": "processed", "event": "account.updated", "charges_enabled": charges_enabled}

    # ── Subscription Paused ──────────────────────────────────────────────────

    async def _handle_subscription_paused(self, subscription: dict, schema: Optional[str] = None) -> dict:
        """Handle subscription paused — update member_memberships status to paused."""
        sub_id = subscription.get("id")
        if sub_id and schema:
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute(
                    """
                    UPDATE member_memberships
                    SET status = 'paused', updated_at = NOW()
                    WHERE stripe_subscription_id = $1 AND status = 'active'
                    """,
                    sub_id,
                )

        logger.info("Subscription paused", subscription_id=sub_id)
        return {"status": "processed", "event": "customer.subscription.paused"}

    # ── Subscription Resumed ─────────────────────────────────────────────────

    async def _handle_subscription_resumed(self, subscription: dict, schema: Optional[str] = None) -> dict:
        """Handle subscription resumed — update member_memberships status to active."""
        sub_id = subscription.get("id")
        if sub_id and schema:
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute(
                    """
                    UPDATE member_memberships
                    SET status = 'active', updated_at = NOW()
                    WHERE stripe_subscription_id = $1 AND status = 'paused'
                    """,
                    sub_id,
                )

        logger.info("Subscription resumed", subscription_id=sub_id)
        return {"status": "processed", "event": "customer.subscription.resumed"}

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _find_member_by_stripe_customer(
        self, customer_id: Optional[str], schema: Optional[str] = None
    ) -> Optional[str]:
        """Look up a member by their Stripe customer ID.

        Refuses to query without an explicit tenant schema. Without this
        guard, schema=None would fall through to whatever tenant context
        is set at the time, risking a cross-tenant lookup where the
        wrong member gets credited.
        """
        if not customer_id:
            return None
        if not schema:
            logger.warning(
                "_find_member_by_stripe_customer called without schema — refusing",
                customer_id=customer_id,
            )
            return None
        async with get_tenant_db(schema_override=schema) as db:
            row = await db.fetchrow(
                "SELECT id FROM members WHERE stripe_customer_id = $1",
                customer_id,
            )
            return str(row["id"]) if row else None

    async def _get_member(self, member_id: str, schema: Optional[str] = None) -> Optional[dict]:
        """Get basic member info for emails. Like _find_member_by_stripe_customer,
        refuses to run without an explicit schema."""
        if not schema:
            logger.warning(
                "_get_member called without schema — refusing",
                member_id=member_id,
            )
            return None
        async with get_tenant_db(schema_override=schema) as db:
            row = await db.fetchrow(
                "SELECT id, first_name, last_name, email FROM members WHERE id = $1",
                member_id,
            )
            return dict(row) if row else None
