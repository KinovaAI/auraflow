"""AuraFlow — Google Ads Service

API wrapper for Google Ads management. Handles OAuth, campaign CRUD,
keyword management, metrics reporting, and budget safety checks.
Follows the same patterns as youtube_service.py for OAuth + credential encryption.
"""
import json
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.utils.encryption import encrypt_credential, decrypt_credential

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"
GOOGLE_ADS_API_VERSION = "v18"
GOOGLE_ADS_BASE = f"https://googleads.googleapis.com/{GOOGLE_ADS_API_VERSION}"


class GoogleAdsService:
    """Manages Google Ads API interactions for a single tenant/organization."""

    async def _get_platform_creds(self) -> dict:
        """DB-first credential lookup with env var fallback."""
        try:
            from app.services.platform.platform_config_service import PlatformConfigService
            return await PlatformConfigService().get_raw_google_credentials()
        except Exception:
            return {
                "google_client_id": settings.GOOGLE_CLIENT_ID,
                "google_client_secret": settings.GOOGLE_CLIENT_SECRET,
                "google_ads_developer_token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                "google_ads_login_customer_id": settings.GOOGLE_ADS_LOGIN_CUSTOMER_ID,
            }

    # ── OAuth 2.0 ─────────────────────────────────────────────────────────────

    async def get_oauth_url(self, org_id: str) -> str:
        """Generate Google OAuth consent URL for Google Ads authorization."""
        creds = await self._get_platform_creds()
        params = {
            "client_id": creds.get("google_client_id") or settings.GOOGLE_CLIENT_ID,
            "redirect_uri": f"{settings.API_URL}/api/v1/google-ads/connect/oauth/callback",
            "response_type": "code",
            "scope": GOOGLE_ADS_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": org_id,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def handle_oauth_callback(self, org_id: str, code: str) -> dict:
        """Exchange authorization code for tokens and store encrypted refresh token."""
        creds = await self._get_platform_creds()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": creds.get("google_client_id") or settings.GOOGLE_CLIENT_ID,
                    "client_secret": creds.get("google_client_secret") or settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": f"{settings.API_URL}/api/v1/google-ads/connect/oauth/callback",
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                error = resp.json().get("error_description", "OAuth token exchange failed")
                raise ValueError(error)

            tokens = resp.json()
            refresh_token = tokens.get("refresh_token")
            if not refresh_token:
                raise ValueError("No refresh token received — try revoking access and re-authorizing")

        async with get_global_db() as db:
            encrypted = await encrypt_credential(db, refresh_token)
            await db.execute(
                """
                UPDATE af_global.organizations
                SET google_ads_refresh_token_encrypted = $1,
                    google_ads_connected_at = NOW(),
                    updated_at = NOW()
                WHERE id = $2
                """,
                encrypted, org_id,
            )

        logger.info("Google Ads OAuth authorized", org_id=org_id)
        return {"authorized": True}

    async def get_connection_status(self, org_id: str) -> dict:
        """Check if Google Ads is connected for this org."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT google_ads_customer_id, google_ads_connected_at,
                       google_ads_refresh_token_encrypted IS NOT NULL AS has_token
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
        if not row:
            return {"connected": False}
        return {
            "connected": bool(row["has_token"]),
            "customer_id": row["google_ads_customer_id"],
            "connected_at": row["google_ads_connected_at"].isoformat() if row["google_ads_connected_at"] else None,
        }

    async def set_customer_id(self, org_id: str, customer_id: str) -> None:
        """Store the Google Ads customer ID for this org."""
        # Normalize: remove dashes
        customer_id = customer_id.replace("-", "")
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET google_ads_customer_id = $1, updated_at = NOW()
                WHERE id = $2
                """,
                customer_id, org_id,
            )

    async def disconnect(self, org_id: str) -> None:
        """Disconnect Google Ads — clear credentials and pause all campaigns."""
        # Pause all active campaigns first
        await self.pause_all_campaigns(org_id)

        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET google_ads_customer_id = NULL,
                    google_ads_refresh_token_encrypted = NULL,
                    google_ads_connected_at = NULL,
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id,
            )
        logger.info("Google Ads disconnected", org_id=org_id)

    # ── Credential Helpers ────────────────────────────────────────────────────

    async def _get_refresh_token(self, org_id: str) -> Optional[str]:
        """Get decrypted refresh token for an org."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT google_ads_refresh_token_encrypted FROM af_global.organizations WHERE id = $1",
                org_id,
            )
            if not row or not row["google_ads_refresh_token_encrypted"]:
                return None
            return await decrypt_credential(db, row["google_ads_refresh_token_encrypted"])

    async def _get_customer_id(self, org_id: str) -> Optional[str]:
        """Get Google Ads customer ID for an org."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT google_ads_customer_id FROM af_global.organizations WHERE id = $1",
                org_id,
            )
        return row["google_ads_customer_id"] if row else None

    async def _get_access_token(self, refresh_token: str) -> str:
        """Use refresh token to get a fresh access token."""
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
                raise ValueError("Failed to refresh Google Ads access token")
            return resp.json()["access_token"]

    def _headers(self, access_token: str, customer_id: str) -> dict:
        """Build standard headers for Google Ads REST API calls."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": settings.GOOGLE_ADS_DEVELOPER_TOKEN or "",
            "Content-Type": "application/json",
        }
        if settings.GOOGLE_ADS_LOGIN_CUSTOMER_ID:
            headers["login-customer-id"] = settings.GOOGLE_ADS_LOGIN_CUSTOMER_ID
        return headers

    async def _api_call(
        self, org_id: str, method: str, endpoint: str,
        body: Optional[dict] = None,
    ) -> dict:
        """Make an authenticated Google Ads REST API call."""
        refresh_token = await self._get_refresh_token(org_id)
        if not refresh_token:
            raise ValueError("Google Ads not connected — complete OAuth setup first")

        customer_id = await self._get_customer_id(org_id)
        if not customer_id:
            raise ValueError("Google Ads customer ID not set")

        access_token = await self._get_access_token(refresh_token)
        headers = self._headers(access_token, customer_id)
        url = f"{GOOGLE_ADS_BASE}/customers/{customer_id}/{endpoint}"

        async with httpx.AsyncClient() as client:
            if method == "GET":
                resp = await client.get(url, headers=headers, timeout=30)
            elif method == "POST":
                resp = await client.post(url, headers=headers, json=body or {}, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

        if resp.status_code not in (200, 201):
            error_detail = resp.text[:500]
            logger.error("Google Ads API error", status=resp.status_code, detail=error_detail, endpoint=endpoint)
            raise ValueError(f"Google Ads API error ({resp.status_code}): {error_detail}")

        return resp.json()

    async def _gaql_query(self, org_id: str, query: str) -> list[dict]:
        """Execute a GAQL (Google Ads Query Language) query."""
        result = await self._api_call(org_id, "POST", "googleAds:searchStream", {"query": query})
        rows = []
        for batch in result if isinstance(result, list) else [result]:
            for r in batch.get("results", []):
                rows.append(r)
        return rows

    # ── Config (Tenant-Level Settings) ────────────────────────────────────────

    async def get_config(self, org_id: str) -> Optional[dict]:
        """Get Google Ads config for this tenant."""
        async with get_tenant_db() as db:
            row = await db.fetchrow("SELECT * FROM google_ads_config LIMIT 1")
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
        """Create or update the Google Ads config for this tenant."""
        async with get_tenant_db() as db:
            existing = await db.fetchrow("SELECT id FROM google_ads_config LIMIT 1")
            if existing:
                await db.execute(
                    """
                    UPDATE google_ads_config SET
                        max_monthly_spend_cents = COALESCE($1, max_monthly_spend_cents),
                        target_latitude = COALESCE($2, target_latitude),
                        target_longitude = COALESCE($3, target_longitude),
                        target_radius_miles = COALESCE($4, target_radius_miles),
                        target_locations = COALESCE($5, target_locations),
                        class_focus = COALESCE($6, class_focus),
                        brand_voice = COALESCE($7, brand_voice),
                        negative_keywords = COALESCE($8, negative_keywords),
                        approval_threshold_cents = COALESCE($9, approval_threshold_cents),
                        is_active = COALESCE($10, is_active),
                        updated_at = NOW()
                    WHERE id = $11
                    """,
                    config_data.get("max_monthly_spend_cents"),
                    config_data.get("target_latitude"),
                    config_data.get("target_longitude"),
                    config_data.get("target_radius_miles"),
                    config_data.get("target_locations"),
                    config_data.get("class_focus"),
                    config_data.get("brand_voice"),
                    config_data.get("negative_keywords"),
                    config_data.get("approval_threshold_cents"),
                    config_data.get("is_active"),
                    str(existing["id"]),
                )
                config_id = str(existing["id"])
            else:
                row = await db.fetchrow(
                    """
                    INSERT INTO google_ads_config
                        (max_monthly_spend_cents, target_latitude, target_longitude,
                         target_radius_miles, target_locations, class_focus,
                         brand_voice, negative_keywords, approval_threshold_cents, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING id
                    """,
                    config_data.get("max_monthly_spend_cents", 50000),
                    config_data.get("target_latitude"),
                    config_data.get("target_longitude"),
                    config_data.get("target_radius_miles", 15),
                    config_data.get("target_locations"),
                    config_data.get("class_focus"),
                    config_data.get("brand_voice"),
                    config_data.get("negative_keywords"),
                    config_data.get("approval_threshold_cents", 10000),
                    config_data.get("is_active", False),
                )
                config_id = str(row["id"])

        return await self.get_config(None) or {"id": config_id}

    # ── Campaign CRUD ─────────────────────────────────────────────────────────

    async def create_search_campaign(
        self, org_id: str, name: str, daily_budget_cents: int,
        location_ids: Optional[list[int]] = None,
        proximity: Optional[dict] = None,
    ) -> dict:
        """Create a Google Ads Search campaign with location targeting."""
        customer_id = await self._get_customer_id(org_id)

        # 1. Create campaign budget
        budget_result = await self._api_call(org_id, "POST", "campaignBudgets:mutate", {
            "operations": [{
                "create": {
                    "name": f"{name} Budget",
                    "amountMicros": str(daily_budget_cents * 10000),  # cents → micros
                    "deliveryMethod": "STANDARD",
                }
            }]
        })
        budget_resource = budget_result["results"][0]["resourceName"]

        # 2. Create campaign
        campaign_op = {
            "create": {
                "name": name,
                "advertisingChannelType": "SEARCH",
                "status": "PAUSED",
                "campaignBudget": budget_resource,
                "biddingStrategyType": "MAXIMIZE_CLICKS",
                "networkSettings": {
                    "targetGoogleSearch": True,
                    "targetSearchNetwork": True,
                    "targetContentNetwork": False,
                },
                "startDate": datetime.now(timezone.utc).strftime("%Y%m%d"),
            }
        }
        campaign_result = await self._api_call(org_id, "POST", "campaigns:mutate", {
            "operations": [campaign_op]
        })
        campaign_resource = campaign_result["results"][0]["resourceName"]
        google_campaign_id = campaign_resource.split("/")[-1]

        # 3. Add location targeting if provided
        if proximity:
            await self._set_proximity_targeting(org_id, campaign_resource, proximity)
        elif location_ids:
            await self._set_location_targeting(org_id, campaign_resource, location_ids)

        # 4. Store in our DB
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO google_ads_campaigns
                    (google_campaign_id, campaign_type, name, status, daily_budget_cents,
                     bidding_strategy, metadata)
                VALUES ($1, 'search', $2, 'paused', $3, 'MAXIMIZE_CLICKS', $4::jsonb)
                """,
                google_campaign_id, name, daily_budget_cents,
                json.dumps({"budget_resource": budget_resource, "campaign_resource": campaign_resource}),
            )

        logger.info("Search campaign created", org_id=org_id, campaign_id=google_campaign_id, name=name)
        return {"google_campaign_id": google_campaign_id, "name": name, "status": "paused"}

    async def _set_proximity_targeting(
        self, org_id: str, campaign_resource: str, proximity: dict
    ) -> None:
        """Set radius-based geo targeting on a campaign."""
        await self._api_call(org_id, "POST", "campaignCriteria:mutate", {
            "operations": [{
                "create": {
                    "campaign": campaign_resource,
                    "proximity": {
                        "geoPoint": {
                            "latitudeInMicroDegrees": int(proximity["latitude"] * 1_000_000),
                            "longitudeInMicroDegrees": int(proximity["longitude"] * 1_000_000),
                        },
                        "radius": proximity.get("radius_miles", 15),
                        "radiusUnits": "MILES",
                    },
                }
            }]
        })

    async def _set_location_targeting(
        self, org_id: str, campaign_resource: str, location_ids: list[int]
    ) -> None:
        """Set geo location targeting on a campaign."""
        operations = []
        for loc_id in location_ids:
            operations.append({
                "create": {
                    "campaign": campaign_resource,
                    "location": {"geoTargetConstant": f"geoTargetConstants/{loc_id}"},
                }
            })
        if operations:
            await self._api_call(org_id, "POST", "campaignCriteria:mutate", {"operations": operations})

    async def update_campaign_status(self, org_id: str, google_campaign_id: str, status: str) -> dict:
        """Update a campaign's status (ENABLED, PAUSED, REMOVED)."""
        customer_id = await self._get_customer_id(org_id)
        resource_name = f"customers/{customer_id}/campaigns/{google_campaign_id}"

        await self._api_call(org_id, "POST", "campaigns:mutate", {
            "operations": [{
                "update": {
                    "resourceName": resource_name,
                    "status": status,
                },
                "updateMask": "status",
            }]
        })

        # Update local record
        status_map = {"ENABLED": "active", "PAUSED": "paused", "REMOVED": "removed"}
        local_status = status_map.get(status, status.lower())
        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE google_ads_campaigns SET status = $1, updated_at = NOW() WHERE google_campaign_id = $2",
                local_status, google_campaign_id,
            )

        return {"google_campaign_id": google_campaign_id, "status": local_status}

    async def update_campaign_budget(self, org_id: str, google_campaign_id: str, daily_budget_cents: int) -> dict:
        """Update a campaign's daily budget."""
        # Get the budget resource from metadata
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT metadata FROM google_ads_campaigns WHERE google_campaign_id = $1",
                google_campaign_id,
            )
        if not row or not row["metadata"]:
            raise ValueError("Campaign not found in local database")

        metadata = row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"])
        budget_resource = metadata.get("budget_resource")
        if not budget_resource:
            raise ValueError("Budget resource not found — campaign may need re-creation")

        await self._api_call(org_id, "POST", "campaignBudgets:mutate", {
            "operations": [{
                "update": {
                    "resourceName": budget_resource,
                    "amountMicros": str(daily_budget_cents * 10000),
                },
                "updateMask": "amountMicros",
            }]
        })

        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE google_ads_campaigns SET daily_budget_cents = $1, updated_at = NOW() WHERE google_campaign_id = $2",
                daily_budget_cents, google_campaign_id,
            )

        return {"google_campaign_id": google_campaign_id, "daily_budget_cents": daily_budget_cents}

    async def update_bidding_strategy(self, org_id: str, google_campaign_id: str, strategy: str, target_roas: Optional[float] = None) -> dict:
        """Update a campaign's bidding strategy."""
        customer_id = await self._get_customer_id(org_id)
        resource_name = f"customers/{customer_id}/campaigns/{google_campaign_id}"

        update_data = {"resourceName": resource_name, "biddingStrategyType": strategy}
        mask_fields = ["biddingStrategyType"]

        if strategy == "TARGET_ROAS" and target_roas:
            update_data["targetRoas"] = {"targetRoas": target_roas}
            mask_fields.append("targetRoas")

        await self._api_call(org_id, "POST", "campaigns:mutate", {
            "operations": [{
                "update": update_data,
                "updateMask": ",".join(mask_fields),
            }]
        })

        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE google_ads_campaigns SET bidding_strategy = $1, target_roas = $2, updated_at = NOW() WHERE google_campaign_id = $3",
                strategy, target_roas, google_campaign_id,
            )

        return {"google_campaign_id": google_campaign_id, "strategy": strategy, "target_roas": target_roas}

    async def pause_all_campaigns(self, org_id: str) -> int:
        """Pause all active campaigns for this org."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                "SELECT google_campaign_id FROM google_ads_campaigns WHERE status = 'active'"
            )
        paused = 0
        for row in rows:
            try:
                await self.update_campaign_status(org_id, row["google_campaign_id"], "PAUSED")
                paused += 1
            except Exception as e:
                logger.error("Failed to pause campaign", campaign_id=row["google_campaign_id"], error=str(e))
        return paused

    # ── Ad Groups & Ads ───────────────────────────────────────────────────────

    async def create_ad_group(
        self, org_id: str, google_campaign_id: str, name: str,
        cpc_bid_micros: int = 2_000_000,
    ) -> dict:
        """Create an ad group within a campaign."""
        customer_id = await self._get_customer_id(org_id)
        campaign_resource = f"customers/{customer_id}/campaigns/{google_campaign_id}"

        result = await self._api_call(org_id, "POST", "adGroups:mutate", {
            "operations": [{
                "create": {
                    "name": name,
                    "campaign": campaign_resource,
                    "status": "ENABLED",
                    "type": "SEARCH_STANDARD",
                    "cpcBidMicros": str(cpc_bid_micros),
                }
            }]
        })
        ad_group_resource = result["results"][0]["resourceName"]
        ad_group_id = ad_group_resource.split("/")[-1]
        return {"ad_group_id": ad_group_id, "resource": ad_group_resource, "name": name}

    async def create_responsive_search_ad(
        self, org_id: str, ad_group_resource: str,
        headlines: list[str], descriptions: list[str],
        final_url: str,
    ) -> dict:
        """Create a responsive search ad in an ad group."""
        headline_assets = [{"text": h, "pinnedField": "UNSPECIFIED"} for h in headlines[:15]]
        description_assets = [{"text": d, "pinnedField": "UNSPECIFIED"} for d in descriptions[:4]]

        result = await self._api_call(org_id, "POST", "adGroupAds:mutate", {
            "operations": [{
                "create": {
                    "adGroup": ad_group_resource,
                    "status": "ENABLED",
                    "ad": {
                        "responsiveSearchAd": {
                            "headlines": headline_assets,
                            "descriptions": description_assets,
                        },
                        "finalUrls": [final_url],
                    },
                }
            }]
        })
        ad_resource = result["results"][0]["resourceName"]
        return {"ad_resource": ad_resource}

    # ── Keywords ──────────────────────────────────────────────────────────────

    async def add_keywords(
        self, org_id: str, ad_group_resource: str,
        keywords: list[dict],
    ) -> dict:
        """Add keywords to an ad group. Each keyword: {text, match_type}."""
        operations = []
        for kw in keywords:
            operations.append({
                "create": {
                    "adGroup": ad_group_resource,
                    "status": "ENABLED",
                    "keyword": {
                        "text": kw["text"],
                        "matchType": kw.get("match_type", "BROAD"),
                    },
                }
            })

        if not operations:
            return {"added": 0}

        result = await self._api_call(org_id, "POST", "adGroupCriteria:mutate", {"operations": operations})
        return {"added": len(result.get("results", []))}

    async def remove_keywords(self, org_id: str, keyword_resources: list[str]) -> dict:
        """Remove keywords by resource name."""
        operations = [{"remove": r} for r in keyword_resources]
        if not operations:
            return {"removed": 0}
        result = await self._api_call(org_id, "POST", "adGroupCriteria:mutate", {"operations": operations})
        return {"removed": len(result.get("results", []))}

    async def get_keyword_suggestions(self, org_id: str, seed_keywords: list[str], url: Optional[str] = None) -> list[dict]:
        """Get keyword ideas from Google Ads Keyword Planner."""
        body = {
            "keywordSeed": {"keywords": seed_keywords},
            "language": "languageConstants/1000",  # English
            "includeAdultKeywords": False,
        }
        if url:
            body["urlSeed"] = {"url": url}

        try:
            result = await self._api_call(org_id, "POST", "generateKeywordIdeas", body)
            ideas = []
            for item in result.get("results", []):
                metrics = item.get("keywordIdeaMetrics", {})
                ideas.append({
                    "text": item.get("text", ""),
                    "avg_monthly_searches": metrics.get("avgMonthlySearches", 0),
                    "competition": metrics.get("competition", "UNSPECIFIED"),
                    "low_bid_micros": metrics.get("lowTopOfPageBidMicros", 0),
                    "high_bid_micros": metrics.get("highTopOfPageBidMicros", 0),
                })
            return ideas
        except Exception as e:
            logger.warning("Keyword suggestions failed", error=str(e))
            return []

    # ── Metrics & Reporting ───────────────────────────────────────────────────

    async def get_campaign_performance(
        self, org_id: str, date_from: str, date_to: str,
    ) -> list[dict]:
        """Get campaign performance metrics for a date range (YYYY-MM-DD)."""
        query = f"""
            SELECT campaign.id, campaign.name, campaign.status,
                   metrics.impressions, metrics.clicks, metrics.conversions,
                   metrics.cost_micros, metrics.conversions_value,
                   metrics.ctr, metrics.average_cpc,
                   segments.date
            FROM campaign
            WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
              AND campaign.status != 'REMOVED'
            ORDER BY segments.date DESC
        """
        rows = await self._gaql_query(org_id, query)

        results = []
        for r in rows:
            campaign = r.get("campaign", {})
            metrics = r.get("metrics", {})
            segments = r.get("segments", {})
            results.append({
                "campaign_id": campaign.get("id"),
                "campaign_name": campaign.get("name"),
                "status": campaign.get("status"),
                "date": segments.get("date"),
                "impressions": int(metrics.get("impressions", 0)),
                "clicks": int(metrics.get("clicks", 0)),
                "conversions": float(metrics.get("conversions", 0)),
                "cost_micros": int(metrics.get("costMicros", 0)),
                "conversion_value_micros": int(float(metrics.get("conversionsValue", 0)) * 1_000_000),
                "ctr": float(metrics.get("ctr", 0)),
                "average_cpc_micros": int(metrics.get("averageCpc", 0)),
            })
        return results

    async def get_keyword_performance(self, org_id: str, date_from: str, date_to: str) -> list[dict]:
        """Get keyword-level performance metrics."""
        query = f"""
            SELECT ad_group_criterion.keyword.text,
                   ad_group_criterion.keyword.match_type,
                   ad_group_criterion.status,
                   metrics.impressions, metrics.clicks, metrics.conversions,
                   metrics.cost_micros, metrics.ctr, metrics.average_cpc
            FROM keyword_view
            WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            ORDER BY metrics.cost_micros DESC
            LIMIT 100
        """
        rows = await self._gaql_query(org_id, query)

        results = []
        for r in rows:
            criterion = r.get("adGroupCriterion", {}).get("keyword", {})
            metrics = r.get("metrics", {})
            results.append({
                "keyword": criterion.get("text"),
                "match_type": criterion.get("matchType"),
                "impressions": int(metrics.get("impressions", 0)),
                "clicks": int(metrics.get("clicks", 0)),
                "conversions": float(metrics.get("conversions", 0)),
                "cost_micros": int(metrics.get("costMicros", 0)),
                "ctr": float(metrics.get("ctr", 0)),
            })
        return results

    async def get_search_terms_report(self, org_id: str, date_from: str, date_to: str) -> list[dict]:
        """Get search terms report — what users actually searched."""
        query = f"""
            SELECT search_term_view.search_term,
                   metrics.impressions, metrics.clicks, metrics.conversions,
                   metrics.cost_micros
            FROM search_term_view
            WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
            ORDER BY metrics.impressions DESC
            LIMIT 200
        """
        rows = await self._gaql_query(org_id, query)

        results = []
        for r in rows:
            stv = r.get("searchTermView", {})
            metrics = r.get("metrics", {})
            results.append({
                "search_term": stv.get("searchTerm"),
                "impressions": int(metrics.get("impressions", 0)),
                "clicks": int(metrics.get("clicks", 0)),
                "conversions": float(metrics.get("conversions", 0)),
                "cost_micros": int(metrics.get("costMicros", 0)),
            })
        return results

    async def get_monthly_spend(self, org_id: str) -> dict:
        """Get total spend for the current calendar month."""
        now = datetime.now(timezone.utc)
        first_of_month = now.strftime("%Y-%m-01")
        today = now.strftime("%Y-%m-%d")

        query = f"""
            SELECT metrics.cost_micros
            FROM campaign
            WHERE segments.date BETWEEN '{first_of_month}' AND '{today}'
              AND campaign.status != 'REMOVED'
        """
        rows = await self._gaql_query(org_id, query)

        total_micros = sum(int(r.get("metrics", {}).get("costMicros", 0)) for r in rows)
        total_cents = total_micros // 10000

        return {
            "month": now.strftime("%Y-%m"),
            "spend_cents": total_cents,
            "spend_micros": total_micros,
        }

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

    # ── Metrics Sync (from Google → local DB) ─────────────────────────────────

    async def sync_performance_metrics(self, org_id: str, date: str) -> int:
        """Sync campaign performance from Google Ads into local google_ads_performance table."""
        metrics = await self.get_campaign_performance(org_id, date, date)
        synced = 0

        async with get_tenant_db() as db:
            for m in metrics:
                # Get our local campaign ID
                campaign_row = await db.fetchrow(
                    "SELECT id FROM google_ads_campaigns WHERE google_campaign_id = $1",
                    str(m["campaign_id"]),
                )
                if not campaign_row:
                    continue

                roas = 0.0
                if m["cost_micros"] > 0:
                    roas = m["conversion_value_micros"] / m["cost_micros"]

                await db.execute(
                    """
                    INSERT INTO google_ads_performance
                        (campaign_id, date, impressions, clicks, conversions,
                         cost_micros, conversion_value_micros, ctr, roas)
                    VALUES ($1, $2::date, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (campaign_id, date) DO UPDATE SET
                        impressions = EXCLUDED.impressions,
                        clicks = EXCLUDED.clicks,
                        conversions = EXCLUDED.conversions,
                        cost_micros = EXCLUDED.cost_micros,
                        conversion_value_micros = EXCLUDED.conversion_value_micros,
                        ctr = EXCLUDED.ctr,
                        roas = EXCLUDED.roas,
                        updated_at = NOW()
                    """,
                    str(campaign_row["id"]), date,
                    m["impressions"], m["clicks"], m["conversions"],
                    m["cost_micros"], m["conversion_value_micros"],
                    m["ctr"], roas,
                )
                synced += 1

        return synced

    # ── Conversion Tracking ───────────────────────────────────────────────────

    async def create_conversion_action(self, org_id: str, name: str, category: str = "PURCHASE") -> dict:
        """Create a conversion action in Google Ads."""
        result = await self._api_call(org_id, "POST", "conversionActions:mutate", {
            "operations": [{
                "create": {
                    "name": name,
                    "category": category,
                    "type": "UPLOAD_CLICKS",
                    "status": "ENABLED",
                    "countingType": "ONE_PER_CLICK",
                }
            }]
        })
        resource = result["results"][0]["resourceName"]
        return {"conversion_action_resource": resource, "name": name}

    async def upload_offline_conversions(self, org_id: str, conversions: list[dict]) -> dict:
        """Upload offline conversions (gclid-based) to Google Ads."""
        if not conversions:
            return {"uploaded": 0}

        operations = []
        for conv in conversions:
            operations.append({
                "create": {
                    "gclid": conv["gclid"],
                    "conversionAction": conv["conversion_action_resource"],
                    "conversionDateTime": conv["conversion_datetime"],
                    "conversionValue": conv.get("conversion_value", 0),
                    "currencyCode": "USD",
                }
            })

        try:
            result = await self._api_call(org_id, "POST", "conversionUploads:uploadClickConversions", {
                "conversions": [op["create"] for op in operations],
                "partialFailure": True,
            })
            return {"uploaded": len(conversions), "partial_failure_error": result.get("partialFailureError")}
        except Exception as e:
            logger.error("Conversion upload failed", org_id=org_id, error=str(e))
            return {"uploaded": 0, "error": str(e)}

    # ── Local DB Queries (Dashboard) ──────────────────────────────────────────

    async def list_campaigns(self) -> list[dict]:
        """List all campaigns from local DB with latest metrics."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT c.*,
                       p.impressions AS latest_impressions,
                       p.clicks AS latest_clicks,
                       p.conversions AS latest_conversions,
                       p.cost_micros AS latest_cost_micros,
                       p.roas AS latest_roas
                FROM google_ads_campaigns c
                LEFT JOIN LATERAL (
                    SELECT impressions, clicks, conversions, cost_micros, roas
                    FROM google_ads_performance
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
                       COALESCE(SUM(clicks), 0) AS total_clicks,
                       COALESCE(SUM(conversions), 0) AS total_conversions,
                       COALESCE(SUM(cost_micros), 0) AS total_cost_micros,
                       COALESCE(SUM(conversion_value_micros), 0) AS total_conversion_value_micros
                FROM google_ads_performance
                WHERE date >= CURRENT_DATE - $1::int
                """,
                days,
            )
        total_cost = row["total_cost_micros"]
        total_value = row["total_conversion_value_micros"]
        roas = total_value / total_cost if total_cost > 0 else 0

        total_clicks = row["total_clicks"]
        total_conversions = row["total_conversions"]
        cost_per_lead_cents = (total_cost // 10000 // total_conversions) if total_conversions > 0 else 0

        return {
            "days": days,
            "impressions": row["total_impressions"],
            "clicks": total_clicks,
            "conversions": total_conversions,
            "spend_cents": total_cost // 10000,
            "conversion_value_cents": total_value // 10000,
            "roas": round(roas, 2),
            "ctr": round(total_clicks / row["total_impressions"] * 100, 2) if row["total_impressions"] > 0 else 0,
            "cost_per_lead_cents": cost_per_lead_cents,
        }

    async def get_daily_performance(self, days: int = 30) -> list[dict]:
        """Get daily performance time series from local DB."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT date,
                       SUM(impressions) AS impressions,
                       SUM(clicks) AS clicks,
                       SUM(conversions) AS conversions,
                       SUM(cost_micros) AS cost_micros,
                       SUM(conversion_value_micros) AS conversion_value_micros
                FROM google_ads_performance
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
                "clicks": r["clicks"],
                "conversions": float(r["conversions"]),
                "spend_cents": r["cost_micros"] // 10000,
                "roas": round(r["conversion_value_micros"] / r["cost_micros"], 2) if r["cost_micros"] > 0 else 0,
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
                INSERT INTO google_ads_ai_actions
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
                    "SELECT * FROM google_ads_ai_actions WHERE status = $1 ORDER BY created_at DESC LIMIT $2",
                    status, limit,
                )
            else:
                rows = await db.fetch(
                    "SELECT * FROM google_ads_ai_actions ORDER BY created_at DESC LIMIT $1",
                    limit,
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

    async def approve_action(self, action_id: str) -> dict:
        """Approve a pending AI action."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE google_ads_ai_actions
                SET status = 'approved', updated_at = NOW()
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
                UPDATE google_ads_ai_actions
                SET status = 'rejected', updated_at = NOW()
                WHERE id = $1 AND status = 'proposed'
                RETURNING id
                """,
                action_id,
            )
        if not row:
            raise ValueError("Action not found or not in proposed status")
        return {"id": str(row["id"]), "status": "rejected"}
