"""AuraFlow — Request timing middleware (pure ASGI)."""
import os
import time
from starlette.types import ASGIApp, Receive, Scope, Send

_IS_DEVELOPMENT = os.environ.get("ENVIRONMENT", "development") == "development"


class TimingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()

        async def send_with_timing(message):
            if message["type"] == "http.response.start" and _IS_DEVELOPMENT:
                duration = time.perf_counter() - start
                headers = list(message.get("headers", []))
                headers.append((b"x-process-time", f"{duration:.4f}".encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_timing)
