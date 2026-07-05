"""AuraFlow — FastAPI dependencies for external API key authentication.

Provides two dependencies:
  - get_api_key_context: validates the API key, sets tenant context, enforces rate limit
  - require_api_scope:   factory that returns a dependency checking required scopes
"""
from fastapi import Depends, HTTPException, Request, status

from app.core.tenant_context import set_tenant_context
from app.services.external.api_key_service import validate_key
from app.services.external.rate_limiter import check_rate_limit


async def get_api_key_context(request: Request) -> dict:
    """Extract and validate the API key from the request.

    Accepts the key via:
      - Authorization: Bearer af_live_...
      - X-API-Key: af_live_...

    On success, sets tenant context for downstream DB calls and returns
    the validated context dict (api_key_id, org_id, scopes, schema_name, etc.).
    """
    raw_key: str | None = None

    # Try Authorization header first
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer af_live_"):
        raw_key = auth_header[7:]  # strip "Bearer "

    # Fall back to X-API-Key header
    if raw_key is None:
        raw_key = request.headers.get("x-api-key")

    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide via Authorization: Bearer af_live_... or X-API-Key header.",
        )

    # Validate the key
    try:
        context = await validate_key(raw_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    # Set tenant context so get_tenant_db() works downstream
    set_tenant_context(
        organization_id=context["org_id"],
        schema_name=context["schema_name"],
        slug=context["org_slug"],
    )

    # Enforce rate limit
    allowed, remaining, reset_at = await check_rate_limit(
        context["api_key_id"],
        context["rate_limit_rpm"],
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(reset_at),
                "X-RateLimit-Limit": str(context["rate_limit_rpm"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_at),
            },
        )

    # Check feature flag — API access requires integrations.api
    from app.services.feature_flags import FeatureFlagService
    flags = FeatureFlagService()
    if not await flags.is_enabled("integrations.api", context["org_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API access requires the Scale plan. Upgrade to enable API integrations.",
        )

    # Attach rate-limit info for downstream use / response headers
    context["rate_limit_remaining"] = remaining
    context["rate_limit_reset"] = reset_at

    return context


def require_api_scope(*required_scopes: str):
    """Return a FastAPI dependency that checks the API key has sufficient scopes.

    Scope matching rules:
      - Exact match:        "members:read" matches "members:read"
      - Resource wildcard:  "members:*" matches "members:read", "members:write"
      - Global wildcard:    "*:*" matches everything

    The key must have at least ONE of the required scopes (OR logic).

    Usage:
        @router.get("/members", dependencies=[Depends(require_api_scope("members:read"))])
        async def list_members(ctx: dict = Depends(get_api_key_context)):
            ...
    """

    async def _check_scopes(
        context: dict = Depends(get_api_key_context),
    ) -> dict:
        key_scopes = context.get("scopes", [])

        # Global wildcard — skip further checks
        if "*:*" in key_scopes:
            return context

        for required in required_scopes:
            # Exact match
            if required in key_scopes:
                return context

            # Check if a wildcard in the key's scopes covers the required scope
            req_resource = required.split(":")[0] if ":" in required else required
            wildcard = f"{req_resource}:*"
            if wildcard in key_scopes:
                return context

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient scope. Required one of: {', '.join(required_scopes)}",
        )

    return _check_scopes
