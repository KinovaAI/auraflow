"""HIPAA-2C-auraflow Phase A backfill: encrypt every plaintext PHI value
into the new *_enc shadow columns using the existing HEALTH_DATA_ENCRYPTION_KEY
Fernet cipher (already wired in production for member_health_data)."""
import asyncio
import os
import sys

import asyncpg
from cryptography.fernet import Fernet


KEY = os.environ.get("HEALTH_DATA_ENCRYPTION_KEY")
if not KEY:
    sys.exit("ABORT: HEALTH_DATA_ENCRYPTION_KEY env not set inside the container")
FERNET = Fernet(KEY.encode("utf-8") if isinstance(KEY, str) else KEY)


def enc(value) -> bytes | None:
    if value is None or value == "":
        return None
    if hasattr(value, "isoformat"):
        value = value.isoformat()
    return FERNET.encrypt(str(value).encode("utf-8"))


PG_DSN = os.environ.get(
    "DATABASE_URL",
    f"postgresql://auraflow:{os.environ['POSTGRES_PASSWORD']}@auraflow_postgres:5432/auraflow",
)


async def main():
    conn = await asyncpg.connect(PG_DSN)
    try:
        # ── members ────────────────────────────────────────────────────
        rows = await conn.fetch(
            "SELECT id, date_of_birth, phone, address_line1, city, state, postal_code, "
            "       emergency_contact_name, emergency_contact_phone, notes "
            "  FROM af_tenant_demo.members "
            " WHERE date_of_birth_enc IS NULL OR phone_enc IS NULL "
            "    OR address_line1_enc IS NULL OR city_enc IS NULL OR state_enc IS NULL "
            "    OR postal_code_enc IS NULL OR emergency_contact_name_enc IS NULL "
            "    OR emergency_contact_phone_enc IS NULL OR notes_enc IS NULL"
        )
        n = 0
        for r in rows:
            await conn.execute(
                "UPDATE af_tenant_demo.members SET "
                " date_of_birth_enc = COALESCE(date_of_birth_enc, $2), "
                " phone_enc = COALESCE(phone_enc, $3), "
                " address_line1_enc = COALESCE(address_line1_enc, $4), "
                " city_enc = COALESCE(city_enc, $5), "
                " state_enc = COALESCE(state_enc, $6), "
                " postal_code_enc = COALESCE(postal_code_enc, $7), "
                " emergency_contact_name_enc = COALESCE(emergency_contact_name_enc, $8), "
                " emergency_contact_phone_enc = COALESCE(emergency_contact_phone_enc, $9), "
                " notes_enc = COALESCE(notes_enc, $10) "
                "WHERE id = $1",
                r["id"],
                enc(r["date_of_birth"]), enc(r["phone"]),
                enc(r["address_line1"]), enc(r["city"]), enc(r["state"]),
                enc(r["postal_code"]),
                enc(r["emergency_contact_name"]), enc(r["emergency_contact_phone"]),
                enc(r["notes"]),
            )
            n += 1
        print(f"members encrypted: {n}")

        # ── member_notes ───────────────────────────────────────────────
        rows = await conn.fetch(
            "SELECT id, note FROM af_tenant_demo.member_notes "
            " WHERE note_enc IS NULL AND note IS NOT NULL AND note <> ''"
        )
        n = 0
        for r in rows:
            await conn.execute(
                "UPDATE af_tenant_demo.member_notes SET note_enc = $2 WHERE id = $1",
                r["id"], enc(r["note"]),
            )
            n += 1
        print(f"member_notes encrypted: {n}")

        # ── af_global.users (phone) ────────────────────────────────────
        rows = await conn.fetch(
            "SELECT id, phone FROM af_global.users "
            " WHERE phone_enc IS NULL AND phone IS NOT NULL AND phone <> ''"
        )
        n = 0
        for r in rows:
            await conn.execute(
                "UPDATE af_global.users SET phone_enc = $2 WHERE id = $1",
                r["id"], enc(r["phone"]),
            )
            n += 1
        print(f"af_global.users phone encrypted: {n}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
