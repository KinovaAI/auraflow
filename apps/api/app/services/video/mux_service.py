"""AuraFlow — Mux Service (BYOA)

Studios connect their own Mux access token + secret.
We use the Mux API for asset management, direct uploads,
and webhook handling. All via httpx with basic auth.
"""
from typing import Optional
from base64 import b64encode

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.utils.encryption import encrypt_credential, decrypt_credential

MUX_API_BASE = "https://api.mux.com"


class MuxService:

    # ── Credential Management ──────────────────────────────────────────────

    async def save_credentials(self, org_id: str, token_id: str, token_secret: str) -> None:
        """Encrypt and store Mux credentials on the org."""
        async with get_global_db() as db:
            encrypted_id = await encrypt_credential(db, token_id)
            encrypted_secret = await encrypt_credential(db, token_secret)

            # Fetch environment ID by listing one asset
            env_id = await self._fetch_environment_id(token_id, token_secret)

            await db.execute(
                """
                UPDATE af_global.organizations
                SET mux_token_id_encrypted = $1,
                    mux_token_secret_encrypted = $2,
                    mux_environment_id = $3,
                    mux_connected_at = NOW(),
                    updated_at = NOW()
                WHERE id = $4
                """,
                encrypted_id, encrypted_secret, env_id, org_id,
            )
        logger.info("Mux connected", org_id=org_id)

    async def get_credentials(self, org_id: str) -> Optional[dict]:
        """Decrypt and return Mux credentials, or None if not connected."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT mux_token_id_encrypted, mux_token_secret_encrypted,
                       mux_environment_id, mux_connected_at
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
            if not row or not row["mux_token_id_encrypted"]:
                return None
            token_id = await decrypt_credential(db, row["mux_token_id_encrypted"])
            token_secret = await decrypt_credential(db, row["mux_token_secret_encrypted"])
            return {
                "token_id": token_id,
                "token_secret": token_secret,
                "environment_id": row["mux_environment_id"],
                "connected_at": row["mux_connected_at"],
            }

    async def remove_credentials(self, org_id: str) -> None:
        """Clear Mux credentials from the org."""
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET mux_token_id_encrypted = NULL,
                    mux_token_secret_encrypted = NULL,
                    mux_environment_id = NULL,
                    mux_connected_at = NULL,
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id,
            )
        logger.info("Mux disconnected", org_id=org_id)

    # ── Mux API Calls ─────────────────────────────────────────────────────

    @staticmethod
    def _auth_header(token_id: str, token_secret: str) -> dict:
        """Build basic auth header for Mux API."""
        cred = b64encode(f"{token_id}:{token_secret}".encode()).decode()
        return {"Authorization": f"Basic {cred}"}

    async def test_connection(self, token_id: str, token_secret: str) -> dict:
        """Test Mux credentials by listing assets."""
        headers = self._auth_header(token_id, token_secret)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MUX_API_BASE}/video/v1/assets",
                headers=headers,
                params={"limit": 1},
                timeout=10,
            )
            if resp.status_code == 401:
                return {"success": False, "error": "Invalid Mux credentials"}
            if resp.status_code != 200:
                return {"success": False, "error": f"Mux API error: {resp.status_code}"}

            data = resp.json().get("data", [])
            return {
                "success": True,
                "asset_count": len(data),
            }

    async def _fetch_environment_id(self, token_id: str, token_secret: str) -> Optional[str]:
        """Fetch the Mux environment ID from the API."""
        headers = self._auth_header(token_id, token_secret)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MUX_API_BASE}/video/v1/assets",
                headers=headers,
                params={"limit": 1},
                timeout=10,
            )
            if resp.status_code == 200:
                # Environment ID comes from the asset response or can be inferred
                # For now, store the token_id as identifier for webhook routing
                return token_id
        return None

    async def list_assets(
        self, token_id: str, token_secret: str, page: int = 1, limit: int = 25
    ) -> list[dict]:
        """List Mux video assets."""
        headers = self._auth_header(token_id, token_secret)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MUX_API_BASE}/video/v1/assets",
                headers=headers,
                params={"limit": limit, "page": page},
                timeout=15,
            )
            if resp.status_code != 200:
                return []

            results = []
            for asset in resp.json().get("data", []):
                playback_ids = asset.get("playback_ids", [])
                playback_id = playback_ids[0]["id"] if playback_ids else None

                results.append({
                    "mux_asset_id": asset["id"],
                    "mux_playback_id": playback_id,
                    "mux_asset_status": asset.get("status", "unknown"),
                    "duration_seconds": int(asset.get("duration", 0)),
                    "title": asset.get("passthrough", "") or asset["id"],
                    "created_at": asset.get("created_at"),
                })
            return results

    async def create_upload_url(
        self, token_id: str, token_secret: str, cors_origin: Optional[str] = None
    ) -> dict:
        """Create a Mux direct upload URL. Studio uploads directly to Mux."""
        headers = self._auth_header(token_id, token_secret)
        body = {
            "new_asset_settings": {
                "playback_policy": ["public"],
            },
            "cors_origin": cors_origin or getattr(settings, "APP_URL", None) or (settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "*"),
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{MUX_API_BASE}/video/v1/uploads",
                headers=headers,
                json=body,
                timeout=15,
            )
            if resp.status_code != 201:
                error = resp.text
                return {"success": False, "error": error}

            data = resp.json().get("data", {})
            return {
                "success": True,
                "upload_url": data.get("url"),
                "upload_id": data.get("id"),
                "asset_id": data.get("asset_id"),
            }

    # ── Sync ───────────────────────────────────────────────────────────────

    async def sync_assets(self, org_id: str) -> dict:
        """Fetch all Mux assets and upsert into tenant videos table."""
        creds = await self.get_credentials(org_id)
        if not creds:
            return {"synced": 0, "new": 0, "updated": 0, "source": "mux"}

        assets = await self.list_assets(creds["token_id"], creds["token_secret"], limit=100)
        new_count = 0
        updated_count = 0

        async with get_tenant_db() as db:
            for a in assets:
                existing = await db.fetchrow(
                    "SELECT id FROM videos WHERE mux_asset_id = $1",
                    a["mux_asset_id"],
                )
                if existing:
                    await db.execute(
                        """
                        UPDATE videos
                        SET mux_playback_id = $1, mux_asset_status = $2,
                            duration_seconds = $3, updated_at = NOW()
                        WHERE mux_asset_id = $4
                        """,
                        a["mux_playback_id"], a["mux_asset_status"],
                        a["duration_seconds"], a["mux_asset_id"],
                    )
                    updated_count += 1
                else:
                    await db.execute(
                        """
                        INSERT INTO videos
                            (source, external_id, mux_asset_id, mux_playback_id,
                             mux_asset_status, title, duration_seconds, is_published)
                        VALUES ('mux', $1, $1, $2, $3, $4, $5, TRUE)
                        """,
                        a["mux_asset_id"], a["mux_playback_id"],
                        a["mux_asset_status"], a["title"], a["duration_seconds"],
                    )
                    new_count += 1

        total = new_count + updated_count
        logger.info("Mux sync complete", org_id=org_id, new=new_count, updated=updated_count)
        return {"synced": total, "new": new_count, "updated": updated_count, "source": "mux"}

    # ── Webhook Handling ───────────────────────────────────────────────────

    async def handle_webhook(self, payload: dict) -> None:
        """Process a Mux webhook event. Updates video status in tenant DB."""
        event_type = payload.get("type", "")
        data = payload.get("data", {})
        asset_id = data.get("id") or data.get("asset_id")

        if not asset_id:
            return

        async with get_tenant_db() as db:
            if event_type == "video.asset.ready":
                playback_ids = data.get("playback_ids", [])
                playback_id = playback_ids[0]["id"] if playback_ids else None
                duration = int(data.get("duration", 0))

                await db.execute(
                    """
                    UPDATE videos
                    SET mux_asset_status = 'ready', mux_playback_id = $1,
                        duration_seconds = $2, updated_at = NOW()
                    WHERE mux_asset_id = $3
                    """,
                    playback_id, duration, asset_id,
                )
                logger.info("Mux asset ready", asset_id=asset_id)

            elif event_type == "video.asset.errored":
                await db.execute(
                    """
                    UPDATE videos
                    SET mux_asset_status = 'errored', updated_at = NOW()
                    WHERE mux_asset_id = $1
                    """,
                    asset_id,
                )
                logger.warning("Mux asset errored", asset_id=asset_id)

            elif event_type == "video.asset.deleted":
                await db.execute(
                    """
                    UPDATE videos
                    SET mux_asset_status = 'deleted', is_published = FALSE,
                        visibility = 'hidden', updated_at = NOW()
                    WHERE mux_asset_id = $1
                    """,
                    asset_id,
                )
                logger.info("Mux asset deleted", asset_id=asset_id)

    async def find_org_by_environment(self, environment_id: str) -> Optional[str]:
        """Look up org ID from Mux environment ID (for webhook routing)."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT id FROM af_global.organizations
                WHERE mux_environment_id = $1
                """,
                environment_id,
            )
            return str(row["id"]) if row else None
