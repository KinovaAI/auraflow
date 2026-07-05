"""AuraFlow — Platform Config Service

CRUD for platform-level credentials (SendGrid, Google Ads, Meta).
Sensitive fields stored encrypted via pgcrypto; returned masked to the API.
Services can call get_raw_*() methods which fall back to env vars.
"""
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_global_db
from app.utils.encryption import encrypt_credential, decrypt_credential


ENCRYPTED_FIELDS = {
    "sendgrid_api_key": "sendgrid_api_key_enc",
    "sendgrid_inbound_webhook_secret": "sendgrid_inbound_webhook_secret_enc",
    "google_ads_developer_token": "google_ads_developer_token_enc",
    "google_client_secret": "google_client_secret_enc",
    "meta_app_secret": "meta_app_secret_enc",
    "meta_page_access_token": "meta_page_access_token_enc",
}

PLAIN_FIELDS = [
    "sendgrid_from_email", "sendgrid_from_name",
    "platform_admin_alert_email", "support_escalation_email",
    "google_ads_login_customer_id", "google_client_id",
    "meta_app_id", "meta_page_id", "instagram_business_account_id",
]


def _mask(value: Optional[str], show_last: int = 4) -> Optional[str]:
    if not value:
        return None
    if len(value) <= show_last + 4:
        return "****" + value[-show_last:]
    return value[:4] + "****..." + value[-show_last:]


class PlatformConfigService:

    async def get_config(self) -> dict:
        """Fetch config with sensitive fields masked."""
        async with get_global_db() as db:
            row = await db.fetchrow("SELECT * FROM af_global.platform_config LIMIT 1")
            if not row:
                return {}

            result = {
                "id": str(row["id"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }

            # Plain fields
            for field in PLAIN_FIELDS:
                result[field] = row[field]

            # Encrypted fields — decrypt then mask
            for api_name, db_col in ENCRYPTED_FIELDS.items():
                raw = row[db_col]
                if raw:
                    try:
                        decrypted = await decrypt_credential(db, raw)
                        result[api_name] = _mask(decrypted)
                    except Exception:
                        result[api_name] = "****"
                else:
                    result[api_name] = None

            return result

    async def update_config(self, updates: dict) -> dict:
        """Update config fields. Encrypts sensitive fields automatically."""
        async with get_global_db() as db:
            row = await db.fetchrow("SELECT id FROM af_global.platform_config LIMIT 1")
            if not row:
                return {}

            parts = []
            params = [row["id"]]
            idx = 2

            for field in PLAIN_FIELDS:
                if field in updates:
                    parts.append(f"{field} = ${idx}")
                    params.append(updates[field])
                    idx += 1

            for api_name, db_col in ENCRYPTED_FIELDS.items():
                if api_name in updates and updates[api_name]:
                    encrypted = await encrypt_credential(db, updates[api_name])
                    parts.append(f"{db_col} = ${idx}")
                    params.append(encrypted)
                    idx += 1

            if not parts:
                return await self.get_config()

            await db.execute(f"""
                UPDATE af_global.platform_config
                SET {', '.join(parts)}
                WHERE id = $1
            """, *params)

        return await self.get_config()

    # ── Raw credential accessors (for internal services) ──────────────

    async def get_raw_sendgrid_api_key(self) -> Optional[str]:
        async with get_global_db() as db:
            raw = await db.fetchval(
                "SELECT sendgrid_api_key_enc FROM af_global.platform_config LIMIT 1"
            )
            if raw:
                return await decrypt_credential(db, raw)
        return settings.SENDGRID_API_KEY

    async def get_raw_sendgrid_from(self) -> tuple[str, str]:
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT sendgrid_from_email, sendgrid_from_name FROM af_global.platform_config LIMIT 1"
            )
            if row and row["sendgrid_from_email"]:
                return row["sendgrid_from_email"], row["sendgrid_from_name"] or "AuraFlow"
        return settings.SENDGRID_FROM_EMAIL, settings.SENDGRID_FROM_NAME

    async def get_raw_google_credentials(self) -> dict:
        result = {}
        async with get_global_db() as db:
            row = await db.fetchrow("""
                SELECT google_ads_developer_token_enc, google_ads_login_customer_id,
                       google_client_id, google_client_secret_enc
                FROM af_global.platform_config LIMIT 1
            """)
            if row:
                if row["google_ads_developer_token_enc"]:
                    result["google_ads_developer_token"] = await decrypt_credential(db, row["google_ads_developer_token_enc"])
                if row["google_client_secret_enc"]:
                    result["google_client_secret"] = await decrypt_credential(db, row["google_client_secret_enc"])
                result["google_ads_login_customer_id"] = row["google_ads_login_customer_id"]
                result["google_client_id"] = row["google_client_id"]

        # Fall back to env vars for any missing values
        result.setdefault("google_ads_developer_token", settings.GOOGLE_ADS_DEVELOPER_TOKEN)
        result.setdefault("google_ads_login_customer_id", settings.GOOGLE_ADS_LOGIN_CUSTOMER_ID)
        result.setdefault("google_client_id", settings.GOOGLE_CLIENT_ID)
        result.setdefault("google_client_secret", settings.GOOGLE_CLIENT_SECRET)
        return result

    async def get_raw_meta_credentials(self) -> dict:
        result = {}
        async with get_global_db() as db:
            row = await db.fetchrow("""
                SELECT meta_app_id, meta_app_secret_enc, meta_page_access_token_enc,
                       meta_page_id, instagram_business_account_id
                FROM af_global.platform_config LIMIT 1
            """)
            if row:
                if row["meta_app_secret_enc"]:
                    result["meta_app_secret"] = await decrypt_credential(db, row["meta_app_secret_enc"])
                if row["meta_page_access_token_enc"]:
                    result["meta_page_access_token"] = await decrypt_credential(db, row["meta_page_access_token_enc"])
                result["meta_app_id"] = row["meta_app_id"]
                result["meta_page_id"] = row["meta_page_id"]
                result["instagram_business_account_id"] = row["instagram_business_account_id"]

        result.setdefault("meta_app_id", settings.META_APP_ID)
        result.setdefault("meta_app_secret", settings.META_APP_SECRET)
        result.setdefault("meta_page_access_token", settings.META_PAGE_ACCESS_TOKEN)
        result.setdefault("meta_page_id", settings.META_PAGE_ID)
        result.setdefault("instagram_business_account_id", settings.INSTAGRAM_BUSINESS_ACCOUNT_ID)
        return result

    # ── Test ──────────────────────────────────────────────────────────

    async def test_sendgrid(self) -> dict:
        """Test SendGrid API key by hitting the scopes endpoint."""
        import httpx

        api_key = await self.get_raw_sendgrid_api_key()
        if not api_key:
            return {"valid": False, "error": "No SendGrid API key configured"}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.sendgrid.com/v3/scopes",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {"valid": True, "scopes": data.get("scopes", [])}
                return {"valid": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"valid": False, "error": str(e)}
