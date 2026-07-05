"""AuraFlow — Member Portal Service

Thin service layer for member self-service. Delegates to existing services
(BookingService, MemberService) with member-scoped access control.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.scheduling.booking_service import BookingService
from app.services.scheduling.course_service import CourseService
from app.services.scheduling.private_session_service import PrivateSessionService
from app.services.members.member_service import MemberService
from app.services.memberships.membership_service import MembershipService
from app.services.ai.ai_service import AIService

_booking_svc = BookingService()
_course_svc = CourseService()
_private_svc = PrivateSessionService()
_member_svc = MemberService()
_membership_svc = MembershipService()
_ai_svc = AIService()

# Fields a member is allowed to update on their own profile
ALLOWED_PROFILE_FIELDS = {
    "phone", "emergency_contact_name", "emergency_contact_phone",
    "email_opt_in", "sms_opt_in",
}


class PortalService:

    async def _get_member_by_user_id(self, user_id: str) -> dict | None:
        """Look up the member record linked to this user account.

        Routes through _row_with_decrypted_phi so the member sees their
        own decrypted phone / DOB / address / emergency contact. Without
        this, after Phase C drops plaintext, the portal profile page
        would render NULL for every PHI field.
        """
        from app.services.members.member_service import _row_with_decrypted_phi
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM members WHERE user_id = $1 AND is_active = TRUE",
                user_id,
            )
            return _row_with_decrypted_phi(dict(row)) if row else None

    async def get_my_profile(self, user_id: str) -> dict | None:
        return await self._get_member_by_user_id(user_id)

    async def update_my_profile(self, user_id: str, data: dict) -> dict | None:
        member = await self._get_member_by_user_id(user_id)
        if not member:
            return None

        # Filter to allowed fields only
        filtered = {k: v for k, v in data.items() if k in ALLOWED_PROFILE_FIELDS}
        if not filtered:
            return member

        return await _member_svc.update_member(str(member["id"]), filtered)

    async def get_my_bookings(
        self,
        user_id: str,
        upcoming_only: bool = False,
        limit: int = 50,
    ) -> list[dict]:
        member = await self._get_member_by_user_id(user_id)
        if not member:
            return []

        member_id = str(member["id"])

        if upcoming_only:
            async with get_tenant_db() as db:
                rows = await db.fetch(
                    """
                    SELECT b.id, b.class_session_id, b.status, b.source,
                           b.booked_at, b.waitlist_position,
                           cs.title AS session_title, cs.starts_at, cs.ends_at,
                           cs.is_virtual, cs.zoom_join_url, cs.zoom_password,
                           ct.name AS class_type_name, ct.category AS class_category,
                           i.display_name AS instructor_name
                    FROM bookings b
                    JOIN class_sessions cs ON cs.id = b.class_session_id
                    LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                    LEFT JOIN instructors i ON i.id = cs.instructor_id
                    WHERE b.member_id = $1
                      AND b.status IN ('confirmed', 'waitlisted')
                      AND cs.starts_at > NOW()
                    ORDER BY cs.starts_at ASC
                    LIMIT $2
                    """,
                    member_id, limit,
                )
                bookings = [dict(r) for r in rows]
                if not await self._member_has_digital_access(member_id):
                    for b in bookings:
                        b["zoom_join_url"] = None
                        b["zoom_password"] = None
                return bookings

        # All bookings (delegates to member service)
        bookings = await _member_svc.get_booking_history(member_id, limit)
        if not await self._member_has_digital_access(member_id):
            for b in bookings:
                b["zoom_join_url"] = None
                b["zoom_password"] = None
        return bookings

    async def _member_has_digital_access(self, member_id: str) -> bool:
        """True if member has an active membership with online/all_access scope."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT 1 FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE mm.member_id = $1
                  AND mm.status = 'active'
                  AND (mm.ends_at IS NULL OR mm.ends_at > NOW())
                  AND mt.access_scope IN ('online', 'all_access')
                  AND (mt.type NOT IN ('single_class', 'class_pack') OR mm.classes_remaining > 0)
                LIMIT 1
                """,
                member_id,
            )
        return row is not None

    async def get_upcoming_sessions(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        class_type_id: str | None = None,
        instructor_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Browse upcoming sessions with availability info."""
        if not start:
            start = datetime.now(timezone.utc)
        if not end:
            end = start + timedelta(days=14)

        async with get_tenant_db() as db:
            conditions = [
                "cs.starts_at >= $1",
                "cs.starts_at < $2",
                "cs.status = 'scheduled'",
            ]
            params: list = [start, end]
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
                SELECT cs.id, cs.title, cs.starts_at, cs.ends_at, cs.capacity,
                       cs.waitlist_capacity, cs.is_virtual,
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
            rows = await db.fetch(query, *params)

            return [
                {
                    **dict(r),
                    "spots_remaining": max(0, r["capacity"] - r["booked_count"]),
                    "is_full": r["booked_count"] >= r["capacity"],
                    "waitlist_available": r["waitlist_count"] < r["waitlist_capacity"],
                }
                for r in rows
            ]

    async def book_class(
        self,
        user_id: str,
        session_id: str,
        membership_id: str | None = None,
    ) -> dict:
        """Book a class for the authenticated member."""
        member = await self._get_member_by_user_id(user_id)
        if not member:
            raise ValueError("Member profile not found")

        member_id = str(member["id"])

        # Check for duplicate booking
        async with get_tenant_db() as db:
            existing = await db.fetchrow(
                """
                SELECT id FROM bookings
                WHERE member_id = $1 AND class_session_id = $2
                  AND status IN ('confirmed', 'waitlisted')
                """,
                member_id, session_id,
            )
            if existing:
                raise ValueError("You are already booked for this class")

            # Check membership eligibility
            session_info = await db.fetchrow(
                "SELECT class_type_id, is_virtual FROM class_sessions WHERE id = $1",
                session_id,
            )
            eligibility = await _membership_svc.check_eligibility(
                member_id,
                class_type_id=str(session_info["class_type_id"]) if session_info.get("class_type_id") else None,
                is_virtual=session_info.get("is_virtual", False),
            )
            if not eligibility["eligible"]:
                raise ValueError("You don't have an active membership. Please purchase a membership to book classes.")
            # Auto-set membership_id
            if not membership_id:
                membership_id = eligibility["membership_id"]

        booking = await _booking_svc.book_class({
            "member_id": member_id,
            "class_session_id": session_id,
            "source": "member_portal",
            "membership_id": membership_id,
        })

        logger.info(
            "Member self-booked",
            member_id=member_id,
            session_id=session_id,
            status=booking["status"],
        )
        return booking

    async def cancel_my_booking(self, user_id: str, booking_id: str, reason: str | None = None) -> dict | None:
        """Cancel a booking, verifying it belongs to this member."""
        member = await self._get_member_by_user_id(user_id)
        if not member:
            raise ValueError("Member profile not found")

        # Verify the booking belongs to this member
        async with get_tenant_db() as db:
            booking = await db.fetchrow(
                "SELECT member_id, status FROM bookings WHERE id = $1",
                booking_id,
            )

        if not booking:
            return None
        if str(booking["member_id"]) != str(member["id"]):
            raise PermissionError("Cannot cancel another member's booking")
        if booking["status"] in ("cancelled", "attended", "no_show"):
            raise ValueError(f"Booking is already {booking['status']}")

        return await _booking_svc.cancel_booking(booking_id, reason=reason)

    async def get_my_memberships(self, user_id: str) -> list[dict]:
        """Get active memberships for this member."""
        member = await self._get_member_by_user_id(user_id)
        if not member:
            return []

        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT mm.id, mm.status, mm.starts_at, mm.ends_at,
                       mm.classes_remaining, mm.stripe_subscription_id,
                       mm.square_subscription_id, mm.current_period_end,
                       mt.auto_renew, mt.billing_period,
                       mt.name AS type_name, mt.type AS membership_type,
                       mt.price_cents, mt.class_count
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE mm.member_id = $1
                  AND mm.status IN ('active', 'frozen')
                ORDER BY mm.starts_at DESC
                """,
                str(member["id"]),
            )
            return [dict(r) for r in rows]

    async def get_available_membership_types(self, user_id: str | None = None) -> list[dict]:
        """Get publicly available membership types for this tenant's studio.

        Filters out:
          - Free intro offers the member has already used (same type_id)
          - Types flagged new_members_only when the member has ANY
            prior member_memberships row (regardless of type or status)
        """
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT id, name, description, type, class_count,
                       price_cents, billing_period, duration_days,
                       is_founding_rate, trial_days, freeze_allowed, is_public,
                       new_members_only
                FROM membership_types
                WHERE is_active = TRUE AND is_public = TRUE
                ORDER BY sort_order, name
                """,
            )
            results = [{**dict(r), "id": str(r["id"])} for r in rows]

            if user_id:
                member = await db.fetchrow(
                    "SELECT id FROM members WHERE user_id = $1 LIMIT 1", user_id
                )
                if member:
                    # Pull all prior membership rows in one shot
                    prior = await db.fetch(
                        "SELECT membership_type_id FROM member_memberships WHERE member_id = $1",
                        str(member["id"]),
                    )
                    used_set = {str(r["membership_type_id"]) for r in prior}
                    has_any_prior_membership = len(prior) > 0

                    results = [
                        mt for mt in results
                        if (mt["price_cents"] > 0 or mt["id"] not in used_set)
                        and not (mt.get("new_members_only") and has_any_prior_membership)
                    ]

            return results

    async def get_my_transactions(self, user_id: str, limit: int = 50) -> list[dict]:
        """Get payment history for this member."""
        member = await self._get_member_by_user_id(user_id)
        if not member:
            return []

        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT id, amount_cents, type, status, description, created_at
                FROM transactions
                WHERE member_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                str(member["id"]), limit,
            )
            return [
                {**dict(r), "id": str(r["id"]), "created_at": r["created_at"].isoformat() if r.get("created_at") else None}
                for r in rows
            ]

    # ── Workshops / Courses ──────────────────────────────────────────────

    async def get_published_courses(self, course_type: str | None = None) -> list[dict]:
        """Get published courses available for enrollment.

        Hard rule: a workshop stays on the portal until its LAST session
        ends. Previously this filtered on starts_at, which removed any
        multi-week workshop 24h after the first session — killing late
        signups for the remaining classes. Now uses ends_at so a series
        is bookable as long as there are sessions left.
        """
        async with get_tenant_db() as db:
            conditions = [
                "c.status = 'published'",
                "(c.registration_closes > NOW() OR c.registration_closes IS NULL)",
                "(c.ends_at > NOW() OR c.ends_at IS NULL)",
            ]
            params: list = []
            idx = 1
            if course_type:
                conditions.append(f"c.type = ${idx}")
                params.append(course_type)
                idx += 1
            where = f"WHERE {' AND '.join(conditions)}"
            rows = await db.fetch(
                f"""
                SELECT c.id, c.title, c.description, c.type, c.instructor_id,
                       c.guest_instructor_id,
                       c.price_cents, c.early_bird_price_cents, c.early_bird_deadline,
                       c.capacity, c.location, c.is_virtual, c.image_url,
                       c.prerequisites, c.registration_opens, c.registration_closes,
                       c.starts_at, c.ends_at,
                       i.display_name AS instructor_name,
                       gi.name      AS guest_instructor_name,
                       gi.photo_url AS guest_instructor_photo_url,
                       gi.bio       AS guest_instructor_bio,
                       (SELECT COUNT(*) FROM course_enrollments ce
                        WHERE ce.course_id = c.id AND ce.status = 'enrolled') AS enrolled_count
                FROM courses c
                LEFT JOIN instructors i ON i.id = c.instructor_id
                LEFT JOIN guest_instructors gi ON gi.id = c.guest_instructor_id
                {where}
                ORDER BY c.starts_at ASC
                """,
                *params,
            )
            return [dict(r) for r in rows]

    async def get_course_detail(self, course_id: str) -> dict | None:
        """Get a single published course with its sessions."""
        course = await _course_svc.get_course(course_id)
        if not course or course.get("status") not in ("published", "in_progress"):
            return None
        sessions = await _course_svc.list_sessions(course_id)
        course["sessions"] = sessions
        return course

    async def get_my_enrollments(self, user_id: str) -> list[dict]:
        """Get the authenticated member's course enrollments."""
        member = await self._get_member_by_user_id(user_id)
        if not member:
            return []
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT ce.id, ce.course_id, ce.status, ce.paid_price_cents, ce.enrolled_at,
                       c.title, c.type, c.starts_at, c.ends_at, c.is_virtual,
                       i.display_name AS instructor_name
                FROM course_enrollments ce
                JOIN courses c ON c.id = ce.course_id
                LEFT JOIN instructors i ON i.id = c.instructor_id
                WHERE ce.member_id = $1
                ORDER BY ce.enrolled_at DESC
                """,
                str(member["id"]),
            )
            return [dict(r) for r in rows]

    async def enroll_in_course(self, user_id: str, course_id: str) -> dict:
        """Enroll the authenticated member in a course."""
        member = await self._get_member_by_user_id(user_id)
        if not member:
            raise ValueError("Member profile not found")
        return await _course_svc.enroll_member(course_id, str(member["id"]))

    async def withdraw_my_enrollment(self, user_id: str, enrollment_id: str) -> dict | None:
        """Withdraw from a course, verifying the enrollment belongs to this member."""
        member = await self._get_member_by_user_id(user_id)
        if not member:
            raise ValueError("Member profile not found")
        async with get_tenant_db() as db:
            enrollment = await db.fetchrow(
                "SELECT member_id FROM course_enrollments WHERE id = $1", enrollment_id
            )
        if not enrollment:
            return None
        if str(enrollment["member_id"]) != str(member["id"]):
            raise PermissionError("Cannot withdraw another member's enrollment")
        return await _course_svc.withdraw_member(enrollment_id)

    # ── Private Lessons ────────────────────────────────────────────────────

    async def get_instructors_with_services(self) -> list[dict]:
        """Get instructors who offer publicly-visible private services."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT DISTINCT i.id, i.display_name, i.bio, i.photo_url,
                       i.specialties, i.certifications
                FROM instructors i
                JOIN private_services ps ON ps.instructor_id = i.id
                WHERE i.is_active = TRUE
                  AND ps.is_active = TRUE
                  AND ps.visibility IN ('public', 'members_only')
                ORDER BY i.display_name
                """,
            )
            return [dict(r) for r in rows]

    async def get_instructor_services(self, instructor_id: str) -> list[dict]:
        """Get an instructor's publicly available private services."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT id, name, description, duration_minutes, price_cents,
                       is_virtual
                FROM private_services
                WHERE instructor_id = $1
                  AND is_active = TRUE
                  AND visibility IN ('public', 'members_only')
                ORDER BY name
                """,
                instructor_id,
            )
            return [dict(r) for r in rows]

    async def get_available_slots(
        self, instructor_id: str, service_id: str, target_date: str
    ) -> list[dict]:
        """Get available time slots for a private session."""
        from datetime import date
        dt = date.fromisoformat(target_date)
        return await _private_svc.get_available_slots(instructor_id, service_id, dt)

    async def book_private_session(self, user_id: str, data: dict) -> dict:
        """Book a private session for the authenticated member."""
        member = await self._get_member_by_user_id(user_id)
        if not member:
            raise ValueError("Member profile not found")
        data["member_id"] = str(member["id"])
        return await _private_svc.book_session(data)

    async def get_my_private_bookings(
        self, user_id: str, upcoming_only: bool = False
    ) -> list[dict]:
        """Get the authenticated member's private session bookings."""
        member = await self._get_member_by_user_id(user_id)
        if not member:
            return []
        member_id = str(member["id"])
        async with get_tenant_db() as db:
            base = """
                SELECT pb.id, pb.starts_at, pb.ends_at, pb.status, pb.is_virtual,
                       pb.zoom_join_url, pb.price_cents, pb.payment_url, pb.created_at,
                       ps.name AS service_name, ps.duration_minutes,
                       i.display_name AS instructor_name, i.photo_url AS instructor_photo
                FROM private_bookings pb
                JOIN private_services ps ON ps.id = pb.private_service_id
                JOIN instructors i ON i.id = pb.instructor_id
                WHERE pb.member_id = $1
            """
            if upcoming_only:
                base += " AND pb.status IN ('pending', 'confirmed') AND pb.starts_at > NOW()"
                base += " ORDER BY pb.starts_at ASC"
            else:
                base += " ORDER BY pb.starts_at DESC"
            base += " LIMIT 50"
            rows = await db.fetch(base, member_id)
            return [dict(r) for r in rows]

    async def cancel_my_private_booking(
        self, user_id: str, booking_id: str, reason: str | None = None
    ) -> dict | None:
        """Cancel a private session booking, verifying ownership."""
        member = await self._get_member_by_user_id(user_id)
        if not member:
            raise ValueError("Member profile not found")
        async with get_tenant_db() as db:
            booking = await db.fetchrow(
                "SELECT member_id, status FROM private_bookings WHERE id = $1",
                booking_id,
            )
        if not booking:
            return None
        if str(booking["member_id"]) != str(member["id"]):
            raise PermissionError("Cannot cancel another member's booking")
        if booking["status"] in ("cancelled", "completed", "no_show"):
            raise ValueError(f"Booking is already {booking['status']}")
        return await _private_svc.cancel_booking(booking_id, reason)

    # ── AI Suggestions ─────────────────────────────────────────────────────

    async def get_suggestions(self, user_id: str) -> list[dict]:
        """Get AI-powered class suggestions based on member's booking history."""
        member = await self._get_member_by_user_id(user_id)
        if not member:
            return []

        member_id = str(member["id"])

        async with get_tenant_db() as db:
            # Get recent booking history (last 20 attended/confirmed classes)
            history_rows = await db.fetch(
                """
                SELECT ct.name AS class_type_name, ct.category, ct.level,
                       i.display_name AS instructor_name
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE b.member_id = $1
                  AND b.status IN ('attended', 'confirmed')
                  AND cs.starts_at < NOW()
                ORDER BY cs.starts_at DESC
                LIMIT 20
                """,
                member_id,
            )

            if not history_rows:
                return []

            # Get upcoming sessions (next 7 days)
            upcoming_rows = await db.fetch(
                """
                SELECT cs.id, cs.title, cs.starts_at,
                       ct.name AS class_type_name, ct.category, ct.level,
                       i.display_name AS instructor_name
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE cs.starts_at > NOW()
                  AND cs.starts_at < NOW() + INTERVAL '7 days'
                  AND cs.status = 'scheduled'
                ORDER BY cs.starts_at
                LIMIT 30
                """,
            )

            if not upcoming_rows:
                return []

        # Build history summary
        history_lines = []
        for r in history_rows:
            line = f"- {r['class_type_name'] or 'Unknown'} ({r['category'] or 'general'})"
            if r.get("level"):
                line += f", Level: {r['level']}"
            if r.get("instructor_name"):
                line += f", Instructor: {r['instructor_name']}"
            history_lines.append(line)
        history_text = "\n".join(history_lines)

        # Build upcoming schedule
        upcoming_map = {}
        schedule_text = ""
        for r in upcoming_rows:
            sid = str(r["id"])
            upcoming_map[sid] = dict(r)
            dt = r["starts_at"].strftime("%a %b %d %I:%M%p") if r.get("starts_at") else "TBD"
            schedule_text += (
                f"- ID:{sid} | {r['class_type_name'] or r.get('title', 'Class')} | "
                f"{dt} | {r.get('instructor_name', 'TBD')}\n"
            )

        system = (
            "You are a wellness advisor for a yoga/fitness studio. "
            "Based on a member's recent class history, suggest 3 upcoming classes they might enjoy. "
            "Return ONLY a JSON array with exactly 3 objects, each with: "
            '"session_id" (from the schedule), "reason" (1 sentence why they\'d like it). '
            "No markdown, no explanation — just the JSON array."
        )
        prompt = (
            f"Member's recent classes:\n{history_text}\n\n"
            f"Upcoming schedule:\n{schedule_text}\n\n"
            "Pick 3 classes from the upcoming schedule that best match this member's preferences."
        )

        from app.core.config import settings
        raw = await _ai_svc._call_claude(prompt, system, model=settings.ANTHROPIC_MODEL_FAST, max_tokens=512)

        # Parse AI response
        try:
            # Strip potential markdown code fences
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()

            picks = json.loads(clean)
            if not isinstance(picks, list):
                return []
        except (json.JSONDecodeError, ValueError):
            logger.warning("AI suggestions parse failed", raw=raw[:200])
            return []

        # Enrich with session details
        results = []
        for pick in picks[:3]:
            sid = pick.get("session_id", "")
            session = upcoming_map.get(sid)
            if not session:
                continue
            starts_at = session["starts_at"]
            results.append({
                "session_id": sid,
                "title": session.get("class_type_name") or session.get("title") or "Class",
                "starts_at": starts_at.isoformat() if hasattr(starts_at, "isoformat") else str(starts_at),
                "instructor_name": session.get("instructor_name"),
                "reason": pick.get("reason", ""),
            })

        return results
