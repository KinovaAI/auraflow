"""AuraFlow — Membership Service

Membership type management, assignment, freeze, cancel, eligibility checks,
and template seeding for default membership configurations.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db


_MEMBERSHIP_TYPE_UPDATE_COLS = {
    "name", "description", "type", "access_scope", "class_count",
    "price_cents", "billing_period", "duration_days", "is_founding_rate",
    "max_enrollments", "auto_renew", "trial_days", "freeze_allowed",
    "max_freeze_days", "cancellation_notice_days", "class_types_allowed",
    "is_active", "is_public", "sort_order",
}


async def increment_pack_credits(
    db,
    membership_id: str,
    class_count: int,
    duration_days: int | None,
):
    """Add `class_count` credits to an existing pack and extend its expiration.

    ends_at is set to GREATEST(existing, NOW + duration_days) when
    duration_days is provided, so re-up purchases earn a fresh
    expiration window without ever shortening one that's already
    longer. Use from both the staff-side assign_membership flow and
    the Stripe checkout webhook to avoid logic drift.
    """
    return await db.fetchrow(
        """
        UPDATE member_memberships
        SET classes_remaining = COALESCE(classes_remaining, 0) + $1,
            ends_at = CASE
                WHEN $3::int IS NULL THEN ends_at
                ELSE GREATEST(
                    COALESCE(ends_at, NOW()),
                    NOW() + ($3::int || ' days')::interval
                )
            END,
            updated_at = NOW()
        WHERE id = $2
        RETURNING *
        """,
        class_count, str(membership_id), duration_days,
    )


class MembershipService:

    # ── Membership Type CRUD ─────────────────────────────────────────────────

    async def create_type(self, data: dict) -> dict:
        type_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO membership_types
                    (id, studio_id, name, description, type, access_scope,
                     class_count, price_cents, billing_period, duration_days,
                     is_founding_rate, max_enrollments, auto_renew, trial_days,
                     freeze_allowed, max_freeze_days, cancellation_notice_days,
                     class_types_allowed, is_template, template_key,
                     is_public, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22)
                RETURNING *
                """,
                type_id, data["studio_id"], data["name"], data.get("description"),
                data["type"], data.get("access_scope", "in_studio"),
                data.get("class_count"), data["price_cents"],
                data.get("billing_period", "monthly"), data.get("duration_days"),
                data.get("is_founding_rate", False), data.get("max_enrollments"),
                data.get("auto_renew", True), data.get("trial_days", 0),
                data.get("freeze_allowed", False), data.get("max_freeze_days", 30),
                data.get("cancellation_notice_days", 0), data.get("class_types_allowed"),
                data.get("is_template", False), data.get("template_key"),
                data.get("is_public", True), data.get("sort_order", 0),
            )
            logger.info("Membership type created", type_id=type_id, name=data["name"])
            return dict(row)

    async def list_types(self, studio_id: str, active_only: bool = True) -> list[dict]:
        async with get_tenant_db() as db:
            where = "WHERE studio_id = $1"
            if active_only:
                where += " AND is_active = TRUE"
            rows = await db.fetch(
                f"SELECT * FROM membership_types {where} ORDER BY sort_order, name",
                studio_id,
            )
            return [dict(r) for r in rows]

    async def get_type(self, type_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow("SELECT * FROM membership_types WHERE id = $1", type_id)
            return dict(row) if row else None

    async def update_type(self, type_id: str, data: dict) -> dict | None:
        data = {k: v for k, v in data.items() if k in _MEMBERSHIP_TYPE_UPDATE_COLS}
        async with get_tenant_db() as db:
            sets, params, idx = [], [], 1
            for k, v in data.items():
                sets.append(f"{k} = ${idx}")
                params.append(v)
                idx += 1
            if not sets:
                return await self.get_type(type_id)

            sets.append(f"updated_at = ${idx}")
            params.append(datetime.now(timezone.utc))
            idx += 1

            params.append(type_id)
            query = f"UPDATE membership_types SET {', '.join(sets)} WHERE id = ${idx} RETURNING *"
            row = await db.fetchrow(query, *params)
            return dict(row) if row else None

    async def deactivate_type(self, type_id: str) -> bool:
        async with get_tenant_db() as db:
            result = await db.execute(
                "UPDATE membership_types SET is_active = FALSE, updated_at = NOW() WHERE id = $1",
                type_id,
            )
            return "UPDATE 1" in result

    # ── Templates ──────────────────────────────────────────────────────────

    async def list_templates(self) -> list[dict]:
        """List global membership templates."""
        async with get_global_db() as db:
            rows = await db.fetch(
                "SELECT * FROM af_global.membership_templates ORDER BY sort_order, name"
            )
            return [dict(r) for r in rows]

    async def seed_from_templates(self, studio_id: str) -> list[dict]:
        """Seed a studio with default membership types from global templates."""
        templates = await self.list_templates()
        created = []
        for t in templates:
            # Check if this template already exists for this studio
            async with get_tenant_db() as db:
                existing = await db.fetchrow(
                    "SELECT id FROM membership_types WHERE studio_id = $1 AND template_key = $2",
                    studio_id, t["template_key"],
                )
                if existing:
                    continue

            row = await self.create_type({
                "studio_id": studio_id,
                "name": t["name"],
                "description": t["description"],
                "type": t["type"],
                "access_scope": t["access_scope"],
                "class_count": t["class_count"],
                "price_cents": t["suggested_price_cents"],
                "billing_period": t["billing_period"],
                "duration_days": t["duration_days"],
                "auto_renew": t["auto_renew"],
                "freeze_allowed": t["freeze_allowed"],
                "is_template": True,
                "template_key": t["template_key"],
                "sort_order": t["sort_order"],
            })
            created.append(row)
        logger.info("Seeded membership templates", studio_id=studio_id, count=len(created))
        return created

    # ── Assignment ───────────────────────────────────────────────────────────

    async def assign_membership(self, data: dict) -> dict:
        """Assign a membership to a member.

        Raises ValueError("WAIVER_REQUIRED: ...") if the member has no
        signed liability waiver on file — a member cannot buy classes
        they're not legally allowed to participate in. Blocks the phantom
        drop-in bug where front desk sold passes to a member who then
        couldn't book the class because of the waiver check.
        """
        # Waiver gate — BEFORE any writes — applies to every membership
        # type since every membership grants the right to participate
        # in classes and the waiver is what makes participation legal.
        from app.services.waivers.waiver_service import WaiverService
        waiver_svc = WaiverService()
        waiver_status = await waiver_svc.check_waiver_status(data["member_id"])
        if not waiver_status.get("signed"):
            raise ValueError(
                "WAIVER NOT COMPLETED! CANNOT PARTICIPATE WITHOUT WAIVER — "
                "member must sign the liability waiver before any class "
                "pass or membership can be added to their account."
            )

        async with get_tenant_db() as db:
            # Get the membership type for class_count
            mt = await db.fetchrow(
                "SELECT * FROM membership_types WHERE id = $1",
                data["membership_type_id"],
            )
            if not mt:
                raise ValueError("Membership type not found")

            # New-members-only gate: refuse if the type is flagged for
            # first-time members and this member already has ANY prior
            # member_memberships row (active, expired, cancelled —
            # doesn't matter). Reject loudly so staff don't accidentally
            # comp a returning customer with a new-student offer.
            if mt.get("new_members_only"):
                prior = await db.fetchval(
                    "SELECT COUNT(*) FROM member_memberships WHERE member_id = $1",
                    data["member_id"],
                )
                if prior and prior > 0:
                    raise ValueError(
                        f"'{mt['name']}' is a new-students-only offer. "
                        f"This member has {prior} prior membership row(s) "
                        f"on file and is not eligible."
                    )

            raw_starts = data.get("starts_at")
            if isinstance(raw_starts, str):
                starts_at = datetime.fromisoformat(raw_starts)
            elif raw_starts is not None:
                starts_at = raw_starts
            else:
                starts_at = datetime.now(timezone.utc)
            ends_at = None
            # Trial-style memberships (e.g. FREE First Week Unlimited)
            # don't pre-compute ends_at — the clock activates on the
            # member's first attended class. See booking_service.check_in
            # for the activation. Without this branch a signup who came
            # to their first class 5 days later would only get 2 days
            # of remaining trial, defeating the offer.
            trial_activates_on_first_class = bool(
                mt.get("trial_starts_on_first_class")
            )
            if mt["duration_days"] and not trial_activates_on_first_class:
                ends_at = starts_at + timedelta(days=mt["duration_days"])

            classes_remaining = mt["class_count"]  # None for unlimited

            # Check for an existing ACTIVE membership of the same type.
            # When a member buys a second drop-in / class pack, the
            # right behavior is to ADD a credit to their existing pass,
            # not create a parallel membership row. This mirrors the
            # behavior already in webhook_handler.py for Stripe checkout
            # purchases — but until now the staff-side "assign
            # membership" path (walk-in, kiosk, manual add) was creating
            # a fresh row each time, leaving members with stacks of
            # zero-credit memberships every purchase.
            #
            # On 2026-05-01 Jean Correll was charged 3× in 65 seconds
            # for one class. The dashboard's "add client" flow created
            # 3 new Single Class Drop-In memberships, each at
            # classes_remaining=0 after the booking deducted. The fix:
            # find the existing one, increment its credits.
            existing = await db.fetchrow(
                """
                SELECT id, classes_remaining FROM member_memberships
                WHERE member_id = $1
                  AND membership_type_id = $2
                  AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                data["member_id"], data["membership_type_id"],
            )

            # Increment-existing path: countable types (class_pack /
            # single_class / intro_offer) where class_count > 0. Unlimited
            # types have class_count IS NULL — they don't accumulate.
            if existing and (mt["class_count"] or 0) > 0:
                row = await increment_pack_credits(
                    db,
                    existing["id"],
                    mt["class_count"],
                    mt.get("duration_days"),
                )
                logger.info(
                    "Membership credits added to existing pass",
                    membership_id=str(existing["id"]),
                    member_id=data["member_id"],
                    type=mt["name"],
                    added=mt["class_count"],
                    new_total=row["classes_remaining"],
                )
                return dict(row)

            # New-membership path: no existing active row OR the type
            # is unlimited / non-countable (don't merge unlimited
            # subscriptions, return a fresh row).
            mm_id = str(uuid.uuid4())
            row = await db.fetchrow(
                """
                INSERT INTO member_memberships
                    (id, member_id, membership_type_id, status, starts_at, ends_at,
                     classes_remaining)
                VALUES ($1, $2, $3, 'active', $4, $5, $6)
                RETURNING *
                """,
                mm_id, data["member_id"], data["membership_type_id"],
                starts_at, ends_at, classes_remaining,
            )
            logger.info(
                "Membership assigned",
                membership_id=mm_id,
                member_id=data["member_id"],
                type=mt["name"],
            )
            return dict(row)

    async def purchase_membership_with_gift_card(self, data: dict) -> dict:
        """Atomically purchase a membership using a gift card.

        Validates the card balance covers the type's price, debits the card,
        assigns the membership, and records a transaction — all in a single
        DB transaction so a failure walks every step back. Recurring (subscription)
        types are rejected — gift cards can't fund a recurring Stripe sub.
        """
        member_id = data["member_id"]
        membership_type_id = data["membership_type_id"]
        gift_card_code = data["gift_card_code"]

        # Waiver gate (same as assign_membership). Block before any reads
        # so we never touch the gift card if the member is ineligible.
        from app.services.waivers.waiver_service import WaiverService
        waiver_status = await WaiverService().check_waiver_status(member_id)
        if not waiver_status.get("signed"):
            raise ValueError(
                "WAIVER NOT COMPLETED! CANNOT PARTICIPATE WITHOUT WAIVER — "
                "member must sign the liability waiver before any class "
                "pass or membership can be added to their account."
            )

        async with get_tenant_db() as db:
            mt = await db.fetchrow(
                "SELECT * FROM membership_types WHERE id = $1",
                membership_type_id,
            )
            if not mt:
                raise ValueError("Membership type not found")
            price = mt.get("price_cents") or 0
            if price <= 0:
                raise ValueError("This membership has no price set — contact the studio")

            # Recurring subscriptions need a card on file for renewals;
            # gift cards can only fund the first period and would leave
            # the member's sub stranded. Reject up front.
            if mt.get("billing_period") in ("monthly", "yearly", "weekly"):
                raise ValueError(
                    "Gift cards can't fund recurring memberships — "
                    "use a class pack or one-time purchase instead"
                )

            async with db.transaction():
                # Debit gift card first. If balance is short, abort
                # before any membership state changes.
                from app.services.payments.gift_card_service import GiftCardService
                gc_svc = GiftCardService()
                bal = await gc_svc.check_balance(gift_card_code)
                if bal["balance_cents"] < price:
                    raise ValueError(
                        f"Gift card balance ${bal['balance_cents']/100:.2f} is less "
                        f"than purchase price ${price/100:.2f}"
                    )

                # Reuse the assign_membership path's logic by inlining the
                # same increment-or-insert decision. We can't call
                # self.assign_membership() because it opens its own
                # connection — we need everything on this transaction.
                from datetime import datetime, timedelta, timezone as _tz
                starts_at = datetime.now(_tz.utc)
                ends_at = (starts_at + timedelta(days=mt["duration_days"])
                           if mt.get("duration_days") else None)
                classes_remaining = mt["class_count"]

                existing = await db.fetchrow(
                    """
                    SELECT id, classes_remaining FROM member_memberships
                    WHERE member_id = $1
                      AND membership_type_id = $2
                      AND status = 'active'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    member_id, membership_type_id,
                )
                if existing and (mt["class_count"] or 0) > 0:
                    mm_row = await increment_pack_credits(
                        db, existing["id"], mt["class_count"], mt.get("duration_days"),
                    )
                else:
                    new_id = str(uuid.uuid4())
                    mm_row = await db.fetchrow(
                        """
                        INSERT INTO member_memberships
                            (id, member_id, membership_type_id, status, starts_at, ends_at,
                             classes_remaining)
                        VALUES ($1, $2, $3, 'active', $4, $5, $6)
                        RETURNING *
                        """,
                        new_id, member_id, membership_type_id,
                        starts_at, ends_at, classes_remaining,
                    )

                # Record the transaction first so the gift-card redemption
                # row can link to it — pre-allocate a UUID to thread through.
                txn_id = str(uuid.uuid4())
                await db.execute(
                    """
                    INSERT INTO transactions
                        (id, member_id, type, amount_cents, status, description,
                         membership_id, fee_cents, net_amount_cents)
                    VALUES ($1, $2, 'payment', $3, 'completed', $4, $5, 0, $3)
                    """,
                    txn_id, member_id, price,
                    f"Purchased: {mt['name']} (gift card)",
                    str(mm_row["id"]),
                )

                # Apply the gift card on the same connection
                await gc_svc.apply_to_transaction(
                    code=gift_card_code,
                    transaction_amount_cents=price,
                    member_id=member_id,
                    db=db,
                    transaction_id=txn_id,
                )

            logger.info(
                "Membership purchased with gift card",
                member_id=member_id,
                membership_id=str(mm_row["id"]),
                type=mt["name"],
                price_cents=price,
            )
            return dict(mm_row)

    async def list_all_memberships(self, active_only: bool = True, limit: int = 200) -> list[dict]:
        async with get_tenant_db() as db:
            where = ""
            if active_only:
                where = "WHERE mm.status IN ('active', 'frozen')"
            rows = await db.fetch(
                f"""
                SELECT mm.*, mt.name AS type_name, mt.type AS membership_type,
                       mt.access_scope, mt.class_count AS total_classes, mt.price_cents,
                       m.first_name AS member_first_name, m.last_name AS member_last_name
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                JOIN members m ON m.id = mm.member_id
                {where}
                ORDER BY mm.created_at DESC
                LIMIT $1
                """,
                limit,
            )
            return [dict(r) for r in rows]

    async def get_member_memberships(self, member_id: str, active_only: bool = True) -> list[dict]:
        async with get_tenant_db() as db:
            where = "WHERE mm.member_id = $1"
            if active_only:
                where += " AND mm.status IN ('active', 'frozen')"
            rows = await db.fetch(
                f"""
                SELECT mm.*, mt.name AS type_name, mt.type AS membership_type,
                       mt.access_scope, mt.class_count AS total_classes, mt.price_cents
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                {where}
                ORDER BY mm.created_at DESC
                """,
                member_id,
            )
            return [dict(r) for r in rows]

    async def get_membership(self, membership_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT mm.*, mt.name AS type_name, mt.type AS membership_type,
                       mt.access_scope, mt.class_count AS total_classes, mt.price_cents,
                       mt.freeze_allowed, mt.max_freeze_days
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE mm.id = $1
                """,
                membership_id,
            )
            return dict(row) if row else None

    # ── Freeze / Unfreeze ────────────────────────────────────────────────────

    async def freeze_membership(self, membership_id: str, until: datetime | None = None) -> dict | None:
        """Freeze a membership.

        For subscription-backed memberships, ALSO pauses the linked Stripe
        subscription with `pause_collection=void` so the member isn't
        billed during the hold. Stripe is paused FIRST so a Stripe
        failure aborts the freeze instead of leaving the local row
        marked frozen while billing continues.
        """
        mm = await self.get_membership(membership_id)
        if not mm:
            return None
        if mm["status"] != "active":
            raise ValueError(f"Cannot freeze membership in '{mm['status']}' status")
        if not mm.get("freeze_allowed"):
            raise ValueError("This membership type does not allow freezing")

        sub_id = mm.get("stripe_subscription_id")
        if sub_id:
            from app.services.payments.stripe_service import StripeService
            from app.core.tenant_context import get_tenant_context
            ctx = get_tenant_context()
            org_id = ctx.organization_id if ctx else None
            await StripeService().pause_subscription(sub_id, org_id=org_id)

        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE member_memberships
                SET status = 'frozen', frozen_at = NOW(), frozen_until = $2, updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                membership_id, until,
            )
            logger.info("Membership frozen", membership_id=membership_id,
                        stripe_paused=bool(sub_id))
            return dict(row) if row else None

    async def unfreeze_membership(self, membership_id: str) -> dict | None:
        """Unfreeze a membership.

        Resumes the linked Stripe subscription FIRST (so any failure aborts
        before the local row goes back to active and the member gets a free
        billing window).
        """
        mm = await self.get_membership(membership_id)
        if not mm:
            return None
        if mm["status"] != "frozen":
            return None

        sub_id = mm.get("stripe_subscription_id")
        if sub_id:
            from app.services.payments.stripe_service import StripeService
            from app.core.tenant_context import get_tenant_context
            ctx = get_tenant_context()
            org_id = ctx.organization_id if ctx else None
            await StripeService().resume_subscription(sub_id, org_id=org_id)

        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE member_memberships
                SET status = 'active', frozen_at = NULL, frozen_until = NULL, updated_at = NOW()
                WHERE id = $1 AND status = 'frozen'
                RETURNING *
                """,
                membership_id,
            )
            if row:
                logger.info("Membership unfrozen", membership_id=membership_id,
                            stripe_resumed=bool(sub_id))
            return dict(row) if row else None

    # ── Cancel ───────────────────────────────────────────────────────────────

    async def cancel_membership(self, membership_id: str, reason: str | None = None) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE member_memberships
                SET status = 'cancelled', cancelled_at = NOW(), cancellation_reason = $2, updated_at = NOW()
                WHERE id = $1 AND status IN ('active', 'frozen')
                RETURNING *
                """,
                membership_id, reason,
            )
            if row:
                logger.info("Membership cancelled", membership_id=membership_id)
            return dict(row) if row else None

    # ── Eligibility Check ────────────────────────────────────────────────────

    async def check_eligibility(
        self, member_id: str, class_type_id: str | None = None,
        is_virtual: bool = False, is_community: bool = False,
        modality: str = "in_studio",
    ) -> dict:
        """Check if member has an active membership that allows booking.

        Priority order:
        1. FREE First Class pass (use first for any class if available)
        2. Community Class Pass (for community classes)
        3. Class-specific passes (10-class pack, single class, etc.)
        4. Unlimited memberships

        For community classes: try Community Pass first, then unlimited.
        For all classes: try Free First Class first if they have one.
        """
        memberships = await self.get_member_memberships(member_id, active_only=True)

        def _is_valid(mm: dict) -> bool:
            if mm["status"] != "active":
                return False
            if mm.get("ends_at") and mm["ends_at"] < datetime.now(timezone.utc):
                return False
            if mm["membership_type"] in ("class_pack", "single_class") and (mm.get("classes_remaining") or 0) <= 0:
                return False
            return True

        def _make_result(mm: dict) -> dict:
            return {
                "eligible": True,
                "membership_id": str(mm["id"]),
                "type": mm["membership_type"],
                "access_scope": mm.get("access_scope", "in_studio"),
                "classes_remaining": mm.get("classes_remaining"),
            }

        not_eligible = {"eligible": False, "membership_id": None, "type": None, "access_scope": None, "classes_remaining": None}

        # Modality × access_scope gate. Three modalities the platform supports:
        #   - in_studio: needs in_studio or all_access plan
        #   - virtual:   needs online    or all_access plan
        #   - hybrid:    any plan — in_studio members attend in person,
        #                online members attend on Zoom; the zoom-link
        #                delivery path independently gates which attendees
        #                actually receive the join URL.
        # all_access plans always pass.
        normalized_modality = modality if modality in ("in_studio", "virtual", "hybrid") else "in_studio"

        def _scope_covers(mm: dict) -> bool:
            scope = (mm.get("access_scope") or "in_studio").lower()
            if scope == "all_access":
                return True
            if normalized_modality == "hybrid":
                return scope in ("in_studio", "online")
            if normalized_modality == "virtual":
                return scope == "online"
            return scope == "in_studio"

        # Categorize valid memberships
        free_first_class = None
        community_pass = None
        class_packs = []
        unlimited = []

        for mm in memberships:
            if not _is_valid(mm):
                continue
            if not _scope_covers(mm):
                continue
            name_lower = (mm.get("type_name") or "").lower()

            if "free first class" in name_lower or ("free" in name_lower and "first" in name_lower):
                free_first_class = mm
            elif "community" in name_lower:
                community_pass = mm
            elif mm["membership_type"] in ("class_pack", "single_class", "intro_offer"):
                class_packs.append(mm)
            elif mm["membership_type"] == "unlimited":
                unlimited.append(mm)

        # Priority 1: Unlimited membership
        if unlimited:
            return _make_result(unlimited[0])

        # Priority 2: Free First Class
        if free_first_class:
            return _make_result(free_first_class)

        # Priority 3: Community Class Pass (community classes ONLY)
        if is_community and community_pass:
            return _make_result(community_pass)

        # Priority 4: Class packs / single passes
        if class_packs:
            return _make_result(class_packs[0])

        return not_eligible

    # ── Deduct Class ─────────────────────────────────────────────────────────

    async def deduct_class(self, membership_id: str, db=None) -> int | None:
        """Deduct one class from a class pack. Returns remaining count.

        If `db` is provided, the deduct runs on that connection — use this
        when the caller is inside a transaction (booking flow) and needs
        the deduct to roll back atomically with the booking insert. Without
        it, opening a fresh connection here means two concurrent bookings
        on the last credit can both succeed.
        """
        if db is not None:
            row = await db.fetchrow(
                """
                UPDATE member_memberships
                SET classes_remaining = classes_remaining - 1, updated_at = NOW()
                WHERE id = $1 AND classes_remaining > 0
                RETURNING classes_remaining
                """,
                membership_id,
            )
            return row["classes_remaining"] if row else None
        async with get_tenant_db() as conn:
            row = await conn.fetchrow(
                """
                UPDATE member_memberships
                SET classes_remaining = classes_remaining - 1, updated_at = NOW()
                WHERE id = $1 AND classes_remaining > 0
                RETURNING classes_remaining
                """,
                membership_id,
            )
            return row["classes_remaining"] if row else None
