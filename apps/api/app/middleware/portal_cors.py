"""AuraFlow — Per-tenant dynamic CORS for white-label portals.

Supplements the static CORSMiddleware in app.main (which covers
*.auraflow.fit) by allowing per-tenant Origins listed in
af_global.organizations.allowed_portal_origins.

Why a separate middleware instead of extending CORSMiddleware:
  - Starlette's CORSMiddleware computes allow_origins at startup. We need
    a per-request lookup driven by the tenant context, which only the
    Origin header (or the path's tenant slug) can provide.
  - Doing this in a middleware means we can short-circuit OPTIONS
    preflights before they hit any auth dependency — preflights don't
    carry the api_key header, so we can't rely on api_key auth here.
    We resolve the tenant from the Origin → DB lookup instead.

Algorithm:
  1. If no Origin header → noop (let downstream handle).
  2. If Origin matches the static *.auraflow.fit regex → noop (the static
     CORSMiddleware will handle it).
  3. Otherwise, look up any tenant whose allowed_portal_origins contains
     this Origin. Cache the lookup for 60s (org → set of origins) so we
     don't hit the DB on every preflight.
  4. If found, write CORS headers and (for OPTIONS) short-circuit with 204.
  5. If not found, let downstream handle it (will fall to the static
     CORSMiddleware, which will reject).

Cache invalidation: 60s TTL is acceptable. Brand admins can also call
POST /api/v1/external/branding/refresh-cors-cache (not implemented yet —
add when first customer needs faster propagation than 1 minute).
"""
from __future__ import annotations

import time
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import logger
from app.db.session import get_global_db


# Origin → tenant_slug (or None if not allowed). 60s TTL.
_CACHE: dict[str, tuple[float, str | None]] = {}
_CACHE_TTL = 60.0
_STATIC_AURAFLOW_RE = "auraflow.fit"  # cheap substring check; the static
                                       # CORSMiddleware does the strict regex
_ALLOWED_HEADERS = "Content-Type, Authorization, X-API-Key, X-Organization-Slug"
_ALLOWED_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"


async def _lookup_origin(origin: str) -> str | None:
    """Look up the tenant slug that has authorized this Origin. Cached."""
    now = time.time()
    cached = _CACHE.get(origin)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT slug
                FROM af_global.organizations
                WHERE $1 = ANY(allowed_portal_origins)
                  AND status NOT IN ('suspended', 'cancelled')
                LIMIT 1
                """,
                origin,
            )
        slug = row["slug"] if row else None
    except Exception as e:
        # If DB is down we don't want to BLOCK the request entirely —
        # just don't add CORS headers. The downstream CORSMiddleware will
        # then reject (correct behavior — we couldn't verify the origin).
        logger.warning("portal_cors: DB lookup failed for origin=%s: %s", origin, e)
        return None

    _CACHE[origin] = (now, slug)
    return slug


def _add_cors_headers(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = _ALLOWED_METHODS
    response.headers["Access-Control-Allow-Headers"] = _ALLOWED_HEADERS
    response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
    response.headers["Vary"] = "Origin"


class PortalCORSMiddleware(BaseHTTPMiddleware):
    """Dynamic CORS for tenant-registered Origins.

    Order matters in app.main: this middleware is added BEFORE the static
    CORSMiddleware (so it runs FIRST in the inbound dispatch — Starlette
    middleware order is FIFO during request, LIFO during response). For
    preflight OPTIONS requests, we short-circuit with a 204 if the origin
    is allowed by a tenant; for non-preflight requests we just augment
    the response headers and let downstream proceed normally.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        origin = request.headers.get("origin")
        if not origin or _STATIC_AURAFLOW_RE in origin:
            # No origin OR a static auraflow.fit origin — let the stock
            # CORSMiddleware downstream handle it.
            return await call_next(request)

        slug = await _lookup_origin(origin)
        if slug is None:
            # Not a tenant-authorized origin. Let the static middleware
            # downstream do its job (which will refuse).
            return await call_next(request)

        # Preflight short-circuit
        if request.method == "OPTIONS":
            response = Response(status_code=204)
            _add_cors_headers(response, origin)
            return response

        # Normal request: dispatch downstream then add CORS headers
        response = await call_next(request)
        _add_cors_headers(response, origin)
        return response
