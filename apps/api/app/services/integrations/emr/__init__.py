"""AuraFlow — EMR Integration (FHIR R4 & HL7v2)

Bidirectional patient/member sync and encounter/appointment sync
between AuraFlow and EMR systems.
"""
from app.services.integrations.emr.emr_service import EmrService

emr_service = EmrService()

__all__ = ["EmrService", "emr_service"]
