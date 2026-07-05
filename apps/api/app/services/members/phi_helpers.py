"""
AuraFlow — PHI Read Helpers (HIPAA 2C Phase C migration support)

When the dual-mode bake completes and plaintext PHI columns get dropped,
every place that reads PHI directly from the `members` table needs to
pull the encrypted shadow column instead and decrypt on the way out.

These helpers centralize that conversion so each call site stays a
1-2 line change rather than spreading Fernet plumbing throughout the
worker / service layer.

Usage:

    rows = await db.fetch(
        '''SELECT m.id, m.first_name, m.last_name,
                  m.email, m.phone_enc, ...
           FROM members m WHERE ...'''
    )
    for row in rows:
        phone = decrypt_phone(row)        # str | None
        # ... use phone ...

The functions accept asyncpg.Record or dict — anything that supports
__getitem__ + .get(). They never raise; an unreadable cipher returns
None (with a warning logged) so a single corrupt row can't kill a
batch task.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Optional

from app.core.logging import logger
from app.services.members.member_service import _decrypt


def _safe_decrypt(value, label: str) -> Optional[str]:
    """Decrypt bytes → str, or return None on any failure."""
    if value is None:
        return None
    try:
        decoded = _decrypt(bytes(value))
        return decoded if decoded else None
    except Exception as exc:
        logger.warning(
            "PHI decrypt failed",
            field=label,
            error=str(exc),
        )
        return None


def decrypt_phone(row: Mapping) -> Optional[str]:
    """Return the decrypted phone for a row, preferring `phone_enc`,
    falling back to plaintext `phone` for migration-era rows whose
    `phone_enc` is NULL."""
    enc = row.get("phone_enc") if isinstance(row, dict) else (
        row["phone_enc"] if "phone_enc" in row.keys() else None
    )
    decrypted = _safe_decrypt(enc, "phone")
    if decrypted:
        return decrypted
    # Fall back to plaintext column if it exists in the row
    try:
        plain = row["phone"] if "phone" in row.keys() else None
    except (KeyError, TypeError):
        plain = None
    if not plain:
        plain = row.get("phone") if isinstance(row, dict) else None
    return plain or None


PHI_FIELDS = (
    "phone",
    "date_of_birth",
    "address_line1",
    "city",
    "state",
    "postal_code",
    "emergency_contact_name",
    "emergency_contact_phone",
    "notes",
)


def decrypt_phi_fields(
    row: Mapping,
    fields: Iterable[str] = PHI_FIELDS,
) -> dict:
    """Return a plain-dict copy of `row` with every requested PHI
    field decrypted. Strips the `*_enc` keys from output. Plaintext
    fallback is applied per-field."""
    out = dict(row)
    for f in fields:
        enc_key = f + "_enc"
        enc_val = out.pop(enc_key, None)
        decrypted = _safe_decrypt(enc_val, f)
        if decrypted is not None:
            out[f] = decrypted
        # else: leave whatever plaintext is already on the row
    return out
