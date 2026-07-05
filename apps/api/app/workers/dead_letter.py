"""
AuraFlow — Celery Dead-Letter Queue

Any task that exhausts its retry budget gets persisted to
`af_global.dead_letter_tasks` with full context (task_name, args,
traceback) so on-call can review and decide to replay, ignore, or
investigate. Replaces the silent-drop behaviour where exhausted tasks
just vanished into the void.
"""
import asyncio
import json
import uuid

from celery.signals import task_failure

from app.core.logging import logger


def _serialize(obj):
    try:
        return json.loads(json.dumps(obj, default=str))
    except Exception:
        return str(obj)


async def _persist(sender_name: str, task_id: str, args, kwargs, einfo):
    from app.db.session import get_global_db
    async with get_global_db() as db:
        await db.execute(
            """
            INSERT INTO af_global.dead_letter_tasks
                (id, task_name, task_id, args, kwargs, exception, traceback, failed_at)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, NOW())
            ON CONFLICT (task_id) DO NOTHING
            """,
            str(uuid.uuid4()),
            sender_name,
            task_id,
            json.dumps(_serialize(args)),
            json.dumps(_serialize(kwargs)),
            str(einfo.exception) if einfo else None,
            str(einfo.traceback) if einfo else None,
        )


@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, args=None,
                    kwargs=None, traceback=None, einfo=None, **_):
    """Celery signal fires once per task failure. We only dead-letter tasks
    that have exhausted their retries — Celery attaches `retries` to the
    task's request; if max_retries reached, task is done for good."""
    try:
        # Determine whether this failure was the final attempt.
        task = sender
        retries_so_far = getattr(
            getattr(task, "request", None), "retries", 0
        ) or 0
        max_retries = (
            getattr(task, "max_retries", None)
            if task is not None
            else None
        )
        # If the task still has retries left, don't dead-letter — it'll
        # be retried automatically by Celery.
        if max_retries is not None and retries_so_far < max_retries:
            return

        sender_name = getattr(task, "name", str(task))
        logger.warning(
            "Task exhausted retries — dead-lettering",
            task_name=sender_name,
            task_id=task_id,
            exception=str(exception),
        )

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                _persist(sender_name, task_id, args, kwargs, einfo)
            )
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()
    except Exception as exc:
        # Never let the DLQ handler itself raise — we already had one failure.
        logger.warning("Dead-letter persist failed", error=str(exc))
