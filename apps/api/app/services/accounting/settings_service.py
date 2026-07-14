"""Settings + K-1 members for the Accounting module.

Faithful port of a standalone single-tenant LLC accounting app's settings and
members routes — now per-tenant and async. The Mercury API key is encrypted
at rest (pgcrypto via encrypt_credential) and always masked on read; a masked
value submitted back is ignored so the UI round-trip never clobbers the key
(server.js:1072-1074). K-1 members carry ownership %, capital, and an encrypted
TIN.

`db` is a tenant-scoped asyncpg connection (search_path = tenant schema).
"""
from app.utils.encryption import encrypt_credential, decrypt_credential
from app.services.accounting.categories import seed_categories

# Non-secret LLC-identity fields editable from the settings UI.
_IDENTITY_FIELDS = {"llc_name", "llc_ein", "llc_state", "llc_tax_class"}


def _mask(key: str) -> str:
    if not key:
        return ""
    return f"{key[:4]}****{key[-4:]}" if len(key) > 8 else "****"


async def ensure_row(db) -> None:
    """Guarantee the single settings row (id=1) exists."""
    await db.execute(
        "INSERT INTO acct_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
    )


async def ensure_seeded(db, schema: str) -> None:
    """Idempotently create the settings row + seed the Schedule C taxonomy.
    Safe to call on every request into the module."""
    await ensure_row(db)
    await seed_categories(db, schema)


async def get_settings(db) -> dict:
    """LLC identity + Mercury connection status. The key is masked; never returns
    the plaintext key."""
    await ensure_row(db)
    row = await db.fetchrow(
        """
        SELECT llc_name, llc_ein, llc_state, llc_tax_class,
               mercury_api_key_enc, mercury_accounts, last_sync_at
        FROM acct_settings WHERE id = 1
        """
    )
    key_plain = None
    if row["mercury_api_key_enc"]:
        try:
            key_plain = await decrypt_credential(db, row["mercury_api_key_enc"])
        except Exception:  # noqa: BLE001
            key_plain = None
    return {
        "llc_name": row["llc_name"],
        "llc_ein": row["llc_ein"],
        "llc_state": row["llc_state"],
        "llc_tax_class": row["llc_tax_class"],
        "mercury_api_key": _mask(key_plain) if key_plain else None,
        "mercury_connected": bool(key_plain),
        "mercury_accounts": row["mercury_accounts"],
        "last_sync_at": row["last_sync_at"],
    }


async def update_settings(db, patch: dict) -> dict:
    """Update LLC identity and/or the Mercury key. A masked Mercury value
    (contains '****') is ignored so the UI round-trip can't clobber the stored
    key (server.js:1072-1074). Returns the fresh masked settings."""
    await ensure_row(db)

    for field in _IDENTITY_FIELDS:
        if field in patch:
            await db.execute(
                f"UPDATE acct_settings SET {field} = $1, updated_at = NOW() WHERE id = 1",
                patch[field],
            )

    if "mercury_api_key" in patch:
        value = patch["mercury_api_key"]
        if value and "****" not in value:
            enc = await encrypt_credential(db, value)
            await db.execute(
                "UPDATE acct_settings SET mercury_api_key_enc = $1, updated_at = NOW() "
                "WHERE id = 1",
                enc,
            )
        elif value == "":
            # explicit clear
            await db.execute(
                "UPDATE acct_settings SET mercury_api_key_enc = NULL, updated_at = NOW() "
                "WHERE id = 1"
            )

    return await get_settings(db)


# ── K-1 members / LLC partners ───────────────────────────────────────────────

async def list_members(db) -> list[dict]:
    rows = await db.fetch(
        """
        SELECT id, name, email, ownership_pct, capital_cents, updated_at
        FROM acct_members ORDER BY name ASC
        """
    )
    return [dict(r) for r in rows]


async def create_member(db, data: dict) -> dict:
    tin_enc = None
    if data.get("tin"):
        tin_enc = await encrypt_credential(db, data["tin"])
    row = await db.fetchrow(
        """
        INSERT INTO acct_members (name, email, ownership_pct, capital_cents, tin_encrypted)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, name, email, ownership_pct, capital_cents, updated_at
        """,
        data["name"], data.get("email"),
        data.get("ownership_pct", 0), data.get("capital_cents", 0), tin_enc,
    )
    return dict(row)


async def update_member(db, member_id: str, data: dict) -> dict | None:
    sets, params = [], []
    for i, field in enumerate(("name", "email", "ownership_pct", "capital_cents"), start=1):
        if field in data:
            sets.append(f"{field} = ${len(params) + 1}")
            params.append(data[field])
    if "tin" in data:
        sets.append(f"tin_encrypted = ${len(params) + 1}")
        params.append(await encrypt_credential(db, data["tin"]) if data["tin"] else None)
    if not sets:
        row = await db.fetchrow(
            "SELECT id, name, email, ownership_pct, capital_cents, updated_at "
            "FROM acct_members WHERE id = $1", member_id,
        )
        return dict(row) if row else None
    sets.append("updated_at = NOW()")
    params.append(member_id)
    row = await db.fetchrow(
        f"UPDATE acct_members SET {', '.join(sets)} WHERE id = ${len(params)} "
        "RETURNING id, name, email, ownership_pct, capital_cents, updated_at",
        *params,
    )
    return dict(row) if row else None


async def delete_member(db, member_id: str) -> bool:
    status = await db.execute("DELETE FROM acct_members WHERE id = $1", member_id)
    return status.endswith(" 1")
