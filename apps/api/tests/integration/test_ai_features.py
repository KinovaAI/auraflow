"""AuraFlow — AI Features Integration Tests

Churn detection, milestones, and marketing drafts.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _create_member(client, headers, **overrides):
    data = {
        "first_name": f"Test-{uuid.uuid4().hex[:6]}",
        "last_name": "Member",
        "email": f"member-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        **overrides,
    }
    resp = await client.post("/api/v1/members", json=data, headers=headers)
    assert resp.status_code == 201
    return resp.json()


async def _create_class_and_session(client, headers, studio_id):
    """Create a class type + session for booking tests."""
    cls_resp = await client.post("/api/v1/scheduling/class-types", json={
        "studio_id": studio_id,
        "name": f"Flow-{uuid.uuid4().hex[:4]}",
    }, headers=headers)
    assert cls_resp.status_code == 201
    class_type_id = cls_resp.json()["id"]

    starts = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    ends = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    sess_resp = await client.post("/api/v1/scheduling/sessions", json={
        "class_type_id": class_type_id,
        "studio_id": studio_id,
        "title": "Test Session",
        "starts_at": starts,
        "ends_at": ends,
        "capacity": 20,
    }, headers=headers)
    assert sess_resp.status_code == 201
    return sess_resp.json()["id"]


# ── Churn Detection ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestChurnDetection:

    async def test_churn_scan_flags_inactive_member(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        """Member with no visits in 21+ days and total_visits > 0 gets flagged."""
        headers = registered_owner_with_studio["headers"]
        org_slug = registered_owner_with_studio["org_slug"]
        member = await _create_member(client, headers)
        member_id = member["id"]
        schema = f"af_tenant_{org_slug.replace('-', '_')}"

        # Simulate member with visits but last visit 25 days ago
        async with db_pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {schema}.members SET total_visits = 5, is_active = TRUE, "
                f"last_visit_at = NOW() - INTERVAL '25 days' WHERE id = $1",
                uuid.UUID(member_id),
            )

        # Run churn scan
        resp = await client.post("/api/v1/ai/churn-scan", headers=headers)
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["newly_flagged"] >= 1

        # Verify member is in flagged list
        flagged_ids = [m["id"] for m in result["flagged_members"]]
        assert member_id in flagged_ids

    async def test_churn_scan_clears_returned_member(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        """Member who visited recently has their churn flag cleared."""
        headers = registered_owner_with_studio["headers"]
        org_slug = registered_owner_with_studio["org_slug"]
        member = await _create_member(client, headers)
        member_id = member["id"]
        schema = f"af_tenant_{org_slug.replace('-', '_')}"

        # Flag the member, then simulate a recent visit
        async with db_pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {schema}.members SET churn_risk_flagged_at = NOW() - INTERVAL '5 days', "
                f"last_visit_at = NOW() - INTERVAL '1 day', total_visits = 3 WHERE id = $1",
                uuid.UUID(member_id),
            )

        # Run scan — should clear the flag
        resp = await client.post("/api/v1/ai/churn-scan", headers=headers)
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["cleared"] >= 1

    async def test_list_at_risk_members(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        """GET /ai/churn-risk returns flagged members."""
        headers = registered_owner_with_studio["headers"]
        org_slug = registered_owner_with_studio["org_slug"]
        member = await _create_member(client, headers)
        member_id = member["id"]
        schema = f"af_tenant_{org_slug.replace('-', '_')}"

        # Flag the member
        async with db_pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {schema}.members SET churn_risk_flagged_at = NOW(), "
                f"is_active = TRUE, total_visits = 10 WHERE id = $1",
                uuid.UUID(member_id),
            )

        resp = await client.get("/api/v1/ai/churn-risk", headers=headers)
        assert resp.status_code == 200
        members = resp.json()["data"]
        assert any(m["id"] == member_id for m in members)

    async def test_dismiss_churn_flag(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        """POST /ai/churn-risk/{id}/dismiss clears the flag."""
        headers = registered_owner_with_studio["headers"]
        org_slug = registered_owner_with_studio["org_slug"]
        member = await _create_member(client, headers)
        member_id = member["id"]
        schema = f"af_tenant_{org_slug.replace('-', '_')}"

        # Flag the member
        async with db_pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {schema}.members SET churn_risk_flagged_at = NOW() WHERE id = $1",
                uuid.UUID(member_id),
            )

        resp = await client.post(f"/api/v1/ai/churn-risk/{member_id}/dismiss", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "dismissed"

        # Verify flag is cleared
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT churn_risk_flagged_at FROM {schema}.members WHERE id = $1",
                uuid.UUID(member_id),
            )
            assert row["churn_risk_flagged_at"] is None

    async def test_send_winback_outreach(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        """POST /ai/churn-risk/{id}/outreach sends winback (mocked)."""
        headers = registered_owner_with_studio["headers"]
        member = await _create_member(client, headers, phone="+15551234567")
        member_id = member["id"]

        with patch("app.services.ai.churn_service.email_svc.send_email", new_callable=AsyncMock) as mock_email, \
             patch("app.services.ai.churn_service.sms_svc.send_sms", new_callable=AsyncMock) as mock_sms:
            resp = await client.post(f"/api/v1/ai/churn-risk/{member_id}/outreach", headers=headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["member_id"] == member_id
        assert "email" in data["channels"]
        assert "sms" in data["channels"]


# ── Milestones ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestMilestones:

    async def test_first_visit_milestone(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        """Check-in at visit 1 creates a milestone."""
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]
        member = await _create_member(client, headers)
        member_id = member["id"]
        schema = f"af_tenant_{org_slug.replace('-', '_')}"

        session_id = await _create_class_and_session(client, headers, studio_id)

        # Book the member
        book_resp = await client.post("/api/v1/scheduling/bookings", json={
            "member_id": member_id,
            "class_session_id": session_id,
        }, headers=headers)
        assert book_resp.status_code == 201
        booking_id = book_resp.json()["id"]

        # Mock notification services to prevent actual sends
        with patch("app.services.ai.milestone_service.email_svc.send_email", new_callable=AsyncMock), \
             patch("app.services.ai.milestone_service.sms_svc.send_sms", new_callable=AsyncMock), \
             patch("app.services.scheduling.booking_service.EmailService"), \
             patch("app.services.scheduling.booking_service.SmsService"):
            check_resp = await client.post(
                f"/api/v1/scheduling/bookings/{booking_id}/check-in", headers=headers,
            )
        assert check_resp.status_code == 200

        # Verify milestone was created
        ms_resp = await client.get(f"/api/v1/ai/milestones/{member_id}", headers=headers)
        assert ms_resp.status_code == 200
        milestones = ms_resp.json()["data"]
        types = [m["milestone_type"] for m in milestones]
        assert "visit_1" in types

    async def test_tenth_visit_milestone(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        """Member at visit_count=9 who checks in gets visit_10 milestone."""
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]
        member = await _create_member(client, headers)
        member_id = member["id"]
        schema = f"af_tenant_{org_slug.replace('-', '_')}"

        # Set total_visits to 9 so check-in bumps to 10
        async with db_pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {schema}.members SET total_visits = 9 WHERE id = $1",
                uuid.UUID(member_id),
            )

        session_id = await _create_class_and_session(client, headers, studio_id)

        book_resp = await client.post("/api/v1/scheduling/bookings", json={
            "member_id": member_id,
            "class_session_id": session_id,
        }, headers=headers)
        assert book_resp.status_code == 201
        booking_id = book_resp.json()["id"]

        with patch("app.services.ai.milestone_service.email_svc.send_email", new_callable=AsyncMock), \
             patch("app.services.ai.milestone_service.sms_svc.send_sms", new_callable=AsyncMock), \
             patch("app.services.scheduling.booking_service.EmailService"), \
             patch("app.services.scheduling.booking_service.SmsService"):
            check_resp = await client.post(
                f"/api/v1/scheduling/bookings/{booking_id}/check-in", headers=headers,
            )
        assert check_resp.status_code == 200

        ms_resp = await client.get(f"/api/v1/ai/milestones/{member_id}", headers=headers)
        assert ms_resp.status_code == 200
        milestones = ms_resp.json()["data"]
        types = [m["milestone_type"] for m in milestones]
        assert "visit_10" in types

    async def test_no_duplicate_milestone(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        """Checking in at visit_1 twice doesn't create duplicate milestones."""
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]
        member = await _create_member(client, headers)
        member_id = member["id"]
        schema = f"af_tenant_{org_slug.replace('-', '_')}"

        # Pre-insert a visit_1 milestone directly
        ms_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {schema}.member_milestones (id, member_id, milestone_type) "
                f"VALUES ($1, $2, 'visit_1')",
                uuid.UUID(ms_id), uuid.UUID(member_id),
            )

        # Now do a real check-in that would trigger visit_1 again
        session_id = await _create_class_and_session(client, headers, studio_id)
        book_resp = await client.post("/api/v1/scheduling/bookings", json={
            "member_id": member_id,
            "class_session_id": session_id,
        }, headers=headers)
        assert book_resp.status_code == 201
        booking_id = book_resp.json()["id"]

        with patch("app.services.ai.milestone_service.email_svc.send_email", new_callable=AsyncMock), \
             patch("app.services.ai.milestone_service.sms_svc.send_sms", new_callable=AsyncMock), \
             patch("app.services.scheduling.booking_service.EmailService"), \
             patch("app.services.scheduling.booking_service.SmsService"):
            await client.post(f"/api/v1/scheduling/bookings/{booking_id}/check-in", headers=headers)

        # Verify only one visit_1 milestone exists (no duplicate)
        ms_resp = await client.get(f"/api/v1/ai/milestones/{member_id}", headers=headers)
        milestones = ms_resp.json()["data"]
        visit_1_count = sum(1 for m in milestones if m["milestone_type"] == "visit_1")
        assert visit_1_count == 1

    async def test_milestone_list_endpoint(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        """GET /ai/milestones/{member_id} returns milestones."""
        headers = registered_owner_with_studio["headers"]
        org_slug = registered_owner_with_studio["org_slug"]
        member = await _create_member(client, headers)
        member_id = member["id"]
        schema = f"af_tenant_{org_slug.replace('-', '_')}"

        # Insert milestones directly
        async with db_pool.acquire() as conn:
            for mt in ("visit_1", "visit_10"):
                await conn.execute(
                    f"INSERT INTO {schema}.member_milestones (id, member_id, milestone_type) "
                    f"VALUES ($1, $2, $3)",
                    uuid.uuid4(), uuid.UUID(member_id), mt,
                )

        resp = await client.get(f"/api/v1/ai/milestones/{member_id}", headers=headers)
        assert resp.status_code == 200
        milestones = resp.json()["data"]
        assert len(milestones) == 2
        types = {m["milestone_type"] for m in milestones}
        assert types == {"visit_1", "visit_10"}


# ── Marketing Drafts ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestMarketingDrafts:

    async def test_create_draft(self, client: AsyncClient, registered_owner_with_studio):
        """POST /ai/drafts generates and saves a draft (mocked Claude)."""
        headers = registered_owner_with_studio["headers"]

        with patch("app.services.ai.ai_service.AIService._call_claude", new_callable=AsyncMock) as mock_claude:
            mock_claude.return_value = "Subject: Spring Sale\n\nJoin us for amazing spring deals!"
            resp = await client.post("/api/v1/ai/drafts", json={
                "prompt_context": "Spring promotion for yoga classes",
                "draft_type": "email",
            }, headers=headers)

        assert resp.status_code == 201
        draft = resp.json()["data"]
        assert draft["draft_type"] == "email"
        assert draft["status"] == "draft"
        assert draft["prompt_context"] == "Spring promotion for yoga classes"
        assert draft["body"]  # Should have content

    async def test_list_drafts(self, client: AsyncClient, registered_owner_with_studio):
        """GET /ai/drafts returns all drafts."""
        headers = registered_owner_with_studio["headers"]

        # Create 2 drafts
        with patch("app.services.ai.ai_service.AIService._call_claude", new_callable=AsyncMock) as mock_claude:
            mock_claude.return_value = "Subject: Test\n\nBody content"
            await client.post("/api/v1/ai/drafts", json={
                "prompt_context": "Draft 1", "draft_type": "email",
            }, headers=headers)
            mock_claude.return_value = "Social post content #yoga"
            await client.post("/api/v1/ai/drafts", json={
                "prompt_context": "Draft 2", "draft_type": "social",
            }, headers=headers)

        resp = await client.get("/api/v1/ai/drafts", headers=headers)
        assert resp.status_code == 200
        drafts = resp.json()["data"]
        assert len(drafts) >= 2

    async def test_list_drafts_filter_status(self, client: AsyncClient, registered_owner_with_studio):
        """GET /ai/drafts?status=draft filters by status."""
        headers = registered_owner_with_studio["headers"]

        with patch("app.services.ai.ai_service.AIService._call_claude", new_callable=AsyncMock) as mock_claude:
            mock_claude.return_value = "Subject: Test\n\nBody"
            await client.post("/api/v1/ai/drafts", json={
                "prompt_context": "Test draft", "draft_type": "email",
            }, headers=headers)

        resp = await client.get("/api/v1/ai/drafts?status=draft", headers=headers)
        assert resp.status_code == 200
        drafts = resp.json()["data"]
        assert all(d["status"] == "draft" for d in drafts)

    async def test_update_draft(self, client: AsyncClient, registered_owner_with_studio):
        """PUT /ai/drafts/{id} updates subject/body."""
        headers = registered_owner_with_studio["headers"]

        with patch("app.services.ai.ai_service.AIService._call_claude", new_callable=AsyncMock) as mock_claude:
            mock_claude.return_value = "Subject: Original\n\nOriginal body"
            create_resp = await client.post("/api/v1/ai/drafts", json={
                "prompt_context": "Test", "draft_type": "email",
            }, headers=headers)

        draft_id = create_resp.json()["data"]["id"]

        update_resp = await client.put(f"/api/v1/ai/drafts/{draft_id}", json={
            "subject": "Updated Subject",
            "body": "Updated body content",
        }, headers=headers)
        assert update_resp.status_code == 200
        updated = update_resp.json()["data"]
        assert updated["subject"] == "Updated Subject"
        assert updated["body"] == "Updated body content"

    async def test_approve_draft(self, client: AsyncClient, registered_owner_with_studio):
        """POST /ai/drafts/{id}/approve sets status to approved."""
        headers = registered_owner_with_studio["headers"]

        with patch("app.services.ai.ai_service.AIService._call_claude", new_callable=AsyncMock) as mock_claude:
            mock_claude.return_value = "Subject: Approve Me\n\nGreat content"
            create_resp = await client.post("/api/v1/ai/drafts", json={
                "prompt_context": "Approval test", "draft_type": "email",
            }, headers=headers)

        draft_id = create_resp.json()["data"]["id"]

        approve_resp = await client.post(f"/api/v1/ai/drafts/{draft_id}/approve", headers=headers)
        assert approve_resp.status_code == 200
        draft = approve_resp.json()["data"]
        assert draft["status"] == "approved"
        assert draft["reviewed_by"] is not None
        assert draft["reviewed_at"] is not None

    async def test_reject_draft(self, client: AsyncClient, registered_owner_with_studio):
        """POST /ai/drafts/{id}/reject sets status to rejected."""
        headers = registered_owner_with_studio["headers"]

        with patch("app.services.ai.ai_service.AIService._call_claude", new_callable=AsyncMock) as mock_claude:
            mock_claude.return_value = "Subject: Reject Me\n\nBad content"
            create_resp = await client.post("/api/v1/ai/drafts", json={
                "prompt_context": "Rejection test", "draft_type": "email",
            }, headers=headers)

        draft_id = create_resp.json()["data"]["id"]

        reject_resp = await client.post(f"/api/v1/ai/drafts/{draft_id}/reject", headers=headers)
        assert reject_resp.status_code == 200
        draft = reject_resp.json()["data"]
        assert draft["status"] == "rejected"
        assert draft["reviewed_by"] is not None
