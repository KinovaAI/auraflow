"""AuraFlow — Member Credits Service

Generic banked-credits system for things that don't fit the
membership-pack model:

  - Instructor cancellation → preserve the client's paid credit
  - Courtesy grants (studio comping a session for a complaint)
  - Refund-to-credit (member doesn't want a Stripe refund, keep balance)
  - Gifts (gift card balances stay in their own table; this is for
    other ad-hoc gifts like a referral reward)

Each credit row has a monetary value (`amount_cents`) and an optional
`service_filter` that restricts which booking flow can consume it.

HIPAA-aware: the `notes` field is encrypted at rest in `notes_enc`
(BYTEA Fernet), same pattern as `members.notes_enc` / `member_notes.note_enc`.
There are no plaintext PHI columns on this table.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.members.member_service import _enc_or_none, _dec_or_none


VALID_SOURCES = {
    "instructor_cancellation", "courtesy", "refund_to_credit",
    "gift", "manual_grant",
}
VALID_SERVICE_FILTERS = {"private_session", "class", "workshop", None}
DEFAULT_EXPIRY_DAYS = 180  # 6 months, matches pack policy


def _row_with_decrypted_note(row: dict) -> dict:
    """Return a copy of a member_credit row with notes_enc decrypted into
    a plain `notes` key (and notes_enc removed). Matches the convention
    used for members + member_notes."""
    if not row:
        return row
    out = dict(row)
    enc = out.pop("notes_enc", None)
    if enc is not None:
        try:
            d = _dec_or_none(enc)
            if d is not None:
                out["notes"] = d
        except Exception:
            pass
    return out


class MemberCreditService:

    # ── Grant ─────────────────────────────────────────────────────────────

    async def grant_credit(
        self,
        member_id: str,
        amount_cents: int,
        source: str,
        service_filter: Optional[str] = None,
        source_ref_id: Optional[str] = None,
        expiry_days: Optional[int] = DEFAULT_EXPIRY_DAYS,
        notes: Optional[str] = None,
        granted_by_user_id: Optional[str] = None,
        db=None,
    ) -> dict:
        """Insert a new available credit for the member.

        Pass db= to run inside a caller's transaction (so a cancellation
        and its credit-grant land atomically).
        """
        if source not in VALID_SOURCES:
            raise ValueError(f"Invalid credit source: {source}")
        if service_filter not in VALID_SERVICE_FILTERS:
            raise ValueError(f"Invalid service_filter: {service_filter}")
        if amount_cents < 0:
            raise ValueError(f"amount_cents must be >= 0, got {amount_cents}")

        credit_id = str(uuid.uuid4())
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=expiry_days)
            if expiry_days else None
        )

        async def _exec(conn):
            return await conn.fetchrow(
                """
                INSERT INTO member_credits
                    (id, member_id, source, source_ref_id, service_filter,
                     amount_cents, expires_at, notes_enc, granted_by_user_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING *
                """,
                credit_id, member_id, source, source_ref_id, service_filter,
                amount_cents, expires_at, _enc_or_none(notes), granted_by_user_id,
            )

        if db is not None:
            row = await _exec(db)
        else:
            async with get_tenant_db() as conn:
                row = await _exec(conn)

        logger.info(
            "Member credit granted",
            credit_id=credit_id, member_id=member_id, source=source,
            amount_cents=amount_cents, expires_at=expires_at.isoformat() if expires_at else None,
        )
        return _row_with_decrypted_note(dict(row))

    # ── List ──────────────────────────────────────────────────────────────

    async def list_available_credits(
        self,
        member_id: str,
        service_filter: Optional[str] = None,
    ) -> list[dict]:
        """Credits available to apply RIGHT NOW: unused + unexpired +
        service_filter compatible. service_filter=None matches any
        credit (universal) or a credit specifically tagged for that
        service."""
        async with get_tenant_db() as db:
            if service_filter:
                rows = await db.fetch(
                    """
                    SELECT * FROM member_credits
                    WHERE member_id = $1
                      AND used_at IS NULL
                      AND (expires_at IS NULL OR expires_at > NOW())
                      AND (service_filter IS NULL OR service_filter = $2)
                    ORDER BY expires_at ASC NULLS LAST, created_at ASC
                    """,
                    member_id, service_filter,
                )
            else:
                rows = await db.fetch(
                    """
                    SELECT * FROM member_credits
                    WHERE member_id = $1
                      AND used_at IS NULL
                      AND (expires_at IS NULL OR expires_at > NOW())
                    ORDER BY expires_at ASC NULLS LAST, created_at ASC
                    """,
                    member_id,
                )
        return [_row_with_decrypted_note(dict(r)) for r in rows]

    async def list_all_credits(self, member_id: str) -> list[dict]:
        """Full credit history for the member, including used and expired.
        For the dashboard's audit-trail view."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM member_credits
                WHERE member_id = $1
                ORDER BY created_at DESC
                """,
                member_id,
            )
        return [_row_with_decrypted_note(dict(r)) for r in rows]

    async def get_credit(self, credit_id: str) -> Optional[dict]:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM member_credits WHERE id = $1", credit_id,
            )
        return _row_with_decrypted_note(dict(row)) if row else None

    # ── Apply ─────────────────────────────────────────────────────────────

    async def apply_credit(
        self,
        credit_id: str,
        member_id: str,
        booking_id: str,
        booking_table: str = "private_bookings",
        db=None,
    ) -> dict:
        """Mark a credit as consumed by a booking. Atomic — pass db= from
        the booking-creation transaction so the credit can't be
        double-spent under a race.

        Raises ValueError if the credit is missing, owned by a different
        member, already used, expired, or service_filter forbids the
        booking type.
        """
        async def _exec(conn):
            credit = await conn.fetchrow(
                "SELECT * FROM member_credits WHERE id = $1 FOR UPDATE",
                credit_id,
            )
            if not credit:
                raise ValueError(f"Credit not found: {credit_id}")
            if str(credit["member_id"]) != str(member_id):
                raise ValueError(
                    f"Credit {credit_id} belongs to a different member"
                )
            if credit["used_at"] is not None:
                raise ValueError(
                    f"Credit {credit_id} already used at {credit['used_at']}"
                )
            if credit["expires_at"] is not None and credit["expires_at"] <= datetime.now(timezone.utc):
                raise ValueError(
                    f"Credit {credit_id} expired on {credit['expires_at']}"
                )
            inferred_filter = (
                "private_session" if booking_table == "private_bookings"
                else "class" if booking_table == "bookings"
                else None
            )
            if (credit["service_filter"] is not None
                    and inferred_filter is not None
                    and credit["service_filter"] != inferred_filter):
                raise ValueError(
                    f"Credit {credit_id} restricted to {credit['service_filter']}; "
                    f"booking is {inferred_filter}"
                )
            row = await conn.fetchrow(
                """
                UPDATE member_credits
                SET used_at = NOW(),
                    used_booking_id = $1,
                    used_booking_table = $2,
                    updated_at = NOW()
                WHERE id = $3
                RETURNING *
                """,
                booking_id, booking_table, credit_id,
            )
            return row

        if db is not None:
            row = await _exec(db)
        else:
            async with get_tenant_db() as conn:
                async with conn.transaction():
                    row = await _exec(conn)

        logger.info(
            "Member credit applied",
            credit_id=credit_id, member_id=member_id, booking_id=booking_id,
            booking_table=booking_table, amount_cents=row["amount_cents"],
        )
        return _row_with_decrypted_note(dict(row))

    # ── Revoke / Refund ───────────────────────────────────────────────────

    async def revoke_credit(self, credit_id: str, reason: str | None = None) -> bool:
        """Soft-revoke a credit (e.g. staff issued by mistake). Sets a
        used_at + used_booking_id=null sentinel to take it out of the
        available list while preserving the audit trail.

        Implementation note: we abuse used_at to mean "consumed OR
        revoked"; the credit row stays for history but won't appear in
        list_available_credits."""
        async with get_tenant_db() as db:
            result = await db.execute(
                """
                UPDATE member_credits
                SET used_at = NOW(),
                    used_booking_id = '00000000-0000-0000-0000-000000000000',
                    used_booking_table = 'revoked',
                    notes_enc = COALESCE($2, notes_enc),
                    updated_at = NOW()
                WHERE id = $1
                  AND used_at IS NULL
                """,
                credit_id, _enc_or_none(reason),
            )
        return "UPDATE 1" in result

    # ── Maintenance ───────────────────────────────────────────────────────

    async def expire_old_credits(self) -> int:
        """No-op placeholder. expires_at is enforced at read time by
        list_available_credits; we don't need a sweep job to delete or
        mark expired rows. Kept so the worker shape is in place if we
        ever want to track expiry events for reporting."""
        return 0
