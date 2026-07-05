"""AuraFlow — GDPR Data Deletion & Export Service

Handles member data deletion requests (right to be forgotten),
data export (right to data portability), and anonymization.
"""
import uuid
from datetime import datetime, timezone, timedelta

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.core.tenant_context import get_organization_id


DELETION_GRACE_PERIOD_DAYS = 30


class DataDeletionService:

    # ── Deletion Requests ────────────────────────────────────────────────

    async def request_deletion(self, member_id: str) -> dict:
        """Create a GDPR deletion request with a 30-day grace period."""
        now = datetime.now(timezone.utc)
        scheduled_at = now + timedelta(days=DELETION_GRACE_PERIOD_DAYS)
        request_id = str(uuid.uuid4())

        async with get_tenant_db() as db:
            # Check for existing pending request
            existing = await db.fetchrow(
                """
                SELECT id FROM gdpr_deletion_requests
                WHERE member_id = $1 AND status = 'pending'
                """,
                member_id,
            )
            if existing:
                return {
                    "id": str(existing["id"]),
                    "member_id": member_id,
                    "status": "pending",
                    "message": "A deletion request is already pending.",
                }

            row = await db.fetchrow(
                """
                INSERT INTO gdpr_deletion_requests
                    (id, member_id, requested_at, scheduled_deletion_at, status)
                VALUES ($1, $2, $3, $4, 'pending')
                RETURNING *
                """,
                request_id, member_id, now, scheduled_at,
            )

        logger.info(
            "GDPR deletion requested",
            member_id=member_id,
            request_id=request_id,
            scheduled_at=scheduled_at.isoformat(),
        )
        return dict(row)

    async def get_deletion_request_status(self, member_id: str) -> dict | None:
        """Get the latest pending deletion request for a member."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT * FROM gdpr_deletion_requests
                WHERE member_id = $1
                ORDER BY requested_at DESC
                LIMIT 1
                """,
                member_id,
            )
        return dict(row) if row else None

    async def cancel_deletion_request(self, request_id: str) -> dict | None:
        """Cancel a pending deletion request."""
        now = datetime.now(timezone.utc)
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE gdpr_deletion_requests
                SET status = 'cancelled', cancelled_at = $2
                WHERE id = $1 AND status = 'pending'
                RETURNING *
                """,
                request_id, now,
            )
        if row:
            logger.info("GDPR deletion request cancelled", request_id=request_id)
        return dict(row) if row else None

    # ── Data Deletion (Anonymization) ────────────────────────────────────

    async def execute_deletion(self, member_id: str) -> bool:
        """
        Execute GDPR data deletion by anonymizing the member record.
        Keeps transaction records for accounting but anonymizes them.
        """
        anonymized_email = f"deleted_{uuid.uuid4().hex[:12]}@removed.local"
        now = datetime.now(timezone.utc)

        async with get_tenant_db() as db:
            # 1. Get member info for Stripe cancellation
            member = await db.fetchrow(
                "SELECT * FROM members WHERE id = $1", member_id
            )
            if not member:
                logger.warning("Member not found for deletion", member_id=member_id)
                return False

            # 2. Cancel any active Stripe subscriptions (best-effort, outside txn)
            await self._cancel_stripe_subscriptions(member_id, db)

            # 3-9. All local data changes in a single transaction
            async with db.transaction():
                # 3. Anonymize member record. Post-Phase-C: plaintext PHI
                # columns no longer exist; we only null the _enc shadows
                # plus the derived (phone_hash, birthday_month/day) and
                # non-PHI fields like gender / photo_url / tags.
                await db.execute(
                    """
                    UPDATE members SET
                        first_name = 'Deleted',
                        last_name = 'User',
                        email = $2,
                        gender = NULL,
                        photo_url = NULL,
                        tags = NULL,
                        phone_enc = NULL,
                        address_line1_enc = NULL,
                        city_enc = NULL,
                        state_enc = NULL,
                        postal_code_enc = NULL,
                        emergency_contact_name_enc = NULL,
                        emergency_contact_phone_enc = NULL,
                        notes_enc = NULL,
                        date_of_birth_enc = NULL,
                        phone_hash = NULL,
                        birthday_month = NULL,
                        birthday_day = NULL,
                        is_active = FALSE,
                        updated_at = $3
                    WHERE id = $1
                    """,
                    member_id, anonymized_email, now,
                )

                # 4. Anonymize transaction records (keep amounts for accounting)
                await db.execute(
                    """
                    UPDATE transactions SET
                        description = 'Anonymized - GDPR deletion'
                    WHERE member_id = $1
                    """,
                    member_id,
                )

                # 5. Delete communication log entries
                await db.execute(
                    "DELETE FROM communication_log WHERE member_id = $1",
                    member_id,
                )

                # 6. Remove bookings older than 7 years
                cutoff = now - timedelta(days=7 * 365)
                await db.execute(
                    """
                    DELETE FROM bookings
                    WHERE member_id = $1 AND booked_at < $2
                    """,
                    member_id, cutoff,
                )

                # 7. Delete health data
                await db.execute(
                    "DELETE FROM member_health_data WHERE member_id = $1",
                    member_id,
                )

                # 8. Delete member notes
                await db.execute(
                    "DELETE FROM member_notes WHERE member_id = $1",
                    member_id,
                )

                # 9. Mark deletion request as completed
                await db.execute(
                    """
                    UPDATE gdpr_deletion_requests
                    SET status = 'completed', completed_at = $2
                    WHERE member_id = $1 AND status = 'pending'
                    """,
                    member_id, now,
                )

        logger.info("GDPR deletion executed", member_id=member_id)
        return True

    async def _cancel_stripe_subscriptions(self, member_id: str, db) -> None:
        """Cancel active Stripe subscriptions for a member. Best-effort."""
        try:
            # Find active memberships with stripe subscription IDs
            rows = await db.fetch(
                """
                SELECT mm.stripe_subscription_id
                FROM member_memberships mm
                WHERE mm.member_id = $1
                  AND mm.status = 'active'
                  AND mm.stripe_subscription_id IS NOT NULL
                """,
                member_id,
            )

            if not rows:
                return

            org_id = get_organization_id()

            # Get Stripe Connect account — chokepoint helper, server-derived only.
            from app.services.payments.connect_account import resolve_stripe_account_for_org
            stripe_account_id = await resolve_stripe_account_for_org(org_id)

            from app.services.payments.stripe_service import StripeService
            stripe_svc = StripeService()

            for row in rows:
                try:
                    await stripe_svc.cancel_subscription(
                        subscription_id=row["stripe_subscription_id"],
                        at_period_end=False,
                        stripe_account_id=stripe_account_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to cancel Stripe subscription during GDPR deletion",
                        subscription_id=row["stripe_subscription_id"],
                        error=str(e),
                    )

            # Mark memberships as cancelled
            await db.execute(
                """
                UPDATE member_memberships
                SET status = 'cancelled', updated_at = NOW()
                WHERE member_id = $1 AND status = 'active'
                """,
                member_id,
            )

        except Exception as e:
            logger.warning(
                "Error cancelling Stripe subscriptions during GDPR deletion",
                member_id=member_id,
                error=str(e),
            )

    # ── Data Export (GDPR Portability) ───────────────────────────────────

    async def export_member_data(self, member_id: str) -> dict:
        """
        Export all member data for GDPR data portability (Article 20).
        Returns a comprehensive dict of all member-related data.
        """
        async with get_tenant_db() as db:
            # Member profile. Route through _row_with_decrypted_phi so the
            # GDPR Article 20 export contains the actual plaintext PHI
            # rather than encrypted bytes (the *_enc shadows would
            # otherwise be exposed as opaque blobs after Phase C drops
            # the plaintext columns).
            from app.services.members.member_service import _row_with_decrypted_phi
            member = await db.fetchrow(
                "SELECT * FROM members WHERE id = $1", member_id
            )
            if not member:
                return {}

            profile = _row_with_decrypted_phi(dict(member))
            # Convert non-serializable types
            for key, val in profile.items():
                if isinstance(val, datetime):
                    profile[key] = val.isoformat()
                elif isinstance(val, uuid.UUID):
                    profile[key] = str(val)

            # Memberships
            memberships = await db.fetch(
                """
                SELECT mm.*, mt.name AS type_name, mt.type AS membership_type
                FROM member_memberships mm
                LEFT JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE mm.member_id = $1
                ORDER BY mm.created_at DESC
                """,
                member_id,
            )

            # Transactions
            transactions = await db.fetch(
                """
                SELECT id, amount_cents, type, status, description, created_at
                FROM transactions
                WHERE member_id = $1
                ORDER BY created_at DESC
                """,
                member_id,
            )

            # Bookings
            bookings = await db.fetch(
                """
                SELECT b.id, b.class_session_id, b.status, b.booked_at,
                       b.cancelled_at, b.checked_in_at, b.cancellation_reason,
                       cs.title AS session_title, cs.starts_at, cs.ends_at,
                       ct.name AS class_type_name
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                WHERE b.member_id = $1
                ORDER BY cs.starts_at DESC
                """,
                member_id,
            )

            # Communication history. communication_log columns:
            # channel, type, recipient, subject, body_preview, status.
            communications = await db.fetch(
                """
                SELECT id, channel, type, recipient, subject, body_preview, status, created_at
                FROM communication_log
                WHERE member_id = $1
                ORDER BY created_at DESC
                """,
                member_id,
            )

            # Notes. note column is dropped in Phase C; read note_enc and
            # decrypt for the export.
            from app.services.members.member_service import _row_with_decrypted_note
            note_rows = await db.fetch(
                """
                SELECT id, note_enc, is_pinned, created_at
                FROM member_notes
                WHERE member_id = $1
                ORDER BY created_at DESC
                """,
                member_id,
            )
            notes = [_row_with_decrypted_note(dict(r)) for r in note_rows]

            # Health data
            health = await db.fetchrow(
                "SELECT * FROM member_health_data WHERE member_id = $1",
                member_id,
            )

        def _serialize_rows(rows):
            result = []
            for row in rows:
                d = dict(row)
                for key, val in d.items():
                    if isinstance(val, datetime):
                        d[key] = val.isoformat()
                    elif isinstance(val, uuid.UUID):
                        d[key] = str(val)
                    elif isinstance(val, (bytes, memoryview)):
                        d[key] = "[encrypted data]"
                result.append(d)
            return result

        export = {
            "profile": profile,
            "memberships": _serialize_rows(memberships),
            "transactions": _serialize_rows(transactions),
            "bookings": _serialize_rows(bookings),
            "communications": _serialize_rows(communications),
            "notes": _serialize_rows(notes),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

        if health:
            health_dict = dict(health)
            for key, val in health_dict.items():
                if isinstance(val, datetime):
                    health_dict[key] = val.isoformat()
                elif isinstance(val, uuid.UUID):
                    health_dict[key] = str(val)
                elif isinstance(val, (bytes, memoryview)):
                    health_dict[key] = "[encrypted data]"
            export["health_data"] = health_dict

        logger.info("GDPR data export generated", member_id=member_id)
        return export
