"""AuraFlow — Square OAuth Token Refresh Sweep

Square Code Flow access tokens last ~30 days; refresh tokens last
indefinitely. We refresh any access token expiring within 7 days so
the on-demand path in billing_dispatcher never hits the slow refresh
exchange under load.

Runs daily at 02:00 Pacific. Idempotent — if a token doesn't need
refreshing, it isn't touched.
"""
import asyncio

from app.core.logging import logger
from app.workers.celery_app import app
from app.services.payments.square_oauth_service import square_oauth_service


@app.task(
    name="app.workers.tasks.square_token_refresh.refresh_tokens",
    bind=True,
    max_retries=0,
)
def refresh_tokens(self):
    """Daily: refresh every Square OAuth access token expiring within 7d."""
    count = asyncio.run(square_oauth_service.refresh_expiring_tokens())
    logger.info("Square token refresh sweep complete", refreshed=count)
    return {"refreshed": count}
