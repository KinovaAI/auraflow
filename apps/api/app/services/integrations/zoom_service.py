"""AuraFlow — Zoom Service (BYOA S2S OAuth)

Studios connect their own Zoom Server-to-Server OAuth app.
We use the Zoom API for meeting CRUD, recording downloads,
and webhook handling. Credentials stored encrypted via pgcrypto.
"""
import hashlib
import hmac
import json
import uuid
from base64 import b64encode
from typing import Optional

import httpx

from app.core.logging import logger
from app.core.redis import get_redis
from app.db.session import get_tenant_db, get_global_db
from app.utils.encryption import encrypt_credential, decrypt_credential

ZOOM_API_BASE = "https://api.zoom.us/v2"
ZOOM_OAUTH_URL = "https://zoom.us/oauth/token"
ZOOM_TOKEN_CACHE_PREFIX = "zoom_token:"


class ZoomService:

    # ── Credential Management ──────────────────────────────────────────

    async def connect(
        self,
        org_id: str,
        account_id: str,
        client_id: str,
        client_secret: str,
        webhook_secret: Optional[str] = None,
    ) -> None:
        """Encrypt and store Zoom S2S OAuth credentials on the org."""
        async with get_global_db() as db:
            encrypted_client_id = await encrypt_credential(db, client_id)
            encrypted_client_secret = await encrypt_credential(db, client_secret)
            encrypted_webhook = None
            if webhook_secret:
                encrypted_webhook = await encrypt_credential(db, webhook_secret)

            await db.execute(
                """
                UPDATE af_global.organizations
                SET zoom_account_id = $1,
                    zoom_client_id_encrypted = $2,
                    zoom_client_secret_encrypted = $3,
                    zoom_webhook_secret_encrypted = $4,
                    zoom_connected_at = NOW(),
                    updated_at = NOW()
                WHERE id = $5
                """,
                account_id, encrypted_client_id, encrypted_client_secret,
                encrypted_webhook, org_id,
            )

            # Enable scheduling.zoom feature flag
            await db.execute(
                """
                INSERT INTO af_global.feature_flags (organization_id, flag_key, is_enabled)
                VALUES ($1, 'scheduling.zoom', TRUE)
                ON CONFLICT (organization_id, flag_key)
                DO UPDATE SET is_enabled = TRUE, updated_at = NOW()
                """,
                org_id,
            )
        logger.info("Zoom connected", org_id=org_id, account_id=account_id)

    async def disconnect(self, org_id: str) -> None:
        """Clear Zoom credentials and disable feature flag."""
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET zoom_account_id = NULL,
                    zoom_client_id_encrypted = NULL,
                    zoom_client_secret_encrypted = NULL,
                    zoom_webhook_secret_encrypted = NULL,
                    zoom_connected_at = NULL,
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id,
            )
            await db.execute(
                """
                UPDATE af_global.feature_flags
                SET is_enabled = FALSE, updated_at = NOW()
                WHERE organization_id = $1 AND flag_key = 'scheduling.zoom'
                """,
                org_id,
            )

        # Clear cached token
        redis = await get_redis()
        if redis:
            await redis.delete(f"{ZOOM_TOKEN_CACHE_PREFIX}{org_id}")

        logger.info("Zoom disconnected", org_id=org_id)

    async def get_credentials(self, org_id: str) -> Optional[dict]:
        """Decrypt and return Zoom credentials, or None if not connected."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT zoom_account_id, zoom_client_id_encrypted,
                       zoom_client_secret_encrypted, zoom_webhook_secret_encrypted,
                       zoom_connected_at, zoom_auto_record, zoom_auto_publish
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
            if not row or not row["zoom_client_id_encrypted"]:
                return None

            client_id = await decrypt_credential(db, row["zoom_client_id_encrypted"])
            client_secret = await decrypt_credential(db, row["zoom_client_secret_encrypted"])
            webhook_secret = None
            if row["zoom_webhook_secret_encrypted"]:
                webhook_secret = await decrypt_credential(db, row["zoom_webhook_secret_encrypted"])

            return {
                "account_id": row["zoom_account_id"],
                "client_id": client_id,
                "client_secret": client_secret,
                "webhook_secret": webhook_secret,
                "connected_at": row["zoom_connected_at"],
                "auto_record": row["zoom_auto_record"],
                "auto_publish": row["zoom_auto_publish"],
            }

    async def get_connection_status(self, org_id: str) -> dict:
        """Return connection status without decrypting secrets."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT zoom_account_id, zoom_connected_at,
                       zoom_auto_record, zoom_auto_publish
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
        if not row or not row["zoom_connected_at"]:
            return {
                "zoom_connected": False,
                "zoom_account_id": None,
                "zoom_connected_at": None,
                "zoom_auto_record": True,
                "zoom_auto_publish": False,
            }
        return {
            "zoom_connected": True,
            "zoom_account_id": row["zoom_account_id"],
            "zoom_connected_at": row["zoom_connected_at"].isoformat() if row["zoom_connected_at"] else None,
            "zoom_auto_record": row["zoom_auto_record"],
            "zoom_auto_publish": row["zoom_auto_publish"],
        }

    async def update_settings(self, org_id: str, auto_record: Optional[bool] = None, auto_publish: Optional[bool] = None) -> dict:
        """Update Zoom org-level settings."""
        updates = []
        params = []
        idx = 1
        if auto_record is not None:
            updates.append(f"zoom_auto_record = ${idx}")
            params.append(auto_record)
            idx += 1
        if auto_publish is not None:
            updates.append(f"zoom_auto_publish = ${idx}")
            params.append(auto_publish)
            idx += 1
        if not updates:
            return await self.get_connection_status(org_id)

        params.append(org_id)
        async with get_global_db() as db:
            await db.execute(
                f"UPDATE af_global.organizations SET {', '.join(updates)}, updated_at = NOW() WHERE id = ${idx}",
                *params,
            )
        return await self.get_connection_status(org_id)

    # ── S2S OAuth Token ────────────────────────────────────────────────

    async def _get_access_token(self, org_id: str) -> str:
        """Get a Zoom S2S OAuth access token, cached in Redis."""
        # Check cache first
        redis = await get_redis()
        if redis:
            cached = await redis.get(f"{ZOOM_TOKEN_CACHE_PREFIX}{org_id}")
            if cached:
                return cached.decode() if isinstance(cached, bytes) else cached

        creds = await self.get_credentials(org_id)
        if not creds:
            raise ValueError("Zoom not connected for this organization")

        auth_str = b64encode(
            f"{creds['client_id']}:{creds['client_secret']}".encode()
        ).decode()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                ZOOM_OAUTH_URL,
                headers={
                    "Authorization": f"Basic {auth_str}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "account_credentials",
                    "account_id": creds["account_id"],
                },
                timeout=10,
            )

        if resp.status_code != 200:
            logger.error("Zoom OAuth failed", status=resp.status_code, body=resp.text)
            raise ValueError(f"Zoom OAuth failed: {resp.status_code}")

        data = resp.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", 3600)

        # Cache with some buffer
        if redis:
            await redis.setex(
                f"{ZOOM_TOKEN_CACHE_PREFIX}{org_id}",
                max(expires_in - 60, 60),
                token,
            )

        return token

    async def test_connection(
        self, account_id: str, client_id: str, client_secret: str
    ) -> dict:
        """Test Zoom credentials by fetching /users/me."""
        auth_str = b64encode(f"{client_id}:{client_secret}".encode()).decode()

        async with httpx.AsyncClient() as client:
            # Get token
            token_resp = await client.post(
                ZOOM_OAUTH_URL,
                headers={
                    "Authorization": f"Basic {auth_str}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "account_credentials",
                    "account_id": account_id,
                },
                timeout=10,
            )

            if token_resp.status_code != 200:
                return {"success": False, "error": "Invalid Zoom credentials — OAuth failed"}

            token = token_resp.json()["access_token"]

            # Test with /users/me
            user_resp = await client.get(
                f"{ZOOM_API_BASE}/users/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )

            if user_resp.status_code != 200:
                return {"success": False, "error": f"Zoom API error: {user_resp.status_code}"}

            user_data = user_resp.json()
            return {
                "success": True,
                "account_id": account_id,
                "email": user_data.get("email"),
                "display_name": f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
            }

    # ── Meeting CRUD ───────────────────────────────────────────────────

    async def _resolve_org_timezone(self, org_id: str) -> str:
        """Look up the org's IANA timezone (organizations.timezone). Falls
        back to America/Los_Angeles for legacy data without a TZ set so
        Zoom doesn't reject the request — but logs a warning so the
        missing config is visible.
        """
        from app.db.session import get_global_db
        try:
            async with get_global_db() as db:
                row = await db.fetchrow(
                    "SELECT timezone FROM af_global.organizations WHERE id = $1",
                    org_id,
                )
            tz = row["timezone"] if row and row["timezone"] else None
            if tz:
                return tz
        except Exception as e:
            logger.warning("Zoom: org timezone lookup failed", error=str(e), org_id=org_id)
        logger.warning(
            "Zoom: no timezone configured for org — defaulting to America/Los_Angeles",
            org_id=org_id,
        )
        return "America/Los_Angeles"

    async def create_meeting(
        self,
        org_id: str,
        topic: str,
        start_time: str,
        duration_minutes: int,
        instructor_zoom_user_id: Optional[str] = None,
        auto_record: bool = False,
    ) -> dict:
        """Create a Zoom meeting. Returns meeting_id, join_url, password.

        Wrapped in zoom_breaker so that a slow/erroring Zoom API fails fast
        for subsequent callers instead of piling up timeouts that drag the
        whole request queue. Breaker trips after 5 consecutive failures,
        half-opens after 90 seconds.
        """
        from app.core.circuit_breakers import zoom_breaker

        token = await self._get_access_token(org_id)
        user_id = instructor_zoom_user_id or "me"

        # Zoom interprets start_time + timezone in a specific way:
        #   - If start_time has a UTC offset (e.g. "2026-05-04T15:30:00+00:00"),
        #     Zoom treats the literal local portion ("15:30") as the time
        #     IN the `timezone` field's zone — so 15:30 in the org's TZ,
        #     not 15:30 UTC. Result: meeting scheduled at the wrong hour
        #     by the offset amount (caught 2026-05-02 when 8:30 AM Yin
        #     Yoga ended up booked at 3:30 PM on Zoom).
        #   - The fix is to send a NAIVE local timestamp + timezone field.
        # Normalize regardless of what the caller passes: parse, convert
        # to the org's TZ if tz-aware, and strip any offset.
        org_tz = await self._resolve_org_timezone(org_id)
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _ZoneInfo
        try:
            parsed = _dt.fromisoformat(start_time)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(_ZoneInfo(org_tz)).replace(tzinfo=None)
            normalized_start = parsed.isoformat(timespec="seconds")
        except (ValueError, TypeError) as parse_err:
            # If start_time isn't ISO-parseable, log loudly and pass
            # through — Zoom will reject and the error will surface.
            # Tighter except than bare Exception so genuine bugs (e.g.
            # zoneinfo not installed) propagate instead of being eaten.
            logger.warning(
                "Zoom create_meeting start_time not ISO-parseable — passing through",
                start_time=start_time, error=str(parse_err),
            )
            normalized_start = start_time

        body = {
            "topic": topic,
            "type": 2,  # Scheduled meeting
            "start_time": normalized_start,
            "duration": duration_minutes,
            "timezone": org_tz,
            "settings": {
                "join_before_host": True,
                "waiting_room": False,
                "auto_recording": "none",  # No recording — causes audio clicks for participants
                "meeting_authentication": False,
            },
        }

        async def _do_create():
            async with httpx.AsyncClient() as client:
                return await client.post(
                    f"{ZOOM_API_BASE}/users/{user_id}/meetings",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=15,
                )

        resp = await zoom_breaker.call_async(_do_create)

        if resp.status_code not in (200, 201):
            logger.error("Zoom create meeting failed", status=resp.status_code, body=resp.text)
            raise ValueError(f"Failed to create Zoom meeting: {resp.status_code}")

        data = resp.json()
        return {
            "meeting_id": str(data["id"]),
            "join_url": data["join_url"],
            "password": data.get("password", ""),
        }

    async def update_meeting(self, org_id: str, meeting_id: str, data: dict) -> None:
        """Update a Zoom meeting."""
        token = await self._get_access_token(org_id)

        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{ZOOM_API_BASE}/meetings/{meeting_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=data,
                timeout=15,
            )

        if resp.status_code not in (200, 204):
            logger.warning("Zoom update meeting failed", meeting_id=meeting_id, status=resp.status_code)

    async def delete_meeting(self, org_id: str, meeting_id: str) -> None:
        """Delete a Zoom meeting."""
        token = await self._get_access_token(org_id)

        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{ZOOM_API_BASE}/meetings/{meeting_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )

        if resp.status_code not in (200, 204, 404):
            logger.warning("Zoom delete meeting failed", meeting_id=meeting_id, status=resp.status_code)
        else:
            logger.info("Zoom meeting deleted", meeting_id=meeting_id)

    async def get_meeting(self, org_id: str, meeting_id: str) -> Optional[dict]:
        """Get Zoom meeting details."""
        token = await self._get_access_token(org_id)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{ZOOM_API_BASE}/meetings/{meeting_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )

        if resp.status_code != 200:
            return None
        return resp.json()

    # ── Recording Pipeline ─────────────────────────────────────────────

    async def get_recordings(self, org_id: str, meeting_id: str) -> list[dict]:
        """Get recording files for a meeting."""
        token = await self._get_access_token(org_id)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{ZOOM_API_BASE}/meetings/{meeting_id}/recordings",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )

        if resp.status_code != 200:
            return []

        data = resp.json()
        files = data.get("recording_files", [])
        return [
            {
                "id": f.get("id"),
                "file_type": f.get("file_type"),
                "file_size": f.get("file_size"),
                "download_url": f.get("download_url"),
                "recording_start": f.get("recording_start"),
                "recording_end": f.get("recording_end"),
                "status": f.get("status"),
            }
            for f in files
            if f.get("file_type") == "MP4"
        ]

    async def process_recording(
        self, org_id: str, session_id: str, meeting_id: str
    ) -> Optional[str]:
        """Process a completed recording — create video library entry.

        Returns video_id if created, None otherwise.
        """
        async with get_tenant_db() as db:
            # Update recording status to processing
            await db.execute(
                "UPDATE class_sessions SET recording_status = 'processing' WHERE id = $1",
                session_id,
            )

            # Get session details
            session = await db.fetchrow(
                "SELECT * FROM class_sessions WHERE id = $1", session_id
            )
            if not session:
                return None

        # Get recording files
        recordings = await self.get_recordings(org_id, meeting_id)
        if not recordings:
            async with get_tenant_db() as db:
                await db.execute(
                    "UPDATE class_sessions SET recording_status = 'failed' WHERE id = $1",
                    session_id,
                )
            return None

        # Use the first MP4 recording
        recording = recordings[0]
        download_url = recording["download_url"]

        # Get org settings
        creds = await self.get_credentials(org_id)
        auto_publish = creds.get("auto_publish", False) if creds else False

        # Create video entry in library
        video_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO videos
                    (id, source, external_id, title, description,
                     duration_seconds, instructor_id, is_published,
                     published_at, metadata)
                VALUES ($1, 'zoom_recording', $2, $3, $4, $5, $6, $7,
                        CASE WHEN $7 THEN NOW() ELSE NULL END,
                        $8)
                """,
                video_id, meeting_id,
                session["title"] or "Recorded Class",
                f"Recorded from live class on {session['starts_at'].strftime('%Y-%m-%d')}",
                recording.get("file_size", 0),  # Will be updated with actual duration later
                str(session["instructor_id"]) if session["instructor_id"] else None,
                auto_publish,
                json.dumps({
                    "zoom_meeting_id": meeting_id,
                    "zoom_download_url": download_url,
                    "recording_start": recording.get("recording_start"),
                    "recording_end": recording.get("recording_end"),
                }),
            )

            # Link video to session
            status = "published" if auto_publish else "ready"
            await db.execute(
                """
                UPDATE class_sessions
                SET recording_status = $1, recording_url = $2,
                    video_id = $3, updated_at = NOW()
                WHERE id = $4
                """,
                status, download_url, video_id, session_id,
            )

        logger.info(
            "Recording processed",
            session_id=session_id, video_id=video_id,
            auto_publish=auto_publish,
        )
        return video_id

    # ── Webhook Handling ───────────────────────────────────────────────

    @staticmethod
    def verify_webhook_signature(
        payload: bytes, signature: str, timestamp: str, secret: str
    ) -> bool:
        """Verify Zoom webhook signature using HMAC-SHA256."""
        message = f"v0:{timestamp}:{payload.decode()}"
        expected = "v0=" + hmac.new(
            secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle_webhook(self, org_id: str, event: dict) -> dict:
        """Route Zoom webhook events."""
        event_type = event.get("event", "")
        payload = event.get("payload", {})
        meeting = payload.get("object", {})
        meeting_id = str(meeting.get("id", ""))

        logger.info("Zoom webhook", event_type=event_type, meeting_id=meeting_id)

        if event_type == "meeting.started":
            await self._handle_meeting_started(meeting_id)
        elif event_type == "meeting.ended":
            await self._handle_meeting_ended(meeting_id)
        elif event_type == "recording.completed":
            await self._handle_recording_completed(org_id, meeting_id)

        return {"status": "ok"}

    async def _handle_meeting_started(self, meeting_id: str) -> None:
        """Mark session as recording if auto_record is enabled."""
        async with get_tenant_db() as db:
            await db.execute(
                """
                UPDATE class_sessions
                SET recording_status = CASE WHEN auto_record THEN 'recording' ELSE recording_status END,
                    updated_at = NOW()
                WHERE zoom_meeting_id = $1
                """,
                meeting_id,
            )

    async def _handle_meeting_ended(self, meeting_id: str) -> None:
        """Update recording status to processing if was recording."""
        async with get_tenant_db() as db:
            await db.execute(
                """
                UPDATE class_sessions
                SET recording_status = CASE
                    WHEN recording_status = 'recording' THEN 'processing'
                    ELSE recording_status END,
                    updated_at = NOW()
                WHERE zoom_meeting_id = $1
                """,
                meeting_id,
            )

    async def _handle_recording_completed(self, org_id: str, meeting_id: str) -> None:
        """Process completed recording — create video entry."""
        async with get_tenant_db() as db:
            session = await db.fetchrow(
                "SELECT id FROM class_sessions WHERE zoom_meeting_id = $1",
                meeting_id,
            )
        if session:
            await self.process_recording(org_id, str(session["id"]), meeting_id)

    # ── Org Lookup ─────────────────────────────────────────────────────

    async def find_org_by_account_id(self, account_id: str) -> Optional[str]:
        """Look up org ID from Zoom account ID (for webhook routing)."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT id FROM af_global.organizations WHERE zoom_account_id = $1",
                account_id,
            )
            return str(row["id"]) if row else None
