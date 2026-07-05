"""AuraFlow — External API key management service.

Handles creation, validation, listing, and revocation of API keys
for external integrations. Keys use a prefix-based routing scheme
so validation can resolve the correct tenant without prior context.

Key format: af_live_{32 hex chars}  (48 chars total)
Storage:    SHA-256 hash only — raw key is returned exactly once at creation.
Routing:    af_global.api_key_routing maps key_prefix → org_slug for
            cross-tenant lookup during validation.
"""
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.db.session import get_tenant_db, get_global_db
from app.core.logging import logger


KEY_PREFIX_TAG = "af_live_"
KEY_HEX_LENGTH = 32  # 32 hex chars = 16 bytes of randomness
ROUTING_PREFIX_LENGTH = 16  # first 16 chars of full key (includes "af_live_" + 8 hex)


def _generate_raw_key() -> str:
    """Generate a new raw API key: af_live_ + 32 random hex chars."""
    return f"{KEY_PREFIX_TAG}{secrets.token_hex(KEY_HEX_LENGTH // 2)}"


def _hash_key(raw_key: str) -> str:
    """Produce a deterministic SHA-256 hex digest of the raw key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _extract_prefix(raw_key: str) -> str:
    """Return the routable prefix (first 16 chars) used for lookup."""
    return raw_key[:ROUTING_PREFIX_LENGTH]


async def create_key(
    name: str,
    scopes: list[str],
    rate_limit_rpm: int = 60,
    created_by: Optional[UUID] = None,
    expires_at: Optional[datetime] = None,
) -> dict:
    """Create a new API key for the current tenant.

    Returns a dict containing the raw key (shown once), key_id, and metadata.
    """
    from app.core.tenant_context import require_tenant_context

    ctx = require_tenant_context()
    raw_key = _generate_raw_key()
    key_hash = _hash_key(raw_key)
    key_prefix = _extract_prefix(raw_key)

    # Insert into tenant schema
    async with get_tenant_db() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO api_keys (name, key_hash, key_prefix, scopes,
                                  rate_limit_rpm, created_by, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, created_at
            """,
            name,
            key_hash,
            key_prefix,
            scopes,
            rate_limit_rpm,
            created_by,
            expires_at,
        )

    # Register in global routing table
    async with get_global_db() as conn:
        await conn.execute(
            """
            INSERT INTO af_global.api_key_routing (key_prefix, org_slug)
            VALUES ($1, $2)
            ON CONFLICT (key_prefix) DO NOTHING
            """,
            key_prefix,
            ctx.slug,
        )

    logger.info(
        "api_key_created",
        key_prefix=key_prefix,
        name=name,
        scopes=scopes,
        org_slug=ctx.slug,
    )

    return {
        "raw_key": raw_key,  # shown ONCE — never stored or logged
        "api_key": raw_key,  # alias
        "key_id": str(row["id"]),
        "key_prefix": key_prefix,
        "name": name,
        "scopes": scopes,
        "rate_limit_rpm": rate_limit_rpm,
        "created_at": row["created_at"].isoformat(),
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


async def validate_key(raw_key: str) -> dict:
    """Validate a raw API key and return its context.

    Steps:
    1. Extract prefix, look up org_slug in af_global.api_key_routing.
    2. Set search_path to the tenant schema.
    3. Verify SHA-256 hash, active status, and expiration.
    4. Bump last_used_at.

    Raises ValueError on any validation failure.
    """
    if not raw_key or not raw_key.startswith(KEY_PREFIX_TAG):
        raise ValueError("Invalid API key format")

    key_prefix = _extract_prefix(raw_key)
    key_hash = _hash_key(raw_key)

    # Step 1 — resolve tenant via global routing table
    async with get_global_db() as conn:
        routing = await conn.fetchrow(
            "SELECT org_slug FROM af_global.api_key_routing WHERE key_prefix = $1",
            key_prefix,
        )
    if routing is None:
        raise ValueError("API key not found")

    org_slug = routing["org_slug"]
    schema_name = f"af_tenant_{org_slug}"

    # Step 2 — look up the organization for org_id
    async with get_global_db() as conn:
        org = await conn.fetchrow(
            "SELECT id FROM af_global.organizations WHERE slug = $1",
            org_slug,
        )
    if org is None:
        raise ValueError("Organization not found")

    # Step 3 — validate key in tenant schema
    async with get_tenant_db(schema_override=schema_name) as conn:
        row = await conn.fetchrow(
            """
            SELECT id, scopes, rate_limit_rpm, is_active, expires_at
            FROM api_keys
            WHERE key_prefix = $1 AND key_hash = $2
            """,
            key_prefix,
            key_hash,
        )

    if row is None:
        raise ValueError("API key not found")

    if not row["is_active"]:
        raise ValueError("API key has been revoked")

    if row["expires_at"] is not None and row["expires_at"] < datetime.now(timezone.utc):
        raise ValueError("API key has expired")

    # Step 4 — update last_used_at
    async with get_tenant_db(schema_override=schema_name) as conn:
        await conn.execute(
            "UPDATE api_keys SET last_used_at = NOW() WHERE id = $1",
            row["id"],
        )

    return {
        "api_key_id": str(row["id"]),
        "org_id": str(org["id"]),
        "org_slug": org_slug,
        "schema_name": schema_name,
        "scopes": list(row["scopes"]) if row["scopes"] else [],
        "rate_limit_rpm": row["rate_limit_rpm"],
    }


async def list_keys() -> list[dict]:
    """List all API keys for the current tenant.

    Never returns the key hash.
    """
    async with get_tenant_db() as conn:
        rows = await conn.fetch(
            """
            SELECT id, key_prefix, name, scopes, rate_limit_rpm,
                   is_active, last_used_at, created_at, expires_at, revoked_at
            FROM api_keys
            WHERE is_active = TRUE
            ORDER BY created_at DESC
            """
        )

    return [
        {
            "id": str(r["id"]),
            "key_prefix": r["key_prefix"],
            "name": r["name"],
            "scopes": list(r["scopes"]) if r["scopes"] else [],
            "rate_limit_rpm": r["rate_limit_rpm"],
            "is_active": r["is_active"],
            "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
            "created_at": r["created_at"].isoformat(),
            "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
            "revoked_at": r["revoked_at"].isoformat() if r["revoked_at"] else None,
        }
        for r in rows
    ]


async def revoke_key(key_id: UUID) -> bool:
    """Revoke an API key by setting is_active=FALSE and recording revoked_at.

    Also removes the routing entry from the global table.
    Returns True if a key was actually revoked, False if not found/already revoked.
    """
    async with get_tenant_db() as conn:
        row = await conn.fetchrow(
            """
            UPDATE api_keys
            SET is_active = FALSE, revoked_at = NOW()
            WHERE id = $1 AND is_active = TRUE
            RETURNING key_prefix
            """,
            key_id,
        )

    if row is None:
        return False

    # Remove global routing entry
    async with get_global_db() as conn:
        await conn.execute(
            "DELETE FROM af_global.api_key_routing WHERE key_prefix = $1",
            row["key_prefix"],
        )

    logger.info("api_key_revoked", key_id=str(key_id), key_prefix=row["key_prefix"])
    return True
