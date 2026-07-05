"""
AuraFlow — Celery task idempotency helpers

Celery retries are non-negotiable for reliability, but naive retries cause
duplicate emails, duplicate SMS, and (worst) duplicate charges. Every task
that produces an external side effect should guard its side effect with a
durable "already-did-this" flag on the target row.

Two usage patterns:

1. **Row-flag pattern** (preferred — persistent, survives Redis flushes)

   .. code-block:: python

       from app.workers.idempotency import claim_row_once

       async def _send_reminder(db, booking_id: str):
           claimed = await claim_row_once(
               db,
               table="bookings",
               row_id=booking_id,
               flag_column="reminder_sent_at",
           )
           if not claimed:
               return False  # someone else got here first
           # ...actually send the reminder...
           return True

2. **Redis-lock pattern** (short-lived tasks, no DB-side flag)

   .. code-block:: python

       from app.workers.idempotency import acquire_once

       async def _compute_expensive_report(task_id: str):
           if not await acquire_once(f"report:{task_id}", ttl=3600):
               return {"duplicate_skipped": True}
           # ...do the work...

Both raise nothing on collision — the caller decides whether "already done"
is success (return True) or a no-op skip.
"""
from __future__ import annotations

from app.core.logging import logger


async def claim_row_once(db, table: str, row_id: str, flag_column: str) -> bool:
    """Atomically set `flag_column = NOW()` on a row *only* if it's currently NULL.

    Returns True when this task was the first to claim the flag (proceed with
    side effect), False when another worker had already claimed it (skip).

    Safe against concurrent workers due to the `WHERE flag_column IS NULL`
    guard being evaluated by Postgres under the row's update lock.
    """
    # Table + column names come from the caller — never user input — but
    # validate anyway to surface programmer errors loudly.
    _validate_ident(table)
    _validate_ident(flag_column)

    result = await db.execute(
        f"UPDATE {table} SET {flag_column} = NOW() "
        f"WHERE id = $1 AND {flag_column} IS NULL",
        row_id,
    )
    claimed = "UPDATE 1" in result
    if not claimed:
        logger.info(
            "Idempotent skip",
            table=table,
            row_id=row_id,
            flag_column=flag_column,
        )
    return claimed


async def acquire_once(key: str, ttl: int = 3600) -> bool:
    """Redis-backed once-only guard for tasks without a natural DB target row.

    Uses SETNX semantics — returns True iff the key didn't already exist.
    Key auto-expires after `ttl` seconds so a crashed task doesn't permanently
    block future executions.

    Use `claim_row_once` when possible — Redis loses state on flushall, the
    DB flag is permanent.
    """
    from app.core.redis import get_redis
    redis = await get_redis()
    if not redis:
        # Without Redis there's nothing we can safely deduplicate against.
        # Default to letting the task run — reliability over strict dedup.
        return True
    # NX = only set if not exists, EX = expire after ttl seconds
    result = await redis.set(f"idem:{key}", "1", nx=True, ex=ttl)
    acquired = result is True or result == 1
    if not acquired:
        logger.info("Idempotent skip (redis)", key=key)
    return acquired


def _validate_ident(name: str) -> None:
    """Allow only [a-zA-Z0-9_]+ to prevent SQL injection via format string."""
    if not name or not all(c.isalnum() or c == "_" for c in name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
