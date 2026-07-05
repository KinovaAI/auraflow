"""AuraFlow — Booking Service

Class booking, cancellation, waitlist management, check-in, and guest booking.
Sends email/SMS notifications on booking events (fire-and-forget).
"""
import uuid
from datetime import datetime

from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.email.email_service import EmailService
from app.services.marketing.campaign_service import SmsService
from app.services.ai.milestone_service import MilestoneService
from app.services.members.phi_helpers import decrypt_phone
from app.services.memberships.membership_service import MembershipService


class BookingError(ValueError):
    """Booking failure with a machine-readable error code.

    Subclasses ValueError so existing ``except ValueError`` handlers
    continue to work while callers can optionally inspect ``code``.
    """

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class BookingService:

    def __init__(self):
        self._email_svc = EmailService()
        self._sms_svc = SmsService()
        self._membership_svc = MembershipService()

    async def _get_notification_data(self, db, booking_id: str) -> dict | None:
        """Fetch enriched booking data for email/SMS notifications."""
        row = await db.fetchrow(
            """
            SELECT b.member_id, b.status,
                   cs.title AS session_title, cs.starts_at, cs.ends_at,
                   m.first_name, m.last_name, m.email, m.phone_enc,
                   m.email_opt_in, m.sms_opt_in
            FROM bookings b
            JOIN class_sessions cs ON cs.id = b.class_session_id
            JOIN members m ON m.id = b.member_id
            WHERE b.id = $1
            """,
            booking_id,
        )
        if not row:
            return None
        info = dict(row)
        info["phone"] = decrypt_phone(info)
        info.pop("phone_enc", None)
        return info

    async def _send_booking_notifications(self, db, booking_id: str, event: str) -> None:
        """Fire-and-forget email + SMS for a booking event."""
        try:
            info = await self._get_notification_data(db, booking_id)
            if not info:
                return

            member_id = str(info["member_id"])
            name = f"{info['first_name']} {info['last_name']}"
            title = info["session_title"]
            dt = info["starts_at"]
            # Convert UTC to Pacific for display
            if dt:
                from zoneinfo import ZoneInfo
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                dt = dt.astimezone(ZoneInfo("America/Los_Angeles"))
            date_str = dt.strftime("%b %d, %Y") if dt else ""
            time_str = dt.strftime("%-I:%M %p") if dt else ""

            if event == "confirmed" and info.get("email_opt_in", True):
                await self._email_svc.send_booking_confirmation(
                    member_id=member_id, to_email=info["email"],
                    member_name=name, class_title=title,
                    session_date=date_str, session_time=time_str,
                )
            elif event == "cancelled" and info.get("email_opt_in", True):
                await self._email_svc.send_booking_cancellation(
                    member_id=member_id, to_email=info["email"],
                    member_name=name, class_title=title,
                    session_date=date_str,
                )
            elif event == "waitlist_promotion" and info.get("email_opt_in", True):
                await self._email_svc.send_waitlist_promotion(
                    member_id=member_id, to_email=info["email"],
                    member_name=name, class_title=title,
                    session_date=date_str, session_time=time_str,
                )

            # SMS for members with phone + opt-in
            if info.get("phone") and info.get("sms_opt_in", True):
                if event == "confirmed":
                    await self._sms_svc.send_booking_confirmation(
                        member_id=member_id, to_phone=info["phone"],
                        member_name=name, class_title=title,
                        session_date=date_str, session_time=time_str,
                    )
                elif event == "cancelled":
                    await self._sms_svc.send_booking_cancellation(
                        member_id=member_id, to_phone=info["phone"],
                        member_name=name, class_title=title,
                        session_date=date_str,
                    )
                elif event == "waitlist_promotion":
                    await self._sms_svc.send_waitlist_promotion(
                        member_id=member_id, to_phone=info["phone"],
                        member_name=name, class_title=title,
                        session_date=date_str, session_time=time_str,
                    )
        except Exception as e:
            logger.warning("Booking notification failed (non-fatal)", error=str(e), booking_id=booking_id)

    async def book_class(self, data: dict) -> dict:
        """Book a member into a class session. Handles capacity/waitlist logic.

        Uses SELECT ... FOR UPDATE inside a transaction to prevent double-booking
        race conditions when concurrent requests check capacity simultaneously.

        Raises ValueError with specific error codes:
          - session_not_found: Session does not exist
          - session_cancelled: Session has been cancelled
          - already_booked: Member already has an active booking for this session
          - no_membership: Member lacks an eligible membership
          - waiver_required: Liability waiver not signed
          - class_full: Class and waitlist are both at capacity
        """
        booking_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            # Use a transaction with row-level locking to prevent double-booking
            async with db.transaction():
                # Lock the session row to prevent concurrent capacity checks
                session = await db.fetchrow(
                    """
                    SELECT cs.capacity, cs.waitlist_capacity, cs.status,
                        (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id
                            AND status = 'confirmed') AS booked_count,
                        (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id
                            AND status = 'waitlisted') AS waitlist_count
                    FROM class_sessions cs WHERE cs.id = $1
                    FOR UPDATE OF cs
                    """,
                    data["class_session_id"],
                )
                if not session:
                    raise BookingError("session_not_found", "Session not found")
                if session["status"] == "cancelled":
                    raise BookingError("session_cancelled", "Session is cancelled")

                # Check for duplicate booking (any prior row for this
                # member+session). The bookings table has a UNIQUE
                # constraint on (member_id, class_session_id), so a plain
                # INSERT on rebook-after-cancel would 500 with a
                # UniqueViolationError — Don hit this trying to book Jill
                # Lloyd back into a class she had cancelled hours earlier.
                # If the prior row is cancelled, we'll revive it later in
                # this method instead of inserting a new row.
                existing_booking_id = None
                if data.get("member_id"):
                    existing = await db.fetchrow(
                        """
                        SELECT id, status FROM bookings
                        WHERE member_id = $1 AND class_session_id = $2
                        """,
                        data["member_id"], data["class_session_id"],
                    )
                    if existing and existing["status"] in ("confirmed", "waitlisted"):
                        raise BookingError(
                            "already_booked",
                            f"You already have a booking for this class (status: {existing['status']})",
                        )
                    if existing and existing["status"] == "cancelled":
                        # Revive path — keep the row id so audit history
                        # (originally booked → cancelled → re-confirmed)
                        # stays attached to one row instead of fragmenting.
                        existing_booking_id = str(existing["id"])
                    # 'attended' / 'no_show' from a *prior* session are
                    # impossible here (different session_id), but if we
                    # ever see one, fall through to INSERT — the unique
                    # constraint will catch genuine corruption.

                    # Check for time-overlap conflict with any existing
                    # confirmed/waitlisted booking. Prevents members from
                    # accidentally double-booking themselves.
                    conflict = await db.fetchrow(
                        """
                        SELECT b.id, cs2.title, cs2.starts_at, cs2.ends_at
                        FROM bookings b
                        JOIN class_sessions cs2 ON cs2.id = b.class_session_id
                        WHERE b.member_id = $1
                          AND b.status IN ('confirmed', 'waitlisted')
                          AND cs2.id != $2
                          AND cs2.status = 'scheduled'
                          AND cs2.starts_at < (
                              SELECT ends_at FROM class_sessions WHERE id = $2
                          )
                          AND cs2.ends_at > (
                              SELECT starts_at FROM class_sessions WHERE id = $2
                          )
                        LIMIT 1
                        """,
                        data["member_id"], data["class_session_id"],
                    )
                    if conflict:
                        raise BookingError(
                            "booking_conflict",
                            f"You already have {conflict['title']} booked at that time — "
                            "cancel it first or pick a different class.",
                        )

                # Validate membership eligibility (skip for guest bookings)
                if data.get("member_id") and not data.get("guest_name"):
                    session_info = await db.fetchrow(
                        "SELECT class_type_id, is_virtual, is_community, modality "
                        "FROM class_sessions WHERE id = $1",
                        data["class_session_id"],
                    )
                    eligibility = await self._membership_svc.check_eligibility(
                        data["member_id"],
                        class_type_id=str(session_info["class_type_id"]) if session_info.get("class_type_id") else None,
                        is_virtual=session_info.get("is_virtual", False),
                        is_community=session_info.get("is_community", False),
                        modality=session_info.get("modality") or "in_studio",
                    )
                    if not eligibility["eligible"]:
                        if session_info.get("is_community"):
                            raise BookingError("no_membership", "This is a community class — a Community Class Pass or unlimited membership is required")
                        modality = session_info.get("modality") or "in_studio"
                        if modality == "virtual":
                            raise BookingError("no_membership", "This is a virtual class — an online or all-access membership is required")
                        if modality == "in_studio":
                            raise BookingError("no_membership", "This is an in-studio class — an in-studio or all-access membership is required")
                        raise BookingError("no_membership", "No active membership — please purchase a membership to book classes")
                    # Auto-set membership_id
                    if not data.get("membership_id"):
                        data["membership_id"] = eligibility["membership_id"]

                    # Check liability waiver BEFORE any state-changing
                    # side effect (credit deduction, booking insert, etc.).
                    # Previous ordering (deduct → waiver check) burned
                    # class credits when the outer txn rolled back
                    # because deduct_class opens its own connection.
                    from app.services.waivers.waiver_service import WaiverService
                    waiver_svc = WaiverService()
                    waiver_status = await waiver_svc.check_waiver_status(data["member_id"])
                    if not waiver_status["signed"]:
                        raise BookingError(
                            "waiver_required",
                            "WAIVER NOT COMPLETED! CANNOT PARTICIPATE WITHOUT WAIVER — "
                            "the member must sign the liability waiver before booking classes.",
                        )

                    # Deduct class for class packs — pass the in-flight
                    # transaction's connection so deduct + insert roll
                    # back together AND the row-level UPDATE participates
                    # in row locking. Two concurrent bookings on the last
                    # credit will now serialize on this row instead of
                    # both succeeding via separate connections.
                    if eligibility["type"] in ("class_pack", "single_class"):
                        deducted = await self._membership_svc.deduct_class(
                            eligibility["membership_id"], db=db,
                        )
                        if deducted is None:
                            # The pre-check `classes_remaining > 0` filter
                            # rejected the row. Race lost — another
                            # concurrent booking just took the last credit.
                            raise BookingError(
                                "no_membership",
                                "No remaining classes on your pass — another booking just consumed the last credit. Please refresh and try again.",
                            )

                # Determine status
                status = "confirmed"
                waitlist_position = None
                if session["booked_count"] >= session["capacity"]:
                    if session["waitlist_count"] >= session["waitlist_capacity"]:
                        raise BookingError("class_full", "Class is full and waitlist is full")
                    status = "waitlisted"
                    waitlist_position = session["waitlist_count"] + 1

                if existing_booking_id:
                    # Revive the cancelled row instead of inserting a new
                    # one. Resets every field a fresh booking would have
                    # so a re-booked class doesn't carry stale state from
                    # the previous cycle.
                    booking_id = existing_booking_id
                    row = await db.fetchrow(
                        """
                        UPDATE bookings
                        SET status = $2,
                            source = $3,
                            membership_id = $4,
                            notes = $5,
                            guest_name = $6,
                            guest_email = $7,
                            waitlist_position = $8,
                            cancelled_at = NULL,
                            cancellation_reason = NULL,
                            booked_at = NOW(),
                            checked_in_at = NULL,
                            reminder_sent_at = NULL,
                            zoom_link_sent_at = NULL,
                            post_class_followup_sent_at = NULL
                        WHERE id = $1
                        RETURNING *
                        """,
                        booking_id, status, data.get("source", "web"),
                        data.get("membership_id"), data.get("notes"),
                        data.get("guest_name"), data.get("guest_email"),
                        waitlist_position,
                    )
                else:
                    row = await db.fetchrow(
                        """
                        INSERT INTO bookings
                            (id, member_id, class_session_id, status, source,
                             membership_id, notes, guest_name, guest_email,
                             waitlist_position)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        RETURNING *
                        """,
                        booking_id, data["member_id"], data["class_session_id"],
                        status, data.get("source", "web"),
                        data.get("membership_id"), data.get("notes"),
                        data.get("guest_name"), data.get("guest_email"),
                        waitlist_position,
                    )

            logger.info(
                "Booking created",
                booking_id=booking_id,
                status=status,
                member_id=data["member_id"],
                session_id=data["class_session_id"],
            )
            booking = dict(row)

            # Send confirmation notification (outside transaction)
            if status == "confirmed":
                await self._send_booking_notifications(db, booking_id, "confirmed")

            # Fire-and-forget webhook: booking.confirmed
            if status == "confirmed":
                try:
                    import asyncio
                    from app.services.webhooks.webhook_delivery_service import WebhookDeliveryService
                    asyncio.create_task(WebhookDeliveryService().fire_event("booking.confirmed", {
                        "booking_id": booking_id,
                        "member_id": data["member_id"],
                        "class_session_id": data["class_session_id"],
                        "status": status,
                    }))
                except Exception:
                    pass

            return booking

    async def cancel_booking(
        self,
        booking_id: str,
        reason: str | None = None,
        late_cancel: bool = False,
    ) -> dict | None:
        """Cancel a booking. Promotes next waitlisted member if applicable."""
        async with get_tenant_db() as db:
            booking = await db.fetchrow("SELECT * FROM bookings WHERE id = $1", booking_id)
            if not booking or booking["status"] in ("cancelled", "attended"):
                return None

            was_confirmed = booking["status"] == "confirmed"

            row = await db.fetchrow(
                """
                UPDATE bookings
                SET status = 'cancelled', cancelled_at = NOW(),
                    cancellation_reason = $2, late_cancel = $3
                WHERE id = $1
                RETURNING *
                """,
                booking_id, reason, late_cancel,
            )

            # Restore class pack credit if one was deducted
            if booking.get("membership_id") and not late_cancel:
                await db.execute(
                    """
                    UPDATE member_memberships
                    SET classes_remaining = classes_remaining + 1, updated_at = NOW()
                    WHERE id = $1 AND classes_remaining IS NOT NULL
                    """,
                    str(booking["membership_id"]),
                )

            # Send cancellation notification
            await self._send_booking_notifications(db, booking_id, "cancelled")

            # Promote from waitlist if a confirmed spot opened
            if was_confirmed:
                await self._promote_waitlist(db, str(booking["class_session_id"]))

            logger.info("Booking cancelled", booking_id=booking_id, late_cancel=late_cancel)
            return dict(row) if row else None

    async def _promote_waitlist(self, db, session_id: str) -> dict | None:
        """Promote the next waitlisted booking to confirmed.

        Uses AI priority scoring if the studio's waitlist_mode is 'ai_priority',
        otherwise falls back to FIFO ordering.
        """
        # Check studio waitlist mode
        mode_row = await db.fetchrow(
            """
            SELECT COALESCE(s.waitlist_mode, 'fifo') AS waitlist_mode
            FROM studios s
            JOIN class_sessions cs ON cs.studio_id = s.id
            WHERE cs.id = $1
            """,
            session_id,
        )
        if mode_row and mode_row["waitlist_mode"] == "ai_priority":
            from app.services.ai.waitlist_triage_service import WaitlistTriageService
            triage_svc = WaitlistTriageService()
            promoted = await triage_svc.promote_by_priority(db, session_id)
            if promoted:
                await self._send_booking_notifications(
                    db, str(promoted["id"]), "waitlist_promotion",
                )
            return promoted

        # Default FIFO logic
        waitlisted = await db.fetchrow(
            """
            SELECT id FROM bookings
            WHERE class_session_id = $1 AND status = 'waitlisted'
            ORDER BY waitlist_position ASC NULLS LAST, booked_at ASC
            LIMIT 1
            """,
            session_id,
        )
        if not waitlisted:
            return None

        row = await db.fetchrow(
            """
            UPDATE bookings
            SET status = 'confirmed', waitlist_position = NULL
            WHERE id = $1
            RETURNING *
            """,
            str(waitlisted["id"]),
        )
        promoted = dict(row) if row else None
        if promoted:
            logger.info(
                "Waitlist promoted",
                booking_id=str(waitlisted["id"]),
                session_id=session_id,
            )
            await self._send_booking_notifications(db, str(waitlisted["id"]), "waitlist_promotion")
        return promoted

    async def check_in(self, booking_id: str) -> dict | None:
        """Check a member in for their class."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE bookings
                SET status = 'attended', checked_in_at = NOW()
                WHERE id = $1 AND status = 'confirmed'
                RETURNING *
                """,
                booking_id,
            )
            if row:
                # Trial activation: if the booking consumed a trial-style
                # membership whose clock hasn't started yet (ends_at IS
                # NULL because membership_types.trial_starts_on_first_class=TRUE
                # at assignment time), compute ends_at = NOW() + the
                # type's duration_days. The member gets the full trial
                # window from their first actual class, not from signup.
                if row.get("membership_id"):
                    await db.execute(
                        """
                        UPDATE member_memberships mm
                        SET ends_at = NOW() + (mt.duration_days || ' days')::interval,
                            updated_at = NOW()
                        FROM membership_types mt
                        WHERE mm.id = $1
                          AND mm.membership_type_id = mt.id
                          AND mm.ends_at IS NULL
                          AND mt.trial_starts_on_first_class = TRUE
                          AND mt.duration_days IS NOT NULL
                        """,
                        str(row["membership_id"]),
                    )

                # Update member visit stats
                member_row = await db.fetchrow(
                    """
                    UPDATE members
                    SET total_visits = total_visits + 1, last_visit_at = NOW(), updated_at = NOW()
                    WHERE id = $1
                    RETURNING total_visits, joined_at
                    """,
                    str(row["member_id"]),
                )
                logger.info("Checked in", booking_id=booking_id)

                # Check for milestones (fire-and-forget)
                if member_row:
                    try:
                        milestone_svc = MilestoneService()
                        await milestone_svc.check_milestones(
                            member_id=str(row["member_id"]),
                            total_visits=member_row["total_visits"],
                            joined_at=member_row["joined_at"],
                        )
                    except Exception as e:
                        logger.warning(
                            "Milestone check failed",
                            member_id=str(row["member_id"]),
                            error=str(e),
                        )

                # Fire-and-forget EMR encounter sync
                try:
                    from app.workers.tasks.emr_sync import sync_attendance_to_emr
                    from app.core.tenant_context import get_tenant_context
                    ctx = get_tenant_context()
                    if ctx:
                        sync_attendance_to_emr.delay(ctx.schema_name, booking_id)
                except Exception as e:
                    logger.warning("EMR attendance sync failed", booking_id=booking_id, error=str(e))

                # Fire-and-forget webhook: booking.checked_in
                try:
                    import asyncio
                    from app.services.webhooks.webhook_delivery_service import WebhookDeliveryService
                    asyncio.create_task(WebhookDeliveryService().fire_event("booking.checked_in", {
                        "booking_id": booking_id,
                        "member_id": str(row["member_id"]),
                    }))
                except Exception:
                    pass

            return dict(row) if row else None

    async def mark_no_show(self, booking_id: str) -> dict | None:
        """Mark a confirmed booking as no-show."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE bookings SET status = 'no_show'
                WHERE id = $1 AND status = 'confirmed'
                RETURNING *
                """,
                booking_id,
            )
            if row:
                logger.info("Marked no-show", booking_id=booking_id)
            return dict(row) if row else None

    async def get_booking(self, booking_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT b.*, cs.title AS session_title, cs.starts_at, cs.ends_at,
                       m.first_name, m.last_name, m.email AS member_email
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                JOIN members m ON m.id = b.member_id
                WHERE b.id = $1
                """,
                booking_id,
            )
            return dict(row) if row else None

    async def get_session_roster(self, session_id: str) -> list[dict]:
        """Get all bookings for a session (confirmed + waitlisted + attended)."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT b.*, m.first_name, m.last_name, m.email AS member_email,
                       m.phone_enc
                FROM bookings b
                JOIN members m ON m.id = b.member_id
                WHERE b.class_session_id = $1
                    AND b.status IN ('confirmed', 'waitlisted', 'attended')
                ORDER BY
                    CASE b.status
                        WHEN 'attended' THEN 0
                        WHEN 'confirmed' THEN 1
                        WHEN 'waitlisted' THEN 2
                    END,
                    b.booked_at
                """,
                session_id,
            )
            out = []
            for r in rows:
                d = dict(r)
                d["phone"] = decrypt_phone(d)
                d.pop("phone_enc", None)
                out.append(d)
            return out

    async def get_session_guest_bookings(self, session_id: str) -> list[dict]:
        """Get guest bookings (non-member walk-ins) for a session."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM bookings
                WHERE class_session_id = $1 AND guest_name IS NOT NULL
                    AND status IN ('confirmed', 'attended')
                ORDER BY booked_at
                """,
                session_id,
            )
            return [dict(r) for r in rows]
