"""AuraFlow — MomoYoga CSV Importer

Parses MomoYoga export CSVs (members, classes, memberships) and imports them
into the tenant's schema. Supports dry-run mode for preview before commit.
"""
import csv
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import zoneinfo

from app.core.logging import logger
from app.core.security import hash_password
from app.db.session import get_tenant_db, get_global_db
from app.services.scheduling.scheduling_service import SchedulingService


class MomoYogaImporter:

    # ── CSV Parsing ───────────────────────────────────────────────────────────

    def _detect_delimiter(self, csv_content: str) -> str:
        """Detect CSV delimiter (tab vs comma)."""
        first_line = csv_content.split("\n")[0]
        if "\t" in first_line:
            return "\t"
        return ","

    def parse_members_csv(self, csv_content: str) -> list[dict]:
        """Parse a MomoYoga members CSV export.

        Handles both comma and tab-separated files.
        Supports: member_name (single field) or first_name/last_name (separate).
        """
        delimiter = self._detect_delimiter(csv_content)
        reader = csv.DictReader(io.StringIO(csv_content), delimiter=delimiter)
        members = []
        for row in reader:
            # Normalize column names (MomoYoga uses various formats)
            normalized = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items() if v}

            # Handle single "member_name" field or separate first/last
            first_name = normalized.get("first_name") or normalized.get("firstname") or ""
            last_name = normalized.get("last_name") or normalized.get("lastname") or ""
            if not first_name and not last_name:
                full_name = normalized.get("member_name") or normalized.get("name") or ""
                parts = full_name.strip().split(None, 1)
                first_name = parts[0] if parts else ""
                last_name = parts[1] if len(parts) > 1 else ""

            # Parse emergency contact (may be "Name: xxx Phone: xxx" or just a string)
            emergency_raw = normalized.get("emergency_contact") or ""
            ec_name = emergency_raw
            ec_phone = None

            # Class attendance may be a number or text
            class_attendance_raw = normalized.get("class_attendance") or ""
            lessons_attended_raw = normalized.get("lessons_attended") or ""
            # Use whichever is numeric for total_visits
            total_visits = 0
            if lessons_attended_raw.isdigit():
                total_visits = int(lessons_attended_raw)
            elif class_attendance_raw.isdigit():
                total_visits = int(class_attendance_raw)

            member = {
                "first_name": first_name,
                "last_name": last_name,
                "email": normalized.get("email") or normalized.get("e-mail") or "",
                "phone": normalized.get("phone") or normalized.get("telephone") or None,
                "date_of_birth": normalized.get("date_of_birth") or normalized.get("dob") or None,
                "address": normalized.get("address") or None,
                "city": normalized.get("city") or None,
                "state": normalized.get("state") or normalized.get("province") or None,
                "postal_code": normalized.get("postal_code") or normalized.get("zip") or normalized.get("zip_code") or None,
                "emergency_contact_name": ec_name or None,
                "emergency_contact_phone": ec_phone,
                "notes": normalized.get("notes") or None,
                "member_since": normalized.get("member_since") or None,
                "total_visits": total_visits,
                "current_membership": normalized.get("current_membership") or None,
                "membership_status": normalized.get("membership_status") or None,
                "class_attendance": class_attendance_raw if not class_attendance_raw.isdigit() and class_attendance_raw else None,
                "source": "momoyoga_import",
            }
            # Skip rows without required fields
            if member["first_name"] and member["email"]:
                members.append(member)
        return members

    def parse_classes_csv(self, csv_content: str) -> list[dict]:
        """Parse a MomoYoga classes/schedule CSV export."""
        reader = csv.DictReader(io.StringIO(csv_content))
        classes = []
        for row in reader:
            normalized = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items() if v}
            cls = {
                "name": normalized.get("class") or normalized.get("class_name") or normalized.get("name") or "",
                "instructor": normalized.get("teacher") or normalized.get("instructor") or "",
                "date": normalized.get("date") or "",
                "time": normalized.get("time") or normalized.get("start_time") or "",
                "duration": normalized.get("duration") or "60",
                "capacity": normalized.get("capacity") or normalized.get("max_participants") or "20",
                "attendees": normalized.get("attendees") or normalized.get("participants") or "0",
            }
            if cls["name"]:
                classes.append(cls)
        return classes

    def parse_memberships_csv(self, csv_content: str) -> list[dict]:
        """Parse a MomoYoga memberships/subscriptions CSV export."""
        reader = csv.DictReader(io.StringIO(csv_content))
        memberships = []
        for row in reader:
            normalized = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items() if v}
            ms = {
                "member_email": normalized.get("email") or normalized.get("e-mail") or "",
                "membership_name": normalized.get("subscription") or normalized.get("membership") or normalized.get("name") or "",
                "status": normalized.get("status") or "active",
                "start_date": normalized.get("start_date") or normalized.get("start") or "",
                "end_date": normalized.get("end_date") or normalized.get("end") or "",
                "price": normalized.get("price") or normalized.get("amount") or "0",
            }
            if ms["member_email"] and ms["membership_name"]:
                memberships.append(ms)
        return memberships

    def parse_instructors_csv(self, csv_content: str) -> list[dict]:
        """Parse a MomoYoga instructor/teacher CSV export."""
        reader = csv.DictReader(io.StringIO(csv_content))
        instructors = []
        for row in reader:
            normalized = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items() if v}
            instr = {
                "display_name": normalized.get("teacher") or normalized.get("instructor")
                               or normalized.get("name") or "",
                "email": normalized.get("email") or normalized.get("e-mail") or None,
                "phone": normalized.get("phone") or normalized.get("telephone") or None,
                "bio": normalized.get("bio") or normalized.get("description") or None,
            }
            if instr["display_name"]:
                instructors.append(instr)
        return instructors

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _infer_membership_type(self, name: str) -> str:
        """Infer membership type from name. Defaults to 'unlimited'."""
        lower = name.lower()
        if any(kw in lower for kw in ("pack", "class pack", "punch", "10 class", "20 class", "5 class")):
            return "class_pack"
        if any(kw in lower for kw in ("drop", "single", "one class")):
            return "single_class"
        if any(kw in lower for kw in ("intro", "trial", "new student")):
            return "intro_offer"
        if any(kw in lower for kw in ("day pass", "daily")):
            return "day_pass"
        return "unlimited"

    def _parse_price(self, price_str: str) -> int:
        """Parse a price string to cents. '150' -> 15000, '29.99' -> 2999."""
        try:
            cleaned = price_str.replace("$", "").replace(",", "").strip()
            return int(float(cleaned) * 100)
        except (ValueError, AttributeError):
            return 0

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """Parse various date formats from MomoYoga exports."""
        if not date_str or not date_str.strip():
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None

    def _map_status(self, momo_status: str) -> str:
        """Map MomoYoga status to AuraFlow membership status."""
        lower = momo_status.lower().strip()
        if lower in ("active", "actief"):
            return "active"
        if lower in ("cancelled", "canceled", "opgezegd"):
            return "cancelled"
        if lower in ("frozen", "paused", "gepauzeerd"):
            return "frozen"
        if lower in ("expired", "verlopen"):
            return "expired"
        return "active"

    # ── Dry Run ───────────────────────────────────────────────────────────────

    async def dry_run(
        self,
        members_csv: Optional[str] = None,
        classes_csv: Optional[str] = None,
        memberships_csv: Optional[str] = None,
        instructors_csv: Optional[str] = None,
        schedule_csv: Optional[str] = None,
    ) -> dict:
        """Preview what would be imported without making changes."""
        DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        result = {
            "members": {"total": 0, "new": 0, "existing": 0, "errors": [], "with_memberships": 0},
            "classes": {"total": 0, "class_types": []},
            "memberships": {"total": 0, "types": []},
            "instructors": {"total": 0, "new": 0, "existing": 0},
            "schedule": {"total": 0, "series": []},
        }

        if members_csv:
            parsed = self.parse_members_csv(members_csv)
            result["members"]["total"] = len(parsed)
            membership_names_found = set()

            async with get_tenant_db() as db:
                for m in parsed:
                    existing = await db.fetchrow(
                        "SELECT id FROM members WHERE email = $1",
                        m["email"],
                    )
                    if existing:
                        result["members"]["existing"] += 1
                    else:
                        result["members"]["new"] += 1
                    if m.get("current_membership"):
                        result["members"]["with_memberships"] += 1
                        membership_names_found.add(m["current_membership"])

            if membership_names_found:
                result["members"]["membership_types_found"] = sorted(membership_names_found)

        if classes_csv:
            parsed = self.parse_classes_csv(classes_csv)
            result["classes"]["total"] = len(parsed)
            types = list(set(c["name"] for c in parsed if c["name"]))
            result["classes"]["class_types"] = types

        if memberships_csv:
            parsed = self.parse_memberships_csv(memberships_csv)
            result["memberships"]["total"] = len(parsed)
            types = list(set(m["membership_name"] for m in parsed if m["membership_name"]))
            result["memberships"]["types"] = types

        if instructors_csv:
            parsed = self.parse_instructors_csv(instructors_csv)
            result["instructors"]["total"] = len(parsed)

            async with get_tenant_db() as db:
                for instr in parsed:
                    existing = await db.fetchrow(
                        "SELECT id FROM instructors WHERE display_name = $1",
                        instr["display_name"],
                    )
                    if existing:
                        result["instructors"]["existing"] += 1
                    else:
                        result["instructors"]["new"] += 1

        if schedule_csv:
            parsed = self.parse_classes_csv(schedule_csv)
            result["schedule"]["total"] = len(parsed)
            for cls in parsed:
                session_date = self._parse_date(cls.get("date"))
                day = DAY_NAMES[session_date.weekday()] if session_date else "Unknown"
                result["schedule"]["series"].append({
                    "name": cls["name"],
                    "instructor": cls.get("instructor", ""),
                    "day": day,
                    "time": cls.get("time", ""),
                    "duration": int(cls.get("duration", 60)),
                })

        return result

    # ── Import ────────────────────────────────────────────────────────────────

    def _clean_membership_name(self, raw_name: str) -> str:
        """Strip status suffixes from MomoYoga membership names.

        E.g. 'One Month Unlimited - In Studio Cancellation scheduled' -> 'One Month Unlimited - In Studio'
        """
        name = raw_name.strip()
        for suffix in ("Cancellation scheduled", "Paused", "Cancelled", "Expired",
                        "Active", "Frozen", "First visit"):
            if name.endswith(suffix):
                name = name[: -len(suffix)].strip()
        return name

    def _match_membership_type(self, csv_name: str, type_map: dict[str, str]) -> str | None:
        """Match a CSV membership name to a membership_type id.

        Cleans status suffixes, then tries exact, case-insensitive, partial matching.
        """
        if not csv_name:
            return None
        cleaned = self._clean_membership_name(csv_name)
        # Try both raw and cleaned
        for name_to_try in [csv_name, cleaned]:
            if not name_to_try:
                continue
            # Exact match
            if name_to_try in type_map:
                return type_map[name_to_try]
            # Case-insensitive
            lower_name = name_to_try.lower().strip()
            for name, tid in type_map.items():
                if name.lower().strip() == lower_name:
                    return tid
            # Partial: CSV name is substring of DB name or vice versa
            for name, tid in type_map.items():
                db_lower = name.lower().strip()
                if lower_name in db_lower or db_lower in lower_name:
                    return tid
        return None

    def _parse_class_attendance(self, raw: str) -> list[dict]:
        """Parse MomoYoga class_attendance column.

        Format: 'date, day | class_name | membership | Yes/No ;; ...'
        Returns list of {date, class_name, membership, attended}.
        """
        if not raw or not raw.strip():
            return []
        entries = raw.split(";;")
        result = []
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            parts = [p.strip() for p in entry.split("|")]
            if len(parts) < 4:
                continue
            # Parse date from "03/02/2026, Mon"
            date_part = parts[0].split(",")[0].strip()
            attendance_date = self._parse_date(date_part)
            class_name = parts[1].strip()
            attended = parts[3].strip().lower() == "yes"
            result.append({
                "date": attendance_date,
                "class_name": class_name,
                "attended": attended,
            })
        return result

    async def import_members(
        self, csv_content: str, studio_id: str, default_password: str = "example-studio",
    ) -> dict:
        """Import members from CSV. Creates user accounts, org links, and membership assignments."""
        parsed = self.parse_members_csv(csv_content)
        imported = 0
        skipped = 0
        memberships_assigned = 0
        bookings_created = 0
        user_accounts_created = 0
        errors = []

        # Hash default password once
        pw_hash = hash_password(default_password)

        # Look up org ID
        async with get_global_db() as gdb:
            org_row = await gdb.fetchrow(
                "SELECT id FROM af_global.organizations LIMIT 1"
            )
            org_id = str(org_row["id"]) if org_row else None

        async with get_tenant_db() as db:
            # Build membership type lookup: name -> id
            mt_rows = await db.fetch(
                "SELECT id, name FROM membership_types WHERE studio_id = $1 AND is_active = TRUE",
                studio_id,
            )
            type_map = {r["name"]: str(r["id"]) for r in mt_rows}

            # Build class type lookup: name -> id (case-insensitive)
            ct_rows = await db.fetch(
                "SELECT id, name FROM class_types WHERE studio_id = $1", studio_id,
            )
            ct_map = {r["name"].lower(): str(r["id"]) for r in ct_rows}

            # Cache for historical sessions: (date_iso, class_type_id) -> session_id
            session_cache: dict[tuple, str] = {}

            for m in parsed:
                try:
                    existing = await db.fetchrow(
                        "SELECT id, user_id FROM members WHERE email = $1",
                        m["email"],
                    )
                    if existing:
                        skipped += 1
                        member_id = str(existing["id"])

                        # Ensure existing imported member has a real user account
                        async with get_global_db() as gdb:
                            user_exists = None
                            if existing["user_id"] is not None:
                                user_exists = await gdb.fetchrow(
                                    "SELECT id FROM af_global.users WHERE id = $1",
                                    str(existing["user_id"]),
                                )
                            if not user_exists:
                                # Create user account for existing member
                                user_id = str(existing["user_id"]) if existing["user_id"] is not None else str(uuid.uuid4())
                                await gdb.execute(
                                    """
                                    INSERT INTO af_global.users
                                        (id, email, password_hash, first_name, last_name,
                                         is_active, force_password_reset)
                                    VALUES ($1, $2, $3, $4, $5, TRUE, TRUE)
                                    ON CONFLICT (email) DO NOTHING
                                    """,
                                    user_id, m["email"].lower(),
                                    pw_hash, m["first_name"], m["last_name"],
                                )
                                # Link to org
                                if org_id:
                                    await gdb.execute(
                                        """
                                        INSERT INTO af_global.organization_users
                                            (id, organization_id, user_id, role, is_active, joined_at)
                                        VALUES ($1, $2, $3, 'member', TRUE, NOW())
                                        ON CONFLICT DO NOTHING
                                        """,
                                        str(uuid.uuid4()), org_id, user_id,
                                    )
                                user_accounts_created += 1
                    else:
                        member_id = str(uuid.uuid4())
                        user_id = str(uuid.uuid4())

                        # Create real user account in af_global.users
                        async with get_global_db() as gdb:
                            # Check if email already has a user account
                            existing_user = await gdb.fetchrow(
                                "SELECT id FROM af_global.users WHERE email = $1",
                                m["email"].lower(),
                            )
                            if existing_user:
                                user_id = str(existing_user["id"])
                            else:
                                await gdb.execute(
                                    """
                                    INSERT INTO af_global.users
                                        (id, email, password_hash, first_name, last_name,
                                         is_active, force_password_reset)
                                    VALUES ($1, $2, $3, $4, $5, TRUE, TRUE)
                                    """,
                                    user_id, m["email"].lower(),
                                    pw_hash, m["first_name"], m["last_name"],
                                )
                                user_accounts_created += 1

                            # Link to org
                            if org_id:
                                await gdb.execute(
                                    """
                                    INSERT INTO af_global.organization_users
                                        (id, organization_id, user_id, role, is_active, joined_at)
                                    VALUES ($1, $2, $3, 'member', TRUE, NOW())
                                    ON CONFLICT DO NOTHING
                                    """,
                                    str(uuid.uuid4()), org_id, user_id,
                                )

                        dob = self._parse_date(m.get("date_of_birth")) if m.get("date_of_birth") else None
                        joined_at = self._parse_date(m.get("member_since")) if m.get("member_since") else None
                        total_visits = m.get("total_visits", 0)

                        # HIPAA-2C dual-write: encrypted shadows + birthday
                        # derived columns + phone_hash so this importer
                        # produces rows that survive the Phase C plaintext
                        # drop. Previously only the plaintext columns were
                        # populated — every imported member would have
                        # been data-loss on drop.
                        from app.services.members.member_service import (
                            _enc_or_none, _extract_birthday_parts,
                        )
                        from app.services.members.phone_hash import hash_phone
                        bday_month, bday_day = _extract_birthday_parts(dob)
                        # Post-Phase-C: plaintext PHI columns are gone.
                        # Write _enc shadows + derived cols only.
                        await db.execute(
                            """
                            INSERT INTO members
                                (id, user_id, first_name, last_name, email,
                                 joined_at, source, is_active, total_visits,
                                 lifetime_revenue_cents,
                                 phone_enc, date_of_birth_enc, address_line1_enc,
                                 city_enc, state_enc, postal_code_enc,
                                 emergency_contact_name_enc, emergency_contact_phone_enc,
                                 notes_enc, birthday_month, birthday_day, phone_hash)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE, $8, 0,
                                    $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
                            ON CONFLICT (email) DO NOTHING
                            """,
                            member_id, user_id, m["first_name"], m["last_name"],
                            m["email"], joined_at, "momoyoga_import", total_visits,
                            _enc_or_none(m.get("phone")),
                            _enc_or_none(dob),
                            _enc_or_none(m.get("address")),
                            _enc_or_none(m.get("city")),
                            _enc_or_none(m.get("state")),
                            _enc_or_none(m.get("postal_code")),
                            _enc_or_none(m.get("emergency_contact_name")),
                            _enc_or_none(m.get("emergency_contact_phone")),
                            _enc_or_none(m.get("notes")),
                            bday_month, bday_day,
                            hash_phone(m.get("phone")),
                        )
                        imported += 1

                    # Assign membership if CSV has current_membership
                    csv_membership = m.get("current_membership")
                    if csv_membership:
                        mt_id = self._match_membership_type(csv_membership, type_map)
                        if not mt_id:
                            # Create new membership type using cleaned name
                            clean_name = self._clean_membership_name(csv_membership)
                            if not clean_name:
                                clean_name = csv_membership
                            new_mt_id = str(uuid.uuid4())
                            inferred = self._infer_membership_type(clean_name)
                            await db.execute(
                                """
                                INSERT INTO membership_types
                                    (id, studio_id, name, type, price_cents, billing_period,
                                     is_active, is_public, sort_order)
                                VALUES ($1, $2, $3, $4, 0, 'monthly', TRUE, TRUE, 99)
                                """,
                                new_mt_id, studio_id, clean_name, inferred,
                            )
                            type_map[clean_name] = new_mt_id
                            mt_id = new_mt_id
                            logger.info("Created membership type from CSV", name=clean_name)

                        # Infer status from CSV membership name suffix or membership_status col
                        csv_status_raw = m.get("membership_status") or ""
                        if not csv_status_raw:
                            # Try to extract status from the membership name suffix
                            lower_ms = csv_membership.lower()
                            if "cancellation scheduled" in lower_ms or "cancelled" in lower_ms:
                                csv_status_raw = "cancelled"
                            elif "paused" in lower_ms or "frozen" in lower_ms:
                                csv_status_raw = "frozen"
                        csv_status = self._map_status(csv_status_raw or "active")

                        # Check if this member already has this membership type assigned
                        existing_mm = await db.fetchrow(
                            "SELECT id FROM member_memberships WHERE member_id = $1 AND membership_type_id = $2",
                            member_id, mt_id,
                        )
                        if not existing_mm:
                            mm_id = str(uuid.uuid4())
                            starts_at = self._parse_date(m.get("member_since")) or datetime.now(timezone.utc)
                            await db.execute(
                                """
                                INSERT INTO member_memberships
                                    (id, member_id, membership_type_id, status, starts_at)
                                VALUES ($1, $2, $3, $4, $5)
                                """,
                                mm_id, member_id, mt_id, csv_status, starts_at,
                            )
                            memberships_assigned += 1

                    # Parse and import class attendance history
                    raw_attendance = m.get("class_attendance")
                    if raw_attendance:
                        attendance_entries = self._parse_class_attendance(raw_attendance)
                        tz = zoneinfo.ZoneInfo("America/Los_Angeles")
                        for att in attendance_entries:
                            if not att["date"]:
                                continue
                            ct_id = ct_map.get(att["class_name"].lower())
                            if not ct_id:
                                continue  # class type not in system

                            # Find or create a historical session for this date+class
                            d = att["date"]
                            cache_key = (d.strftime("%Y-%m-%d"), ct_id)
                            if cache_key not in session_cache:
                                # Check if session already exists
                                existing_sess = await db.fetchrow(
                                    """
                                    SELECT id FROM class_sessions
                                    WHERE class_type_id = $1
                                      AND starts_at::date = $2
                                      AND status = 'completed'
                                    LIMIT 1
                                    """,
                                    ct_id, d.date() if hasattr(d, 'date') else d,
                                )
                                if existing_sess:
                                    session_cache[cache_key] = str(existing_sess["id"])
                                else:
                                    # Create historical session
                                    sess_id = str(uuid.uuid4())
                                    local_start = datetime(d.year, d.month, d.day, 9, 0, tzinfo=tz)
                                    local_end = local_start + timedelta(hours=1)
                                    await db.execute(
                                        """
                                        INSERT INTO class_sessions
                                            (id, studio_id, class_type_id, title,
                                             starts_at, ends_at, timezone, capacity, status)
                                        VALUES ($1, $2, $3, $4, $5, $6, 'America/Los_Angeles', 20, 'completed')
                                        """,
                                        sess_id, studio_id, ct_id, att["class_name"],
                                        local_start, local_end,
                                    )
                                    session_cache[cache_key] = sess_id

                            session_id = session_cache[cache_key]
                            # Create booking if not already exists
                            existing_bk = await db.fetchrow(
                                "SELECT id FROM bookings WHERE member_id = $1 AND class_session_id = $2",
                                member_id, session_id,
                            )
                            if not existing_bk:
                                bk_id = str(uuid.uuid4())
                                status = "attended" if att["attended"] else "no_show"
                                d_tz = datetime(d.year, d.month, d.day, 9, 0, tzinfo=tz)
                                await db.execute(
                                    """
                                    INSERT INTO bookings
                                        (id, member_id, class_session_id, status,
                                         booked_at, checked_in_at, source)
                                    VALUES ($1, $2, $3, $4, $5, $6, 'momoyoga_import')
                                    """,
                                    bk_id, member_id, session_id, status,
                                    d_tz, d_tz if att["attended"] else None,
                                )
                                bookings_created += 1

                except Exception as e:
                    errors.append({"email": m.get("email"), "error": str(e)})
                    logger.error("Member import error", email=m.get("email"), error=str(e))

        logger.info(
            "MomoYoga member import complete",
            imported=imported,
            skipped=skipped,
            user_accounts_created=user_accounts_created,
            memberships_assigned=memberships_assigned,
            bookings_created=bookings_created,
            errors=len(errors),
            error_samples=errors[:5],
        )
        return {
            "imported": imported,
            "skipped": skipped,
            "memberships_assigned": memberships_assigned,
            "bookings_created": bookings_created,
            "user_accounts_created": user_accounts_created,
            "errors": errors,
            "total": len(parsed),
        }

    async def import_class_types(self, csv_content: str, studio_id: str) -> dict:
        """Extract unique class types from a classes CSV and create them."""
        parsed = self.parse_classes_csv(csv_content)
        unique_names = list(set(c["name"] for c in parsed if c["name"]))
        created = 0
        skipped = 0

        async with get_tenant_db() as db:
            existing_rows = await db.fetch(
                "SELECT name FROM class_types WHERE studio_id = $1",
                studio_id,
            )
            existing_names = {r["name"] for r in existing_rows}

            for name in unique_names:
                if name in existing_names:
                    skipped += 1
                    continue

                # Try to infer duration from the CSV data
                durations = [int(c.get("duration", 60)) for c in parsed if c["name"] == name]
                avg_dur = sum(durations) // len(durations) if durations else 60
                capacities = [int(c.get("capacity", 20)) for c in parsed if c["name"] == name]
                avg_cap = sum(capacities) // len(capacities) if capacities else 20

                ct_id = str(uuid.uuid4())
                await db.execute(
                    """
                    INSERT INTO class_types
                        (id, studio_id, name, duration_minutes, capacity, is_active)
                    VALUES ($1, $2, $3, $4, $5, TRUE)
                    """,
                    ct_id, studio_id, name, avg_dur, avg_cap,
                )
                created += 1

        return {
            "created": created,
            "skipped": skipped,
            "total": len(unique_names),
        }

    async def import_instructors(self, csv_content: str) -> dict:
        """Import instructors from CSV. Skips existing by display_name."""
        parsed = self.parse_instructors_csv(csv_content)
        created = 0
        skipped = 0
        errors = []

        async with get_tenant_db() as db:
            for instr in parsed:
                try:
                    existing = await db.fetchrow(
                        "SELECT id FROM instructors WHERE display_name = $1",
                        instr["display_name"],
                    )
                    if existing:
                        skipped += 1
                        continue

                    instructor_id = str(uuid.uuid4())
                    placeholder_user_id = str(uuid.uuid4())
                    from app.services.members.phone_hash import hash_phone
                    await db.execute(
                        """
                        INSERT INTO instructors
                            (id, user_id, display_name, email, phone, phone_hash, bio, is_active)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE)
                        """,
                        instructor_id, placeholder_user_id, instr["display_name"],
                        instr.get("email"), instr.get("phone"), hash_phone(instr.get("phone")),
                        instr.get("bio"),
                    )
                    created += 1
                except Exception as e:
                    errors.append({"name": instr["display_name"], "error": str(e)})

        logger.info("MomoYoga instructor import complete", created=created, skipped=skipped)
        return {"created": created, "skipped": skipped, "errors": errors, "total": len(parsed)}

    async def import_memberships(self, csv_content: str, studio_id: str) -> dict:
        """Import memberships from CSV. Creates membership_types and member_memberships."""
        parsed = self.parse_memberships_csv(csv_content)
        types_created = 0
        memberships_created = 0
        skipped = 0
        errors = []

        async with get_tenant_db() as db:
            # Phase 1: Ensure all membership types exist
            type_name_to_id: dict[str, str] = {}
            unique_types = set(m["membership_name"] for m in parsed)

            for type_name in unique_types:
                existing = await db.fetchrow(
                    "SELECT id FROM membership_types WHERE studio_id = $1 AND name = $2",
                    studio_id, type_name,
                )
                if existing:
                    type_name_to_id[type_name] = str(existing["id"])
                else:
                    type_id = str(uuid.uuid4())
                    inferred_type = self._infer_membership_type(type_name)
                    prices = [self._parse_price(m["price"]) for m in parsed
                             if m["membership_name"] == type_name]
                    avg_price = sum(prices) // len(prices) if prices else 0

                    await db.execute(
                        """
                        INSERT INTO membership_types
                            (id, studio_id, name, type, price_cents, billing_period,
                             is_active, is_public, sort_order)
                        VALUES ($1, $2, $3, $4, $5, 'monthly', TRUE, TRUE, 0)
                        """,
                        type_id, studio_id, type_name, inferred_type, avg_price,
                    )
                    type_name_to_id[type_name] = type_id
                    types_created += 1

            # Phase 2: Create member_memberships
            for m in parsed:
                try:
                    member = await db.fetchrow(
                        "SELECT id FROM members WHERE email = $1",
                        m["member_email"],
                    )
                    if not member:
                        errors.append({
                            "email": m["member_email"],
                            "error": "Member not found (import members first)",
                        })
                        continue

                    mt_id = type_name_to_id.get(m["membership_name"])
                    if not mt_id:
                        skipped += 1
                        continue

                    starts_at = self._parse_date(m.get("start_date")) or datetime.now(timezone.utc)
                    ends_at = self._parse_date(m.get("end_date"))
                    status = self._map_status(m.get("status", "active"))

                    mm_id = str(uuid.uuid4())
                    await db.execute(
                        """
                        INSERT INTO member_memberships
                            (id, member_id, membership_type_id, status, starts_at, ends_at)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        mm_id, str(member["id"]), mt_id, status, starts_at, ends_at,
                    )
                    memberships_created += 1
                except Exception as e:
                    errors.append({"email": m.get("member_email"), "error": str(e)})

        logger.info(
            "MomoYoga membership import complete",
            types_created=types_created,
            memberships_created=memberships_created,
        )
        return {
            "types_created": types_created,
            "memberships_created": memberships_created,
            "skipped": skipped,
            "errors": errors,
            "total": len(parsed),
        }

    async def import_attendance_history(self, csv_content: str, studio_id: str) -> dict:
        """Import class session history from a classes CSV.

        Creates historical class_sessions with status='completed' and
        accurate attendee counts. Does not create per-member bookings
        (MomoYoga only exports aggregate attendee counts per class).
        """
        parsed = self.parse_classes_csv(csv_content)
        sessions_created = 0
        errors = []

        async with get_tenant_db() as db:
            # Build lookup maps
            instr_rows = await db.fetch("SELECT id, display_name FROM instructors")
            instructor_map = {r["display_name"].lower(): str(r["id"]) for r in instr_rows}

            ct_rows = await db.fetch(
                "SELECT id, name FROM class_types WHERE studio_id = $1", studio_id,
            )
            ct_map = {r["name"]: str(r["id"]) for r in ct_rows}

            for cls in parsed:
                try:
                    ct_id = ct_map.get(cls["name"])
                    if not ct_id:
                        continue  # class type not imported yet

                    instr_id = instructor_map.get(cls.get("instructor", "").lower())

                    session_date = self._parse_date(cls.get("date"))
                    if not session_date:
                        continue

                    raw_time = cls.get("time", "09:00").strip()
                    is_pm = "PM" in raw_time.upper()
                    is_am = "AM" in raw_time.upper()
                    cleaned = raw_time.upper().replace("AM", "").replace("PM", "").strip()
                    time_parts = cleaned.split(":")
                    hour = int(time_parts[0]) if time_parts else 9
                    minute = int(time_parts[1]) if len(time_parts) > 1 else 0
                    if is_pm and hour != 12:
                        hour += 12
                    elif is_am and hour == 12:
                        hour = 0
                    starts_at = session_date.replace(hour=hour, minute=minute)
                    duration = int(cls.get("duration", 60))
                    ends_at = starts_at + timedelta(minutes=duration)
                    capacity = int(cls.get("capacity", 20))
                    attendee_count = int(cls.get("attendees", 0))

                    session_id = str(uuid.uuid4())
                    await db.execute(
                        """
                        INSERT INTO class_sessions
                            (id, studio_id, class_type_id, instructor_id, title,
                             starts_at, ends_at, capacity, booked_count, status)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'completed')
                        """,
                        session_id, studio_id, ct_id, instr_id, cls["name"],
                        starts_at, ends_at, capacity, attendee_count,
                    )
                    sessions_created += 1
                except Exception as e:
                    errors.append({"class": cls.get("name"), "error": str(e)})

        logger.info(
            "MomoYoga attendance import complete",
            sessions_created=sessions_created,
            errors=len(errors),
        )
        return {"sessions_created": sessions_created, "errors": errors, "total": len(parsed)}

    def _parse_time_12h(self, raw: str) -> tuple[int, int]:
        """Parse time string like '10:00 AM', '1:30 PM', or '14:00' into (hour, minute)."""
        raw = raw.strip()
        is_pm = "PM" in raw.upper()
        is_am = "AM" in raw.upper()
        cleaned = raw.upper().replace("AM", "").replace("PM", "").strip()
        parts = cleaned.split(":")
        hour = int(parts[0]) if parts else 9
        minute = int(parts[1]) if len(parts) > 1 else 0
        if is_pm and hour != 12:
            hour += 12
        elif is_am and hour == 12:
            hour = 0
        return hour, minute

    async def import_schedule(self, csv_content: str, studio_id: str, expand_weeks: int = 4) -> dict:
        """Import every CSV row as a recurring weekly class series.

        Each row becomes a class_series with RRULE, then sessions are created
        directly with proper timezone-aware timestamps (America/Los_Angeles).
        """
        DAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        tz = zoneinfo.ZoneInfo("America/Los_Angeles")

        parsed = self.parse_classes_csv(csv_content)
        series_created = 0
        sessions_created = 0
        errors = []

        async with get_tenant_db() as db:
            # Build lookup maps
            instr_rows = await db.fetch("SELECT id, display_name FROM instructors")
            instructor_map = {r["display_name"].lower(): str(r["id"]) for r in instr_rows}

            ct_rows = await db.fetch(
                "SELECT id, name FROM class_types WHERE studio_id = $1", studio_id,
            )
            ct_map = {r["name"]: str(r["id"]) for r in ct_rows}

            today = date.today()
            until_date = today + timedelta(weeks=expand_weeks)

            for cls in parsed:
                try:
                    ct_id = ct_map.get(cls["name"])
                    if not ct_id:
                        errors.append({"class": cls["name"], "error": "Class type not found"})
                        continue

                    instr_id = instructor_map.get(cls.get("instructor", "").lower())

                    # Parse date to determine day of week
                    session_date = self._parse_date(cls.get("date"))
                    if not session_date:
                        errors.append({"class": cls["name"], "error": "Could not parse date"})
                        continue

                    day_code = DAY_CODES[session_date.weekday()]
                    target_weekday = session_date.weekday()
                    rrule = f"FREQ=WEEKLY;BYDAY={day_code}"

                    hour, minute = self._parse_time_12h(cls.get("time", "09:00"))
                    duration = int(cls.get("duration", 60))
                    capacity = int(cls.get("capacity", 20))

                    # Create the series record
                    series_id = str(uuid.uuid4())
                    await db.execute(
                        """
                        INSERT INTO class_series
                            (id, studio_id, class_type_id, instructor_id, title, rrule,
                             start_time, duration_minutes, capacity, waitlist_capacity,
                             effective_from, timezone, is_active, is_virtual, auto_record)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 10, $10, 'America/Los_Angeles', TRUE, FALSE, FALSE)
                        """,
                        series_id, studio_id, ct_id, instr_id, cls["name"], rrule,
                        datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time(),
                        duration, capacity, today,
                    )
                    series_created += 1

                    # Generate sessions with timezone-aware timestamps
                    # Find the next occurrence of this weekday from today
                    days_ahead = target_weekday - today.weekday()
                    if days_ahead < 0:
                        days_ahead += 7
                    next_date = today + timedelta(days=days_ahead)

                    d = next_date
                    while d <= until_date:
                        local_start = datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)
                        local_end = local_start + timedelta(minutes=duration)

                        session_id = str(uuid.uuid4())
                        await db.execute(
                            """
                            INSERT INTO class_sessions
                                (id, studio_id, class_type_id, instructor_id, series_id,
                                 title, starts_at, ends_at, timezone, capacity, waitlist_capacity)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'America/Los_Angeles', $9, 10)
                            """,
                            session_id, studio_id, ct_id, instr_id, series_id,
                            cls["name"], local_start, local_end, capacity,
                        )
                        sessions_created += 1
                        d += timedelta(weeks=1)

                except Exception as e:
                    errors.append({"class": cls.get("name"), "error": str(e)})

        logger.info(
            "MomoYoga schedule import complete",
            series_created=series_created,
            sessions_created=sessions_created,
            errors=len(errors),
            error_details=errors[:5] if errors else [],
        )
        return {
            "series_created": series_created,
            "sessions_created": sessions_created,
            "errors": errors,
            "total": len(parsed),
        }
