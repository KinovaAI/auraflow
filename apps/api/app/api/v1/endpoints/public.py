"""AuraFlow — Public Schedule API

Unauthenticated endpoints for embedding studio schedules on external websites.
Tenant is resolved from the org_slug path parameter instead of JWT.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.logging import logger
from app.db.session import get_global_db

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _resolve_tenant_schema(org_slug: str) -> str:
    """Look up the tenant schema for a given org slug. Raises 404 if not found."""
    async with get_global_db() as db:
        row = await db.fetchrow(
            """
            SELECT schema_name, status
            FROM af_global.organizations
            WHERE slug = $1
            """,
            org_slug,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Studio not found")
    if row["status"] in ("suspended", "cancelled"):
        raise HTTPException(status_code=403, detail="Studio is not available")
    return row["schema_name"]


async def _tenant_query(schema: str, query: str, *params):
    """Execute a query against a specific tenant schema."""
    async with get_global_db() as db:
        await db.execute(f"SET search_path TO \"{schema}\", public")
        rows = await db.fetch(query, *params)
        await db.execute("SET search_path TO public")
        return [dict(r) for r in rows]


async def _tenant_query_row(schema: str, query: str, *params):
    """Execute a single-row query against a specific tenant schema."""
    async with get_global_db() as db:
        await db.execute(f"SET search_path TO \"{schema}\", public")
        row = await db.fetchrow(query, *params)
        await db.execute("SET search_path TO public")
        return dict(row) if row else None


# ── Response Schemas ─────────────────────────────────────────────────────────

class PublicSession(BaseModel):
    id: str
    title: Optional[str] = None
    starts_at: str
    ends_at: Optional[str] = None
    class_type_name: Optional[str] = None
    class_category: Optional[str] = None
    class_description: Optional[str] = None
    level: Optional[str] = None
    instructor_name: Optional[str] = None
    room_name: Optional[str] = None
    spots_remaining: int = 0
    is_full: bool = False
    waitlist_available: bool = False


class PublicClassType(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    duration_minutes: int = 60
    category: Optional[str] = None
    level: Optional[str] = None
    color: Optional[str] = None
    image_url: Optional[str] = None


class PublicInstructor(BaseModel):
    id: str
    display_name: str
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    specialties: Optional[list[str]] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{org_slug}/schedule.html")
async def public_schedule_html(
    org_slug: str,
    days: int = Query(14, ge=1, le=60),
):
    """Public HTML schedule page — human-readable, no auth required."""
    from fastapi.responses import HTMLResponse
    from zoneinfo import ZoneInfo

    schema = await _resolve_tenant_schema(org_slug)
    pacific = ZoneInfo("America/Los_Angeles")

    # Get org name
    async with get_global_db() as db:
        org = await db.fetchrow("SELECT name FROM af_global.organizations WHERE slug = $1", org_slug)
    studio_name = org["name"] if org else org_slug

    now = datetime.now(timezone.utc)
    end_dt = now + timedelta(days=days)

    rows = await _tenant_query(
        schema,
        """
        SELECT cs.title, cs.starts_at, cs.ends_at, cs.capacity,
               i.display_name AS instructor_name,
               (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id AND status = 'confirmed') AS booked_count
        FROM class_sessions cs
        LEFT JOIN instructors i ON i.id = cs.instructor_id
        WHERE cs.starts_at >= $1 AND cs.starts_at < $2 AND cs.status = 'scheduled'
        ORDER BY cs.starts_at
        LIMIT 500
        """,
        now, end_dt,
    )

    # Build HTML table
    table_rows = ""
    current_date = ""
    for r in rows:
        starts = r["starts_at"]
        if starts.tzinfo is None:
            starts = starts.replace(tzinfo=timezone.utc)
        local = starts.astimezone(pacific)
        date_str = local.strftime("%A, %B %d, %Y")
        time_str = local.strftime("%-I:%M %p")

        ends = r.get("ends_at")
        end_time = ""
        if ends:
            if ends.tzinfo is None:
                ends = ends.replace(tzinfo=timezone.utc)
            end_time = ends.astimezone(pacific).strftime("%-I:%M %p")

        spots = max(0, r["capacity"] - r["booked_count"])

        if date_str != current_date:
            current_date = date_str
            table_rows += f'<tr><td colspan="5" style="background:#f3f4f6;padding:10px 12px;font-weight:700;font-size:15px;border-top:2px solid #d1d5db;">{date_str}</td></tr>\n'

        table_rows += f"""<tr>
            <td style="padding:8px 12px;">{r['title']}</td>
            <td style="padding:8px 12px;">{time_str}{(' – ' + end_time) if end_time else ''}</td>
            <td style="padding:8px 12px;">{r.get('instructor_name') or ''}</td>
            <td style="padding:8px 12px;text-align:center;">{spots}</td>
        </tr>\n"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{studio_name} — Class Schedule</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #fff; color: #111; }}
        h1 {{ font-size: 24px; margin-bottom: 4px; }}
        .subtitle {{ color: #6b7280; margin-bottom: 20px; font-size: 14px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; padding: 10px 12px; border-bottom: 2px solid #111; font-size: 13px; text-transform: uppercase; color: #6b7280; }}
        td {{ border-bottom: 1px solid #e5e7eb; font-size: 14px; }}
        tr:hover td {{ background: #f9fafb; }}
        .footer {{ margin-top: 20px; font-size: 12px; color: #9ca3af; }}
    </style>
</head>
<body>
    <h1>{studio_name}</h1>
    <p class="subtitle">Class Schedule — Next {days} Days</p>
    <table>
        <thead>
            <tr>
                <th>Class</th>
                <th>Time</th>
                <th>Instructor</th>
                <th style="text-align:center;">Spots</th>
            </tr>
        </thead>
        <tbody>
            {table_rows if table_rows else '<tr><td colspan="5" style="padding:20px;text-align:center;color:#9ca3af;">No classes scheduled</td></tr>'}
        </tbody>
    </table>
    <p class="footer">Updated {datetime.now(pacific).strftime('%B %d, %Y at %-I:%M %p')} Pacific · Powered by AuraFlow</p>
</body>
</html>"""

    return HTMLResponse(content=html)


@router.get("/{org_slug}/schedule", response_model=list[PublicSession])
async def public_schedule(
    org_slug: str,
    start: Optional[str] = Query(None, description="Start date ISO 8601"),
    end: Optional[str] = Query(None, description="End date ISO 8601"),
    class_type_id: Optional[str] = Query(None),
    instructor_id: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
):
    """Public schedule — upcoming class sessions for a studio.

    Redis-cached for 5 minutes per unique (org, filters) combination.
    This endpoint is hit repeatedly by ClassPass + external scrapers and
    by public schedule widgets on the studio's marketing site; caching
    cuts P95 from ~800ms to ~20ms and protects against abuse.
    """
    schema = await _resolve_tenant_schema(org_slug)

    # Cache key incorporates every input that affects the result.
    cache_key = (
        f"public_schedule:{org_slug}:{start or ''}:{end or ''}:"
        f"{class_type_id or ''}:{instructor_id or ''}:{limit}"
    )
    try:
        from app.core.redis import get_redis
        import json as _json
        redis = await get_redis()
        if redis:
            cached = await redis.get(cache_key)
            if cached:
                payload = _json.loads(cached)
                return [PublicSession(**item) for item in payload]
    except Exception:
        # Never let cache failures block the live path.
        pass

    start_dt = datetime.fromisoformat(start) if start else datetime.now(timezone.utc)
    end_dt = datetime.fromisoformat(end) if end else start_dt + timedelta(days=14)

    conditions = [
        "cs.starts_at >= $1",
        "cs.starts_at < $2",
        "cs.status = 'scheduled'",
    ]
    params: list = [start_dt, end_dt]
    idx = 3

    if class_type_id:
        conditions.append(f"cs.class_type_id = ${idx}")
        params.append(class_type_id)
        idx += 1
    if instructor_id:
        conditions.append(f"cs.instructor_id = ${idx}")
        params.append(instructor_id)
        idx += 1

    params.append(limit)

    query = f"""
        SELECT cs.id, cs.title, cs.starts_at, cs.ends_at,
               cs.capacity, cs.waitlist_capacity,
               ct.name AS class_type_name, ct.category AS class_category,
               ct.description AS class_description, ct.level,
               i.display_name AS instructor_name,
               r.name AS room_name,
               (SELECT COUNT(*) FROM bookings
                WHERE class_session_id = cs.id AND status = 'confirmed') AS booked_count,
               (SELECT COUNT(*) FROM bookings
                WHERE class_session_id = cs.id AND status = 'waitlisted') AS waitlist_count
        FROM class_sessions cs
        LEFT JOIN class_types ct ON ct.id = cs.class_type_id
        LEFT JOIN instructors i ON i.id = cs.instructor_id
        LEFT JOIN rooms r ON r.id = cs.room_id
        WHERE {' AND '.join(conditions)}
        ORDER BY cs.starts_at
        LIMIT ${idx}
    """

    rows = await _tenant_query(schema, query, *params)

    def _fmt(dt):
        if dt and hasattr(dt, "isoformat"):
            return dt.isoformat()
        return str(dt) if dt else None

    sessions = [
        PublicSession(
            id=str(r["id"]),
            title=r.get("title"),
            starts_at=_fmt(r["starts_at"]),
            ends_at=_fmt(r.get("ends_at")),
            class_type_name=r.get("class_type_name"),
            class_category=r.get("class_category"),
            class_description=r.get("class_description"),
            level=r.get("level"),
            instructor_name=r.get("instructor_name"),
            room_name=r.get("room_name"),
            spots_remaining=max(0, r["capacity"] - r["booked_count"]),
            is_full=r["booked_count"] >= r["capacity"],
            waitlist_available=r["waitlist_count"] < r["waitlist_capacity"],
        )
        for r in rows
    ]

    try:
        from app.core.redis import get_redis
        import json as _json
        redis = await get_redis()
        if redis:
            payload = [s.model_dump() for s in sessions]
            await redis.set(cache_key, _json.dumps(payload), ex=300)
    except Exception:
        pass

    return sessions


@router.get("/{org_slug}/class-types", response_model=list[PublicClassType])
async def public_class_types(org_slug: str):
    """Public list of active class types for a studio."""
    schema = await _resolve_tenant_schema(org_slug)

    rows = await _tenant_query(
        schema,
        """
        SELECT id, name, description, duration_minutes, category, level, color, image_url
        FROM class_types
        WHERE is_active = TRUE
        ORDER BY name
        """,
    )

    return [
        PublicClassType(
            id=str(r["id"]),
            name=r["name"],
            description=r.get("description"),
            duration_minutes=r.get("duration_minutes", 60),
            category=r.get("category"),
            level=r.get("level"),
            color=r.get("color"),
            image_url=r.get("image_url"),
        )
        for r in rows
    ]


@router.get("/{org_slug}/instructors", response_model=list[PublicInstructor])
async def public_instructors(org_slug: str):
    """Public list of active instructors for a studio."""
    schema = await _resolve_tenant_schema(org_slug)

    rows = await _tenant_query(
        schema,
        """
        SELECT id, display_name, bio, photo_url, specialties
        FROM instructors
        WHERE is_active = TRUE
        ORDER BY display_name
        """,
    )

    return [
        PublicInstructor(
            id=str(r["id"]),
            display_name=r["display_name"],
            bio=r.get("bio"),
            photo_url=r.get("photo_url"),
            specialties=r.get("specialties"),
        )
        for r in rows
    ]
