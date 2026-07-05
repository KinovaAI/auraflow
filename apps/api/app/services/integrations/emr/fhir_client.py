"""FHIR R4 EMR client implementation.

Uses httpx for REST calls. Supports OAuth2 client_credentials for authentication.
Maps AuraFlow data to FHIR Patient and Encounter resources.
"""
import time
from typing import Optional

import httpx

from app.core.logging import logger
from app.services.integrations.emr.base_client import EmrClient

# FHIR coding system for AuraFlow class types
AURAFLOW_SYSTEM = "http://auraflow.fit/class-type"


class FhirClient(EmrClient):
    """FHIR R4 REST client."""

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        token_url: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url or f"{self.base_url}/oauth2/token"
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    async def _get_token(self) -> str:
        """Get or refresh OAuth2 access token via client_credentials grant."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "system/*.read system/*.write",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 3600)
            return self._access_token

    async def _request(
        self, method: str, path: str, json_data: dict | None = None
    ) -> dict:
        """Make an authenticated FHIR API request."""
        token = await self._get_token()
        url = f"{self.base_url}/{path.lstrip('/')}"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method,
                url,
                json=json_data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/fhir+json",
                    "Accept": "application/fhir+json",
                },
            )
            resp.raise_for_status()
            return resp.json() if resp.content else {}

    async def test_connection(self) -> bool:
        """Test connection by reading the FHIR CapabilityStatement."""
        try:
            result = await self._request("GET", "/metadata")
            return result.get("resourceType") == "CapabilityStatement"
        except Exception as e:
            logger.warning("FHIR connection test failed", error=str(e))
            return False

    async def create_patient(self, member_data: dict) -> str:
        """Create a FHIR Patient resource from AuraFlow member data."""
        patient = self._build_patient_resource(member_data)
        result = await self._request("POST", "/Patient", patient)
        patient_id = result.get("id", "")
        logger.info("FHIR Patient created", emr_patient_id=patient_id)
        return patient_id

    async def update_patient(self, emr_patient_id: str, member_data: dict) -> bool:
        """Update an existing FHIR Patient resource."""
        patient = self._build_patient_resource(member_data)
        patient["id"] = emr_patient_id
        await self._request("PUT", f"/Patient/{emr_patient_id}", patient)
        return True

    async def search_patient(
        self, email: Optional[str] = None, name: Optional[str] = None
    ) -> Optional[dict]:
        """Search for a patient by email or name."""
        params = []
        if email:
            params.append(f"email={email}")
        if name:
            params.append(f"name={name}")
        if not params:
            return None

        query = "&".join(params)
        result = await self._request("GET", f"/Patient?{query}")

        entries = result.get("entry", [])
        if not entries:
            return None

        resource = entries[0].get("resource", {})
        return self._parse_patient_resource(resource)

    async def create_encounter(self, emr_patient_id: str, encounter_data: dict) -> str:
        """Create a FHIR Encounter resource from AuraFlow class attendance."""
        encounter = self._build_encounter_resource(emr_patient_id, encounter_data)
        result = await self._request("POST", "/Encounter", encounter)
        encounter_id = result.get("id", "")
        logger.info(
            "FHIR Encounter created",
            emr_encounter_id=encounter_id,
            class_title=encounter_data.get("class_title"),
        )
        return encounter_id

    # ── FHIR Resource Builders ────────────────────────────────────────────

    def _build_patient_resource(self, m: dict) -> dict:
        """Map AuraFlow member data to a FHIR R4 Patient resource."""
        resource: dict = {
            "resourceType": "Patient",
            "active": True,
            "name": [
                {
                    "use": "official",
                    "family": m.get("last_name", ""),
                    "given": [m.get("first_name", "")],
                }
            ],
        }

        # Contact info
        telecom = []
        if m.get("email"):
            telecom.append({"system": "email", "value": m["email"], "use": "home"})
        if m.get("phone"):
            telecom.append({"system": "phone", "value": m["phone"], "use": "mobile"})
        if telecom:
            resource["telecom"] = telecom

        # Demographics
        if m.get("date_of_birth"):
            dob = m["date_of_birth"]
            resource["birthDate"] = (
                dob.isoformat() if hasattr(dob, "isoformat") else str(dob)
            )

        gender_map = {"male": "male", "female": "female", "non_binary": "other"}
        if m.get("gender"):
            resource["gender"] = gender_map.get(m["gender"], "unknown")

        # Address
        if m.get("address_line1") or m.get("city"):
            address = {"use": "home"}
            if m.get("address_line1"):
                address["line"] = [m["address_line1"]]
            if m.get("city"):
                address["city"] = m["city"]
            if m.get("state"):
                address["state"] = m["state"]
            if m.get("postal_code"):
                address["postalCode"] = m["postal_code"]
            resource["address"] = [address]

        # AuraFlow member ID as identifier
        if m.get("id"):
            resource["identifier"] = [
                {
                    "system": "http://auraflow.fit/member-id",
                    "value": str(m["id"]),
                }
            ]

        return resource

    def _build_encounter_resource(
        self, emr_patient_id: str, data: dict
    ) -> dict:
        """Map AuraFlow class attendance to a FHIR R4 Encounter resource."""
        resource: dict = {
            "resourceType": "Encounter",
            "status": "finished",
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "AMB",
                "display": "ambulatory",
            },
            "subject": {"reference": f"Patient/{emr_patient_id}"},
            "serviceType": {
                "coding": [
                    {
                        "system": AURAFLOW_SYSTEM,
                        "code": data.get("class_type", "wellness-class"),
                        "display": data.get("class_title", "Wellness Class"),
                    }
                ],
                "text": data.get("class_title", "Wellness Class"),
            },
        }

        # Period
        period = {}
        if data.get("session_start"):
            period["start"] = data["session_start"]
        if data.get("session_end"):
            period["end"] = data["session_end"]
        if period:
            resource["period"] = period

        # Encounter type
        encounter_type = data.get("encounter_type", "group_class")
        type_display = {
            "group_class": "Group Wellness Class",
            "private_session": "Private Wellness Session",
            "workshop": "Wellness Workshop",
            "teacher_training": "Instructor Training",
        }
        resource["type"] = [
            {
                "coding": [
                    {
                        "system": AURAFLOW_SYSTEM,
                        "code": encounter_type,
                        "display": type_display.get(encounter_type, encounter_type),
                    }
                ],
                "text": type_display.get(encounter_type, encounter_type),
            }
        ]

        # Instructor as participant
        if data.get("instructor_name"):
            resource["participant"] = [
                {
                    "type": [
                        {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationType",
                                    "code": "PPRF",
                                    "display": "primary performer",
                                }
                            ]
                        }
                    ],
                    "individual": {"display": data["instructor_name"]},
                }
            ]

        # Notes
        if data.get("notes"):
            resource["text"] = {
                "status": "generated",
                "div": f'<div xmlns="http://www.w3.org/1999/xhtml">{data["notes"]}</div>',
            }

        return resource

    def _parse_patient_resource(self, resource: dict) -> dict:
        """Parse a FHIR Patient resource into a flat dict."""
        result: dict = {"emr_patient_id": resource.get("id", "")}

        # Name
        names = resource.get("name", [])
        if names:
            name = names[0]
            result["last_name"] = name.get("family", "")
            given = name.get("given", [])
            result["first_name"] = given[0] if given else ""

        # Contact
        for t in resource.get("telecom", []):
            if t.get("system") == "email":
                result["email"] = t.get("value")
            elif t.get("system") == "phone":
                result["phone"] = t.get("value")

        # Demographics
        result["date_of_birth"] = resource.get("birthDate")
        gender_map = {"male": "male", "female": "female", "other": "non_binary"}
        result["gender"] = gender_map.get(resource.get("gender", ""), None)

        # Address
        addresses = resource.get("address", [])
        if addresses:
            addr = addresses[0]
            lines = addr.get("line", [])
            result["address_line1"] = lines[0] if lines else None
            result["city"] = addr.get("city")
            result["state"] = addr.get("state")
            result["postal_code"] = addr.get("postalCode")

        return result
