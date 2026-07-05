"""AuraFlow — Mailchimp Service (BYOA Marketing API v3)

Studios connect their own Mailchimp account by providing an API key
and list (audience) ID. Members are auto-synced to the Mailchimp
audience on creation/update.

Auth: Basic auth with base64("anystring:{api_key}"), data center
extracted from the API key suffix (e.g., "abc123-us21" → us21).

Credentials stored encrypted via pgcrypto in af_global.organizations.
All methods fail silently (log warnings) — never break the main flow.
"""
import base64
import hashlib
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.utils.encryption import encrypt_credential, decrypt_credential


def _build_auth_header(api_key: str) -> dict:
    """Build Mailchimp Basic auth header from an API key."""
    encoded = base64.b64encode(f"auraflow:{api_key}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def _get_data_center(api_key: str) -> str:
    """Extract data center from Mailchimp API key (last part after '-')."""
    return api_key.rsplit("-", 1)[-1]


def _subscriber_hash(email: str) -> str:
    """MD5 hash of lowercase email, used as Mailchimp subscriber ID."""
    return hashlib.md5(email.lower().strip().encode()).hexdigest()


class MailchimpService:

    # ── Credential Management ──────────────────────────────────────────

    async def connect(self, org_id: str, api_key: str, list_id: str) -> dict:
        """Store Mailchimp credentials and verify the connection."""
        # Test the connection first
        dc = _get_data_center(api_key)
        headers = _build_auth_header(api_key)
        base_url = f"https://{dc}.api.mailchimp.com/3.0"

        async with httpx.AsyncClient(timeout=15) as client:
            # Verify API key
            resp = await client.get(f"{base_url}/ping", headers=headers)
            if resp.status_code != 200:
                raise ValueError(f"Mailchimp API key validation failed: {resp.status_code}")

            # Verify list exists
            resp = await client.get(f"{base_url}/lists/{list_id}", headers=headers)
            if resp.status_code != 200:
                raise ValueError(f"Mailchimp list '{list_id}' not found: {resp.status_code}")
            list_info = resp.json()

        # Store encrypted credentials
        async with get_global_db() as db:
            encrypted_key = await encrypt_credential(db, api_key)
            await db.execute(
                """
                UPDATE af_global.organizations
                SET mailchimp_api_key_encrypted = $1,
                    mailchimp_list_id = $2,
                    mailchimp_connected_at = NOW(),
                    updated_at = NOW()
                WHERE id = $3
                """,
                encrypted_key, list_id, org_id,
            )

        logger.info(
            "Mailchimp connected",
            org_id=org_id,
            list_id=list_id,
            list_name=list_info.get("name"),
        )
        return {
            "connected": True,
            "list_name": list_info.get("name"),
            "member_count": list_info.get("stats", {}).get("member_count", 0),
        }

    async def disconnect(self, org_id: str) -> None:
        """Clear Mailchimp credentials from the organization."""
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET mailchimp_api_key_encrypted = NULL,
                    mailchimp_list_id = NULL,
                    mailchimp_connected_at = NULL,
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id,
            )
        logger.info("Mailchimp disconnected", org_id=org_id)

    async def get_status(self, org_id: str) -> dict:
        """Return Mailchimp connection status for the organization."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT mailchimp_api_key_encrypted, mailchimp_list_id,
                       mailchimp_connected_at
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )

        if not row or not row["mailchimp_api_key_encrypted"] or not row["mailchimp_list_id"]:
            return {"connected": False}

        # Fetch live list info
        try:
            async with get_global_db() as db:
                api_key = await decrypt_credential(db, row["mailchimp_api_key_encrypted"])
            list_id = row["mailchimp_list_id"]
            dc = _get_data_center(api_key)
            headers = _build_auth_header(api_key)

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://{dc}.api.mailchimp.com/3.0/lists/{list_id}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    info = resp.json()
                    return {
                        "connected": True,
                        "list_id": list_id,
                        "list_name": info.get("name"),
                        "member_count": info.get("stats", {}).get("member_count", 0),
                        "connected_at": row["mailchimp_connected_at"].isoformat()
                        if row["mailchimp_connected_at"]
                        else None,
                    }
        except Exception as e:
            logger.warning("Mailchimp status check failed", org_id=org_id, error=str(e))

        return {
            "connected": True,
            "list_id": row["mailchimp_list_id"],
            "list_name": None,
            "member_count": None,
            "connected_at": row["mailchimp_connected_at"].isoformat()
            if row["mailchimp_connected_at"]
            else None,
            "error": "Could not reach Mailchimp API",
        }

    # ── Member Sync ────────────────────────────────────────────────────

    async def _get_credentials(self, org_id: str) -> Optional[tuple[str, str]]:
        """Return (api_key, list_id) or None if not connected."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT mailchimp_api_key_encrypted, mailchimp_list_id
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
            if not row or not row["mailchimp_api_key_encrypted"] or not row["mailchimp_list_id"]:
                return None
            api_key = await decrypt_credential(db, row["mailchimp_api_key_encrypted"])
        return api_key, row["mailchimp_list_id"]

    async def _get_org_id_for_schema(self, schema_name: str) -> Optional[str]:
        """Resolve tenant schema name to org ID."""
        slug = schema_name.replace("af_tenant_", "")
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT id FROM af_global.organizations WHERE slug = $1", slug
            )
            return str(row["id"]) if row else None

    async def sync_member(self, schema_name: str, member_id: str) -> Optional[str]:
        """Add or update a member in the Mailchimp audience.

        Returns the Mailchimp subscriber hash on success, None on skip/failure.
        """
        try:
            org_id = await self._get_org_id_for_schema(schema_name)
            if not org_id:
                return None

            creds = await self._get_credentials(org_id)
            if not creds:
                return None
            api_key, list_id = creds

            # Fetch member from tenant DB
            async with get_tenant_db(schema_name) as db:
                member = await db.fetchrow(
                    "SELECT first_name, last_name, email FROM members WHERE id = $1",
                    member_id,
                )
            if not member or not member["email"]:
                return None

            dc = _get_data_center(api_key)
            headers = _build_auth_header(api_key)
            sub_hash = _subscriber_hash(member["email"])

            payload = {
                "email_address": member["email"],
                "status_if_new": "subscribed",
                "merge_fields": {
                    "FNAME": member["first_name"] or "",
                    "LNAME": member["last_name"] or "",
                },
            }

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.put(
                    f"https://{dc}.api.mailchimp.com/3.0/lists/{list_id}/members/{sub_hash}",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code in (200, 201):
                    logger.info(
                        "Mailchimp member synced",
                        member_id=member_id,
                        email=member["email"],
                    )
                    return sub_hash
                else:
                    logger.warning(
                        "Mailchimp member sync failed",
                        member_id=member_id,
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
                    return None

        except Exception as e:
            logger.warning("Mailchimp sync_member error", member_id=member_id, error=str(e))
            return None

    async def remove_member(self, schema_name: str, email: str) -> bool:
        """Archive a member from the Mailchimp audience."""
        try:
            org_id = await self._get_org_id_for_schema(schema_name)
            if not org_id:
                return False

            creds = await self._get_credentials(org_id)
            if not creds:
                return False
            api_key, list_id = creds

            dc = _get_data_center(api_key)
            headers = _build_auth_header(api_key)
            sub_hash = _subscriber_hash(email)

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.delete(
                    f"https://{dc}.api.mailchimp.com/3.0/lists/{list_id}/members/{sub_hash}",
                    headers=headers,
                )
                if resp.status_code in (200, 204):
                    logger.info("Mailchimp member archived", email=email)
                    return True
                else:
                    logger.warning(
                        "Mailchimp member archive failed",
                        email=email,
                        status=resp.status_code,
                    )
                    return False

        except Exception as e:
            logger.warning("Mailchimp remove_member error", email=email, error=str(e))
            return False

    async def sync_all_members(self, schema_name: str) -> dict:
        """Bulk sync all active members to Mailchimp using batch operations."""
        org_id = await self._get_org_id_for_schema(schema_name)
        if not org_id:
            raise ValueError("Organization not found for schema")

        creds = await self._get_credentials(org_id)
        if not creds:
            raise ValueError("Mailchimp not connected")
        api_key, list_id = creds

        # Fetch all active members
        async with get_tenant_db(schema_name) as db:
            members = await db.fetch(
                "SELECT id, first_name, last_name, email FROM members WHERE is_active = TRUE AND email IS NOT NULL"
            )

        if not members:
            return {"synced": 0, "total": 0}

        dc = _get_data_center(api_key)
        headers = _build_auth_header(api_key)

        # Build batch operations
        operations = []
        for m in members:
            sub_hash = _subscriber_hash(m["email"])
            operations.append({
                "method": "PUT",
                "path": f"/lists/{list_id}/members/{sub_hash}",
                "body": (
                    '{"email_address":"' + m["email"] + '",'
                    '"status_if_new":"subscribed",'
                    '"merge_fields":{"FNAME":"' + (m["first_name"] or "") + '",'
                    '"LNAME":"' + (m["last_name"] or "") + '"}}'
                ),
            })

        # Submit batch (Mailchimp accepts up to 500 operations per batch)
        synced = 0
        batch_size = 500
        for i in range(0, len(operations), batch_size):
            batch = operations[i : i + batch_size]
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"https://{dc}.api.mailchimp.com/3.0/batches",
                    headers=headers,
                    json={"operations": batch},
                )
                if resp.status_code in (200, 201):
                    synced += len(batch)
                    logger.info(
                        "Mailchimp batch submitted",
                        batch_index=i // batch_size,
                        count=len(batch),
                    )
                else:
                    logger.warning(
                        "Mailchimp batch failed",
                        status=resp.status_code,
                        body=resp.text[:200],
                    )

        logger.info("Mailchimp bulk sync complete", total=len(members), synced=synced)
        return {"synced": synced, "total": len(members)}


mailchimp_service = MailchimpService()
