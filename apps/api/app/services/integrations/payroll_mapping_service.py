"""AuraFlow — Payroll Employee Mapping Service

Maps AuraFlow instructors to external payroll provider employee IDs
(Gusto or QuickBooks).
"""
import uuid

from app.core.logging import logger
from app.db.session import get_tenant_db


class PayrollMappingService:

    async def list_mappings(self, provider: str) -> list[dict]:
        """List all instructor-to-external-employee mappings for a provider."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT pem.*, i.display_name AS instructor_name
                FROM payroll_employee_mapping pem
                JOIN instructors i ON i.id = pem.instructor_id
                WHERE pem.provider = $1
                ORDER BY i.display_name
                """,
                provider,
            )
        return [_mapping_to_dict(r) for r in rows]

    async def upsert_mapping(
        self,
        instructor_id: str,
        provider: str,
        external_employee_id: str,
        external_employee_name: str | None = None,
    ) -> dict:
        """Create or update a mapping."""
        mapping_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO payroll_employee_mapping
                    (id, instructor_id, provider, external_employee_id, external_employee_name)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (instructor_id, provider) DO UPDATE
                SET external_employee_id = EXCLUDED.external_employee_id,
                    external_employee_name = EXCLUDED.external_employee_name,
                    mapped_at = NOW()
                """,
                mapping_id, instructor_id, provider,
                external_employee_id, external_employee_name,
            )
            row = await db.fetchrow(
                """
                SELECT pem.*, i.display_name AS instructor_name
                FROM payroll_employee_mapping pem
                JOIN instructors i ON i.id = pem.instructor_id
                WHERE pem.instructor_id = $1 AND pem.provider = $2
                """,
                instructor_id, provider,
            )
        logger.info(
            "Payroll mapping upserted",
            instructor_id=instructor_id,
            provider=provider,
            external_id=external_employee_id,
        )
        return _mapping_to_dict(row)

    async def delete_mapping(self, instructor_id: str, provider: str) -> None:
        """Remove a mapping."""
        async with get_tenant_db() as db:
            await db.execute(
                """
                DELETE FROM payroll_employee_mapping
                WHERE instructor_id = $1 AND provider = $2
                """,
                instructor_id, provider,
            )
        logger.info(
            "Payroll mapping deleted",
            instructor_id=instructor_id,
            provider=provider,
        )


def _mapping_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "instructor_id"):
        if d.get(k):
            d[k] = str(d[k])
    if d.get("mapped_at"):
        d["mapped_at"] = d["mapped_at"].isoformat()
    return d
