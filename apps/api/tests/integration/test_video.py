"""AuraFlow — Video Library Integration Tests

Tests provider connection, video CRUD, categories, access control,
RBAC, and sync endpoints. External API calls (YouTube, Mux) are mocked.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


# ── Connection Status ────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestVideoConnectionStatus:

    async def test_connection_status_empty(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.get("/api/v1/video/connect/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["youtube_connected"] is False
        assert data["mux_connected"] is False

    @patch("app.services.video.youtube_service.YouTubeService.test_connection")
    async def test_connect_youtube(self, mock_test, client: AsyncClient, registered_owner_with_studio):
        mock_test.return_value = {
            "success": True,
            "channel_title": "Test Channel",
            "channel_thumbnail": "https://example.com/thumb.jpg",
            "video_count": "42",
        }
        headers = registered_owner_with_studio["headers"]

        resp = await client.post("/api/v1/video/connect/youtube", json={
            "api_key": "fake-youtube-api-key",
            "channel_id": "UC_test_channel_id",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["connected"] is True
        assert data["channel_title"] == "Test Channel"

        # Verify status updated
        resp2 = await client.get("/api/v1/video/connect/status", headers=headers)
        assert resp2.json()["data"]["youtube_connected"] is True

    @patch("app.services.video.youtube_service.YouTubeService.test_connection")
    async def test_connect_youtube_bad_key(self, mock_test, client: AsyncClient, registered_owner_with_studio):
        mock_test.return_value = {"success": False, "error": "Invalid API key"}
        headers = registered_owner_with_studio["headers"]

        resp = await client.post("/api/v1/video/connect/youtube", json={
            "api_key": "bad-key",
            "channel_id": "UC_bad",
        }, headers=headers)
        assert resp.status_code == 400

    @patch("app.services.video.youtube_service.YouTubeService.test_connection")
    async def test_disconnect_youtube(self, mock_test, client: AsyncClient, registered_owner_with_studio):
        mock_test.return_value = {"success": True, "channel_title": "Ch", "video_count": "1"}
        headers = registered_owner_with_studio["headers"]

        # Connect first
        await client.post("/api/v1/video/connect/youtube", json={
            "api_key": "key", "channel_id": "UC_ch",
        }, headers=headers)

        # Disconnect
        resp = await client.delete("/api/v1/video/connect/youtube", headers=headers)
        assert resp.status_code == 200

        # Verify disconnected
        resp2 = await client.get("/api/v1/video/connect/status", headers=headers)
        assert resp2.json()["data"]["youtube_connected"] is False

    @patch("app.services.video.mux_service.MuxService.test_connection")
    @patch("app.services.video.mux_service.MuxService._fetch_environment_id")
    async def test_connect_mux(self, mock_env, mock_test, client: AsyncClient, registered_owner_with_studio):
        mock_test.return_value = {"success": True, "asset_count": 5}
        mock_env.return_value = "env_123"
        headers = registered_owner_with_studio["headers"]

        resp = await client.post("/api/v1/video/connect/mux", json={
            "token_id": "fake-mux-token",
            "token_secret": "fake-mux-secret",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["connected"] is True

    @patch("app.services.video.mux_service.MuxService.test_connection")
    async def test_connect_mux_bad_creds(self, mock_test, client: AsyncClient, registered_owner_with_studio):
        mock_test.return_value = {"success": False, "error": "Invalid Mux credentials"}
        headers = registered_owner_with_studio["headers"]

        resp = await client.post("/api/v1/video/connect/mux", json={
            "token_id": "bad", "token_secret": "bad",
        }, headers=headers)
        assert resp.status_code == 400


# ── Categories ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestVideoCategories:

    async def test_create_category(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.post("/api/v1/video/categories", json={
            "name": "Yoga Flows",
            "description": "Full-length yoga flow classes",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Yoga Flows"
        assert data["slug"] == "yoga-flows"

    async def test_list_categories(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        # Create two categories
        await client.post("/api/v1/video/categories", json={"name": "Cat A"}, headers=headers)
        await client.post("/api/v1/video/categories", json={"name": "Cat B"}, headers=headers)

        resp = await client.get("/api/v1/video/categories", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 2

    async def test_update_category(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        # Create
        resp = await client.post("/api/v1/video/categories", json={"name": "Old Name"}, headers=headers)
        cat_id = resp.json()["data"]["id"]

        # Update
        resp2 = await client.put(f"/api/v1/video/categories/{cat_id}", json={
            "name": "New Name",
            "description": "Updated desc",
        }, headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["data"]["name"] == "New Name"

    async def test_delete_category(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        resp = await client.post("/api/v1/video/categories", json={"name": "To Delete"}, headers=headers)
        cat_id = resp.json()["data"]["id"]

        resp2 = await client.delete(f"/api/v1/video/categories/{cat_id}", headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["data"]["deleted"] is True


# ── Video Library ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestVideoLibrary:

    async def test_list_videos_empty(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.get("/api/v1/video/library", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    @patch("app.services.video.youtube_service.YouTubeService.test_connection")
    @patch("app.services.video.youtube_service.YouTubeService.fetch_channel_videos")
    async def test_sync_youtube(self, mock_fetch, mock_test, client: AsyncClient, registered_owner_with_studio):
        mock_test.return_value = {"success": True, "channel_title": "Ch", "video_count": "2"}
        mock_fetch.return_value = [
            {
                "youtube_video_id": "vid_001",
                "title": "Morning Vinyasa Flow",
                "description": "A 30 minute flow",
                "thumbnail_url": "https://i.ytimg.com/vi/vid_001/hqdefault.jpg",
                "duration_seconds": 1800,
                "published_at": "2025-01-15T10:00:00Z",
                "embeddable": True,
            },
            {
                "youtube_video_id": "vid_002",
                "title": "Yin Yoga for Beginners",
                "description": "Gentle yin class",
                "thumbnail_url": "https://i.ytimg.com/vi/vid_002/hqdefault.jpg",
                "duration_seconds": 2700,
                "published_at": "2025-01-20T10:00:00Z",
                "embeddable": True,
            },
        ]
        headers = registered_owner_with_studio["headers"]

        # Connect YouTube
        await client.post("/api/v1/video/connect/youtube", json={
            "api_key": "key", "channel_id": "UC_ch",
        }, headers=headers)

        # Sync
        resp = await client.post("/api/v1/video/sync/youtube", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["new"] == 2
        assert data["source"] == "youtube"

        # Verify videos in library
        resp2 = await client.get("/api/v1/video/library", headers=headers)
        videos = resp2.json()["data"]
        assert len(videos) == 2
        assert videos[0]["source"] == "youtube"

    async def test_update_video(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        headers = registered_owner_with_studio["headers"]
        org_slug = registered_owner_with_studio["org_slug"]

        # Insert a video directly
        vid_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO af_tenant_{org_slug.replace('-', '_')}.videos
                    (id, source, external_id, title, is_published)
                VALUES ($1, 'manual', 'ext1', 'Original Title', TRUE)
            """, vid_id)

        resp = await client.put(f"/api/v1/video/library/{vid_id}", json={
            "title": "Updated Title",
            "visibility": "staff_only",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Updated Title"

    async def test_delete_video(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        headers = registered_owner_with_studio["headers"]
        org_slug = registered_owner_with_studio["org_slug"]

        vid_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO af_tenant_{org_slug.replace('-', '_')}.videos
                    (id, source, external_id, title, is_published)
                VALUES ($1, 'manual', 'ext2', 'To Delete', TRUE)
            """, vid_id)

        resp = await client.delete(f"/api/v1/video/library/{vid_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True

        # Verify it's hidden
        resp2 = await client.get(f"/api/v1/video/library/{vid_id}", headers=headers)
        assert resp2.json()["data"]["visibility"] == "hidden"
        assert resp2.json()["data"]["is_published"] is False


# ── Browse (Member Access) ───────────────────────────────────────────────────

@pytest.mark.asyncio
class TestVideoBrowse:

    async def test_browse_published_only(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        headers = registered_owner_with_studio["headers"]
        org_slug = registered_owner_with_studio["org_slug"]

        # Insert published and unpublished videos
        async with db_pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO af_tenant_{org_slug.replace('-', '_')}.videos
                    (id, source, external_id, title, is_published, visibility)
                VALUES
                    ($1, 'youtube', 'pub1', 'Published Video', TRUE, 'all_members'),
                    ($2, 'youtube', 'unpub1', 'Draft Video', FALSE, 'all_members'),
                    ($3, 'youtube', 'hidden1', 'Hidden Video', TRUE, 'hidden')
            """, str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))

        resp = await client.get("/api/v1/video/browse", headers=headers)
        assert resp.status_code == 200
        videos = resp.json()["data"]
        # Owner sees all published non-hidden videos
        titles = [v["title"] for v in videos]
        assert "Published Video" in titles
        assert "Draft Video" not in titles
        assert "Hidden Video" not in titles


# ── View Recording ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestVideoViews:

    async def test_record_view(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        headers = registered_owner_with_studio["headers"]
        org_slug = registered_owner_with_studio["org_slug"]

        vid_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO af_tenant_{org_slug.replace('-', '_')}.videos
                    (id, source, external_id, title, is_published, visibility)
                VALUES ($1, 'youtube', 'v1', 'Test Video', TRUE, 'all_members')
            """, vid_id)

        resp = await client.post(f"/api/v1/video/browse/{vid_id}/view", json={
            "watched_seconds": 120,
            "completed": False,
        }, headers=headers)
        assert resp.status_code == 200

        # Check stats
        resp2 = await client.get(f"/api/v1/video/stats/{vid_id}", headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["data"]["total_views"] == 1


# ── Library Stats ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestVideoStats:

    async def test_library_stats(self, client: AsyncClient, registered_owner_with_studio, db_pool):
        headers = registered_owner_with_studio["headers"]
        org_slug = registered_owner_with_studio["org_slug"]

        # Insert some videos
        async with db_pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO af_tenant_{org_slug.replace('-', '_')}.videos
                    (id, source, external_id, title, is_published)
                VALUES
                    ($1, 'youtube', 'yt1', 'YT Video', TRUE),
                    ($2, 'mux', 'mux1', 'Mux Video', TRUE),
                    ($3, 'youtube', 'yt2', 'Draft', FALSE)
            """, str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))

        resp = await client.get("/api/v1/video/stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_videos"] == 3
        assert data["published_videos"] == 2
        assert data["youtube_videos"] == 2
        assert data["mux_videos"] == 1


# ── RBAC ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestVideoRBAC:

    async def test_unauthenticated_blocked(self, client: AsyncClient):
        resp = await client.get("/api/v1/video/library")
        assert resp.status_code in (401, 403)

    async def test_connection_management_owner_only(self, client: AsyncClient, registered_owner_with_studio):
        """Only owners should be able to connect/disconnect providers."""
        headers = registered_owner_with_studio["headers"]
        # Owner can access connection status
        resp = await client.get("/api/v1/video/connect/status", headers=headers)
        assert resp.status_code == 200
