"""AuraFlow — Employer Profile Service

Per-tenant employer info used by the onboarding forms (DLSE-NTE wage-theft
notice, DE-34 new-hire report, DWC-7). One row per tenant; get/upsert.
Every studio enters their own — nothing is hardcoded.
"""
import uuid

from app.db.session import get_tenant_db

_FIELDS = [
    "legal_name", "dba_name", "ein", "edd_account_number",
    "address_line1", "address_line2", "city", "state", "postal_code", "phone",
    "wc_carrier_name", "wc_policy_number", "wc_carrier_phone", "wc_policy_effective",
    "pay_schedule", "regular_payday", "overtime_basis", "sick_leave_policy",
]
_DATE_FIELDS = {"wc_policy_effective"}


def _to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["id"] = str(d["id"])
    for k in ("created_at", "updated_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    if d.get("wc_policy_effective") is not None:
        d["wc_policy_effective"] = d["wc_policy_effective"].isoformat()
    return d


async def get_profile() -> dict | None:
    """Return the tenant's employer profile, or None if not set up yet."""
    async with get_tenant_db() as db:
        row = await db.fetchrow("SELECT * FROM employer_profile ORDER BY created_at LIMIT 1")
    return _to_dict(row)


async def upsert_profile(data: dict) -> dict:
    """Create or update the tenant's single employer-profile row."""
    from datetime import date

    def coerce(k, v):
        if k in _DATE_FIELDS and isinstance(v, str) and v:
            return date.fromisoformat(v)
        return v

    clean = {k: coerce(k, data[k]) for k in _FIELDS if k in data}

    async with get_tenant_db() as db:
        existing = await db.fetchrow("SELECT id FROM employer_profile ORDER BY created_at LIMIT 1")
        if existing:
            if clean:
                sets = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(clean))
                params = list(clean.values())
                params.append(str(existing["id"]))
                await db.execute(
                    f"UPDATE employer_profile SET {sets}, updated_at = NOW() WHERE id = ${len(params)}",
                    *params,
                )
            row_id = str(existing["id"])
        else:
            row_id = str(uuid.uuid4())
            cols = ["id"] + list(clean.keys())
            vals = [row_id] + list(clean.values())
            placeholders = ", ".join(f"${i + 1}" for i in range(len(vals)))
            await db.execute(
                f"INSERT INTO employer_profile ({', '.join(cols)}) VALUES ({placeholders})",
                *vals,
            )
        row = await db.fetchrow("SELECT * FROM employer_profile WHERE id = $1", row_id)
    return _to_dict(row)
