"""AuraFlow — Webhook Delivery Service

Manages outbound webhook configs, delivery attempts with exponential back-off,
HMAC-SHA256 signing, and dead-letter handling.
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone, timedelta

import httpx

from app.core.logging import logger
from app.db.session import get_tenant_db

# Back-off delays between retries (seconds): 1s, 5s, 30s, 2min, 15min
RETRY_DELAYS = [1, 5, 30, 120, 900]

# HTTP timeout for outbound webhook calls
DELIVERY_TIMEOUT = 10.0


class WebhookDeliveryService:
    """Manages webhook configuration, delivery, and retry logic."""

    # ── Signing ─────────────────────────────────────────────────────────

    def _sign_payload(self, payload: str, secret: str) -> str:
        """Legacy HMAC-SHA256 hex-digest (body only).

        Retained for backwards compatibility with existing `X-Webhook-Signature`
        consumers. New integrations should verify against `X-AuraFlow-Signature`
        which includes a timestamp for replay protection.
        """
        return hmac.new(
            secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

    def _sign_payload_v2(
        self, payload: str, secret: str, timestamp: int
    ) -> str:
        """Stripe-compatible signature: HMAC-SHA256 over `{timestamp}.{body}`.

        Payload the recipient verifies is the concatenation of the unix timestamp,
        a literal `.`, and the raw JSON body. Header format is:

            X-AuraFlow-Signature: t=<timestamp>,v1=<hex>

        Recipients SHOULD reject requests with a timestamp older than 5 minutes
        to defeat replay attacks.
        """
        signed = f"{timestamp}.{payload}"
        digest = hmac.new(
            secret.encode(), signed.encode(), hashlib.sha256
        ).hexdigest()
        return f"t={timestamp},v1={digest}"

    # ── Event Firing ────────────────────────────────────────────────────

    async def fire_event(self, event_type: str, payload: dict) -> list[str]:
        """Find active configs subscribing to *event_type*, create delivery
        records, and attempt the first send for each.

        Returns a list of delivery IDs that were created.
        """
        async with get_tenant_db() as db:
            configs = await db.fetch(
                """
                SELECT id, url, secret, events
                FROM webhook_configs
                WHERE is_active = TRUE
                """,
            )

        delivery_ids: list[str] = []
        for cfg in configs:
            events = cfg["events"] or []
            # Match if config subscribes to this event or uses wildcard '*'
            if event_type not in events and "*" not in events:
                continue

            delivery_id = str(uuid.uuid4())
            payload_json = json.dumps(payload, default=str)

            async with get_tenant_db() as db:
                await db.execute(
                    """
                    INSERT INTO webhook_deliveries
                        (id, webhook_config_id, event_type, payload, status,
                         attempt_count, max_attempts)
                    VALUES ($1, $2, $3, $4::jsonb, 'pending', 0, $5)
                    """,
                    delivery_id,
                    str(cfg["id"]),
                    event_type,
                    payload_json,
                    len(RETRY_DELAYS) + 1,
                )

            delivery_ids.append(delivery_id)

            # Attempt first delivery immediately
            try:
                await self.attempt_delivery(delivery_id)
            except Exception as exc:
                logger.warning(
                    "Webhook first attempt failed",
                    delivery_id=delivery_id,
                    error=str(exc),
                )

        return delivery_ids

    # ── Delivery Attempt ────────────────────────────────────────────────

    async def attempt_delivery(self, delivery_id: str) -> bool:
        """Attempt to deliver a webhook. Returns True on success (2xx)."""
        async with get_tenant_db() as db:
            delivery = await db.fetchrow(
                """
                SELECT d.id, d.event_type, d.payload, d.attempt_count,
                       d.max_attempts, d.status,
                       c.url, c.secret
                FROM webhook_deliveries d
                JOIN webhook_configs c ON c.id = d.webhook_config_id
                WHERE d.id = $1
                """,
                delivery_id,
            )

        if not delivery:
            logger.warning("Webhook delivery not found", delivery_id=delivery_id)
            return False

        url = delivery["url"]
        payload_str = json.dumps(
            delivery["payload"] if isinstance(delivery["payload"], dict)
            else json.loads(delivery["payload"]),
            default=str,
        )
        secret = delivery["secret"]
        attempt = delivery["attempt_count"] + 1
        max_attempts = delivery["max_attempts"]

        # Both the v2 signature header and the success/failure UPDATEs need
        # the same timestamp; assign once up top so the header block can use
        # it without an UnboundLocalError.
        now = datetime.now(timezone.utc)

        # Build headers
        timestamp = int(now.timestamp())
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": delivery["event_type"],
            "X-AuraFlow-Event": delivery["event_type"],
            "X-AuraFlow-Event-Id": delivery_id,  # idempotency key for recipients
            "X-AuraFlow-Timestamp": str(timestamp),
            "User-Agent": "AuraFlow-Webhook/1.0",
        }
        if secret:
            # Legacy header — body-only HMAC, kept for backwards compatibility
            headers["X-Webhook-Signature"] = self._sign_payload(payload_str, secret)
            # New header — Stripe-compatible, replay-protected
            headers["X-AuraFlow-Signature"] = self._sign_payload_v2(
                payload_str, secret, timestamp
            )

        response_status = None
        response_body = None
        error_message = None
        success = False

        try:
            async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT) as client:
                resp = await client.post(url, content=payload_str, headers=headers)
            response_status = resp.status_code
            response_body = resp.text[:2000]  # cap stored body
            success = 200 <= resp.status_code < 300
        except httpx.TimeoutException:
            error_message = "Request timed out"
        except httpx.ConnectError as exc:
            error_message = f"Connection error: {exc}"
        except Exception as exc:
            error_message = f"Unexpected error: {exc}"

        if success:
            async with get_tenant_db() as db:
                await db.execute(
                    """
                    UPDATE webhook_deliveries
                    SET status = 'delivered',
                        response_status = $2,
                        response_body = $3,
                        attempt_count = $4,
                        last_attempt_at = $5,
                        delivered_at = $5,
                        error_message = NULL
                    WHERE id = $1
                    """,
                    delivery_id,
                    response_status,
                    response_body,
                    attempt,
                    now,
                )
            logger.info(
                "Webhook delivered",
                delivery_id=delivery_id,
                url=url,
                status=response_status,
            )
            return True

        # Failure path — schedule retry or mark dead_letter
        retry_index = attempt - 1  # 0-based index into RETRY_DELAYS
        if retry_index < len(RETRY_DELAYS) and attempt < max_attempts:
            next_retry = now + timedelta(seconds=RETRY_DELAYS[retry_index])
            new_status = "failed"
        else:
            next_retry = None
            new_status = "dead_letter"

        async with get_tenant_db() as db:
            await db.execute(
                """
                UPDATE webhook_deliveries
                SET status = $2,
                    response_status = $3,
                    response_body = $4,
                    attempt_count = $5,
                    last_attempt_at = $6,
                    next_retry_at = $7,
                    error_message = $8
                WHERE id = $1
                """,
                delivery_id,
                new_status,
                response_status,
                response_body,
                attempt,
                now,
                next_retry,
                error_message or f"HTTP {response_status}",
            )

        logger.warning(
            "Webhook delivery failed",
            delivery_id=delivery_id,
            url=url,
            attempt=attempt,
            status=new_status,
            error=error_message,
        )
        return False

    # ── Retry Processing ────────────────────────────────────────────────

    async def process_retries(self) -> int:
        """Find deliveries due for retry and attempt them.

        Returns the number of deliveries processed.
        """
        now = datetime.now(timezone.utc)
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT id FROM webhook_deliveries
                WHERE status = 'failed'
                  AND next_retry_at IS NOT NULL
                  AND next_retry_at <= $1
                ORDER BY next_retry_at
                LIMIT 100
                """,
                now,
            )

        processed = 0
        for row in rows:
            try:
                await self.attempt_delivery(str(row["id"]))
                processed += 1
            except Exception as exc:
                logger.warning(
                    "Webhook retry processing error",
                    delivery_id=str(row["id"]),
                    error=str(exc),
                )
                processed += 1  # still counts as processed

        if processed:
            logger.info("Webhook retries processed", count=processed)
        return processed

    # ── Config CRUD ─────────────────────────────────────────────────────

    async def list_configs(self) -> list[dict]:
        """List all webhook configurations."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM webhook_configs
                ORDER BY created_at DESC
                """,
            )
        return [_config_to_dict(r) for r in rows]

    async def create_config(
        self,
        url: str,
        events: list[str],
        secret: str | None = None,
        created_by: str | None = None,
    ) -> dict:
        """Create a new webhook configuration."""
        config_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO webhook_configs
                    (id, url, secret, events, is_active, created_by)
                VALUES ($1, $2, $3, $4, TRUE, $5)
                """,
                config_id,
                url,
                secret,
                events,
                created_by,
            )
            row = await db.fetchrow(
                "SELECT * FROM webhook_configs WHERE id = $1",
                config_id,
            )
        logger.info("Webhook config created", config_id=config_id, url=url)
        return _config_to_dict(row)

    async def update_config(self, config_id: str, data: dict) -> dict | None:
        """Update a webhook configuration. Returns None if not found."""
        allowed = {"url", "secret", "events", "is_active"}
        updates = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not updates:
            async with get_tenant_db() as db:
                row = await db.fetchrow(
                    "SELECT * FROM webhook_configs WHERE id = $1", config_id
                )
            return _config_to_dict(row) if row else None

        set_clauses = []
        params: list = [config_id]
        idx = 2
        for key, val in updates.items():
            set_clauses.append(f"{key} = ${idx}")
            params.append(val)
            idx += 1
        set_clauses.append("updated_at = NOW()")

        async with get_tenant_db() as db:
            result = await db.execute(
                f"UPDATE webhook_configs SET {', '.join(set_clauses)} WHERE id = $1",
                *params,
            )
            if "UPDATE 0" in result:
                return None
            row = await db.fetchrow(
                "SELECT * FROM webhook_configs WHERE id = $1", config_id
            )
        logger.info("Webhook config updated", config_id=config_id)
        return _config_to_dict(row)

    async def delete_config(self, config_id: str) -> bool:
        """Delete a webhook configuration (hard delete, cascades deliveries)."""
        async with get_tenant_db() as db:
            result = await db.execute(
                "DELETE FROM webhook_configs WHERE id = $1",
                config_id,
            )
        deleted = "DELETE 1" in result
        if deleted:
            logger.info("Webhook config deleted", config_id=config_id)
        return deleted

    # ── Delivery Queries ────────────────────────────────────────────────

    async def list_deliveries(
        self,
        config_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List deliveries with optional filters."""
        conditions = []
        params: list = []
        idx = 1

        if config_id:
            conditions.append(f"webhook_config_id = ${idx}")
            params.append(config_id)
            idx += 1
        if status:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(min(limit, 200))

        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"""
                SELECT * FROM webhook_deliveries
                {where}
                ORDER BY created_at DESC
                LIMIT ${idx}
                """,
                *params,
            )
        return [_delivery_to_dict(r) for r in rows]

    async def retry_delivery(self, delivery_id: str) -> dict | None:
        """Manually reset a delivery for retry. Returns None if not found."""
        now = datetime.now(timezone.utc)
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM webhook_deliveries WHERE id = $1",
                delivery_id,
            )
            if not row:
                return None

            # Reset status to pending for immediate retry
            await db.execute(
                """
                UPDATE webhook_deliveries
                SET status = 'pending',
                    next_retry_at = NULL,
                    error_message = NULL
                WHERE id = $1
                """,
                delivery_id,
            )

        # Attempt delivery now
        success = await self.attempt_delivery(delivery_id)

        async with get_tenant_db() as db:
            updated = await db.fetchrow(
                "SELECT * FROM webhook_deliveries WHERE id = $1",
                delivery_id,
            )
        return _delivery_to_dict(updated) if updated else None


# ── Serialization Helpers ──────────────────────────────────────────────


def _config_to_dict(row) -> dict:
    """Convert a webhook_configs row to a JSON-safe dict."""
    d = dict(row)
    for k in ("id", "created_by"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    # events is a PG text[] — ensure it's a list
    if d.get("events") and not isinstance(d["events"], list):
        d["events"] = list(d["events"])
    return d


def _delivery_to_dict(row) -> dict:
    """Convert a webhook_deliveries row to a JSON-safe dict."""
    d = dict(row)
    for k in ("id", "webhook_config_id"):
        if d.get(k):
            d[k] = str(d[k])
    for k in (
        "next_retry_at",
        "last_attempt_at",
        "delivered_at",
        "created_at",
    ):
        if d.get(k):
            d[k] = d[k].isoformat()
    # Ensure payload is a dict (not a string)
    if isinstance(d.get("payload"), str):
        try:
            d["payload"] = json.loads(d["payload"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d
