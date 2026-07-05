"""AuraFlow — Import Integration Tests

MomoYoga CSV parsing, instructor/membership/attendance import, and endpoint tests.
"""
import uuid

import pytest
from httpx import AsyncClient

from app.services.import_export.momoyoga_importer import MomoYogaImporter


# ── Parsing Tests ─────────────────────────────────────────────────────────────

importer = MomoYogaImporter()


class TestMomoYogaParsing:

    def test_parse_instructors_csv(self):
        csv = "Teacher,Email,Phone\nJane Doe,jane@test.com,555-0100\nBob Smith,,\n"
        result = importer.parse_instructors_csv(csv)
        assert len(result) == 2
        assert result[0]["display_name"] == "Jane Doe"
        assert result[0]["email"] == "jane@test.com"
        assert result[1]["display_name"] == "Bob Smith"
        assert result[1]["email"] is None

    def test_infer_membership_type(self):
        assert importer._infer_membership_type("10 Class Pack") == "class_pack"
        assert importer._infer_membership_type("Drop-In") == "single_class"
        assert importer._infer_membership_type("Intro Offer") == "intro_offer"
        assert importer._infer_membership_type("Day Pass") == "day_pass"
        assert importer._infer_membership_type("Monthly Unlimited") == "unlimited"
        assert importer._infer_membership_type("Premium") == "unlimited"

    def test_parse_price(self):
        assert importer._parse_price("150") == 15000
        assert importer._parse_price("$29.99") == 2999
        assert importer._parse_price("$1,200.50") == 120050
        assert importer._parse_price("") == 0
        assert importer._parse_price("free") == 0

    def test_parse_date_formats(self):
        d1 = importer._parse_date("2024-06-15")
        assert d1 is not None
        assert d1.year == 2024 and d1.month == 6 and d1.day == 15

        d2 = importer._parse_date("06/15/2024")
        assert d2 is not None
        assert d2.month == 6

        d3 = importer._parse_date("15-06-2024")
        assert d3 is not None

        assert importer._parse_date("") is None
        assert importer._parse_date(None) is None

    def test_map_status(self):
        assert importer._map_status("active") == "active"
        assert importer._map_status("Actief") == "active"
        assert importer._map_status("cancelled") == "cancelled"
        assert importer._map_status("Opgezegd") == "cancelled"
        assert importer._map_status("Paused") == "frozen"
        assert importer._map_status("Verlopen") == "expired"
        assert importer._map_status("unknown") == "active"


# ── Import Tests ──────────────────────────────────────────────────────────────

MEMBERS_CSV = "First Name,Last Name,Email,Phone\nAlice,Wonder,alice@test.dev,555-0001\nBob,Builder,bob@test.dev,555-0002\n"

INSTRUCTORS_CSV = "Teacher,Email,Phone\nSarah Yoga,sarah@test.dev,555-1000\nMike Flow,mike@test.dev,555-1001\n"

CLASSES_CSV = "Class,Teacher,Date,Time,Duration,Capacity,Attendees\nVinyasa Flow,Sarah Yoga,2024-06-15,09:00,60,20,12\nYin Yoga,Mike Flow,2024-06-15,11:00,75,15,8\n"

MEMBERSHIPS_CSV = "Email,Subscription,Status,Start Date,End Date,Price\nalice@test.dev,Monthly Unlimited,active,2024-01-01,2024-12-31,$99\nbob@test.dev,10 Class Pack,active,2024-03-01,,$150\n"


async def _create_member_direct(client, headers, first_name, last_name, email):
    resp = await client.post("/api/v1/members", json={
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
class TestImportInstructors:

    async def test_import_creates_instructors(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        resp = await client.post(
            "/api/v1/import/csv/import/instructors",
            files={"file": ("instructors.csv", INSTRUCTORS_CSV.encode(), "text/csv")},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["created"] == 2
        assert data["skipped"] == 0
        assert data["total"] == 2

    async def test_import_dedup_skips_existing(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        # First import
        await client.post(
            "/api/v1/import/csv/import/instructors",
            files={"file": ("instructors.csv", INSTRUCTORS_CSV.encode(), "text/csv")},
            headers=headers,
        )
        # Second import — same names
        resp = await client.post(
            "/api/v1/import/csv/import/instructors",
            files={"file": ("instructors.csv", INSTRUCTORS_CSV.encode(), "text/csv")},
            headers=headers,
        )
        data = resp.json()["data"]
        assert data["created"] == 0
        assert data["skipped"] == 2


@pytest.mark.asyncio
class TestImportMemberships:

    async def test_creates_types_and_assigns(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        # Create the members first
        await _create_member_direct(client, headers, "Alice", "Wonder", "alice@test.dev")
        await _create_member_direct(client, headers, "Bob", "Builder", "bob@test.dev")

        resp = await client.post(
            "/api/v1/import/csv/import/memberships",
            data={"studio_id": studio_id},
            files={"file": ("memberships.csv", MEMBERSHIPS_CSV.encode(), "text/csv")},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["types_created"] == 2  # Monthly Unlimited + 10 Class Pack
        assert data["memberships_created"] == 2
        assert data["errors"] == []

    async def test_errors_on_missing_members(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        # Import memberships without importing members first
        csv = "Email,Subscription,Status,Price\nnoone@test.dev,Unlimited,active,$99\n"
        resp = await client.post(
            "/api/v1/import/csv/import/memberships",
            data={"studio_id": studio_id},
            files={"file": ("memberships.csv", csv.encode(), "text/csv")},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["memberships_created"] == 0
        assert len(data["errors"]) == 1
        assert "not found" in data["errors"][0]["error"].lower()


@pytest.mark.asyncio
class TestImportAttendance:

    async def test_creates_historical_sessions(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]

        # Import instructors first, then class types, then attendance
        await client.post(
            "/api/v1/import/csv/import/instructors",
            files={"file": ("instructors.csv", INSTRUCTORS_CSV.encode(), "text/csv")},
            headers=headers,
        )
        await client.post(
            "/api/v1/import/csv/import/class-types",
            data={"studio_id": studio_id},
            files={"file": ("classes.csv", CLASSES_CSV.encode(), "text/csv")},
            headers=headers,
        )

        resp = await client.post(
            "/api/v1/import/csv/import/attendance",
            data={"studio_id": studio_id},
            files={"file": ("classes.csv", CLASSES_CSV.encode(), "text/csv")},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["sessions_created"] == 2
        assert data["errors"] == []


@pytest.mark.asyncio
class TestDryRunEnhanced:

    async def test_all_four_file_types(self, client: AsyncClient, registered_owner_with_studio):
        headers = registered_owner_with_studio["headers"]

        resp = await client.post(
            "/api/v1/import/csv/dry-run",
            files={
                "members_file": ("members.csv", MEMBERS_CSV.encode(), "text/csv"),
                "classes_file": ("classes.csv", CLASSES_CSV.encode(), "text/csv"),
                "memberships_file": ("memberships.csv", MEMBERSHIPS_CSV.encode(), "text/csv"),
                "instructors_file": ("instructors.csv", INSTRUCTORS_CSV.encode(), "text/csv"),
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]

        assert data["members"]["total"] == 2
        assert data["members"]["new"] == 2
        assert data["classes"]["total"] == 2
        assert len(data["classes"]["class_types"]) == 2
        assert data["memberships"]["total"] == 2
        assert len(data["memberships"]["types"]) == 2
        assert data["instructors"]["total"] == 2
        assert data["instructors"]["new"] == 2
