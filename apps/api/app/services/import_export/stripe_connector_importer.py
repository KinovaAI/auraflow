"""AuraFlow — Stripe Connector Importer

Imports Stripe customer/subscription data from a studio's connected Stripe account
into AuraFlow members. Supports two modes:

1. Auto-sync: Fetches all customers from the studio's Stripe Connect account and
   matches them to existing AuraFlow members by email.
2. CSV upload: Accepts a CSV mapping member email -> stripe_customer_id for manual
   mapping.

This preserves members' payment methods and active subscriptions during migration
from another platform (e.g. Momoyoga) that used the same Stripe account.
"""
import asyncio
import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db


def _configure_stripe():
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeConnectorImporter:

    def __init__(self):
        _configure_stripe()

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _get_stripe_account_id(self, org_id: str) -> Optional[str]:
        """Get the Stripe Connect account ID for the organization."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT stripe_account_id FROM af_global.organizations WHERE id = $1",
                org_id,
            )
        if not row or not row.get("stripe_account_id"):
            return None
        return row["stripe_account_id"]

    async def _fetch_all_stripe_customers(self, stripe_account_id: str) -> list[dict]:
        """Fetch all customers from the studio's Stripe account."""
        _configure_stripe()
        customers = []
        has_more = True
        starting_after = None

        while has_more:
            params = {"limit": 100, "stripe_account": stripe_account_id}
            if starting_after:
                params["starting_after"] = starting_after

            result = await asyncio.to_thread(
                lambda p=params: stripe.Customer.list(**p)
            )
            for cust in result.data:
                if cust.get("deleted"):
                    continue
                customers.append({
                    "id": cust.id,
                    "email": (cust.email or "").lower().strip(),
                    "name": cust.name or "",
                    "created": cust.created,
                    "metadata": dict(cust.metadata) if cust.metadata else {},
                })

            has_more = result.has_more
            if result.data:
                starting_after = result.data[-1].id

        return customers

    async def _fetch_customer_subscriptions(
        self, customer_id: str, stripe_account_id: str
    ) -> list[dict]:
        """Fetch active subscriptions for a customer."""
        _configure_stripe()
        result = await asyncio.to_thread(
            lambda: stripe.Subscription.list(
                customer=customer_id,
                status="active",
                stripe_account=stripe_account_id,
                limit=100,
            )
        )
        subs = []
        for sub in result.data:
            items = []
            for item in sub["items"]["data"]:
                price = item.get("price", {})
                items.append({
                    "price_id": price.get("id"),
                    "product_id": price.get("product"),
                    "amount_cents": price.get("unit_amount"),
                    "interval": price.get("recurring", {}).get("interval") if price.get("recurring") else None,
                    "nickname": price.get("nickname") or "",
                })
            subs.append({
                "subscription_id": sub.id,
                "status": sub.status,
                "current_period_start": sub.current_period_start,
                "current_period_end": sub.current_period_end,
                "items": items,
            })
        return subs

    async def _verify_customer(self, customer_id: str, stripe_account_id: str) -> Optional[dict]:
        """Verify a single Stripe customer ID exists on the connected account."""
        _configure_stripe()
        try:
            cust = await asyncio.to_thread(
                lambda: stripe.Customer.retrieve(
                    customer_id, stripe_account=stripe_account_id
                )
            )
            if cust.get("deleted"):
                return None
            return {
                "id": cust.id,
                "email": (cust.email or "").lower().strip(),
                "name": cust.name or "",
            }
        except stripe.error.InvalidRequestError:
            return None

    def _parse_csv(self, csv_content: str) -> list[dict]:
        """Parse a CSV mapping emails to Stripe customer IDs.

        Expected columns: email, stripe_customer_id
        Optional: first_name, last_name
        """
        first_line = csv_content.split("\n")[0]
        delimiter = "\t" if "\t" in first_line else ","
        reader = csv.DictReader(io.StringIO(csv_content), delimiter=delimiter)
        rows = []
        for row in reader:
            normalized = {
                k.strip().lower().replace(" ", "_"): v.strip()
                for k, v in row.items()
                if v
            }
            email = (
                normalized.get("email")
                or normalized.get("e-mail")
                or normalized.get("email_address")
                or ""
            ).lower().strip()
            stripe_id = (
                normalized.get("stripe_customer_id")
                or normalized.get("customer_id")
                or normalized.get("stripe_id")
                or normalized.get("cus_id")
                or ""
            ).strip()
            if email and stripe_id:
                rows.append({"email": email, "stripe_customer_id": stripe_id})
        return rows

    # ── Dry Run: Auto-sync ─────────────────────────────────────────────────────

    async def dry_run_auto_sync(self, org_id: str) -> dict:
        """Preview auto-sync: fetch Stripe customers and match to AuraFlow members."""
        stripe_account_id = await self._get_stripe_account_id(org_id)
        if not stripe_account_id:
            return {
                "error": "No Stripe Connect account found. Please connect your Stripe account first.",
                "matched": 0,
                "unmatched_stripe": 0,
                "already_linked": 0,
                "matches": [],
                "unmatched": [],
            }

        # Fetch all Stripe customers
        stripe_customers = await self._fetch_all_stripe_customers(stripe_account_id)

        # Build email -> stripe customer map
        stripe_by_email = {}
        for cust in stripe_customers:
            if cust["email"]:
                stripe_by_email[cust["email"]] = cust

        # Fetch all AuraFlow members
        async with get_tenant_db() as db:
            members = await db.fetch(
                "SELECT id, email, first_name, last_name, stripe_customer_id FROM members"
            )

        matches = []
        already_linked = 0
        for member in members:
            email = (member["email"] or "").lower().strip()
            stripe_cust = stripe_by_email.pop(email, None)
            if stripe_cust:
                if member.get("stripe_customer_id") == stripe_cust["id"]:
                    already_linked += 1
                else:
                    matches.append({
                        "member_email": email,
                        "member_name": f"{member['first_name']} {member['last_name']}",
                        "member_id": str(member["id"]),
                        "stripe_customer_id": stripe_cust["id"],
                        "stripe_name": stripe_cust["name"],
                        "already_has_stripe": bool(member.get("stripe_customer_id")),
                    })

        # Remaining unmatched Stripe customers
        unmatched = [
            {
                "stripe_customer_id": c["id"],
                "stripe_email": c["email"],
                "stripe_name": c["name"],
            }
            for c in stripe_by_email.values()
        ]

        return {
            "matched": len(matches),
            "unmatched_stripe": len(unmatched),
            "already_linked": already_linked,
            "total_stripe_customers": len(stripe_customers),
            "total_members": len(members),
            "matches": matches,
            "unmatched": unmatched[:50],  # Limit preview to 50
        }

    # ── Dry Run: CSV ───────────────────────────────────────────────────────────

    async def dry_run_csv(self, csv_content: str, org_id: str) -> dict:
        """Preview CSV-based Stripe mapping."""
        stripe_account_id = await self._get_stripe_account_id(org_id)
        if not stripe_account_id:
            return {
                "error": "No Stripe Connect account found. Please connect your Stripe account first.",
                "matched": 0,
                "invalid": 0,
                "not_found": 0,
                "matches": [],
                "errors": [],
            }

        rows = self._parse_csv(csv_content)
        if not rows:
            return {
                "error": "No valid rows found. CSV must have 'email' and 'stripe_customer_id' columns.",
                "matched": 0,
                "invalid": 0,
                "not_found": 0,
                "matches": [],
                "errors": [],
            }

        # Look up members by email
        async with get_tenant_db() as db:
            members = await db.fetch(
                "SELECT id, email, first_name, last_name, stripe_customer_id FROM members"
            )
        members_by_email = {
            (m["email"] or "").lower().strip(): m for m in members
        }

        matches = []
        errors = []
        already_linked = 0

        for row in rows:
            member = members_by_email.get(row["email"])
            if not member:
                errors.append({
                    "email": row["email"],
                    "stripe_customer_id": row["stripe_customer_id"],
                    "error": "No matching AuraFlow member found",
                })
                continue

            if member.get("stripe_customer_id") == row["stripe_customer_id"]:
                already_linked += 1
                continue

            # Verify the Stripe customer ID exists
            cust = await self._verify_customer(row["stripe_customer_id"], stripe_account_id)
            if not cust:
                errors.append({
                    "email": row["email"],
                    "stripe_customer_id": row["stripe_customer_id"],
                    "error": f"Stripe customer '{row['stripe_customer_id']}' not found on connected account",
                })
                continue

            matches.append({
                "member_email": row["email"],
                "member_name": f"{member['first_name']} {member['last_name']}",
                "member_id": str(member["id"]),
                "stripe_customer_id": row["stripe_customer_id"],
                "stripe_name": cust["name"],
                "already_has_stripe": bool(member.get("stripe_customer_id")),
            })

        return {
            "matched": len(matches),
            "already_linked": already_linked,
            "invalid": len(errors),
            "total_rows": len(rows),
            "matches": matches,
            "errors": errors,
        }

    # ── Import: Link Stripe Customers ──────────────────────────────────────────

    async def import_stripe_customers(
        self,
        org_id: str,
        matches: list[dict],
        import_subscriptions: bool = False,
    ) -> dict:
        """Link Stripe customer IDs to AuraFlow members and optionally import subscriptions.

        Args:
            org_id: Organization ID
            matches: List of {member_id, stripe_customer_id} dicts
            import_subscriptions: If True, also fetch and link active subscriptions
        """
        stripe_account_id = await self._get_stripe_account_id(org_id)
        if not stripe_account_id:
            return {
                "linked": 0,
                "subscriptions_linked": 0,
                "errors": [{"error": "No Stripe Connect account found"}],
            }

        linked = 0
        subscriptions_linked = 0
        errors = []

        async with get_tenant_db() as db:
            for match in matches:
                member_id = match["member_id"]
                stripe_customer_id = match["stripe_customer_id"]

                try:
                    # Update member with stripe_customer_id
                    await db.execute(
                        """
                        UPDATE members
                        SET stripe_customer_id = $1,
                            source = CASE
                                WHEN source IS NULL OR source = '' THEN 'stripe_import'
                                WHEN source NOT LIKE '%stripe_import%' THEN source || ',stripe_import'
                                ELSE source
                            END,
                            updated_at = NOW()
                        WHERE id = $2
                        """,
                        stripe_customer_id, member_id,
                    )
                    linked += 1

                    # Update Stripe customer metadata to reference AuraFlow
                    try:
                        await asyncio.to_thread(
                            lambda cid=stripe_customer_id, mid=member_id: stripe.Customer.modify(
                                cid,
                                stripe_account=stripe_account_id,
                                metadata={"auraflow_member_id": mid},
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to update Stripe customer metadata",
                            customer_id=stripe_customer_id,
                            error=str(e),
                        )

                    # Import active subscriptions
                    if import_subscriptions:
                        try:
                            subs = await self._fetch_customer_subscriptions(
                                stripe_customer_id, stripe_account_id
                            )
                            for sub in subs:
                                # Check if this subscription is already linked
                                existing = await db.fetchrow(
                                    "SELECT id FROM member_memberships WHERE stripe_subscription_id = $1",
                                    sub["subscription_id"],
                                )
                                if existing:
                                    continue

                                # Try to match subscription to a membership type by price
                                for item in sub["items"]:
                                    if not item.get("amount_cents"):
                                        continue

                                    # Find matching membership type by price
                                    mt = await db.fetchrow(
                                        """
                                        SELECT id, name FROM membership_types
                                        WHERE price_cents = $1
                                          AND billing_period = $2
                                          AND is_active = true
                                        LIMIT 1
                                        """,
                                        item["amount_cents"],
                                        self._stripe_interval_to_billing_period(
                                            item.get("interval")
                                        ),
                                    )
                                    if mt:
                                        mm_id = str(uuid.uuid4())
                                        await db.execute(
                                            """
                                            INSERT INTO member_memberships
                                                (id, member_id, membership_type_id,
                                                 stripe_subscription_id, status,
                                                 start_date, current_period_end)
                                            VALUES ($1, $2, $3, $4, 'active', $5, $6)
                                            ON CONFLICT DO NOTHING
                                            """,
                                            mm_id,
                                            member_id,
                                            str(mt["id"]),
                                            sub["subscription_id"],
                                            datetime.fromtimestamp(
                                                sub["current_period_start"],
                                                tz=timezone.utc,
                                            ).date(),
                                            datetime.fromtimestamp(
                                                sub["current_period_end"],
                                                tz=timezone.utc,
                                            ).date(),
                                        )
                                        subscriptions_linked += 1
                                        logger.info(
                                            "Subscription linked",
                                            member_id=member_id,
                                            subscription_id=sub["subscription_id"],
                                            membership_type=mt["name"],
                                        )
                        except Exception as e:
                            errors.append({
                                "member_id": member_id,
                                "error": f"Failed to import subscriptions: {str(e)}",
                            })

                except Exception as e:
                    errors.append({
                        "member_id": member_id,
                        "stripe_customer_id": stripe_customer_id,
                        "error": str(e),
                    })

        logger.info(
            "Stripe connector import complete",
            linked=linked,
            subscriptions_linked=subscriptions_linked,
            errors=len(errors),
        )
        return {
            "linked": linked,
            "subscriptions_linked": subscriptions_linked,
            "errors": errors,
            "total": len(matches),
        }

    # ── Import: Auto-sync (convenience wrapper) ───────────────────────────────

    async def auto_sync_import(
        self, org_id: str, import_subscriptions: bool = False
    ) -> dict:
        """Full auto-sync: fetch Stripe customers, match by email, link them."""
        preview = await self.dry_run_auto_sync(org_id)
        if preview.get("error"):
            return {
                "linked": 0,
                "subscriptions_linked": 0,
                "errors": [{"error": preview["error"]}],
            }

        if not preview["matches"]:
            return {
                "linked": 0,
                "subscriptions_linked": 0,
                "already_linked": preview["already_linked"],
                "unmatched_stripe": preview["unmatched_stripe"],
                "errors": [],
                "total": 0,
            }

        result = await self.import_stripe_customers(
            org_id=org_id,
            matches=preview["matches"],
            import_subscriptions=import_subscriptions,
        )
        result["already_linked"] = preview["already_linked"]
        result["unmatched_stripe"] = preview["unmatched_stripe"]
        return result

    @staticmethod
    def _stripe_interval_to_billing_period(interval: Optional[str]) -> str:
        return {
            "month": "monthly",
            "year": "yearly",
            "week": "weekly",
            "day": "daily",
        }.get(interval or "", "monthly")
