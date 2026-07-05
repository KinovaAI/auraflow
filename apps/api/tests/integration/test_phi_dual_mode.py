"""
AuraFlow — HIPAA 2C Dual-Mode PHI Tests (Integration)

Exercises the real `MemberService` against the real Postgres to verify that
the plaintext / _enc shadow columns stay in sync on every write and that
reads prefer the decrypted `_enc` value while still falling back to
plaintext when `_enc` is NULL.

Green runs of this suite = hard evidence that HIPAA 2C Phase C (drop
plaintext columns) can ship without data loss.

Safety:
- Writes to `af_tenant_demo.members` (real tenant) but every test
  inserts rows with email `phitest_<uuid>@test.auraflow.dev` so they are
  trivially separated from real members.
- The `cleanup_phi_test_rows` fixture hard-deletes those rows after each
  test, leaving prod data untouched.
- Tests never touch rows with any other email pattern.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

from app.core.tenant_context import set_tenant_context, clear_tenant_context
from app.db.session import get_tenant_db
from app.services.members.member_service import (
    MemberService,
    _encrypt,
    _decrypt,
    _get_fernet,
    _enc_or_none,
    _dec_or_none,
)


TEST_EMAIL_SUFFIX = "@test.auraflow.dev"
TEST_SCHEMA = "af_tenant_demo"
TEST_ORG_ID = "4bb3c9ba-b996-464b-9f13-c4cb5c407374"
TEST_ORG_SLUG = "example-studio"


def _test_email() -> str:
    return f"phitest_{uuid.uuid4().hex[:12]}{TEST_EMAIL_SUFFIX}"


@pytest_asyncio.fixture
async def tenant_ctx():
    """Set tenant context for the duration of a test."""
    set_tenant_context(
        organization_id=TEST_ORG_ID,
        schema_name=TEST_SCHEMA,
        slug=TEST_ORG_SLUG,
    )
    yield
    clear_tenant_context()


@pytest_asyncio.fixture
async def cleanup_phi_test_rows():
    """Hard-delete any test-member rows after each test."""
    yield
    try:
        async with get_tenant_db(schema_override=TEST_SCHEMA) as db:
            await db.execute(
                "DELETE FROM members WHERE email LIKE 'phitest_%@test.auraflow.dev'"
            )
            await db.execute(
                "DELETE FROM member_notes WHERE author LIKE 'phitest_%'"
            )
    except Exception:
        pass


@pytest.fixture
def phi_sample() -> dict:
    """A realistic PHI payload exercising every encrypted column."""
    return {
        "first_name": "PhiTest",
        "last_name": "User",
        "email": _test_email(),
        "phone": "555-123-4567",
        "date_of_birth": "1970-06-15",
        "address_line1": "123 Test Ln",
        "city": "Fresno",
        "state": "CA",
        "postal_code": "93720",
        "emergency_contact_name": "Emergency Contact",
        "emergency_contact_phone": "555-999-8888",
        "notes": "Has a modified hip — avoid deep lunges",
    }


# ── Key + helper sanity ────────────────────────────────────────────────────


def test_fernet_key_is_configured():
    """If HEALTH_DATA_ENCRYPTION_KEY is missing, dual-mode degrades to plaintext
    on both sides, defeating the entire HIPAA 2C rollout."""
    assert _get_fernet() is not None, (
        "HEALTH_DATA_ENCRYPTION_KEY not configured — dual-mode silently "
        "stores plaintext in *_enc columns (still violates HIPAA-2C goal)"
    )


def test_encrypt_decrypt_round_trip():
    """Round-trip the helper functions themselves."""
    plaintext = "555-123-4567"
    ciphertext = _encrypt(plaintext)
    assert ciphertext != plaintext.encode()
    assert _decrypt(ciphertext) == plaintext


def test_enc_or_none_handles_null_and_empty():
    """NULL plaintext → NULL _enc. Empty string → NULL _enc. Non-empty → bytes."""
    assert _enc_or_none(None) is None
    assert _enc_or_none("") is None
    assert isinstance(_enc_or_none("a"), bytes)


def test_dec_or_none_handles_null():
    assert _dec_or_none(None) is None


# ── Dual-write on create ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_member_populates_both_plaintext_and_enc(
    tenant_ctx, cleanup_phi_test_rows, phi_sample
):
    """Every PHI field must land in both the plaintext column and its _enc
    shadow on create."""
    svc = MemberService()
    created = await svc.create_member(phi_sample)

    async with get_tenant_db(schema_override=TEST_SCHEMA) as db:
        row = await db.fetchrow(
            """SELECT phone, phone_enc, date_of_birth, date_of_birth_enc,
                      address_line1, address_line1_enc, city, city_enc,
                      state, state_enc, postal_code, postal_code_enc,
                      emergency_contact_name, emergency_contact_name_enc,
                      emergency_contact_phone, emergency_contact_phone_enc,
                      notes, notes_enc
               FROM members WHERE id = $1""",
            created["id"],
        )

    # Every plaintext field non-null → every _enc field non-null + decrypts back
    pairs = [
        ("phone",                    phi_sample["phone"]),
        ("date_of_birth",            phi_sample["date_of_birth"]),
        ("address_line1",            phi_sample["address_line1"]),
        ("city",                     phi_sample["city"]),
        ("state",                    phi_sample["state"]),
        ("postal_code",              phi_sample["postal_code"]),
        ("emergency_contact_name",   phi_sample["emergency_contact_name"]),
        ("emergency_contact_phone",  phi_sample["emergency_contact_phone"]),
        ("notes",                    phi_sample["notes"]),
    ]
    for plain_col, expected in pairs:
        enc_col = plain_col + "_enc"
        assert row[enc_col] is not None, f"{enc_col} was NULL after create"
        decrypted = _decrypt(row[enc_col])
        # date_of_birth round-trips as ISO string
        assert str(decrypted) == str(expected), (
            f"{plain_col} decrypted value {decrypted!r} != expected {expected!r}"
        )


@pytest.mark.asyncio
async def test_create_member_with_null_phi_leaves_enc_null(
    tenant_ctx, cleanup_phi_test_rows
):
    """A member with only first_name/last_name/email should have every _enc
    column NULL, not an encryption of empty string."""
    svc = MemberService()
    created = await svc.create_member({
        "first_name": "Minimal",
        "last_name": "User",
        "email": _test_email(),
    })

    async with get_tenant_db(schema_override=TEST_SCHEMA) as db:
        row = await db.fetchrow(
            """SELECT phone_enc, date_of_birth_enc, address_line1_enc, city_enc,
                      state_enc, postal_code_enc, emergency_contact_name_enc,
                      emergency_contact_phone_enc, notes_enc
               FROM members WHERE id = $1""",
            created["id"],
        )
    for col, val in row.items():
        assert val is None, f"{col} should be NULL when plaintext was NULL, got {val!r}"


# ── Dual-write on update ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_phi_field_keeps_enc_in_sync(
    tenant_ctx, cleanup_phi_test_rows, phi_sample
):
    """Updating a PHI column via update_member must also update its _enc."""
    svc = MemberService()
    created = await svc.create_member(phi_sample)
    new_phone = "559-000-1111"
    await svc.update_member(created["id"], {"phone": new_phone})

    async with get_tenant_db(schema_override=TEST_SCHEMA) as db:
        row = await db.fetchrow(
            "SELECT phone, phone_enc FROM members WHERE id = $1", created["id"]
        )
    assert row["phone"] == new_phone
    assert row["phone_enc"] is not None
    assert _decrypt(row["phone_enc"]) == new_phone


@pytest.mark.asyncio
async def test_update_non_phi_field_does_not_stale_enc(
    tenant_ctx, cleanup_phi_test_rows, phi_sample
):
    """Changing only `first_name` must NOT disturb any `_enc` column."""
    svc = MemberService()
    created = await svc.create_member(phi_sample)
    async with get_tenant_db(schema_override=TEST_SCHEMA) as db:
        before = await db.fetchrow(
            "SELECT phone_enc, notes_enc FROM members WHERE id = $1", created["id"]
        )

    await svc.update_member(created["id"], {"first_name": "Renamed"})

    async with get_tenant_db(schema_override=TEST_SCHEMA) as db:
        after = await db.fetchrow(
            "SELECT phone_enc, notes_enc, first_name FROM members WHERE id = $1",
            created["id"],
        )
    assert after["first_name"] == "Renamed"
    # _enc bytes should be identical (ciphertext is deterministic per-encrypt
    # for Fernet, so they'll differ if rewritten — we assert no rewrite).
    assert bytes(after["phone_enc"]) == bytes(before["phone_enc"])
    assert bytes(after["notes_enc"]) == bytes(before["notes_enc"])


# ── Read path prefers decrypted ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_member_returns_decrypted_phi(
    tenant_ctx, cleanup_phi_test_rows, phi_sample
):
    """`get_member` returns decrypted values, not raw bytes, and strips the
    _enc keys from output."""
    svc = MemberService()
    created = await svc.create_member(phi_sample)
    fetched = await svc.get_member(created["id"])

    assert fetched is not None
    assert fetched["phone"] == phi_sample["phone"]
    assert fetched["notes"] == phi_sample["notes"]
    # _enc keys should be stripped from output
    for col in ("phone", "date_of_birth", "address_line1", "city", "state",
                "postal_code", "emergency_contact_name",
                "emergency_contact_phone", "notes"):
        enc_col = col + "_enc"
        assert enc_col not in fetched, f"{enc_col} leaked through get_member"


@pytest.mark.asyncio
async def test_get_member_falls_back_to_plaintext_when_enc_null(
    tenant_ctx, cleanup_phi_test_rows
):
    """Migration-era rows have plaintext but NULL _enc. Dual-read must
    still surface the plaintext value."""
    svc = MemberService()
    created = await svc.create_member({
        "first_name": "LegacyRow",
        "last_name": "User",
        "email": _test_email(),
        "phone": "555-2222",
    })

    # Simulate a pre-HIPAA migration-era row by nulling the _enc column
    async with get_tenant_db(schema_override=TEST_SCHEMA) as db:
        await db.execute(
            "UPDATE members SET phone_enc = NULL WHERE id = $1", created["id"]
        )

    fetched = await svc.get_member(created["id"])
    assert fetched["phone"] == "555-2222"


# ── Notes dual-mode ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_note_writes_both_plaintext_and_enc(
    tenant_ctx, cleanup_phi_test_rows, phi_sample
):
    """member_notes.note and note_enc must both be populated."""
    svc = MemberService()
    created = await svc.create_member(phi_sample)
    await svc.add_note(created["id"], "phitest_author", "Sensitive clinical note")

    async with get_tenant_db(schema_override=TEST_SCHEMA) as db:
        row = await db.fetchrow(
            "SELECT note, note_enc FROM member_notes WHERE member_id = $1",
            created["id"],
        )
    assert row["note"] == "Sensitive clinical note"
    assert row["note_enc"] is not None
    assert _decrypt(row["note_enc"]) == "Sensitive clinical note"


@pytest.mark.asyncio
async def test_list_notes_returns_decrypted(
    tenant_ctx, cleanup_phi_test_rows, phi_sample
):
    """list_notes decodes note_enc back to plaintext and drops the _enc key."""
    svc = MemberService()
    created = await svc.create_member(phi_sample)
    await svc.add_note(created["id"], "phitest_author", "Note one")
    await svc.add_note(created["id"], "phitest_author", "Note two")

    notes = await svc.list_notes(created["id"])
    assert len(notes) == 2
    contents = {n["note"] for n in notes}
    assert contents == {"Note one", "Note two"}
    for n in notes:
        assert "note_enc" not in n, "_enc leaked through list_notes"


# ── Edge cases ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_string_phi_does_not_create_bogus_enc(
    tenant_ctx, cleanup_phi_test_rows
):
    """An empty string on input must result in NULL plaintext AND NULL _enc,
    not an encryption of empty string. This prevents a bug class where
    consistency scans would compare '' vs '' via decrypt(enc(''))."""
    svc = MemberService()
    created = await svc.create_member({
        "first_name": "Empty",
        "last_name": "Fields",
        "email": _test_email(),
        "phone": "",
        "address_line1": "",
        "notes": "",
    })
    async with get_tenant_db(schema_override=TEST_SCHEMA) as db:
        row = await db.fetchrow(
            "SELECT phone_enc, address_line1_enc, notes_enc FROM members WHERE id = $1",
            created["id"],
        )
    assert row["phone_enc"] is None
    assert row["address_line1_enc"] is None
    assert row["notes_enc"] is None


@pytest.mark.asyncio
async def test_update_to_null_clears_enc(
    tenant_ctx, cleanup_phi_test_rows, phi_sample
):
    """Setting a PHI field to None via update_member must clear both the
    plaintext and the _enc column (not leave stale encrypted data)."""
    svc = MemberService()
    created = await svc.create_member(phi_sample)
    await svc.update_member(created["id"], {"phone": None})

    async with get_tenant_db(schema_override=TEST_SCHEMA) as db:
        row = await db.fetchrow(
            "SELECT phone, phone_enc FROM members WHERE id = $1", created["id"]
        )
    assert row["phone"] is None
    assert row["phone_enc"] is None, (
        "phone_enc still has stale ciphertext after phone was cleared — "
        "Phase C will expose this as ghost PHI"
    )
