"""AuraFlow — Meta/Facebook Ads Service

API wrapper for Meta Marketing API. Handles OAuth (Facebook Login),
campaign/ad set/ad CRUD, interest targeting, Insights API metrics,
and budget safety checks. Mirrors google_ads_service.py patterns.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.utils.encryption import encrypt_credential, decrypt_credential

META_AUTH_URL = "https://www.facebook.com/v21.0/dialog/oauth"
META_TOKEN_URL = "https://graph.facebook.com/v21.0/oauth/access_token"
META_GRAPH_BASE = "https://graph.facebook.com/v21.0"
META_ADS_SCOPES = "ads_management,ads_read,pages_read_engagement"


class MetaAdsService:
    """Manages Meta Marketing API interactions for a single tenant/organization."""

    async def _get_platform_creds(self) -> dict:
        """DB-first credential lookup with env var fallback."""
        try:
            from app.services.platform.platform_config_service import PlatformConfigService
            return await PlatformConfigService().get_raw_meta_credentials()
        except Exception:
            return {
                "meta_app_id": settings.META_APP_ID,
                "meta_app_secret": settings.META_APP_SECRET,
                "meta_page_access_token": settings.META_PAGE_ACCESS_TOKEN,
                "meta_page_id": settings.META_PAGE_ID,
                "instagram_business_account_id": settings.INSTAGRAM_BUSINESS_ACCOUNT_ID,
            }

    # ── OAuth 2.0 (Facebook Login) ─────────────────────────────────────────────

    async def get_oauth_url(self, org_id: str) -> str:
        """Generate Facebook Login consent URL for Meta Ads authorization."""
        creds = await self._get_platform_creds()
        params = {
            "client_id": creds.get("meta_app_id") or settings.META_APP_ID,
            "redirect_uri": f"{settings.API_URL}/api/v1/meta-ads/connect/oauth/callback",
            "response_type": "code",
            "scope": META_ADS_SCOPES,
            "state": org_id,
        }
        return f"{META_AUTH_URL}?{urlencode(params)}"

    async def handle_oauth_callback(self, org_id: str, code: str) -> dict:
        """Exchange code for short-lived token, then exchange for 60-day long-lived token."""
        creds = await self._get_platform_creds()
        app_id = creds.get("meta_app_id") or settings.META_APP_ID
        app_secret = creds.get("meta_app_secret") or settings.META_APP_SECRET
        async with httpx.AsyncClient() as client:
            # Step 1: Exchange code for short-lived token
            resp = await client.get(
                META_TOKEN_URL,
                params={
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "redirect_uri": f"{settings.API_URL}/api/v1/meta-ads/connect/oauth/callback",
                    "code": code,
                },
                timeout=15,
            )
            if resp.status_code != 200:
                error = resp.json().get("error", {}).get("message", "OAuth token exchange failed")
                raise ValueError(error)

            short_token = resp.json()["access_token"]

            # Step 2: Exchange short-lived for 60-day long-lived token
            resp2 = await client.get(
                META_TOKEN_URL,
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "fb_exchange_token": short_token,
                },
                timeout=15,
            )
            if resp2.status_code != 200:
                error = resp2.json().get("error", {}).get("message", "Long-lived token exchange failed")
                raise ValueError(error)

            long_token = resp2.json()["access_token"]

        # Store encrypted long-lived token
        async with get_global_db() as db:
            encrypted = await encrypt_credential(db, long_token)
            await db.execute(
                """
                UPDATE af_global.organizations
                SET meta_access_token_encrypted = $1,
                    meta_connected_at = NOW(),
                    updated_at = NOW()
                WHERE id = $2
                """,
                encrypted, org_id,
            )

        logger.info("Meta Ads OAuth authorized", org_id=org_id)
        return {"authorized": True}

    async def get_connection_status(self, org_id: str) -> dict:
        """Check if Meta Ads is connected for this org."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT meta_ad_account_id, meta_connected_at,
                       meta_access_token_encrypted IS NOT NULL AS has_token
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
        if not row:
            return {"connected": False}
        return {
            "connected": bool(row["has_token"]),
            "ad_account_id": row["meta_ad_account_id"],
            "connected_at": row["meta_connected_at"].isoformat() if row["meta_connected_at"] else None,
        }

    async def set_ad_account_id(self, org_id: str, ad_account_id: str) -> None:
        """Store the Meta Ad Account ID for this org."""
        # Normalize: ensure it starts with "act_"
        if not ad_account_id.startswith("act_"):
            ad_account_id = f"act_{ad_account_id}"
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET meta_ad_account_id = $1, updated_at = NOW()
                WHERE id = $2
                """,
                ad_account_id, org_id,
            )

    async def disconnect(self, org_id: str) -> None:
        """Disconnect Meta Ads — clear credentials and pause all campaigns."""
        await self.pause_all_campaigns(org_id)

        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET meta_ad_account_id = NULL,
                    meta_access_token_encrypted = NULL,
                    meta_connected_at = NULL,
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id,
            )
        logger.info("Meta Ads disconnected", org_id=org_id)

    # ── Credential Helpers ────────────────────────────────────────────────────

    async def _get_access_token(self, org_id: str) -> Optional[str]:
        """Get decrypted access token for an org."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT meta_access_token_encrypted FROM af_global.organizations WHERE id = $1",
                org_id,
            )
            if not row or not row["meta_access_token_encrypted"]:
                return None
            return await decrypt_credential(db, row["meta_access_token_encrypted"])

    async def _get_ad_account_id(self, org_id: str) -> Optional[str]:
        """Get Meta Ad Account ID for an org."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT meta_ad_account_id FROM af_global.organizations WHERE id = $1",
                org_id,
            )
        return row["meta_ad_account_id"] if row else None

    async def _api_call(
        self, org_id: str, method: str, endpoint: str,
        body: Optional[dict] = None, params: Optional[dict] = None,
    ) -> dict:
        """Make an authenticated Meta Graph API call."""
        access_token = await self._get_access_token(org_id)
        if not access_token:
            raise ValueError("Meta Ads not connected — complete OAuth setup first")

        url = f"{META_GRAPH_BASE}/{endpoint}"
        request_params = {"access_token": access_token}
        if params:
            request_params.update(params)

        async with httpx.AsyncClient() as client:
            if method == "GET":
                resp = await client.get(url, params=request_params, timeout=30)
            elif method == "POST":
                resp = await client.post(url, params=request_params, json=body or {}, timeout=30)
            elif method == "DELETE":
                resp = await client.delete(url, params=request_params, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

        if resp.status_code not in (200, 201):
            error_detail = resp.text[:500]
            logger.error("Meta Ads API error", status=resp.status_code, detail=error_detail, endpoint=endpoint)
            raise ValueError(f"Meta Ads API error ({resp.status_code}): {error_detail}")

        return resp.json()

    # ── Config (Tenant-Level Settings) ────────────────────────────────────────

    async def get_config(self, org_id: str) -> Optional[dict]:
        """Get Meta Ads config for this tenant."""
        async with get_tenant_db() as db:
            row = await db.fetchrow("SELECT * FROM meta_ads_config LIMIT 1")
        if not row:
            return None
        d = dict(row)
        for k in ("id",):
            if d.get(k):
                d[k] = str(d[k])
        for k in ("created_at", "updated_at"):
            if d.get(k):
                d[k] = d[k].isoformat()
        return d

    async def save_config(self, config_data: dict) -> dict:
        """Create or update the Meta Ads config for this tenant."""
        async with get_tenant_db() as db:
            existing = await db.fetchrow("SELECT id FROM meta_ads_config LIMIT 1")
            if existing:
                await db.execute(
                    """
                    UPDATE meta_ads_config SET
                        max_monthly_spend_cents = COALESCE($1, max_monthly_spend_cents),
                        target_latitude = COALESCE($2, target_latitude),
                        target_longitude = COALESCE($3, target_longitude),
                        target_radius_miles = COALESCE($4, target_radius_miles),
                        target_age_min = COALESCE($5, target_age_min),
                        target_age_max = COALESCE($6, target_age_max),
                        target_genders = COALESCE($7, target_genders),
                        target_interests = COALESCE($8, target_interests),
                        class_focus = COALESCE($9, class_focus),
                        brand_voice = COALESCE($10, brand_voice),
                        excluded_interests = COALESCE($11, excluded_interests),
                        approval_threshold_cents = COALESCE($12, approval_threshold_cents),
                        is_active = COALESCE($13, is_active),
                        meta_pixel_id = COALESCE($14, meta_pixel_id),
                        default_page_id = COALESCE($15, default_page_id),
                        instagram_account_id = COALESCE($16, instagram_account_id),
                        updated_at = NOW()
                    WHERE id = $17
                    """,
                    config_data.get("max_monthly_spend_cents"),
                    config_data.get("target_latitude"),
                    config_data.get("target_longitude"),
                    config_data.get("target_radius_miles"),
                    config_data.get("target_age_min"),
                    config_data.get("target_age_max"),
                    config_data.get("target_genders"),
                    config_data.get("target_interests"),
                    config_data.get("class_focus"),
                    config_data.get("brand_voice"),
                    config_data.get("excluded_interests"),
                    config_data.get("approval_threshold_cents"),
                    config_data.get("is_active"),
                    config_data.get("meta_pixel_id"),
                    config_data.get("default_page_id"),
                    config_data.get("instagram_account_id"),
                    str(existing["id"]),
                )
                config_id = str(existing["id"])
            else:
                row = await db.fetchrow(
                    """
                    INSERT INTO meta_ads_config
                        (max_monthly_spend_cents, target_latitude, target_longitude,
                         target_radius_miles, target_age_min, target_age_max,
                         target_genders, target_interests, class_focus,
                         brand_voice, excluded_interests, approval_threshold_cents,
                         is_active, meta_pixel_id, default_page_id, instagram_account_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                    RETURNING id
                    """,
                    config_data.get("max_monthly_spend_cents", 50000),
                    config_data.get("target_latitude"),
                    config_data.get("target_longitude"),
                    config_data.get("target_radius_miles", 15),
                    config_data.get("target_age_min", 18),
                    config_data.get("target_age_max", 65),
                    config_data.get("target_genders"),
                    config_data.get("target_interests"),
                    config_data.get("class_focus"),
                    config_data.get("brand_voice"),
                    config_data.get("excluded_interests"),
                    config_data.get("approval_threshold_cents", 10000),
                    config_data.get("is_active", False),
                    config_data.get("meta_pixel_id"),
                    config_data.get("default_page_id"),
                    config_data.get("instagram_account_id"),
                )
                config_id = str(row["id"])

        return await self.get_config(None) or {"id": config_id}

    # ── Campaign CRUD ─────────────────────────────────────────────────────────

    async def create_campaign(
        self, org_id: str, name: str, objective: str, daily_budget_cents: int,
    ) -> dict:
        """Create a Meta Ads campaign."""
        ad_account_id = await self._get_ad_account_id(org_id)
        if not ad_account_id:
            raise ValueError("Meta Ad Account ID not set")

        result = await self._api_call(org_id, "POST", f"{ad_account_id}/campaigns", {
            "name": name,
            "objective": objective,
            "status": "PAUSED",
            "special_ad_categories": [],
        })
        meta_campaign_id = result["id"]

        # Store in local DB
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO meta_ads_campaigns
                    (meta_campaign_id, campaign_objective, name, status, daily_budget_cents, metadata)
                VALUES ($1, $2, $3, 'paused', $4, $5::jsonb)
                """,
                meta_campaign_id, objective, name, daily_budget_cents,
                json.dumps({"ad_account_id": ad_account_id}),
            )

        logger.info("Meta campaign created", org_id=org_id, campaign_id=meta_campaign_id, name=name)
        return {"meta_campaign_id": meta_campaign_id, "name": name, "status": "paused"}

    async def create_ad_set(
        self, org_id: str, campaign_id: str, name: str,
        daily_budget_cents: int,
        interests: Optional[list[dict]] = None,
        age_min: int = 18, age_max: int = 65,
        genders: Optional[list[int]] = None,
        geo_latitude: Optional[float] = None,
        geo_longitude: Optional[float] = None,
        geo_radius_miles: Optional[int] = None,
    ) -> dict:
        """Create an ad set with targeting within a campaign."""
        ad_account_id = await self._get_ad_account_id(org_id)

        targeting = {
            "age_min": age_min,
            "age_max": age_max,
        }
        if genders:
            targeting["genders"] = genders
        if interests:
            targeting["flexible_spec"] = [{"interests": interests}]
        if geo_latitude and geo_longitude:
            targeting["geo_locations"] = {
                "custom_locations": [{
                    "latitude": geo_latitude,
                    "longitude": geo_longitude,
                    "radius": geo_radius_miles or 15,
                    "distance_unit": "mile",
                }]
            }

        result = await self._api_call(org_id, "POST", f"{ad_account_id}/adsets", {
            "name": name,
            "campaign_id": campaign_id,
            "daily_budget": daily_budget_cents,  # Meta uses cents
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "LEAD_GENERATION",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "targeting": targeting,
            "status": "PAUSED",
        })
        return {"ad_set_id": result["id"], "name": name}

    async def create_ad_creative(
        self, org_id: str, page_id: str,
        headline: str, body_text: str,
        link_url: str, call_to_action: str = "LEARN_MORE",
        description: Optional[str] = None,
    ) -> dict:
        """Create an ad creative for Facebook/Instagram feed."""
        ad_account_id = await self._get_ad_account_id(org_id)

        link_data = {
            "link": link_url,
            "message": body_text,
            "name": headline,
            "call_to_action": {"type": call_to_action},
        }
        if description:
            link_data["description"] = description

        result = await self._api_call(org_id, "POST", f"{ad_account_id}/adcreatives", {
            "name": f"Creative: {headline[:40]}",
            "object_story_spec": {
                "page_id": page_id,
                "link_data": link_data,
            },
        })
        return {"creative_id": result["id"], "headline": headline}

    async def create_ad(
        self, org_id: str, ad_set_id: str, creative_id: str, name: str,
    ) -> dict:
        """Create an ad linking an ad set to a creative."""
        ad_account_id = await self._get_ad_account_id(org_id)

        result = await self._api_call(org_id, "POST", f"{ad_account_id}/ads", {
            "name": name,
            "adset_id": ad_set_id,
            "creative": {"creative_id": creative_id},
            "status": "PAUSED",
        })
        return {"ad_id": result["id"], "name": name}

    async def update_campaign_status(self, org_id: str, meta_campaign_id: str, status: str) -> dict:
        """Update a campaign's status (ACTIVE, PAUSED, DELETED)."""
        await self._api_call(org_id, "POST", meta_campaign_id, {"status": status})

        status_map = {"ACTIVE": "active", "PAUSED": "paused", "DELETED": "removed"}
        local_status = status_map.get(status, status.lower())
        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE meta_ads_campaigns SET status = $1, updated_at = NOW() WHERE meta_campaign_id = $2",
                local_status, meta_campaign_id,
            )
        return {"meta_campaign_id": meta_campaign_id, "status": local_status}

    async def update_ad_set_budget(self, org_id: str, ad_set_id: str, daily_budget_cents: int) -> dict:
        """Update an ad set's daily budget."""
        await self._api_call(org_id, "POST", ad_set_id, {"daily_budget": daily_budget_cents})
        return {"ad_set_id": ad_set_id, "daily_budget_cents": daily_budget_cents}

    async def update_ad_set_targeting(self, org_id: str, ad_set_id: str, targeting: dict) -> dict:
        """Update an ad set's targeting."""
        await self._api_call(org_id, "POST", ad_set_id, {"targeting": targeting})
        return {"ad_set_id": ad_set_id, "targeting_updated": True}

    async def pause_all_campaigns(self, org_id: str) -> int:
        """Pause all active campaigns for this org."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                "SELECT meta_campaign_id FROM meta_ads_campaigns WHERE status = 'active'"
            )
        paused = 0
        for row in rows:
            try:
                await self.update_campaign_status(org_id, row["meta_campaign_id"], "PAUSED")
                paused += 1
            except Exception as e:
                logger.error("Failed to pause Meta campaign", campaign_id=row["meta_campaign_id"], error=str(e))
        return paused

    # ── Interest & Audience Management ─────────────────────────────────────────

    async def search_interests(self, org_id: str, query: str) -> list[dict]:
        """Search for targeting interests by keyword."""
        result = await self._api_call(org_id, "GET", "search", params={
            "type": "adinterest",
            "q": query,
        })
        return [
            {"id": item["id"], "name": item["name"], "audience_size": item.get("audience_size", 0)}
            for item in result.get("data", [])
        ]

    async def create_custom_audience(self, org_id: str, name: str, emails: list[str]) -> dict:
        """Create a custom audience from hashed emails."""
        ad_account_id = await self._get_ad_account_id(org_id)
        hashed = [hashlib.sha256(e.strip().lower().encode()).hexdigest() for e in emails]

        result = await self._api_call(org_id, "POST", f"{ad_account_id}/customaudiences", {
            "name": name,
            "subtype": "CUSTOM",
            "customer_file_source": "USER_PROVIDED_ONLY",
        })
        audience_id = result["id"]

        # Upload hashed emails
        await self._api_call(org_id, "POST", f"{audience_id}/users", {
            "payload": {"schema": ["EMAIL_SHA256"], "data": [[h] for h in hashed]},
        })
        return {"audience_id": audience_id, "name": name, "users_added": len(hashed)}

    async def create_lookalike_audience(self, org_id: str, source_audience_id: str, ratio: float = 0.01) -> dict:
        """Create a lookalike audience from a source audience."""
        ad_account_id = await self._get_ad_account_id(org_id)

        result = await self._api_call(org_id, "POST", f"{ad_account_id}/customaudiences", {
            "name": f"Lookalike ({int(ratio * 100)}%) from {source_audience_id}",
            "subtype": "LOOKALIKE",
            "origin_audience_id": source_audience_id,
            "lookalike_spec": json.dumps({
                "ratio": ratio,
                "country": "US",
            }),
        })
        return {"audience_id": result["id"], "ratio": ratio}

    # ── Metrics & Reporting (Insights API) ────────────────────────────────────

    async def get_campaign_performance(
        self, org_id: str, date_from: str, date_to: str,
    ) -> list[dict]:
        """Get campaign performance metrics for a date range."""
        ad_account_id = await self._get_ad_account_id(org_id)
        if not ad_account_id:
            return []

        result = await self._api_call(org_id, "GET", f"{ad_account_id}/insights", params={
            "level": "campaign",
            "fields": "campaign_id,campaign_name,impressions,reach,clicks,actions,spend,ctr,cpm,cpc,frequency,cost_per_action_type",
            "time_range": json.dumps({"since": date_from, "until": date_to}),
            "time_increment": 1,
        })

        results = []
        for row in result.get("data", []):
            conversions = 0
            actions = row.get("actions", [])
            for a in actions:
                if a.get("action_type") in ("lead", "offsite_conversion.fb_pixel_lead", "omni_complete_registration"):
                    conversions += int(a.get("value", 0))

            results.append({
                "campaign_id": row.get("campaign_id"),
                "campaign_name": row.get("campaign_name"),
                "date": row.get("date_start"),
                "impressions": int(row.get("impressions", 0)),
                "reach": int(row.get("reach", 0)),
                "clicks": int(row.get("clicks", 0)),
                "conversions": conversions,
                "spend_cents": int(float(row.get("spend", 0)) * 100),
                "ctr": float(row.get("ctr", 0)),
                "cpm_cents": int(float(row.get("cpm", 0)) * 100),
                "cpc_cents": int(float(row.get("cpc", 0)) * 100),
                "frequency": float(row.get("frequency", 0)),
                "actions_json": actions,
                "cost_per_action_json": row.get("cost_per_action_type", []),
            })
        return results

    async def get_ad_set_performance(self, org_id: str, date_from: str, date_to: str) -> list[dict]:
        """Get ad set level performance metrics."""
        ad_account_id = await self._get_ad_account_id(org_id)
        if not ad_account_id:
            return []

        result = await self._api_call(org_id, "GET", f"{ad_account_id}/insights", params={
            "level": "adset",
            "fields": "adset_id,adset_name,impressions,reach,clicks,actions,spend,ctr,frequency",
            "time_range": json.dumps({"since": date_from, "until": date_to}),
        })

        results = []
        for row in result.get("data", []):
            results.append({
                "ad_set_id": row.get("adset_id"),
                "ad_set_name": row.get("adset_name"),
                "impressions": int(row.get("impressions", 0)),
                "reach": int(row.get("reach", 0)),
                "clicks": int(row.get("clicks", 0)),
                "spend_cents": int(float(row.get("spend", 0)) * 100),
                "ctr": float(row.get("ctr", 0)),
                "frequency": float(row.get("frequency", 0)),
            })
        return results

    async def get_monthly_spend(self, org_id: str) -> dict:
        """Get total spend for the current calendar month."""
        now = datetime.now(timezone.utc)
        first_of_month = now.strftime("%Y-%m-01")
        today = now.strftime("%Y-%m-%d")

        ad_account_id = await self._get_ad_account_id(org_id)
        if not ad_account_id:
            return {"month": now.strftime("%Y-%m"), "spend_cents": 0}

        result = await self._api_call(org_id, "GET", f"{ad_account_id}/insights", params={
            "fields": "spend",
            "time_range": json.dumps({"since": first_of_month, "until": today}),
        })

        total_cents = 0
        for row in result.get("data", []):
            total_cents += int(float(row.get("spend", 0)) * 100)

        return {"month": now.strftime("%Y-%m"), "spend_cents": total_cents}

    # ── Budget Safety ─────────────────────────────────────────────────────────

    async def check_budget_remaining(self, org_id: str) -> dict:
        """Check how much budget remains before hitting the monthly cap."""
        config = await self.get_config(org_id)
        if not config:
            return {"remaining_cents": 0, "over_budget": True}

        max_monthly = config.get("max_monthly_spend_cents", 50000)
        spend = await self.get_monthly_spend(org_id)
        spent_cents = spend["spend_cents"]
        remaining = max(0, max_monthly - spent_cents)

        return {
            "max_monthly_cents": max_monthly,
            "spent_cents": spent_cents,
            "remaining_cents": remaining,
            "utilization_pct": round(spent_cents / max_monthly * 100, 1) if max_monthly > 0 else 100,
            "over_budget": spent_cents >= max_monthly,
        }

    # ── Metrics Sync (from Meta → local DB) ──────────────────────────────────

    async def sync_performance_metrics(self, org_id: str, date: str) -> int:
        """Sync campaign performance from Meta Insights into local meta_ads_performance table."""
        metrics = await self.get_campaign_performance(org_id, date, date)
        synced = 0

        async with get_tenant_db() as db:
            for m in metrics:
                campaign_row = await db.fetchrow(
                    "SELECT id FROM meta_ads_campaigns WHERE meta_campaign_id = $1",
                    str(m["campaign_id"]),
                )
                if not campaign_row:
                    continue

                roas = 0.0
                if m["spend_cents"] > 0:
                    # Estimate ROAS from conversion value (simplified)
                    roas = m["conversions"] * 5000 / m["spend_cents"] if m["conversions"] > 0 else 0

                await db.execute(
                    """
                    INSERT INTO meta_ads_performance
                        (campaign_id, date, impressions, reach, clicks, conversions,
                         spend_cents, ctr, cpm_cents, cpc_cents, frequency,
                         actions_json, cost_per_action_json, roas)
                    VALUES ($1, $2::date, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13::jsonb, $14)
                    ON CONFLICT (campaign_id, date) DO UPDATE SET
                        impressions = EXCLUDED.impressions,
                        reach = EXCLUDED.reach,
                        clicks = EXCLUDED.clicks,
                        conversions = EXCLUDED.conversions,
                        spend_cents = EXCLUDED.spend_cents,
                        ctr = EXCLUDED.ctr,
                        cpm_cents = EXCLUDED.cpm_cents,
                        cpc_cents = EXCLUDED.cpc_cents,
                        frequency = EXCLUDED.frequency,
                        actions_json = EXCLUDED.actions_json,
                        cost_per_action_json = EXCLUDED.cost_per_action_json,
                        roas = EXCLUDED.roas
                    """,
                    str(campaign_row["id"]), date,
                    m["impressions"], m["reach"], m["clicks"], m["conversions"],
                    m["spend_cents"], m["ctr"], m["cpm_cents"], m["cpc_cents"],
                    m["frequency"],
                    json.dumps(m["actions_json"]), json.dumps(m["cost_per_action_json"]),
                    roas,
                )
                synced += 1

        return synced

    # ── Conversions API (CAPI) ───────────────────────────────────────────────

    async def send_conversion_events(self, org_id: str, pixel_id: str, events: list[dict]) -> dict:
        """Upload server-side conversion events via Conversions API."""
        if not events:
            return {"uploaded": 0}

        result = await self._api_call(org_id, "POST", f"{pixel_id}/events", {
            "data": events,
        })
        return {"uploaded": len(events), "events_received": result.get("events_received", 0)}

    # ── Local DB Queries (Dashboard) ──────────────────────────────────────────

    async def list_campaigns(self) -> list[dict]:
        """List all campaigns from local DB with latest metrics."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT c.*,
                       p.impressions AS latest_impressions,
                       p.reach AS latest_reach,
                       p.clicks AS latest_clicks,
                       p.conversions AS latest_conversions,
                       p.spend_cents AS latest_spend_cents,
                       p.frequency AS latest_frequency,
                       p.roas AS latest_roas
                FROM meta_ads_campaigns c
                LEFT JOIN LATERAL (
                    SELECT impressions, reach, clicks, conversions, spend_cents, frequency, roas
                    FROM meta_ads_performance
                    WHERE campaign_id = c.id
                    ORDER BY date DESC LIMIT 1
                ) p ON TRUE
                ORDER BY c.created_at DESC
                """
            )
        results = []
        for r in rows:
            d = dict(r)
            for k in ("id",):
                if d.get(k):
                    d[k] = str(d[k])
            for k in ("created_at", "updated_at"):
                if d.get(k):
                    d[k] = d[k].isoformat()
            results.append(d)
        return results

    async def get_performance_summary(self, days: int = 30) -> dict:
        """Get aggregate performance summary from local DB."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT COALESCE(SUM(impressions), 0) AS total_impressions,
                       COALESCE(SUM(reach), 0) AS total_reach,
                       COALESCE(SUM(clicks), 0) AS total_clicks,
                       COALESCE(SUM(conversions), 0) AS total_conversions,
                       COALESCE(SUM(spend_cents), 0) AS total_spend_cents
                FROM meta_ads_performance
                WHERE date >= CURRENT_DATE - $1::int
                """,
                days,
            )
        total_spend = row["total_spend_cents"]
        total_clicks = row["total_clicks"]
        total_conversions = float(row["total_conversions"])
        cost_per_lead_cents = int(total_spend / total_conversions) if total_conversions > 0 else 0

        return {
            "days": days,
            "impressions": row["total_impressions"],
            "reach": row["total_reach"],
            "clicks": total_clicks,
            "conversions": total_conversions,
            "spend_cents": total_spend,
            "ctr": round(total_clicks / row["total_impressions"] * 100, 2) if row["total_impressions"] > 0 else 0,
            "cost_per_lead_cents": cost_per_lead_cents,
            "roas": round(total_conversions * 5000 / total_spend, 2) if total_spend > 0 else 0,
        }

    async def get_daily_performance(self, days: int = 30) -> list[dict]:
        """Get daily performance time series from local DB."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT date,
                       SUM(impressions) AS impressions,
                       SUM(reach) AS reach,
                       SUM(clicks) AS clicks,
                       SUM(conversions) AS conversions,
                       SUM(spend_cents) AS spend_cents,
                       AVG(frequency) AS avg_frequency
                FROM meta_ads_performance
                WHERE date >= CURRENT_DATE - $1::int
                GROUP BY date
                ORDER BY date ASC
                """,
                days,
            )
        return [
            {
                "date": r["date"].isoformat(),
                "impressions": r["impressions"],
                "reach": r["reach"],
                "clicks": r["clicks"],
                "conversions": float(r["conversions"]),
                "spend_cents": r["spend_cents"],
                "frequency": round(float(r["avg_frequency"] or 0), 2),
                "roas": round(float(r["conversions"]) * 5000 / r["spend_cents"], 2) if r["spend_cents"] > 0 else 0,
            }
            for r in rows
        ]

    # ── AI Actions Audit Trail ────────────────────────────────────────────────

    async def log_ai_action(
        self, action_type: str, description: str, reasoning: str,
        changes: dict, requires_approval: bool = False,
    ) -> str:
        """Log an AI action to the audit trail. Returns the action ID."""
        status = "proposed" if requires_approval else "executed"
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO meta_ads_ai_actions
                    (action_type, description, reasoning, changes_json, status, requires_approval)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                RETURNING id
                """,
                action_type, description, reasoning,
                json.dumps(changes), status, requires_approval,
            )
        return str(row["id"])

    async def list_ai_actions(self, status: Optional[str] = None, limit: int = 50) -> list[dict]:
        """List AI actions, optionally filtered by status."""
        async with get_tenant_db() as db:
            if status:
                rows = await db.fetch(
                    "SELECT * FROM meta_ads_ai_actions WHERE status = $1 ORDER BY created_at DESC LIMIT $2",
                    status, limit,
                )
            else:
                rows = await db.fetch(
                    "SELECT * FROM meta_ads_ai_actions ORDER BY created_at DESC LIMIT $1",
                    limit,
                )
        results = []
        for r in rows:
            d = dict(r)
            for k in ("id",):
                if d.get(k):
                    d[k] = str(d[k])
            for k in ("created_at",):
                if d.get(k):
                    d[k] = d[k].isoformat()
            results.append(d)
        return results

    async def approve_action(self, action_id: str) -> dict:
        """Approve a pending AI action."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE meta_ads_ai_actions
                SET status = 'approved', approved_at = NOW()
                WHERE id = $1 AND status = 'proposed'
                RETURNING id, action_type, changes_json
                """,
                action_id,
            )
        if not row:
            raise ValueError("Action not found or not in proposed status")
        return {"id": str(row["id"]), "action_type": row["action_type"], "status": "approved"}

    async def reject_action(self, action_id: str) -> dict:
        """Reject a pending AI action."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE meta_ads_ai_actions
                SET status = 'rejected'
                WHERE id = $1 AND status = 'proposed'
                RETURNING id
                """,
                action_id,
            )
        if not row:
            raise ValueError("Action not found or not in proposed status")
        return {"id": str(row["id"]), "status": "rejected"}
