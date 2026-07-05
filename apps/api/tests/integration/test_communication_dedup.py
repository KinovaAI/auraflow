"""AuraFlow — Communication Dedup / Idempotency Regression Tests

These tests guard against the duplicate-email regressions Don reported in
April 2026:

  - Members getting 10x "thanks for coming" emails after class
    (`post_class` follow-up dedup was COUNT-based and broken).
  - Members getting 2x class reminder emails when the 15-min beat
    overlapped with a long task run.

The fix in both cases is the same `claim_row_once` pattern: an atomic
``UPDATE … RETURNING id`` that flips a per-booking sent_at marker only if
it's still NULL. These tests assert the pattern by running the inner
worker coroutine twice and confirming the mocked transport was called
exactly once.

If a future refactor reverts to COUNT-based dedup or removes the
``WHERE … _sent_at IS NULL`` claim guard, both tests fail loud.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _create_member(client, headers, **overrides):
    data = {
        "first_name": f"Dedup-{uuid.uuid4().hex[:6]}",
        "last_name": "Test",
        "email": f"dedup-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        **overrides,
    }
    resp = await client.post("/api/v1/members", json=data, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_session(client, headers, studio_id, starts_at):
    """Create a class type + session at the given start time. Returns session id."""
    ct = await client.post(
        "/api/v1/scheduling/class-types",
        json={"studio_id": studio_id, "name": f"Dedup-{uuid.uuid4().hex[:4]}"},
        headers=headers,
    )
    assert ct.status_code == 201, ct.text
    ct_id = ct.json()["id"]

    sess = await client.post(
        "/api/v1/scheduling/sessions",
        json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "Dedup Test Session",
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
            "capacity": 20,
        },
        headers=headers,
    )
    assert sess.status_code == 201, sess.text
    return sess.json()["id"]


async def _book(client, headers, member_id, session_id):
    resp = await client.post(
        "/api/v1/scheduling/bookings",
        json={"member_id": member_id, "class_session_id": session_id},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _schema_for(org_slug: str) -> str:
    return f"af_tenant_{org_slug.replace('-', '_')}"


# ── post-class follow-up ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPostClassFollowupIdempotency:
    """Regression: members were receiving 8-10 thank-you emails per class."""

    async def test_followup_sends_exactly_once_across_two_runs(
        self, client: AsyncClient, registered_owner_with_studio, db_pool
    ):
        from app.workers.tasks import post_class

        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]
        schema = _schema_for(org_slug)

        # Class started 25h ago so booking sits inside the 20-28h window
        # the post-class task scans.
        starts = datetime.now(timezone.utc) - timedelta(hours=25)
        session_id = await _create_session(client, headers, studio_id, starts)
        member = await _create_member(client, headers)
        booking_id = await _book(client, headers, member["id"], session_id)

        # Mark the booking attended with a check-in inside the window and
        # ensure the dedup column starts NULL.
        async with db_pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {schema}.bookings "
                f"SET status = 'attended', "
                f"    checked_in_at = NOW() - INTERVAL '24 hours', "
                f"    post_class_followup_sent_at = NULL "
                f"WHERE id = $1",
                uuid.UUID(booking_id),
            )

        send_mock = AsyncMock(return_value={"status": "sent"})
        with patch.object(post_class.email_svc, "send_email", send_mock):
            sent_first = await post_class._send_followups_for_tenant(schema)
            sent_second = await post_class._send_followups_for_tenant(schema)

        # First run sends, second run finds the booking already claimed.
        assert sent_first == 1, "first run should have sent the followup"
        assert sent_second == 0, "second run must NOT re-send"
        assert send_mock.await_count == 1, (
            f"send_email was awaited {send_mock.await_count} times — "
            f"the dedup claim is broken"
        )

        # Sanity: the claim column should be set.
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT post_class_followup_sent_at FROM {schema}.bookings "
                f"WHERE id = $1",
                uuid.UUID(booking_id),
            )
        assert row["post_class_followup_sent_at"] is not None

    async def test_followup_smtp_failure_resets_claim(
        self, client: AsyncClient, registered_owner_with_studio, db_pool
    ):
        """If send_email raises, the claim column must reset so a future
        run can retry. Without this, one transient SMTP blip silences the
        member forever."""
        from app.workers.tasks import post_class

        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]
        schema = _schema_for(org_slug)

        starts = datetime.now(timezone.utc) - timedelta(hours=25)
        session_id = await _create_session(client, headers, studio_id, starts)
        member = await _create_member(client, headers)
        booking_id = await _book(client, headers, member["id"], session_id)

        async with db_pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {schema}.bookings "
                f"SET status = 'attended', "
                f"    checked_in_at = NOW() - INTERVAL '24 hours' "
                f"WHERE id = $1",
                uuid.UUID(booking_id),
            )

        # First run: SMTP fails. Claim should reset to NULL.
        boom = AsyncMock(side_effect=RuntimeError("smtp down"))
        with patch.object(post_class.email_svc, "send_email", boom):
            await post_class._send_followups_for_tenant(schema)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT post_class_followup_sent_at FROM {schema}.bookings "
                f"WHERE id = $1",
                uuid.UUID(booking_id),
            )
        assert row["post_class_followup_sent_at"] is None, (
            "transient send failure left the claim set — task can never retry"
        )

        # Second run with working SMTP: should send exactly once.
        ok = AsyncMock(return_value={"status": "sent"})
        with patch.object(post_class.email_svc, "send_email", ok):
            sent = await post_class._send_followups_for_tenant(schema)
        assert sent == 1
        assert ok.await_count == 1


# ── class reminders ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestClassReminderIdempotency:
    """Regression: 15-min beat overlapping a long task run sent 2 reminders."""

    async def test_reminder_sends_exactly_once_across_two_runs(
        self, client: AsyncClient, registered_owner_with_studio, db_pool
    ):
        from app.workers.tasks import reminders

        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]
        schema = _schema_for(org_slug)

        # Class starts in 90 minutes — inside the 0-2h reminder window.
        starts = datetime.now(timezone.utc) + timedelta(minutes=90)
        session_id = await _create_session(client, headers, studio_id, starts)
        member = await _create_member(client, headers)
        booking_id = await _book(client, headers, member["id"], session_id)

        async with db_pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {schema}.bookings "
                f"SET reminder_sent_at = NULL "
                f"WHERE id = $1",
                uuid.UUID(booking_id),
            )

        email_mock = AsyncMock(return_value={"status": "sent"})
        sms_mock = AsyncMock(return_value={"status": "sent"})
        with patch.object(reminders.email_svc, "send_email", email_mock), \
             patch.object(reminders.sms_svc, "send_class_reminder", sms_mock):
            sent_first = await reminders._send_reminders_for_tenant(schema)
            sent_second = await reminders._send_reminders_for_tenant(schema)

        assert sent_first == 1
        assert sent_second == 0, (
            "second run re-sent the reminder — claim_row_once guard is broken"
        )
        assert email_mock.await_count == 1, (
            f"reminder email was awaited {email_mock.await_count} times"
        )

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT reminder_sent_at FROM {schema}.bookings WHERE id = $1",
                uuid.UUID(booking_id),
            )
        assert row["reminder_sent_at"] is not None

    async def test_reminder_email_failure_resets_claim(
        self, client: AsyncClient, registered_owner_with_studio, db_pool
    ):
        """SMTP failure must un-claim so the next 15-min beat retries."""
        from app.workers.tasks import reminders

        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]
        schema = _schema_for(org_slug)

        starts = datetime.now(timezone.utc) + timedelta(minutes=90)
        session_id = await _create_session(client, headers, studio_id, starts)
        member = await _create_member(client, headers)
        booking_id = await _book(client, headers, member["id"], session_id)

        boom = AsyncMock(side_effect=RuntimeError("smtp down"))
        sms_noop = AsyncMock(return_value={"status": "sent"})
        with patch.object(reminders.email_svc, "send_email", boom), \
             patch.object(reminders.sms_svc, "send_class_reminder", sms_noop):
            await reminders._send_reminders_for_tenant(schema)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT reminder_sent_at FROM {schema}.bookings WHERE id = $1",
                uuid.UUID(booking_id),
            )
        assert row["reminder_sent_at"] is None, (
            "transient email failure left reminder claim set — task can never retry"
        )
