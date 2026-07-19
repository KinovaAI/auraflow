"""AuraFlow — Instructor Service

Instructor profiles, availability, and schedule management.
"""
import uuid
from datetime import time as dt_time

from app.core.logging import logger
from app.core.security import hash_password
from app.db.session import get_tenant_db, get_global_db
from app.services.permissions import PermissionService


def _parse_time(val) -> dt_time:
    """Convert a time string 'HH:MM' or time object to datetime.time."""
    if isinstance(val, dt_time):
        return val
    parts = val.split(":")
    return dt_time(int(parts[0]), int(parts[1]))


_INSTRUCTOR_UPDATE_COLS = {
    "display_name", "bio", "photo_url", "specialties", "certifications",
    "zoom_user_id", "email", "phone", "pay_rate_cents", "pay_type", "salary_cents",
    "tax_classification", "workshop_pay_percent", "private_session_pay_percent",
    "training_pay_percent", "color", "sort_order", "is_active",
}


class InstructorService:

    async def create_instructor(self, data: dict, org_slug: str | None = None) -> dict:
        instructor_id = str(uuid.uuid4())
        user_id = data.get("user_id") or str(uuid.uuid4())
        email = (data.get("email") or "").strip().lower()

        # If email provided, create a real user account + staff entry
        if email and org_slug:
            pw_hash = hash_password("example-studio")
            # Split display_name into first/last
            parts = data["display_name"].strip().split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

            async with get_global_db() as gdb:
                async with gdb.transaction():
                    # Check if user already exists
                    existing_user = await gdb.fetchrow(
                        "SELECT id FROM af_global.users WHERE email = $1", email,
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
                            user_id, email, pw_hash, first_name, last_name,
                        )

                    # Get org_id and add to organization_users as instructor
                    org_row = await gdb.fetchrow(
                        "SELECT id FROM af_global.organizations WHERE slug = $1",
                        org_slug,
                    )
                    if org_row:
                        org_id = str(org_row["id"])
                        await gdb.execute(
                            """
                            INSERT INTO af_global.organization_users
                                (id, organization_id, user_id, role, is_active, joined_at)
                            VALUES ($1, $2, $3, 'instructor', TRUE, NOW())
                            ON CONFLICT (organization_id, user_id)
                            DO UPDATE SET role = 'instructor', is_active = TRUE
                            """,
                            str(uuid.uuid4()), org_id, user_id,
                        )

                        # Initialize default permissions for instructor role
                        perm_svc = PermissionService()
                        await perm_svc.initialize_default_permissions(org_id, user_id, "instructor")
            logger.info("Instructor user account created", email=email, user_id=user_id)

        from app.services.members.phone_hash import hash_phone
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO instructors
                    (id, user_id, display_name, bio, photo_url,
                     specialties, certifications, email, phone, phone_hash,
                     pay_rate_cents, pay_type, salary_cents, tax_classification,
                     workshop_pay_percent, private_session_pay_percent, training_pay_percent,
                     color, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
                """,
                instructor_id, user_id, data["display_name"],
                data.get("bio"), data.get("photo_url"),
                data.get("specialties", []), data.get("certifications", []),
                data.get("email"), data.get("phone"), hash_phone(data.get("phone")),
                data.get("pay_rate_cents"), data.get("pay_type", "per_class"),
                data.get("salary_cents", 0),
                data.get("tax_classification", "1099"),
                data.get("workshop_pay_percent", 60),
                data.get("private_session_pay_percent", 70),
                data.get("training_pay_percent", 50),
                data.get("color", "#4F46E5"), data.get("sort_order", 0),
            )
            row = await db.fetchrow("SELECT * FROM instructors WHERE id = $1", instructor_id)
        logger.info("Instructor created", instructor_id=instructor_id, name=data["display_name"])

        # Auto-assign Friends & Family membership to instructors/staff
        try:
            await self._assign_staff_membership(data.get("email"), data["display_name"])
        except Exception as e:
            logger.warning("Failed to auto-assign staff membership", error=str(e))

        return dict(row)

    async def update_instructor(self, instructor_id: str, data: dict) -> dict | None:
        updates = {k: v for k, v in data.items() if v is not None and k in _INSTRUCTOR_UPDATE_COLS}
        if not updates:
            return await self.get_instructor(instructor_id)

        # If phone is changing, recompute phone_hash so the SMS-routing
        # lookup in office_manager_service stays in sync. Without this,
        # a phone update would leave a stale hash and inbound SMS would
        # mis-route or fall through to "unknown".
        if "phone" in updates:
            from app.services.members.phone_hash import hash_phone
            updates["phone_hash"] = hash_phone(updates["phone"])

        set_clauses = []
        params = []
        for i, (col, val) in enumerate(updates.items(), start=1):
            set_clauses.append(f"{col} = ${i}")
            params.append(val)
        params.append(instructor_id)

        async with get_tenant_db() as db:
            await db.execute(
                f"UPDATE instructors SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = ${len(params)}",
                *params,
            )
            row = await db.fetchrow("SELECT * FROM instructors WHERE id = $1", instructor_id)
        return dict(row) if row else None

    async def _assign_staff_membership(self, email: str | None, display_name: str) -> None:
        """Auto-assign a free Friends & Family membership to new instructors/staff.

        Creates a member record if one doesn't exist, then assigns the first
        free (price_cents=0) unlimited membership type found.
        """
        if not email:
            return

        async with get_tenant_db() as db:
            # Find or create member
            member = await db.fetchrow(
                "SELECT id FROM members WHERE email = $1", email.strip().lower()
            )
            if not member:
                parts = display_name.strip().split(" ", 1)
                member = await db.fetchrow(
                    """
                    INSERT INTO members (id, user_id, first_name, last_name, email, source, is_active)
                    VALUES ($1, $2, $3, $4, $5, 'staff', TRUE)
                    RETURNING id
                    """,
                    str(uuid.uuid4()), str(uuid.uuid4()),
                    parts[0], parts[1] if len(parts) > 1 else "",
                    email.strip().lower(),
                )

            # Find a free unlimited membership type (Friends & Family or similar)
            ff_type = await db.fetchrow(
                """
                SELECT id FROM membership_types
                WHERE price_cents = 0 AND type = 'unlimited' AND is_active = TRUE
                ORDER BY CASE WHEN LOWER(name) LIKE '%friend%' THEN 0 ELSE 1 END
                LIMIT 1
                """
            )
            if not ff_type:
                return

            # Check if already assigned
            existing = await db.fetchval(
                """
                SELECT id FROM member_memberships
                WHERE member_id = $1 AND membership_type_id = $2 AND status = 'active'
                """,
                member["id"], ff_type["id"],
            )
            if existing:
                return

            # Assign
            await db.execute(
                """
                INSERT INTO member_memberships (id, member_id, membership_type_id, status, starts_at)
                VALUES ($1, $2, $3, 'active', NOW())
                """,
                str(uuid.uuid4()), str(member["id"]), str(ff_type["id"]),
            )
            logger.info("Staff membership assigned", email=email, membership_type_id=str(ff_type["id"]))

    async def get_instructor(self, instructor_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow("SELECT * FROM instructors WHERE id = $1", instructor_id)
        return dict(row) if row else None

    async def list_instructors(self, active_only: bool = True) -> list[dict]:
        query = "SELECT * FROM instructors"
        if active_only:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY sort_order, display_name"
        async with get_tenant_db() as db:
            rows = await db.fetch(query)
        return [dict(r) for r in rows]

    async def deactivate_instructor(self, instructor_id: str) -> None:
        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE instructors SET is_active = FALSE, updated_at = NOW() WHERE id = $1",
                instructor_id,
            )

    # ── Availability ────────────────────────────────────────────────

    async def set_availability(self, instructor_id: str, slots: list[dict]) -> list[dict]:
        """Replace all recurring availability for an instructor."""
        async with get_tenant_db() as db:
            # Remove existing recurring slots
            await db.execute(
                "DELETE FROM instructor_availability WHERE instructor_id = $1 AND is_recurring = TRUE",
                instructor_id,
            )
            created = []
            for slot in slots:
                slot_id = str(uuid.uuid4())
                await db.execute(
                    """
                    INSERT INTO instructor_availability
                        (id, instructor_id, day_of_week, start_time, end_time,
                         is_recurring, specific_date, is_blocked)
                    VALUES ($1, $2, $3, $4::time, $5::time, $6, $7, $8)
                    """,
                    slot_id, instructor_id, slot["day_of_week"],
                    _parse_time(slot["start_time"]), _parse_time(slot["end_time"]),
                    slot.get("is_recurring", True), slot.get("specific_date"),
                    slot.get("is_blocked", False),
                )
                created.append({"id": slot_id, **slot})
            return created

    async def get_availability(self, instructor_id: str) -> list[dict]:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM instructor_availability
                WHERE instructor_id = $1
                ORDER BY day_of_week, start_time
                """,
                instructor_id,
            )
        return [dict(r) for r in rows]

    async def get_instructor_schedule(
        self, instructor_id: str, start: str, end: str
    ) -> list[dict]:
        """Get all sessions for an instructor in a date range."""
        from datetime import datetime as dt, timedelta

        start_dt = dt.fromisoformat(start) if isinstance(start, str) else start
        end_dt = dt.fromisoformat(end) if isinstance(end, str) else end
        # Pad range to catch sessions that cross UTC date boundaries
        start_dt = start_dt - timedelta(hours=12)
        end_dt = end_dt + timedelta(hours=12)

        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT cs.*, ct.name as class_type_name, ct.color,
                       r.name as room_name,
                       (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id AND status NOT IN ('cancelled', 'waitlisted')) as booked_count
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN rooms r ON r.id = cs.room_id
                WHERE (cs.instructor_id = $1 OR cs.substitute_instructor_id = $1)
                  AND cs.starts_at >= $2 AND cs.starts_at < $3
                  AND cs.status != 'cancelled'
                ORDER BY cs.starts_at
                """,
                instructor_id, start_dt, end_dt,
            )
        return [dict(r) for r in rows]
