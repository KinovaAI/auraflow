"""AuraFlow — Google My Business (Business Profile) Service

OAuth2 authorization code flow for Google Business Profile API.
Syncs GMB reviews into the local reviews table with sentiment analysis,
allows posting reply responses back to GMB, and manages location selection.

Credentials are stored in af_global.organization_integrations with encrypted
tokens via pgcrypto. Uses httpx for all HTTP calls and Redis for token caching.
"""
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.core.redis import get_redis
from app.db.session import get_tenant_db, get_global_db
from app.utils.encryption import encrypt_credential, decrypt_credential

# ── Google API Constants ────────────────────────────────────────────────────
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMB_SCOPES = " ".join([
    "https://www.googleapis.com/auth/business.manage",
])
GMB_API_BASE = "https://mybusiness.googleapis.com/v4"
GMB_ACCOUNT_MGMT_BASE = "https://mybusinessaccountmanagement.googleapis.com/v1"
GMB_TOKEN_CACHE_PREFIX = "gmb_token:"
GMB_TOKEN_CACHE_TTL = 3500  # ~58 min (tokens last 60 min)
INTEGRATION_TYPE = "gmb"


class GmbService:
    """Google My Business integration: OAuth, review sync, location management."""

    # ══════════════════════════════════════════════════════════════════════════
    # OAuth & Connection
    # ══════════════════════════════════════════════════════════════════════════

    async def get_oauth_url(self, org_id: str) -> str:
        """Generate the Google OAuth2 consent URL for Business Profile access."""
        if not settings.GOOGLE_CLIENT_ID:
            raise ValueError("Google OAuth not configured — GOOGLE_CLIENT_ID is missing")

        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": f"{settings.API_URL}/api/v1/integrations/gmb/callback",
            "response_type": "code",
            "scope": GMB_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": org_id,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def handle_oauth_callback(self, org_id: str, code: str) -> dict:
        """Exchange the authorization code for tokens, encrypt, and persist."""
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise ValueError("Google OAuth not configured")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": f"{settings.API_URL}/api/v1/integrations/gmb/callback",
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                error_msg = resp.json().get("error_description", "Token exchange failed")
                logger.error("GMB OAuth token exchange failed", status=resp.status_code, error=error_msg)
                raise ValueError(f"Google OAuth error: {error_msg}")

            tokens = resp.json()

        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in", 3600)

        if not refresh_token:
            raise ValueError(
                "No refresh token received — revoke app access in your Google account and retry"
            )

        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Encrypt and store
        async with get_global_db() as db:
            enc_access = await encrypt_credential(db, access_token)
            enc_refresh = await encrypt_credential(db, refresh_token)

            await db.execute(
                """
                INSERT INTO af_global.organization_integrations
                    (id, organization_id, integration_type,
                     access_token_encrypted, refresh_token_encrypted,
                     token_expires_at, metadata, connected_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
                ON CONFLICT (organization_id, integration_type)
                DO UPDATE SET
                    access_token_encrypted = EXCLUDED.access_token_encrypted,
                    refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
                    token_expires_at = EXCLUDED.token_expires_at,
                    connected_at = NOW(),
                    disconnected_at = NULL,
                    updated_at = NOW()
                """,
                str(uuid.uuid4()), org_id, INTEGRATION_TYPE,
                enc_access, enc_refresh, token_expires_at,
                json.dumps({}),
            )

            # Enable feature flag
            await db.execute(
                """
                INSERT INTO af_global.feature_flags (organization_id, flag_key, is_enabled)
                VALUES ($1, 'integrations.gmb', TRUE)
                ON CONFLICT (organization_id, flag_key)
                DO UPDATE SET is_enabled = TRUE, updated_at = NOW()
                """,
                org_id,
            )

        # Cache access token
        redis = await get_redis()
        if redis:
            await redis.setex(
                f"{GMB_TOKEN_CACHE_PREFIX}{org_id}",
                min(expires_in - 60, GMB_TOKEN_CACHE_TTL),
                access_token,
            )

        logger.info("GMB OAuth connected", org_id=org_id)
        return {"connected": True}

    async def refresh_access_token(self, org_id: str) -> str:
        """Refresh the GMB access token using the stored refresh token.

        Returns the new access token string. Caches it in Redis.
        """
        # Check cache first
        redis = await get_redis()
        if redis:
            cached = await redis.get(f"{GMB_TOKEN_CACHE_PREFIX}{org_id}")
            if cached:
                return cached.decode() if isinstance(cached, bytes) else cached

        # Fetch encrypted refresh token
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT refresh_token_encrypted
                FROM af_global.organization_integrations
                WHERE organization_id = $1
                  AND integration_type = $2
                  AND disconnected_at IS NULL
                """,
                org_id, INTEGRATION_TYPE,
            )
            if not row or not row["refresh_token_encrypted"]:
                raise ValueError("GMB not connected — no refresh token found")

            refresh_token = await decrypt_credential(db, row["refresh_token_encrypted"])

        # Exchange refresh token for new access token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                logger.error("GMB token refresh failed", status=resp.status_code, body=resp.text)
                raise ValueError("Failed to refresh GMB access token")

            tokens = resp.json()

        access_token = tokens["access_token"]
        expires_in = tokens.get("expires_in", 3600)
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Update stored access token + expiry
        async with get_global_db() as db:
            enc_access = await encrypt_credential(db, access_token)
            await db.execute(
                """
                UPDATE af_global.organization_integrations
                SET access_token_encrypted = $1,
                    token_expires_at = $2,
                    updated_at = NOW()
                WHERE organization_id = $3 AND integration_type = $4
                """,
                enc_access, token_expires_at, org_id, INTEGRATION_TYPE,
            )

        # Cache
        if redis:
            await redis.setex(
                f"{GMB_TOKEN_CACHE_PREFIX}{org_id}",
                min(expires_in - 60, GMB_TOKEN_CACHE_TTL),
                access_token,
            )

        return access_token

    async def get_connection_status(self, org_id: str) -> dict:
        """Return GMB connection status without decrypting secrets."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT connected_at, disconnected_at, token_expires_at, metadata
                FROM af_global.organization_integrations
                WHERE organization_id = $1 AND integration_type = $2
                """,
                org_id, INTEGRATION_TYPE,
            )

        if not row or row["disconnected_at"] is not None:
            return {"connected": False, "connected_at": None, "location_id": None}

        metadata = row["metadata"] if isinstance(row["metadata"], dict) else (
            json.loads(row["metadata"]) if row["metadata"] else {}
        )

        return {
            "connected": True,
            "connected_at": row["connected_at"].isoformat() if row["connected_at"] else None,
            "token_expires_at": row["token_expires_at"].isoformat() if row["token_expires_at"] else None,
            "location_id": metadata.get("location_id"),
            "location_name": metadata.get("location_name"),
            "account_id": metadata.get("account_id"),
        }

    async def disconnect(self, org_id: str) -> bool:
        """Disconnect GMB integration. Soft-delete: sets disconnected_at."""
        async with get_global_db() as db:
            result = await db.execute(
                """
                UPDATE af_global.organization_integrations
                SET disconnected_at = NOW(), updated_at = NOW()
                WHERE organization_id = $1
                  AND integration_type = $2
                  AND disconnected_at IS NULL
                """,
                org_id, INTEGRATION_TYPE,
            )

            # Disable feature flag
            await db.execute(
                """
                UPDATE af_global.feature_flags
                SET is_enabled = FALSE, updated_at = NOW()
                WHERE organization_id = $1 AND flag_key = 'integrations.gmb'
                """,
                org_id,
            )

        # Clear cached token
        redis = await get_redis()
        if redis:
            await redis.delete(f"{GMB_TOKEN_CACHE_PREFIX}{org_id}")

        disconnected = "UPDATE 1" in result
        if disconnected:
            logger.info("GMB disconnected", org_id=org_id)
        return disconnected

    # ══════════════════════════════════════════════════════════════════════════
    # Review Sync
    # ══════════════════════════════════════════════════════════════════════════

    async def sync_reviews(self, org_id: str) -> dict:
        """Fetch reviews from GMB and upsert into the tenant reviews table.

        Returns summary: {synced, created, updated, errors}.
        """
        location = await self._get_location_info(org_id)
        if not location:
            raise ValueError(
                "No GMB location configured — use set_primary_location first"
            )

        access_token = await refresh_access_token_safe(self, org_id)
        account_id = location["account_id"]
        location_id = location["location_id"]

        # Fetch reviews from GMB API
        all_reviews = []
        next_page_token = None

        async with httpx.AsyncClient() as client:
            while True:
                url = (
                    f"{GMB_API_BASE}/accounts/{account_id}"
                    f"/locations/{location_id}/reviews"
                )
                params = {"pageSize": 50}
                if next_page_token:
                    params["pageToken"] = next_page_token

                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                    timeout=30,
                )

                if resp.status_code == 401:
                    # Token may have expired mid-sync; try one refresh
                    access_token = await self.refresh_access_token(org_id)
                    resp = await client.get(
                        url,
                        headers={"Authorization": f"Bearer {access_token}"},
                        params=params,
                        timeout=30,
                    )

                if resp.status_code != 200:
                    logger.error(
                        "GMB reviews fetch failed",
                        status=resp.status_code, body=resp.text[:500],
                    )
                    raise ValueError(f"GMB API error: {resp.status_code}")

                data = resp.json()
                reviews = data.get("reviews", [])
                all_reviews.extend(reviews)

                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break

        # Upsert into tenant reviews table
        created = 0
        updated = 0
        errors = 0

        async with get_tenant_db() as db:
            for gmb_review in all_reviews:
                try:
                    result = await self._upsert_gmb_review(db, gmb_review)
                    if result == "created":
                        created += 1
                    elif result == "updated":
                        updated += 1
                except Exception as e:
                    errors += 1
                    logger.warning(
                        "GMB review upsert failed",
                        gmb_review_id=gmb_review.get("reviewId"),
                        error=str(e),
                    )

        logger.info(
            "GMB review sync complete",
            org_id=org_id, total=len(all_reviews),
            created=created, updated=updated, errors=errors,
        )

        return {
            "synced": len(all_reviews),
            "created": created,
            "updated": updated,
            "errors": errors,
        }

    async def _upsert_gmb_review(self, db, gmb_review: dict) -> str:
        """Upsert a single GMB review into the reviews table.

        Returns 'created' or 'updated'.
        """
        gmb_review_id = gmb_review.get("reviewId", "")
        reviewer = gmb_review.get("reviewer", {})
        reviewer_name = reviewer.get("displayName", "Google User")
        star_rating = gmb_review.get("starRating", "FIVE")
        comment = gmb_review.get("comment", "")
        create_time = gmb_review.get("createTime", "")
        update_time = gmb_review.get("updateTime", "")

        # Map Google star rating enum to integer
        star_map = {
            "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5,
        }
        rating = star_map.get(star_rating, 5)

        # Check for existing GMB reply
        reply = gmb_review.get("reviewReply", {})
        reply_text = reply.get("comment") if reply else None

        # Sentiment analysis (reuse ReviewService logic inline to avoid circular deps)
        sentiment_data = await self._quick_sentiment(comment)

        # Check if already exists
        existing = await db.fetchrow(
            "SELECT id FROM reviews WHERE gmb_review_id = $1",
            gmb_review_id,
        )

        gmb_metadata = json.dumps({
            "reviewer_name": reviewer_name,
            "reviewer_profile_photo": reviewer.get("profilePhotoUrl"),
            "star_rating_enum": star_rating,
            "create_time": create_time,
            "update_time": update_time,
            "gmb_reply": reply_text,
            "source": "google_my_business",
        })

        if existing:
            await db.execute(
                """
                UPDATE reviews
                SET rating = $2,
                    review_text = $3,
                    sentiment = $4,
                    sentiment_score = $5,
                    ai_analysis = $6,
                    gmb_metadata = $7::jsonb,
                    updated_at = NOW()
                WHERE gmb_review_id = $1
                """,
                gmb_review_id, rating, comment,
                sentiment_data["sentiment"],
                sentiment_data["score"],
                sentiment_data["analysis"],
                gmb_metadata,
            )
            return "updated"
        else:
            review_id = str(uuid.uuid4())
            await db.execute(
                """
                INSERT INTO reviews
                    (id, gmb_review_id, rating, review_text, reviewer_name,
                     sentiment, sentiment_score, ai_analysis, gmb_metadata,
                     source, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, 'gmb', $10)
                """,
                review_id, gmb_review_id, rating, comment, reviewer_name,
                sentiment_data["sentiment"],
                sentiment_data["score"],
                sentiment_data["analysis"],
                gmb_metadata,
                _parse_iso_datetime(create_time),
            )
            return "created"

    async def _quick_sentiment(self, text: str) -> dict:
        """Run sentiment analysis on review text. Graceful fallback."""
        if not text or not settings.ANTHROPIC_API_KEY:
            return {"sentiment": None, "score": None, "analysis": None}

        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            message = await client.messages.create(
                model=settings.ANTHROPIC_MODEL_FAST,
                max_tokens=256,
                system=(
                    "Analyze the sentiment of this Google review for a wellness studio. "
                    "Return ONLY a JSON object (no markdown fences): "
                    '{"sentiment": "positive"|"neutral"|"negative", '
                    '"score": float from -1.0 to 1.0, '
                    '"analysis": "one sentence summary of key themes"}'
                ),
                messages=[{"role": "user", "content": text}],
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(raw)
            return {
                "sentiment": result.get("sentiment"),
                "score": float(result.get("score", 0)),
                "analysis": result.get("analysis"),
            }
        except Exception as e:
            logger.warning("GMB sentiment analysis failed", error=str(e))
            return {"sentiment": None, "score": None, "analysis": None}

    async def post_review_response(
        self, org_id: str, review_id: str, response_text: str,
    ) -> dict:
        """Post a reply to a GMB review and update the local record.

        `review_id` is the local review UUID — we look up the gmb_review_id from it.
        """
        # Get local review with GMB identifiers
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT id, gmb_review_id, gmb_metadata FROM reviews WHERE id = $1",
                review_id,
            )
        if not row or not row["gmb_review_id"]:
            raise ValueError("Review not found or is not a GMB review")

        gmb_review_id = row["gmb_review_id"]

        location = await self._get_location_info(org_id)
        if not location:
            raise ValueError("No GMB location configured")

        access_token = await refresh_access_token_safe(self, org_id)
        account_id = location["account_id"]
        location_id = location["location_id"]

        # PUT reply to GMB
        url = (
            f"{GMB_API_BASE}/accounts/{account_id}"
            f"/locations/{location_id}/reviews/{gmb_review_id}/reply"
        )

        async with httpx.AsyncClient() as client:
            resp = await client.put(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"comment": response_text},
                timeout=15,
            )

            if resp.status_code == 401:
                access_token = await self.refresh_access_token(org_id)
                resp = await client.put(
                    url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json={"comment": response_text},
                    timeout=15,
                )

            if resp.status_code not in (200, 201):
                logger.error(
                    "GMB reply post failed",
                    status=resp.status_code, body=resp.text[:500],
                    gmb_review_id=gmb_review_id,
                )
                raise ValueError(f"Failed to post GMB reply: {resp.status_code}")

        # Update local record
        async with get_tenant_db() as db:
            await db.execute(
                """
                UPDATE reviews
                SET response_text = $2,
                    responded_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                """,
                review_id, response_text,
            )

        logger.info(
            "GMB review response posted",
            org_id=org_id, review_id=review_id,
            gmb_review_id=gmb_review_id,
        )
        return {"posted": True, "review_id": review_id, "gmb_review_id": gmb_review_id}

    async def get_gmb_reviews(
        self, org_id: str, limit: int = 50,
    ) -> list[dict]:
        """Return locally synced GMB reviews from the tenant reviews table."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT id, gmb_review_id, rating, review_text, reviewer_name,
                       sentiment, sentiment_score, ai_analysis,
                       response_text, responded_at,
                       gmb_metadata, source, created_at, updated_at
                FROM reviews
                WHERE source = 'gmb' AND gmb_review_id IS NOT NULL
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit,
            )

        results = []
        for r in rows:
            d = dict(r)
            for k in ("id",):
                if d.get(k):
                    d[k] = str(d[k])
            for k in ("created_at", "updated_at", "responded_at"):
                if d.get(k):
                    d[k] = d[k].isoformat()
            if d.get("sentiment_score") is not None:
                d["sentiment_score"] = float(d["sentiment_score"])
            if d.get("gmb_metadata") and isinstance(d["gmb_metadata"], str):
                d["gmb_metadata"] = json.loads(d["gmb_metadata"])
            results.append(d)

        return results

    # ══════════════════════════════════════════════════════════════════════════
    # Location Management
    # ══════════════════════════════════════════════════════════════════════════

    async def list_locations(self, org_id: str) -> list[dict]:
        """List all GMB locations accessible by this account."""
        access_token = await refresh_access_token_safe(self, org_id)

        # Step 1: Get accounts
        accounts = await self._list_accounts(access_token)
        if not accounts:
            return []

        # Step 2: For each account, list locations
        all_locations = []
        async with httpx.AsyncClient() as client:
            for account in accounts:
                account_name = account.get("name", "")  # e.g. "accounts/123"
                url = f"{GMB_API_BASE}/{account_name}/locations"
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"readMask": "name,title,storefrontAddress,websiteUri,metadata"},
                    timeout=20,
                )

                if resp.status_code != 200:
                    logger.warning(
                        "GMB locations fetch failed for account",
                        account=account_name, status=resp.status_code,
                    )
                    continue

                data = resp.json()
                for loc in data.get("locations", []):
                    location_name = loc.get("name", "")
                    # Extract location_id from resource name "accounts/123/locations/456"
                    parts = location_name.split("/")
                    location_id = parts[-1] if len(parts) >= 4 else location_name
                    account_id = parts[1] if len(parts) >= 2 else ""

                    address = loc.get("storefrontAddress", {})
                    address_lines = address.get("addressLines", [])

                    all_locations.append({
                        "location_id": location_id,
                        "account_id": account_id,
                        "resource_name": location_name,
                        "title": loc.get("title", ""),
                        "address": ", ".join(address_lines) if address_lines else "",
                        "city": address.get("locality", ""),
                        "state": address.get("administrativeArea", ""),
                        "postal_code": address.get("postalCode", ""),
                        "website": loc.get("websiteUri", ""),
                    })

        return all_locations

    async def set_primary_location(
        self, org_id: str, location_id: str,
    ) -> dict:
        """Set the primary GMB location for review sync.

        Stores account_id + location_id in the integration metadata.
        """
        # Verify the location exists by listing locations
        locations = await self.list_locations(org_id)
        target = None
        for loc in locations:
            if loc["location_id"] == location_id:
                target = loc
                break

        if not target:
            raise ValueError(f"Location {location_id} not found in your GMB account")

        metadata = {
            "location_id": target["location_id"],
            "account_id": target["account_id"],
            "location_name": target["title"],
            "location_address": target["address"],
        }

        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organization_integrations
                SET metadata = $1::jsonb, updated_at = NOW()
                WHERE organization_id = $2 AND integration_type = $3
                """,
                json.dumps(metadata), org_id, INTEGRATION_TYPE,
            )

        logger.info(
            "GMB primary location set",
            org_id=org_id, location_id=location_id, name=target["title"],
        )
        return {
            "location_id": target["location_id"],
            "location_name": target["title"],
            "address": target["address"],
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Internal Helpers
    # ══════════════════════════════════════════════════════════════════════════

    async def _get_location_info(self, org_id: str) -> Optional[dict]:
        """Get the configured location_id and account_id from integration metadata."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT metadata
                FROM af_global.organization_integrations
                WHERE organization_id = $1
                  AND integration_type = $2
                  AND disconnected_at IS NULL
                """,
                org_id, INTEGRATION_TYPE,
            )

        if not row or not row["metadata"]:
            return None

        metadata = row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"])

        location_id = metadata.get("location_id")
        account_id = metadata.get("account_id")
        if not location_id or not account_id:
            return None

        return {
            "location_id": location_id,
            "account_id": account_id,
            "location_name": metadata.get("location_name"),
        }

    async def _list_accounts(self, access_token: str) -> list[dict]:
        """List GMB accounts the authorized user has access to."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GMB_ACCOUNT_MGMT_BASE}/accounts",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning("GMB accounts list failed", status=resp.status_code)
                return []

            return resp.json().get("accounts", [])


# ── Module-level Helpers ────────────────────────────────────────────────────

async def refresh_access_token_safe(svc: GmbService, org_id: str) -> str:
    """Convenience wrapper that raises a clear error if GMB is not connected."""
    try:
        return await svc.refresh_access_token(org_id)
    except ValueError:
        raise ValueError(
            "GMB not connected — complete the OAuth flow at /integrations/gmb/connect"
        )


def _parse_iso_datetime(iso_str: str) -> datetime:
    """Parse a Google API ISO datetime string to a Python datetime."""
    if not iso_str:
        return datetime.now(timezone.utc)
    try:
        # Google uses RFC 3339: "2024-01-15T10:30:00.000Z"
        cleaned = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)
