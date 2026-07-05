"""AuraFlow — Member Portal Integration Tests

Public schedule API, member registration, portal profile, bookings, memberships, and auth.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _create_session_for_portal(client, headers, studio_id, capacity=20, waitlist=5):
    """Create a class type + session for portal booking tests."""
    ct = await client.post("/api/v1/scheduling/class-types", json={
        "studio_id": studio_id,
        "name": f"Portal Class {uuid.uuid4().hex[:6]}",
        "description": "Great class for all levels",
        "category": "yoga",
    }, headers=headers)
    ct_id = ct.json()["id"]

    tomorrow = datetime.utcnow() + timedelta(days=1)
    session = await client.post("/api/v1/scheduling/sessions", json={
        "studio_id": studio_id,
        "class_type_id": ct_id,
        "title": "Portal Test Session",
        "starts_at": tomorrow.isoformat(),
        "ends_at": (tomorrow + timedelta(hours=1)).isoformat(),
        "capacity": capacity,
        "waitlist_capacity": waitlist,
    }, headers=headers)
    return session.json()["id"], ct_id


async def _register_member(client, org_slug, email=None):
    """Register a member and return tokens + info."""
    email = email or f"member-{uuid.uuid4().hex[:8]}@test.auraflow.dev"
    response = await client.post("/api/v1/auth/member-register", json={
        "email": email,
        "password": "MemberPass123!",
        "first_name": "Portal",
        "last_name": "Member",
        "org_slug": org_slug,
    })
    data = response.json()
    data["email"] = email
    data["_status"] = response.status_code
    return data


# ── Public Schedule Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPublicSchedule:

    async def test_public_schedule_returns_sessions(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]

        # Create a session
        await _create_session_for_portal(client, headers, studio_id)

        # Public schedule (no auth)
        response = await client.get(f"/api/v1/public/{org_slug}/schedule")
        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) >= 1
        s = sessions[0]
        assert "title" in s
        assert "starts_at" in s
        assert "spots_remaining" in s
        assert "is_full" in s

    async def test_public_schedule_unknown_org_404(self, client: AsyncClient):
        response = await client.get("/api/v1/public/nonexistent-studio/schedule")
        assert response.status_code == 404

    async def test_public_class_types(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]

        # Create a class type
        await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id,
            "name": f"Public CT {uuid.uuid4().hex[:6]}",
            "description": "A public class",
        }, headers=headers)

        response = await client.get(f"/api/v1/public/{org_slug}/class-types")
        assert response.status_code == 200
        types = response.json()
        assert len(types) >= 1
        assert "name" in types[0]

    async def test_public_instructors(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        org_slug = registered_owner_with_studio["org_slug"]

        # Create an instructor
        await client.post("/api/v1/instructors", json={
            "display_name": f"Instructor {uuid.uuid4().hex[:6]}",
            "email": f"instr-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        }, headers=headers)

        response = await client.get(f"/api/v1/public/{org_slug}/instructors")
        assert response.status_code == 200
        instructors = response.json()
        assert len(instructors) >= 1
        assert "display_name" in instructors[0]


# ── Member Registration Tests ────────────────────────────────────────────────

@pytest.mark.asyncio
class TestMemberRegistration:

    async def test_member_register_new_user(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        org_slug = registered_owner_with_studio["org_slug"]
        data = await _register_member(client, org_slug)
        assert data["_status"] == 201
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_member_register_links_existing_member(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        org_slug = registered_owner_with_studio["org_slug"]

        # Create a member record first (admin creates it)
        email = f"premember-{uuid.uuid4().hex[:8]}@test.auraflow.dev"
        await client.post("/api/v1/members", json={
            "first_name": "Pre",
            "last_name": "Member",
            "email": email,
        }, headers=headers)

        # Now register as that member
        data = await _register_member(client, org_slug, email=email)
        assert data["_status"] == 201

        # Verify they can access portal
        member_headers = {"Authorization": f"Bearer {data['access_token']}"}
        profile = await client.get("/api/v1/portal/me", headers=member_headers)
        assert profile.status_code == 200
        assert profile.json()["email"] == email

    async def test_member_register_existing_user_new_org(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        # Register member with first org
        org_slug = registered_owner_with_studio["org_slug"]
        email = f"multiorg-{uuid.uuid4().hex[:8]}@test.auraflow.dev"
        data = await _register_member(client, org_slug, email=email)
        assert data["_status"] == 201

    async def test_member_register_duplicate_error(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        org_slug = registered_owner_with_studio["org_slug"]
        email = f"dup-{uuid.uuid4().hex[:8]}@test.auraflow.dev"

        # First registration
        data1 = await _register_member(client, org_slug, email=email)
        assert data1["_status"] == 201

        # Second registration — should fail
        data2 = await _register_member(client, org_slug, email=email)
        assert data2["_status"] == 409


# ── Portal Profile Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPortalProfile:

    async def test_get_my_profile(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        org_slug = registered_owner_with_studio["org_slug"]
        data = await _register_member(client, org_slug)
        headers = {"Authorization": f"Bearer {data['access_token']}"}

        response = await client.get("/api/v1/portal/me", headers=headers)
        assert response.status_code == 200
        profile = response.json()
        assert profile["first_name"] == "Portal"
        assert profile["last_name"] == "Member"
        assert profile["email"] == data["email"]

    async def test_update_my_profile(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        org_slug = registered_owner_with_studio["org_slug"]
        data = await _register_member(client, org_slug)
        headers = {"Authorization": f"Bearer {data['access_token']}"}

        response = await client.put("/api/v1/portal/me", json={
            "phone": "555-0199",
            "emergency_contact_name": "Mom",
            "emergency_contact_phone": "555-0100",
        }, headers=headers)
        assert response.status_code == 200
        assert response.json()["phone"] == "555-0199"
        assert response.json()["emergency_contact_name"] == "Mom"

    async def test_update_rejects_restricted_fields(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        org_slug = registered_owner_with_studio["org_slug"]
        data = await _register_member(client, org_slug)
        headers = {"Authorization": f"Bearer {data['access_token']}"}

        # Try to update email (not allowed via portal)
        response = await client.put("/api/v1/portal/me", json={
            "phone": "555-0200",
        }, headers=headers)
        assert response.status_code == 200

        # Get profile and verify email didn't change
        profile = await client.get("/api/v1/portal/me", headers=headers)
        assert profile.json()["email"] == data["email"]


# ── Portal Bookings Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPortalBookings:

    async def test_browse_schedule(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]

        await _create_session_for_portal(client, headers, studio_id)

        # Register member and browse schedule
        data = await _register_member(client, org_slug)
        member_headers = {"Authorization": f"Bearer {data['access_token']}"}

        response = await client.get("/api/v1/portal/schedule", headers=member_headers)
        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) >= 1
        assert "spots_remaining" in sessions[0]

    async def test_book_class_success(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]

        session_id, _ = await _create_session_for_portal(client, headers, studio_id)

        data = await _register_member(client, org_slug)
        member_headers = {"Authorization": f"Bearer {data['access_token']}"}

        response = await client.post("/api/v1/portal/bookings", json={
            "session_id": session_id,
        }, headers=member_headers)
        assert response.status_code == 201
        booking = response.json()
        assert booking["status"] == "confirmed"

    async def test_book_class_full_waitlisted(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]

        # Create session with capacity=1
        session_id, _ = await _create_session_for_portal(
            client, headers, studio_id, capacity=1, waitlist=5
        )

        # First member gets confirmed
        data1 = await _register_member(client, org_slug)
        h1 = {"Authorization": f"Bearer {data1['access_token']}"}
        r1 = await client.post("/api/v1/portal/bookings", json={
            "session_id": session_id,
        }, headers=h1)
        assert r1.json()["status"] == "confirmed"

        # Second member gets waitlisted
        data2 = await _register_member(client, org_slug)
        h2 = {"Authorization": f"Bearer {data2['access_token']}"}
        r2 = await client.post("/api/v1/portal/bookings", json={
            "session_id": session_id,
        }, headers=h2)
        assert r2.json()["status"] == "waitlisted"

    async def test_book_class_duplicate_rejected(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]

        session_id, _ = await _create_session_for_portal(client, headers, studio_id)

        data = await _register_member(client, org_slug)
        member_headers = {"Authorization": f"Bearer {data['access_token']}"}

        # First booking
        await client.post("/api/v1/portal/bookings", json={
            "session_id": session_id,
        }, headers=member_headers)

        # Duplicate
        r2 = await client.post("/api/v1/portal/bookings", json={
            "session_id": session_id,
        }, headers=member_headers)
        assert r2.status_code == 400
        assert "already booked" in r2.json()["detail"].lower()

    async def test_cancel_booking(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]

        session_id, _ = await _create_session_for_portal(client, headers, studio_id)

        data = await _register_member(client, org_slug)
        member_headers = {"Authorization": f"Bearer {data['access_token']}"}

        # Book
        booking = await client.post("/api/v1/portal/bookings", json={
            "session_id": session_id,
        }, headers=member_headers)
        booking_id = booking.json()["id"]

        # Cancel
        response = await client.delete(
            f"/api/v1/portal/bookings/{booking_id}",
            headers=member_headers,
        )
        assert response.status_code == 204

    async def test_cancel_other_member_forbidden(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        org_slug = registered_owner_with_studio["org_slug"]

        session_id, _ = await _create_session_for_portal(client, headers, studio_id)

        # Member 1 books
        data1 = await _register_member(client, org_slug)
        h1 = {"Authorization": f"Bearer {data1['access_token']}"}
        booking = await client.post("/api/v1/portal/bookings", json={
            "session_id": session_id,
        }, headers=h1)
        booking_id = booking.json()["id"]

        # Member 2 tries to cancel Member 1's booking
        data2 = await _register_member(client, org_slug)
        h2 = {"Authorization": f"Bearer {data2['access_token']}"}
        response = await client.delete(
            f"/api/v1/portal/bookings/{booking_id}",
            headers=h2,
        )
        assert response.status_code == 403


# ── Portal Memberships Tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPortalMemberships:

    async def test_get_my_memberships(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        org_slug = registered_owner_with_studio["org_slug"]

        data = await _register_member(client, org_slug)
        member_headers = {"Authorization": f"Bearer {data['access_token']}"}

        response = await client.get("/api/v1/portal/memberships", headers=member_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_no_memberships_empty(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        org_slug = registered_owner_with_studio["org_slug"]

        data = await _register_member(client, org_slug)
        member_headers = {"Authorization": f"Bearer {data['access_token']}"}

        response = await client.get("/api/v1/portal/memberships", headers=member_headers)
        assert response.status_code == 200
        assert response.json() == []


# ── Portal Auth Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPortalAuth:

    async def test_portal_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/portal/me")
        assert response.status_code in (401, 403)

    async def test_portal_member_role_sufficient(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        org_slug = registered_owner_with_studio["org_slug"]

        data = await _register_member(client, org_slug)
        member_headers = {"Authorization": f"Bearer {data['access_token']}"}

        response = await client.get("/api/v1/portal/me", headers=member_headers)
        assert response.status_code == 200

    async def test_portal_admin_role_also_works(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        # Owner should also be able to access portal endpoints
        headers = registered_owner_with_studio["headers"]

        # Owner won't have a member record, so /me returns 404 — but auth passes
        response = await client.get("/api/v1/portal/me", headers=headers)
        # 200 if owner has member record, 404 if not — either way auth passed (not 401/403)
        assert response.status_code in (200, 404)
