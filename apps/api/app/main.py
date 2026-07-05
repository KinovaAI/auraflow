"""
AuraFlow API — Main Application Entry Point
"""
import re
import sentry_sdk
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import setup_logging, logger
from app.db.session import init_db
from app.middleware.error_handler import app_error_handler
from app.middleware.tenant import TenantMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.timing import TimingMiddleware
from app.middleware.request_tracker import RequestTrackerMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.api.v1.router import api_router

# ── Rate Limiter (defense-in-depth alongside nginx) ──────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


# ── Sentry ────────────────────────────────────────────────────────────────────
if settings.SENTRY_DSN_API:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN_API,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
    )


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    setup_logging()
    logger.info("AuraFlow API starting up", version=settings.APP_VERSION)
    await init_db()
    logger.info("Database initialized")

    # Startup warnings for missing security config
    if not settings.HEALTH_DATA_ENCRYPTION_KEY:
        logger.warning("HEALTH_DATA_ENCRYPTION_KEY not set — health data will be stored unencrypted")
    if not settings.BACKUP_ENCRYPTION_KEY:
        logger.warning("BACKUP_ENCRYPTION_KEY not set — database backups will not be encrypted")
    if settings.ENVIRONMENT == "production" and not settings.SENTRY_DSN_API:
        logger.warning("SENTRY_DSN_API not set — error monitoring disabled in production")

    yield
    logger.info("AuraFlow API shutting down")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AuraFlow API",
    description="Studio management platform API — MindBody alternative",
    version=settings.APP_VERSION,
    # Schema docs: only in development. Explicit allowlist (not "everything
    # that isn't development is prod") so staging / preview / unknown envs
    # don't accidentally publish the API surface.
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(AppError, app_error_handler)


# ── Middleware (order matters — last added = first executed) ──────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.auraflow\.fit",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Organization-Slug"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
# Kiosk-device enforcement runs AFTER tenant resolution but before
# request tracking, so a kiosk device's blocked requests are still
# attributed to the right org_id in logs. Added BEFORE TenantMiddleware
# in source so it runs AFTER it inbound (Starlette LIFO order).
from app.middleware.kiosk_device import KioskDeviceMiddleware  # noqa: E402
app.add_middleware(KioskDeviceMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestTrackerMiddleware)

# Per-tenant CORS for white-label portals — added LAST so it runs FIRST
# inbound. Looks up Origin in af_global.organizations.allowed_portal_origins,
# short-circuits OPTIONS preflights with 204, augments response headers
# for actual requests. Falls through cleanly for any Origin it doesn't
# recognize, letting the static CORSMiddleware above handle it (which is
# what we want for the *.auraflow.fit subdomains).
from app.middleware.portal_cors import PortalCORSMiddleware  # noqa: E402
app.add_middleware(PortalCORSMiddleware)


# ── Prometheus metrics + OpenTelemetry tracing (Phase 0.5) ────────────────────
# Instrumentation is best-effort — if the dependencies aren't installed the
# app still boots. Metrics exposed at /metrics (IP-allowlisted at nginx);
# OTEL spans export to stdout for now, wire up an OTLP collector later.
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_group_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health", "/health/ready", "/metrics"],
        inprogress_name="auraflow_http_requests_inprogress",
        inprogress_labels=True,
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("Prometheus instrumentator enabled at /metrics")
except ImportError:
    logger.info("prometheus_fastapi_instrumentator not installed — /metrics disabled")

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    _resource = Resource.create({
        "service.name": "auraflow-api",
        "service.version": settings.APP_VERSION,
        "deployment.environment": settings.ENVIRONMENT,
    })
    _provider = TracerProvider(resource=_resource)
    _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(_provider)

    FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/health/ready,/metrics")
    AsyncPGInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    logger.info("OpenTelemetry tracing enabled (stdout exporter)")
except ImportError:
    logger.info("opentelemetry not installed — tracing disabled")


# ── Health Endpoints ──────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check():
    """Kubernetes/Docker health probe."""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "platform": "AuraFlow",
    }


@app.get("/health/ready", tags=["system"])
async def readiness_check():
    """Deep health check including DB and Redis."""
    from app.db.session import get_db_status
    from app.core.redis import get_redis_status
    db_ok = await get_db_status()
    redis_ok = await get_redis_status()
    healthy = db_ok and redis_ok
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ready" if healthy else "not_ready",
            "checks": {"database": db_ok, "redis": redis_ok},
        }
    )


# ── API Router ────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")


# ── Webhook Routers (no auth prefix) ─────────────────────────────────────────
from app.api.v1.endpoints.webhooks import stripe_router, square_router, mux_router, zoom_router, sendgrid_router, twilio_router, voice_router
app.include_router(stripe_router, prefix="/webhooks/stripe")
app.include_router(square_router, prefix="/webhooks/square")
app.include_router(mux_router, prefix="/webhooks/mux")
app.include_router(zoom_router, prefix="/webhooks/zoom")
app.include_router(sendgrid_router, prefix="/webhooks/sendgrid")
app.include_router(twilio_router, prefix="/webhooks/twilio")
app.include_router(voice_router, prefix="/webhooks/twilio/voice")

from app.api.v1.endpoints.emr_webhooks import emr_router
app.include_router(emr_router, prefix="/webhooks/emr")
