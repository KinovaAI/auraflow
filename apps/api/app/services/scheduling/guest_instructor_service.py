"""AuraFlow — Guest Instructor Service

CRUD for 1099-contractor instructors who teach WORKSHOPS only. Lives
in a dedicated `guest_instructors` table — fully separate from staff
`instructors`. Returning guests re-use their record so tax history
stays attached.

California labor law gate: a guest_instructor_id can only be set on a
courses row whose type='workshop'. The DB enforces this with a CHECK
constraint added in alembic a28_guest_instructors; the course service
also rejects assignment to non-workshops.

tax_id (SSN/EIN for 1099 reporting) is Fernet-encrypted at rest using
HEALTH_DATA_ENCRYPTION_KEY — same key that protects PHI columns.
"""
import uuid
from typing import Optional

from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.members.member_service import _enc_or_none, _dec_or_none


_GUEST_UPDATE_COLS = {
    "name", "bio", "photo_url", "email", "phone",
    "address_line1", "city", "state", "postal_code",
    "revenue_share_percent_to_guest", "notes", "is_active",
}


def _row_with_decrypted_tax_id(row) -> dict:
    """Return a plain dict with tax_id_encrypted decrypted into tax_id.
    Drops the *_encrypted key from the output so callers see a single
    `tax_id` field. Empty/missing returns None."""
    if not row:
        return row
    out = dict(row)
    enc = out.pop("tax_id_encrypted", None)
    out["tax_id"] = _dec_or_none(enc)
    return out


class GuestInstructorService:

    async def create_guest(self, data: dict) -> dict:
        guest_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO guest_instructors
                    (id, studio_id, name, bio, photo_url, email, phone,
                     address_line1, city, state, postal_code,
                     tax_id_encrypted,
                     revenue_share_percent_to_guest, notes, is_active)
                VALUES ($1, $2, $3, $4, $5, $6, $7,
                        $8, $9, $10, $11,
                        $12,
                        $13, $14, COALESCE($15, TRUE))
                RETURNING *
                """,
                guest_id,
                data.get("studio_id"),
                data["name"].strip(),
                data.get("bio"),
                data.get("photo_url"),
                (data.get("email") or "").strip().lower() or None,
                data.get("phone"),
                data.get("address_line1"),
                data.get("city"),
                data.get("state"),
                data.get("postal_code"),
                _enc_or_none(data.get("tax_id")),
                int(data.get("revenue_share_percent_to_guest", 60)),
                data.get("notes"),
                data.get("is_active"),
            )
            logger.info("Guest instructor created", guest_id=guest_id, name=data["name"])
            return _row_with_decrypted_tax_id(row)

    async def list_guests(
        self, studio_id: Optional[str] = None, active_only: bool = True
    ) -> list[dict]:
        conditions = []
        params: list = []
        idx = 1
        if active_only:
            conditions.append(f"is_active = ${idx}")
            params.append(True)
            idx += 1
        if studio_id:
            conditions.append(f"(studio_id = ${idx} OR studio_id IS NULL)")
            params.append(studio_id)
            idx += 1
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"SELECT * FROM guest_instructors {where} ORDER BY LOWER(name)",
                *params,
            )
        return [_row_with_decrypted_tax_id(r) for r in rows]

    async def get_guest(self, guest_id: str) -> Optional[dict]:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM guest_instructors WHERE id = $1", guest_id,
            )
        return _row_with_decrypted_tax_id(row) if row else None

    async def update_guest(self, guest_id: str, data: dict) -> Optional[dict]:
        updates = {k: v for k, v in data.items() if k in _GUEST_UPDATE_COLS and v is not None}
        # Special-case tax_id → encrypted column
        if "tax_id" in data:
            updates["tax_id_encrypted"] = _enc_or_none(data["tax_id"])

        if not updates:
            return await self.get_guest(guest_id)

        sets, params, idx = [], [], 1
        for k, v in updates.items():
            sets.append(f"{k} = ${idx}")
            params.append(v)
            idx += 1
        sets.append("updated_at = NOW()")
        params.append(guest_id)

        async with get_tenant_db() as db:
            row = await db.fetchrow(
                f"UPDATE guest_instructors SET {', '.join(sets)} "
                f"WHERE id = ${idx} RETURNING *",
                *params,
            )
        return _row_with_decrypted_tax_id(row) if row else None

    async def archive_guest(self, guest_id: str) -> bool:
        """Soft-delete: flip is_active=false. Tax history stays attached
        for 1099 reporting in past years."""
        async with get_tenant_db() as db:
            result = await db.execute(
                "UPDATE guest_instructors SET is_active = FALSE, updated_at = NOW() "
                "WHERE id = $1",
                guest_id,
            )
        return "UPDATE 1" in result
