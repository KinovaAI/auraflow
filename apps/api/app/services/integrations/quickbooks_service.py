"""AuraFlow — QuickBooks Payroll Integration Service

OAuth2 authorization code flow, employee sync, time activity push.
Credentials stored encrypted via pgcrypto on af_global.organizations.
"""
from base64 import b64encode
from urllib.parse import urlencode
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.core.redis import get_redis
from app.db.session import get_tenant_db, get_global_db
from app.utils.encryption import encrypt_credential, decrypt_credential

QB_OAUTH_AUTHORIZE = "https://appcenter.intuit.com/connect/oauth2"
QB_OAUTH_TOKEN = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QB_API_BASE_SANDBOX = "https://sandbox-quickbooks.api.intuit.com"
QB_API_BASE_PROD = "https://quickbooks.api.intuit.com"
QB_TOKEN_CACHE_PREFIX = "qb_token:"
QB_TOKEN_TTL = 3540  # 1 hour minus 60s buffer
QB_MINOR_VERSION = "70"


class QuickBooksService:

    @property
    def _api_base(self) -> str:
        if settings.QB_ENVIRONMENT == "production":
            return QB_API_BASE_PROD
        return QB_API_BASE_SANDBOX

    # ── OAuth Flow ────────────────────────────────────────────────────

    def get_authorize_url(self, org_id: str) -> str:
        """Build the OAuth2 authorization URL."""
        params = {
            "client_id": settings.QB_CLIENT_ID,
            "redirect_uri": settings.QB_REDIRECT_URI,
            "response_type": "code",
            "scope": "com.intuit.quickbooks.accounting com.intuit.quickbooks.payroll",
            "state": org_id,
        }
        return f"{QB_OAUTH_AUTHORIZE}?{urlencode(params)}"

    async def handle_callback(self, org_id: str, code: str, realm_id: str) -> None:
        """Exchange authorization code for tokens, encrypt & store."""
        auth_header = b64encode(
            f"{settings.QB_CLIENT_ID}:{settings.QB_CLIENT_SECRET}".encode()
        ).decode()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                QB_OAUTH_TOKEN,
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.QB_REDIRECT_URI,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        access_token = token_data["access_token"]
        refresh_token = token_data["refresh_token"]

        async with get_global_db() as db:
            enc_access = await encrypt_credential(db, access_token)
            enc_refresh = await encrypt_credential(db, refresh_token)

            await db.execute(
                """
                UPDATE af_global.organizations
                SET qb_access_token_encrypted = $1,
                    qb_refresh_token_encrypted = $2,
                    qb_realm_id = $3,
                    qb_connected_at = NOW(),
                    updated_at = NOW()
                WHERE id = $4
                """,
                enc_access, enc_refresh, realm_id, org_id,
            )

            # Enable feature flag
            await db.execute(
                """
                INSERT INTO af_global.feature_flags (organization_id, flag_key, is_enabled)
                VALUES ($1, 'payroll.quickbooks', TRUE)
                ON CONFLICT (organization_id, flag_key)
                DO UPDATE SET is_enabled = TRUE, updated_at = NOW()
                """,
                org_id,
            )

        # Cache access token
        redis = await get_redis()
        if redis:
            await redis.setex(
                f"{QB_TOKEN_CACHE_PREFIX}{org_id}",
                QB_TOKEN_TTL,
                access_token,
            )

        logger.info("QuickBooks connected", org_id=org_id, realm_id=realm_id)

    async def disconnect(self, org_id: str) -> None:
        """Clear QuickBooks credentials and disable feature flag."""
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET qb_access_token_encrypted = NULL,
                    qb_refresh_token_encrypted = NULL,
                    qb_client_id_encrypted = NULL,
                    qb_client_secret_encrypted = NULL,
                    qb_realm_id = NULL,
                    qb_connected_at = NULL,
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id,
            )
            await db.execute(
                """
                INSERT INTO af_global.feature_flags (organization_id, flag_key, is_enabled)
                VALUES ($1, 'payroll.quickbooks', FALSE)
                ON CONFLICT (organization_id, flag_key)
                DO UPDATE SET is_enabled = FALSE, updated_at = NOW()
                """,
                org_id,
            )

        redis = await get_redis()
        if redis:
            await redis.delete(f"{QB_TOKEN_CACHE_PREFIX}{org_id}")

        logger.info("QuickBooks disconnected", org_id=org_id)

    async def get_connection_status(self, org_id: str) -> dict:
        """Return connection status without decrypting secrets."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT qb_realm_id, qb_connected_at
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
        if not row:
            return {"connected": False}
        return {
            "connected": row["qb_connected_at"] is not None,
            "realm_id": row["qb_realm_id"],
            "connected_at": row["qb_connected_at"].isoformat() if row["qb_connected_at"] else None,
        }

    # ── Token Management ──────────────────────────────────────────────

    async def _get_access_token(self, org_id: str) -> tuple[str, str]:
        """Get valid access token + realm_id, refreshing if needed."""
        redis = await get_redis()
        cached = await redis.get(f"{QB_TOKEN_CACHE_PREFIX}{org_id}") if redis else None

        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT qb_refresh_token_encrypted, qb_realm_id
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
            if not row or not row["qb_refresh_token_encrypted"]:
                raise ValueError("QuickBooks not connected")
            realm_id = row["qb_realm_id"]

            if cached:
                token = cached.decode() if isinstance(cached, bytes) else cached
                return token, realm_id

            refresh_token = await decrypt_credential(db, row["qb_refresh_token_encrypted"])

        auth_header = b64encode(
            f"{settings.QB_CLIENT_ID}:{settings.QB_CLIENT_SECRET}".encode()
        ).decode()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                QB_OAUTH_TOKEN,
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        new_access = token_data["access_token"]
        new_refresh = token_data.get("refresh_token", refresh_token)

        async with get_global_db() as db:
            enc_access = await encrypt_credential(db, new_access)
            enc_refresh = await encrypt_credential(db, new_refresh)
            await db.execute(
                """
                UPDATE af_global.organizations
                SET qb_access_token_encrypted = $1,
                    qb_refresh_token_encrypted = $2,
                    updated_at = NOW()
                WHERE id = $3
                """,
                enc_access, enc_refresh, org_id,
            )

        if redis:
            await redis.setex(
                f"{QB_TOKEN_CACHE_PREFIX}{org_id}",
                QB_TOKEN_TTL,
                new_access,
            )
        return new_access, realm_id

    # ── Employee Sync ─────────────────────────────────────────────────

    async def list_employees(self, org_id: str) -> list[dict]:
        """List employees from QuickBooks for mapping UI."""
        token, realm_id = await self._get_access_token(org_id)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._api_base}/v3/company/{realm_id}/query",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                params={
                    "query": "SELECT * FROM Employee WHERE Active = true",
                    "minorversion": QB_MINOR_VERSION,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        employees = data.get("QueryResponse", {}).get("Employee", [])
        return [
            {
                "id": str(emp.get("Id", "")),
                "first_name": emp.get("GivenName", ""),
                "last_name": emp.get("FamilyName", ""),
                "email": emp.get("PrimaryEmailAddr", {}).get("Address", ""),
            }
            for emp in employees
        ]

    # ── Time Activity Push ────────────────────────────────────────────

    async def push_time_activities(self, org_id: str, run_id: str) -> dict:
        """
        Push payroll line items as TimeActivity entries to QuickBooks.
        """
        token, realm_id = await self._get_access_token(org_id)

        async with get_tenant_db() as db:
            run = await db.fetchrow(
                "SELECT * FROM payroll_runs WHERE id = $1", run_id
            )
            if not run:
                raise ValueError("Payroll run not found")
            if run["status"] not in ("finalized", "exported"):
                raise ValueError("Payroll run must be finalized before export")

            items = await db.fetch(
                """
                SELECT pli.*, i.display_name AS instructor_name,
                       pem.external_employee_id
                FROM payroll_line_items pli
                JOIN instructors i ON i.id = pli.instructor_id
                LEFT JOIN payroll_employee_mapping pem
                    ON pem.instructor_id = pli.instructor_id
                    AND pem.provider = 'quickbooks'
                WHERE pli.payroll_run_id = $1
                """,
                run_id,
            )

        submitted = []
        skipped = []

        for item in items:
            if not item["external_employee_id"]:
                skipped.append(item["instructor_name"])
                continue

            total_hours = float(item["hours_worked"]) + float(item["overtime_hours"])
            if total_hours == 0 and item["classes_taught"] == 0:
                skipped.append(item["instructor_name"])
                continue

            # Convert hours to HH:MM format for QuickBooks
            hours_int = int(total_hours)
            minutes_int = int((total_hours - hours_int) * 60)

            time_activity = {
                "NameOf": "Employee",
                "EmployeeRef": {"value": item["external_employee_id"]},
                "TxnDate": run["period_start"].isoformat(),
                "Hours": hours_int,
                "Minutes": minutes_int,
                "Description": (
                    f"Payroll period {run['period_start']} to {run['period_end']}. "
                    f"Classes: {item['classes_taught']}"
                ),
            }

            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{self._api_base}/v3/company/{realm_id}/timeactivity",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        params={"minorversion": QB_MINOR_VERSION},
                        json=time_activity,
                    )
                    resp.raise_for_status()
                submitted.append(item["instructor_name"])
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "QB time activity push failed",
                    employee_id=item["external_employee_id"],
                    status=e.response.status_code,
                    detail=e.response.text[:200],
                )
                skipped.append(f"{item['instructor_name']} (API error)")

        # Mark run as exported
        async with get_tenant_db() as db:
            await db.execute(
                """
                UPDATE payroll_runs
                SET status = 'exported', exported_at = NOW(),
                    export_method = 'quickbooks', updated_at = NOW()
                WHERE id = $1
                """,
                run_id,
            )

        logger.info(
            "QuickBooks time activities pushed",
            run_id=run_id,
            submitted=len(submitted),
            skipped=len(skipped),
        )
        return {
            "success": True,
            "submitted": submitted,
            "skipped": skipped,
        }
