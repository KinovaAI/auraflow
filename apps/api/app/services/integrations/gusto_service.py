"""AuraFlow — Gusto Payroll Integration Service

OAuth2 authorization code flow, employee sync, payroll push.
Credentials stored encrypted via pgcrypto on af_global.organizations.
"""
from urllib.parse import urlencode
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.core.redis import get_redis
from app.db.session import get_tenant_db, get_global_db
from app.utils.encryption import encrypt_credential, decrypt_credential

GUSTO_API_BASE = "https://api.gusto.com/v1"
GUSTO_OAUTH_AUTHORIZE = "https://api.gusto.com/oauth/authorize"
GUSTO_OAUTH_TOKEN = "https://api.gusto.com/oauth/token"
GUSTO_TOKEN_CACHE_PREFIX = "gusto_token:"
GUSTO_TOKEN_TTL = 7140  # 2 hours minus 60s buffer


class GustoService:

    # ── OAuth Flow ────────────────────────────────────────────────────

    def get_authorize_url(self, org_id: str) -> str:
        """Build the OAuth2 authorization URL."""
        params = {
            "client_id": settings.GUSTO_CLIENT_ID,
            "redirect_uri": settings.GUSTO_REDIRECT_URI,
            "response_type": "code",
            "state": org_id,
        }
        return f"{GUSTO_OAUTH_AUTHORIZE}?{urlencode(params)}"

    async def handle_callback(self, org_id: str, code: str) -> None:
        """Exchange authorization code for tokens, encrypt & store."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GUSTO_OAUTH_TOKEN,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.GUSTO_CLIENT_ID,
                    "client_secret": settings.GUSTO_CLIENT_SECRET,
                    "redirect_uri": settings.GUSTO_REDIRECT_URI,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        access_token = token_data["access_token"]
        refresh_token = token_data["refresh_token"]

        # Fetch company ID
        company_id = await self._fetch_company_id(access_token)

        async with get_global_db() as db:
            enc_access = await encrypt_credential(db, access_token)
            enc_refresh = await encrypt_credential(db, refresh_token)

            await db.execute(
                """
                UPDATE af_global.organizations
                SET gusto_access_token_encrypted = $1,
                    gusto_refresh_token_encrypted = $2,
                    gusto_company_id = $3,
                    gusto_connected_at = NOW(),
                    updated_at = NOW()
                WHERE id = $4
                """,
                enc_access, enc_refresh, company_id, org_id,
            )

            # Enable feature flag
            await db.execute(
                """
                INSERT INTO af_global.feature_flags (organization_id, flag_key, is_enabled)
                VALUES ($1, 'payroll.gusto', TRUE)
                ON CONFLICT (organization_id, flag_key)
                DO UPDATE SET is_enabled = TRUE, updated_at = NOW()
                """,
                org_id,
            )

        # Cache access token
        redis = await get_redis()
        if redis:
            await redis.setex(
                f"{GUSTO_TOKEN_CACHE_PREFIX}{org_id}",
                GUSTO_TOKEN_TTL,
                access_token,
            )

        logger.info("Gusto connected", org_id=org_id, company_id=company_id)

    async def disconnect(self, org_id: str) -> None:
        """Clear Gusto credentials and disable feature flag."""
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET gusto_access_token_encrypted = NULL,
                    gusto_refresh_token_encrypted = NULL,
                    gusto_client_id_encrypted = NULL,
                    gusto_company_id = NULL,
                    gusto_connected_at = NULL,
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id,
            )
            await db.execute(
                """
                INSERT INTO af_global.feature_flags (organization_id, flag_key, is_enabled)
                VALUES ($1, 'payroll.gusto', FALSE)
                ON CONFLICT (organization_id, flag_key)
                DO UPDATE SET is_enabled = FALSE, updated_at = NOW()
                """,
                org_id,
            )

        # Clear cached token
        redis = await get_redis()
        if redis:
            await redis.delete(f"{GUSTO_TOKEN_CACHE_PREFIX}{org_id}")

        logger.info("Gusto disconnected", org_id=org_id)

    async def get_connection_status(self, org_id: str) -> dict:
        """Return connection status without decrypting secrets."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT gusto_company_id, gusto_connected_at
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
        if not row:
            return {"connected": False}
        return {
            "connected": row["gusto_connected_at"] is not None,
            "company_id": row["gusto_company_id"],
            "connected_at": row["gusto_connected_at"].isoformat() if row["gusto_connected_at"] else None,
        }

    # ── Token Management ──────────────────────────────────────────────

    async def _get_access_token(self, org_id: str) -> str:
        """Get valid access token, refreshing if needed."""
        redis = await get_redis()
        if redis:
            cached = await redis.get(f"{GUSTO_TOKEN_CACHE_PREFIX}{org_id}")
            if cached:
                return cached.decode() if isinstance(cached, bytes) else cached

        # Refresh token
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT gusto_refresh_token_encrypted
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
            if not row or not row["gusto_refresh_token_encrypted"]:
                raise ValueError("Gusto not connected")
            refresh_token = await decrypt_credential(db, row["gusto_refresh_token_encrypted"])

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GUSTO_OAUTH_TOKEN,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": settings.GUSTO_CLIENT_ID,
                    "client_secret": settings.GUSTO_CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        new_access = token_data["access_token"]
        new_refresh = token_data.get("refresh_token", refresh_token)

        # Store new tokens
        async with get_global_db() as db:
            enc_access = await encrypt_credential(db, new_access)
            enc_refresh = await encrypt_credential(db, new_refresh)
            await db.execute(
                """
                UPDATE af_global.organizations
                SET gusto_access_token_encrypted = $1,
                    gusto_refresh_token_encrypted = $2,
                    updated_at = NOW()
                WHERE id = $3
                """,
                enc_access, enc_refresh, org_id,
            )

        if redis:
            await redis.setex(
                f"{GUSTO_TOKEN_CACHE_PREFIX}{org_id}",
                GUSTO_TOKEN_TTL,
                new_access,
            )
        return new_access

    async def _fetch_company_id(self, access_token: str) -> str:
        """Fetch the company ID for the authenticated user."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GUSTO_API_BASE}/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        # Gusto returns current_user with roles containing company info
        roles = data.get("roles", [])
        for role in roles:
            if role.get("type") == "Role::PayrollAdmin":
                entities = role.get("entities", [])
                if entities:
                    return str(entities[0].get("uuid", ""))
        # Fallback: try companies list
        companies = data.get("companies", [])
        if companies:
            return str(companies[0].get("uuid", ""))
        raise ValueError("Could not determine Gusto company ID")

    # ── Employee Sync ─────────────────────────────────────────────────

    async def list_employees(self, org_id: str) -> list[dict]:
        """List employees from Gusto for mapping UI."""
        token = await self._get_access_token(org_id)

        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT gusto_company_id FROM af_global.organizations WHERE id = $1",
                org_id,
            )
        company_id = row["gusto_company_id"]

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GUSTO_API_BASE}/companies/{company_id}/employees",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            employees = resp.json()

        return [
            {
                "id": str(emp.get("uuid", "")),
                "first_name": emp.get("first_name", ""),
                "last_name": emp.get("last_name", ""),
                "email": emp.get("email", ""),
            }
            for emp in employees
            if emp.get("terminated") is not True
        ]

    # ── Payroll Push ──────────────────────────────────────────────────

    async def push_payroll(self, org_id: str, run_id: str) -> dict:
        """
        Push a finalized payroll run to Gusto.
        Submits hours for mapped employees.
        """
        token = await self._get_access_token(org_id)

        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT gusto_company_id FROM af_global.organizations WHERE id = $1",
                org_id,
            )
        company_id = row["gusto_company_id"]

        async with get_tenant_db() as db:
            run = await db.fetchrow(
                "SELECT * FROM payroll_runs WHERE id = $1", run_id
            )
            if not run:
                raise ValueError("Payroll run not found")
            if run["status"] not in ("finalized", "exported"):
                raise ValueError("Payroll run must be finalized before export")

            # Get line items with employee mappings
            items = await db.fetch(
                """
                SELECT pli.*, i.display_name AS instructor_name,
                       pem.external_employee_id
                FROM payroll_line_items pli
                JOIN instructors i ON i.id = pli.instructor_id
                LEFT JOIN payroll_employee_mapping pem
                    ON pem.instructor_id = pli.instructor_id
                    AND pem.provider = 'gusto'
                WHERE pli.payroll_run_id = $1
                """,
                run_id,
            )

        # Build payroll data for each mapped employee
        submitted = []
        skipped = []

        for item in items:
            if not item["external_employee_id"]:
                skipped.append(item["instructor_name"])
                continue

            hours = float(item["hours_worked"]) + float(item["overtime_hours"])
            if hours == 0 and item["classes_taught"] == 0:
                skipped.append(item["instructor_name"])
                continue

            # Submit hours via Gusto API
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{GUSTO_API_BASE}/companies/{company_id}/payrolls",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "employee_uuid": item["external_employee_id"],
                            "hours_worked": float(item["hours_worked"]),
                            "overtime_hours": float(item["overtime_hours"]),
                            "period_start": run["period_start"].isoformat(),
                            "period_end": run["period_end"].isoformat(),
                        },
                    )
                    resp.raise_for_status()
                submitted.append(item["instructor_name"])
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Gusto payroll push failed for employee",
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
                    export_method = 'gusto', updated_at = NOW()
                WHERE id = $1
                """,
                run_id,
            )

        logger.info(
            "Gusto payroll pushed",
            run_id=run_id,
            submitted=len(submitted),
            skipped=len(skipped),
        )
        return {
            "success": True,
            "submitted": submitted,
            "skipped": skipped,
        }
