"""AuraFlow — Hiring / Applicant-Tracking + W-4 integration tests.

Covers the full lifecycle:
  public application submit (api-key) → resume upload → internal review
  (list/filter/status/rating/notes) → hire (creates user+org_user+instructor
  +studio assignment) → W-4 token → public sign (SSN encrypted, PDF stored)
  → restricted W-4 view.
"""
import uuid

import pytest
from httpx import AsyncClient


async def _mint_api_key(client: AsyncClient, jwt_headers: dict, scopes: list[str]) -> dict:
    resp = await client.post("/api/v1/external/api-keys", json={
        "name": f"hire-{uuid.uuid4().hex[:6]}", "scopes": scopes,
    }, headers=jwt_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _application_body(**over) -> dict:
    body = {
        "first_name": "Jane", "last_name": "Yogi",
        "email": f"applicant-{uuid.uuid4().hex[:8]}@test.auraflow.dev",
        "phone": "5595551234",
        "address_line1": "123 Calm St", "city": "Fresno", "state": "CA",
        "postal_code": "93701",
        "position_type": "instructor",
        "earliest_start_date": "2026-07-15",
        "authorized_to_work": True, "over_18": True,
        "years_experience": 8,
        "experience_seniors": "5 yrs teaching chair yoga at a senior center.",
        "experience_injuries": "Trained in working around knee + shoulder injuries.",
        "experience_pain": "Comfortable adapting for chronic lower-back pain.",
        "specialties": ["restorative", "chair", "prenatal"],
        "certifications": [{"name": "RYT-500", "issuer": "Yoga Alliance", "issued_on": "2020-01-01"}],
        "yoga_alliance_number": "YA-998877",
        "yoga_alliance_level": "RYT-500",
        "cpr_first_aid": True, "liability_insurance": True,
        "cover_letter": "I would love to serve your senior community.",
        "attestation": True,
    }
    body.update(over)
    return body


@pytest.mark.asyncio
class TestJobApplicationSubmission:

    async def test_submit_requires_api_key(self, client: AsyncClient):
        resp = await client.post("/api/v1/external/job-applications", json=_application_body())
        assert resp.status_code in (401, 403)

    async def test_submit_and_schema(self, client: AsyncClient, registered_owner_with_studio):
        jwt = registered_owner_with_studio["headers"]
        key = await _mint_api_key(client, jwt, ["applications:read", "applications:write"])
        ak = {"Authorization": f"Bearer {key['raw_key']}"}

        schema = await client.get("/api/v1/external/job-application/schema", headers=ak)
        assert schema.status_code == 200
        assert "instructor" in schema.json()["data"]["position_types"]

        resp = await client.post("/api/v1/external/job-applications",
                                 json=_application_body(), headers=ak)
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["status"] == "new"
        assert uuid.UUID(data["id"])

    async def test_attestation_required(self, client: AsyncClient, registered_owner_with_studio):
        jwt = registered_owner_with_studio["headers"]
        key = await _mint_api_key(client, jwt, ["applications:write"])
        ak = {"Authorization": f"Bearer {key['raw_key']}"}
        resp = await client.post("/api/v1/external/job-applications",
                                 json=_application_body(attestation=False), headers=ak)
        assert resp.status_code == 422

    async def test_upload_resume(self, client: AsyncClient, registered_owner_with_studio):
        jwt = registered_owner_with_studio["headers"]
        key = await _mint_api_key(client, jwt, ["applications:write"])
        ak = {"Authorization": f"Bearer {key['raw_key']}"}
        app = (await client.post("/api/v1/external/job-applications",
                                 json=_application_body(), headers=ak)).json()["data"]
        files = {"file": ("resume.pdf", b"%PDF-1.4 fake pdf bytes", "application/pdf")}
        resp = await client.post(
            f"/api/v1/external/job-applications/{app['id']}/documents",
            data={"doc_type": "resume"}, files=files, headers=ak,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["doc_type"] == "resume"

    async def test_upload_rejects_bad_type(self, client: AsyncClient, registered_owner_with_studio):
        jwt = registered_owner_with_studio["headers"]
        key = await _mint_api_key(client, jwt, ["applications:write"])
        ak = {"Authorization": f"Bearer {key['raw_key']}"}
        app = (await client.post("/api/v1/external/job-applications",
                                 json=_application_body(), headers=ak)).json()["data"]
        files = {"file": ("virus.exe", b"MZ...", "application/x-msdownload")}
        resp = await client.post(
            f"/api/v1/external/job-applications/{app['id']}/documents",
            data={"doc_type": "resume"}, files=files, headers=ak,
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestReviewPipeline:

    async def _submit(self, client, ak, **over):
        return (await client.post("/api/v1/external/job-applications",
                                  json=_application_body(**over), headers=ak)).json()["data"]

    async def test_list_filter_and_status(self, client: AsyncClient, registered_owner_with_studio):
        jwt = registered_owner_with_studio["headers"]
        key = await _mint_api_key(client, jwt, ["applications:write"])
        ak = {"Authorization": f"Bearer {key['raw_key']}"}
        app = await self._submit(client, ak)

        # Owner has all permissions → can view.
        lst = await client.get("/api/v1/hiring?status=new", headers=jwt)
        assert lst.status_code == 200, lst.text
        ids = [a["id"] for a in lst.json()["data"]]
        assert app["id"] in ids

        # Move through the pipeline; first move stamps reviewed_at.
        upd = await client.patch(f"/api/v1/hiring/{app['id']}",
                                 json={"status": "shortlisted", "rating": 5}, headers=jwt)
        assert upd.status_code == 200, upd.text
        assert upd.json()["data"]["status"] == "shortlisted"
        assert upd.json()["data"]["rating"] == 5
        assert upd.json()["data"]["reviewed_at"] is not None

        detail = await client.get(f"/api/v1/hiring/{app['id']}", headers=jwt)
        assert detail.status_code == 200
        dd = detail.json()["data"]
        # JSONB columns must come back as real arrays (not strings) — the
        # detail UI does .map/.length on them.
        assert isinstance(dd["certifications"], list)
        assert isinstance(dd["work_history"], list)
        assert isinstance(dd["references"], list)
        assert isinstance(dd["specialties"], list)
        events = [e["event_type"] for e in dd["events"]]
        assert "created" in events and "status_changed" in events and "rated" in events

    async def test_notes(self, client: AsyncClient, registered_owner_with_studio):
        jwt = registered_owner_with_studio["headers"]
        key = await _mint_api_key(client, jwt, ["applications:write"])
        ak = {"Authorization": f"Bearer {key['raw_key']}"}
        app = await self._submit(client, ak)
        note = await client.post(f"/api/v1/hiring/{app['id']}/notes",
                                 json={"note": "Strong senior-care background."}, headers=jwt)
        assert note.status_code == 200, note.text
        detail = await client.get(f"/api/v1/hiring/{app['id']}", headers=jwt)
        notes = [e for e in detail.json()["data"]["events"] if e["event_type"] == "note"]
        assert notes and notes[0]["note"] == "Strong senior-care background."

    async def test_invalid_status_rejected(self, client: AsyncClient, registered_owner_with_studio):
        jwt = registered_owner_with_studio["headers"]
        key = await _mint_api_key(client, jwt, ["applications:write"])
        ak = {"Authorization": f"Bearer {key['raw_key']}"}
        app = await self._submit(client, ak)
        resp = await client.patch(f"/api/v1/hiring/{app['id']}",
                                  json={"status": "bogus"}, headers=jwt)
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestHireAndW4:

    async def _submit(self, client, ak, **over):
        return (await client.post("/api/v1/external/job-applications",
                                  json=_application_body(**over), headers=ak)).json()["data"]

    async def test_hire_creates_instructor_and_w4(self, client: AsyncClient, registered_owner_with_studio):
        jwt = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        key = await _mint_api_key(client, jwt, ["applications:write"])
        ak = {"Authorization": f"Bearer {key['raw_key']}"}
        app = await self._submit(client, ak)

        hire = await client.post(f"/api/v1/hiring/{app['id']}/hire", json={
            "role": "instructor", "studio_id": studio_id,
            "pay_rate_cents": 6000, "pay_type": "per_class",
            "title": "Senior Yoga Instructor", "hire_date": "2026-07-15",
            "send_w4_email": False,
        }, headers=jwt)
        assert hire.status_code == 200, hire.text
        hd = hire.json()["data"]
        assert hd["user_id"] and hd["instructor_id"]
        assert hd["role"] == "instructor"
        assert hd["onboarding_token"] and hd["onboarding_status"] == "pending"

        # Application now shows hired.
        detail = (await client.get(f"/api/v1/hiring/{app['id']}", headers=jwt)).json()["data"]
        assert detail["status"] == "hired"
        assert detail["hired_user_id"] == hd["user_id"]

        # Instructor row exists.
        instructors = await client.get("/api/v1/instructors", headers=jwt)
        assert instructors.status_code == 200
        emails = [i.get("email") for i in (instructors.json().get("data") or instructors.json())]
        assert app["email"] in emails

        # ── Onboarding packet (public token flow) ──
        token = hd["onboarding_token"]
        packet = await client.get(f"/api/v1/external/onboarding/{token}")
        assert packet.status_code == 200, packet.text
        pd = packet.json()["data"]
        assert pd["status"] == "pending"
        doc_types = {d["doc_type"] for d in pd["documents"]}
        assert {"w4", "de4", "i9_section1", "dlse_nte", "dwc7"} <= doc_types

        # Sign every document. SSN forms need an SSN; the rest just a signature.
        ssn_forms = {"w4", "de4", "i9_section1"}
        for d in pd["documents"]:
            payload = {"signature_text": "Jane Yogi", "form_data": {}}
            if d["doc_type"] in ssn_forms:
                payload["ssn"] = "123-45-6789"
            if d["doc_type"] == "w4":
                payload["form_data"] = {"filing_status": "single", "dependents_amount_cents": 200000}
            if d["doc_type"] == "de4":
                payload["form_data"] = {"filing_status": "single", "allowances_regular": 1}
            if d["doc_type"] == "i9_section1":
                payload["form_data"] = {"citizenship_status": "citizen", "date_of_birth": "1980-01-01"}
            r = await client.post(
                f"/api/v1/external/onboarding/{token}/documents/{d['id']}/sign", json=payload,
            )
            assert r.status_code == 200, f"{d['doc_type']}: {r.text}"
            assert r.json()["data"]["status"] == "completed"

        # Packet token is single-use once everything is signed.
        again = await client.get(f"/api/v1/external/onboarding/{token}")
        assert again.status_code == 404

        # Internal packet view shows all complete + PDFs available.
        view = await client.get(f"/api/v1/hiring/employees/{hd['user_id']}/onboarding", headers=jwt)
        assert view.status_code == 200, view.text
        vd = view.json()["data"]
        assert vd["status"] == "completed"
        assert all(doc["status"] == "completed" and doc["has_pdf"] for doc in vd["documents"])

        w4_doc = next(d for d in vd["documents"] if d["doc_type"] == "w4")
        pdf = await client.get(
            f"/api/v1/hiring/employees/{hd['user_id']}/onboarding/documents/{w4_doc['id']}.pdf",
            headers=jwt,
        )
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content[:4] == b"%PDF"

    async def test_hire_front_desk_no_instructor_row(self, client: AsyncClient, registered_owner_with_studio):
        jwt = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        key = await _mint_api_key(client, jwt, ["applications:write"])
        ak = {"Authorization": f"Bearer {key['raw_key']}"}
        app = await self._submit(client, ak, position_type="front_desk")
        hire = await client.post(f"/api/v1/hiring/{app['id']}/hire", json={
            "role": "front_desk", "studio_id": studio_id, "send_w4_email": False,
        }, headers=jwt)
        assert hire.status_code == 200, hire.text
        assert hire.json()["data"]["instructor_id"] is None
        assert hire.json()["data"]["user_id"]

    async def test_double_hire_rejected(self, client: AsyncClient, registered_owner_with_studio):
        jwt = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        key = await _mint_api_key(client, jwt, ["applications:write"])
        ak = {"Authorization": f"Bearer {key['raw_key']}"}
        app = await self._submit(client, ak)
        body = {"role": "instructor", "studio_id": studio_id, "send_w4_email": False}
        first = await client.post(f"/api/v1/hiring/{app['id']}/hire", json=body, headers=jwt)
        assert first.status_code == 200
        second = await client.post(f"/api/v1/hiring/{app['id']}/hire", json=body, headers=jwt)
        assert second.status_code == 422

    async def test_w4_sign_bad_ssn_rejected(self, client: AsyncClient, registered_owner_with_studio):
        jwt = registered_owner_with_studio["headers"]
        studio_id = registered_owner_with_studio["studio_id"]
        key = await _mint_api_key(client, jwt, ["applications:write"])
        ak = {"Authorization": f"Bearer {key['raw_key']}"}
        app = await self._submit(client, ak)
        hire = (await client.post(f"/api/v1/hiring/{app['id']}/hire", json={
            "role": "instructor", "studio_id": studio_id, "send_w4_email": False,
        }, headers=jwt)).json()["data"]
        token = hire["onboarding_token"]
        packet = (await client.get(f"/api/v1/external/onboarding/{token}")).json()["data"]
        w4 = next(d for d in packet["documents"] if d["doc_type"] == "w4")
        resp = await client.post(
            f"/api/v1/external/onboarding/{token}/documents/{w4['id']}/sign",
            json={"ssn": "12345", "signature_text": "Jane Yogi",
                  "form_data": {"filing_status": "single"}},
        )
        assert resp.status_code == 422

    async def test_onboarding_token_unknown(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/external/onboarding/{'0' * 64}")
        assert resp.status_code == 404
