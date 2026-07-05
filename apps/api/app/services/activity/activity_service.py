"""AuraFlow — Activity Service

Org-wide activity log and per-member timelines.
Actions follow dot-notation: booking.created, payment.completed, etc.
"""
import uuid
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db


# Recognized action types (not enforced at DB level, but documented here
# so callers can reference canonical values).
ACTIONS = [
    "booking.created",
    "booking.cancelled",
    "payment.completed",
    "checkin.completed",
    "membership.purchased",
    "milestone.achieved",
    "member.created",
    "class.created",
]


class ActivityService:

    async def log_activity(
        self,
        actor_type: str,
        actor_id: str | None,
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Record an activity event in the tenant's activity_log table."""
        activity_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO activity_log
                    (id, actor_type, actor_id, action,
                     resource_type, resource_id, description, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
                """,
                activity_id,
                actor_type,
                actor_id,
                action,
                resource_type,
                resource_id,
                description,
                _json_or_empty(metadata),
            )
        logger.info(
            "activity.logged",
            activity_id=activity_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
        )
        return _row_to_dict(row)

    async def get_member_timeline(
        self,
        member_id: str,
        limit: int = 50,
    ) -> list[dict]:
        """Return recent activity where the member is either the actor
        or the resource (e.g. bookings, check-ins, payments).
        """
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM activity_log
                WHERE actor_id = $1
                   OR (resource_type = 'member' AND resource_id = $1)
                ORDER BY created_at DESC
                LIMIT $2
                """,
                member_id,
                limit,
            )
        return [_row_to_dict(r) for r in rows]

    async def get_org_feed(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Return the org-wide activity feed, newest first."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM activity_log
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        return [_row_to_dict(r) for r in rows]


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
    for k in ("id", "actor_id", "resource_id"):
        if d.get(k):
            d[k] = str(d[k])
    if d.get("created_at"):
        d["created_at"] = d["created_at"].isoformat()
    return d
