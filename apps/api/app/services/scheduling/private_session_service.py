"""AuraFlow — Private Session Service

Manages private services, instructor availability, slot computation,
and 1-on-1 booking lifecycle.
"""
import uuid
from datetime import datetime, date, time, timedelta

from app.core.logging import logger
from app.db.session import get_tenant_db


_PRIVATE_SERVICE_UPDATE_COLS = {
    "name", "description", "duration_minutes", "price_cents",
    "buffer_before_minutes", "buffer_after_minutes", "max_per_day",
    "visibility", "required_membership_type_id", "is_virtual", "is_active",
    "package_sessions", "package_price_cents",
}


class PrivateSessionService:

    # ── Private Services CRUD ─────────────────────────────────────────────

    async def create_service(self, data: dict) -> dict:
        svc_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO private_services
                    (id, instructor_id, name, description, duration_minutes,
                     price_cents, buffer_before_minutes, buffer_after_minutes,
                     max_per_day, visibility, required_membership_type_id,
                     is_virtual)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING *
                """,
                svc_id, data["instructor_id"], data["name"],
                data.get("description"), data.get("duration_minutes", 60),
                data["price_cents"], data.get("buffer_before_minutes", 0),
                data.get("buffer_after_minutes", 15), data.get("max_per_day"),
                data.get("visibility", "members_only"),
                data.get("required_membership_type_id"),
                data.get("is_virtual", False),
            )
            logger.info("Private service created", service_id=svc_id, name=data["name"])
            return dict(row)

    async def update_service(self, service_id: str, data: dict) -> dict | None:
        data = {k: v for k, v in data.items() if k in _PRIVATE_SERVICE_UPDATE_COLS}
        async with get_tenant_db() as db:
            sets, params, idx = [], [], 1
            for k, v in data.items():
                sets.append(f"{k} = ${idx}")
                params.append(v)
                idx += 1
            if not sets:
                return await self.get_service(service_id)
            params.append(service_id)
            query = f"UPDATE private_services SET {', '.join(sets)} WHERE id = ${idx} AND is_active = TRUE RETURNING *"
            row = await db.fetchrow(query, *params)
            return dict(row) if row else None

    async def get_service(self, service_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow("SELECT * FROM private_services WHERE id = $1", service_id)
            return dict(row) if row else None

    async def list_services(self, instructor_id: str | None = None, active_only: bool = True) -> list[dict]:
        async with get_tenant_db() as db:
            conditions = []
            params = []
            idx = 1
            if instructor_id:
                conditions.append(f"instructor_id = ${idx}")
                params.append(instructor_id)
                idx += 1
            if active_only:
                conditions.append("is_active = TRUE")
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            rows = await db.fetch(
                f"SELECT * FROM private_services {where} ORDER BY name", *params
            )
            return [dict(r) for r in rows]

    async def deactivate_service(self, service_id: str) -> bool:
        async with get_tenant_db() as db:
            result = await db.execute(
                "UPDATE private_services SET is_active = FALSE WHERE id = $1", service_id
            )
            return "UPDATE 1" in result

    # ── Instructor Availability ───────────────────────────────────────────

    async def set_availability(self, instructor_id: str, slots: list[dict]) -> list[dict]:
        """Replace recurring availability for an instructor."""
        async with get_tenant_db() as db:
            # Remove old recurring availability
            await db.execute(
                "DELETE FROM instructor_availability WHERE instructor_id = $1 AND is_recurring = TRUE AND is_blocked = FALSE",
                instructor_id,
            )
            created = []
            for slot in slots:
                row = await db.fetchrow(
                    """
                    INSERT INTO instructor_availability
                        (id, instructor_id, day_of_week, start_time, end_time, is_recurring, is_blocked)
                    VALUES ($1, $2, $3, $4, $5, TRUE, FALSE)
                    RETURNING *
                    """,
                    str(uuid.uuid4()), instructor_id,
                    slot["day_of_week"], slot["start_time"], slot["end_time"],
                )
                created.append(dict(row))
            logger.info("Availability set", instructor_id=instructor_id, slots=len(created))
            return created

    async def get_availability(self, instructor_id: str) -> list[dict]:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM instructor_availability
                WHERE instructor_id = $1 AND is_recurring = TRUE AND is_blocked = FALSE
                ORDER BY day_of_week, start_time
                """,
                instructor_id,
            )
            return [dict(r) for r in rows]

    async def add_blocked_time(self, instructor_id: str, specific_date: date,
                                start_time: time, end_time: time) -> dict:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO instructor_availability
                    (id, instructor_id, day_of_week, start_time, end_time,
                     is_recurring, specific_date, is_blocked)
                VALUES ($1, $2, $3, $4, $5, FALSE, $6, TRUE)
                RETURNING *
                """,
                str(uuid.uuid4()), instructor_id,
                specific_date.weekday(),  # 0=Monday in Python
                start_time, end_time,
                specific_date,
            )
            logger.info("Blocked time added", instructor_id=instructor_id, date=str(specific_date))
            return dict(row)

    # ── Available Slots ───────────────────────────────────────────────────

    async def get_available_slots(
        self, instructor_id: str, service_id: str, target_date: date
    ) -> list[dict]:
        """Compute available 15-minute-interval slots for a given date.

        Availability windows and blocked times are stored in local time.
        Bookings are stored in UTC. We convert bookings to local time
        (America/Los_Angeles) before comparing against availability.
        """
        from zoneinfo import ZoneInfo

        service = await self.get_service(service_id)
        if not service:
            return []

        duration = service["duration_minutes"]
        buffer_before = service.get("buffer_before_minutes") or 0
        buffer_after = service.get("buffer_after_minutes") or 0
        total_block = buffer_before + duration + buffer_after

        # Get recurring availability for this day of week
        # Python weekday: Monday=0..Sunday=6 → DB stores same
        dow = target_date.weekday()
        local_tz = ZoneInfo("America/Los_Angeles")

        async with get_tenant_db() as db:
            avail_rows = await db.fetch(
                """
                SELECT start_time, end_time FROM instructor_availability
                WHERE instructor_id = $1 AND day_of_week = $2
                  AND is_recurring = TRUE AND is_blocked = FALSE
                """,
                instructor_id, dow,
            )

            # Get blocked times for the specific date
            blocked_rows = await db.fetch(
                """
                SELECT start_time, end_time FROM instructor_availability
                WHERE instructor_id = $1 AND specific_date = $2 AND is_blocked = TRUE
                """,
                instructor_id, target_date,
            )

            # Get existing bookings for the date — query wide UTC range to
            # catch bookings that straddle midnight when converted to local time
            day_start_local = datetime.combine(target_date, time(0, 0), tzinfo=local_tz)
            day_end_local = datetime.combine(target_date + timedelta(days=1), time(0, 0), tzinfo=local_tz)
            day_start_utc = day_start_local.astimezone(ZoneInfo("UTC"))
            day_end_utc = day_end_local.astimezone(ZoneInfo("UTC"))

            booking_rows = await db.fetch(
                """
                SELECT starts_at, ends_at FROM private_bookings
                WHERE instructor_id = $1
                  AND starts_at >= $2 AND starts_at < $3
                  AND status NOT IN ('cancelled')
                """,
                instructor_id, day_start_utc.replace(tzinfo=None), day_end_utc.replace(tzinfo=None),
            )

        # Build availability windows
        windows = []
        for r in avail_rows:
            windows.append((r["start_time"], r["end_time"]))

        # Remove blocked windows
        blocked = [(r["start_time"], r["end_time"]) for r in blocked_rows]

        # Build booked windows (with buffer) — convert UTC bookings to local time
        booked = []
        for r in booking_rows:
            # Bookings are stored as UTC; convert to local time for comparison
            starts_utc = r["starts_at"]
            ends_utc = r["ends_at"]
            if starts_utc.tzinfo is None:
                starts_utc = starts_utc.replace(tzinfo=ZoneInfo("UTC"))
            if ends_utc.tzinfo is None:
                ends_utc = ends_utc.replace(tzinfo=ZoneInfo("UTC"))
            book_start = starts_utc.astimezone(local_tz).time()
            book_end = ends_utc.astimezone(local_tz).time()
            # Add buffer around bookings
            effective_start = (datetime.combine(target_date, book_start) - timedelta(minutes=buffer_after)).time()
            effective_end = (datetime.combine(target_date, book_end) + timedelta(minutes=buffer_before)).time()
            booked.append((effective_start, effective_end))

        # Generate 15-min slots and check availability
        slots = []
        for win_start, win_end in windows:
            current = datetime.combine(target_date, win_start)
            end_dt = datetime.combine(target_date, win_end)

            while current + timedelta(minutes=total_block) <= end_dt:
                slot_start = (current + timedelta(minutes=buffer_before)).time()
                slot_end = (current + timedelta(minutes=buffer_before + duration)).time()

                # Check if slot overlaps with blocked or booked times
                conflict = False
                slot_block_start = current.time()
                slot_block_end = (current + timedelta(minutes=total_block)).time()

                for b_start, b_end in blocked + booked:
                    if slot_block_start < b_end and slot_block_end > b_start:
                        conflict = True
                        break

                if not conflict:
                    slots.append({
                        "start_time": slot_start.isoformat(),
                        "end_time": slot_end.isoformat(),
                        "duration_minutes": duration,
                    })

                current += timedelta(minutes=15)

        return slots

    # ── Booking Lifecycle ─────────────────────────────────────────────────

    async def book_session(self, data: dict) -> dict:
        """Book a private session. Checks for conflicts."""
        booking_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            service = await db.fetchrow(
                "SELECT * FROM private_services WHERE id = $1 AND is_active = TRUE",
                data["private_service_id"],
            )
            if not service:
                raise ValueError("Private service not found or inactive")

            starts_at = data["starts_at"]
            if isinstance(starts_at, str):
                starts_at = datetime.fromisoformat(starts_at)
            # If naive datetime (no timezone), treat as Pacific and convert to UTC
            if starts_at.tzinfo is None:
                from zoneinfo import ZoneInfo
                starts_at = starts_at.replace(tzinfo=ZoneInfo("America/Los_Angeles")).astimezone(ZoneInfo("UTC"))

            duration = service["duration_minutes"]
            ends_at = starts_at + timedelta(minutes=duration)
            buffer_after = service.get("buffer_after_minutes") or 0

            # Check for double-booking (including buffer)
            conflict = await db.fetchrow(
                """
                SELECT id FROM private_bookings
                WHERE instructor_id = $1
                  AND status NOT IN ('cancelled')
                  AND starts_at < $3 AND ends_at > $2
                """,
                data["instructor_id"],
                starts_at - timedelta(minutes=buffer_after),
                ends_at + timedelta(minutes=buffer_after),
            )
            if conflict:
                raise ValueError("Time slot conflicts with an existing booking")

            # Check max per day
            if service.get("max_per_day"):
                day_start = datetime.combine(starts_at.date(), time(0, 0))
                day_end = day_start + timedelta(days=1)
                count = await db.fetchval(
                    """
                    SELECT COUNT(*) FROM private_bookings
                    WHERE instructor_id = $1 AND private_service_id = $2
                      AND starts_at >= $3 AND starts_at < $4
                      AND status NOT IN ('cancelled')
                    """,
                    data["instructor_id"], data["private_service_id"],
                    day_start, day_end,
                )
                if count >= service["max_per_day"]:
                    raise ValueError("Maximum bookings per day reached for this service")

            # Pricing resolution. Three credit sources, in order:
            #   1. Banked credit (member_credits) — staff explicitly passes
            #      apply_credit_id when creating from the new "Apply
            #      credit" picker.
            #   2. Membership pack (member_memberships.classes_remaining)
            #      — auto-applied when the service has a required_membership_type.
            #   3. Otherwise full price.
            #
            # All pricing-resolution writes + the booking INSERT happen
            # inside one transaction so a race can't double-spend a
            # credit (credit gets marked used but booking insert fails).
            price = service["price_cents"]
            membership_used_id = None
            applied_credit_id = data.get("apply_credit_id")
            initial_payment_status = "unpaid"

            # All pricing writes + the booking INSERT happen inside one
            # transaction so a race can't double-spend a credit (credit
            # gets marked used but booking insert fails).
            async with db.transaction():
                if applied_credit_id:
                    from app.services.members.member_credit_service import (
                        MemberCreditService,
                    )
                    await MemberCreditService().apply_credit(
                        credit_id=str(applied_credit_id),
                        member_id=str(data["member_id"]),
                        booking_id=booking_id,
                        booking_table="private_bookings",
                        db=db,
                    )
                    price = 0
                    initial_payment_status = "paid"
                    logger.info(
                        "Booked via banked credit",
                        booking_id=booking_id, credit_id=applied_credit_id,
                    )
                else:
                    req_type_id = service.get("required_membership_type_id")
                    if req_type_id:
                        pack = await db.fetchrow(
                            """
                            SELECT id, classes_remaining FROM member_memberships
                            WHERE member_id = $1 AND membership_type_id = $2
                              AND status = 'active'
                              AND (classes_remaining > 0 OR classes_remaining IS NULL)
                            ORDER BY created_at ASC LIMIT 1
                            FOR UPDATE
                            """,
                            data["member_id"], str(req_type_id),
                        )
                        if pack and pack.get("classes_remaining") and pack["classes_remaining"] > 0:
                            await db.execute(
                                "UPDATE member_memberships SET classes_remaining = classes_remaining - 1, updated_at = NOW() WHERE id = $1",
                                str(pack["id"]),
                            )
                            price = 0
                            initial_payment_status = "paid"
                            membership_used_id = str(pack["id"])
                            logger.info(
                                "Pack credit deducted",
                                pack_id=str(pack["id"]),
                                remaining=pack["classes_remaining"] - 1,
                            )

                row = await db.fetchrow(
                    """
                    INSERT INTO private_bookings
                        (id, member_id, instructor_id, private_service_id,
                         starts_at, ends_at, status, is_virtual, intake_notes,
                         price_cents, payment_status)
                    VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7, $8, $9, $10)
                    RETURNING *
                    """,
                    booking_id, data["member_id"], data["instructor_id"],
                    data["private_service_id"], starts_at, ends_at,
                    service.get("is_virtual", False),
                    data.get("intake_notes"),
                    price, initial_payment_status,
                )
            logger.info(
                "Private session booked",
                booking_id=booking_id,
                member_id=data["member_id"],
                instructor_id=data["instructor_id"],
            )

            # Fire-and-forget webhook: private_session.booked
            try:
                import asyncio
                from app.services.webhooks.webhook_delivery_service import WebhookDeliveryService
                asyncio.create_task(WebhookDeliveryService().fire_event("private_session.booked", {
                    "booking_id": booking_id,
                    "member_id": data["member_id"],
                    "instructor_id": data["instructor_id"],
                    "private_service_id": data["private_service_id"],
                    "starts_at": str(starts_at),
                }))
            except Exception:
                pass

            return dict(row)

    async def get_booking(self, booking_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT pb.*, ps.name AS service_name, ps.duration_minutes,
                       m.first_name AS member_first_name, m.last_name AS member_last_name,
                       i.display_name AS instructor_name
                FROM private_bookings pb
                JOIN private_services ps ON ps.id = pb.private_service_id
                JOIN members m ON m.id = pb.member_id
                JOIN instructors i ON i.id = pb.instructor_id
                WHERE pb.id = $1
                """,
                booking_id,
            )
            return dict(row) if row else None

    async def list_bookings(
        self,
        instructor_id: str | None = None,
        member_id: str | None = None,
        status: str | None = None,
        payment_status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[dict]:
        async with get_tenant_db() as db:
            conditions = []
            params = []
            idx = 1
            if instructor_id:
                conditions.append(f"pb.instructor_id = ${idx}")
                params.append(instructor_id)
                idx += 1
            if member_id:
                conditions.append(f"pb.member_id = ${idx}")
                params.append(member_id)
                idx += 1
            if status:
                conditions.append(f"pb.status = ${idx}")
                params.append(status)
                idx += 1
            if payment_status:
                conditions.append(f"pb.payment_status = ${idx}")
                params.append(payment_status)
                idx += 1
            if from_date:
                conditions.append(f"pb.starts_at >= ${idx}")
                params.append(datetime.combine(from_date, time(0, 0)))
                idx += 1
            if to_date:
                conditions.append(f"pb.starts_at < ${idx}")
                params.append(datetime.combine(to_date, time(23, 59, 59)))
                idx += 1

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            rows = await db.fetch(
                f"""
                SELECT pb.*, ps.name AS service_name, ps.duration_minutes,
                       m.first_name AS member_first_name, m.last_name AS member_last_name,
                       i.display_name AS instructor_name
                FROM private_bookings pb
                JOIN private_services ps ON ps.id = pb.private_service_id
                JOIN members m ON m.id = pb.member_id
                JOIN instructors i ON i.id = pb.instructor_id
                {where}
                ORDER BY pb.starts_at DESC
                """,
                *params,
            )
            return [dict(r) for r in rows]

    async def confirm_booking(self, booking_id: str, mark_paid: bool = True) -> dict | None:
        async with get_tenant_db() as db:
            if mark_paid:
                row = await db.fetchrow(
                    """
                    UPDATE private_bookings
                    SET status = 'confirmed', payment_status = 'paid', updated_at = NOW()
                    WHERE id = $1 AND status = 'pending'
                    RETURNING *
                    """,
                    booking_id,
                )
            else:
                row = await db.fetchrow(
                    """
                    UPDATE private_bookings
                    SET status = 'confirmed', updated_at = NOW()
                    WHERE id = $1 AND status = 'pending'
                    RETURNING *
                    """,
                    booking_id,
                )
            if row:
                logger.info("Private session confirmed", booking_id=booking_id)
            return dict(row) if row else None

    async def cancel_booking(
        self,
        booking_id: str,
        reason: str | None = None,
        cancelled_by_role: str | None = None,
        cancelled_by_user_id: str | None = None,
    ) -> dict | None:
        """Cancel a private session booking.

        When cancelled_by_role == 'instructor', the client's paid credit
        is preserved by inserting a member_credits row for the booking's
        price. Member cancellations and unmarked cancellations forfeit
        the credit (current policy).
        """
        if cancelled_by_role is not None and cancelled_by_role not in (
            "instructor", "member", "staff"
        ):
            raise ValueError(
                f"cancelled_by_role must be instructor|member|staff, got {cancelled_by_role!r}"
            )

        async with get_tenant_db() as db:
            async with db.transaction():
                row = await db.fetchrow(
                    """
                    UPDATE private_bookings
                    SET status = 'cancelled', cancelled_at = NOW(),
                        cancellation_reason = $2,
                        cancelled_by_role = $3,
                        updated_at = NOW()
                    WHERE id = $1 AND status IN ('pending', 'confirmed')
                    RETURNING *
                    """,
                    booking_id, reason, cancelled_by_role,
                )
                if not row:
                    return None

                granted_credit = None
                # Preserve the client's credit when the studio side is at
                # fault. payment_status='paid' means they actually paid
                # (or used an earlier credit); status='unpaid'/'pending'
                # had nothing collected so there's nothing to bank.
                if (cancelled_by_role == "instructor"
                        and row["payment_status"] in ("paid", "comp")
                        and row["price_cents"] and row["price_cents"] > 0):
                    from app.services.members.member_credit_service import (
                        MemberCreditService,
                    )
                    granted_credit = await MemberCreditService().grant_credit(
                        member_id=str(row["member_id"]),
                        amount_cents=int(row["price_cents"]),
                        source="instructor_cancellation",
                        service_filter="private_session",
                        source_ref_id=str(row["id"]),
                        notes=reason,
                        granted_by_user_id=cancelled_by_user_id,
                        db=db,
                    )

        logger.info(
            "Private session cancelled",
            booking_id=booking_id, cancelled_by_role=cancelled_by_role,
            credit_granted=bool(granted_credit),
        )
        result = dict(row)
        if granted_credit:
            result["granted_credit_id"] = granted_credit["id"]
            result["granted_credit_amount_cents"] = granted_credit["amount_cents"]
        return result

    async def complete_booking(self, booking_id: str, instructor_notes: str | None = None) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE private_bookings
                SET status = 'completed', instructor_notes = COALESCE($2, instructor_notes),
                    updated_at = NOW()
                WHERE id = $1 AND status IN ('pending', 'confirmed')
                RETURNING *
                """,
                booking_id, instructor_notes,
            )
            if row:
                logger.info("Private session completed", booking_id=booking_id)
            return dict(row) if row else None
