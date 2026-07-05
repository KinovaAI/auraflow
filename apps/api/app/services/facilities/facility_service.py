"""AuraFlow — Facility Management Service

Rooms (enhanced), equipment tracking, maintenance requests,
and recurring cleaning/inspection schedules.
"""
import uuid
from datetime import datetime, timedelta, timezone, date

from app.core.logging import logger
from app.db.session import get_tenant_db


class FacilityService:

    # ── Enhanced Rooms ──────────────────────────────────────────────────

    async def list_rooms_with_details(self, studio_id: str) -> list[dict]:
        """List rooms enriched with equipment count and today's sessions."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT r.*,
                    COALESCE(eq.cnt, 0)  AS equipment_count,
                    COALESCE(cs.cnt, 0)  AS sessions_today
                FROM rooms r
                LEFT JOIN (
                    SELECT room_id, COUNT(*) AS cnt
                    FROM equipment WHERE is_active = TRUE
                    GROUP BY room_id
                ) eq ON eq.room_id = r.id
                LEFT JOIN (
                    SELECT room_id, COUNT(*) AS cnt
                    FROM class_sessions
                    WHERE starts_at::date = CURRENT_DATE
                      AND status != 'cancelled'
                    GROUP BY room_id
                ) cs ON cs.room_id = r.id
                WHERE r.studio_id = $1 AND r.is_active = TRUE
                ORDER BY r.sort_order, r.name
                """,
                studio_id,
            )
        return [_room_to_dict(r) for r in rows]

    async def get_room_detail(self, room_id: str) -> dict | None:
        """Get a single room with enrichment."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT r.*,
                    COALESCE(eq.cnt, 0)  AS equipment_count,
                    COALESCE(cs.cnt, 0)  AS sessions_today
                FROM rooms r
                LEFT JOIN (
                    SELECT room_id, COUNT(*) AS cnt
                    FROM equipment WHERE is_active = TRUE
                    GROUP BY room_id
                ) eq ON eq.room_id = r.id
                LEFT JOIN (
                    SELECT room_id, COUNT(*) AS cnt
                    FROM class_sessions
                    WHERE starts_at::date = CURRENT_DATE
                      AND status != 'cancelled'
                    GROUP BY room_id
                ) cs ON cs.room_id = r.id
                WHERE r.id = $1
                """,
                room_id,
            )
        return _room_to_dict(row) if row else None

    async def update_room_extended(self, room_id: str, data: dict) -> dict | None:
        """PATCH-style update for extended room fields."""
        allowed = {
            "description", "room_type", "amenities", "photo_url",
            "hourly_rate_cents", "max_classes_per_day", "floor_area_sqft",
            "setup_instructions", "is_bookable",
        }
        updates = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not updates:
            return await self.get_room_detail(room_id)

        set_clauses = []
        params = [room_id]
        idx = 2
        for key, val in updates.items():
            set_clauses.append(f"{key} = ${idx}")
            params.append(val)
            idx += 1
        set_clauses.append("updated_at = NOW()")

        async with get_tenant_db() as db:
            await db.execute(
                f"UPDATE rooms SET {', '.join(set_clauses)} WHERE id = $1",
                *params,
            )
        return await self.get_room_detail(room_id)

    async def get_room_availability(
        self, room_id: str, date_str: str
    ) -> list[dict]:
        """Get class sessions scheduled in a room on a given date."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT cs.id AS session_id, cs.title,
                       cs.starts_at, cs.ends_at,
                       i.display_name AS instructor_name
                FROM class_sessions cs
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE cs.room_id = $1
                  AND cs.starts_at::date = $2::date
                  AND cs.status != 'cancelled'
                ORDER BY cs.starts_at
                """,
                room_id,
                date_str,
            )
        return [_availability_to_dict(r) for r in rows]

    # ── Equipment ───────────────────────────────────────────────────────

    async def list_equipment(
        self,
        studio_id: str,
        room_id: str | None = None,
        category: str | None = None,
        condition: str | None = None,
    ) -> list[dict]:
        """List equipment with optional filters."""
        conditions = ["e.studio_id = $1", "e.is_active = TRUE"]
        params: list = [studio_id]
        idx = 2

        if room_id:
            conditions.append(f"e.room_id = ${idx}")
            params.append(room_id)
            idx += 1
        if category:
            conditions.append(f"e.category = ${idx}")
            params.append(category)
            idx += 1
        if condition:
            conditions.append(f"e.condition = ${idx}")
            params.append(condition)
            idx += 1

        where = " AND ".join(conditions)

        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"""
                SELECT e.*, r.name AS room_name
                FROM equipment e
                LEFT JOIN rooms r ON r.id = e.room_id
                WHERE {where}
                ORDER BY e.category, e.name
                """,
                *params,
            )
        return [_equipment_to_dict(r) for r in rows]

    async def get_equipment(self, equipment_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT e.*, r.name AS room_name
                FROM equipment e
                LEFT JOIN rooms r ON r.id = e.room_id
                WHERE e.id = $1
                """,
                equipment_id,
            )
        return _equipment_to_dict(row) if row else None

    async def create_equipment(self, data: dict) -> dict:
        eid = str(uuid.uuid4())
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO equipment
                    (id, studio_id, room_id, name, category, description,
                     quantity, purchase_date, purchase_cost_cents, condition,
                     warranty_expiry, serial_number, photo_url, notes)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                """,
                eid,
                data["studio_id"],
                data.get("room_id"),
                data["name"],
                data.get("category", "props"),
                data.get("description"),
                data.get("quantity", 1),
                data.get("purchase_date"),
                data.get("purchase_cost_cents"),
                data.get("condition", "good"),
                data.get("warranty_expiry"),
                data.get("serial_number"),
                data.get("photo_url"),
                data.get("notes"),
            )
        logger.info("Equipment created", equipment_id=eid, name=data["name"])
        return await self.get_equipment(eid)

    async def update_equipment(self, equipment_id: str, data: dict) -> dict | None:
        allowed = {
            "room_id", "name", "category", "description", "quantity",
            "condition", "warranty_expiry", "serial_number", "photo_url", "notes",
        }
        updates = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not updates:
            return await self.get_equipment(equipment_id)

        set_clauses = []
        params = [equipment_id]
        idx = 2
        for key, val in updates.items():
            set_clauses.append(f"{key} = ${idx}")
            params.append(val)
            idx += 1
        set_clauses.append("updated_at = NOW()")

        async with get_tenant_db() as db:
            await db.execute(
                f"UPDATE equipment SET {', '.join(set_clauses)} WHERE id = $1",
                *params,
            )
        return await self.get_equipment(equipment_id)

    async def delete_equipment(self, equipment_id: str) -> bool:
        async with get_tenant_db() as db:
            result = await db.execute(
                "UPDATE equipment SET is_active = FALSE, updated_at = NOW() WHERE id = $1",
                equipment_id,
            )
        return "UPDATE 1" in result

    # ── Maintenance Requests ────────────────────────────────────────────

    async def list_maintenance_requests(
        self,
        studio_id: str,
        status: str | None = None,
        priority: str | None = None,
    ) -> list[dict]:
        conditions = ["m.studio_id = $1"]
        params: list = [studio_id]
        idx = 2

        if status:
            conditions.append(f"m.status = ${idx}")
            params.append(status)
            idx += 1
        if priority:
            conditions.append(f"m.priority = ${idx}")
            params.append(priority)
            idx += 1

        where = " AND ".join(conditions)

        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"""
                SELECT m.*, r.name AS room_name, e.name AS equipment_name
                FROM maintenance_requests m
                LEFT JOIN rooms r ON r.id = m.room_id
                LEFT JOIN equipment e ON e.id = m.equipment_id
                WHERE {where}
                ORDER BY
                    CASE m.priority
                        WHEN 'urgent' THEN 0 WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2 ELSE 3 END,
                    m.created_at DESC
                """,
                *params,
            )
        return [_maintenance_to_dict(r) for r in rows]

    async def get_maintenance_request(self, request_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT m.*, r.name AS room_name, e.name AS equipment_name
                FROM maintenance_requests m
                LEFT JOIN rooms r ON r.id = m.room_id
                LEFT JOIN equipment e ON e.id = m.equipment_id
                WHERE m.id = $1
                """,
                request_id,
            )
        return _maintenance_to_dict(row) if row else None

    async def create_maintenance_request(self, data: dict) -> dict:
        mid = str(uuid.uuid4())
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO maintenance_requests
                    (id, studio_id, room_id, equipment_id, title, description,
                     priority, category, requested_by, assigned_to,
                     estimated_cost_cents, scheduled_date)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                """,
                mid,
                data["studio_id"],
                data.get("room_id"),
                data.get("equipment_id"),
                data["title"],
                data.get("description"),
                data.get("priority", "medium"),
                data.get("category", "repair"),
                data.get("requested_by"),
                data.get("assigned_to"),
                data.get("estimated_cost_cents"),
                data.get("scheduled_date"),
            )
        logger.info("Maintenance request created", request_id=mid, title=data["title"])
        return await self.get_maintenance_request(mid)

    async def update_maintenance_request(
        self, request_id: str, data: dict
    ) -> dict | None:
        allowed = {
            "title", "description", "priority", "status", "category",
            "assigned_to", "estimated_cost_cents", "actual_cost_cents",
            "scheduled_date", "completion_notes",
        }
        updates = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not updates:
            return await self.get_maintenance_request(request_id)

        # Auto-set completed_at when status becomes 'completed'
        if updates.get("status") == "completed":
            updates["completed_at"] = datetime.now(timezone.utc)

        set_clauses = []
        params = [request_id]
        idx = 2
        for key, val in updates.items():
            set_clauses.append(f"{key} = ${idx}")
            params.append(val)
            idx += 1
        set_clauses.append("updated_at = NOW()")

        async with get_tenant_db() as db:
            await db.execute(
                f"UPDATE maintenance_requests SET {', '.join(set_clauses)} WHERE id = $1",
                *params,
            )
        return await self.get_maintenance_request(request_id)

    async def get_maintenance_stats(self, studio_id: str) -> dict:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'open')         AS open,
                    COUNT(*) FILTER (WHERE status = 'in_progress')  AS in_progress,
                    COUNT(*) FILTER (
                        WHERE status = 'completed'
                        AND completed_at >= date_trunc('month', CURRENT_DATE)
                    ) AS completed_this_month
                FROM maintenance_requests
                WHERE studio_id = $1
                """,
                studio_id,
            )
            overdue_row = await db.fetchrow(
                """
                SELECT COUNT(*) AS cnt
                FROM facility_schedules
                WHERE studio_id = $1 AND is_active = TRUE
                  AND next_due_at < NOW()
                """,
                studio_id,
            )
        return {
            "open": row["open"],
            "in_progress": row["in_progress"],
            "completed_this_month": row["completed_this_month"],
            "overdue_schedules": overdue_row["cnt"],
        }

    # ── Facility Schedules ──────────────────────────────────────────────

    async def list_schedules(
        self,
        studio_id: str,
        schedule_type: str | None = None,
        overdue_only: bool = False,
    ) -> list[dict]:
        conditions = ["s.studio_id = $1", "s.is_active = TRUE"]
        params: list = [studio_id]
        idx = 2

        if schedule_type:
            conditions.append(f"s.schedule_type = ${idx}")
            params.append(schedule_type)
            idx += 1
        if overdue_only:
            conditions.append("s.next_due_at < NOW()")

        where = " AND ".join(conditions)

        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"""
                SELECT s.*, r.name AS room_name, e.name AS equipment_name
                FROM facility_schedules s
                LEFT JOIN rooms r ON r.id = s.room_id
                LEFT JOIN equipment e ON e.id = s.equipment_id
                WHERE {where}
                ORDER BY s.next_due_at NULLS LAST, s.title
                """,
                *params,
            )
        return [_schedule_to_dict(r) for r in rows]

    async def get_schedule(self, schedule_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT s.*, r.name AS room_name, e.name AS equipment_name
                FROM facility_schedules s
                LEFT JOIN rooms r ON r.id = s.room_id
                LEFT JOIN equipment e ON e.id = s.equipment_id
                WHERE s.id = $1
                """,
                schedule_id,
            )
        return _schedule_to_dict(row) if row else None

    async def create_schedule(self, data: dict) -> dict:
        sid = str(uuid.uuid4())
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO facility_schedules
                    (id, studio_id, room_id, equipment_id, schedule_type,
                     title, description, rrule, assigned_to, next_due_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                """,
                sid,
                data["studio_id"],
                data.get("room_id"),
                data.get("equipment_id"),
                data.get("schedule_type", "cleaning"),
                data["title"],
                data.get("description"),
                data.get("rrule"),
                data.get("assigned_to"),
                data.get("next_due_at"),
            )
        logger.info("Facility schedule created", schedule_id=sid, title=data["title"])
        return await self.get_schedule(sid)

    async def update_schedule(self, schedule_id: str, data: dict) -> dict | None:
        allowed = {
            "title", "description", "rrule", "assigned_to",
            "next_due_at", "is_active",
        }
        updates = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not updates:
            return await self.get_schedule(schedule_id)

        set_clauses = []
        params = [schedule_id]
        idx = 2
        for key, val in updates.items():
            set_clauses.append(f"{key} = ${idx}")
            params.append(val)
            idx += 1
        set_clauses.append("updated_at = NOW()")

        async with get_tenant_db() as db:
            await db.execute(
                f"UPDATE facility_schedules SET {', '.join(set_clauses)} WHERE id = $1",
                *params,
            )
        return await self.get_schedule(schedule_id)

    async def delete_schedule(self, schedule_id: str) -> bool:
        async with get_tenant_db() as db:
            result = await db.execute(
                "UPDATE facility_schedules SET is_active = FALSE, updated_at = NOW() WHERE id = $1",
                schedule_id,
            )
        return "UPDATE 1" in result

    async def complete_schedule(
        self,
        schedule_id: str,
        completed_by: str | None = None,
        notes: str | None = None,
        photos: list | None = None,
    ) -> dict:
        """Record a completion and bump next_due_at based on rrule interval."""
        import json

        completion_id = str(uuid.uuid4())
        photos_json = json.dumps(photos or [])

        async with get_tenant_db() as db:
            # Insert completion record
            await db.execute(
                """
                INSERT INTO facility_schedule_completions
                    (id, schedule_id, completed_by, notes, photos)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                """,
                completion_id,
                schedule_id,
                completed_by,
                notes,
                photos_json,
            )

            # Get the schedule to compute next_due_at
            sched = await db.fetchrow(
                "SELECT rrule, next_due_at FROM facility_schedules WHERE id = $1",
                schedule_id,
            )
            next_due = _compute_next_due(sched["rrule"]) if sched else None

            await db.execute(
                """
                UPDATE facility_schedules
                SET last_completed_at = NOW(),
                    next_due_at = $2,
                    updated_at = NOW()
                WHERE id = $1
                """,
                schedule_id,
                next_due,
            )

        logger.info("Schedule completed", schedule_id=schedule_id)
        return await self.get_schedule(schedule_id)

    async def get_schedule_history(
        self, schedule_id: str, limit: int = 20
    ) -> list[dict]:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM facility_schedule_completions
                WHERE schedule_id = $1
                ORDER BY completed_at DESC
                LIMIT $2
                """,
                schedule_id,
                limit,
            )
        return [_completion_to_dict(r) for r in rows]

    async def get_overdue_tasks(self, studio_id: str) -> list[dict]:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT s.*, r.name AS room_name, e.name AS equipment_name
                FROM facility_schedules s
                LEFT JOIN rooms r ON r.id = s.room_id
                LEFT JOIN equipment e ON e.id = s.equipment_id
                WHERE s.studio_id = $1 AND s.is_active = TRUE
                  AND s.next_due_at < NOW()
                ORDER BY s.next_due_at
                """,
                studio_id,
            )
        return [_schedule_to_dict(r) for r in rows]


# ── Helpers ─────────────────────────────────────────────────────────────

def _compute_next_due(rrule: str | None) -> datetime | None:
    """Simple interval-based next_due_at from rrule string.

    Supports: FREQ=DAILY;INTERVAL=N, FREQ=WEEKLY;INTERVAL=N, FREQ=MONTHLY;INTERVAL=N
    Falls back to 7 days if rrule is missing or unparseable.
    """
    if not rrule:
        return datetime.now(timezone.utc) + timedelta(days=7)

    parts = {}
    for segment in rrule.upper().split(";"):
        if "=" in segment:
            k, v = segment.split("=", 1)
            parts[k] = v

    freq = parts.get("FREQ", "WEEKLY")
    interval = int(parts.get("INTERVAL", "1"))

    now = datetime.now(timezone.utc)
    if freq == "DAILY":
        return now + timedelta(days=interval)
    elif freq == "WEEKLY":
        return now + timedelta(weeks=interval)
    elif freq == "MONTHLY":
        return now + timedelta(days=30 * interval)
    return now + timedelta(days=7)


# ── Serialization ───────────────────────────────────────────────────────

def _room_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "studio_id"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


def _availability_to_dict(row) -> dict:
    d = dict(row)
    if d.get("session_id"):
        d["session_id"] = str(d["session_id"])
    for k in ("starts_at", "ends_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


def _equipment_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "studio_id", "room_id"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("purchase_date", "warranty_expiry"):
        if d.get(k):
            d[k] = d[k].isoformat()
    for k in ("created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


def _maintenance_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "studio_id", "room_id", "equipment_id", "requested_by"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("scheduled_date",):
        if d.get(k):
            d[k] = d[k].isoformat()
    for k in ("completed_at", "created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


def _schedule_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "studio_id", "room_id", "equipment_id"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("last_completed_at", "next_due_at", "created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


def _completion_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "schedule_id", "completed_by"):
        if d.get(k):
            d[k] = str(d[k])
    if d.get("completed_at"):
        d["completed_at"] = d["completed_at"].isoformat()
    return d
