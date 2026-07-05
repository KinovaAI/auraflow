"""AuraFlow — External Guest Workshops Endpoint

Single endpoint that returns a registered guest instructor's upcoming
workshops with their rosters baked in. Used by the
your-domain.com /guestworkshops page so guest instructors can pull
up the roster for their workshop on the day of teaching.

POST /api/v1/external/guest-workshops
Auth: Bearer <existing studio API key with `courses:read` scope>
Body: { "guest_instructor_email": "name@example.com" }

→ 200 with the guest's upcoming workshops + rosters, or 404 if no
  active guest_instructors row matches that email (within the tenant
  resolved from the API key).

Email is matched case-insensitively against `guest_instructors.email`.
Only active (`is_active = TRUE`) guests are considered. A 404 is
returned for any miss — never reveals "email not found" vs "inactive
guest" vs anything else.

A workshop is "upcoming" if it has at least one `course_sessions` row
with `starts_at > NOW()`. Past workshops drop off automatically. Only
courses in status `published` or `in_progress` are returned (drafts
and cancelled ones are hidden).

Roster rows include only the member's first + last name and a boolean
`paid` flag. No email, no phone, no member_id, no payment amount.
Booking statuses included: `enrolled` (the active one); `withdrawn`
rows are excluded.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from app.api.v1.dependencies.api_key_auth import get_api_key_context, require_api_scope
from app.db.session import get_tenant_db


router = APIRouter()


class GuestWorkshopsRequest(BaseModel):
    guest_instructor_email: EmailStr


def _fmt(dt):
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else None


@router.post(
    "/guest-workshops",
    dependencies=[Depends(require_api_scope("courses:read"))],
    summary="List a registered guest instructor's upcoming workshops with rosters",
)
async def list_guest_workshops(
    body: GuestWorkshopsRequest,
    ctx: dict = Depends(get_api_key_context),
):
    email_lower = body.guest_instructor_email.strip().lower()

    async with get_tenant_db() as db:
        # Resolve the guest instructor by their registered email. Active
        # only. Returns generic 404 on any miss.
        guest = await db.fetchrow(
            """
            SELECT id, name
              FROM guest_instructors
             WHERE LOWER(email) = $1
               AND is_active = TRUE
            """,
            email_lower,
        )
        if not guest:
            raise HTTPException(
                status_code=404,
                detail="No active guest instructor found for that email",
            )

        workshops = await db.fetch(
            """
            SELECT c.id,
                   c.title,
                   c.location,
                   c.is_virtual,
                   c.price_cents,
                   (SELECT MIN(cs.starts_at)
                      FROM course_sessions cs
                     WHERE cs.course_id = c.id
                       AND cs.starts_at > NOW()) AS next_session_at
              FROM courses c
             WHERE c.guest_instructor_id = $1
               AND c.status IN ('published', 'in_progress')
               AND EXISTS (
                   SELECT 1 FROM course_sessions cs
                    WHERE cs.course_id = c.id
                      AND cs.starts_at > NOW()
               )
             ORDER BY next_session_at ASC NULLS LAST
            """,
            guest["id"],
        )

        result = []
        for w in workshops:
            roster = await db.fetch(
                """
                SELECT m.first_name,
                       m.last_name,
                       ce.paid_price_cents
                  FROM course_enrollments ce
                  JOIN members m ON m.id = ce.member_id
                 WHERE ce.course_id = $1
                   AND ce.status = 'enrolled'
                 ORDER BY LOWER(COALESCE(m.last_name, '')),
                          LOWER(COALESCE(m.first_name, ''))
                """,
                w["id"],
            )

            result.append({
                "id": str(w["id"]),
                "title": w["title"],
                "location": w["location"],
                "is_virtual": w["is_virtual"],
                "starts_at": _fmt(w["next_session_at"]),
                "price_cents": w["price_cents"],
                "roster": [
                    {
                        "name": " ".join(
                            p for p in (r["first_name"], r["last_name"]) if p
                        ) or "(no name on file)",
                        "paid": bool((r["paid_price_cents"] or 0) > 0),
                    }
                    for r in roster
                ],
            })

        return {
            "guest_instructor_name": guest["name"],
            "workshops": result,
        }
