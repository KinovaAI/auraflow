"""AuraFlow — Kiosk Device Service

Server-side device-bound kiosk lockdown. The studio iPad is registered
once via the dashboard; the server issues a long-lived device_token
(stored httponly on the iPad) AND a server-side row keyed by
(org_id, ip_hash, user_agent_hash).

The token is the primary identifier. The fingerprint exists so that
clearing Safari cookies does NOT escape the lock — when a non-tokened
request arrives, we re-bind the device from its fingerprint.

We never store raw IPs or User-Agents. Only sha256 hashes. A leak of
the kiosk_devices table cannot deanonymize a studio's network or
device list beyond what the org_id already reveals.
"""
import hashlib
import secrets
import uuid
from typing import Optional

from app.db.session import get_global_db


def _hash(value: Optional[str]) -> Optional[str]:
    """sha256 of an IP or User-Agent string. Returns None if empty."""
    if not value:
        return None
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


class KioskDeviceService:
    """CRUD for kiosk-device registrations + fingerprint-based rebind."""

    async def register(
        self,
        organization_id: str,
        label: str,
        ip_address: Optional[str],
        user_agent: Optional[str],
        registered_by_user_id: Optional[str],
    ) -> dict:
        """Register a new kiosk device. Returns the row including device_token.

        The caller is responsible for setting the auraflow_kiosk_device
        cookie on the response to the iPad's browser.
        """
        device_token = secrets.token_urlsafe(48)
        device_id = str(uuid.uuid4())
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO af_global.kiosk_devices
                    (id, organization_id, device_token,
                     ip_hash, user_agent_hash,
                     label, registered_by, last_seen_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                RETURNING id, organization_id, device_token, label,
                          is_active, registered_at, last_seen_at
                """,
                device_id,
                organization_id,
                device_token,
                _hash(ip_address),
                _hash(user_agent),
                label,
                registered_by_user_id,
            )
        return dict(row)

    async def find_by_token(self, device_token: str) -> Optional[dict]:
        """Look up an active device by its token (the cookie value)."""
        if not device_token:
            return None
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT id, organization_id, device_token, label,
                       is_active, registered_at, last_seen_at
                FROM af_global.kiosk_devices
                WHERE device_token = $1 AND is_active = TRUE
                """,
                device_token,
            )
        return dict(row) if row else None

    async def find_by_fingerprint(
        self,
        ip_address: Optional[str],
        user_agent: Optional[str],
    ) -> Optional[dict]:
        """Cookie-less rebind: if (ip, user-agent) matches a registered
        device, return its row so the middleware can re-set the cookie."""
        ip_h = _hash(ip_address)
        ua_h = _hash(user_agent)
        if not ip_h or not ua_h:
            return None
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT id, organization_id, device_token, label,
                       is_active, registered_at, last_seen_at
                FROM af_global.kiosk_devices
                WHERE ip_hash = $1
                  AND user_agent_hash = $2
                  AND is_active = TRUE
                ORDER BY registered_at DESC
                LIMIT 1
                """,
                ip_h, ua_h,
            )
        return dict(row) if row else None

    async def touch_last_seen(self, device_token: str) -> None:
        """Update last_seen_at when the kiosk makes a request. Best-effort;
        a failure here must not block the request."""
        if not device_token:
            return
        try:
            async with get_global_db() as db:
                await db.execute(
                    "UPDATE af_global.kiosk_devices "
                    "SET last_seen_at = NOW() WHERE device_token = $1",
                    device_token,
                )
        except Exception:
            pass

    async def list_for_org(self, organization_id: str) -> list[dict]:
        """List all kiosk devices for an org (active and revoked).
        device_token is NEVER returned — only the metadata."""
        async with get_global_db() as db:
            rows = await db.fetch(
                """
                SELECT id, label, is_active, registered_at, registered_by,
                       last_seen_at, revoked_at, revoked_by
                FROM af_global.kiosk_devices
                WHERE organization_id = $1
                ORDER BY registered_at DESC
                """,
                organization_id,
            )
        return [dict(r) for r in rows]

    async def revoke(
        self,
        device_id: str,
        organization_id: str,
        revoked_by_user_id: Optional[str],
    ) -> bool:
        """Revoke a kiosk device. Returns True if anything changed."""
        async with get_global_db() as db:
            result = await db.execute(
                """
                UPDATE af_global.kiosk_devices
                SET is_active = FALSE,
                    revoked_at = NOW(),
                    revoked_by = $3
                WHERE id = $1
                  AND organization_id = $2
                  AND is_active = TRUE
                """,
                device_id, organization_id, revoked_by_user_id,
            )
        return result != "UPDATE 0"


kiosk_device_service = KioskDeviceService()
