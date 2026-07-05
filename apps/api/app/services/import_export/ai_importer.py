"""AuraFlow — AI-Powered CSV Import Service

Uses Claude Sonnet to intelligently analyze CSV files from ANY studio
management platform, map columns to AuraFlow fields, and import data.
Replaces rigid column-name parsing with AI-driven understanding.
"""
import csv
import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import zoneinfo

from app.core.config import settings
from app.core.logging import logger
from app.core.security import hash_password
from app.db.session import get_tenant_db, get_global_db
from app.services.ai.token_tracking_service import track_ai_usage


# ── Known membership name mappings ────────────────────────────────────────────

NAME_MAP = {
    "One Month Unlimited - In Studio": "Unlimited In-Studio (Monthly)",
    "One Month Unlimited - In Studio & Digital": "Unlimited All-Access (Monthly)",
    "One Year Unlimited - In Studio & Digital": "Unlimited All-Access (Yearly)",
    "One Year Unlimited - In Studio": "Unlimited In-Studio (Yearly)",
    "FREE First Class - In Studio & Digital": "FREE First Class - All-Access",
    "FREE First Class - In Studio": "FREE First Class - In-Studio",
    "Family & Friends": "Friends and Family",
    "10 Class Pack - In Studio": "10-Class Pack (In-Studio)",
    "10 Class Pack - In Studio & Digital": "10-Class Pack (All-Access)",
    "20 Class Pack - In Studio": "20-Class Pack (In-Studio)",
    "5 Class Pack - In Studio": "5-Class Pack (In-Studio)",
    "Drop-In - In Studio": "Drop-In",
    "Intro Offer - 2 Weeks Unlimited": "Intro Offer (2-Week Unlimited)",
    "Intro Offer - 1 Month Unlimited": "Intro Offer (1-Month Unlimited)",
    "New Student Special": "New Student Special",
}

# AuraFlow field definitions for Claude analysis prompt
AURAFLOW_FIELDS = """
Members table fields:
- first_name (required): Member's first name
- last_name (required): Member's last name
- email (required): Email address — used as unique identifier
- phone: Phone number
- date_of_birth: Date of birth
- address_line1: Street address
- city: City
- state: State/Province
- postal_code: Zip/Postal code
- emergency_contact_name: Emergency contact name
- emergency_contact_phone: Emergency contact phone
- notes: Free-text notes
- member_since: Date they joined the studio
- total_visits: Total number of visits/classes attended (numeric)
- source: Where this member came from (will be set to 'ai_import')

Membership fields (may be columns in the same CSV or a separate file):
- membership_type: Name of the membership/subscription plan
- membership_status: active, frozen, cancelled, expired
- membership_start_date: When the membership started
- membership_end_date: When the membership expires
- billing_period: monthly, yearly, etc.
- price: Membership price

Class pass fields:
- pass_type: Name of the class pass/pack
- credits_remaining: Number of classes left
- pass_expiry_date: When the pass expires

Attendance history fields (usually a separate CSV):
- class_name: Name of the class attended
- attendance_date: Date of attendance
- attendance_status: attended, no_show, cancelled
- instructor: Instructor/teacher name

Waiver fields:
- waiver_signed: Whether a liability waiver was signed (yes/no/true/false)
"""


class AIImporter:
    """AI-powered CSV import that works with exports from any studio platform."""

    # ── CSV Parsing Helpers ───────────────────────────────────────────────────

    def _detect_delimiter(self, csv_content: str) -> str:
        """Detect CSV delimiter (tab vs comma vs semicolon)."""
        first_line = csv_content.split("\n")[0]
        if "\t" in first_line:
            return "\t"
        if ";" in first_line and "," not in first_line:
            return ";"
        return ","

    def _read_csv(self, csv_content: str) -> tuple[list[str], list[list[str]]]:
        """Read CSV and return (headers, rows)."""
        delimiter = self._detect_delimiter(csv_content)
        reader = csv.reader(io.StringIO(csv_content), delimiter=delimiter)
        rows = list(reader)
        if not rows:
            return [], []
        headers = [h.strip() for h in rows[0]]
        data_rows = rows[1:]
        return headers, data_rows

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """Parse various date formats."""
        if not date_str or not date_str.strip():
            return None
        date_str = date_str.strip()
        # Try standard formats
        for fmt in (
            "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
            "%m-%d-%Y", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y",
            "%Y-%m-%dT%H:%M:%S", "%m/%d/%y", "%d-%m-%y",
        ):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        # Try dateutil as fallback
        try:
            from dateutil import parser as dateutil_parser
            return dateutil_parser.parse(date_str)
        except Exception:
            pass
        return None

    def _parse_price(self, price_str: str) -> int:
        """Parse a price string to cents. '150' -> 15000, '29.99' -> 2999."""
        try:
            cleaned = price_str.replace("$", "").replace(",", "").replace("€", "").replace("£", "").strip()
            return int(float(cleaned) * 100)
        except (ValueError, AttributeError):
            return 0

    def _infer_membership_type(self, name: str) -> str:
        """Infer membership type category from name."""
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

    def _map_status(self, raw_status: str) -> str:
        """Map various status strings to AuraFlow status."""
        lower = raw_status.lower().strip()
        if lower in ("active", "actief", "current"):
            return "active"
        if lower in ("cancelled", "canceled", "opgezegd", "cancellation scheduled"):
            return "cancelled"
        if lower in ("frozen", "paused", "gepauzeerd", "on hold", "hold"):
            return "frozen"
        if lower in ("expired", "verlopen", "lapsed"):
            return "expired"
        return "active"

    def _clean_membership_name(self, raw_name: str) -> str:
        """Strip status suffixes from membership names."""
        name = raw_name.strip()
        for suffix in (
            "Cancellation scheduled", "Paused", "Cancelled", "Canceled",
            "Expired", "Active", "Frozen", "First visit",
        ):
            if name.endswith(suffix):
                name = name[: -len(suffix)].strip()
                if name.endswith(" -"):
                    name = name[:-2].strip()
        return name

    # ── AI Analysis ──────────────────────────────────────────────────────────

    async def analyze_csv_files(self, file_contents: dict[str, str]) -> dict:
        """Analyze uploaded CSV files using Claude to map columns to AuraFlow fields.

        Args:
            file_contents: dict of {filename: csv_content_string}

        Returns:
            Analysis with column mappings, preview data, and summary.
        """
        import anthropic

        # Build file summaries for Claude
        file_summaries = []
        all_preview_data = {}
        total_rows = 0

        for filename, content in file_contents.items():
            headers, rows = self._read_csv(content)
            total_rows += len(rows)
            preview_rows = rows[:5]
            all_preview_data[filename] = {
                "headers": headers,
                "preview_rows": preview_rows,
                "total_rows": len(rows),
            }

            file_summaries.append(
                f"File: {filename}\n"
                f"Total rows: {len(rows)}\n"
                f"Headers: {', '.join(headers)}\n"
                f"Sample data (first 5 rows):\n"
                + "\n".join(
                    " | ".join(row[:len(headers)]) for row in preview_rows
                )
            )

        prompt = f"""You are a data migration expert for a yoga/fitness studio management platform called AuraFlow. Analyze these CSV files exported from another studio management system and identify what data they contain.

For each file, map each CSV column to the appropriate AuraFlow database field.

{AURAFLOW_FIELDS}

Here are the CSV files to analyze:

{"---".join(file_summaries)}

Respond with ONLY valid JSON (no markdown, no code fences) in this exact format:
{{
    "files": {{
        "<filename>": {{
            "detected_type": "members|memberships|attendance|classes|mixed",
            "column_mappings": {{
                "<csv_column_name>": "<auraflow_field_name or null if no match>"
            }},
            "notes": "any relevant observations about this file"
        }}
    }},
    "membership_types_found": ["list of unique membership/subscription names found in data"],
    "summary": "1-2 sentence summary of what was found across all files"
}}

Important rules:
- If a single file contains BOTH member info AND membership info, map all columns
- If a column has no clear AuraFlow equivalent, map it to null
- For membership names, list ALL unique values you see in the sample data
- Be smart about column names: "Subscription" = membership_type, "Lessons Attended" = total_visits, etc.
- If a column contains dates, identify the date format used
"""

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        try:
            message = await client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            await track_ai_usage(
                service_name="ai_importer",
                function_name="analyze_csv_files",
                model=settings.ANTHROPIC_MODEL,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            )

            response_text = message.content[0].text.strip()
            # Strip markdown code fences if present
            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[1]
                if response_text.endswith("```"):
                    response_text = response_text[:-3].strip()

            analysis = json.loads(response_text)

        except json.JSONDecodeError as e:
            logger.error("AI analysis JSON parse error", error=str(e), response=response_text[:500])
            raise ValueError(f"AI returned invalid JSON: {str(e)}")
        except anthropic.APIError as e:
            logger.error("Claude API error during CSV analysis", error=str(e))
            raise ValueError(f"AI analysis failed: {str(e)}")

        # Build membership type mappings using NAME_MAP
        membership_types = analysis.get("membership_types_found", [])
        membership_type_mappings = {}
        for mt in membership_types:
            cleaned = self._clean_membership_name(mt)
            if cleaned in NAME_MAP:
                membership_type_mappings[mt] = NAME_MAP[cleaned]
            elif mt in NAME_MAP:
                membership_type_mappings[mt] = NAME_MAP[mt]
            else:
                # Keep as-is but cleaned
                membership_type_mappings[mt] = cleaned

        return {
            "files_analyzed": len(file_contents),
            "total_rows": total_rows,
            "column_mappings": analysis.get("files", {}),
            "preview_data": all_preview_data,
            "membership_type_mappings": membership_type_mappings,
            "membership_types_found": membership_types,
            "summary": analysis.get("summary", "Analysis complete."),
        }

    # ── Preview Import ───────────────────────────────────────────────────────

    async def preview_import(
        self,
        file_contents: dict[str, str],
        column_mappings: dict[str, dict],
        membership_type_mappings: dict[str, str],
    ) -> dict:
        """Apply mappings to full data and return a detailed preview.

        Args:
            file_contents: {filename: csv_content}
            column_mappings: {filename: {detected_type, column_mappings: {csv_col: af_field}}}
            membership_type_mappings: {old_name: new_name}
        """
        members = []
        memberships = []
        attendance_records = []
        issues = []
        seen_emails = set()

        for filename, content in file_contents.items():
            file_mapping = column_mappings.get(filename, {})
            detected_type = file_mapping.get("detected_type", "unknown")
            col_map = file_mapping.get("column_mappings", {})

            headers, rows = self._read_csv(content)

            # Build reverse map: auraflow_field -> csv_column_index
            field_to_idx = {}
            for csv_col, af_field in col_map.items():
                if af_field and csv_col in headers:
                    field_to_idx[af_field] = headers.index(csv_col)

            for row_idx, row in enumerate(rows):
                def get_val(field_name: str) -> str:
                    idx = field_to_idx.get(field_name)
                    if idx is not None and idx < len(row):
                        return row[idx].strip()
                    return ""

                if detected_type in ("members", "mixed"):
                    email = get_val("email").lower()
                    first_name = get_val("first_name")
                    last_name = get_val("last_name")

                    if not email:
                        issues.append(f"Row {row_idx + 2} in {filename}: missing email")
                        continue
                    if not first_name:
                        issues.append(f"Row {row_idx + 2} in {filename}: missing first_name for {email}")

                    if email in seen_emails:
                        issues.append(f"Duplicate email: {email} in {filename} row {row_idx + 2}")
                    else:
                        seen_emails.add(email)
                        member = {
                            "email": email,
                            "first_name": first_name,
                            "last_name": last_name,
                            "phone": get_val("phone") or None,
                            "date_of_birth": get_val("date_of_birth") or None,
                            "address_line1": get_val("address_line1") or None,
                            "city": get_val("city") or None,
                            "state": get_val("state") or None,
                            "postal_code": get_val("postal_code") or None,
                            "emergency_contact_name": get_val("emergency_contact_name") or None,
                            "emergency_contact_phone": get_val("emergency_contact_phone") or None,
                            "notes": get_val("notes") or None,
                            "member_since": get_val("member_since") or None,
                            "total_visits": get_val("total_visits") or "0",
                            "waiver_signed": get_val("waiver_signed") or None,
                        }
                        members.append(member)

                    # Check for membership data in same row
                    membership_type = get_val("membership_type")
                    if membership_type:
                        cleaned = self._clean_membership_name(membership_type)
                        mapped_name = membership_type_mappings.get(
                            membership_type,
                            membership_type_mappings.get(cleaned, cleaned),
                        )
                        memberships.append({
                            "member_email": email,
                            "original_name": membership_type,
                            "mapped_name": mapped_name,
                            "status": get_val("membership_status") or "active",
                            "start_date": get_val("membership_start_date") or None,
                            "end_date": get_val("membership_end_date") or None,
                            "price": get_val("price") or "0",
                        })

                    # Check for pass data
                    pass_type = get_val("pass_type")
                    if pass_type:
                        memberships.append({
                            "member_email": email,
                            "original_name": pass_type,
                            "mapped_name": membership_type_mappings.get(pass_type, pass_type),
                            "status": "active",
                            "start_date": None,
                            "end_date": get_val("pass_expiry_date") or None,
                            "credits_remaining": get_val("credits_remaining") or None,
                            "price": "0",
                        })

                elif detected_type == "memberships":
                    email = get_val("email").lower()
                    membership_type = get_val("membership_type")
                    if email and membership_type:
                        cleaned = self._clean_membership_name(membership_type)
                        mapped_name = membership_type_mappings.get(
                            membership_type,
                            membership_type_mappings.get(cleaned, cleaned),
                        )
                        memberships.append({
                            "member_email": email,
                            "original_name": membership_type,
                            "mapped_name": mapped_name,
                            "status": get_val("membership_status") or "active",
                            "start_date": get_val("membership_start_date") or None,
                            "end_date": get_val("membership_end_date") or None,
                            "price": get_val("price") or "0",
                        })

                elif detected_type == "attendance":
                    email = get_val("email").lower()
                    class_name = get_val("class_name")
                    att_date = get_val("attendance_date")
                    if class_name and att_date:
                        attendance_records.append({
                            "member_email": email or None,
                            "class_name": class_name,
                            "date": att_date,
                            "status": get_val("attendance_status") or "attended",
                            "instructor": get_val("instructor") or None,
                        })

        # Check for duplicate emails against existing DB
        duplicate_emails = []
        if members:
            async with get_tenant_db() as db:
                for m in members:
                    existing = await db.fetchrow(
                        "SELECT id FROM members WHERE email = $1", m["email"]
                    )
                    if existing:
                        duplicate_emails.append(m["email"])

        # Count membership types
        membership_type_counts = {}
        for ms in memberships:
            name = ms["mapped_name"]
            membership_type_counts[name] = membership_type_counts.get(name, 0) + 1

        return {
            "members_found": len(members),
            "members_with_existing_account": len(duplicate_emails),
            "members_new": len(members) - len(duplicate_emails),
            "memberships_found": len(memberships),
            "membership_type_counts": membership_type_counts,
            "membership_type_mappings": membership_type_mappings,
            "attendance_records": len(attendance_records),
            "issues": issues[:50],  # Cap at 50 issues
            "duplicate_emails": duplicate_emails[:20],
            "sample_members": [
                {"name": f"{m['first_name']} {m['last_name']}", "email": m["email"]}
                for m in members[:10]
            ],
        }

    # ── Execute Import ───────────────────────────────────────────────────────

    async def execute_import(
        self,
        file_contents: dict[str, str],
        column_mappings: dict[str, dict],
        membership_type_mappings: dict[str, str],
        studio_id: str,
        default_password: str = "example-studio",
    ) -> dict:
        """Execute the actual import. Processes one member at a time.

        Args:
            file_contents: {filename: csv_content}
            column_mappings: {filename: {detected_type, column_mappings}}
            membership_type_mappings: {old_name: new_name}
            studio_id: Target studio UUID
            default_password: Default password for new accounts
        """
        pw_hash = hash_password(default_password)
        tz = zoneinfo.ZoneInfo("America/Los_Angeles")

        # Counters
        members_created = 0
        members_updated = 0
        user_accounts_created = 0
        memberships_created = 0
        passes_with_credits = 0
        attendance_imported = 0
        errors = []

        # Collect all data
        all_members = []  # list of member dicts
        all_memberships = []  # list of {member_email, mapped_name, status, ...}
        all_attendance = []  # list of {member_email, class_name, date, status}

        for filename, content in file_contents.items():
            file_mapping = column_mappings.get(filename, {})
            detected_type = file_mapping.get("detected_type", "unknown")
            col_map = file_mapping.get("column_mappings", {})

            headers, rows = self._read_csv(content)

            field_to_idx = {}
            for csv_col, af_field in col_map.items():
                if af_field and csv_col in headers:
                    field_to_idx[af_field] = headers.index(csv_col)

            for row in rows:
                def get_val(field_name: str) -> str:
                    idx = field_to_idx.get(field_name)
                    if idx is not None and idx < len(row):
                        return row[idx].strip()
                    return ""

                if detected_type in ("members", "mixed"):
                    email = get_val("email").lower().strip()
                    if not email:
                        continue
                    member = {
                        "email": email,
                        "first_name": get_val("first_name"),
                        "last_name": get_val("last_name"),
                        "phone": get_val("phone") or None,
                        "date_of_birth": get_val("date_of_birth") or None,
                        "address_line1": get_val("address_line1") or None,
                        "city": get_val("city") or None,
                        "state": get_val("state") or None,
                        "postal_code": get_val("postal_code") or None,
                        "emergency_contact_name": get_val("emergency_contact_name") or None,
                        "emergency_contact_phone": get_val("emergency_contact_phone") or None,
                        "notes": get_val("notes") or None,
                        "member_since": get_val("member_since") or None,
                        "total_visits": get_val("total_visits") or "0",
                    }
                    all_members.append(member)

                    # Membership in same row
                    ms_type = get_val("membership_type")
                    if ms_type:
                        cleaned = self._clean_membership_name(ms_type)
                        mapped = membership_type_mappings.get(
                            ms_type, membership_type_mappings.get(cleaned, cleaned)
                        )
                        all_memberships.append({
                            "member_email": email,
                            "mapped_name": mapped,
                            "status": get_val("membership_status") or "active",
                            "start_date": get_val("membership_start_date") or None,
                            "end_date": get_val("membership_end_date") or None,
                            "price": get_val("price") or "0",
                            "credits_remaining": None,
                        })

                    # Pass in same row
                    pass_type = get_val("pass_type")
                    if pass_type:
                        mapped = membership_type_mappings.get(pass_type, pass_type)
                        all_memberships.append({
                            "member_email": email,
                            "mapped_name": mapped,
                            "status": "active",
                            "start_date": None,
                            "end_date": get_val("pass_expiry_date") or None,
                            "credits_remaining": get_val("credits_remaining") or None,
                            "price": "0",
                        })

                elif detected_type == "memberships":
                    email = get_val("email").lower().strip()
                    ms_type = get_val("membership_type")
                    if email and ms_type:
                        cleaned = self._clean_membership_name(ms_type)
                        mapped = membership_type_mappings.get(
                            ms_type, membership_type_mappings.get(cleaned, cleaned)
                        )
                        all_memberships.append({
                            "member_email": email,
                            "mapped_name": mapped,
                            "status": get_val("membership_status") or "active",
                            "start_date": get_val("membership_start_date") or None,
                            "end_date": get_val("membership_end_date") or None,
                            "price": get_val("price") or "0",
                            "credits_remaining": get_val("credits_remaining") or None,
                        })

                elif detected_type == "attendance":
                    email = get_val("email").lower().strip()
                    class_name = get_val("class_name")
                    att_date = get_val("attendance_date")
                    if class_name and att_date:
                        all_attendance.append({
                            "member_email": email or None,
                            "class_name": class_name,
                            "date": att_date,
                            "status": get_val("attendance_status") or "attended",
                        })

        # Look up org ID
        async with get_global_db() as gdb:
            org_row = await gdb.fetchrow("SELECT id FROM af_global.organizations LIMIT 1")
            org_id = str(org_row["id"]) if org_row else None

        # ── Step 1: Create/update members one at a time ──────────────────────
        member_id_map = {}  # email -> member_id

        async with get_tenant_db() as db:
            # Pre-fetch membership types for this studio
            mt_rows = await db.fetch(
                "SELECT id, name FROM membership_types WHERE studio_id = $1 AND is_active = TRUE",
                studio_id,
            )
            type_map = {r["name"]: str(r["id"]) for r in mt_rows}

            # Pre-fetch class types
            ct_rows = await db.fetch(
                "SELECT id, name FROM class_types WHERE studio_id = $1", studio_id,
            )
            ct_map = {r["name"].lower(): str(r["id"]) for r in ct_rows}

            # Deduplicate members by email (keep first occurrence)
            seen_emails = set()
            unique_members = []
            for m in all_members:
                if m["email"] not in seen_emails:
                    seen_emails.add(m["email"])
                    unique_members.append(m)

            for m in unique_members:
                try:
                    # Post-Phase-C: plain PHI columns are gone. Pull the
                    # _enc shadows so we can decrypt the existing PHI and
                    # decide whether to keep it (existing wins) or insert
                    # the incoming CSV value.
                    existing = await db.fetchrow(
                        """
                        SELECT id, user_id,
                               phone_enc, date_of_birth_enc, address_line1_enc,
                               city_enc, state_enc, postal_code_enc,
                               emergency_contact_name_enc,
                               emergency_contact_phone_enc, notes_enc
                        FROM members WHERE email = $1
                        """,
                        m["email"],
                    )

                    if existing:
                        member_id = str(existing["id"])
                        member_id_map[m["email"]] = member_id
                        members_updated += 1

                        # Update fields that may be missing.
                        # HIPAA-2C Phase C: every PHI field gets dual-written
                        # to its _enc shadow AND, for phone, to phone_hash —
                        # otherwise re-imports of legacy members leave them
                        # unsearchable after the plaintext drop.
                        #
                        # Resulting value rule: if the existing _enc shadow
                        # decrypts to something non-empty, that value wins
                        # (don't overwrite real data with a stale CSV).
                        # Otherwise the incoming CSV value gets dual-written.
                        from app.services.members.member_service import (
                            _enc_or_none, _extract_birthday_parts,
                        )
                        from app.services.members.phi_helpers import _safe_decrypt
                        from app.services.members.phone_hash import hash_phone

                        def _existing_plain(field: str):
                            """Decrypt the existing _enc shadow for `field`,
                            returning None if missing/unreadable."""
                            enc_val = existing[f"{field}_enc"]
                            if enc_val is None:
                                return None
                            return _safe_decrypt(enc_val, field)

                        update_fields = []
                        update_values = []
                        param_idx = 1

                        for field in ("phone", "date_of_birth", "address_line1", "city",
                                      "state", "postal_code", "emergency_contact_name",
                                      "emergency_contact_phone", "notes"):
                            val = m.get(field)
                            if val and field == "date_of_birth":
                                val = self._parse_date(val)
                            if val:
                                existing_plain = _existing_plain(field)
                                # Resulting value: existing wins if non-empty.
                                resulting = existing_plain if existing_plain else val
                                if field == "date_of_birth" and isinstance(resulting, str):
                                    resulting = self._parse_date(resulting) or val

                                # Only write _enc if the existing shadow is
                                # actually NULL (a re-import shouldn't churn
                                # encryption bytes on every run).
                                if existing[f"{field}_enc"] is None:
                                    param_idx += 1
                                    update_fields.append(
                                        f"{field}_enc = ${param_idx}"
                                    )
                                    update_values.append(_enc_or_none(resulting))
                                if field == "phone":
                                    # Always recompute hash if missing.
                                    param_idx += 1
                                    update_fields.append(
                                        f"phone_hash = COALESCE(phone_hash, ${param_idx})"
                                    )
                                    update_values.append(hash_phone(resulting))
                                if field == "date_of_birth":
                                    bm, bd = _extract_birthday_parts(resulting)
                                    param_idx += 1
                                    update_fields.append(
                                        f"birthday_month = COALESCE(birthday_month, ${param_idx})"
                                    )
                                    update_values.append(bm)
                                    param_idx += 1
                                    update_fields.append(
                                        f"birthday_day = COALESCE(birthday_day, ${param_idx})"
                                    )
                                    update_values.append(bd)

                        if update_fields:
                            query = f"UPDATE members SET {', '.join(update_fields)} WHERE id = $1"
                            await db.execute(query, member_id, *update_values)

                        # Ensure user account exists
                        async with get_global_db() as gdb:
                            user_exists = None
                            if existing["user_id"] is not None:
                                user_exists = await gdb.fetchrow(
                                    "SELECT id FROM af_global.users WHERE id = $1",
                                    str(existing["user_id"]),
                                )
                            if not user_exists:
                                user_id = str(existing["user_id"]) if existing["user_id"] else str(uuid.uuid4())
                                await gdb.execute(
                                    """
                                    INSERT INTO af_global.users
                                        (id, email, password_hash, first_name, last_name,
                                         is_active, force_password_reset)
                                    VALUES ($1, $2, $3, $4, $5, TRUE, TRUE)
                                    ON CONFLICT (email) DO NOTHING
                                    """,
                                    user_id, m["email"].lower(), pw_hash,
                                    m["first_name"], m["last_name"],
                                )
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
                        member_id_map[m["email"]] = member_id

                        # Create user account
                        async with get_global_db() as gdb:
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
                                    user_id, m["email"].lower(), pw_hash,
                                    m["first_name"], m["last_name"],
                                )
                                user_accounts_created += 1

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
                        total_visits = 0
                        try:
                            total_visits = int(m.get("total_visits", "0"))
                        except (ValueError, TypeError):
                            pass

                        # HIPAA-2C dual-write: encrypted shadows + birthday
                        # derived columns + phone_hash. See momoyoga_importer
                        # for the rationale — Phase C drop would otherwise
                        # erase every PHI field for every AI-imported member.
                        from app.services.members.member_service import (
                            _enc_or_none, _extract_birthday_parts,
                        )
                        from app.services.members.phone_hash import hash_phone
                        bday_month, bday_day = _extract_birthday_parts(dob)
                        # Post-Phase-C: insert _enc shadows + derived
                        # columns only; plaintext PHI columns no longer
                        # exist on the members table.
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
                            m["email"], joined_at, "ai_import", total_visits,
                            _enc_or_none(m.get("phone")),
                            _enc_or_none(dob),
                            _enc_or_none(m.get("address_line1")),
                            _enc_or_none(m.get("city")),
                            _enc_or_none(m.get("state")),
                            _enc_or_none(m.get("postal_code")),
                            _enc_or_none(m.get("emergency_contact_name")),
                            _enc_or_none(m.get("emergency_contact_phone")),
                            _enc_or_none(m.get("notes")),
                            bday_month, bday_day,
                            hash_phone(m.get("phone")),
                        )
                        members_created += 1

                except Exception as e:
                    errors.append({"email": m.get("email"), "error": str(e)})
                    logger.error("AI import member error", email=m.get("email"), error=str(e))

            # ── Step 2: Create memberships one at a time ─────────────────────

            for ms in all_memberships:
                try:
                    email = ms["member_email"]
                    member_id = member_id_map.get(email)
                    if not member_id:
                        # Look up member by email
                        row = await db.fetchrow(
                            "SELECT id FROM members WHERE email = $1", email
                        )
                        if row:
                            member_id = str(row["id"])
                            member_id_map[email] = member_id
                        else:
                            errors.append({"email": email, "error": "Member not found for membership"})
                            continue

                    mapped_name = ms["mapped_name"]

                    # Find or create membership type
                    mt_id = None
                    # Try exact match first
                    for name, tid in type_map.items():
                        if name.lower().strip() == mapped_name.lower().strip():
                            mt_id = tid
                            break
                    # Try partial match
                    if not mt_id:
                        for name, tid in type_map.items():
                            if mapped_name.lower() in name.lower() or name.lower() in mapped_name.lower():
                                mt_id = tid
                                break

                    if not mt_id:
                        # Create new membership type
                        new_mt_id = str(uuid.uuid4())
                        inferred = self._infer_membership_type(mapped_name)
                        price_cents = self._parse_price(ms.get("price", "0"))
                        await db.execute(
                            """
                            INSERT INTO membership_types
                                (id, studio_id, name, type, price_cents, billing_period,
                                 is_active, is_public, sort_order)
                            VALUES ($1, $2, $3, $4, $5, 'monthly', TRUE, TRUE, 99)
                            """,
                            new_mt_id, studio_id, mapped_name, inferred, price_cents,
                        )
                        type_map[mapped_name] = new_mt_id
                        mt_id = new_mt_id
                        logger.info("Created membership type from AI import", name=mapped_name)

                    # Check for existing membership assignment
                    existing_mm = await db.fetchrow(
                        "SELECT id FROM member_memberships WHERE member_id = $1 AND membership_type_id = $2",
                        member_id, mt_id,
                    )
                    if not existing_mm:
                        mm_id = str(uuid.uuid4())
                        status = self._map_status(ms.get("status", "active"))
                        starts_at = self._parse_date(ms.get("start_date")) or datetime.now(timezone.utc)

                        await db.execute(
                            """
                            INSERT INTO member_memberships
                                (id, member_id, membership_type_id, status, starts_at)
                            VALUES ($1, $2, $3, $4, $5)
                            """,
                            mm_id, member_id, mt_id, status, starts_at,
                        )
                        memberships_created += 1

                        if ms.get("credits_remaining"):
                            passes_with_credits += 1

                except Exception as e:
                    errors.append({"email": ms.get("member_email"), "error": str(e)})
                    logger.error("AI import membership error", email=ms.get("member_email"), error=str(e))

            # ── Step 3: Import attendance one at a time ──────────────────────

            session_cache: dict[tuple, str] = {}

            for att in all_attendance:
                try:
                    class_name = att["class_name"]
                    att_date = self._parse_date(att["date"])
                    if not att_date:
                        continue

                    # Find member
                    member_id = None
                    if att.get("member_email"):
                        member_id = member_id_map.get(att["member_email"])
                        if not member_id:
                            row = await db.fetchrow(
                                "SELECT id FROM members WHERE email = $1",
                                att["member_email"],
                            )
                            if row:
                                member_id = str(row["id"])
                                member_id_map[att["member_email"]] = member_id

                    if not member_id:
                        continue

                    # Find class type
                    ct_id = ct_map.get(class_name.lower())
                    if not ct_id:
                        continue

                    # Find or create historical session
                    cache_key = (att_date.strftime("%Y-%m-%d"), ct_id)
                    if cache_key not in session_cache:
                        existing_sess = await db.fetchrow(
                            """
                            SELECT id FROM class_sessions
                            WHERE class_type_id = $1
                              AND starts_at::date = $2
                              AND status = 'completed'
                            LIMIT 1
                            """,
                            ct_id, att_date.date() if hasattr(att_date, "date") else att_date,
                        )
                        if existing_sess:
                            session_cache[cache_key] = str(existing_sess["id"])
                        else:
                            sess_id = str(uuid.uuid4())
                            local_start = datetime(
                                att_date.year, att_date.month, att_date.day, 9, 0, tzinfo=tz
                            )
                            local_end = local_start + timedelta(hours=1)
                            await db.execute(
                                """
                                INSERT INTO class_sessions
                                    (id, studio_id, class_type_id, title,
                                     starts_at, ends_at, timezone, capacity, status)
                                VALUES ($1, $2, $3, $4, $5, $6, 'America/Los_Angeles', 20, 'completed')
                                """,
                                sess_id, studio_id, ct_id, class_name,
                                local_start, local_end,
                            )
                            session_cache[cache_key] = sess_id

                    session_id = session_cache[cache_key]

                    # Create booking
                    existing_bk = await db.fetchrow(
                        "SELECT id FROM bookings WHERE member_id = $1 AND class_session_id = $2",
                        member_id, session_id,
                    )
                    if not existing_bk:
                        bk_id = str(uuid.uuid4())
                        status = "attended" if att.get("status", "attended").lower() in ("attended", "yes", "present") else "no_show"
                        d_tz = datetime(
                            att_date.year, att_date.month, att_date.day, 9, 0, tzinfo=tz
                        )
                        await db.execute(
                            """
                            INSERT INTO bookings
                                (id, member_id, class_session_id, status,
                                 booked_at, checked_in_at, source)
                            VALUES ($1, $2, $3, $4, $5, $6, 'ai_import')
                            """,
                            bk_id, member_id, session_id, status,
                            d_tz, d_tz if status == "attended" else None,
                        )
                        attendance_imported += 1

                except Exception as e:
                    errors.append({"class": att.get("class_name"), "error": str(e)})
                    logger.error("AI import attendance error", error=str(e))

        logger.info(
            "AI CSV import complete",
            members_created=members_created,
            members_updated=members_updated,
            user_accounts_created=user_accounts_created,
            memberships_created=memberships_created,
            attendance_imported=attendance_imported,
            errors=len(errors),
        )

        return {
            "members_created": members_created,
            "members_updated": members_updated,
            "user_accounts_created": user_accounts_created,
            "memberships_created": memberships_created,
            "passes_with_credits": passes_with_credits,
            "attendance_imported": attendance_imported,
            "errors": errors[:50],
            "total_members_processed": len(unique_members) if 'unique_members' in dir() else members_created + members_updated,
        }

    # ── Chat Interaction ─────────────────────────────────────────────────────

    async def chat_interaction(self, message: str, import_context: dict) -> str:
        """Chat with AI about the import results.

        Args:
            message: User's question
            import_context: Results from the import (summary, counts, errors)
        """
        import anthropic

        prompt = f"""You are a data migration assistant for AuraFlow, a yoga/fitness studio management platform. The user just completed a CSV data import. Here is the import context:

{json.dumps(import_context, indent=2, default=str)}

The user is asking a question about their import. Answer helpfully and concisely. If they ask to make changes, explain what steps would be needed (they may need to use the member management UI to fix individual records).

User question: {message}"""

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        try:
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            await track_ai_usage(
                service_name="ai_importer",
                function_name="chat_interaction",
                model=settings.ANTHROPIC_MODEL,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            return response.content[0].text.strip()

        except anthropic.APIError as e:
            logger.error("AI import chat error", error=str(e))
            return "I encountered an error processing your question. Please try again."
        except Exception as e:
            logger.error("AI import chat unexpected error", error=str(e))
            return "Something went wrong. Please try again."
