"""AuraFlow — External Public Events Endpoint.

API-key gated, returns the next-N-days of publishable events
(workshops, teacher trainings, retreats) for the authenticated
studio. Used by public marketing sites that want a 'what's coming up'
listing without exposing the member-portal JWT surface.

Tenant scoping is enforced by the API key (each studio has its own).
Filters baked in: status='published', type IN known set, ends_at still
in the future so multi-week workshop series stay listed until the last
session is over."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.v1.dependencies.api_key_auth import (
    get_api_key_context,
    require_api_scope,
)
from app.db.session import get_tenant_db


router = APIRouter()

_EVENT_TYPES = ("workshop", "teacher_training", "retreat")


def _fmt(dt):
    if dt and hasattr(dt, "isoformat"):
        return dt.isoformat()
    return None


@router.get(
    "/events/upcoming",
    dependencies=[Depends(require_api_scope("courses:read"))],
    summary="Public upcoming events (workshops, teacher trainings, retreats)",
)
async def list_upcoming_events(
    ctx: dict = Depends(get_api_key_context),
    days: int = Query(60, ge=1, le=365),
):
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=days)
    async with get_tenant_db() as db:
        rows = await db.fetch(
            """
            SELECT c.id, c.title, c.description, c.type, c.price_cents,
                   c.early_bird_price_cents, c.early_bird_deadline,
                   c.capacity, c.location, c.is_virtual,
                   c.image_url,
                   c.starts_at, c.ends_at,
                   c.registration_opens, c.registration_closes,
                   (c.flyer_image_data IS NOT NULL) AS has_flyer,
                   i.display_name AS instructor_name,
                   gi.name        AS guest_instructor_name,
                   (SELECT COUNT(*) FROM course_enrollments ce
                    WHERE ce.course_id = c.id AND ce.status = 'enrolled')
                       AS enrolled_count
            FROM courses c
            LEFT JOIN instructors i  ON i.id  = c.instructor_id
            LEFT JOIN guest_instructors gi ON gi.id = c.guest_instructor_id
            WHERE c.status = 'published'
              AND c.type   = ANY($1::text[])
              AND c.starts_at IS NOT NULL
              AND (c.ends_at > $2 OR c.ends_at IS NULL)
              AND c.starts_at <  $3
            ORDER BY c.starts_at ASC
            """,
            list(_EVENT_TYPES),
            now,
            until,
        )
        course_ids = [r["id"] for r in rows]
        sessions_by_course: dict = {}
        if course_ids:
            session_rows = await db.fetch(
                """
                SELECT id, course_id, session_number, title,
                       starts_at, ends_at, location, is_virtual
                FROM course_sessions
                WHERE course_id = ANY($1::uuid[])
                ORDER BY session_number ASC
                """,
                course_ids,
            )
            for s in session_rows:
                sessions_by_course.setdefault(s["course_id"], []).append(s)

    out = []
    for r in rows:
        capacity = r.get("capacity")
        enrolled = r.get("enrolled_count") or 0
        spots_remaining = (capacity - enrolled) if capacity else None
        instructor = r.get("instructor_name") or r.get("guest_instructor_name")
        course_sessions = sessions_by_course.get(r["id"], [])
        out.append({
            "id": str(r["id"]),
            "title": r["title"],
            "description": r.get("description"),
            "type": r.get("type"),
            "instructor_name": instructor,
            "price_cents": r.get("price_cents"),
            "early_bird_price_cents": r.get("early_bird_price_cents"),
            "early_bird_deadline": _fmt(r.get("early_bird_deadline")),
            "capacity": capacity,
            "enrolled_count": enrolled,
            "spots_remaining": spots_remaining,
            "is_full": (spots_remaining == 0) if spots_remaining is not None else False,
            "location": r.get("location"),
            "is_virtual": r.get("is_virtual", False),
            "image_url": r.get("image_url"),
            "has_flyer": r.get("has_flyer", False),
            "flyer_data_url": None,
            "starts_at": _fmt(r.get("starts_at")),
            "ends_at": _fmt(r.get("ends_at")),
            "registration_opens": _fmt(r.get("registration_opens")),
            "registration_closes": _fmt(r.get("registration_closes")),
            "session_count": len(course_sessions),
            "sessions": [
                {
                    "id": str(s["id"]),
                    "session_number": s["session_number"],
                    "title": s.get("title"),
                    "starts_at": _fmt(s["starts_at"]),
                    "ends_at": _fmt(s["ends_at"]),
                    "location": s.get("location"),
                    "is_virtual": s.get("is_virtual", False),
                }
                for s in course_sessions
            ],
        })
    return {"data": out, "count": len(out), "days": days}


@router.get(
    "/events/{course_id}/flyer",
    dependencies=[Depends(require_api_scope("courses:read"))],
    summary="Serve the flyer image for a published event",
)
async def get_event_flyer(
    course_id: str,
    ctx: dict = Depends(get_api_key_context),
):
    async with get_tenant_db() as db:
        row = await db.fetchrow(
            """
            SELECT flyer_image_data, flyer_image_mime
            FROM courses
            WHERE id = $1 AND status = 'published'
            """,
            course_id,
        )
    if not row or not row["flyer_image_data"]:
        raise HTTPException(status_code=404, detail="No flyer for this event")
    return Response(
        content=row["flyer_image_data"],
        media_type=row["flyer_image_mime"] or "image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )
