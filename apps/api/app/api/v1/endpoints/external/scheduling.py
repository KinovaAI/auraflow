"""AuraFlow — External Scheduling Endpoints

Read-only class types and sessions for third-party schedule displays.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.dependencies.api_key_auth import get_api_key_context, require_api_scope
from app.db.session import get_tenant_db
from app.services.external.csv_export import export_csv

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt) if dt else None


def _session_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "title": row.get("title"),
        "class_type_name": row.get("class_type_name"),
        "class_type_id": str(row["class_type_id"]) if row.get("class_type_id") else None,
        "instructor_name": row.get("instructor_name"),
        "instructor_id": str(row["instructor_id"]) if row.get("instructor_id") else None,
        "room_name": row.get("room_name"),
        "starts_at": _fmt(row.get("starts_at")),
        "ends_at": _fmt(row.get("ends_at")),
        "capacity": row.get("capacity"),
        "booked_count": row.get("booked_count", 0),
        "waitlist_count": row.get("waitlist_count", 0),
        "status": row.get("status"),
        "is_virtual": row.get("is_virtual", False),
    }


# ── Class Types ──────────────────────────────────────────────────────────────

@router.get(
    "/class-types",
    dependencies=[Depends(require_api_scope("scheduling:read"))],
    summary="List class types",
)
async def list_class_types(
    ctx: dict = Depends(get_api_key_context),
):
    async with get_tenant_db() as db:
        rows = await db.fetch(
            "SELECT * FROM class_types WHERE is_active = TRUE ORDER BY name"
        )
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "description": r.get("description"),
            "duration_minutes": r.get("duration_minutes"),
            "capacity": r.get("capacity"),
            "level": r.get("level"),
            "category": r.get("category"),
            "color": r.get("color"),
        }
        for r in rows
    ]


# ── Sessions ─────────────────────────────────────────────────────────────────

_SESSION_CSV_COLS = [
    ("id", "ID"),
    ("title", "Title"),
    ("class_type_name", "Class Type"),
    ("instructor_name", "Instructor"),
    ("room_name", "Room"),
    ("starts_at", "Starts At"),
    ("ends_at", "Ends At"),
    ("capacity", "Capacity"),
    ("booked_count", "Booked"),
    ("waitlist_count", "Waitlisted"),
    ("status", "Status"),
]


@router.get(
    "/sessions/export.csv",
    dependencies=[Depends(require_api_scope("scheduling:read"))],
    summary="Export sessions as CSV",
)
async def export_sessions_csv(
    ctx: dict = Depends(get_api_key_context),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    rows = await _fetch_sessions(date_from, date_to)
    return export_csv([_session_dict(r) for r in rows], _SESSION_CSV_COLS, "sessions.csv")


@router.get(
    "/sessions",
    dependencies=[Depends(require_api_scope("scheduling:read"))],
    summary="List class sessions",
)
async def list_sessions(
    ctx: dict = Depends(get_api_key_context),
    date_from: Optional[str] = Query(None, description="ISO date or datetime"),
    date_to: Optional[str] = Query(None, description="ISO date or datetime"),
    class_type: Optional[str] = Query(None, description="Class type ID filter"),
):
    rows = await _fetch_sessions(date_from, date_to, class_type)
    return [_session_dict(r) for r in rows]


@router.get(
    "/upcoming-zoom-sessions",
    dependencies=[Depends(require_api_scope("scheduling:read"))],
    summary="Upcoming scheduled sessions with Zoom join info — for autostart programs",
)
async def list_upcoming_zoom_sessions(
    ctx: dict = Depends(get_api_key_context),
    window_minutes: int = Query(
        30, ge=1, le=720,
        description="How many minutes ahead to look. Default 30. Max 720 (12 hours).",
    ),
    include_started: bool = Query(
        False,
        description="If true, also include sessions that have already started but not yet ended (useful for late-start automation).",
    ),
):
    """Lightweight feed for an external Zoom-autostart program.

    Returns every `scheduled` class session whose `starts_at` falls within
    the next `window_minutes`, along with the Zoom meeting id, join URL,
    and meeting password. Only sessions that actually have a
    `zoom_join_url` populated are returned — sessions without Zoom info
    are silently filtered.

    Recommended poll cadence: every 5 minutes with `window_minutes=15` so
    your autostart program sees each meeting twice (at T-10 and T-5)
    and can decide when to fire. Idempotency is on the caller.

    Times are returned as RFC3339 UTC strings — convert to the local
    timezone yourself.
    """
    where = [
        "cs.status = 'scheduled'",
        "cs.zoom_join_url IS NOT NULL",
        "cs.zoom_join_url <> ''",
    ]
    if include_started:
        where.append("cs.ends_at >= NOW()")
        where.append("cs.starts_at <= NOW() + ($1::int || ' minutes')::interval")
    else:
        where.append("cs.starts_at >= NOW()")
        where.append("cs.starts_at <= NOW() + ($1::int || ' minutes')::interval")
    sql = f"""
        SELECT cs.id, cs.title,
               cs.starts_at, cs.ends_at,
               cs.zoom_meeting_id, cs.zoom_join_url, cs.zoom_password,
               cs.is_virtual, cs.modality,
               i.display_name AS instructor_name,
               ct.name AS class_type_name
          FROM class_sessions cs
          LEFT JOIN instructors i ON i.id = cs.instructor_id
          LEFT JOIN class_types ct ON ct.id = cs.class_type_id
         WHERE {' AND '.join(where)}
         ORDER BY cs.starts_at ASC
    """
    async with get_tenant_db() as db:
        rows = await db.fetch(sql, window_minutes)

    # Mint a fresh zoom_start_url for each session. start_url carries
    # the host's ZAK token and grants host privileges on join — exactly
    # what an autostart program needs to BE the host. Zoom only emits
    # it via the GET /meetings/{id} response and it expires in ~2 hours,
    # so it can't be stored; we fetch on demand.
    org_id = ctx.get("organization_id") or ctx.get("org_id")
    start_urls: dict[str, str | None] = {}
    if org_id:
        from app.services.integrations.zoom_service import ZoomService
        zoom_svc = ZoomService()
        for r in rows:
            mid = r["zoom_meeting_id"]
            if not mid:
                continue
            try:
                m = await zoom_svc.get_meeting(org_id, str(mid))
                start_urls[str(mid)] = m.get("start_url") if m else None
            except Exception:
                # Best effort — if Zoom is flaky, return the row
                # without start_url rather than failing the whole feed.
                start_urls[str(mid)] = None

    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "instructor_name": r["instructor_name"],
            "class_type_name": r["class_type_name"],
            "starts_at": r["starts_at"].isoformat() if r["starts_at"] else None,
            "ends_at": r["ends_at"].isoformat() if r["ends_at"] else None,
            "is_virtual": r["is_virtual"],
            "modality": r["modality"],
            "zoom_meeting_id": r["zoom_meeting_id"],
            "zoom_join_url": r["zoom_join_url"],
            "zoom_start_url": start_urls.get(str(r["zoom_meeting_id"])) if r["zoom_meeting_id"] else None,
            "zoom_password": r["zoom_password"],
        }
        for r in rows
    ]


@router.get(
    "/sessions/{session_id}",
    dependencies=[Depends(require_api_scope("scheduling:read"))],
    summary="Get session detail",
)
async def get_session(
    session_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            """
            SELECT cs.*, ct.name AS class_type_name, ct.color,
                   i.display_name AS instructor_name,
                   r.name AS room_name,
                   (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id
                       AND status = 'confirmed') AS booked_count,
                   (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id
                       AND status = 'waitlisted') AS waitlist_count
            FROM class_sessions cs
            LEFT JOIN class_types ct ON ct.id = cs.class_type_id
            LEFT JOIN instructors i ON i.id = cs.instructor_id
            LEFT JOIN rooms r ON r.id = cs.room_id
            WHERE cs.id = $1
            """,
            session_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_dict(dict(row))


# ── Internal helpers ─────────────────────────────────────────────────────────

async def _fetch_sessions(
    date_from: str | None = None,
    date_to: str | None = None,
    class_type: str | None = None,
) -> list[dict]:
    """Fetch sessions with optional date and class_type filters."""
    from datetime import date as date_type

    conditions = ["cs.status != 'cancelled'"]
    params: list = []
    idx = 1

    # Parse date strings to datetime objects for asyncpg
    def _parse_dt(s: str) -> datetime:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        # Try date-only and convert to datetime
        return datetime.strptime(s[:10], "%Y-%m-%d")

    if date_from:
        conditions.append(f"cs.starts_at >= ${idx}")
        params.append(_parse_dt(date_from))
        idx += 1
    else:
        conditions.append(f"cs.starts_at >= ${idx}")
        params.append(datetime.utcnow().replace(hour=0, minute=0, second=0))
        idx += 1

    if date_to:
        # If date_to is just a date (no time), add 1 day to include the full day
        dt_to = _parse_dt(date_to)
        if dt_to.hour == 0 and dt_to.minute == 0:
            dt_to = dt_to + timedelta(days=1)
        conditions.append(f"cs.starts_at < ${idx}")
        params.append(dt_to)
        idx += 1
    else:
        conditions.append(f"cs.starts_at < ${idx}")
        params.append(datetime.utcnow() + timedelta(days=30))
        idx += 1

    if class_type:
        conditions.append(f"cs.class_type_id = ${idx}")
        params.append(class_type)
        idx += 1

    where = "WHERE " + " AND ".join(conditions)

    async with get_tenant_db() as db:
        rows = await db.fetch(
            f"""
            SELECT cs.*, ct.name AS class_type_name, ct.color,
                   i.display_name AS instructor_name,
                   r.name AS room_name,
                   (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id
                       AND status = 'confirmed') AS booked_count,
                   (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id
                       AND status = 'waitlisted') AS waitlist_count
            FROM class_sessions cs
            LEFT JOIN class_types ct ON ct.id = cs.class_type_id
            LEFT JOIN instructors i ON i.id = cs.instructor_id
            LEFT JOIN rooms r ON r.id = cs.room_id
            {where}
            ORDER BY cs.starts_at
            LIMIT 500
            """,
            *params,
        )
    return [dict(r) for r in rows]
