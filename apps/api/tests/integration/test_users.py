"""
AuraFlow — User Profile Endpoint Tests
"""
import pytest
from httpx import AsyncClient

from tests.conftest import auth_header


@pytest.mark.asyncio
class TestUserProfile:
    async def test_get_me(self, client: AsyncClient, registered_user):
        resp = await client.get(
            "/api/v1/users/me",
            headers=auth_header(registered_user["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == registered_user["email"]
        assert data["first_name"] == "Test"
        assert data["last_name"] == "User"
        assert data["is_platform_admin"] is False

    async def test_get_me_with_org(self, client: AsyncClient, registered_owner):
        resp = await client.get(
            "/api/v1/users/me",
            headers=auth_header(registered_owner["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["organizations"]) >= 1
        org = data["organizations"][0]
        assert org["slug"] == registered_owner["org_slug"]
        assert org["role"] == "owner"

    async def test_get_me_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/users/me")
        assert resp.status_code == 401

    async def test_update_me(self, client: AsyncClient, registered_user):
        resp = await client.put(
            "/api/v1/users/me",
            headers=auth_header(registered_user["access_token"]),
            json={"first_name": "Updated", "phone": "+15551234567"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["first_name"] == "Updated"
        assert data["phone"] == "+15551234567"

    async def test_update_me_empty(self, client: AsyncClient, registered_user):
        resp = await client.put(
            "/api/v1/users/me",
            headers=auth_header(registered_user["access_token"]),
            json={},
        )
        assert resp.status_code == 400

    async def test_get_me_invalid_token(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/users/me",
            headers=auth_header("invalid.jwt.token"),
        )
        assert resp.status_code == 401
