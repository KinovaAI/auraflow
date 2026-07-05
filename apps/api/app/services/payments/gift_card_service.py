"""AuraFlow — Gift Card Service

Purchase, redeem, and manage gift cards for studio members.
Supports checkout integration, admin adjustments, and email delivery.
"""
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.logging import logger
from app.db.session import get_tenant_db


def _generate_code() -> str:
    """Generate a unique 16-character alphanumeric code in XXXX-XXXX-XXXX-XXXX format."""
    chars = string.ascii_uppercase + string.digits
    raw = "".join(secrets.choice(chars) for _ in range(16))
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"


def _normalize_code(code: str) -> str:
    """Normalize gift card code: uppercase, strip whitespace."""
    return code.strip().upper()


class GiftCardService:

    # ── Create ───────────────────────────────────────────────────────────────

    async def create_gift_card(
        self,
        amount_cents: int,
        purchaser_member_id: Optional[str] = None,
        recipient_email: Optional[str] = None,
        recipient_name: Optional[str] = None,
        message: Optional[str] = None,
        purchased_by_name: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> dict:
        """Create a new gift card. Optionally sends an email to the recipient."""
        if amount_cents <= 0:
            raise ValueError("Gift card amount must be positive")

        gift_card_id = str(uuid.uuid4())
        code = _generate_code()

        if expires_at is None:
            expires_at = datetime.now(timezone.utc) + timedelta(days=365)

        # Ensure code uniqueness (retry up to 5 times on collision)
        async with get_tenant_db() as db:
            for attempt in range(5):
                existing = await db.fetchrow(
                    "SELECT id FROM gift_cards WHERE code = $1", code
                )
                if not existing:
                    break
                code = _generate_code()
            else:
                raise RuntimeError("Failed to generate unique gift card code")

            row = await db.fetchrow(
                """
                INSERT INTO gift_cards
                    (id, code, amount_cents, balance_cents, status,
                     purchaser_member_id, purchased_by_name,
                     recipient_email, recipient_name, message, expires_at)
                VALUES ($1, $2, $3, $4, 'active', $5, $6, $7, $8, $9, $10)
                RETURNING *
                """,
                gift_card_id, code, amount_cents, amount_cents,
                purchaser_member_id, purchased_by_name,
                recipient_email, recipient_name, message, expires_at,
            )

        result = dict(row)
        logger.info(
            "Gift card created",
            gift_card_id=gift_card_id,
            code=code,
            amount_cents=amount_cents,
            recipient_email=recipient_email,
        )

        # Send email to recipient if provided
        if recipient_email:
            try:
                await self._send_gift_card_email(result)
            except Exception as e:
                logger.warning(
                    "Failed to send gift card email",
                    gift_card_id=gift_card_id,
                    error=str(e),
                )

        return result

    # ── Purchase (with payment) ──────────────────────────────────────────────

    # Stripe-routed payment methods defer card creation to the webhook.
    # Non-Stripe methods create the card immediately.
    _STRIPE_PAYMENT_METHODS = {"card", "stripe", "send_payment_link"}
    _IMMEDIATE_PAYMENT_METHODS = {"cash", "check", "comp", "venmo"}

    async def purchase_gift_card(
        self,
        amount_cents: int,
        payment_method: str,
        purchaser_member_id: Optional[str] = None,
        recipient_email: Optional[str] = None,
        recipient_name: Optional[str] = None,
        message: Optional[str] = None,
        purchased_by_name: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> dict:
        """Purchase a gift card with payment collection.

        Returns one of two shapes:
          - {"gift_card": <row>, "payment_method": "..."} — card created
            immediately for cash / check / comp / venmo (transaction also
            recorded).
          - {"checkout_url": "...", "checkout_session_id": "...",
             "payment_method": "..."} — Stripe checkout deferred. The
            actual gift card row is created by the webhook handler when
            checkout.session.completed fires. Caller should redirect the
            user to checkout_url.

        This replaces the old free-creation flow that just inserted a
        row with no payment collected. Direct calls to create_gift_card
        without this wrapper are now considered comped/manual issuance
        and should only be made by trusted code (admin scripts).
        """
        if amount_cents <= 0:
            raise ValueError("Gift card amount must be positive")

        if payment_method in self._STRIPE_PAYMENT_METHODS:
            if not purchaser_member_id:
                raise ValueError(
                    "purchaser_member_id is required for card / stripe / "
                    "send_payment_link payment — Stripe Checkout needs a "
                    "customer record. Use cash/check/comp for non-member buyers."
                )
            if not (success_url and cancel_url):
                raise ValueError(
                    "success_url and cancel_url are required when paying "
                    "via card / stripe / send_payment_link"
                )
            return await self._purchase_via_stripe(
                amount_cents=amount_cents,
                purchaser_member_id=purchaser_member_id,
                recipient_email=recipient_email,
                recipient_name=recipient_name,
                message=message,
                purchased_by_name=purchased_by_name,
                expires_at=expires_at,
                success_url=success_url,
                cancel_url=cancel_url,
                payment_method=payment_method,
            )

        if payment_method in self._IMMEDIATE_PAYMENT_METHODS:
            return await self._purchase_immediate(
                amount_cents=amount_cents,
                payment_method=payment_method,
                purchaser_member_id=purchaser_member_id,
                recipient_email=recipient_email,
                recipient_name=recipient_name,
                message=message,
                purchased_by_name=purchased_by_name,
                expires_at=expires_at,
            )

        raise ValueError(
            f"Unsupported payment_method: {payment_method!r}. "
            f"Use one of: {', '.join(sorted(self._STRIPE_PAYMENT_METHODS | self._IMMEDIATE_PAYMENT_METHODS))}"
        )

    async def _purchase_via_stripe(
        self,
        amount_cents: int,
        purchaser_member_id: str,
        success_url: str,
        cancel_url: str,
        payment_method: str,
        recipient_email: Optional[str],
        recipient_name: Optional[str],
        message: Optional[str],
        purchased_by_name: Optional[str],
        expires_at: Optional[datetime],
    ) -> dict:
        """Open a Stripe Checkout session. Card creation is deferred to
        the webhook handler — this returns only a checkout URL.

        Buyer's gift-card details (recipient, message, expiry) are
        encoded into Stripe metadata so the webhook can reconstruct
        the create_gift_card call when payment confirms.
        """
        from app.services.payments.stripe_service import StripeService
        from app.core.tenant_context import require_tenant_context
        ctx = require_tenant_context()

        gc_metadata = {
            "auraflow_gift_card": "true",
            "amount_cents": str(amount_cents),
            "purchaser_member_id": purchaser_member_id,
            "auraflow_org_schema": ctx.schema_name,
        }
        if recipient_email:
            gc_metadata["recipient_email"] = recipient_email
        if recipient_name:
            gc_metadata["recipient_name"] = recipient_name
        if message:
            # Stripe metadata values are limited to 500 chars
            gc_metadata["message"] = message[:500]
        if purchased_by_name:
            gc_metadata["purchased_by_name"] = purchased_by_name
        if expires_at:
            gc_metadata["expires_at"] = expires_at.isoformat()

        session = await StripeService().create_one_time_checkout_session(
            org_id=ctx.organization_id,
            member_id=purchaser_member_id,
            item_name=f"Gift Card — ${amount_cents/100:.2f}",
            price_cents=amount_cents,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=gc_metadata,
        )
        return {
            "gift_card": None,
            "checkout_url": session["url"],
            "checkout_session_id": session["session_id"],
            "payment_method": payment_method,
        }

    async def _purchase_immediate(
        self,
        amount_cents: int,
        payment_method: str,
        purchaser_member_id: Optional[str],
        recipient_email: Optional[str],
        recipient_name: Optional[str],
        message: Optional[str],
        purchased_by_name: Optional[str],
        expires_at: Optional[datetime],
    ) -> dict:
        """Cash / check / comp / venmo path. Create the card now and
        record a transaction with the chosen payment method. Comp
        transactions get recorded with type='comp' so reporting shows
        the lost revenue."""
        gc_row = await self.create_gift_card(
            amount_cents=amount_cents,
            purchaser_member_id=purchaser_member_id,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            message=message,
            purchased_by_name=purchased_by_name,
            expires_at=expires_at,
        )

        # Record a transaction so the sale shows up in reports. Comp
        # purchases still record with amount_cents but a flag that the
        # studio is eating the cost — distinguishable from paid sales.
        if purchaser_member_id:
            import json as _json
            async with get_tenant_db() as db:
                await db.execute(
                    """
                    INSERT INTO transactions
                        (id, member_id, type, amount_cents, status, description,
                         metadata, fee_cents, net_amount_cents)
                    VALUES ($1, $2, $3, $4, 'completed', $5, $6::jsonb, 0, $4)
                    """,
                    str(uuid.uuid4()),
                    purchaser_member_id,
                    "comp" if payment_method == "comp" else "payment",
                    amount_cents,
                    f"Gift card purchase ({payment_method}) — {gc_row['code']}",
                    _json.dumps({"gift_card_id": str(gc_row["id"]), "payment_method": payment_method}),
                )

        return {
            "gift_card": gc_row,
            "checkout_url": None,
            "checkout_session_id": None,
            "payment_method": payment_method,
        }

    # ── Redeem ───────────────────────────────────────────────────────────────

    async def redeem_gift_card(
        self,
        code: str,
        member_id: str,
        amount_cents: Optional[int] = None,
    ) -> dict:
        """
        Redeem a gift card (full or partial balance) onto a member.
        Returns the redemption record.
        """
        code = _normalize_code(code)

        async with get_tenant_db() as db:
            gc = await db.fetchrow(
                "SELECT * FROM gift_cards WHERE code = $1 FOR UPDATE",
                code,
            )
            if not gc:
                raise ValueError("Gift card not found")
            if gc["status"] == "voided":
                raise ValueError("Gift card has been voided")
            if gc["status"] == "fully_redeemed":
                raise ValueError("Gift card has already been fully redeemed")
            if gc["expires_at"] and gc["expires_at"] < datetime.now(timezone.utc):
                # Mark as expired if not already
                await db.execute(
                    "UPDATE gift_cards SET status = 'expired', updated_at = NOW() WHERE id = $1",
                    gc["id"],
                )
                raise ValueError("Gift card has expired")
            if gc["balance_cents"] <= 0:
                raise ValueError("Gift card has no remaining balance")

            redeem_amount = amount_cents if amount_cents is not None else gc["balance_cents"]
            if redeem_amount <= 0:
                raise ValueError("Redemption amount must be positive")
            if redeem_amount > gc["balance_cents"]:
                raise ValueError(
                    f"Insufficient balance: {gc['balance_cents']} cents available, "
                    f"{redeem_amount} cents requested"
                )

            new_balance = gc["balance_cents"] - redeem_amount
            new_status = "fully_redeemed" if new_balance == 0 else "active"

            await db.execute(
                """
                UPDATE gift_cards
                SET balance_cents = $1, status = $2, updated_at = NOW()
                WHERE id = $3
                """,
                new_balance, new_status, gc["id"],
            )

            redemption_id = str(uuid.uuid4())
            redemption = await db.fetchrow(
                """
                INSERT INTO gift_card_redemptions (id, gift_card_id, member_id, amount_cents)
                VALUES ($1, $2, $3, $4)
                RETURNING *
                """,
                redemption_id, gc["id"], member_id, redeem_amount,
            )

        logger.info(
            "Gift card redeemed",
            gift_card_id=gc["id"],
            member_id=member_id,
            amount_cents=redeem_amount,
            remaining_balance=new_balance,
        )
        return dict(redemption)

    # ── Check Balance ────────────────────────────────────────────────────────

    async def check_balance(self, code: str) -> dict:
        """Public balance check by code. Returns gift card info."""
        code = _normalize_code(code)
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT id, code, amount_cents, balance_cents, status,
                       recipient_name, expires_at, created_at
                FROM gift_cards WHERE code = $1
                """,
                code,
            )
        if not row:
            raise ValueError("Gift card not found")

        result = dict(row)

        # Check if expired but not yet marked
        if (
            result["status"] == "active"
            and result["expires_at"]
            and result["expires_at"] < datetime.now(timezone.utc)
        ):
            async with get_tenant_db() as db:
                await db.execute(
                    "UPDATE gift_cards SET status = 'expired', updated_at = NOW() WHERE id = $1",
                    result["id"],
                )
            result["status"] = "expired"

        return result

    # ── Member: List my purchased cards ──────────────────────────────────────

    async def list_cards_purchased_by(self, purchaser_member_id: str) -> list[dict]:
        """Cards a specific member has bought. Used by the member-portal
        "My Gift Cards" view so the buyer can see codes for cards they
        purchased — particularly important when the buyer didn't enter
        a recipient email and is using the card themselves."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM gift_cards
                WHERE purchaser_member_id = $1
                ORDER BY created_at DESC
                """,
                purchaser_member_id,
            )
            return [dict(r) for r in rows]

    async def list_cards_for_member(
        self, member_id: str, member_email: str | None,
    ) -> list[dict]:
        """All gift cards relevant to a member — cards they purchased AND
        cards where they are the recipient (matched on email). Each row
        is annotated with `relationship` ∈ {"purchased", "received",
        "purchased_and_received"} so the UI can label them.

        Recipient match is by email rather than by id because the
        gift_cards schema doesn't carry recipient_member_id — gift
        cards can be sent to non-members. Email match is the
        practical link for members.
        """
        async with get_tenant_db() as db:
            params: list = [member_id]
            email_clause = ""
            if member_email:
                params.append(member_email.strip().lower())
                email_clause = "OR LOWER(recipient_email) = $2"
            rows = await db.fetch(
                f"""
                SELECT * FROM gift_cards
                WHERE purchaser_member_id = $1
                   {email_clause}
                ORDER BY created_at DESC
                """,
                *params,
            )
            out = []
            for r in rows:
                d = dict(r)
                purchased = str(d.get("purchaser_member_id") or "") == str(member_id)
                received = bool(
                    member_email
                    and (d.get("recipient_email") or "").strip().lower()
                        == member_email.strip().lower()
                )
                if purchased and received:
                    d["relationship"] = "purchased_and_received"
                elif purchased:
                    d["relationship"] = "purchased"
                else:
                    d["relationship"] = "received"
                out.append(d)
            return out

    # ── Admin: List ──────────────────────────────────────────────────────────

    async def list_gift_cards(
        self,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List gift cards with optional filters."""
        conditions: list[str] = []
        params: list = []
        idx = 1

        if status:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1

        if search:
            safe = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(
                f"(code ILIKE ${idx} OR recipient_email ILIKE ${idx} "
                f"OR recipient_name ILIKE ${idx} OR purchased_by_name ILIKE ${idx})"
            )
            params.append(f"%{safe}%")
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"""
                SELECT * FROM gift_cards {where}
                ORDER BY created_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}
                """,
                *params,
            )
            return [dict(r) for r in rows]

    # ── Admin: Detail ────────────────────────────────────────────────────────

    async def get_gift_card(self, gift_card_id: str) -> Optional[dict]:
        """Get a gift card with its redemption history."""
        async with get_tenant_db() as db:
            gc = await db.fetchrow(
                "SELECT * FROM gift_cards WHERE id = $1", gift_card_id
            )
            if not gc:
                return None

            redemptions = await db.fetch(
                """
                SELECT r.*, m.first_name, m.last_name, m.email AS member_email
                FROM gift_card_redemptions r
                LEFT JOIN members m ON m.id = r.member_id
                WHERE r.gift_card_id = $1
                ORDER BY r.created_at DESC
                """,
                gift_card_id,
            )

        result = dict(gc)
        result["redemptions"] = [dict(r) for r in redemptions]
        return result

    # ── Admin: Void ──────────────────────────────────────────────────────────

    async def void_gift_card(
        self, gift_card_id: str, reason: Optional[str] = None
    ) -> dict:
        """Void a gift card (admin action). Sets balance to 0."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE gift_cards
                SET status = 'voided', balance_cents = 0,
                    voided_at = NOW(), void_reason = $1, updated_at = NOW()
                WHERE id = $2 AND status != 'voided'
                RETURNING *
                """,
                reason, gift_card_id,
            )
        if not row:
            raise ValueError("Gift card not found or already voided")

        logger.info("Gift card voided", gift_card_id=gift_card_id, reason=reason)
        return dict(row)

    # ── Admin: Adjust Balance ────────────────────────────────────────────────

    async def adjust_balance(
        self, gift_card_id: str, amount_cents: int, reason: str
    ) -> dict:
        """
        Admin balance adjustment (positive = add, negative = subtract).
        Cannot go below 0.
        """
        async with get_tenant_db() as db:
            gc = await db.fetchrow(
                "SELECT * FROM gift_cards WHERE id = $1 FOR UPDATE",
                gift_card_id,
            )
            if not gc:
                raise ValueError("Gift card not found")
            if gc["status"] == "voided":
                raise ValueError("Cannot adjust a voided gift card")

            new_balance = gc["balance_cents"] + amount_cents
            if new_balance < 0:
                raise ValueError(
                    f"Adjustment would result in negative balance: {new_balance}"
                )

            new_status = "fully_redeemed" if new_balance == 0 else "active"

            row = await db.fetchrow(
                """
                UPDATE gift_cards
                SET balance_cents = $1, status = $2, updated_at = NOW()
                WHERE id = $3
                RETURNING *
                """,
                new_balance, new_status, gift_card_id,
            )

        logger.info(
            "Gift card balance adjusted",
            gift_card_id=gift_card_id,
            adjustment=amount_cents,
            new_balance=new_balance,
            reason=reason,
        )
        return dict(row)

    # ── Checkout Integration ─────────────────────────────────────────────────

    async def apply_to_transaction(
        self,
        code: str,
        transaction_amount_cents: int,
        member_id: str,
        db=None,
        transaction_id: str | None = None,
    ) -> dict:
        """
        Apply a gift card during checkout. Deducts up to the transaction amount.
        Returns {discount_cents, remaining_balance, gift_card_id, redemption_id}.

        If `db` is provided, runs on the caller's connection so the gift-card
        debit + redemption insert participate in the same transaction as the
        sale itself (POS create_transaction, membership purchase, etc.).
        Without it, two concurrent purchases on the last $X of a card can
        both succeed via separate connections.

        If `transaction_id` is provided, the redemption row links back to
        the parent transaction (POS sale or membership transaction) so
        we can audit which sale consumed which redemption.
        """
        code = _normalize_code(code)

        async def _apply(conn) -> dict:
            gc = await conn.fetchrow(
                "SELECT * FROM gift_cards WHERE code = $1 FOR UPDATE",
                code,
            )
            if not gc:
                raise ValueError("Gift card not found")
            if gc["status"] != "active":
                raise ValueError(f"Gift card is {gc['status']}")
            if gc["expires_at"] and gc["expires_at"] < datetime.now(timezone.utc):
                await conn.execute(
                    "UPDATE gift_cards SET status = 'expired', updated_at = NOW() WHERE id = $1",
                    gc["id"],
                )
                raise ValueError("Gift card has expired")
            if gc["balance_cents"] <= 0:
                raise ValueError("Gift card has no remaining balance")

            discount = min(gc["balance_cents"], transaction_amount_cents)
            new_balance = gc["balance_cents"] - discount
            new_status = "fully_redeemed" if new_balance == 0 else "active"

            await conn.execute(
                """
                UPDATE gift_cards
                SET balance_cents = $1, status = $2, updated_at = NOW()
                WHERE id = $3
                """,
                new_balance, new_status, gc["id"],
            )

            redemption_id = str(uuid.uuid4())
            await conn.fetchrow(
                """
                INSERT INTO gift_card_redemptions
                    (id, gift_card_id, member_id, amount_cents, transaction_id)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
                """,
                redemption_id, gc["id"], member_id, discount, transaction_id,
            )

            logger.info(
                "Gift card applied to transaction",
                gift_card_id=gc["id"],
                discount_cents=discount,
                remaining_balance=new_balance,
                transaction_id=transaction_id,
            )

            return {
                "discount_cents": discount,
                "remaining_balance": new_balance,
                "gift_card_id": str(gc["id"]),
                "redemption_id": redemption_id,
            }

        if db is not None:
            return await _apply(db)
        async with get_tenant_db() as conn:
            return await _apply(conn)

    # ── Resend Email ─────────────────────────────────────────────────────────

    async def resend_gift_card_email(self, gift_card_id: str) -> bool:
        """Resend the gift card email to the recipient."""
        async with get_tenant_db() as db:
            gc = await db.fetchrow(
                "SELECT * FROM gift_cards WHERE id = $1", gift_card_id
            )
        if not gc:
            raise ValueError("Gift card not found")
        if not gc["recipient_email"]:
            raise ValueError("Gift card has no recipient email")

        await self._send_gift_card_email(dict(gc))
        logger.info(
            "Gift card email resent",
            gift_card_id=gift_card_id,
            recipient_email=gc["recipient_email"],
        )
        return True

    # ── Email Sending ────────────────────────────────────────────────────────

    async def _send_gift_card_email(self, gift_card: dict) -> None:
        """Send the gift card delivery email to the recipient."""
        from app.services.email.email_service import EmailService

        email_svc = EmailService()
        amount_dollars = gift_card["amount_cents"] / 100
        code = gift_card["code"]
        recipient_name = gift_card.get("recipient_name") or "there"
        purchased_by = gift_card.get("purchased_by_name") or "Someone special"
        message = gift_card.get("message") or ""

        message_html = ""
        if message:
            message_html = f"""
            <div style="background:#f8f5f0;border-left:4px solid #8b6f47;padding:16px 20px;
                        margin:24px 0;border-radius:0 8px 8px 0;font-style:italic;color:#555;">
                <p style="margin:0 0 8px 0;font-size:13px;color:#8b6f47;font-style:normal;
                          font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">
                    Personal Message
                </p>
                <p style="margin:0;font-size:15px;line-height:1.6;">"{message}"</p>
            </div>
            """

        html_content = f"""
        <div style="max-width:560px;margin:0 auto;font-family:'Segoe UI',Roboto,sans-serif;
                    color:#333;">
            <div style="text-align:center;padding:32px 0 24px;">
                <h1 style="margin:0;font-size:28px;color:#2d2d2d;font-weight:300;
                           letter-spacing:-0.5px;">
                    You've received a gift card!
                </h1>
                <p style="margin:8px 0 0;font-size:15px;color:#777;">
                    From <strong>{purchased_by}</strong>
                </p>
            </div>

            {message_html}

            <div style="background:linear-gradient(135deg,#8b6f47 0%,#a0845c 100%);
                        border-radius:12px;padding:32px;text-align:center;margin:24px 0;">
                <p style="margin:0 0 8px;font-size:13px;color:rgba(255,255,255,0.8);
                          text-transform:uppercase;letter-spacing:1px;">
                    Gift Card Value
                </p>
                <p style="margin:0 0 20px;font-size:42px;font-weight:700;color:#fff;">
                    ${amount_dollars:,.2f}
                </p>
                <div style="background:rgba(255,255,255,0.15);border-radius:8px;
                            padding:16px;display:inline-block;">
                    <p style="margin:0 0 4px;font-size:11px;color:rgba(255,255,255,0.7);
                              text-transform:uppercase;letter-spacing:1px;">
                        Your Code
                    </p>
                    <p style="margin:0;font-size:24px;font-weight:700;color:#fff;
                              letter-spacing:3px;font-family:'Courier New',monospace;">
                        {code}
                    </p>
                </div>
            </div>

            <div style="text-align:center;padding:16px 0 32px;">
                <p style="margin:0;font-size:14px;color:#777;line-height:1.6;">
                    Present this code at checkout or enter it online to redeem your gift card.
                </p>
            </div>
        </div>
        """

        await email_svc.send_email(
            to_email=gift_card["recipient_email"],
            subject=f"You've received a ${amount_dollars:,.2f} gift card from {purchased_by}!",
            html_content=html_content,
            email_type="transactional",
        )

        # Also email the purchaser a receipt with the code so they have
        # a copy regardless of where the gift card got delivered. If
        # purchaser_email == recipient_email (they bought it for
        # themselves), skip the duplicate.
        purchaser_id = gift_card.get("purchaser_member_id")
        if not purchaser_id:
            return
        try:
            async with get_tenant_db() as db:
                buyer = await db.fetchrow(
                    "SELECT email, first_name FROM members WHERE id = $1",
                    str(purchaser_id),
                )
            if not buyer or not buyer["email"]:
                return
            if buyer["email"].strip().lower() == (gift_card["recipient_email"] or "").strip().lower():
                return  # bought for self — recipient email already covers it
            buyer_first = buyer["first_name"] or "there"
            recipient_label = (
                gift_card.get("recipient_name")
                or gift_card.get("recipient_email")
                or "the recipient"
            )
            buyer_html = f"""
            <div style="max-width:560px;margin:0 auto;font-family:'Segoe UI',Roboto,sans-serif;color:#333;">
                <h2 style="font-weight:300;letter-spacing:-0.5px;color:#2d2d2d;">
                    Your gift card receipt
                </h2>
                <p>Hi {buyer_first},</p>
                <p>Thanks for purchasing a <strong>${amount_dollars:,.2f}</strong> gift card.
                We've emailed it to <strong>{recipient_label}</strong>. A copy of the code
                is below in case you'd like to print it, hand-deliver it, or keep it
                for your own records.</p>
                <div style="background:#f8f5f0;border:1px solid #e7dfd4;border-radius:8px;
                            padding:16px;text-align:center;margin:20px 0;">
                    <p style="margin:0 0 6px;font-size:11px;text-transform:uppercase;
                              letter-spacing:1px;color:#8b6f47;">Gift Card Code</p>
                    <p style="margin:0;font-size:22px;font-weight:700;letter-spacing:3px;
                              font-family:'Courier New',monospace;color:#2d2d2d;">{code}</p>
                </div>
                <p style="font-size:13px;color:#777;">
                    The recipient can redeem this at the studio or via your member portal.
                </p>
            </div>
            """
            await email_svc.send_email(
                to_email=buyer["email"],
                subject=f"Your gift card purchase — ${amount_dollars:,.2f}",
                html_content=buyer_html,
                member_id=str(purchaser_id),
                email_type="transactional",
            )
        except Exception as e:
            logger.warning(
                "Gift card purchaser receipt failed (non-fatal)",
                gift_card_id=str(gift_card.get("id")), error=str(e),
            )
