"""AuraFlow — Scheduling Service

Class types, rooms, class series (recurring), and class sessions CRUD.
Uses tenant-scoped DB via get_tenant_db().
Integrates with Zoom for virtual class meetings.
"""
import uuid
from datetime import date, datetime, time, timedelta

from dateutil.rrule import rrulestr

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.integrations.zoom_service import ZoomService

_zoom_svc = ZoomService()

# Column whitelists for dynamic UPDATE queries
_CLASS_TYPE_UPDATE_COLS = {
    "name", "description", "duration_minutes", "color", "capacity",
    "level", "tags", "category", "image_url", "is_active",
}
_ROOM_UPDATE_COLS = {
    "name", "capacity", "color", "sort_order", "is_active",
}
_CLASS_SERIES_UPDATE_COLS = {
    "class_type_id", "instructor_id", "room_id", "title", "rrule",
    "start_time", "duration_minutes", "capacity", "waitlist_capacity",
    "effective_from", "effective_until", "timezone", "is_active",
    "is_virtual", "auto_record",
}
_CLASS_SESSION_UPDATE_COLS = {
    "class_type_id", "instructor_id", "room_id", "title", "description",
    "starts_at", "ends_at", "timezone", "capacity", "waitlist_capacity",
    "status", "notes", "substitute_instructor_id", "is_virtual",
    "auto_record", "is_community", "modality",
    "zoom_meeting_id", "zoom_join_url", "zoom_password",
    "cancellation_reason",
}

# Valid modality values; mirrors the CHECK constraint added in
# alembic a27_class_modality. Setting modality='virtual' or 'hybrid'
# implies is_virtual=True (a Zoom meeting will be created); 'in_studio'
# implies is_virtual=False.
_VALID_MODALITIES = ("in_studio", "virtual", "hybrid")


def _modality_to_is_virtual(modality: str | None, fallback_is_virtual: bool | None = None) -> tuple[str, bool]:
    """Reconcile modality + is_virtual. modality wins when set; otherwise
    derive from is_virtual (legacy clients). Returns (modality, is_virtual)."""
    if modality and modality in _VALID_MODALITIES:
        return modality, modality in ("virtual", "hybrid")
    if fallback_is_virtual is True:
        return "virtual", True
    if fallback_is_virtual is False:
        return "in_studio", False
    return "in_studio", False


class SchedulingService:

    # ── Class Types ──────────────────────────────────────────────────

    async def create_class_type(self, studio_id: str, data: dict) -> dict:
        ct_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO class_types
                    (id, studio_id, name, description, duration_minutes, color,
                     capacity, level, tags, category, image_url)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                ct_id, studio_id, data["name"], data.get("description"),
                data.get("duration_minutes", 60), data.get("color", "#4F46E5"),
                data.get("capacity", 20), data.get("level", "all_levels"),
                data.get("tags", []), data.get("category"), data.get("image_url"),
            )
            row = await db.fetchrow("SELECT * FROM class_types WHERE id = $1", ct_id)
        logger.info("Class type created", class_type_id=ct_id, name=data["name"])
        return dict(row)

    async def update_class_type(self, class_type_id: str, data: dict) -> dict:
        updates = {k: v for k, v in data.items() if v is not None and k in _CLASS_TYPE_UPDATE_COLS}
        if not updates:
            async with get_tenant_db() as db:
                row = await db.fetchrow("SELECT * FROM class_types WHERE id = $1", class_type_id)
            return dict(row) if row else None

        set_clauses = []
        params = []
        for i, (col, val) in enumerate(updates.items(), start=1):
            set_clauses.append(f"{col} = ${i}")
            params.append(val)
        params.append(class_type_id)

        async with get_tenant_db() as db:
            await db.execute(
                f"UPDATE class_types SET {', '.join(set_clauses)} WHERE id = ${len(params)}",
                *params,
            )
            row = await db.fetchrow("SELECT * FROM class_types WHERE id = $1", class_type_id)
        return dict(row) if row else None

    async def list_class_types(self, studio_id: str, active_only: bool = True) -> list[dict]:
        query = "SELECT * FROM class_types WHERE studio_id = $1"
        if active_only:
            query += " AND is_active = TRUE"
        query += " ORDER BY name"
        async with get_tenant_db() as db:
            rows = await db.fetch(query, studio_id)
        return [dict(r) for r in rows]

    async def get_class_type(self, class_type_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow("SELECT * FROM class_types WHERE id = $1", class_type_id)
        return dict(row) if row else None

    async def deactivate_class_type(self, class_type_id: str) -> None:
        async with get_tenant_db() as db:
            await db.execute(
                "UPDATE class_types SET is_active = FALSE WHERE id = $1", class_type_id
            )

    # ── Rooms ────────────────────────────────────────────────────────

    async def create_room(self, studio_id: str, data: dict) -> dict:
        room_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO rooms (id, studio_id, name, capacity, color, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                room_id, studio_id, data["name"],
                data.get("capacity"), data.get("color", "#6366F1"),
                data.get("sort_order", 0),
            )
            row = await db.fetchrow("SELECT * FROM rooms WHERE id = $1", room_id)
        return dict(row)

    async def update_room(self, room_id: str, data: dict) -> dict | None:
        updates = {k: v for k, v in data.items() if v is not None and k in _ROOM_UPDATE_COLS}
        if not updates:
            async with get_tenant_db() as db:
                row = await db.fetchrow("SELECT * FROM rooms WHERE id = $1", room_id)
            return dict(row) if row else None

        set_clauses = []
        params = []
        for i, (col, val) in enumerate(updates.items(), start=1):
            set_clauses.append(f"{col} = ${i}")
            params.append(val)
        params.append(room_id)

        async with get_tenant_db() as db:
            await db.execute(
                f"UPDATE rooms SET {', '.join(set_clauses)} WHERE id = ${len(params)}",
                *params,
            )
            row = await db.fetchrow("SELECT * FROM rooms WHERE id = $1", room_id)
        return dict(row) if row else None

    async def list_rooms(self, studio_id: str) -> list[dict]:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                "SELECT * FROM rooms WHERE studio_id = $1 AND is_active = TRUE ORDER BY sort_order, name",
                studio_id,
            )
        return [dict(r) for r in rows]

    async def delete_room(self, room_id: str) -> None:
        async with get_tenant_db() as db:
            await db.execute("UPDATE rooms SET is_active = FALSE WHERE id = $1", room_id)

    # ── Class Series (recurring schedules) ───────────────────────────

    async def create_series(self, data: dict) -> dict:
        series_id = str(uuid.uuid4())
        effective_from = (
            data["effective_from"]
            if isinstance(data["effective_from"], date)
            else date.fromisoformat(data["effective_from"])
        )
        effective_until = None
        if data.get("effective_until"):
            effective_until = (
                data["effective_until"]
                if isinstance(data["effective_until"], date)
                else date.fromisoformat(data["effective_until"])
            )
        start_time_val = (
            data["start_time"]
            if isinstance(data["start_time"], time)
            else time.fromisoformat(data["start_time"])
        )

        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO class_series
                    (id, studio_id, class_type_id, instructor_id, room_id,
                     title, rrule, start_time, duration_minutes, capacity,
                     waitlist_capacity, effective_from, effective_until, timezone,
                     is_virtual, auto_record)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                """,
                series_id, data["studio_id"], data["class_type_id"],
                data.get("instructor_id"), data.get("room_id"),
                data["title"], data["rrule"], start_time_val,
                data["duration_minutes"], data.get("capacity"),
                data.get("waitlist_capacity", 10),
                effective_from, effective_until,
                data.get("timezone", "America/Los_Angeles"),
                data.get("is_virtual", False),
                data.get("auto_record", False),
            )
            row = await db.fetchrow("SELECT * FROM class_series WHERE id = $1", series_id)

        logger.info("Class series created", series_id=series_id, title=data["title"])
        return dict(row)

    async def update_series(self, series_id: str, data: dict) -> dict | None:
        updates = {}
        for k, v in data.items():
            if v is not None and k in _CLASS_SERIES_UPDATE_COLS:
                if k == "effective_from" and isinstance(v, str):
                    v = date.fromisoformat(v)
                elif k == "effective_until" and isinstance(v, str):
                    v = date.fromisoformat(v)
                elif k == "start_time" and isinstance(v, str):
                    v = time.fromisoformat(v)
                updates[k] = v

        if not updates:
            async with get_tenant_db() as db:
                row = await db.fetchrow("SELECT * FROM class_series WHERE id = $1", series_id)
            return dict(row) if row else None

        set_clauses = []
        params = []
        for i, (col, val) in enumerate(updates.items(), start=1):
            set_clauses.append(f"{col} = ${i}")
            params.append(val)
        params.append(series_id)

        async with get_tenant_db() as db:
            await db.execute(
                f"UPDATE class_series SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = ${len(params)}",
                *params,
            )
            row = await db.fetchrow("SELECT * FROM class_series WHERE id = $1", series_id)
        return dict(row) if row else None

    async def get_series(self, series_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow("SELECT * FROM class_series WHERE id = $1", series_id)
        return dict(row) if row else None

    async def list_series(self, studio_id: str) -> list[dict]:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                "SELECT * FROM class_series WHERE studio_id = $1 AND is_active = TRUE ORDER BY title",
                studio_id,
            )
        return [dict(r) for r in rows]

    async def delete_series(self, series_id: str, delete_future_sessions: bool = True, org_id: str | None = None) -> None:
        async with get_tenant_db() as db:
            if delete_future_sessions:
                # Get Zoom meeting IDs for future sessions before cancelling
                if org_id:
                    zoom_sessions = await db.fetch(
                        """
                        SELECT zoom_meeting_id FROM class_sessions
                        WHERE series_id = $1 AND starts_at > NOW() AND status = 'scheduled'
                          AND zoom_meeting_id IS NOT NULL
                        """,
                        series_id,
                    )
                    for row in zoom_sessions:
                        try:
                            await _zoom_svc.delete_meeting(org_id, row["zoom_meeting_id"])
                        except Exception as e:
                            logger.warning("Failed to delete Zoom meeting on series delete", meeting_id=row["zoom_meeting_id"], error=str(e))

                await db.execute(
                    """
                    UPDATE class_sessions SET status = 'cancelled', cancellation_reason = 'Series deleted'
                    WHERE series_id = $1 AND starts_at > NOW() AND status = 'scheduled'
                    """,
                    series_id,
                )
            await db.execute(
                "UPDATE class_series SET is_active = FALSE WHERE id = $1", series_id
            )
        logger.info("Class series deleted", series_id=series_id)

    async def expand_series(self, series_id: str, until_date: date, org_id: str | None = None) -> list[dict]:
        """Expand RRULE into individual class_sessions up to until_date."""
        async with get_tenant_db() as db:
            series = await db.fetchrow("SELECT * FROM class_series WHERE id = $1", series_id)
            if not series:
                raise ValueError("Series not found")

            dtstart = datetime.combine(series["effective_from"], series["start_time"])
            rule = rrulestr(series["rrule"], dtstart=dtstart)

            existing = await db.fetch(
                "SELECT starts_at::date as session_date FROM class_sessions WHERE series_id = $1",
                series_id,
            )
            existing_dates = {r["session_date"] for r in existing}

            # Get class type for default capacity
            ct = await db.fetchrow(
                "SELECT capacity FROM class_types WHERE id = $1", str(series["class_type_id"])
            )
            default_capacity = ct["capacity"] if ct else 20

            is_virtual = series.get("is_virtual", False)
            auto_record = series.get("auto_record", False)

            # Get instructor zoom_user_id if virtual
            instructor_zoom_user_id = None
            if is_virtual and series["instructor_id"]:
                instructor = await db.fetchrow(
                    "SELECT zoom_user_id FROM instructors WHERE id = $1",
                    str(series["instructor_id"]),
                )
                if instructor:
                    instructor_zoom_user_id = instructor.get("zoom_user_id")

            created = []
            for dt in rule:
                if dt.date() > until_date:
                    break
                if series["effective_until"] and dt.date() > series["effective_until"]:
                    break
                if dt.date() < date.today():
                    continue
                if dt.date() in existing_dates:
                    continue

                ends_at = dt + timedelta(minutes=series["duration_minutes"])
                session_id = str(uuid.uuid4())

                # Create Zoom meeting if virtual
                zoom_meeting_id = None
                zoom_join_url = None
                zoom_password = None
                if is_virtual and org_id:
                    try:
                        meeting = await _zoom_svc.create_meeting(
                            org_id=org_id,
                            topic=series["title"] or "Class Session",
                            start_time=dt.isoformat(),
                            duration_minutes=series["duration_minutes"],
                            instructor_zoom_user_id=instructor_zoom_user_id,
                            auto_record=auto_record,
                        )
                        zoom_meeting_id = meeting["meeting_id"]
                        zoom_join_url = meeting["join_url"]
                        zoom_password = meeting["password"]
                    except Exception as e:
                        logger.warning("Failed to create Zoom meeting for series session", error=str(e))

                await db.execute(
                    """
                    INSERT INTO class_sessions
                        (id, studio_id, class_type_id, instructor_id, room_id,
                         series_id, title, starts_at, ends_at, timezone,
                         capacity, waitlist_capacity,
                         is_virtual, auto_record,
                         zoom_meeting_id, zoom_join_url, zoom_password)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                            $13, $14, $15, $16, $17)
                    """,
                    session_id, str(series["studio_id"]),
                    str(series["class_type_id"]),
                    str(series["instructor_id"]) if series["instructor_id"] else None,
                    str(series["room_id"]) if series["room_id"] else None,
                    series_id, series["title"], dt, ends_at,
                    series["timezone"],
                    series["capacity"] or default_capacity,
                    series["waitlist_capacity"],
                    is_virtual, auto_record,
                    zoom_meeting_id, zoom_join_url, zoom_password,
                )
                created.append({"id": session_id, "starts_at": dt.isoformat()})

            logger.info("Series expanded", series_id=series_id, sessions_created=len(created))
            return created

    # ── Class Sessions ───────────────────────────────────────────────

    async def create_session(self, data: dict, org_id: str | None = None) -> dict:
        session_id = str(uuid.uuid4())
        starts_at = (
            data["starts_at"]
            if isinstance(data["starts_at"], datetime)
            else datetime.fromisoformat(data["starts_at"])
        )
        ends_at = (
            data["ends_at"]
            if isinstance(data["ends_at"], datetime)
            else datetime.fromisoformat(data["ends_at"])
        )
        modality, is_virtual = _modality_to_is_virtual(
            data.get("modality"), data.get("is_virtual"),
        )
        auto_record = data.get("auto_record", False)

        # Create Zoom meeting if virtual
        zoom_meeting_id = None
        zoom_join_url = None
        zoom_password = None
        if is_virtual and org_id:
            try:
                # Get instructor zoom_user_id
                instructor_zoom_user_id = None
                if data.get("instructor_id"):
                    async with get_tenant_db() as db:
                        instructor = await db.fetchrow(
                            "SELECT zoom_user_id FROM instructors WHERE id = $1",
                            data["instructor_id"],
                        )
                        if instructor:
                            instructor_zoom_user_id = instructor.get("zoom_user_id")

                duration = int((ends_at - starts_at).total_seconds() / 60)
                meeting = await _zoom_svc.create_meeting(
                    org_id=org_id,
                    topic=data["title"],
                    start_time=starts_at.isoformat(),
                    duration_minutes=duration,
                    instructor_zoom_user_id=instructor_zoom_user_id,
                    auto_record=auto_record,
                )
                zoom_meeting_id = meeting["meeting_id"]
                zoom_join_url = meeting["join_url"]
                zoom_password = meeting["password"]
            except Exception as e:
                logger.warning("Failed to create Zoom meeting", error=str(e))

        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO class_sessions
                    (id, studio_id, class_type_id, instructor_id, room_id,
                     title, description, starts_at, ends_at, timezone,
                     capacity, waitlist_capacity, notes,
                     is_virtual, is_community, modality, auto_record,
                     zoom_meeting_id, zoom_join_url, zoom_password)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                        $14, $15, $16, $17, $18, $19, $20)
                """,
                session_id, data["studio_id"], data["class_type_id"],
                data.get("instructor_id"), data.get("room_id"),
                data["title"], data.get("description"),
                starts_at, ends_at,
                data.get("timezone", "America/Los_Angeles"),
                data.get("capacity", 20), data.get("waitlist_capacity", 10),
                data.get("notes"),
                is_virtual, data.get("is_community", False), modality, auto_record,
                zoom_meeting_id, zoom_join_url, zoom_password,
            )
            row = await db.fetchrow("SELECT * FROM class_sessions WHERE id = $1", session_id)
        return dict(row)

    async def update_session(self, session_id: str, data: dict, org_id: str | None = None) -> dict | None:
        updates = {}
        for k, v in data.items():
            if v is not None and k in _CLASS_SESSION_UPDATE_COLS:
                if k in ("starts_at", "ends_at") and isinstance(v, str):
                    v = datetime.fromisoformat(v)
                updates[k] = v

        # Reconcile modality + is_virtual: modality is the source of truth
        # for access semantics, is_virtual derives from it. If only one is
        # provided, sync the other.
        if "modality" in updates and updates["modality"] in _VALID_MODALITIES:
            updates["is_virtual"] = updates["modality"] in ("virtual", "hybrid")
        elif "is_virtual" in updates and "modality" not in updates:
            updates["modality"] = "virtual" if updates["is_virtual"] else "in_studio"

        if not updates:
            async with get_tenant_db() as db:
                row = await db.fetchrow("SELECT * FROM class_sessions WHERE id = $1", session_id)
            return dict(row) if row else None

        # Fetch current session to check Zoom state changes
        async with get_tenant_db() as db:
            current = await db.fetchrow("SELECT * FROM class_sessions WHERE id = $1", session_id)
            if not current:
                return None

        was_virtual = current.get("is_virtual", False)
        becoming_virtual = updates.get("is_virtual", was_virtual)
        had_meeting = current.get("zoom_meeting_id")

        # Handle Zoom meeting lifecycle
        if org_id:
            if was_virtual and not becoming_virtual and had_meeting:
                # Turning off virtual — delete Zoom meeting
                try:
                    await _zoom_svc.delete_meeting(org_id, had_meeting)
                except Exception as e:
                    logger.warning("Failed to delete Zoom meeting on virtual toggle off", error=str(e))
                updates["zoom_meeting_id"] = None
                updates["zoom_join_url"] = None
                updates["zoom_password"] = None

            elif not was_virtual and becoming_virtual:
                # Turning on virtual — create Zoom meeting
                try:
                    instructor_zoom_user_id = None
                    inst_id = updates.get("instructor_id") or (str(current["instructor_id"]) if current["instructor_id"] else None)
                    if inst_id:
                        async with get_tenant_db() as db:
                            instructor = await db.fetchrow(
                                "SELECT zoom_user_id FROM instructors WHERE id = $1", inst_id
                            )
                            if instructor:
                                instructor_zoom_user_id = instructor.get("zoom_user_id")

                    starts_at = updates.get("starts_at", current["starts_at"])
                    ends_at = updates.get("ends_at", current["ends_at"])
                    duration = int((ends_at - starts_at).total_seconds() / 60)
                    auto_record = updates.get("auto_record", current.get("auto_record", False))

                    meeting = await _zoom_svc.create_meeting(
                        org_id=org_id,
                        topic=updates.get("title", current["title"]) or "Class Session",
                        start_time=starts_at.isoformat() if isinstance(starts_at, datetime) else starts_at,
                        duration_minutes=duration,
                        instructor_zoom_user_id=instructor_zoom_user_id,
                        auto_record=auto_record,
                    )
                    updates["zoom_meeting_id"] = meeting["meeting_id"]
                    updates["zoom_join_url"] = meeting["join_url"]
                    updates["zoom_password"] = meeting["password"]
                except Exception as e:
                    logger.warning("Failed to create Zoom meeting on virtual toggle on", error=str(e))

            elif was_virtual and becoming_virtual and had_meeting:
                # Still virtual — update meeting if time or title changed
                time_changed = "starts_at" in updates or "ends_at" in updates
                title_changed = "title" in updates
                if time_changed or title_changed:
                    try:
                        update_data = {}
                        if title_changed:
                            update_data["topic"] = updates["title"]
                        if time_changed:
                            starts_at = updates.get("starts_at", current["starts_at"])
                            ends_at = updates.get("ends_at", current["ends_at"])
                            update_data["start_time"] = starts_at.isoformat() if isinstance(starts_at, datetime) else starts_at
                            update_data["duration"] = int((ends_at - starts_at).total_seconds() / 60)
                        await _zoom_svc.update_meeting(org_id, had_meeting, update_data)
                    except Exception as e:
                        logger.warning("Failed to update Zoom meeting", error=str(e))

        set_clauses = []
        params = []
        for i, (col, val) in enumerate(updates.items(), start=1):
            set_clauses.append(f"{col} = ${i}")
            params.append(val)
        params.append(session_id)

        async with get_tenant_db() as db:
            await db.execute(
                f"UPDATE class_sessions SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = ${len(params)}",
                *params,
            )
            row = await db.fetchrow("SELECT * FROM class_sessions WHERE id = $1", session_id)
        return dict(row) if row else None

    async def get_session(self, session_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT cs.*, ct.name as class_type_name, ct.color,
                       i.display_name as instructor_name,
                       r.name as room_name,
                       (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id AND status = 'confirmed') as booked_count,
                       (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id AND status = 'waitlisted') as waitlist_count
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                LEFT JOIN rooms r ON r.id = cs.room_id
                WHERE cs.id = $1
                """,
                session_id,
            )
        return dict(row) if row else None

    async def list_sessions(
        self,
        studio_id: str,
        start: datetime,
        end: datetime,
        instructor_id: str | None = None,
        room_id: str | None = None,
    ) -> list[dict]:
        query = """
            SELECT cs.*, ct.name as class_type_name, ct.color,
                   i.display_name as instructor_name,
                   r.name as room_name,
                   (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id AND status = 'confirmed') as booked_count,
                   (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id AND status = 'waitlisted') as waitlist_count
            FROM class_sessions cs
            LEFT JOIN class_types ct ON ct.id = cs.class_type_id
            LEFT JOIN instructors i ON i.id = cs.instructor_id
            LEFT JOIN rooms r ON r.id = cs.room_id
            WHERE cs.studio_id = $1 AND cs.starts_at >= $2 AND cs.starts_at < $3
              AND cs.status != 'cancelled'
        """
        params = [studio_id, start, end]
        idx = 4

        if instructor_id:
            query += f" AND cs.instructor_id = ${idx}"
            params.append(instructor_id)
            idx += 1
        if room_id:
            query += f" AND cs.room_id = ${idx}"
            params.append(room_id)
            idx += 1

        query += " ORDER BY cs.starts_at"

        async with get_tenant_db() as db:
            rows = await db.fetch(query, *params)
        return [dict(r) for r in rows]

    async def cancel_session(self, session_id: str, reason: str | None = None, org_id: str | None = None) -> dict | None:
        async with get_tenant_db() as db:
            # Get session first to check for Zoom meeting
            session = await db.fetchrow("SELECT * FROM class_sessions WHERE id = $1", session_id)
            if not session:
                return None

            await db.execute(
                """
                UPDATE class_sessions
                SET status = 'cancelled', cancellation_reason = $2, updated_at = NOW()
                WHERE id = $1 AND status = 'scheduled'
                """,
                session_id, reason,
            )
            row = await db.fetchrow("SELECT * FROM class_sessions WHERE id = $1", session_id)

            # Cascade: cancel every active booking on this session and
            # refund their pack credits. Without this the session shows
            # cancelled but members keep "confirmed" rows attached and
            # their credits stay deducted — the bug Don hit when an
            # instructor called out sick.
            cascaded = await db.fetch(
                """
                UPDATE bookings
                SET status = 'cancelled',
                    cancelled_at = NOW(),
                    cancellation_reason = COALESCE(
                        $2, 'class cancelled by studio'
                    )
                WHERE class_session_id = $1
                  AND status IN ('confirmed', 'waitlisted')
                RETURNING id, member_id, membership_id, status
                """,
                session_id, reason,
            )

            # Restore credits on every booking that consumed one. We
            # only refund pack credits — unlimited memberships don't
            # accumulate so there's nothing to give back.
            for b in cascaded:
                if b.get("membership_id"):
                    await db.execute(
                        """
                        UPDATE member_memberships
                        SET classes_remaining = classes_remaining + 1, updated_at = NOW()
                        WHERE id = $1 AND classes_remaining IS NOT NULL
                        """,
                        str(b["membership_id"]),
                    )

            # Only delete the Zoom meeting if no OTHER scheduled session is
            # still pointing at it. Historically the importer reused a single
            # zoom_meeting_id across every session of a recurring class, so
            # blindly deleting on a one-off cancel wiped the meeting for
            # ~90 future sessions and left them stranded with a dead ID.
            zid = session.get("zoom_meeting_id")
            other_users = 0
            if zid:
                other_users = await db.fetchval(
                    """
                    SELECT COUNT(*) FROM class_sessions
                    WHERE zoom_meeting_id = $1
                      AND id <> $2
                      AND status = 'scheduled'
                    """,
                    zid, session_id,
                )
                # Detach this session from the shared meeting either way so
                # zoom_auto_create can refill it if it ever gets re-scheduled.
                await db.execute(
                    "UPDATE class_sessions "
                    "SET zoom_meeting_id = NULL, zoom_join_url = NULL, zoom_password = NULL "
                    "WHERE id = $1",
                    session_id,
                )

        if zid and org_id and other_users == 0:
            try:
                await _zoom_svc.delete_meeting(org_id, zid)
            except Exception as e:
                logger.warning("Failed to delete Zoom meeting on cancel", error=str(e))

        # Notify each cancelled member out-of-band. Best-effort —
        # email failures shouldn't block the cancellation.
        try:
            from app.services.scheduling.booking_service import BookingService
            booking_svc = BookingService()
            async with get_tenant_db() as db2:
                for b in cascaded:
                    try:
                        await booking_svc._send_booking_notifications(
                            db2, str(b["id"]), "cancelled",
                        )
                    except Exception as nerr:
                        logger.warning(
                            "Cascade cancel: notification failed",
                            booking_id=str(b["id"]), error=str(nerr),
                        )
        except Exception as e:
            logger.warning("Cascade cancel: notifier unavailable", error=str(e))

        logger.info(
            "Session cancelled",
            session_id=session_id,
            bookings_cascaded=len(cascaded),
            zoom_meeting_kept=bool(zid and other_users > 0),
            zoom_other_users=other_users,
        )
        return dict(row) if row else None
