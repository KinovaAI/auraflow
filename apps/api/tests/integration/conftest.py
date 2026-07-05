"""
AuraFlow — Integration Test Fixtures

Requires running PostgreSQL and Redis (from Docker Compose).
"""
import os
import uuid

import app  # noqa: F401 — pre-import to register package before fixtures run
import asyncpg
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest_asyncio.fixture
async def db_pool():
    pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"],
        min_size=2,
        max_size=5,
    )
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing the FastAPI app."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def clean_test_data(db_pool):
    """Clean up test data after each test. Preserves Your Studio seed."""
    yield
    # Cleanup after test
    async with db_pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM af_global.refresh_tokens
            WHERE user_id IN (
                SELECT id FROM af_global.users WHERE email LIKE '%@test.auraflow.dev'
            )
        """)
        await conn.execute("""
            DELETE FROM af_global.audit_log
            WHERE user_id IN (
                SELECT id FROM af_global.users WHERE email LIKE '%@test.auraflow.dev'
            )
        """)
        await conn.execute("""
            DELETE FROM af_global.feature_flags
            WHERE organization_id IN (
                SELECT id FROM af_global.organizations WHERE slug LIKE 'test-%'
            )
        """)
        await conn.execute("""
            DELETE FROM af_global.organization_users
            WHERE user_id IN (
                SELECT id FROM af_global.users WHERE email LIKE '%@test.auraflow.dev'
            )
        """)
        test_orgs = await conn.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE slug LIKE 'test-%'"
        )
        for org in test_orgs:
            await conn.execute(f"DROP SCHEMA IF EXISTS {org['schema_name']} CASCADE")
        await conn.execute("DELETE FROM af_global.organizations WHERE slug LIKE 'test-%'")
        await conn.execute("DELETE FROM af_global.users WHERE email LIKE '%@test.auraflow.dev'")

    # Flush test Redis DB
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(os.environ["REDIS_URL"])
        await r.flushdb()
        await r.aclose()
    except Exception:
        pass


@pytest_asyncio.fixture
async def registered_user(client: AsyncClient):
    """Register a test user and return their tokens + info."""
    email = f"testuser-{uuid.uuid4().hex[:8]}@test.auraflow.dev"
    response = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "TestPassword123!",
        "first_name": "Test",
        "last_name": "User",
    })
    assert response.status_code == 201
    data = response.json()
    data["email"] = email
    data["password"] = "TestPassword123!"
    return data


@pytest_asyncio.fixture
async def registered_owner(client: AsyncClient):
    """Register a test user with an organization (studio owner)."""
    slug = f"test-{uuid.uuid4().hex[:8]}"
    email = f"owner-{uuid.uuid4().hex[:8]}@test.auraflow.dev"
    response = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "OwnerPassword123!",
        "first_name": "Studio",
        "last_name": "Owner",
        "organization_name": "Test Studio",
        "organization_slug": slug,
    })
    assert response.status_code == 201
    data = response.json()
    data["email"] = email
    data["password"] = "OwnerPassword123!"
    data["org_slug"] = slug
    return data


@pytest_asyncio.fixture
async def registered_owner_with_studio(client: AsyncClient, registered_owner):
    """Registered owner + a default studio. Returns owner data + studio_id."""
    token = registered_owner["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create a studio in the tenant
    response = await client.post("/api/v1/studios", json={
        "name": "Test Studio Location",
        "slug": "test-main",
        "city": "Test City",
        "state": "CA",
        "timezone": "America/Los_Angeles",
    }, headers=headers)
    assert response.status_code == 201
    studio = response.json()

    data = dict(registered_owner)
    data["studio_id"] = studio["id"]
    data["headers"] = headers
    return data
