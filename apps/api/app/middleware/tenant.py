"""
AuraFlow — Tenant Resolution Middleware (pure ASGI)

Resolves which organization/tenant is making the request.
Sets tenant context so all DB queries automatically scope to the right schema.

Resolution order:
1. JWT token → organization_id claim
2. Subdomain → e.g. example-studio.auraflow.fit
3. Custom domain → e.g. booking.your-domain.com
4. X-Organization-ID header (for API integrations)
"""
import json
import re
from typing import Optional

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.logging import logger
from app.core.tenant_context import set_tenant_context, clear_tenant_context

# Paths that don't require tenant resolution
PUBLIC_PATHS = {
    "/health",
    "/health/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/login/json",
    "/api/v1/auth/register",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/auth/refresh",
    "/api/v1/auth/switch-org",
    "/api/v1/organizations",          # org list/create (user-scoped, not tenant-scoped)
    "/api/v1/platform/studios",      # public studio discovery
    "/api/v1/auth/member-register",  # member self-registration
    "/webhooks/stripe",
    "/webhooks/mux",
    "/webhooks/twilio",
}

PLATFORM_DOMAIN = "auraflow.fit"
SUBDOMAIN_PATTERN = re.compile(r"^([a-z0-9-]+)\." + re.escape(PLATFORM_DOMAIN) + r"$")


class TenantMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Skip tenant resolution for public paths
        if self._is_public_path(path):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        host = (headers.get(b"host", b"") or b"").decode()

        tenant_slug = await self._resolve_tenant_slug(headers, host)

        if tenant_slug is None:
            # Platform-level requests (super admin, onboarding)
            await self.app(scope, receive, send)
            return

        # Load tenant from cache or DB
        tenant = await self._load_tenant(tenant_slug, host)
        if tenant is None:
            await self._send_json_response(send, 404, {
                "error": "Studio not found", "code": "TENANT_NOT_FOUND"
            })
            return

        if tenant["status"] == "cancelled":
            await self._send_json_response(send, 403, {
                "error": "Account cancelled", "code": "ACCOUNT_CANCELLED"
            })
            return

        # Restrict access for expired trials and suspended accounts
        if tenant["status"] in ("trial_expired", "suspended"):
            method = scope.get("method", "GET")
            if not self._is_allowed_for_restricted(path, method):
                msg = (
                    "Your trial has expired. Please upgrade to a paid plan to continue."
                    if tenant["status"] == "trial_expired"
                    else "Your account has been suspended. Please contact support."
                )
                await self._send_json_response(send, 403, {
                    "error": msg,
                    "code": "ACCOUNT_RESTRICTED",
                    "status": tenant["status"],
                })
                return

        # Set tenant context for this request
        set_tenant_context(
            organization_id=tenant["id"],
            schema_name=tenant["schema_name"],
            slug=tenant["slug"],
            plan_id=tenant.get("plan_id"),
        )

        # Attach to scope state for use in endpoints
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["tenant"] = tenant
        scope["state"]["schema_name"] = tenant["schema_name"]

        try:
            await self.app(scope, receive, send)
        finally:
            clear_tenant_context()

    def _is_allowed_for_restricted(self, path: str, method: str) -> bool:
        """Check if a request is allowed for trial_expired or suspended orgs.

        Allowed:
        - GET /api/v1/organizations/ (view billing/upgrade info)
        - GET/POST /api/v1/auth/ (login, refresh)
        - GET/POST /api/v1/organizations/billing/ and /api/v1/organizations/reactivate
        """
        stripped = path.rstrip("/")

        # Auth endpoints (login, refresh, etc.)
        if stripped.startswith("/api/v1/auth"):
            return method in ("GET", "POST")

        # Organization list / detail (so they can see billing/upgrade)
        if stripped.startswith("/api/v1/organizations/billing"):
            return method in ("GET", "POST")

        if stripped == "/api/v1/organizations/reactivate":
            return method == "POST"

        if stripped.startswith("/api/v1/organizations/apply-coupon"):
            return method == "POST"

        if stripped.startswith("/api/v1/organizations/discount"):
            return method == "GET"

        # Allow viewing org list and org details
        if stripped == "/api/v1/organizations":
            return method == "GET"

        if re.match(r"^/api/v1/organizations/[^/]+$", stripped):
            return method == "GET"

        # User profile (needed for frontend to load)
        if stripped == "/api/v1/users/me":
            return method == "GET"

        return False

    def _is_public_path(self, path: str) -> bool:
        if path in PUBLIC_PATHS:
            return True
        if path.startswith("/webhooks/"):
            return True
        # Organizations endpoints use global DB (not tenant-scoped),
        # but only match the list/create and single-org detail paths —
        # not nested sub-resources like /{slug}/members which need RBAC
        stripped = path.rstrip("/")
        if stripped == "/api/v1/organizations":
            return True
        if re.match(r"^/api/v1/organizations/[^/]+$", stripped):
            return True
        if path.startswith("/api/v1/public/"):
            return True
        # Self-serve signup resolves the org from the request body itself
        # (org_slug) and uses schema_override, so it needs no tenant header.
        if path.startswith("/api/v1/self-serve/"):
            return True
        # Managed billing broker authenticates self-hosted clients by broker API
        # key (not a tenant); it never touches tenant schemas.
        if path.startswith("/api/v1/broker/"):
            return True
        return False

    async def _resolve_tenant_slug(self, headers: dict, host: str) -> Optional[str]:
        # 1. Check JWT token for organization context (most trusted)
        auth_header = (headers.get(b"authorization", b"") or b"").decode()
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            slug = await self._extract_slug_from_token(token)
            if slug:
                return slug

        # 2. Check subdomain
        match = SUBDOMAIN_PATTERN.match(host)
        if match:
            subdomain = match.group(1)
            if subdomain not in ("app", "api", "www", "status", "mail"):
                return subdomain

        # 3. X-Organization-Slug header — lowest priority, only for authenticated requests
        # This prevents unauthenticated callers from spoofing tenant context
        slug = (headers.get(b"x-organization-slug", b"") or b"").decode()
        if slug and auth_header.startswith("Bearer "):
            return slug

        return None

    async def _extract_slug_from_token(self, token: str) -> Optional[str]:
        try:
            from app.core.security import decode_token
            payload = decode_token(token)
            return payload.get("org_slug")
        except Exception:
            return None

    async def _load_tenant(self, slug: str, host: str) -> Optional[dict]:
        from app.core.redis import get_redis
        from app.db.session import get_global_db

        cache_key = f"tenant:{slug}"

        # Try cache first
        redis = await get_redis()
        if redis:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)

        # Load from database
        async with get_global_db() as db:
            result = await db.fetchrow(
                """
                SELECT id, slug, name, schema_name, status, plan_id,
                       stripe_account_id, timezone, currency, primary_color
                FROM af_global.organizations
                WHERE slug = $1 OR custom_domain = $2
                """,
                slug, host,
            )

            if not result:
                return None

            tenant = dict(result)
            tenant["id"] = str(tenant["id"])

            # Cache for 5 minutes
            if redis:
                await redis.setex(cache_key, 300, json.dumps(tenant))

            return tenant

    async def _send_json_response(self, send: Send, status: int, body: dict):
        content = json.dumps(body).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(content)).encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": content,
        })
