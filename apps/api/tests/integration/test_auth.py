"""
AuraFlow — Auth Endpoint Tests

Tests registration, login, refresh, logout, password reset, and org switching.
"""
import pytest
from httpx import AsyncClient

from tests.conftest import auth_header


@pytest.mark.asyncio
class TestRegister:
    async def test_register_user_only(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "newuser@test.auraflow.dev",
            "password": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_register_with_org(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "studioowner@test.auraflow.dev",
            "password": "SecurePass123!",
            "first_name": "Studio",
            "last_name": "Owner",
            "organization_name": "Test Yoga Studio",
            "organization_slug": "test-yoga-studio",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data

        # Verify the token contains org_slug by checking user profile
        me = await client.get("/api/v1/users/me", headers=auth_header(data["access_token"]))
        assert me.status_code == 200
        profile = me.json()
        assert any(org["slug"] == "test-yoga-studio" for org in profile["organizations"])

    async def test_register_duplicate_email(self, client: AsyncClient, registered_user):
        resp = await client.post("/api/v1/auth/register", json={
            "email": registered_user["email"],
            "password": "AnotherPass123!",
            "first_name": "Dup",
            "last_name": "User",
        })
        assert resp.status_code == 409

    async def test_register_weak_password(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "weakpw@test.auraflow.dev",
            "password": "short",
            "first_name": "Weak",
            "last_name": "Pass",
        })
        assert resp.status_code == 422

    async def test_register_invalid_slug(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "badslug@test.auraflow.dev",
            "password": "SecurePass123!",
            "first_name": "Bad",
            "last_name": "Slug",
            "organization_name": "Bad Slug Studio",
            "organization_slug": "BAD SLUG!",
        })
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestLogin:
    async def test_login_json(self, client: AsyncClient, registered_user):
        resp = await client.post("/api/v1/auth/login/json", json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_login_oauth2_form(self, client: AsyncClient, registered_user):
        resp = await client.post("/api/v1/auth/login", data={
            "username": registered_user["email"],
            "password": registered_user["password"],
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_login_wrong_password(self, client: AsyncClient, registered_user):
        resp = await client.post("/api/v1/auth/login/json", json={
            "email": registered_user["email"],
            "password": "WrongPassword!",
        })
        assert resp.status_code == 401

    async def test_login_nonexistent_email(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login/json", json={
            "email": "nobody@test.auraflow.dev",
            "password": "Whatever123!",
        })
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestRefresh:
    async def test_refresh_token(self, client: AsyncClient, registered_user):
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": registered_user["refresh_token"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # New refresh token should differ (rotation)
        assert data["refresh_token"] != registered_user["refresh_token"]

    async def test_refresh_token_single_use(self, client: AsyncClient, registered_user):
        """Refresh tokens are single-use — the old one is revoked after rotation."""
        # First refresh succeeds
        resp1 = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": registered_user["refresh_token"],
        })
        assert resp1.status_code == 200

        # Second use of same token fails (revoked)
        resp2 = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": registered_user["refresh_token"],
        })
        assert resp2.status_code == 401

    async def test_refresh_invalid_token(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": "totally-bogus-token",
        })
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestLogout:
    async def test_logout_revokes_refresh(self, client: AsyncClient, registered_user):
        # Logout
        resp = await client.post("/api/v1/auth/logout", json={
            "refresh_token": registered_user["refresh_token"],
        })
        assert resp.status_code == 204

        # Refresh with revoked token should fail
        resp2 = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": registered_user["refresh_token"],
        })
        assert resp2.status_code == 401


@pytest.mark.asyncio
class TestPasswordReset:
    async def test_forgot_password_existing_email(self, client: AsyncClient, registered_user):
        """Should return 202 regardless (no email enumeration)."""
        resp = await client.post("/api/v1/auth/forgot-password", json={
            "email": registered_user["email"],
        })
        assert resp.status_code == 202

    async def test_forgot_password_nonexistent_email(self, client: AsyncClient):
        """Should also return 202 (prevents email enumeration)."""
        resp = await client.post("/api/v1/auth/forgot-password", json={
            "email": "nobody@test.auraflow.dev",
        })
        assert resp.status_code == 202

    async def test_reset_password_invalid_token(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/reset-password", json={
            "token": "invalid-token",
            "new_password": "NewSecurePass123!",
        })
        assert resp.status_code in (400, 503)  # 503 if Redis unavailable, 400 if token invalid


@pytest.mark.asyncio
class TestSwitchOrg:
    async def test_switch_to_owned_org(self, client: AsyncClient, registered_owner):
        resp = await client.post(
            f"/api/v1/auth/switch-org?org_slug={registered_owner['org_slug']}",
            headers=auth_header(registered_owner["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data

    async def test_switch_to_nonmember_org(self, client: AsyncClient, registered_user):
        resp = await client.post(
            "/api/v1/auth/switch-org?org_slug=nonexistent-org",
            headers=auth_header(registered_user["access_token"]),
        )
        assert resp.status_code == 403
