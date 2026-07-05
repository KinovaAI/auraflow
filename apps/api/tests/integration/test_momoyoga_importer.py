"""AuraFlow — MomoYoga Importer Tests

Tests CSV parsing (unit-level) and import via API endpoints (integration).
"""
import uuid

import pytest
from httpx import AsyncClient

from app.services.import_export.momoyoga_importer import MomoYogaImporter


# ── Unit Tests: CSV Parsing ──────────────────────────────────────────────────

class TestMomoYogaCSVParsing:

    def test_parse_members_csv(self):
        csv = (
            "First Name,Last Name,Email,Phone,City\n"
            "Jane,Doe,jane@example.com,555-1234,Fresno\n"
            "John,Smith,john@example.com,,\n"
            ",,empty@test.com,,\n"  # Missing name — should be skipped
        )
        importer = MomoYogaImporter()
        result = importer.parse_members_csv(csv)
        assert len(result) == 2
        assert result[0]["first_name"] == "Jane"
        assert result[0]["email"] == "jane@example.com"
        assert result[0]["phone"] == "555-1234"
        assert result[0]["source"] == "momoyoga_import"
        assert result[1]["first_name"] == "John"
        assert result[1]["phone"] is None

    def test_parse_members_csv_alternate_columns(self):
        csv = (
            "FirstName,LastName,E-mail,Telephone\n"
            "Maria,Garcia,maria@example.com,559-999-0000\n"
        )
        importer = MomoYogaImporter()
        result = importer.parse_members_csv(csv)
        assert len(result) == 1
        assert result[0]["first_name"] == "Maria"
        assert result[0]["email"] == "maria@example.com"
        assert result[0]["phone"] == "559-999-0000"

    def test_parse_classes_csv(self):
        csv = (
            "Class,Teacher,Date,Time,Duration,Capacity,Attendees\n"
            "Vinyasa Flow,Sarah,2025-01-15,09:00,75,20,18\n"
            "Yin Yoga,Mike,2025-01-15,18:00,60,15,10\n"
            "Vinyasa Flow,Sarah,2025-01-17,09:00,75,20,15\n"
        )
        importer = MomoYogaImporter()
        result = importer.parse_classes_csv(csv)
        assert len(result) == 3
        assert result[0]["name"] == "Vinyasa Flow"
        assert result[0]["instructor"] == "Sarah"
        assert result[0]["duration"] == "75"

    def test_parse_memberships_csv(self):
        csv = (
            "Email,Subscription,Status,Start Date,End Date,Price\n"
            "jane@example.com,Unlimited Monthly,active,2025-01-01,2025-02-01,150\n"
            "john@example.com,10 Class Pack,active,2025-01-01,,100\n"
        )
        importer = MomoYogaImporter()
        result = importer.parse_memberships_csv(csv)
        assert len(result) == 2
        assert result[0]["member_email"] == "jane@example.com"
        assert result[0]["membership_name"] == "Unlimited Monthly"

    def test_empty_csv(self):
        importer = MomoYogaImporter()
        assert importer.parse_members_csv("First Name,Last Name,Email\n") == []
        assert importer.parse_classes_csv("Class,Teacher\n") == []


# ── Integration Tests: API Endpoints ─────────────────────────────────────────

@pytest.mark.asyncio
class TestMomoYogaDryRun:

    async def test_dry_run_members(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        csv_content = (
            "First Name,Last Name,Email,Phone\n"
            "Jane,Doe,jane-import@test.auraflow.dev,555-1234\n"
            "John,Smith,john-import@test.auraflow.dev,\n"
        )

        resp = await client.post(
            "/api/v1/import/csv/dry-run",
            files={"members_file": ("members.csv", csv_content, "text/csv")},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["members"]["total"] == 2
        assert data["members"]["new"] == 2
        assert data["members"]["existing"] == 0

    async def test_dry_run_no_files(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.post(
            "/api/v1/import/csv/dry-run",
            headers=headers,
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestMomoYogaImport:

    async def test_import_members(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        csv_content = (
            "First Name,Last Name,Email,Phone,City\n"
            f"Import,Test1,import1-{uuid.uuid4().hex[:6]}@test.auraflow.dev,555-0001,Fresno\n"
            f"Import,Test2,import2-{uuid.uuid4().hex[:6]}@test.auraflow.dev,555-0002,Fresno\n"
        )

        resp = await client.post(
            "/api/v1/import/csv/import/members",
            files={"file": ("members.csv", csv_content, "text/csv")},
            data={"studio_id": studio_id},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["imported"] == 2
        assert data["skipped"] == 0
        assert data["total"] == 2

    async def test_import_members_skip_duplicates(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        email = f"dup-{uuid.uuid4().hex[:6]}@test.auraflow.dev"

        # First, create a member via API
        await client.post("/api/v1/members", json={
            "first_name": "Existing",
            "last_name": "Member",
            "email": email,
        }, headers=headers)

        # Now try to import with same email
        csv_content = f"First Name,Last Name,Email\nExisting,Member,{email}\n"

        resp = await client.post(
            "/api/v1/import/csv/import/members",
            files={"file": ("members.csv", csv_content, "text/csv")},
            data={"studio_id": studio_id},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["imported"] == 0
        assert data["skipped"] == 1

    async def test_import_class_types(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        csv_content = (
            "Class,Teacher,Date,Time,Duration,Capacity\n"
            "Import Vinyasa,Sarah,2025-01-15,09:00,75,20\n"
            "Import Yin,Mike,2025-01-15,18:00,60,15\n"
            "Import Vinyasa,Sarah,2025-01-17,09:00,75,20\n"
        )

        resp = await client.post(
            "/api/v1/import/csv/import/class-types",
            files={"file": ("classes.csv", csv_content, "text/csv")},
            data={"studio_id": studio_id},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["created"] == 2  # "Import Vinyasa" and "Import Yin"
        assert data["total"] == 2
