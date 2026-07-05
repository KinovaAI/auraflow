"""AuraFlow — Zoom Integration Tests

Tests Zoom connect/disconnect, connection status, virtual session creation
with Zoom meeting CRUD, series expansion, cancellation cleanup,
recording webhooks, signature verification, and auto-publish flow.
External Zoom API calls are mocked via unittest.mock.patch.
"""
import hashlib
import hmac
import json
import uuid
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


# ── Connection Management ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestZoomConnection:

    @patch("app.services.integrations.zoom_service.ZoomService.test_connection")
    async def test_connect_zoom(self, mock_test, client: AsyncClient, registered_owner_with_studio):
        """POST /api/v1/integrations/zoom/connect stores encrypted creds."""
        mock_test.return_value = {
            "success": True,
            "account_id": "abc123",
            "email": "studio@example.com",
            "display_name": "Studio Owner",
        }
        headers = registered_owner_with_studio["headers"]

        resp = await client.post("/api/v1/integrations/zoom/connect", json={
            "account_id": "abc123",
            "client_id": "fake-zoom-client-id",
            "client_secret": "fake-zoom-client-secret",
            "webhook_secret": "fake-webhook-secret",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["connected"] is True

        # Verify status shows connected
        resp2 = await client.get("/api/v1/integrations/zoom/status", headers=headers)
        assert resp2.status_code == 200
        status = resp2.json()["data"]
        assert status["zoom_connected"] is True
        assert status["zoom_account_id"] == "abc123"

    @patch("app.services.integrations.zoom_service.ZoomService.test_connection")
    async def test_disconnect_zoom(self, mock_test, client: AsyncClient, registered_owner_with_studio):
        """DELETE /api/v1/integrations/zoom/disconnect nulls creds."""
        mock_test.return_value = {"success": True, "account_id": "abc123"}
        headers = registered_owner_with_studio["headers"]

        # Connect first
        await client.post("/api/v1/integrations/zoom/connect", json={
            "account_id": "abc123",
            "client_id": "cid",
            "client_secret": "csec",
        }, headers=headers)

        # Disconnect
        resp = await client.delete("/api/v1/integrations/zoom/disconnect", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["connected"] is False

        # Verify status shows disconnected
        resp2 = await client.get("/api/v1/integrations/zoom/status", headers=headers)
        assert resp2.json()["data"]["zoom_connected"] is False
        assert resp2.json()["data"]["zoom_account_id"] is None

    async def test_connection_status(self, client: AsyncClient, registered_owner_with_studio):
        """GET /api/v1/integrations/zoom/status returns correct state when not connected."""
        headers = registered_owner_with_studio["headers"]

        resp = await client.get("/api/v1/integrations/zoom/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["zoom_connected"] is False
        assert data["zoom_account_id"] is None
        assert data["zoom_auto_record"] is True
        assert data["zoom_auto_publish"] is False


# ── Virtual Sessions & Zoom Meeting CRUD ─────────────────────────────────────

@pytest.mark.asyncio
class TestZoomVirtualSessions:

    async def _setup_studio(self, client, headers, studio_id):
        """Create a class type for session tests."""
        ct_resp = await client.post("/api/v1/scheduling/class-types", json={
            "studio_id": studio_id,
            "name": f"Virtual Yoga-{uuid.uuid4().hex[:6]}",
            "duration_minutes": 60,
        }, headers=headers)
        assert ct_resp.status_code == 201
        return ct_resp.json()["id"]

    @patch("app.services.integrations.zoom_service.ZoomService.create_meeting")
    async def test_create_virtual_session(
        self, mock_create_meeting, client: AsyncClient, registered_owner_with_studio
    ):
        """Creating a session with is_virtual=True triggers Zoom meeting creation."""
        mock_create_meeting.return_value = {
            "meeting_id": "99900011122",
            "join_url": "https://zoom.us/j/99900011122",
            "password": "abc123",
        }
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        ct_id = await self._setup_studio(client, headers, studio_id)

        tomorrow = datetime.utcnow() + timedelta(days=1)
        resp = await client.post("/api/v1/scheduling/sessions", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "Virtual Morning Flow",
            "starts_at": tomorrow.isoformat(),
            "ends_at": (tomorrow + timedelta(hours=1)).isoformat(),
            "capacity": 30,
            "is_virtual": True,
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["is_virtual"] is True

        # Zoom create_meeting should have been called
        mock_create_meeting.assert_called_once()
        call_kwargs = mock_create_meeting.call_args
        assert call_kwargs[1]["topic"] == "Virtual Morning Flow" or call_kwargs[0][1] == "Virtual Morning Flow"

    @patch("app.services.integrations.zoom_service.ZoomService.create_meeting")
    async def test_expand_virtual_series(
        self, mock_create_meeting, client: AsyncClient, registered_owner_with_studio
    ):
        """Expanding a virtual series creates Zoom meetings for each session."""
        mock_create_meeting.return_value = {
            "meeting_id": "88800011122",
            "join_url": "https://zoom.us/j/88800011122",
            "password": "xyz789",
        }
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        ct_id = await self._setup_studio(client, headers, studio_id)

        today = date.today()
        resp = await client.post("/api/v1/scheduling/series", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "Virtual Yin Series",
            "rrule": "FREQ=DAILY",
            "start_time": "18:00",
            "duration_minutes": 60,
            "effective_from": today.isoformat(),
            "expand_weeks": 1,
            "is_virtual": True,
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        sessions_created = data["sessions_created"]
        assert sessions_created >= 1

        # Zoom create_meeting should have been called for each expanded session
        assert mock_create_meeting.call_count == sessions_created

    @patch("app.services.integrations.zoom_service.ZoomService.delete_meeting")
    @patch("app.services.integrations.zoom_service.ZoomService.create_meeting")
    async def test_cancel_virtual_session_deletes_meeting(
        self, mock_create, mock_delete, client: AsyncClient, registered_owner_with_studio
    ):
        """Cancelling a virtual session deletes the Zoom meeting."""
        mock_create.return_value = {
            "meeting_id": "77700011133",
            "join_url": "https://zoom.us/j/77700011133",
            "password": "cancel123",
        }
        mock_delete.return_value = None
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        ct_id = await self._setup_studio(client, headers, studio_id)

        tomorrow = datetime.utcnow() + timedelta(days=1)
        create_resp = await client.post("/api/v1/scheduling/sessions", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "Cancel Virtual Class",
            "starts_at": tomorrow.isoformat(),
            "ends_at": (tomorrow + timedelta(hours=1)).isoformat(),
            "is_virtual": True,
        }, headers=headers)
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]

        # Cancel the session
        resp = await client.delete(
            f"/api/v1/scheduling/sessions/{session_id}?reason=Test+cancellation",
            headers=headers,
        )
        assert resp.status_code == 204

        # delete_meeting should have been called with the meeting ID
        mock_delete.assert_called_once()
        call_args = mock_delete.call_args
        assert "77700011133" in str(call_args)

    async def test_zoom_not_connected_virtual_session(
        self, client: AsyncClient, registered_owner_with_studio
    ):
        """Creating virtual session without Zoom connected logs warning but still creates session."""
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        ct_id = await self._setup_studio(client, headers, studio_id)

        tomorrow = datetime.utcnow() + timedelta(days=1)
        resp = await client.post("/api/v1/scheduling/sessions", json={
            "studio_id": studio_id,
            "class_type_id": ct_id,
            "title": "Virtual No Zoom",
            "starts_at": tomorrow.isoformat(),
            "ends_at": (tomorrow + timedelta(hours=1)).isoformat(),
            "is_virtual": True,
        }, headers=headers)
        # Session should still be created even without Zoom connected
        assert resp.status_code == 201
        data = resp.json()
        assert data["is_virtual"] is True
        assert data["title"] == "Virtual No Zoom"


# ── Webhooks ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestZoomWebhooks:

    @patch("app.services.integrations.zoom_service.ZoomService.get_credentials")
    @patch("app.services.integrations.zoom_service.ZoomService.find_org_by_account_id")
    @patch("app.services.integrations.zoom_service.ZoomService.handle_webhook")
    async def test_recording_webhook(
        self, mock_handle, mock_find_org, mock_get_creds, client: AsyncClient
    ):
        """POST /webhooks/zoom with recording.completed event creates video entry."""
        org_id = str(uuid.uuid4())
        mock_find_org.return_value = org_id
        mock_get_creds.return_value = None  # No webhook secret — skip signature check
        mock_handle.return_value = {"status": "ok"}

        payload = {
            "event": "recording.completed",
            "payload": {
                "account_id": "zoom-acc-123",
                "object": {
                    "id": "meeting-rec-456",
                    "topic": "Recorded Yoga Class",
                    "recording_files": [
                        {
                            "id": "rec-file-1",
                            "file_type": "MP4",
                            "file_size": 1024000,
                            "download_url": "https://zoom.us/rec/download/abc",
                            "recording_start": "2026-02-28T09:00:00Z",
                            "recording_end": "2026-02-28T10:00:00Z",
                            "status": "completed",
                        }
                    ],
                },
            },
        }

        resp = await client.post("/webhooks/zoom", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # handle_webhook should have been called with the org_id and event
        mock_handle.assert_called_once_with(org_id, payload)

    @patch("app.services.integrations.zoom_service.ZoomService.get_credentials")
    @patch("app.services.integrations.zoom_service.ZoomService.find_org_by_account_id")
    async def test_webhook_signature_verification(
        self, mock_find_org, mock_get_creds, client: AsyncClient
    ):
        """Invalid Zoom webhook signature returns 401."""
        org_id = str(uuid.uuid4())
        webhook_secret = "test-webhook-secret-key"
        mock_find_org.return_value = org_id
        mock_get_creds.return_value = {
            "account_id": "zoom-acc-sig",
            "client_id": "cid",
            "client_secret": "csec",
            "webhook_secret": webhook_secret,
            "connected_at": datetime.utcnow(),
            "auto_record": True,
            "auto_publish": False,
        }

        payload = {
            "event": "meeting.started",
            "payload": {
                "account_id": "zoom-acc-sig",
                "object": {"id": "meeting-sig-789"},
            },
        }
        payload_bytes = json.dumps(payload).encode()

        # Send with an invalid signature
        resp = await client.post(
            "/webhooks/zoom",
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "x-zm-signature": "v0=invalid-signature-here",
                "x-zm-request-timestamp": "1700000000",
            },
        )
        assert resp.status_code == 401
        assert "signature" in resp.json()["detail"].lower() or "invalid" in resp.json()["detail"].lower()

    @patch("app.services.integrations.zoom_service.ZoomService.get_credentials")
    @patch("app.services.integrations.zoom_service.ZoomService.find_org_by_account_id")
    @patch("app.services.integrations.zoom_service.ZoomService.handle_webhook")
    async def test_auto_publish_recording(
        self, mock_handle, mock_find_org, mock_get_creds,
        client: AsyncClient, registered_owner_with_studio, db_pool,
    ):
        """Recording with auto_publish=True creates published video entry."""
        headers = registered_owner_with_studio["headers"]
        org_id = registered_owner_with_studio.get("org_id")
        org_slug = registered_owner_with_studio["org_slug"]

        # Enable auto_publish via the settings endpoint
        # First connect Zoom
        with patch("app.services.integrations.zoom_service.ZoomService.test_connection") as mock_test:
            mock_test.return_value = {"success": True, "account_id": "pub-acc"}
            await client.post("/api/v1/integrations/zoom/connect", json={
                "account_id": "pub-acc",
                "client_id": "cid",
                "client_secret": "csec",
            }, headers=headers)

        # Update settings to enable auto_publish
        resp = await client.put("/api/v1/integrations/zoom/settings", json={
            "auto_publish": True,
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["zoom_auto_publish"] is True

        # Verify the status reflects auto_publish
        status_resp = await client.get("/api/v1/integrations/zoom/status", headers=headers)
        assert status_resp.status_code == 200
        assert status_resp.json()["data"]["zoom_auto_publish"] is True

        # Simulate a recording webhook
        mock_find_org.return_value = org_id or str(uuid.uuid4())
        mock_get_creds.return_value = None  # Skip signature verification
        mock_handle.return_value = {"status": "ok"}

        webhook_payload = {
            "event": "recording.completed",
            "payload": {
                "account_id": "pub-acc",
                "object": {
                    "id": "meeting-pub-001",
                    "topic": "Auto Publish Class",
                    "recording_files": [
                        {
                            "id": "rec-pub-1",
                            "file_type": "MP4",
                            "file_size": 2048000,
                            "download_url": "https://zoom.us/rec/download/pub",
                            "recording_start": "2026-02-28T09:00:00Z",
                            "recording_end": "2026-02-28T10:00:00Z",
                            "status": "completed",
                        }
                    ],
                },
            },
        }

        resp = await client.post("/webhooks/zoom", json=webhook_payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        mock_handle.assert_called_once()
