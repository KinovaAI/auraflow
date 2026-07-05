"""
AuraFlow — Organization Endpoint Tests
"""
import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header


@pytest.mark.asyncio
class TestListOrganizations:
    async def test_list_orgs_empty(self, client: AsyncClient, registered_user):
        resp = await client.get(
            "/api/v1/organizations",
            headers=auth_header(registered_user["access_token"]),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_orgs_with_org(self, client: AsyncClient, registered_owner):
        resp = await client.get(
            "/api/v1/organizations",
            headers=auth_header(registered_owner["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert any(o["slug"] == registered_owner["org_slug"] for o in data)


@pytest.mark.asyncio
class TestGetOrganization:
    async def test_get_org(self, client: AsyncClient, registered_owner):
        resp = await client.get(
            f"/api/v1/organizations/{registered_owner['org_slug']}",
            headers=auth_header(registered_owner["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == registered_owner["org_slug"]
        assert data["name"] == "Test Studio"
        assert data["status"] == "trial"

    async def test_get_org_not_member(self, client: AsyncClient, registered_user, registered_owner):
        resp = await client.get(
            f"/api/v1/organizations/{registered_owner['org_slug']}",
            headers=auth_header(registered_user["access_token"]),
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestCreateOrganization:
    async def test_create_org(self, client: AsyncClient, registered_user):
        slug = f"test-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/api/v1/organizations",
            headers=auth_header(registered_user["access_token"]),
            json={
                "name": "New Test Studio",
                "slug": slug,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["slug"] == slug
        assert data["name"] == "New Test Studio"
        assert data["status"] == "trial"

    async def test_create_org_duplicate_slug(self, client: AsyncClient, registered_owner):
        resp = await client.post(
            "/api/v1/organizations",
            headers=auth_header(registered_owner["access_token"]),
            json={
                "name": "Duplicate Studio",
                "slug": registered_owner["org_slug"],
            },
        )
        assert resp.status_code == 409

    async def test_create_org_invalid_slug(self, client: AsyncClient, registered_user):
        resp = await client.post(
            "/api/v1/organizations",
            headers=auth_header(registered_user["access_token"]),
            json={
                "name": "Bad Slug Studio",
                "slug": "BAD SLUG!",
            },
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestUpdateOrganization:
    async def test_update_org(self, client: AsyncClient, registered_owner):
        resp = await client.put(
            f"/api/v1/organizations/{registered_owner['org_slug']}",
            headers=auth_header(registered_owner["access_token"]),
            json={"name": "Updated Studio Name", "primary_color": "#FF5733"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Studio Name"
        assert data["primary_color"] == "#FF5733"

    async def test_update_org_no_fields(self, client: AsyncClient, registered_owner):
        resp = await client.put(
            f"/api/v1/organizations/{registered_owner['org_slug']}",
            headers=auth_header(registered_owner["access_token"]),
            json={},
        )
        assert resp.status_code == 400

    async def test_update_org_not_member(self, client: AsyncClient, registered_user, registered_owner):
        resp = await client.put(
            f"/api/v1/organizations/{registered_owner['org_slug']}",
            headers=auth_header(registered_user["access_token"]),
            json={"name": "Hijacked!"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestOrganizationMembers:
    async def test_list_members(self, client: AsyncClient, registered_owner):
        resp = await client.get(
            f"/api/v1/organizations/{registered_owner['org_slug']}/members",
            headers=auth_header(registered_owner["access_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert any(m["role"] == "owner" for m in data)

    async def test_invite_member(self, client: AsyncClient, registered_owner):
        resp = await client.post(
            f"/api/v1/organizations/{registered_owner['org_slug']}/members",
            headers=auth_header(registered_owner["access_token"]),
            json={"email": "newinstructor@test.auraflow.dev", "role": "instructor"},
        )
        assert resp.status_code == 201

        # Verify they appear in member list
        list_resp = await client.get(
            f"/api/v1/organizations/{registered_owner['org_slug']}/members",
            headers=auth_header(registered_owner["access_token"]),
        )
        members = list_resp.json()
        assert any(m["email"] == "newinstructor@test.auraflow.dev" for m in members)

    async def test_invite_as_owner_forbidden(self, client: AsyncClient, registered_owner):
        resp = await client.post(
            f"/api/v1/organizations/{registered_owner['org_slug']}/members",
            headers=auth_header(registered_owner["access_token"]),
            json={"email": "badactor@test.auraflow.dev", "role": "owner"},
        )
        assert resp.status_code == 422  # Pydantic validation rejects "owner" role

    async def test_list_members_unauthorized(self, client: AsyncClient, registered_user, registered_owner):
        resp = await client.get(
            f"/api/v1/organizations/{registered_owner['org_slug']}/members",
            headers=auth_header(registered_user["access_token"]),
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestDeactivateOrganization:
    async def test_deactivate_org(self, client: AsyncClient, registered_owner):
        resp = await client.delete(
            f"/api/v1/organizations/{registered_owner['org_slug']}",
            headers=auth_header(registered_owner["access_token"]),
        )
        assert resp.status_code == 204

        # Verify org is cancelled
        get_resp = await client.get(
            f"/api/v1/organizations/{registered_owner['org_slug']}",
            headers=auth_header(registered_owner["access_token"]),
        )
        # May be 200 (still visible to owner) or 404 depending on filter
        if get_resp.status_code == 200:
            assert get_resp.json()["status"] == "cancelled"
