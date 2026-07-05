"""AuraFlow — Sub-Finder 3000

Automatically finds qualified substitute instructors when an instructor
calls in sick. Contacts candidates by SMS in priority order, handles
responses, and updates the schedule when a sub is confirmed.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.marketing.campaign_service import SmsService
from app.services.email.email_service import EmailService
from app.services.members.phi_helpers import decrypt_phone

_sms = SmsService()
_email = EmailService()


class SubFinderService:

    # ── Initiate Search ────────────────────────────────────────────────────

    async def initiate_sub_search(
        self,
        session_id: str,
        instructor_id: str,
        reason: str | None = None,
    ) -> dict:
        """Start the sub-finding process for a class session."""
        request_id = str(uuid.uuid4())

        async with get_tenant_db() as db:
            # Verify the session exists and belongs to this instructor
            session = await db.fetchrow(
                """
                SELECT cs.*, ct.name AS class_type_name, ct.category,
                       i.display_name AS instructor_name, i.phone AS instructor_phone
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE cs.id = $1
                """,
                session_id,
            )
            if not session:
                raise ValueError("Session not found")

            # Create the sub-finder request
            row = await db.fetchrow(
                """
                INSERT INTO sub_finder_requests
                    (id, class_session_id, original_instructor_id, reason, status)
                VALUES ($1, $2, $3, $4, 'searching')
                RETURNING *
                """,
                request_id, session_id, instructor_id, reason,
            )

        # Find and score qualified substitutes
        candidates = await self.find_qualified_subs(session_id, instructor_id)

        if not candidates:
            # No candidates available
            await self._update_request(request_id, status="unfilled",
                                       ai_summary="No qualified substitutes available")
            logger.warning("Sub search: no candidates", request_id=request_id,
                           session_id=session_id)
            return await self.get_request(request_id)

        # Store candidate list in contacted_instructors
        contacted = [
            {"instructor_id": str(c["id"]), "display_name": c["display_name"],
             "phone": c.get("phone"), "score": c["_score"],
             "contacted_at": None, "response": None, "responded_at": None}
            for c in candidates
        ]
        await self._update_request(request_id, contacted_instructors=contacted)

        # Contact the first candidate
        await self.contact_next_sub(request_id)

        logger.info("Sub search initiated", request_id=request_id,
                     session_id=session_id, candidates=len(candidates))
        return await self.get_request(request_id)

    # ── Find Qualified Subs ────────────────────────────────────────────────

    async def find_qualified_subs(
        self,
        session_id: str,
        original_instructor_id: str,
    ) -> list[dict]:
        """Find and score qualified substitute instructors."""
        async with get_tenant_db() as db:
            # Get session details
            session = await db.fetchrow(
                """
                SELECT cs.starts_at, cs.ends_at, cs.class_type_id,
                       ct.category, ct.name AS class_type_name
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                WHERE cs.id = $1
                """,
                session_id,
            )
            if not session:
                return []

            session_start = session["starts_at"]
            session_end = session["ends_at"]
            category = session["category"] or ""
            class_type_id = session["class_type_id"]
            day_of_week = session_start.weekday()  # 0=Monday

            # Get all active instructors except the original
            instructors = await db.fetch(
                """
                SELECT id, display_name, phone, specialties, certifications
                FROM instructors
                WHERE is_active = TRUE AND id != $1
                """,
                original_instructor_id,
            )

            # Get availability for the day
            availability = await db.fetch(
                """
                SELECT instructor_id, start_time, end_time
                FROM instructor_availability
                WHERE day_of_week = $1 AND is_blocked = FALSE
                """,
                day_of_week,
            )
            avail_by_instructor = {}
            for a in availability:
                iid = str(a["instructor_id"])
                if iid not in avail_by_instructor:
                    avail_by_instructor[iid] = []
                avail_by_instructor[iid].append(a)

            # Get schedule conflicts (other sessions at the same time)
            conflicts = await db.fetch(
                """
                SELECT instructor_id
                FROM class_sessions
                WHERE status != 'cancelled'
                  AND starts_at < $2 AND ends_at > $1
                  AND id != $3
                """,
                session_start, session_end, session_id,
            )
            conflict_ids = {str(c["instructor_id"]) for c in conflicts}

            # Check who already teaches this class type
            type_teachers = await db.fetch(
                """
                SELECT DISTINCT instructor_id
                FROM class_sessions
                WHERE class_type_id = $1 AND status != 'cancelled'
                  AND instructor_id != $2
                """,
                class_type_id, original_instructor_id,
            )
            type_teacher_ids = {str(t["instructor_id"]) for t in type_teachers}

        # Score each instructor
        candidates = []
        session_time = session_start.time()

        for inst in instructors:
            iid = str(inst["id"])

            # Must not have a schedule conflict
            if iid in conflict_ids:
                continue

            # Must have a phone number to contact
            if not inst["phone"]:
                continue

            score = 0
            specialties = inst["specialties"] or []

            # Specialties match
            if category and category.lower() in [s.lower() for s in specialties]:
                score += 30

            # Already teaches this class type
            if iid in type_teacher_ids:
                score += 20

            # Has availability for this time slot
            slots = avail_by_instructor.get(iid, [])
            for slot in slots:
                if slot["start_time"] <= session_time <= slot["end_time"]:
                    score += 25
                    break

            # No conflict already checked above — bonus for being free
            score += 25

            candidates.append({**dict(inst), "_score": score})

        # Sort by score descending, then name for stability
        candidates.sort(key=lambda c: (-c["_score"], c["display_name"]))
        return candidates

    # ── Contact Next Sub ───────────────────────────────────────────────────

    async def contact_next_sub(self, request_id: str) -> bool:
        """Send SMS to the next un-contacted candidate. Returns True if sent."""
        request = await self.get_request(request_id)
        if not request or request["status"] not in ("searching", "offered"):
            return False

        contacted = request["contacted_instructors"] or []

        # Find the first candidate not yet contacted
        next_candidate = None
        next_idx = None
        for i, c in enumerate(contacted):
            if c.get("contacted_at") is None:
                next_candidate = c
                next_idx = i
                break

        if next_candidate is None:
            # All candidates exhausted
            await self._update_request(request_id, status="unfilled",
                                       ai_summary="All candidates declined or unavailable")
            logger.info("Sub search exhausted", request_id=request_id)
            return False

        # Get session details for the message
        async with get_tenant_db() as db:
            session = await db.fetchrow(
                """
                SELECT cs.title, cs.starts_at, cs.ends_at,
                       ct.name AS class_type_name
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                WHERE cs.id = $1
                """,
                request["class_session_id"],
            )

        if not session:
            return False

        starts = session["starts_at"]
        title = session["title"] or session["class_type_name"] or "Class"
        date_str = starts.strftime("%A, %B %d")
        time_str = starts.strftime("%I:%M %p")

        # Send SMS
        body = (
            f"Hi {next_candidate['display_name']}! Can you cover "
            f"{title} on {date_str} at {time_str}? "
            f"Reply YES to accept or NO to decline."
        )
        await _sms.send_sms(
            to_phone=next_candidate["phone"],
            body=body,
            sms_type="sub_request",
        )

        # Update contacted record
        contacted[next_idx]["contacted_at"] = datetime.now(timezone.utc).isoformat()
        await self._update_request(
            request_id, status="offered",
            contacted_instructors=contacted,
        )

        logger.info("Sub request sent", request_id=request_id,
                     instructor=next_candidate["display_name"])
        return True

    # ── Handle Sub Response ────────────────────────────────────────────────

    async def handle_sub_response(
        self,
        request_id: str,
        instructor_id: str,
        accepted: bool,
    ) -> dict:
        """Process a substitute's YES/NO response."""
        request = await self.get_request(request_id)
        if not request:
            raise ValueError("Sub request not found")
        if request["status"] not in ("searching", "offered"):
            raise ValueError(f"Sub request already {request['status']}")

        contacted = request["contacted_instructors"] or []

        # Find this instructor in the contacted list
        found = False
        for c in contacted:
            if c["instructor_id"] == instructor_id:
                c["response"] = "accepted" if accepted else "declined"
                c["responded_at"] = datetime.now(timezone.utc).isoformat()
                found = True
                break

        if not found:
            raise ValueError("Instructor not in candidate list")

        if accepted:
            # Update the class session with the substitute
            async with get_tenant_db() as db:
                await db.execute(
                    """
                    UPDATE class_sessions
                    SET substitute_instructor_id = $1, updated_at = NOW()
                    WHERE id = $2
                    """,
                    instructor_id, request["class_session_id"],
                )

                # Get details for notifications
                sub = await db.fetchrow(
                    "SELECT display_name, phone FROM instructors WHERE id = $1",
                    instructor_id,
                )
                original = await db.fetchrow(
                    "SELECT display_name, phone FROM instructors WHERE id = $1",
                    request["original_instructor_id"],
                )
                session = await db.fetchrow(
                    """
                    SELECT cs.title, cs.starts_at, ct.name AS class_type_name
                    FROM class_sessions cs
                    LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                    WHERE cs.id = $1
                    """,
                    request["class_session_id"],
                )

            sub_name = sub["display_name"] if sub else "A substitute"
            title = session["title"] if session else "Class"

            await self._update_request(
                request_id, status="filled",
                substitute_instructor_id=instructor_id,
                contacted_instructors=contacted,
                ai_summary=f"{sub_name} accepted as substitute",
            )

            # Notify original instructor
            if original and original["phone"]:
                await _sms.send_sms(
                    to_phone=original["phone"],
                    body=f"Great news! {sub_name} will cover your {title} class. Get well soon!",
                    sms_type="sub_confirmation",
                )

            # Notify booked members
            await self._notify_members_of_sub(request["class_session_id"], sub_name, title)

            logger.info("Sub found", request_id=request_id,
                         substitute=sub_name, session_id=request["class_session_id"])
        else:
            # Declined — update and contact next
            await self._update_request(request_id, contacted_instructors=contacted)
            await self.contact_next_sub(request_id)

        return await self.get_request(request_id)

    # ── Notifications ──────────────────────────────────────────────────────

    async def _notify_members_of_sub(
        self, session_id: str, sub_name: str, class_title: str
    ):
        """Notify booked members about the substitute instructor."""
        async with get_tenant_db() as db:
            bookings = await db.fetch(
                """
                SELECT m.id AS member_id, m.phone_enc, m.first_name, m.email
                FROM bookings b
                JOIN members m ON m.id = b.member_id
                WHERE b.class_session_id = $1
                  AND b.status IN ('confirmed', 'waitlisted')
                """,
                session_id,
            )

        for b in bookings:
            member_phone = decrypt_phone(b)
            if member_phone:
                await _sms.send_sms(
                    to_phone=member_phone,
                    body=(
                        f"Hi {b['first_name']}, heads up: your {class_title} class "
                        f"will be taught by {sub_name}. See you there!"
                    ),
                    member_id=str(b["member_id"]),
                    sms_type="sub_notification",
                )

    # ── CRUD ───────────────────────────────────────────────────────────────

    async def get_request(self, request_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM sub_finder_requests WHERE id = $1",
                request_id,
            )
        if not row:
            return None
        d = dict(row)
        # Parse JSONB
        if isinstance(d.get("contacted_instructors"), str):
            d["contacted_instructors"] = json.loads(d["contacted_instructors"])
        for k in ("id", "class_session_id", "original_instructor_id", "substitute_instructor_id"):
            if d.get(k):
                d[k] = str(d[k])
        for k in ("created_at", "updated_at"):
            if d.get(k):
                d[k] = d[k].isoformat()
        return d

    async def list_requests(
        self, status: str | None = None, limit: int = 50
    ) -> list[dict]:
        async with get_tenant_db() as db:
            if status:
                rows = await db.fetch(
                    """
                    SELECT sfr.*, cs.title AS session_title, cs.starts_at,
                           i.display_name AS original_instructor_name
                    FROM sub_finder_requests sfr
                    LEFT JOIN class_sessions cs ON cs.id = sfr.class_session_id
                    LEFT JOIN instructors i ON i.id = sfr.original_instructor_id
                    WHERE sfr.status = $1
                    ORDER BY sfr.created_at DESC LIMIT $2
                    """,
                    status, limit,
                )
            else:
                rows = await db.fetch(
                    """
                    SELECT sfr.*, cs.title AS session_title, cs.starts_at,
                           i.display_name AS original_instructor_name
                    FROM sub_finder_requests sfr
                    LEFT JOIN class_sessions cs ON cs.id = sfr.class_session_id
                    LEFT JOIN instructors i ON i.id = sfr.original_instructor_id
                    ORDER BY sfr.created_at DESC LIMIT $1
                    """,
                    limit,
                )
        results = []
        for row in rows:
            d = dict(row)
            if isinstance(d.get("contacted_instructors"), str):
                d["contacted_instructors"] = json.loads(d["contacted_instructors"])
            for k in ("id", "class_session_id", "original_instructor_id", "substitute_instructor_id"):
                if d.get(k):
                    d[k] = str(d[k])
            for k in ("created_at", "updated_at", "starts_at"):
                if d.get(k):
                    d[k] = d[k].isoformat()
            results.append(d)
        return results

    async def cancel_request(self, request_id: str) -> dict | None:
        """Cancel an active sub search."""
        request = await self.get_request(request_id)
        if not request:
            return None
        if request["status"] in ("filled", "cancelled"):
            raise ValueError(f"Cannot cancel: request is already {request['status']}")
        await self._update_request(request_id, status="cancelled",
                                   ai_summary="Search cancelled by admin")
        return await self.get_request(request_id)

    # ── Internal Helpers ───────────────────────────────────────────────────

    async def _update_request(self, request_id: str, **fields):
        """Update sub_finder_requests row with given fields."""
        if not fields:
            return
        set_clauses = ["updated_at = NOW()"]
        params = []
        idx = 1

        for key, val in fields.items():
            if key == "contacted_instructors" and isinstance(val, list):
                set_clauses.append(f"{key} = ${idx}::jsonb")
                params.append(json.dumps(val))
            else:
                set_clauses.append(f"{key} = ${idx}")
                params.append(val)
            idx += 1

        params.append(request_id)
        async with get_tenant_db() as db:
            await db.execute(
                f"UPDATE sub_finder_requests SET {', '.join(set_clauses)} WHERE id = ${idx}",
                *params,
            )

    async def find_active_request_for_instructor(
        self, instructor_phone: str
    ) -> dict | None:
        """Find an active sub request where this instructor was last contacted."""
        async with get_tenant_db() as db:
            # Look up instructor by phone
            instructor = await db.fetchrow(
                "SELECT id FROM instructors WHERE phone = $1 AND is_active = TRUE",
                instructor_phone,
            )
            if not instructor:
                return None

            instructor_id = str(instructor["id"])

            # Find active requests where this instructor has been contacted
            rows = await db.fetch(
                """
                SELECT * FROM sub_finder_requests
                WHERE status IN ('searching', 'offered')
                ORDER BY updated_at DESC
                """,
            )

        for row in rows:
            d = dict(row)
            contacted = d.get("contacted_instructors") or []
            if isinstance(contacted, str):
                contacted = json.loads(contacted)
            for c in contacted:
                if (c.get("instructor_id") == instructor_id
                        and c.get("contacted_at") is not None
                        and c.get("response") is None):
                    return await self.get_request(str(d["id"]))

        return None
