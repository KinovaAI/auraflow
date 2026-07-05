"""AuraFlow — Platform Admin Integration Tests

Tests organization management, user management, feature flag toggling,
metrics, announcements, and non-admin rejection (403).
"""
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture
async def platform_admin(client: AsyncClient, db_pool):
    """Register a user and promote them to platform admin."""
    email = f"padmin-{uuid.uuid4().hex[:8]}@test.auraflow.dev"
    slug = f"test-{uuid.uuid4().hex[:8]}"

    resp = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "AdminPass123!",
        "first_name": "Platform",
        "last_name": "Admin",
        "organization_name": "Admin Org",
        "organization_slug": slug,
    })
    assert resp.status_code == 201

    # Look up user_id from DB
    async with db_pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT id FROM af_global.users WHERE email = $1", email
        )
        user_id = str(user_row["id"])

        # Promote to platform admin
        await conn.execute(
            "UPDATE af_global.users SET is_platform_admin = TRUE WHERE id = $1",
            user_row["id"],
        )

    # Re-login to get token with is_platform_admin=True
    login_resp = await client.post("/api/v1/auth/login/json", json={
        "email": email,
        "password": "AdminPass123!",
    })
    assert login_resp.status_code == 200
    login_data = login_resp.json()

    return {
        "user_id": user_id,
        "email": email,
        "org_slug": slug,
        "access_token": login_data["access_token"],
        "headers": {"Authorization": f"Bearer {login_data['access_token']}"},
    }


@pytest.mark.asyncio
class TestPlatformOrganizations:

    async def test_list_organizations(self, client: AsyncClient, platform_admin):
        headers = platform_admin["headers"]

        resp = await client.get("/api/v1/platform/organizations", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) >= 1  # At least the admin's own org

    async def test_get_organization_detail(self, client: AsyncClient, platform_admin, db_pool):
        headers = platform_admin["headers"]

        # Get the org_id
        async with db_pool.acquire() as conn:
            org = await conn.fetchrow(
                "SELECT id FROM af_global.organizations WHERE slug = $1",
                platform_admin["org_slug"],
            )
        org_id = str(org["id"])

        resp = await client.get(f"/api/v1/platform/organizations/{org_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["slug"] == platform_admin["org_slug"]
        assert "users" in data
        assert "feature_flags" in data

    async def test_suspend_organization(self, client: AsyncClient, platform_admin, db_pool):
        headers = platform_admin["headers"]

        async with db_pool.acquire() as conn:
            org = await conn.fetchrow(
                "SELECT id FROM af_global.organizations WHERE slug = $1",
                platform_admin["org_slug"],
            )
        org_id = str(org["id"])

        resp = await client.put(f"/api/v1/platform/organizations/{org_id}/status", json={
            "status": "suspended",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "suspended"

        # Reactivate
        resp2 = await client.put(f"/api/v1/platform/organizations/{org_id}/status", json={
            "status": "active",
        }, headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["data"]["status"] == "active"


@pytest.mark.asyncio
class TestPlatformUsers:

    async def test_list_users(self, client: AsyncClient, platform_admin):
        headers = platform_admin["headers"]

        resp = await client.get("/api/v1/platform/users", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_deactivate_user(self, client: AsyncClient, platform_admin, db_pool):
        headers = platform_admin["headers"]

        # Create another user to deactivate
        email = f"deact-{uuid.uuid4().hex[:8]}@test.auraflow.dev"
        await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "DeactPass123!",
            "first_name": "Deact",
            "last_name": "User",
        })

        # Look up user_id from DB
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM af_global.users WHERE email = $1", email
            )
        user_id = str(row["id"])

        resp = await client.put(f"/api/v1/platform/users/{user_id}/deactivate",
                                headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False


@pytest.mark.asyncio
class TestFeatureFlags:

    async def test_get_org_feature_flags(self, client: AsyncClient, platform_admin, db_pool):
        headers = platform_admin["headers"]

        async with db_pool.acquire() as conn:
            org = await conn.fetchrow(
                "SELECT id FROM af_global.organizations WHERE slug = $1",
                platform_admin["org_slug"],
            )
        org_id = str(org["id"])

        resp = await client.get(f"/api/v1/platform/feature-flags/{org_id}", headers=headers)
        assert resp.status_code == 200
        flags = resp.json()["data"]
        assert isinstance(flags, list)

    async def test_toggle_feature_flag(self, client: AsyncClient, platform_admin, db_pool):
        headers = platform_admin["headers"]

        async with db_pool.acquire() as conn:
            org = await conn.fetchrow(
                "SELECT id FROM af_global.organizations WHERE slug = $1",
                platform_admin["org_slug"],
            )
        org_id = str(org["id"])

        # Enable a flag
        resp = await client.put(f"/api/v1/platform/feature-flags/{org_id}", json={
            "flag_key": "video.mux_hosting",
            "is_enabled": True,
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["is_enabled"] is True
        assert resp.json()["data"]["flag_key"] == "video.mux_hosting"

        # Disable it
        resp2 = await client.put(f"/api/v1/platform/feature-flags/{org_id}", json={
            "flag_key": "video.mux_hosting",
            "is_enabled": False,
        }, headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["data"]["is_enabled"] is False


@pytest.mark.asyncio
class TestPlatformMetrics:

    async def test_get_dashboard_metrics(self, client: AsyncClient, platform_admin):
        headers = platform_admin["headers"]

        resp = await client.get("/api/v1/platform/metrics", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_organizations" in data
        assert "active_organizations" in data
        assert "total_users" in data

    async def test_snapshot_metrics(self, client: AsyncClient, platform_admin):
        headers = platform_admin["headers"]

        resp = await client.post("/api/v1/platform/metrics/snapshot", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "metric_date" in data
        assert "total_organizations" in data

    async def test_metrics_history(self, client: AsyncClient, platform_admin):
        headers = platform_admin["headers"]

        # Create a snapshot first
        await client.post("/api/v1/platform/metrics/snapshot", headers=headers)

        resp = await client.get("/api/v1/platform/metrics/history", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1


@pytest.mark.asyncio
class TestPlatformAnnouncements:

    async def test_create_announcement(self, client: AsyncClient, platform_admin):
        headers = platform_admin["headers"]

        resp = await client.post("/api/v1/platform/announcements", json={
            "title": "Scheduled Maintenance",
            "body": "System will be down for maintenance on Saturday.",
            "type": "maintenance",
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Scheduled Maintenance"
        assert data["type"] == "maintenance"

    async def test_list_announcements(self, client: AsyncClient, platform_admin):
        headers = platform_admin["headers"]

        await client.post("/api/v1/platform/announcements", json={
            "title": "Ann 1",
            "type": "info",
        }, headers=headers)
        await client.post("/api/v1/platform/announcements", json={
            "title": "Ann 2",
            "type": "feature",
        }, headers=headers)

        resp = await client.get("/api/v1/platform/announcements", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 2


@pytest.mark.asyncio
class TestNonAdminRejected:

    async def test_regular_user_rejected(self, client: AsyncClient, registered_owner_with_studio):
        """Non-platform-admin gets 403 on all platform endpoints."""
        headers = registered_owner_with_studio["headers"]

        resp = await client.get("/api/v1/platform/organizations", headers=headers)
        assert resp.status_code == 403

        resp2 = await client.get("/api/v1/platform/users", headers=headers)
        assert resp2.status_code == 403

        resp3 = await client.get("/api/v1/platform/metrics", headers=headers)
        assert resp3.status_code == 403

        resp4 = await client.get("/api/v1/platform/announcements", headers=headers)
        assert resp4.status_code == 403
