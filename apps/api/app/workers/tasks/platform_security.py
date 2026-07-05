"""AuraFlow — Platform Security Celery Tasks

Periodic security scans, request metrics aggregation, and alert sending.
"""
import asyncio

from app.core.logging import logger
from app.workers.celery_app import app as celery_app


def _run_async(coro):
    """Run an async coroutine from sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="platform.security_scan", bind=True, max_retries=2)
def security_scan(self):
    """Run brute force, rate limit, and error spike detection."""
    try:
        from app.services.platform.security_service import SecurityService
        result = _run_async(SecurityService().run_security_scan())
        if result["total_new_events"] > 0:
            logger.info(f"Security scan: {result['total_new_events']} new events")
    except Exception as e:
        logger.error(f"security_scan failed: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(name="platform.aggregate_request_metrics")
def aggregate_request_metrics():
    """Flush Redis traffic counters to DB."""
    try:
        from app.services.platform.traffic_monitor_service import TrafficMonitorService
        result = _run_async(TrafficMonitorService().aggregate_metrics())
        if result:
            logger.debug(f"Aggregated metrics for {result.get('period_start')}")
    except Exception as e:
        logger.error(f"aggregate_request_metrics failed: {e}")


@celery_app.task(name="platform.send_security_alerts")
def send_security_alerts():
    """Send email alerts for critical security events."""
    try:
        from app.services.platform.security_service import SecurityService
        count = _run_async(SecurityService().send_alerts())
        if count:
            logger.info(f"Sent {count} security alert(s)")
    except Exception as e:
        logger.error(f"send_security_alerts failed: {e}")
