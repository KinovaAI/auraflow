"""Abstract EMR client interface.

Concrete implementations: FhirClient (REST/JSON) and Hl7Client (MLLP/pipe-delimited).
"""
from abc import ABC, abstractmethod
from typing import Optional


class EmrClient(ABC):
    """Protocol-agnostic interface for EMR operations."""

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test that the EMR connection is valid. Returns True if OK."""

    @abstractmethod
    async def create_patient(self, member_data: dict) -> str:
        """Create a patient in the EMR.

        Args:
            member_data: Dict with keys: first_name, last_name, email, phone,
                         date_of_birth, gender, address_line1, city, state, postal_code

        Returns:
            EMR patient identifier (FHIR Patient.id or MRN).
        """

    @abstractmethod
    async def update_patient(self, emr_patient_id: str, member_data: dict) -> bool:
        """Update an existing patient in the EMR. Returns True on success."""

    @abstractmethod
    async def search_patient(
        self, email: Optional[str] = None, name: Optional[str] = None
    ) -> Optional[dict]:
        """Search for an existing patient by email or name.

        Returns:
            Dict with keys: emr_patient_id, first_name, last_name, email, phone, etc.
            None if no match found.
        """

    @abstractmethod
    async def create_encounter(self, emr_patient_id: str, encounter_data: dict) -> str:
        """Create an encounter/appointment in the EMR.

        Args:
            emr_patient_id: The patient's EMR identifier.
            encounter_data: Dict with keys: class_title, class_type, instructor_name,
                            session_start (ISO), session_end (ISO), encounter_type,
                            notes

        Returns:
            EMR encounter/appointment identifier.
        """
