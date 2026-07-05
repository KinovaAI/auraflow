"""AuraFlow — Member Service

Member profiles, search, notes, and health data management.
"""
import uuid
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db


def _get_fernet() -> Fernet | None:
    """Return Fernet cipher if HEALTH_DATA_ENCRYPTION_KEY is configured."""
    key = settings.HEALTH_DATA_ENCRYPTION_KEY
    if not key:
        return None
    return Fernet(key.encode("utf-8"))


def _encrypt(value: str) -> bytes:
    """Encrypt a string. Returns raw bytes if no key configured."""
    f = _get_fernet()
    if f and value:
        return f.encrypt(value.encode("utf-8"))
    return value.encode("utf-8") if value else b""


def _decrypt(value: bytes) -> str:
    """Decrypt bytes. Falls back to plain decode if not Fernet-encrypted."""
    if not value:
        return ""
    f = _get_fernet()
    if f:
        try:
            return f.decrypt(value).decode("utf-8")
        except InvalidToken:
            # Data was stored before encryption was enabled — return as-is
            return value.decode("utf-8", errors="replace")
    return value.decode("utf-8", errors="replace")


def _extract_birthday_parts(dob) -> tuple[int | None, int | None]:
    """Pull (month, day) ints from a date_of_birth value (date, datetime,
    ISO string, or None). Returns (None, None) if unparseable. The
    full DOB stays encrypted; only month+day are stored in plaintext
    derived columns for HIPAA-safe filtering by birthday."""
    if dob is None or dob == "":
        return (None, None)
    if hasattr(dob, "month") and hasattr(dob, "day"):
        return (int(dob.month), int(dob.day))
    if isinstance(dob, str):
        from datetime import date as _date
        try:
            d = _date.fromisoformat(dob[:10])
            return (d.month, d.day)
        except (ValueError, TypeError):
            return (None, None)
    return (None, None)


def _enc_or_none(v) -> bytes | None:
    """Encrypt PHI value to bytes, or None for null/empty (so NULL stays NULL)."""
    if v is None or v == "":
        return None
    if hasattr(v, "isoformat"):
        v = v.isoformat()
    return _encrypt(str(v))


def _dec_or_none(b) -> str | None:
    """Decrypt; return None for null."""
    if b is None:
        return None
    s = _decrypt(b)
    return s if s != "" else None


def _row_with_decrypted_phi(row: dict) -> dict:
    """Take a member row, prefer *_enc decrypted values when present, fall
    back to plaintext columns. Reversible — if any decrypt fails, plaintext
    is still returned. Drop the *_enc keys from the output (clients see
    the public column names)."""
    if not row:
        return row
    out = dict(row)
    for plain_key in (
        "date_of_birth", "phone", "address_line1", "city", "state", "postal_code",
        "emergency_contact_name", "emergency_contact_phone", "notes",
    ):
        enc_key = plain_key + "_enc"
        enc_val = out.pop(enc_key, None)
        if enc_val is not None:
            try:
                decrypted = _dec_or_none(enc_val)
                if decrypted is not None:
                    # date_of_birth round-trips as ISO string; keep type-compat
                    if plain_key == "date_of_birth":
                        from datetime import date as _date
                        try:
                            out[plain_key] = _date.fromisoformat(decrypted)
                        except (ValueError, TypeError):
                            out[plain_key] = decrypted
                    else:
                        out[plain_key] = decrypted
            except Exception:
                pass  # plaintext stays
    return out


def _row_with_decrypted_note(row: dict) -> dict:
    """Same idea for member_notes.note column."""
    if not row:
        return row
    out = dict(row)
    enc = out.pop("note_enc", None)
    if enc is not None:
        try:
            d = _dec_or_none(enc)
            if d is not None:
                out["note"] = d
        except Exception:
            pass
    return out


class MemberService:

    async def create_member(self, data: dict) -> dict:
        member_id = str(uuid.uuid4())

        # Derive birthday_month/day for HIPAA-safe filtering by birthday
        # Phase C-aware: when plaintext date_of_birth column drops, the
        # derived month+day stays so the daily birthday-emails task
        # keeps working. Month+day alone are not PHI under §164.514
        # Safe Harbor.
        birthday_month, birthday_day = _extract_birthday_parts(
            data.get("date_of_birth")
        )

        from app.services.members.phone_hash import hash_phone
        async with get_tenant_db() as db:
            # Post-Phase-C: write _enc shadows + derived columns only;
            # the plaintext PHI columns no longer exist.
            row = await db.fetchrow(
                """
                INSERT INTO members
                    (id, user_id, first_name, last_name, email,
                     gender, tags, source, referral_source,
                     phone_enc, date_of_birth_enc, address_line1_enc, city_enc,
                     state_enc, postal_code_enc, emergency_contact_name_enc,
                     emergency_contact_phone_enc, notes_enc,
                     birthday_month, birthday_day, phone_hash)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                        $10, $11, $12, $13, $14, $15, $16, $17, $18,
                        $19, $20, $21)
                RETURNING *
                """,
                member_id, data.get("user_id", str(uuid.uuid4())),
                data["first_name"], data["last_name"], data["email"],
                data.get("gender"), data.get("tags"),
                data.get("source", "manual"), data.get("referral_source"),
                _enc_or_none(data.get("phone")),
                _enc_or_none(data.get("date_of_birth")),
                _enc_or_none(data.get("address_line1")),
                _enc_or_none(data.get("city")),
                _enc_or_none(data.get("state")),
                _enc_or_none(data.get("postal_code")),
                _enc_or_none(data.get("emergency_contact_name")),
                _enc_or_none(data.get("emergency_contact_phone")),
                _enc_or_none(data.get("notes")),
                birthday_month, birthday_day,
                hash_phone(data.get("phone")),
            )
            logger.info("Member created", member_id=member_id, name=f"{data['first_name']} {data['last_name']}")

            # Fire-and-forget EMR sync
            try:
                from app.workers.tasks.emr_sync import sync_member_to_emr
                from app.core.tenant_context import get_tenant_context
                ctx = get_tenant_context()
                if ctx:
                    sync_member_to_emr.delay(ctx.schema_name, member_id)
            except Exception as e:
                logger.warning("EMR sync failed for new member", member_id=member_id, error=str(e))

            # Fire-and-forget webhook: member.created
            try:
                import asyncio
                from app.services.webhooks.webhook_delivery_service import WebhookDeliveryService
                asyncio.create_task(WebhookDeliveryService().fire_event("member.created", {
                    "id": member_id,
                    "email": data.get("email"),
                    "first_name": data.get("first_name"),
                    "last_name": data.get("last_name"),
                }))
            except Exception:
                pass

            # Fire-and-forget Mailchimp sync
            try:
                from app.workers.tasks.mailchimp_sync import sync_member_to_mailchimp
                from app.core.tenant_context import get_tenant_context
                ctx = get_tenant_context()
                if ctx:
                    sync_member_to_mailchimp.delay(ctx.schema_name, member_id)
            except Exception:
                pass

            # Route through dual-mode helper so callers (external API,
            # webhooks) see decrypted PHI. Post-Phase-C the plaintext
            # columns are gone, so without this, every create_member
            # response returns null phone/dob/address.
            return _row_with_decrypted_phi(dict(row))

    async def list_members(
        self,
        search: str | None = None,
        active_only: bool = True,
        membership_status: str | None = None,
        has_failed_payments: bool | None = None,
        churn_risk: bool | None = None,
        min_visits: int | None = None,
        max_visits: int | None = None,
        inactive_weeks: int | None = None,
        joined_after: str | None = None,
        joined_before: str | None = None,
        min_revenue: int | None = None,
        has_coupon: bool | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        async with get_tenant_db() as db:
            conditions = []
            params: list = []
            idx = 1

            if active_only:
                conditions.append(f"m.is_active = ${idx}")
                params.append(True)
                idx += 1

            if search:
                # Fuzzy trigram match so "meri" finds "Merilee", "stocdale"
                # finds "Stockdale". Threshold 0.3 is conservative enough
                # to avoid random matches while tolerating typos of 1-2 chars.
                # pg_trgm is already enabled; GIN indexes live on
                # (first_name || ' ' || last_name) and (email).
                # HIPAA Phase C: phone is encrypted and intentionally not
                # searchable. A plaintext-or-blind-index phone column would
                # leak PHI; staff search by name or email instead.
                conditions.append(
                    f"(\n"
                    f"  (m.first_name || ' ' || m.last_name) ILIKE ${idx}\n"
                    f"  OR m.email ILIKE ${idx}\n"
                    f"  OR similarity(m.first_name || ' ' || m.last_name, ${idx + 1}) > 0.3\n"
                    f"  OR similarity(m.email, ${idx + 1}) > 0.3\n"
                    f")"
                )
                safe_like = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                params.append(f"%{safe_like}%")
                params.append(search)
                idx += 2

            if min_visits is not None:
                conditions.append(f"m.total_visits >= ${idx}")
                params.append(min_visits)
                idx += 1
            if max_visits is not None:
                conditions.append(f"m.total_visits <= ${idx}")
                params.append(max_visits)
                idx += 1

            if inactive_weeks is not None:
                conditions.append(
                    f"(m.last_visit_at IS NULL OR m.last_visit_at < NOW() - INTERVAL '1 week' * ${idx})"
                )
                params.append(inactive_weeks)
                idx += 1

            if churn_risk is True:
                conditions.append("m.churn_risk_flagged_at IS NOT NULL")

            if joined_after:
                conditions.append(f"m.joined_at >= ${idx}::timestamptz")
                params.append(joined_after)
                idx += 1
            if joined_before:
                conditions.append(f"m.joined_at <= ${idx}::timestamptz")
                params.append(joined_before)
                idx += 1

            if min_revenue is not None:
                conditions.append(f"m.lifetime_revenue_cents >= ${idx}")
                params.append(min_revenue)
                idx += 1

            # Membership status: EXISTS subquery to avoid row duplication
            if membership_status == "none":
                conditions.append(
                    "NOT EXISTS (SELECT 1 FROM member_memberships mm WHERE mm.member_id = m.id)"
                )
            elif membership_status in ("active", "frozen", "cancelled", "expired"):
                conditions.append(
                    f"EXISTS (SELECT 1 FROM member_memberships mm "
                    f"WHERE mm.member_id = m.id AND mm.status = ${idx})"
                )
                params.append(membership_status)
                idx += 1

            # Coupon filter
            if has_coupon is True:
                conditions.append("m.stripe_coupon_id IS NOT NULL")
            elif has_coupon is False:
                conditions.append("m.stripe_coupon_id IS NULL")

            # Failed payments: EXISTS subquery
            if has_failed_payments is True:
                conditions.append(
                    "EXISTS (SELECT 1 FROM failed_payment_attempts fp "
                    "WHERE fp.member_id = m.id AND fp.resolved = FALSE)"
                )

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            # Sort with whitelist to prevent injection
            allowed_sort = {"total_visits", "lifetime_revenue_cents", "last_visit_at", "joined_at"}
            if sort_by in allowed_sort:
                direction = "ASC" if sort_dir == "asc" else "DESC"
                nulls = " NULLS LAST" if sort_by in ("last_visit_at",) else ""
                order = f"ORDER BY m.{sort_by} {direction}{nulls}, m.last_name, m.first_name"
            else:
                order = "ORDER BY m.last_name, m.first_name"

            params.extend([limit, offset])
            query = f"""
                SELECT m.* FROM members m {where}
                {order}
                LIMIT ${idx} OFFSET ${idx + 1}
            """
            rows = await db.fetch(query, *params)
            # HIPAA-2C dual-read: decrypt PHI on each row so list endpoints
            # surface plaintext values once the unencrypted columns drop.
            return [_row_with_decrypted_phi(dict(r)) for r in rows]

    async def get_member(self, member_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow("SELECT * FROM members WHERE id = $1", member_id)
            # HIPAA-2C dual-read: prefer *_enc decrypted values, fall back to plaintext.
            return _row_with_decrypted_phi(dict(row)) if row else None

    _MEMBER_UPDATE_COLS = {
        "first_name", "last_name", "email", "phone", "date_of_birth",
        "gender", "address_line1", "city", "state", "postal_code",
        "emergency_contact_name", "emergency_contact_phone", "notes",
        "source", "referral_source",
    }

    async def update_member(self, member_id: str, data: dict) -> dict | None:
        async with get_tenant_db() as db:
            sets, params, idx = [], [], 1
            # Post-Phase-C: PHI fields are stored only in their _enc shadow
            # columns + derived (phone_hash, birthday_month/day). Non-PHI
            # fields (first_name, last_name, email, gender, source,
            # referral_source) still write to the plain column.
            _PHI_ENC_ONLY = {
                "date_of_birth", "phone", "address_line1", "city", "state",
                "postal_code", "emergency_contact_name",
                "emergency_contact_phone", "notes",
            }
            for k, v in data.items():
                if k not in self._MEMBER_UPDATE_COLS:
                    continue
                if k in _PHI_ENC_ONLY:
                    # Write _enc shadow only (plaintext column is gone).
                    sets.append(f"{k}_enc = ${idx}")
                    params.append(_enc_or_none(v))
                    idx += 1
                else:
                    sets.append(f"{k} = ${idx}")
                    params.append(v)
                    idx += 1
                # Maintain birthday_month/day derived cols when DOB
                # changes — keeps the daily birthday-emails task working
                # after Phase C drops plaintext date_of_birth.
                if k == "date_of_birth":
                    bm, bd = _extract_birthday_parts(v)
                    sets.append(f"birthday_month = ${idx}")
                    params.append(bm)
                    idx += 1
                    sets.append(f"birthday_day = ${idx}")
                    params.append(bd)
                    idx += 1
                # Maintain phone_hash deterministic index when phone
                # changes — used by inbound-SMS lookups (TCPA STOP/START)
                # so we can resolve a member from a Twilio webhook.
                if k == "phone":
                    from app.services.members.phone_hash import hash_phone
                    sets.append(f"phone_hash = ${idx}")
                    params.append(hash_phone(v))
                    idx += 1
            if not sets:
                return await self.get_member(member_id)

            sets.append(f"updated_at = ${idx}")
            params.append(datetime.now(timezone.utc))
            idx += 1

            params.append(member_id)
            query = f"UPDATE members SET {', '.join(sets)} WHERE id = ${idx} RETURNING *"
            row = await db.fetchrow(query, *params)
            row = _row_with_decrypted_phi(dict(row)) if row else None

            # Fire-and-forget Mailchimp sync on update
            if row:
                try:
                    from app.workers.tasks.mailchimp_sync import sync_member_to_mailchimp
                    from app.core.tenant_context import get_tenant_context
                    ctx = get_tenant_context()
                    if ctx:
                        sync_member_to_mailchimp.delay(ctx.schema_name, member_id)
                except Exception:
                    pass

            return dict(row) if row else None

    async def deactivate_member(self, member_id: str) -> bool:
        async with get_tenant_db() as db:
            result = await db.execute(
                "UPDATE members SET is_active = FALSE, updated_at = NOW() WHERE id = $1",
                member_id,
            )
            return "UPDATE 1" in result

    async def search_members(self, query: str, limit: int = 20) -> list[dict]:
        """Fast search by name, email, phone, or member number."""
        return await self.list_members(search=query, active_only=False, limit=limit)

    # ── Notes ────────────────────────────────────────────────────────────────

    async def add_note(self, member_id: str, author_id: str, note: str, is_pinned: bool = False) -> dict:
        note_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            # Post-Phase-C: note column is dropped; note_enc is canonical.
            row = await db.fetchrow(
                """
                INSERT INTO member_notes (id, member_id, author_id, is_pinned, note_enc)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
                """,
                note_id, member_id, author_id, is_pinned, _enc_or_none(note),
            )
            return _row_with_decrypted_note(dict(row))

    async def list_notes(self, member_id: str) -> list[dict]:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                "SELECT * FROM member_notes WHERE member_id = $1 ORDER BY is_pinned DESC, created_at DESC",
                member_id,
            )
            return [_row_with_decrypted_note(dict(r)) for r in rows]

    async def delete_note(self, note_id: str) -> bool:
        async with get_tenant_db() as db:
            result = await db.execute("DELETE FROM member_notes WHERE id = $1", note_id)
            return "DELETE 1" in result

    # ── Health Data ──────────────────────────────────────────────────────────

    async def set_health_data(self, member_id: str, data: dict) -> dict:
        """Store health data with Fernet encryption at the application layer."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO member_health_data (id, member_id, health_data_encrypted,
                    injuries_encrypted, conditions_encrypted, medications_encrypted)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (member_id) DO UPDATE SET
                    health_data_encrypted = EXCLUDED.health_data_encrypted,
                    injuries_encrypted = EXCLUDED.injuries_encrypted,
                    conditions_encrypted = EXCLUDED.conditions_encrypted,
                    medications_encrypted = EXCLUDED.medications_encrypted,
                    updated_at = NOW()
                RETURNING *
                """,
                str(uuid.uuid4()), member_id,
                _encrypt(data.get("health_data", "")),
                _encrypt(data.get("injuries", "")),
                _encrypt(data.get("conditions", "")),
                _encrypt(data.get("medications", "")),
            )
            return dict(row)

    async def get_health_data(self, member_id: str) -> dict | None:
        """Retrieve health data, decrypting Fernet-encrypted fields."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM member_health_data WHERE member_id = $1", member_id
            )
            if not row:
                return None
            result = dict(row)
            for field in ("health_data_encrypted", "injuries_encrypted",
                          "conditions_encrypted", "medications_encrypted"):
                if field in result and isinstance(result[field], (bytes, memoryview)):
                    result[field] = _decrypt(bytes(result[field]))
            return result

    # ── Booking History ──────────────────────────────────────────────────────

    async def get_booking_history(self, member_id: str, limit: int = 100) -> list[dict]:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT b.id, b.member_id, b.class_session_id, b.status,
                       b.source, b.booked_at, b.cancelled_at, b.checked_in_at,
                       b.cancellation_reason, b.late_cancel,
                       cs.title AS session_title, cs.starts_at, cs.ends_at,
                       cs.status AS session_status,
                       cs.is_virtual, cs.zoom_join_url, cs.zoom_password,
                       ct.name AS class_type_name, ct.category AS class_category
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                WHERE b.member_id = $1
                ORDER BY cs.starts_at DESC
                LIMIT $2
                """,
                member_id, limit,
            )
            return [dict(r) for r in rows]
