"""HL7v2 EMR client implementation.

Sends HL7v2 messages over MLLP (Minimal Lower Layer Protocol) via TCP.
Supports ADT (Admit/Discharge/Transfer) and SIU (Scheduling) message types.
"""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.logging import logger
from app.services.integrations.emr.base_client import EmrClient

# MLLP framing characters
MLLP_START = b"\x0b"
MLLP_END = b"\x1c\x0d"
FIELD_SEP = "|"
COMPONENT_SEP = "^"


class Hl7Client(EmrClient):
    """HL7v2 MLLP client."""

    def __init__(self, host: str, port: int, sending_app: str = "AURAFLOW"):
        self.host = host
        self.port = port
        self.sending_app = sending_app

    async def _send_message(self, message: str) -> str:
        """Send an HL7v2 message via MLLP and return the ACK response."""
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=30,
        )

        try:
            # Wrap message in MLLP framing
            payload = MLLP_START + message.encode("utf-8") + MLLP_END
            writer.write(payload)
            await writer.drain()

            # Read ACK response
            data = await asyncio.wait_for(reader.read(8192), timeout=30)
            response = data.decode("utf-8").strip("\x0b\x1c\x0d")
            return response
        finally:
            writer.close()
            await writer.wait_closed()

    def _make_msh(self, message_type: str, trigger_event: str) -> str:
        """Build MSH (Message Header) segment."""
        now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        control_id = str(uuid.uuid4())[:20]
        return FIELD_SEP.join([
            "MSH",
            "^~\\&",                     # Encoding characters
            self.sending_app,            # Sending application
            "AURAFLOW_FACILITY",         # Sending facility
            "EMR_APP",                   # Receiving application
            "EMR_FACILITY",              # Receiving facility
            now,                         # Date/time
            "",                          # Security
            f"{message_type}{COMPONENT_SEP}{trigger_event}",  # Message type
            control_id,                  # Message control ID
            "P",                         # Processing ID (P=production)
            "2.5.1",                     # HL7 version
        ])

    def _make_pid(self, member_data: dict, emr_patient_id: str = "") -> str:
        """Build PID (Patient Identification) segment."""
        dob = ""
        if member_data.get("date_of_birth"):
            d = member_data["date_of_birth"]
            dob = d.strftime("%Y%m%d") if hasattr(d, "strftime") else str(d).replace("-", "")

        gender_map = {"male": "M", "female": "F", "non_binary": "O"}
        gender = gender_map.get(member_data.get("gender", ""), "U")

        name = f"{member_data.get('last_name', '')}{COMPONENT_SEP}{member_data.get('first_name', '')}"
        address = COMPONENT_SEP.join([
            member_data.get("address_line1", ""),
            "",
            member_data.get("city", ""),
            member_data.get("state", ""),
            member_data.get("postal_code", ""),
        ])

        phone = member_data.get("phone", "")
        email = member_data.get("email", "")

        fields = [
            "PID",
            "1",                         # Set ID
            emr_patient_id,              # Patient ID (external)
            str(member_data.get("id", "")),  # Patient ID (internal/AuraFlow)
            "",                          # Alternate Patient ID
            name,                        # Patient name
            "",                          # Mother's maiden name
            dob,                         # Date of birth
            gender,                      # Sex
            "",                          # Patient alias
            "",                          # Race
            address,                     # Patient address
            "",                          # County code
            phone,                       # Phone (home)
            "",                          # Phone (business)
            "",                          # Primary language
            "",                          # Marital status
            "",                          # Religion
            "",                          # Patient account number
            "",                          # SSN
            "",                          # Driver's license
            "",                          # Mother's identifier
            "",                          # Ethnic group
            "",                          # Birth place
            "",                          # Multiple birth indicator
            "",                          # Birth order
            "",                          # Citizenship
            "",                          # Veterans military status
            "",                          # Nationality
            "",                          # Patient death date and time
            "",                          # Patient death indicator
        ]

        # Add email as PID-13 repeat
        if email:
            fields[13] = f"{phone}~{COMPONENT_SEP}{COMPONENT_SEP}{COMPONENT_SEP}{email}"

        return FIELD_SEP.join(fields)

    def _make_evn(self, trigger_event: str) -> str:
        """Build EVN (Event Type) segment."""
        now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"EVN{FIELD_SEP}{trigger_event}{FIELD_SEP}{now}"

    async def test_connection(self) -> bool:
        """Test the MLLP connection by opening and closing a socket."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception as e:
            logger.warning("HL7 connection test failed", error=str(e))
            return False

    async def create_patient(self, member_data: dict) -> str:
        """Send ADT^A04 (Register a Patient) message."""
        segments = [
            self._make_msh("ADT", "A04"),
            self._make_evn("A04"),
            self._make_pid(member_data),
        ]
        message = "\r".join(segments)
        response = await self._send_message(message)

        # Parse ACK to extract patient ID if present
        patient_id = self._parse_ack_patient_id(response)
        if not patient_id:
            patient_id = f"HL7-{uuid.uuid4().hex[:12]}"

        logger.info("HL7 Patient registered", emr_patient_id=patient_id)
        return patient_id

    async def update_patient(self, emr_patient_id: str, member_data: dict) -> bool:
        """Send ADT^A08 (Update Patient Information) message."""
        segments = [
            self._make_msh("ADT", "A08"),
            self._make_evn("A08"),
            self._make_pid(member_data, emr_patient_id=emr_patient_id),
        ]
        message = "\r".join(segments)
        response = await self._send_message(message)
        return self._is_ack_success(response)

    async def search_patient(
        self, email: Optional[str] = None, name: Optional[str] = None
    ) -> Optional[dict]:
        """HL7v2 doesn't natively support search queries.

        Returns None — search must be done via other means (e.g., an API layer
        on top of the EMR, or manual mapping during initial setup).
        """
        logger.info("HL7v2 patient search not supported; use manual mapping or FHIR")
        return None

    async def create_encounter(self, emr_patient_id: str, encounter_data: dict) -> str:
        """Send SIU^S12 (New Appointment Booking) message."""
        segments = [
            self._make_msh("SIU", "S12"),
            self._make_sch(encounter_data),
            self._make_pid_ref(emr_patient_id),
            self._make_aig(encounter_data),
        ]
        message = "\r".join(segments)
        response = await self._send_message(message)

        encounter_id = self._parse_ack_encounter_id(response)
        if not encounter_id:
            encounter_id = f"HL7-ENC-{uuid.uuid4().hex[:12]}"

        logger.info(
            "HL7 Encounter created",
            emr_encounter_id=encounter_id,
            class_title=encounter_data.get("class_title"),
        )
        return encounter_id

    def _make_sch(self, data: dict) -> str:
        """Build SCH (Scheduling Activity) segment."""
        start = data.get("session_start", "")
        end = data.get("session_end", "")
        # Convert ISO to HL7 datetime format
        if start and "T" in start:
            start = start.replace("-", "").replace(":", "").replace("T", "")[:14]
        if end and "T" in end:
            end = end.replace("-", "").replace(":", "").replace("T", "")[:14]

        appt_id = str(uuid.uuid4())[:20]
        reason = data.get("class_title", "Wellness Class")

        return FIELD_SEP.join([
            "SCH",
            appt_id,                    # Placer Appointment ID
            "",                          # Filler Appointment ID
            "",                          # Occurrence Number
            "",                          # Placer Group Number
            "",                          # Schedule ID
            "",                          # Event Reason
            f"{COMPONENT_SEP}{COMPONENT_SEP}{COMPONENT_SEP}{COMPONENT_SEP}{COMPONENT_SEP}{reason}",  # Appointment Reason
            data.get("encounter_type", "group_class"),  # Appointment Type
            "",                          # Appointment Duration
            "",                          # Appointment Duration Units
            f"{start}{COMPONENT_SEP}{end}",  # Appointment Timing Quantity
        ])

    def _make_pid_ref(self, emr_patient_id: str) -> str:
        """Build minimal PID segment referencing existing patient."""
        return f"PID{FIELD_SEP}1{FIELD_SEP}{emr_patient_id}"

    def _make_aig(self, data: dict) -> str:
        """Build AIG (Appointment Information - General Resource) segment."""
        instructor = data.get("instructor_name", "")
        return f"AIG{FIELD_SEP}1{FIELD_SEP}{FIELD_SEP}{instructor}"

    def _is_ack_success(self, response: str) -> bool:
        """Check if the HL7 ACK indicates success (AA or CA)."""
        if not response:
            return False
        # MSA segment: MSA|AA|control_id
        for line in response.split("\r"):
            if line.startswith("MSA"):
                fields = line.split(FIELD_SEP)
                if len(fields) > 1 and fields[1] in ("AA", "CA"):
                    return True
        return False

    def _parse_ack_patient_id(self, response: str) -> Optional[str]:
        """Try to extract a patient ID from the ACK response."""
        if not response:
            return None
        for line in response.split("\r"):
            if line.startswith("PID"):
                fields = line.split(FIELD_SEP)
                if len(fields) > 2 and fields[2]:
                    return fields[2]
        return None

    def _parse_ack_encounter_id(self, response: str) -> Optional[str]:
        """Try to extract an encounter/appointment ID from the ACK response."""
        if not response:
            return None
        for line in response.split("\r"):
            if line.startswith("SCH"):
                fields = line.split(FIELD_SEP)
                if len(fields) > 2 and fields[2]:
                    return fields[2]
        return None
