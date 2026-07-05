"""AuraFlow — EMR Integration Service

Orchestrates bidirectional sync between AuraFlow and EMR systems.
Supports FHIR R4 (REST) and HL7v2 (MLLP) protocols.

Outbound: AuraFlow member creation -> EMR Patient, class attendance -> EMR Encounter
Inbound:  EMR Patient webhook -> AuraFlow member creation
"""
import uuid
from typing import Optional

from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.utils.encryption import encrypt_credential, decrypt_credential
from app.services.integrations.emr.base_client import EmrClient
from app.services.integrations.emr.fhir_client import FhirClient
from app.services.integrations.emr.hl7_client import Hl7Client


class EmrService:
    """Main EMR integration orchestration service."""

    # ── Connection Management ─────────────────────────────────────────────

    async def connect(
        self,
        org_id: str,
        protocol: str,
        config: dict,
    ) -> dict:
        """Store encrypted EMR credentials and enable sync.

        Args:
            org_id: Organization UUID.
            protocol: 'fhir_r4' or 'hl7v2'.
            config: Protocol-specific config:
                FHIR: base_url, client_id, client_secret, token_url (optional)
                HL7v2: host, port
        """
        if protocol not in ("fhir_r4", "hl7v2"):
            raise ValueError("Protocol must be 'fhir_r4' or 'hl7v2'")

        async with get_global_db() as db:
            if protocol == "fhir_r4":
                encrypted_id = await encrypt_credential(db, config["client_id"])
                encrypted_secret = await encrypt_credential(db, config["client_secret"])
                await db.execute(
                    """
                    UPDATE af_global.organizations
                    SET emr_protocol = $1,
                        emr_base_url = $2,
                        emr_client_id_encrypted = $3,
                        emr_client_secret_encrypted = $4,
                        emr_hl7_host = NULL,
                        emr_hl7_port = NULL,
                        emr_connected_at = NOW(),
                        emr_sync_enabled = TRUE,
                        updated_at = NOW()
                    WHERE id = $5
                    """,
                    protocol, config["base_url"], encrypted_id,
                    encrypted_secret, org_id,
                )
            else:  # hl7v2
                await db.execute(
                    """
                    UPDATE af_global.organizations
                    SET emr_protocol = $1,
                        emr_base_url = NULL,
                        emr_client_id_encrypted = NULL,
                        emr_client_secret_encrypted = NULL,
                        emr_hl7_host = $2,
                        emr_hl7_port = $3,
                        emr_connected_at = NOW(),
                        emr_sync_enabled = TRUE,
                        updated_at = NOW()
                    WHERE id = $4
                    """,
                    protocol, config["host"], config["port"], org_id,
                )

        # Test connection
        client = await self._get_client(org_id)
        connected = await client.test_connection()

        if not connected:
            # Disable sync if test fails
            async with get_global_db() as db:
                await db.execute(
                    "UPDATE af_global.organizations SET emr_sync_enabled = FALSE WHERE id = $1",
                    org_id,
                )
            raise ValueError("EMR connection test failed. Check credentials and endpoint.")

        logger.info("EMR connected", org_id=org_id, protocol=protocol)
        return {"status": "connected", "protocol": protocol}

    async def disconnect(self, org_id: str) -> bool:
        """Clear EMR credentials and disable sync."""
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET emr_protocol = NULL,
                    emr_base_url = NULL,
                    emr_client_id_encrypted = NULL,
                    emr_client_secret_encrypted = NULL,
                    emr_hl7_host = NULL,
                    emr_hl7_port = NULL,
                    emr_connected_at = NULL,
                    emr_sync_enabled = FALSE,
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id,
            )
        logger.info("EMR disconnected", org_id=org_id)
        return True

    async def get_status(self, org_id: str) -> dict:
        """Get EMR connection status for an organization."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT emr_protocol, emr_base_url, emr_hl7_host, emr_hl7_port,
                       emr_connected_at, emr_sync_enabled
                FROM af_global.organizations
                WHERE id = $1
                """,
                org_id,
            )

        if not row or not row["emr_protocol"]:
            return {"connected": False, "protocol": None, "sync_enabled": False}

        return {
            "connected": True,
            "protocol": row["emr_protocol"],
            "endpoint": row["emr_base_url"] or f"{row['emr_hl7_host']}:{row['emr_hl7_port']}",
            "connected_at": row["emr_connected_at"].isoformat() if row["emr_connected_at"] else None,
            "sync_enabled": row["emr_sync_enabled"],
        }

    async def test_connection(self, org_id: str) -> dict:
        """Test the current EMR connection."""
        try:
            client = await self._get_client(org_id)
            ok = await client.test_connection()
            return {"success": ok, "message": "Connection OK" if ok else "Connection failed"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Outbound Sync: AuraFlow -> EMR ────────────────────────────────────

    async def sync_member_to_emr(self, schema: str, member_id: str) -> Optional[str]:
        """Create or update a patient in the EMR from an AuraFlow member.

        Returns the EMR patient ID, or None if sync is disabled/fails.
        """
        # Resolve org_id from schema
        org_id = await self._org_id_from_schema(schema)
        if not org_id:
            return None

        # Check if EMR sync is enabled
        status = await self.get_status(org_id)
        if not status.get("sync_enabled"):
            return None

        # Get member data — pull encrypted shadows alongside plaintext so
        # the EMR API receives the actual PHI values regardless of which
        # column carries them. _row_with_decrypted_phi returns a dict
        # keyed on the public field names (phone, date_of_birth, etc.)
        # with the *_enc keys stripped.
        from app.services.members.member_service import _row_with_decrypted_phi
        async with get_tenant_db(schema_override=schema) as db:
            row = await db.fetchrow(
                """
                SELECT id, first_name, last_name, email, gender,
                       phone_enc, date_of_birth_enc, address_line1_enc,
                       city_enc, state_enc, postal_code_enc
                FROM members WHERE id = $1
                """,
                member_id,
            )
            if not row:
                logger.warning("EMR sync: member not found", member_id=member_id)
                return None

            member_data = _row_with_decrypted_phi(dict(row))

            # Check if already mapped
            existing = await db.fetchrow(
                "SELECT emr_patient_id FROM emr_patient_map WHERE member_id = $1",
                member_id,
            )

        client = await self._get_client(org_id)

        try:
            if existing:
                # Update existing patient
                emr_patient_id = existing["emr_patient_id"]
                await client.update_patient(emr_patient_id, member_data)
                async with get_tenant_db(schema_override=schema) as db:
                    await db.execute(
                        "UPDATE emr_patient_map SET last_synced_at = NOW(), updated_at = NOW() WHERE member_id = $1",
                        member_id,
                    )
            else:
                # Check if patient exists in EMR by email
                found = await client.search_patient(email=member_data.get("email"))
                if found:
                    emr_patient_id = found["emr_patient_id"]
                    await client.update_patient(emr_patient_id, member_data)
                else:
                    emr_patient_id = await client.create_patient(member_data)

                # Save mapping
                async with get_tenant_db(schema_override=schema) as db:
                    await db.execute(
                        """
                        INSERT INTO emr_patient_map
                            (id, member_id, emr_patient_id, emr_system, sync_direction, last_synced_at)
                        VALUES ($1, $2, $3, $4, 'outbound', NOW())
                        ON CONFLICT (member_id) DO UPDATE
                            SET emr_patient_id = $3, last_synced_at = NOW(), updated_at = NOW()
                        """,
                        str(uuid.uuid4()), member_id, emr_patient_id, status["protocol"],
                    )

            # Log sync
            await self._log_sync(
                schema, "outbound", "Patient", "create" if not existing else "update",
                emr_patient_id, member_id, "success",
            )

            logger.info(
                "Member synced to EMR",
                member_id=member_id,
                emr_patient_id=emr_patient_id,
            )
            return emr_patient_id

        except Exception as e:
            await self._log_sync(
                schema, "outbound", "Patient", "create",
                None, member_id, "failed", error=str(e),
            )
            logger.error("EMR member sync failed", member_id=member_id, error=str(e))
            return None

    async def sync_attendance_to_emr(self, schema: str, booking_id: str) -> Optional[str]:
        """Create an encounter in the EMR from a class check-in.

        Returns the EMR encounter ID, or None if sync is disabled/fails.
        """
        org_id = await self._org_id_from_schema(schema)
        if not org_id:
            return None

        status = await self.get_status(org_id)
        if not status.get("sync_enabled"):
            return None

        # Get booking + class + member data
        async with get_tenant_db(schema_override=schema) as db:
            row = await db.fetchrow(
                """
                SELECT b.id AS booking_id, b.member_id, b.checked_in_at,
                       cs.title AS class_title, cs.starts_at, cs.ends_at,
                       ct.name AS class_type,
                       i.display_name AS instructor_name,
                       pm.emr_patient_id
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                LEFT JOIN emr_patient_map pm ON pm.member_id = b.member_id
                WHERE b.id = $1
                """,
                booking_id,
            )

            if not row:
                logger.warning("EMR sync: booking not found", booking_id=booking_id)
                return None

            # Check if encounter already logged
            existing = await db.fetchrow(
                "SELECT emr_encounter_id FROM emr_encounter_log WHERE booking_id = $1 AND status = 'synced'",
                booking_id,
            )
            if existing:
                return existing["emr_encounter_id"]

        emr_patient_id = row["emr_patient_id"]

        # If member not yet in EMR, sync them first
        if not emr_patient_id:
            emr_patient_id = await self.sync_member_to_emr(schema, str(row["member_id"]))
            if not emr_patient_id:
                logger.warning("EMR sync: cannot sync encounter without patient", booking_id=booking_id)
                return None

        encounter_data = {
            "class_title": row["class_title"] or row["class_type"] or "Wellness Class",
            "class_type": row["class_type"] or "wellness-class",
            "instructor_name": row["instructor_name"],
            "session_start": row["starts_at"].isoformat() if row["starts_at"] else None,
            "session_end": row["ends_at"].isoformat() if row["ends_at"] else None,
            "encounter_type": "group_class",
        }

        client = await self._get_client(org_id)
        encounter_log_id = str(uuid.uuid4())

        try:
            emr_encounter_id = await client.create_encounter(emr_patient_id, encounter_data)

            # Log the encounter
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute(
                    """
                    INSERT INTO emr_encounter_log
                        (id, booking_id, member_id, emr_encounter_id, encounter_type,
                         class_title, instructor_name, session_start, session_end, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'synced')
                    """,
                    encounter_log_id, booking_id, str(row["member_id"]),
                    emr_encounter_id, "group_class",
                    encounter_data["class_title"], encounter_data.get("instructor_name"),
                    row["starts_at"], row["ends_at"],
                )

            await self._log_sync(
                schema, "outbound", "Encounter", "create",
                emr_encounter_id, booking_id, "success",
            )

            logger.info(
                "Attendance synced to EMR",
                booking_id=booking_id,
                emr_encounter_id=emr_encounter_id,
            )
            return emr_encounter_id

        except Exception as e:
            # Log failure for retry
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute(
                    """
                    INSERT INTO emr_encounter_log
                        (id, booking_id, member_id, encounter_type,
                         class_title, instructor_name, session_start, session_end,
                         status, error_message)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'failed', $9)
                    ON CONFLICT DO NOTHING
                    """,
                    encounter_log_id, booking_id, str(row["member_id"]),
                    "group_class", encounter_data["class_title"],
                    encounter_data.get("instructor_name"),
                    row["starts_at"], row["ends_at"], str(e),
                )

            await self._log_sync(
                schema, "outbound", "Encounter", "create",
                None, booking_id, "failed", error=str(e),
            )
            logger.error("EMR attendance sync failed", booking_id=booking_id, error=str(e))
            return None

    # ── Inbound Sync: EMR -> AuraFlow ─────────────────────────────────────

    async def sync_patient_to_auraflow(
        self, org_id: str, schema: str, patient_data: dict
    ) -> Optional[str]:
        """Create or update an AuraFlow member from EMR patient data.

        Args:
            org_id: Organization UUID.
            schema: Tenant schema name.
            patient_data: Dict with emr_patient_id, first_name, last_name, email, etc.

        Returns:
            AuraFlow member ID, or None on failure.
        """
        emr_patient_id = patient_data.get("emr_patient_id")
        if not emr_patient_id:
            logger.warning("EMR inbound sync: no patient ID provided")
            return None

        async with get_tenant_db(schema_override=schema) as db:
            # Check if already mapped
            existing = await db.fetchrow(
                "SELECT member_id FROM emr_patient_map WHERE emr_patient_id = $1",
                emr_patient_id,
            )

            if existing:
                # Update existing member.
                # HIPAA-2C Phase C: every PHI field must dual-write to its
                # _enc shadow AND, for phone, to phone_hash. Without this,
                # an EMR-driven update silently wipes the search/decrypt
                # path for that field after the plaintext drop.
                from app.services.members.member_service import (
                    _enc_or_none, _extract_birthday_parts,
                )
                from app.services.members.phone_hash import hash_phone

                # Post-Phase-C: PHI fields live only in *_enc shadows +
                # derived columns. Non-PHI fields (first_name, last_name,
                # email, gender) still write the plain column.
                _EMR_PHI_FIELDS = {
                    "phone", "date_of_birth", "address_line1",
                    "city", "state", "postal_code",
                }
                member_id = str(existing["member_id"])
                update_fields = []
                update_params = []
                idx = 2

                for field in ("first_name", "last_name", "email", "phone",
                              "date_of_birth", "gender", "address_line1",
                              "city", "state", "postal_code"):
                    if patient_data.get(field):
                        if field in _EMR_PHI_FIELDS:
                            update_fields.append(f"{field}_enc = ${idx}")
                            update_params.append(_enc_or_none(patient_data[field]))
                            idx += 1
                        else:
                            update_fields.append(f"{field} = ${idx}")
                            update_params.append(patient_data[field])
                            idx += 1
                        if field == "phone":
                            update_fields.append(f"phone_hash = ${idx}")
                            update_params.append(hash_phone(patient_data[field]))
                            idx += 1
                        if field == "date_of_birth":
                            bm, bd = _extract_birthday_parts(patient_data[field])
                            update_fields.append(f"birthday_month = ${idx}")
                            update_params.append(bm)
                            idx += 1
                            update_fields.append(f"birthday_day = ${idx}")
                            update_params.append(bd)
                            idx += 1

                if update_fields:
                    update_fields.append(f"updated_at = NOW()")
                    await db.execute(
                        f"UPDATE members SET {', '.join(update_fields)} WHERE id = $1",
                        member_id, *update_params,
                    )

                await db.execute(
                    "UPDATE emr_patient_map SET last_synced_at = NOW(), updated_at = NOW() WHERE emr_patient_id = $1",
                    emr_patient_id,
                )

                await self._log_sync(
                    schema, "inbound", "Patient", "update",
                    emr_patient_id, member_id, "success",
                )
                return member_id
            else:
                # Create new member
                if not patient_data.get("first_name") or not patient_data.get("last_name"):
                    logger.warning("EMR inbound: missing required name fields")
                    return None

                # HIPAA-2C Phase C: dual-write _enc shadows + phone_hash +
                # birthday derived cols on EMR-originated INSERTs too.
                from app.services.members.member_service import (
                    _enc_or_none, _extract_birthday_parts,
                )
                from app.services.members.phone_hash import hash_phone

                member_id = str(uuid.uuid4())
                # members.user_id is NOT NULL — EMR-originated members get a
                # placeholder UUID like the kiosk / momoyoga importer flows
                # do. A real user account is linked later if the patient ever
                # registers in the portal.
                member_user_id = str(uuid.uuid4())
                bm, bd = _extract_birthday_parts(patient_data.get("date_of_birth"))
                # Post-Phase-C: plain PHI columns no longer exist.
                await db.execute(
                    """
                    INSERT INTO members
                        (id, user_id, first_name, last_name, email,
                         gender, source,
                         phone_enc, date_of_birth_enc, address_line1_enc,
                         city_enc, state_enc, postal_code_enc,
                         birthday_month, birthday_day, phone_hash)
                    VALUES ($1, $2, $3, $4, $5, $6, 'emr_sync',
                            $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    """,
                    member_id,
                    member_user_id,
                    patient_data.get("first_name", ""),
                    patient_data.get("last_name", ""),
                    patient_data.get("email"),
                    patient_data.get("gender"),
                    _enc_or_none(patient_data.get("phone")),
                    _enc_or_none(patient_data.get("date_of_birth")),
                    _enc_or_none(patient_data.get("address_line1")),
                    _enc_or_none(patient_data.get("city")),
                    _enc_or_none(patient_data.get("state")),
                    _enc_or_none(patient_data.get("postal_code")),
                    bm, bd,
                    hash_phone(patient_data.get("phone")),
                )

                # Create mapping. get_status returns protocol=None when EMR
                # is not configured for this org; .get("protocol", "fhir_r4")
                # would return None too (the key is present, just null), so
                # use `or` to fall through to the default.
                protocol = (await self.get_status(org_id)).get("protocol") or "fhir_r4"
                await db.execute(
                    """
                    INSERT INTO emr_patient_map
                        (id, member_id, emr_patient_id, emr_system, sync_direction, last_synced_at)
                    VALUES ($1, $2, $3, $4, 'inbound', NOW())
                    """,
                    str(uuid.uuid4()), member_id, emr_patient_id, protocol,
                )

                await self._log_sync(
                    schema, "inbound", "Patient", "create",
                    emr_patient_id, member_id, "success",
                )

                logger.info(
                    "Member created from EMR patient",
                    member_id=member_id,
                    emr_patient_id=emr_patient_id,
                )
                return member_id

    # ── Sync Log ──────────────────────────────────────────────────────────

    async def get_sync_log(
        self, schema: str, limit: int = 50, direction: Optional[str] = None
    ) -> list[dict]:
        """Get recent sync log entries."""
        async with get_tenant_db(schema_override=schema) as db:
            conditions = []
            params: list = []
            idx = 1

            if direction:
                conditions.append(f"direction = ${idx}")
                params.append(direction)
                idx += 1

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            rows = await db.fetch(
                f"""
                SELECT id, direction, resource_type, operation,
                       emr_resource_id, auraflow_resource_id,
                       status, error_message, created_at
                FROM emr_sync_log
                {where}
                ORDER BY created_at DESC
                LIMIT ${idx}
                """,
                *params, limit,
            )

        return [
            {
                "id": str(r["id"]),
                "direction": r["direction"],
                "resource_type": r["resource_type"],
                "operation": r["operation"],
                "emr_resource_id": r["emr_resource_id"],
                "auraflow_resource_id": str(r["auraflow_resource_id"]) if r["auraflow_resource_id"] else None,
                "status": r["status"],
                "error_message": r["error_message"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

    async def retry_failed_syncs(self, schema: str) -> int:
        """Retry failed encounter syncs. Returns count of retried items."""
        async with get_tenant_db(schema_override=schema) as db:
            failed = await db.fetch(
                """
                SELECT booking_id FROM emr_encounter_log
                WHERE status = 'failed'
                ORDER BY created_at DESC
                LIMIT 50
                """,
            )

        retried = 0
        for row in failed:
            result = await self.sync_attendance_to_emr(schema, str(row["booking_id"]))
            if result:
                retried += 1

        return retried

    # ── Internal Helpers ──────────────────────────────────────────────────

    async def _get_client(self, org_id: str) -> EmrClient:
        """Factory: return the correct EMR client for the org's protocol."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT emr_protocol, emr_base_url,
                       emr_client_id_encrypted, emr_client_secret_encrypted,
                       emr_hl7_host, emr_hl7_port
                FROM af_global.organizations
                WHERE id = $1
                """,
                org_id,
            )

        if not row or not row["emr_protocol"]:
            raise ValueError("EMR not configured for this organization")

        if row["emr_protocol"] == "fhir_r4":
            async with get_global_db() as db:
                client_id = await decrypt_credential(db, row["emr_client_id_encrypted"])
                client_secret = await decrypt_credential(db, row["emr_client_secret_encrypted"])
            return FhirClient(
                base_url=row["emr_base_url"],
                client_id=client_id,
                client_secret=client_secret,
            )
        else:  # hl7v2
            return Hl7Client(
                host=row["emr_hl7_host"],
                port=row["emr_hl7_port"],
            )

    async def _org_id_from_schema(self, schema: str) -> Optional[str]:
        """Resolve org_id from tenant schema name."""
        slug = schema.replace("af_tenant_", "")
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT id FROM af_global.organizations WHERE slug = $1",
                slug,
            )
        return str(row["id"]) if row else None

    async def _log_sync(
        self,
        schema: str,
        direction: str,
        resource_type: str,
        operation: str,
        emr_resource_id: Optional[str],
        auraflow_resource_id: Optional[str],
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Write an entry to the sync audit log."""
        try:
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute(
                    """
                    INSERT INTO emr_sync_log
                        (id, direction, resource_type, operation,
                         emr_resource_id, auraflow_resource_id, status, error_message)
                    VALUES ($1, $2, $3, $4, $5, $6::uuid, $7, $8)
                    """,
                    str(uuid.uuid4()), direction, resource_type, operation,
                    emr_resource_id, auraflow_resource_id, status, error,
                )
        except Exception as e:
            logger.error("Failed to write EMR sync log", error=str(e))
