"""AuraFlow — Course & Workshop Service

Manages courses (workshops, teacher trainings, retreats), sessions,
enrollment lifecycle, and attendance tracking.
"""
import uuid
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db
import base64


def _decode_flyer_data_url(data_url: str | None) -> tuple[bytes | None, str | None]:
    """Parse a data: URL (data:image/png;base64,XXX) into (bytes, mime).
    Empty string clears the flyer (None, None). None means 'do not touch'.
    Anything malformed returns (None, None) silently."""
    if data_url is None:
        return (None, None)  # caller treats as 'no change'
    if data_url == "":
        return (b"", "")     # caller treats as 'clear'
    if not data_url.startswith("data:") or ";base64," not in data_url:
        return (None, None)
    try:
        header, payload = data_url.split(";base64,", 1)
        mime = header.removeprefix("data:") or "image/jpeg"
        return (base64.b64decode(payload), mime)
    except Exception:
        return (None, None)


def _encode_flyer_to_data_url(blob: bytes | None, mime: str | None) -> str | None:
    if not blob:
        return None
    return f"data:{mime or 'image/jpeg'};base64,{base64.b64encode(blob).decode('ascii')}"


def _row_with_flyer_url(row) -> dict | None:
    """Convert flyer_image_data bytes -> flyer_data_url for JSON return."""
    if row is None:
        return None
    d = dict(row)
    blob = d.pop("flyer_image_data", None)
    mime = d.get("flyer_image_mime")
    d["flyer_data_url"] = _encode_flyer_to_data_url(blob, mime)
    return d



_COURSE_UPDATE_COLS = {
    "title", "description", "type", "instructor_id", "guest_instructor_id",
    "price_cents",
    "early_bird_price_cents", "early_bird_deadline", "capacity",
    "min_enrollment", "location", "is_virtual", "image_url",
    "prerequisites", "registration_opens", "registration_closes",
    "starts_at", "ends_at",
}


def _validate_guest_only_for_workshops(data: dict) -> None:
    """CA labor law gate: a 1099 guest_instructor can only be attached
    to a workshop. Non-workshop course types must use a staff
    instructor_id only. The DB has a CHECK constraint as the last line
    of defense; this is the friendlier error before it ever hits the
    constraint."""
    if data.get("guest_instructor_id") and data.get("type") not in (None, "workshop"):
        raise ValueError(
            "Guest instructors can only teach workshops. California labor "
            "law prohibits 1099 contractors from teaching classes, courses, "
            "teacher trainings, or retreats — assign a staff instructor_id "
            "instead."
        )
_COURSE_SESSION_UPDATE_COLS = {
    "title", "session_number", "starts_at", "ends_at", "location", "is_virtual",
}


class CourseService:

    # ── Course CRUD ──────────────────────────────────────────────────────

    async def create_course(self, data: dict) -> dict:
        _validate_guest_only_for_workshops(data)
        course_id = str(uuid.uuid4())
        flyer_blob, flyer_mime = _decode_flyer_data_url(data.get("flyer_data_url"))
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO courses
                    (id, studio_id, title, description, type, instructor_id,
                     guest_instructor_id,
                     price_cents, early_bird_price_cents, early_bird_deadline,
                     capacity, min_enrollment, location, is_virtual, image_url,
                     prerequisites, registration_opens, registration_closes,
                     starts_at, ends_at,
                     flyer_image_data, flyer_image_mime)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                        $13, $14, $15, $16, $17, $18, $19, $20, $21, $22)
                RETURNING *
                """,
                course_id, data.get("studio_id"), data["title"],
                data.get("description"), data.get("type", "workshop"),
                data.get("instructor_id"),
                data.get("guest_instructor_id"),
                data.get("price_cents", 0),
                data.get("early_bird_price_cents"), data.get("early_bird_deadline"),
                # Default capacity to 20 if not provided — every workshop
                # should have a capacity for spots-available display logic;
                # NULL led to "null spots available" rendering in the
                # portal/marketing layers.
                data.get("capacity") or 20, data.get("min_enrollment"),
                data.get("location"), data.get("is_virtual", False),
                data.get("image_url"), data.get("prerequisites"),
                data.get("registration_opens"), data.get("registration_closes"),
                data.get("starts_at"), data.get("ends_at"),
                flyer_blob if flyer_blob else None,
                flyer_mime if flyer_mime else None,
            )
            logger.info("Course created", course_id=course_id, title=data["title"])
            return _row_with_flyer_url(row)

    async def get_course(self, course_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT c.*, i.display_name AS instructor_name,
                       gi.name AS guest_instructor_name,
                       gi.photo_url AS guest_instructor_photo_url,
                       gi.bio AS guest_instructor_bio,
                       gi.revenue_share_percent_to_guest,
                       (SELECT COUNT(*) FROM course_enrollments ce
                        WHERE ce.course_id = c.id AND ce.status = 'enrolled') AS enrolled_count
                FROM courses c
                LEFT JOIN instructors i ON i.id = c.instructor_id
                LEFT JOIN guest_instructors gi ON gi.id = c.guest_instructor_id
                WHERE c.id = $1
                """,
                course_id,
            )
            return _row_with_flyer_url(row) if row else None

    async def list_courses(
        self, status: str | None = None, course_type: str | None = None
    ) -> list[dict]:
        async with get_tenant_db() as db:
            conditions = []
            params = []
            idx = 1
            if status:
                conditions.append(f"c.status = ${idx}")
                params.append(status)
                idx += 1
            if course_type:
                conditions.append(f"c.type = ${idx}")
                params.append(course_type)
                idx += 1
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            rows = await db.fetch(
                f"""
                SELECT c.*, i.display_name AS instructor_name,
                       gi.name AS guest_instructor_name,
                       gi.photo_url AS guest_instructor_photo_url,
                       gi.bio AS guest_instructor_bio,
                       gi.revenue_share_percent_to_guest,
                       (SELECT COUNT(*) FROM course_enrollments ce
                        WHERE ce.course_id = c.id AND ce.status = 'enrolled') AS enrolled_count
                FROM courses c
                LEFT JOIN instructors i ON i.id = c.instructor_id
                LEFT JOIN guest_instructors gi ON gi.id = c.guest_instructor_id
                {where}
                ORDER BY c.created_at DESC
                """,
                *params,
            )
            return [_row_with_flyer_url(r) for r in rows]

    async def update_course(self, course_id: str, data: dict) -> dict | None:
        # Pull flyer out — it lives in two columns (bytea + mime) and goes
        # in a separate UPDATE so the dynamic field-list builder below stays
        # simple. Empty string clears the flyer; absence means leave alone.
        flyer_data_url = data.pop("flyer_data_url", None)
        flyer_blob, flyer_mime = _decode_flyer_data_url(flyer_data_url)
        if flyer_data_url is not None:
            async with get_tenant_db() as db:
                if flyer_data_url == "":
                    await db.execute(
                        "UPDATE courses SET flyer_image_data = NULL, flyer_image_mime = NULL, updated_at = NOW() WHERE id = $1",
                        course_id,
                    )
                elif flyer_blob:
                    await db.execute(
                        "UPDATE courses SET flyer_image_data = $1, flyer_image_mime = $2, updated_at = NOW() WHERE id = $3",
                        flyer_blob, flyer_mime, course_id,
                    )
        # If the caller is changing type or guest_instructor_id, validate
        # the combination against the workshop-only rule before issuing
        # the UPDATE. The merge with the existing row handles partial
        # updates: e.g. changing only `type` to non-workshop on a course
        # that already has a guest_instructor_id should be rejected.
        if "type" in data or "guest_instructor_id" in data:
            existing = await self.get_course(course_id)
            if existing:
                merged = {
                    "type": data.get("type", existing.get("type")),
                    "guest_instructor_id": data.get(
                        "guest_instructor_id", existing.get("guest_instructor_id")
                    ),
                }
                _validate_guest_only_for_workshops(merged)

        data = {k: v for k, v in data.items() if k in _COURSE_UPDATE_COLS}
        async with get_tenant_db() as db:
            sets, params, idx = [], [], 1
            for k, v in data.items():
                sets.append(f"{k} = ${idx}")
                params.append(v)
                idx += 1
            if not sets:
                return await self.get_course(course_id)
            sets.append(f"updated_at = ${idx}")
            params.append(datetime.now(timezone.utc))
            idx += 1
            params.append(course_id)
            query = f"UPDATE courses SET {', '.join(sets)} WHERE id = ${idx} RETURNING *"
            row = await db.fetchrow(query, *params)
            return _row_with_flyer_url(row) if row else None

    async def publish_course(self, course_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE courses
                SET status = 'published', updated_at = NOW()
                WHERE id = $1 AND status = 'draft'
                RETURNING *
                """,
                course_id,
            )
            if row:
                logger.info("Course published", course_id=course_id)
            return _row_with_flyer_url(row) if row else None

    async def cancel_course(self, course_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE courses
                SET status = 'cancelled', updated_at = NOW()
                WHERE id = $1 AND status IN ('draft', 'published')
                RETURNING *
                """,
                course_id,
            )
            if row:
                # Also withdraw all enrolled members
                await db.execute(
                    """
                    UPDATE course_enrollments
                    SET status = 'withdrawn', withdrawn_at = NOW(), updated_at = NOW()
                    WHERE course_id = $1 AND status = 'enrolled'
                    """,
                    course_id,
                )
                logger.info("Course cancelled", course_id=course_id)
            return _row_with_flyer_url(row) if row else None

    async def complete_course(self, course_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE courses
                SET status = 'completed', updated_at = NOW()
                WHERE id = $1 AND status IN ('published', 'in_progress')
                RETURNING *
                """,
                course_id,
            )
            if row:
                # Mark enrolled members as completed
                await db.execute(
                    """
                    UPDATE course_enrollments
                    SET status = 'completed', completed_at = NOW(), updated_at = NOW()
                    WHERE course_id = $1 AND status = 'enrolled'
                    """,
                    course_id,
                )
                logger.info("Course completed", course_id=course_id)
            return _row_with_flyer_url(row) if row else None

    async def delete_course(self, course_id: str) -> bool:
        """Hard-delete a course and its sessions/enrollments."""
        async with get_tenant_db() as db:
            # Delete attendance records for course sessions
            await db.execute(
                """
                DELETE FROM course_session_attendance
                WHERE course_session_id IN (SELECT id FROM course_sessions WHERE course_id = $1)
                """,
                course_id,
            )
            # Delete sessions
            await db.execute(
                "DELETE FROM course_sessions WHERE course_id = $1", course_id
            )
            # Delete enrollments
            await db.execute(
                "DELETE FROM course_enrollments WHERE course_id = $1", course_id
            )
            # Delete course
            result = await db.execute(
                "DELETE FROM courses WHERE id = $1", course_id
            )
            deleted = "DELETE 1" in result
            if deleted:
                logger.info("Course deleted", course_id=course_id)
            return deleted

    # ── Sessions ─────────────────────────────────────────────────────────

    async def add_session(self, course_id: str, data: dict) -> dict:
        session_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            # Get next session number
            max_num = await db.fetchval(
                "SELECT COALESCE(MAX(session_number), 0) FROM course_sessions WHERE course_id = $1",
                course_id,
            )
            row = await db.fetchrow(
                """
                INSERT INTO course_sessions
                    (id, course_id, title, session_number, starts_at, ends_at,
                     location, is_virtual)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
                """,
                session_id, course_id, data.get("title"),
                max_num + 1,
                data["starts_at"], data["ends_at"],
                data.get("location"), data.get("is_virtual", False),
            )
            return dict(row)

    async def update_session(self, session_id: str, data: dict) -> dict | None:
        data = {k: v for k, v in data.items() if k in _COURSE_SESSION_UPDATE_COLS}
        async with get_tenant_db() as db:
            sets, params, idx = [], [], 1
            for k, v in data.items():
                sets.append(f"{k} = ${idx}")
                params.append(v)
                idx += 1
            if not sets:
                row = await db.fetchrow(
                    "SELECT * FROM course_sessions WHERE id = $1", session_id
                )
                return dict(row) if row else None
            sets.append(f"updated_at = ${idx}")
            params.append(datetime.now(timezone.utc))
            idx += 1
            params.append(session_id)
            query = f"UPDATE course_sessions SET {', '.join(sets)} WHERE id = ${idx} RETURNING *"
            row = await db.fetchrow(query, *params)
            return dict(row) if row else None

    async def delete_session(self, session_id: str) -> bool:
        async with get_tenant_db() as db:
            result = await db.execute(
                "DELETE FROM course_sessions WHERE id = $1", session_id
            )
            return "DELETE 1" in result

    async def list_sessions(self, course_id: str) -> list[dict]:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM course_sessions
                WHERE course_id = $1
                ORDER BY session_number
                """,
                course_id,
            )
            return [dict(r) for r in rows]

    # ── Enrollment ───────────────────────────────────────────────────────

    async def enroll_member(self, course_id: str, member_id: str) -> dict:
        enrollment_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            # Get course for capacity and pricing
            course = await db.fetchrow(
                "SELECT * FROM courses WHERE id = $1", course_id
            )
            if not course:
                raise ValueError("Course not found")
            if course["status"] not in ("published", "in_progress"):
                raise ValueError(f"Cannot enroll in course with status '{course['status']}'")

            # Check capacity
            if course["capacity"]:
                enrolled = await db.fetchval(
                    "SELECT COUNT(*) FROM course_enrollments WHERE course_id = $1 AND status = 'enrolled'",
                    course_id,
                )
                if enrolled >= course["capacity"]:
                    raise ValueError("Course is at capacity")

            # Check duplicate
            existing = await db.fetchrow(
                "SELECT id FROM course_enrollments WHERE course_id = $1 AND member_id = $2 AND status = 'enrolled'",
                course_id, member_id,
            )
            if existing:
                raise ValueError("Member is already enrolled in this course")

            # Determine price (early bird vs regular)
            price = course["price_cents"]
            now = datetime.now(timezone.utc)
            deadline = course.get("early_bird_deadline")
            if deadline and deadline.tzinfo:
                now = now.replace(tzinfo=deadline.tzinfo)
            if (
                course.get("early_bird_price_cents")
                and deadline
                and now < deadline
            ):
                price = course["early_bird_price_cents"]

            row = await db.fetchrow(
                """
                INSERT INTO course_enrollments
                    (id, course_id, member_id, status, paid_price_cents)
                VALUES ($1, $2, $3, 'enrolled', $4)
                RETURNING *
                """,
                enrollment_id, course_id, member_id, price,
            )
            logger.info(
                "Member enrolled in course",
                enrollment_id=enrollment_id,
                course_id=course_id,
                member_id=member_id,
            )
            return dict(row)

    async def withdraw_member(self, enrollment_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE course_enrollments
                SET status = 'withdrawn', withdrawn_at = NOW(), updated_at = NOW()
                WHERE id = $1 AND status = 'enrolled'
                RETURNING *
                """,
                enrollment_id,
            )
            if row:
                logger.info("Member withdrawn from course", enrollment_id=enrollment_id)
            return dict(row) if row else None

    async def list_enrollments(self, course_id: str) -> list[dict]:
        from app.services.members.phi_helpers import decrypt_phone
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT ce.*, m.first_name, m.last_name, m.email,
                       m.phone_enc
                FROM course_enrollments ce
                JOIN members m ON m.id = ce.member_id
                WHERE ce.course_id = $1
                ORDER BY ce.enrolled_at
                """,
                course_id,
            )
            # Decrypt phone before returning so the roster modal can
            # display contact info — survives the Phase C plaintext drop.
            out = []
            for r in rows:
                d = dict(r)
                d["phone"] = decrypt_phone(d)
                d.pop("phone_enc", None)
                out.append(d)
            return out

    # ── Attendance ───────────────────────────────────────────────────────

    async def record_attendance(
        self, session_id: str, member_id: str, status: str = "attended"
    ) -> dict:
        att_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO course_session_attendance
                    (id, course_session_id, member_id, status)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (course_session_id, member_id)
                DO UPDATE SET status = EXCLUDED.status
                RETURNING *
                """,
                att_id, session_id, member_id, status,
            )
            return dict(row)

    async def get_session_attendance(self, session_id: str) -> list[dict]:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT csa.*, m.first_name, m.last_name
                FROM course_session_attendance csa
                JOIN members m ON m.id = csa.member_id
                WHERE csa.course_session_id = $1
                ORDER BY m.last_name
                """,
                session_id,
            )
            return [dict(r) for r in rows]
