"""AuraFlow — Workshops & Courses Integration Tests

Tests course CRUD, publish/cancel lifecycle, sessions, enrollment
(capacity, early bird pricing, duplicates), withdrawal, attendance,
and course completion.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestCourseCRUD:

    async def test_create_workshop(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        resp = await client.post("/api/v1/courses", json={
            "title": "Weekend Yoga Workshop",
            "description": "Intensive weekend workshop",
            "type": "workshop",
            "price_cents": 15000,
            "capacity": 20,
            "location": "Main Studio",
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Weekend Yoga Workshop"
        assert data["type"] == "workshop"
        assert data["price_cents"] == 15000
        assert data["status"] == "draft"

    async def test_create_teacher_training(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        resp = await client.post("/api/v1/courses", json={
            "title": "200hr Teacher Training",
            "type": "teacher_training",
            "price_cents": 350000,
            "capacity": 15,
        }, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["data"]["type"] == "teacher_training"

    async def test_list_courses(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        await client.post("/api/v1/courses", json={
            "title": "Course A",
            "price_cents": 5000,
        }, headers=headers)
        await client.post("/api/v1/courses", json={
            "title": "Course B",
            "type": "retreat",
            "price_cents": 50000,
        }, headers=headers)

        resp = await client.get("/api/v1/courses", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 2

    async def test_get_course(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/courses", json={
            "title": "Get Test",
            "price_cents": 5000,
        }, headers=headers)
        course_id = create.json()["data"]["id"]

        resp = await client.get(f"/api/v1/courses/{course_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Get Test"

    async def test_update_course(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/courses", json={
            "title": "Old Title",
            "price_cents": 5000,
        }, headers=headers)
        course_id = create.json()["data"]["id"]

        resp = await client.put(f"/api/v1/courses/{course_id}", json={
            "title": "Updated Title",
            "price_cents": 7500,
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Updated Title"
        assert resp.json()["data"]["price_cents"] == 7500


@pytest.mark.asyncio
class TestCourseLifecycle:

    async def test_publish_course(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/courses", json={
            "title": "Publish Test",
            "price_cents": 10000,
        }, headers=headers)
        course_id = create.json()["data"]["id"]

        resp = await client.post(f"/api/v1/courses/{course_id}/publish", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "published"

    async def test_cancel_course(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/courses", json={
            "title": "Cancel Test",
            "price_cents": 10000,
        }, headers=headers)
        course_id = create.json()["data"]["id"]

        resp = await client.post(f"/api/v1/courses/{course_id}/cancel", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelled"

    async def test_complete_course(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/courses", json={
            "title": "Complete Test",
            "price_cents": 10000,
        }, headers=headers)
        course_id = create.json()["data"]["id"]

        # Publish first
        await client.post(f"/api/v1/courses/{course_id}/publish", headers=headers)

        # Complete
        resp = await client.post(f"/api/v1/courses/{course_id}/complete", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "completed"

    async def test_cannot_publish_cancelled(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        create = await client.post("/api/v1/courses", json={
            "title": "Already Cancelled",
            "price_cents": 10000,
        }, headers=headers)
        course_id = create.json()["data"]["id"]

        await client.post(f"/api/v1/courses/{course_id}/cancel", headers=headers)

        resp = await client.post(f"/api/v1/courses/{course_id}/publish", headers=headers)
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestCourseSessions:

    async def _create_course(self, client, headers):
        resp = await client.post("/api/v1/courses", json={
            "title": f"Session Test-{uuid.uuid4().hex[:6]}",
            "price_cents": 10000,
        }, headers=headers)
        return resp.json()["data"]["id"]

    async def test_add_sessions(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        course_id = await self._create_course(client, headers)

        s1 = await client.post(f"/api/v1/courses/{course_id}/sessions", json={
            "title": "Session 1",
            "starts_at": "2026-04-01T09:00:00",
            "ends_at": "2026-04-01T12:00:00",
        }, headers=headers)
        assert s1.status_code == 201
        assert s1.json()["data"]["session_number"] == 1

        s2 = await client.post(f"/api/v1/courses/{course_id}/sessions", json={
            "title": "Session 2",
            "starts_at": "2026-04-02T09:00:00",
            "ends_at": "2026-04-02T12:00:00",
        }, headers=headers)
        assert s2.status_code == 201
        assert s2.json()["data"]["session_number"] == 2

    async def test_list_sessions(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        course_id = await self._create_course(client, headers)

        await client.post(f"/api/v1/courses/{course_id}/sessions", json={
            "title": "Sess A",
            "starts_at": "2026-04-05T09:00:00",
            "ends_at": "2026-04-05T12:00:00",
        }, headers=headers)
        await client.post(f"/api/v1/courses/{course_id}/sessions", json={
            "title": "Sess B",
            "starts_at": "2026-04-06T09:00:00",
            "ends_at": "2026-04-06T12:00:00",
        }, headers=headers)

        resp = await client.get(f"/api/v1/courses/{course_id}/sessions", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    async def test_update_session(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        course_id = await self._create_course(client, headers)

        create = await client.post(f"/api/v1/courses/{course_id}/sessions", json={
            "title": "Old Session",
            "starts_at": "2026-04-10T09:00:00",
            "ends_at": "2026-04-10T12:00:00",
        }, headers=headers)
        session_id = create.json()["data"]["id"]

        resp = await client.put(f"/api/v1/courses/sessions/{session_id}", json={
            "title": "Updated Session",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Updated Session"

    async def test_delete_session(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        course_id = await self._create_course(client, headers)

        create = await client.post(f"/api/v1/courses/{course_id}/sessions", json={
            "title": "To Delete",
            "starts_at": "2026-04-15T09:00:00",
            "ends_at": "2026-04-15T12:00:00",
        }, headers=headers)
        session_id = create.json()["data"]["id"]

        resp = await client.delete(f"/api/v1/courses/sessions/{session_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True


@pytest.mark.asyncio
class TestCourseEnrollment:

    async def _setup(self, client, headers):
        course_resp = await client.post("/api/v1/courses", json={
            "title": f"Enroll Test-{uuid.uuid4().hex[:6]}",
            "price_cents": 10000,
            "capacity": 3,
        }, headers=headers)
        course_id = course_resp.json()["data"]["id"]

        # Publish so enrollment is possible
        await client.post(f"/api/v1/courses/{course_id}/publish", headers=headers)

        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Course",
            "last_name": f"Student-{uuid.uuid4().hex[:6]}",
            "email": f"student-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        member_id = member_resp.json()["id"]

        return course_id, member_id

    async def test_enroll_member(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        course_id, member_id = await self._setup(client, headers)

        resp = await client.post(f"/api/v1/courses/{course_id}/enroll", json={
            "member_id": member_id,
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["status"] == "enrolled"
        assert data["paid_price_cents"] == 10000

    async def test_capacity_limit(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        # Create course with capacity 2
        course_resp = await client.post("/api/v1/courses", json={
            "title": "Tiny Course",
            "price_cents": 5000,
            "capacity": 2,
        }, headers=headers)
        course_id = course_resp.json()["data"]["id"]
        await client.post(f"/api/v1/courses/{course_id}/publish", headers=headers)

        # Enroll 2 members
        for i in range(2):
            m = await client.post("/api/v1/members", json={
                "first_name": f"Cap{i}",
                "last_name": f"Test-{uuid.uuid4().hex[:6]}",
                "email": f"cap{i}-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
            }, headers=headers)
            await client.post(f"/api/v1/courses/{course_id}/enroll", json={
                "member_id": m.json()["id"],
            }, headers=headers)

        # 3rd should fail
        m3 = await client.post("/api/v1/members", json={
            "first_name": "Cap3",
            "last_name": f"Test-{uuid.uuid4().hex[:6]}",
            "email": f"cap3-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        resp = await client.post(f"/api/v1/courses/{course_id}/enroll", json={
            "member_id": m3.json()["id"],
        }, headers=headers)
        assert resp.status_code == 400
        assert "capacity" in resp.json()["detail"].lower()

    async def test_duplicate_enrollment_rejected(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        course_id, member_id = await self._setup(client, headers)

        await client.post(f"/api/v1/courses/{course_id}/enroll", json={
            "member_id": member_id,
        }, headers=headers)

        resp = await client.post(f"/api/v1/courses/{course_id}/enroll", json={
            "member_id": member_id,
        }, headers=headers)
        assert resp.status_code == 400
        assert "already enrolled" in resp.json()["detail"].lower()

    async def test_cannot_enroll_in_draft(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        course_resp = await client.post("/api/v1/courses", json={
            "title": "Draft Course",
            "price_cents": 5000,
        }, headers=headers)
        course_id = course_resp.json()["data"]["id"]

        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Draft",
            "last_name": f"Test-{uuid.uuid4().hex[:6]}",
            "email": f"draft-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)

        resp = await client.post(f"/api/v1/courses/{course_id}/enroll", json={
            "member_id": member_resp.json()["id"],
        }, headers=headers)
        assert resp.status_code == 400

    async def test_early_bird_pricing(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        # Early bird deadline in the future
        future = (datetime.utcnow() + timedelta(days=30)).isoformat()

        course_resp = await client.post("/api/v1/courses", json={
            "title": "Early Bird Course",
            "price_cents": 20000,
            "early_bird_price_cents": 15000,
            "early_bird_deadline": future,
        }, headers=headers)
        course_id = course_resp.json()["data"]["id"]
        await client.post(f"/api/v1/courses/{course_id}/publish", headers=headers)

        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Early",
            "last_name": f"Bird-{uuid.uuid4().hex[:6]}",
            "email": f"early-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)

        resp = await client.post(f"/api/v1/courses/{course_id}/enroll", json={
            "member_id": member_resp.json()["id"],
        }, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["data"]["paid_price_cents"] == 15000

    async def test_withdraw_member(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        course_id, member_id = await self._setup(client, headers)

        enroll = await client.post(f"/api/v1/courses/{course_id}/enroll", json={
            "member_id": member_id,
        }, headers=headers)
        enrollment_id = enroll.json()["data"]["id"]

        resp = await client.post(f"/api/v1/courses/enrollments/{enrollment_id}/withdraw",
                                 headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "withdrawn"

    async def test_list_enrollments(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        course_id, member_id = await self._setup(client, headers)

        await client.post(f"/api/v1/courses/{course_id}/enroll", json={
            "member_id": member_id,
        }, headers=headers)

        resp = await client.get(f"/api/v1/courses/{course_id}/enrollments", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        assert data[0]["first_name"] == "Course"


@pytest.mark.asyncio
class TestCourseAttendance:

    async def _setup(self, client, headers):
        """Create course, session, enrolled member."""
        course_resp = await client.post("/api/v1/courses", json={
            "title": f"Attend Test-{uuid.uuid4().hex[:6]}",
            "price_cents": 10000,
        }, headers=headers)
        course_id = course_resp.json()["data"]["id"]
        await client.post(f"/api/v1/courses/{course_id}/publish", headers=headers)

        sess_resp = await client.post(f"/api/v1/courses/{course_id}/sessions", json={
            "title": "Attendance Session",
            "starts_at": "2026-04-20T09:00:00",
            "ends_at": "2026-04-20T12:00:00",
        }, headers=headers)
        session_id = sess_resp.json()["data"]["id"]

        member_resp = await client.post("/api/v1/members", json={
            "first_name": "Attend",
            "last_name": f"Test-{uuid.uuid4().hex[:6]}",
            "email": f"attend-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)
        member_id = member_resp.json()["id"]

        await client.post(f"/api/v1/courses/{course_id}/enroll", json={
            "member_id": member_id,
        }, headers=headers)

        return course_id, session_id, member_id

    async def test_record_attendance(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        course_id, session_id, member_id = await self._setup(client, headers)

        resp = await client.post(f"/api/v1/courses/sessions/{session_id}/attendance", json={
            "member_id": member_id,
            "status": "attended",
        }, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["data"]["status"] == "attended"

    async def test_get_session_attendance(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        course_id, session_id, member_id = await self._setup(client, headers)

        await client.post(f"/api/v1/courses/sessions/{session_id}/attendance", json={
            "member_id": member_id,
            "status": "attended",
        }, headers=headers)

        resp = await client.get(f"/api/v1/courses/sessions/{session_id}/attendance",
                                headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        assert data[0]["first_name"] == "Attend"

    async def test_complete_course_marks_enrollments(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        course_id, session_id, member_id = await self._setup(client, headers)

        # Complete the course
        resp = await client.post(f"/api/v1/courses/{course_id}/complete", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "completed"

        # Check enrollment is completed
        enrollments = await client.get(f"/api/v1/courses/{course_id}/enrollments",
                                       headers=headers)
        for e in enrollments.json()["data"]:
            assert e["status"] == "completed"
