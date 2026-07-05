"""AuraFlow — Kiosk-Device Enforcement Middleware

Pairs with af_global.kiosk_devices. If the incoming request carries the
auraflow_kiosk_device cookie OR (less commonly) its (source_ip,
user_agent) fingerprint matches a registered device row, this
middleware:

  1. Sets request.state.kiosk_device = <row> so endpoints can reason
     about it (e.g. /auth/login refuses).
  2. Blocks every API path except the allowlist below with 403.
  3. On a fingerprint-match path, sets the device cookie on the
     response so cookie-clearing doesn't escape the lock.

Allowlisted prefixes are the minimum the in-house check-in kiosk
actually needs (session roster, member lookup, booking check-in, voice
check-in, plus auth/me & refresh so the JWT stays alive). Anything
else — POS, settings, payroll, marketing, etc. — returns 403 with a
kiosk-friendly body.

This middleware does NOT replace the Next.js client-side redirect at
/kiosk-locked. The redirect gives a friendly UI; this middleware is
the actual enforcement that survives cookie clears.
"""
import re
from typing import Optional

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.services.kiosk.kiosk_device_service import kiosk_device_service


# Paths the kiosk is allowed to hit. Anything else → 403.
# Regex match against the path (no scheme/host).
_KIOSK_ALLOWED_PATTERNS = [
    # Health & infra
    re.compile(r"^/health$"),
    re.compile(r"^/health/.*"),
    re.compile(r"^/metrics$"),
    # Auth lifecycle: the kiosk uses a logged-in session, so refresh +
    # who-am-I have to work. Login is HANDLED SEPARATELY in this
    # middleware (kiosk devices cannot complete a /auth/login).
    re.compile(r"^/api/v1/auth/me$"),
    re.compile(r"^/api/v1/auth/refresh$"),
    re.compile(r"^/api/v1/auth/logout$"),
    re.compile(r"^/api/v1/users/me$"),
    # Branding for the kiosk shell (logo, color)
    re.compile(r"^/api/v1/public/.*"),
    # In-house check-in kiosk APIs
    re.compile(r"^/api/v1/scheduling/sessions(?:/.*)?$"),
    re.compile(r"^/api/v1/scheduling/bookings(?:/.*)?$"),
    re.compile(r"^/api/v1/members(?:/[^/]+)?$"),      # GET member detail
    re.compile(r"^/api/v1/members/search.*"),         # member search
    re.compile(r"^/api/v1/voice/.*"),                  # voice check-in
    re.compile(r"^/api/v1/payments/charge-drop-in$"),  # POS drop-in only
    re.compile(r"^/api/v1/payments/record-drop-in$"),
    # The kiosk-device admin endpoint itself uses /api/v1/kiosk/devices
    # but those are owner-only and blocked from kiosk devices on purpose
    # (we don't want the kiosk to re-register itself or revoke). NOT
    # in the allowlist.
]

# Login paths are special — we don't just 403, we want to log the
# attempt and return a kiosk-specific error.
_LOGIN_PATTERNS = [
    re.compile(r"^/api/v1/auth/login.*"),
]

# iPad UA fingerprint. Catches Safari in "mobile" mode (default UA on
# iPadOS contains the literal "iPad" string). It does NOT catch iPadOS
# 13+ Safari running in default "desktop" mode — that UA is the same
# as Mac Safari. The device-binding + (ip, user-agent) fingerprint
# catches that case. Studio has no other iPads (owner-confirmed), so a
# false positive here is impossible by the owner's own rule.
_IPAD_UA_PATTERN = re.compile(r"\biPad\b", re.IGNORECASE)


def _path_allowed(path: str) -> bool:
    return any(p.match(path) for p in _KIOSK_ALLOWED_PATTERNS)


def _is_login(path: str) -> bool:
    return any(p.match(path) for p in _LOGIN_PATTERNS)


def _is_ipad(user_agent: Optional[str]) -> bool:
    return bool(user_agent and _IPAD_UA_PATTERN.search(user_agent))


def _read_cookie(scope: Scope, name: str) -> Optional[str]:
    """Pull a cookie value from raw ASGI headers."""
    for header_name, header_val in scope.get("headers", []):
        if header_name == b"cookie":
            cookies = header_val.decode("latin-1").split("; ")
            for c in cookies:
                if "=" in c:
                    k, v = c.split("=", 1)
                    if k == name:
                        return v
    return None


def _client_ip(scope: Scope) -> Optional[str]:
    """Prefer X-Forwarded-For (Traefik/nginx) over the direct peer."""
    for header_name, header_val in scope.get("headers", []):
        if header_name == b"x-forwarded-for":
            fwd = header_val.decode("latin-1").split(",")[0].strip()
            if fwd:
                return fwd
    client = scope.get("client")
    return client[0] if client else None


def _user_agent(scope: Scope) -> Optional[str]:
    for header_name, header_val in scope.get("headers", []):
        if header_name == b"user-agent":
            return header_val.decode("latin-1")
    return None


_KIOSK_COOKIE_NAME = "auraflow_kiosk_device"
# 10 years. The studio re-registers if they retire the iPad.
_KIOSK_COOKIE_MAX_AGE = 10 * 365 * 24 * 3600


def _build_cookie_value(device_token: str) -> bytes:
    """Build the Set-Cookie header value for the kiosk device cookie.
    HttpOnly so JS can't read or delete it; Secure so it only ships
    over HTTPS; SameSite=Lax so it travels with normal nav."""
    parts = [
        f"{_KIOSK_COOKIE_NAME}={device_token}",
        "Path=/",
        f"Max-Age={_KIOSK_COOKIE_MAX_AGE}",
        "HttpOnly",
        "Secure",
        "SameSite=Lax",
    ]
    return "; ".join(parts).encode("latin-1")


class KioskDeviceMiddleware:
    """ASGI middleware that gates non-kiosk API surface for registered
    kiosk devices."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Quick exits — never gate health, metrics, or non-API paths
        # (those are handled by the Next.js redirect anyway).
        if path in ("/health", "/metrics") or path.startswith("/health/"):
            await self.app(scope, receive, send)
            return

        # Look up device by cookie first, then by fingerprint.
        device = None
        rebind_needed = False
        token = _read_cookie(scope, _KIOSK_COOKIE_NAME)
        if token:
            device = await kiosk_device_service.find_by_token(token)
        ua = _user_agent(scope)
        if device is None:
            # Fingerprint rebind: only for paths that would actually
            # benefit (don't fingerprint every health check).
            ip = _client_ip(scope)
            device = await kiosk_device_service.find_by_fingerprint(ip, ua)
            if device:
                rebind_needed = True

        if device is None:
            # Hard block: any iPad UA hitting /auth/login is rejected.
            # Studio has no other iPads — the only iPad is the kiosk.
            if _is_login(path) and _is_ipad(ua):
                response = JSONResponse(
                    status_code=403,
                    content={
                        "detail": {
                            "error": "iPads cannot sign in to AuraFlow",
                            "code": "IPAD_LOGIN_BLOCKED",
                            "message": (
                                "This device is restricted to the check-in "
                                "kiosk. Use a laptop or phone to sign in."
                            ),
                        },
                    },
                )
                await response(scope, receive, send)
                return
            # Not a kiosk device — pass through.
            await self.app(scope, receive, send)
            return

        # Mark request state so endpoints can introspect.
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["kiosk_device"] = device

        # Best-effort last-seen update (don't await — fire-and-forget
        # is fine but we await to keep it simple; failure is swallowed
        # inside the service).
        await kiosk_device_service.touch_last_seen(device["device_token"])

        # Login is explicitly blocked on kiosk devices.
        if _is_login(path):
            response = JSONResponse(
                status_code=403,
                content={
                    "detail": {
                        "error": "Kiosk device cannot sign in",
                        "code": "KIOSK_DEVICE_BLOCKED",
                        "message": (
                            "This device is registered as a studio kiosk. "
                            "Use a personal laptop or phone to access AuraFlow."
                        ),
                    },
                },
            )
            if rebind_needed:
                response.headers.append(
                    "Set-Cookie",
                    _build_cookie_value(device["device_token"]).decode("latin-1"),
                )
            await response(scope, receive, send)
            return

        # Allowlisted paths pass through, with cookie rebind if needed.
        if _path_allowed(path):
            if rebind_needed:
                # Wrap send to inject Set-Cookie on the response start.
                async def send_with_cookie(message):
                    if message["type"] == "http.response.start":
                        headers = list(message.get("headers", []))
                        headers.append((b"set-cookie", _build_cookie_value(device["device_token"])))
                        message["headers"] = headers
                    await send(message)
                await self.app(scope, receive, send_with_cookie)
                return
            await self.app(scope, receive, send)
            return

        # Anything else on a kiosk device is denied.
        response = JSONResponse(
            status_code=403,
            content={
                "detail": {
                    "error": "Not available on kiosk device",
                    "code": "KIOSK_DEVICE_BLOCKED",
                    "path": path,
                },
            },
        )
        if rebind_needed:
            response.headers.append(
                "Set-Cookie",
                _build_cookie_value(device["device_token"]).decode("latin-1"),
            )
        await response(scope, receive, send)
