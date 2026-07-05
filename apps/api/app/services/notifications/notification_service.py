"""AuraFlow — Notification Service

Create, list, read, and delete notifications for tenant users.
Includes convenience methods for common notification types
(booking confirmations, waitlist promotions, payments, etc.).
"""
import uuid
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db


class NotificationService:

    # ── Core CRUD ────────────────────────────────────────────────────────

    async def create(
        self,
        user_id: str,
        type: str,
        title: str,
        body: str | None = None,
        action_url: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Insert a new notification and return it as a dict."""
        notification_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO notifications
                    (id, user_id, type, title, body, action_url, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING *
                """,
                notification_id,
                user_id,
                type,
                title,
                body,
                action_url,
                _json_or_empty(metadata),
            )
        logger.info(
            "notification.created",
            notification_id=notification_id,
            user_id=user_id,
            type=type,
        )
        return _row_to_dict(row)

    async def list_notifications(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Return notifications for a user, newest first."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM notifications
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                user_id,
                limit,
                offset,
            )
        return [_row_to_dict(r) for r in rows]

    async def get_unread_count(self, user_id: str) -> int:
        """Return the number of unread notifications for a user."""
        async with get_tenant_db() as db:
            count = await db.fetchval(
                """
                SELECT COUNT(*) FROM notifications
                WHERE user_id = $1 AND is_read = FALSE
                """,
                user_id,
            )
        return count or 0

    async def mark_read(self, notification_id: str) -> dict | None:
        """Mark a single notification as read. Returns the updated row."""
        now = datetime.now(timezone.utc)
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE notifications
                SET is_read = TRUE, read_at = $2
                WHERE id = $1
                RETURNING *
                """,
                notification_id,
                now,
            )
        if not row:
            return None
        logger.info("notification.read", notification_id=notification_id)
        return _row_to_dict(row)

    async def mark_all_read(self, user_id: str) -> int:
        """Mark every unread notification for a user as read.
        Returns the count of notifications that were updated.
        """
        now = datetime.now(timezone.utc)
        async with get_tenant_db() as db:
            result = await db.execute(
                """
                UPDATE notifications
                SET is_read = TRUE, read_at = $2
                WHERE user_id = $1 AND is_read = FALSE
                """,
                user_id,
                now,
            )
        # asyncpg returns e.g. "UPDATE 5"
        count = int(result.split()[-1]) if result else 0
        logger.info("notification.mark_all_read", user_id=user_id, count=count)
        return count

    async def delete(self, notification_id: str) -> bool:
        """Delete a single notification. Returns True if deleted."""
        async with get_tenant_db() as db:
            result = await db.execute(
                "DELETE FROM notifications WHERE id = $1",
                notification_id,
            )
        deleted = "DELETE 1" in result
        if deleted:
            logger.info("notification.deleted", notification_id=notification_id)
        return deleted

    # ── Convenience Methods ──────────────────────────────────────────────

    async def notify_booking_confirmed(
        self,
        user_id: str,
        class_name: str,
        start_time: str,
    ) -> dict:
        """Notify a member that their booking has been confirmed."""
        return await self.create(
            user_id=user_id,
            type="booking.confirmed",
            title="Booking Confirmed",
            body=f"Your spot in {class_name} on {start_time} is confirmed.",
            action_url="/portal/bookings",
            metadata={"class_name": class_name, "start_time": start_time},
        )

    async def notify_waitlist_promoted(
        self,
        user_id: str,
        class_name: str,
    ) -> dict:
        """Notify a member that they have been moved off the waitlist."""
        return await self.create(
            user_id=user_id,
            type="waitlist.promoted",
            title="You're In!",
            body=f"A spot opened up in {class_name} and you've been booked.",
            action_url="/portal/bookings",
            metadata={"class_name": class_name},
        )

    async def notify_payment_received(
        self,
        user_id: str,
        amount_cents: int,
        description: str,
    ) -> dict:
        """Notify a member that a payment has been processed."""
        amount_str = f"${amount_cents / 100:.2f}"
        return await self.create(
            user_id=user_id,
            type="payment.received",
            title="Payment Received",
            body=f"{amount_str} payment for {description} has been processed.",
            action_url="/portal/payments",
            metadata={"amount_cents": amount_cents, "description": description},
        )

    async def notify_membership_expiring(
        self,
        user_id: str,
        membership_name: str,
        days_left: int,
    ) -> dict:
        """Notify a member that their membership is about to expire."""
        plural = "day" if days_left == 1 else "days"
        return await self.create(
            user_id=user_id,
            type="membership.expiring",
            title="Membership Expiring Soon",
            body=f"Your {membership_name} membership expires in {days_left} {plural}.",
            action_url="/portal/memberships",
            metadata={
                "membership_name": membership_name,
                "days_left": days_left,
            },
        )

    async def notify_milestone_achieved(
        self,
        user_id: str,
        milestone_name: str,
        description: str,
    ) -> dict:
        """Notify a member that they have reached a milestone."""
        return await self.create(
            user_id=user_id,
            type="milestone.achieved",
            title=f"Milestone: {milestone_name}",
            body=description,
            action_url="/portal/achievements",
            metadata={"milestone_name": milestone_name},
        )


# ── Serialization ────────────────────────────────────────────────────────

def _json_or_empty(val: dict | None) -> str:
    """Convert a dict to a JSON string for JSONB columns, defaulting to '{}'."""
    import json
    if val is None:
        return "{}"
    return json.dumps(val)


def _row_to_dict(row) -> dict:
    """Convert an asyncpg Record to a JSON-safe dict."""
    d = dict(row)
    for k in ("id", "user_id"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("created_at", "read_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d
