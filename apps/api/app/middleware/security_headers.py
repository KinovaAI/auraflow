"""AuraFlow — Security headers middleware (pure ASGI)."""
from starlette.types import ASGIApp, Receive, Scope, Send

# Headers applied to every HTTP response
_SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
    (b"x-xss-protection", b"1; mode=block"),
]


class SecurityHeadersMiddleware:
    """Injects HTTP security headers into every response."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(_SECURITY_HEADERS)

                # Add Cache-Control: no-store for API responses
                path: str = scope.get("path", "")
                if path.startswith("/api/"):
                    headers.append((b"cache-control", b"no-store"))

                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
