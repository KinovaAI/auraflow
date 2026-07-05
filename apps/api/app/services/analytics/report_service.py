"""AuraFlow — Report / Analytics Service

Revenue, attendance, membership health, room utilization, and instructor reports.
All queries are tenant-scoped via get_tenant_db().
"""
from datetime import datetime, timedelta, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db


class ReportService:

    # ── Revenue ───────────────────────────────────────────────────────────────

    async def revenue_over_time(
        self,
        start: datetime,
        end: datetime,
        group_by: str = "day",
    ) -> list[dict]:
        """Revenue grouped by day, week, or month."""
        trunc = {"day": "day", "week": "week", "month": "month"}.get(group_by, "day")
        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"""
                SELECT
                    date_trunc($3, created_at) AS period,
                    COALESCE(SUM(amount_cents), 0) AS revenue,
                    COALESCE(SUM(net_amount_cents), 0) AS net_revenue,
                    COALESCE(SUM(refund_amount_cents), 0) AS refunds,
                    COUNT(*) AS count
                FROM transactions
                WHERE status IN ('completed', 'partially_refunded')
                  AND created_at >= $1 AND created_at < $2
                GROUP BY period
                ORDER BY period
                """,
                start, end, trunc,
            )
            return [
                {
                    "period": r["period"].isoformat() if r["period"] else None,
                    "revenue": r["revenue"],
                    "net_revenue": r["net_revenue"],
                    "refunds": r["refunds"],
                    "count": r["count"],
                }
                for r in rows
            ]

    async def revenue_by_type(self, start: datetime, end: datetime) -> list[dict]:
        """Revenue broken down by transaction type."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT type,
                    COALESCE(SUM(amount_cents), 0) AS revenue,
                    COUNT(*) AS count
                FROM transactions
                WHERE status IN ('completed', 'partially_refunded')
                  AND created_at >= $1 AND created_at < $2
                GROUP BY type
                ORDER BY revenue DESC
                """,
                start, end,
            )
            return [dict(r) for r in rows]

    async def revenue_by_instructor(
        self, start: datetime, end: datetime
    ) -> list[dict]:
        """Revenue attributed to each instructor with pay and profit estimates."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT i.id, i.display_name,
                    COALESCE(SUM(t.amount_cents), 0) AS revenue,
                    COUNT(DISTINCT cs.id) AS sessions_taught,
                    COUNT(DISTINCT b.id) AS total_attendees,
                    i.pay_rate_cents, i.pay_type
                FROM instructors i
                LEFT JOIN class_sessions cs ON cs.instructor_id = i.id
                    AND cs.starts_at >= $1 AND cs.starts_at < $2
                    AND cs.status != 'cancelled'
                LEFT JOIN bookings b ON b.class_session_id = cs.id
                    AND b.status = 'attended'
                LEFT JOIN transactions t ON t.booking_id = b.id
                    AND t.status IN ('completed', 'partially_refunded')
                WHERE i.is_active = TRUE
                GROUP BY i.id, i.display_name, i.pay_rate_cents, i.pay_type
                ORDER BY revenue DESC
                """,
                start, end,
            )
            result = []
            for r in rows:
                pay = 0
                rate = r["pay_rate_cents"] or 0
                if r["pay_type"] == "per_class":
                    pay = rate * r["sessions_taught"]
                elif r["pay_type"] == "per_student":
                    pay = rate * r["total_attendees"]
                revenue = r["revenue"]
                result.append({
                    **dict(r),
                    "estimated_pay_cents": pay,
                    "profit_cents": revenue - pay,
                })
            return result

    # ── Attendance ────────────────────────────────────────────────────────────

    async def attendance_over_time(
        self,
        start: datetime,
        end: datetime,
        group_by: str = "day",
    ) -> list[dict]:
        """Attendance (check-ins) grouped by period."""
        trunc = {"day": "day", "week": "week", "month": "month"}.get(group_by, "day")
        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"""
                SELECT
                    date_trunc($3, cs.starts_at) AS period,
                    COUNT(CASE WHEN b.status = 'attended' THEN 1 END) AS attended,
                    COUNT(CASE WHEN b.status = 'confirmed' THEN 1 END) AS confirmed,
                    COUNT(CASE WHEN b.status = 'no_show' THEN 1 END) AS no_shows,
                    COUNT(CASE WHEN b.status = 'cancelled' THEN 1 END) AS cancelled
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                WHERE cs.starts_at >= $1 AND cs.starts_at < $2
                GROUP BY period
                ORDER BY period
                """,
                start, end, trunc,
            )
            return [
                {
                    "period": r["period"].isoformat() if r["period"] else None,
                    "attended": r["attended"],
                    "confirmed": r["confirmed"],
                    "no_shows": r["no_shows"],
                    "cancelled": r["cancelled"],
                }
                for r in rows
            ]

    async def attendance_by_class_type(self, start: datetime, end: datetime) -> list[dict]:
        """Attendance broken down by class type."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT ct.name AS class_type,
                    COUNT(CASE WHEN b.status = 'attended' THEN 1 END) AS attended,
                    COUNT(*) AS total_bookings,
                    COUNT(DISTINCT cs.id) AS sessions
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                JOIN class_types ct ON ct.id = cs.class_type_id
                WHERE cs.starts_at >= $1 AND cs.starts_at < $2
                GROUP BY ct.name
                ORDER BY attended DESC
                """,
                start, end,
            )
            return [dict(r) for r in rows]

    async def attendance_heatmap(
        self, start: datetime, end: datetime
    ) -> list[dict]:
        """Attendance heatmap: bookings by day-of-week and hour-of-day."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT
                    EXTRACT(DOW FROM cs.starts_at) AS day_of_week,
                    EXTRACT(HOUR FROM cs.starts_at) AS hour_of_day,
                    COUNT(CASE WHEN b.status = 'attended' THEN 1 END) AS attended,
                    COUNT(*) AS total_bookings,
                    COUNT(DISTINCT cs.id) AS sessions
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                WHERE cs.starts_at >= $1 AND cs.starts_at < $2
                GROUP BY day_of_week, hour_of_day
                ORDER BY day_of_week, hour_of_day
                """,
                start, end,
            )
            return [
                {
                    "day_of_week": int(r["day_of_week"]),
                    "hour_of_day": int(r["hour_of_day"]),
                    "attended": r["attended"],
                    "total_bookings": r["total_bookings"],
                    "sessions": r["sessions"],
                }
                for r in rows
            ]

    # ── Membership Health ─────────────────────────────────────────────────────

    async def membership_summary(self) -> dict:
        """Current membership health snapshot."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'active') AS active,
                    COUNT(*) FILTER (WHERE status = 'frozen') AS frozen,
                    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled,
                    COUNT(*) FILTER (WHERE status = 'expired') AS expired,
                    COUNT(*) AS total
                FROM member_memberships
                """
            )
            return dict(row) if row else {}

    async def membership_by_type(self) -> list[dict]:
        """Active memberships broken down by type."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT mt.name, mt.type, mt.price_cents,
                    COUNT(*) FILTER (WHERE mm.status = 'active') AS active_count,
                    COUNT(*) FILTER (WHERE mm.status = 'frozen') AS frozen_count,
                    COUNT(*) AS total_count
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                GROUP BY mt.name, mt.type, mt.price_cents
                ORDER BY active_count DESC
                """
            )
            return [dict(r) for r in rows]

    async def churn_rate(self, days: int = 30) -> dict:
        """Membership churn: cancellations vs active over a period."""
        async with get_tenant_db() as db:
            since = datetime.now(timezone.utc) - timedelta(days=days)
            row = await db.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE cancelled_at >= $1) AS cancelled_in_period,
                    COUNT(*) FILTER (WHERE status = 'active') AS currently_active
                FROM member_memberships
                """,
                since,
            )
            active = row["currently_active"] or 0
            cancelled = row["cancelled_in_period"] or 0
            rate = (cancelled / (active + cancelled) * 100) if (active + cancelled) > 0 else 0
            return {
                "cancelled_in_period": cancelled,
                "currently_active": active,
                "churn_rate_percent": round(rate, 1),
                "period_days": days,
            }

    # ── Utilization ───────────────────────────────────────────────────────────

    async def room_utilization(self, start: datetime, end: datetime) -> list[dict]:
        """Room utilization: sessions run vs capacity used."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT r.name AS room_name, r.capacity AS room_capacity,
                    COUNT(DISTINCT cs.id) AS sessions,
                    COALESCE(SUM(
                        (SELECT COUNT(*) FROM bookings
                         WHERE class_session_id = cs.id AND status IN ('confirmed', 'attended'))
                    ), 0) AS total_bookings,
                    COALESCE(SUM(cs.capacity), 0) AS total_capacity
                FROM class_sessions cs
                JOIN rooms r ON r.id = cs.room_id
                WHERE cs.starts_at >= $1 AND cs.starts_at < $2
                  AND cs.status != 'cancelled'
                GROUP BY r.name, r.capacity
                ORDER BY sessions DESC
                """,
                start, end,
            )
            result = []
            for r in rows:
                cap = r["total_capacity"] or 1
                util = round(r["total_bookings"] / cap * 100, 1)
                result.append({
                    **dict(r),
                    "utilization_percent": util,
                })
            return result

    # ── Instructor Reports ────────────────────────────────────────────────────

    async def instructor_summary(self, start: datetime, end: datetime) -> list[dict]:
        """Instructor activity and pay summary."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT i.id, i.display_name,
                    i.pay_rate_cents, i.pay_type,
                    COUNT(DISTINCT cs.id) AS sessions_taught,
                    COALESCE(SUM(
                        (SELECT COUNT(*) FROM bookings
                         WHERE class_session_id = cs.id AND status = 'attended')
                    ), 0) AS total_attended
                FROM instructors i
                LEFT JOIN class_sessions cs
                    ON cs.instructor_id = i.id
                    AND cs.starts_at >= $1 AND cs.starts_at < $2
                    AND cs.status != 'cancelled'
                WHERE i.is_active = TRUE
                GROUP BY i.id, i.display_name, i.pay_rate_cents, i.pay_type
                ORDER BY sessions_taught DESC
                """,
                start, end,
            )
            result = []
            for r in rows:
                pay = 0
                if r["pay_rate_cents"] and r["pay_type"] == "per_class":
                    pay = r["pay_rate_cents"] * r["sessions_taught"]
                result.append({
                    **dict(r),
                    "estimated_pay_cents": pay,
                })
            return result

    async def payout_report(
        self, start: datetime, end: datetime
    ) -> dict:
        """Instructor payout report with per-class and per-student pay calculations."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT i.id, i.display_name, i.email, i.pay_type, i.pay_rate_cents,
                    COUNT(DISTINCT cs.id) AS sessions_taught,
                    COALESCE(SUM(
                        (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id AND status = 'attended')
                    ), 0) AS total_attended,
                    CASE
                        WHEN i.pay_type = 'per_class' THEN i.pay_rate_cents * COUNT(DISTINCT cs.id)
                        WHEN i.pay_type = 'per_student' THEN i.pay_rate_cents * COALESCE(SUM(
                            (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id AND status = 'attended')
                        ), 0)
                        ELSE 0
                    END AS total_pay_cents
                FROM instructors i
                LEFT JOIN class_sessions cs ON cs.instructor_id = i.id
                    AND cs.starts_at >= $1 AND cs.starts_at < $2
                    AND cs.status != 'cancelled'
                WHERE i.is_active = TRUE
                GROUP BY i.id, i.display_name, i.email, i.pay_type, i.pay_rate_cents
                ORDER BY total_pay_cents DESC
                """,
                start, end,
            )
            instructors = [dict(r) for r in rows]
            total_payout = sum(r["total_pay_cents"] for r in instructors)
            total_sessions = sum(r["sessions_taught"] for r in instructors)
            total_attendees = sum(r["total_attended"] for r in instructors)
            return {
                "instructors": instructors,
                "total_payout_cents": total_payout,
                "total_sessions": total_sessions,
                "total_attendees": total_attendees,
            }

    async def guest_instructor_1099_report(self, year: int) -> dict:
        """Per-guest annual workshop revenue + their share for 1099 reporting.

        Sums paid_price_cents from course_enrollments (excluding withdrawn)
        for each workshop a guest taught in the calendar year, then applies
        the guest's stored revenue_share_percent_to_guest. The IRS 1099-NEC
        threshold is $600/year — flagged in the response so the UI can show
        which guests need a form filed.

        Pulls decrypted tax_id and full mailing address so the report has
        everything needed to populate the 1099 directly.
        """
        from datetime import datetime as _dt
        from app.services.scheduling.guest_instructor_service import (
            _row_with_decrypted_tax_id,
        )

        start = _dt(year, 1, 1)
        end = _dt(year + 1, 1, 1)

        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT g.id, g.name, g.email, g.phone,
                       g.address_line1, g.city, g.state, g.postal_code,
                       g.tax_id_encrypted,
                       g.revenue_share_percent_to_guest,
                       COUNT(DISTINCT c.id)               AS workshops_taught,
                       COALESCE(SUM(ce.paid_price_cents), 0) AS gross_revenue_cents,
                       COUNT(ce.id) FILTER (WHERE ce.status != 'withdrawn')
                                                          AS attendees_paid
                FROM guest_instructors g
                LEFT JOIN courses c
                    ON c.guest_instructor_id = g.id
                   AND c.type = 'workshop'
                   AND c.starts_at >= $1 AND c.starts_at < $2
                LEFT JOIN course_enrollments ce
                    ON ce.course_id = c.id
                   AND ce.status != 'withdrawn'
                GROUP BY g.id, g.name, g.email, g.phone, g.address_line1,
                         g.city, g.state, g.postal_code, g.tax_id_encrypted,
                         g.revenue_share_percent_to_guest
                ORDER BY gross_revenue_cents DESC
                """,
                start, end,
            )

        guests = []
        total_studio_cents = 0
        total_guest_cents = 0
        for r in rows:
            d = _row_with_decrypted_tax_id(r)
            gross = int(d.get("gross_revenue_cents") or 0)
            pct = int(d.get("revenue_share_percent_to_guest") or 60)
            guest_cents = gross * pct // 100
            studio_cents = gross - guest_cents
            d["gross_revenue_cents"] = gross
            d["guest_payout_cents"] = guest_cents
            d["studio_revenue_cents"] = studio_cents
            d["needs_1099"] = guest_cents >= 60000  # $600 threshold
            guests.append(d)
            total_guest_cents += guest_cents
            total_studio_cents += studio_cents

        return {
            "year": year,
            "guests": guests,
            "totals": {
                "guest_payout_cents": total_guest_cents,
                "studio_revenue_cents": total_studio_cents,
                "gross_revenue_cents": total_guest_cents + total_studio_cents,
            },
        }

    # ── Studio Health / Extended Metrics ──────────────────────────────────────

    async def studio_health(self, start: datetime, end: datetime) -> dict:
        """Comprehensive studio health metrics for the analytics page."""
        async with get_tenant_db() as db:
            # New members in period
            new_members = await db.fetchrow(
                """
                SELECT COUNT(*) AS count
                FROM members
                WHERE joined_at >= $1 AND joined_at < $2
                """,
                start, end,
            )
            # Booked spots and capacity
            capacity_stats = await db.fetchrow(
                """
                SELECT
                    COALESCE(SUM(cs.capacity), 0) AS total_capacity,
                    COALESCE(SUM(
                        (SELECT COUNT(*) FROM bookings
                         WHERE class_session_id = cs.id
                           AND status IN ('confirmed', 'attended'))
                    ), 0) AS total_booked
                FROM class_sessions cs
                WHERE cs.starts_at >= $1 AND cs.starts_at < $2
                  AND cs.status != 'cancelled'
                """,
                start, end,
            )
            # Booking cancellations and waitlisted
            booking_stats = await db.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE b.status IN ('cancelled', 'late_cancel')) AS cancellations,
                    COUNT(*) FILTER (WHERE b.status = 'late_cancel') AS late_cancels,
                    COUNT(*) FILTER (WHERE b.status = 'waitlisted') AS waitlisted,
                    COUNT(*) FILTER (WHERE b.status = 'no_show') AS no_shows,
                    COUNT(*) FILTER (WHERE b.status = 'attended') AS attended,
                    COUNT(*) AS total_bookings
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                WHERE cs.starts_at >= $1 AND cs.starts_at < $2
                """,
                start, end,
            )
            # Average class size
            avg_class = await db.fetchrow(
                """
                SELECT
                    COUNT(DISTINCT cs.id) AS sessions_held,
                    CASE WHEN COUNT(DISTINCT cs.id) = 0 THEN 0
                         ELSE COALESCE(
                            (SELECT COUNT(*)::numeric FROM bookings b
                             JOIN class_sessions cs2 ON cs2.id = b.class_session_id
                             WHERE cs2.starts_at >= $1 AND cs2.starts_at < $2
                               AND cs2.status != 'cancelled'
                               AND b.status IN ('confirmed', 'attended'))
                            / COUNT(DISTINCT cs.id)::numeric, 0)
                    END AS avg_class_size
                FROM class_sessions cs
                WHERE cs.starts_at >= $1 AND cs.starts_at < $2
                  AND cs.status != 'cancelled'
                """,
                start, end,
            )
            # New memberships sold in period
            new_memberships = await db.fetchrow(
                """
                SELECT COUNT(*) AS count
                FROM member_memberships
                WHERE created_at >= $1 AND created_at < $2
                """,
                start, end,
            )

        total_cap = capacity_stats["total_capacity"] if capacity_stats else 0
        total_booked = capacity_stats["total_booked"] if capacity_stats else 0
        booking_rate = round(total_booked / total_cap * 100, 1) if total_cap > 0 else 0
        total_bk = booking_stats["total_bookings"] if booking_stats else 0
        attended = booking_stats["attended"] if booking_stats else 0
        attendance_rate = round(attended / total_bk * 100, 1) if total_bk > 0 else 0

        return {
            "new_members": new_members["count"] if new_members else 0,
            "total_booked_spots": total_booked,
            "total_capacity": total_cap,
            "booking_rate_percent": booking_rate,
            "cancellations": booking_stats["cancellations"] if booking_stats else 0,
            "late_cancellations": booking_stats["late_cancels"] if booking_stats else 0,
            "waitlisted": booking_stats["waitlisted"] if booking_stats else 0,
            "no_shows": booking_stats["no_shows"] if booking_stats else 0,
            "attendance_rate_percent": attendance_rate,
            "sessions_held": avg_class["sessions_held"] if avg_class else 0,
            "avg_class_size": round(float(avg_class["avg_class_size"]), 1) if avg_class else 0,
            "new_memberships_sold": new_memberships["count"] if new_memberships else 0,
        }

    async def top_cancellers(self, start: datetime, end: datetime, limit: int = 10) -> list[dict]:
        """Members with the most booking cancellations in the period."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT m.id, m.first_name, m.last_name, m.email,
                    COUNT(*) AS cancel_count,
                    COUNT(*) FILTER (WHERE b.status = 'late_cancel') AS late_cancel_count,
                    COUNT(*) FILTER (WHERE b.status = 'no_show') AS no_show_count
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                JOIN members m ON m.id = b.member_id
                WHERE cs.starts_at >= $1 AND cs.starts_at < $2
                  AND b.status IN ('cancelled', 'late_cancel', 'no_show')
                GROUP BY m.id, m.first_name, m.last_name, m.email
                ORDER BY cancel_count DESC
                LIMIT $3
                """,
                start, end, limit,
            )
            return [dict(r) for r in rows]

    async def top_selling_memberships(self, start: datetime, end: datetime, limit: int = 10) -> list[dict]:
        """Most sold membership/pricing options in the period."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT mt.id, mt.name, mt.type, mt.price_cents,
                    COUNT(*) AS sold_count,
                    COALESCE(SUM(mt.price_cents), 0) AS total_revenue_cents
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE mm.created_at >= $1 AND mm.created_at < $2
                GROUP BY mt.id, mt.name, mt.type, mt.price_cents
                ORDER BY sold_count DESC
                LIMIT $3
                """,
                start, end, limit,
            )
            return [dict(r) for r in rows]

    async def new_members_over_time(
        self, start: datetime, end: datetime, group_by: str = "day"
    ) -> list[dict]:
        """New member signups over time."""
        trunc = {"day": "day", "week": "week", "month": "month"}.get(group_by, "day")
        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"""
                SELECT
                    date_trunc($3, joined_at) AS period,
                    COUNT(*) AS count
                FROM members
                WHERE joined_at >= $1 AND joined_at < $2
                GROUP BY period
                ORDER BY period
                """,
                start, end, trunc,
            )
            return [
                {
                    "period": r["period"].isoformat() if r["period"] else None,
                    "count": r["count"],
                }
                for r in rows
            ]

    # ── KPI Dashboard ─────────────────────────────────────────────────────────

    async def dashboard_kpis(self, days: int = 30) -> dict:
        """Key performance indicators for the main dashboard."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        prev_start = start - timedelta(days=days)

        async with get_tenant_db() as db:
            # Current period revenue
            curr = await db.fetchrow(
                """
                SELECT COALESCE(SUM(amount_cents), 0) AS revenue,
                       COUNT(*) AS txn_count
                FROM transactions
                WHERE status IN ('completed', 'partially_refunded')
                  AND created_at >= $1 AND created_at < $2
                """,
                start, end,
            )
            # Previous period for comparison
            prev = await db.fetchrow(
                """
                SELECT COALESCE(SUM(amount_cents), 0) AS revenue
                FROM transactions
                WHERE status IN ('completed', 'partially_refunded')
                  AND created_at >= $1 AND created_at < $2
                """,
                prev_start, start,
            )
            # Active members
            members = await db.fetchrow(
                """
                SELECT COUNT(*) FILTER (WHERE is_active) AS active_members,
                       COUNT(*) AS total_members
                FROM members
                """
            )
            # Attendance
            attendance = await db.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE b.status = 'attended') AS attended,
                    COUNT(*) AS total_bookings
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                WHERE cs.starts_at >= $1 AND cs.starts_at < $2
                """,
                start, end,
            )
            # Active memberships
            memberships = await db.fetchrow(
                "SELECT COUNT(*) FILTER (WHERE status = 'active') AS active FROM member_memberships"
            )

        curr_rev = curr["revenue"] if curr else 0
        prev_rev = prev["revenue"] if prev else 0
        rev_change = ((curr_rev - prev_rev) / prev_rev * 100) if prev_rev > 0 else 0

        return {
            "revenue": curr_rev,
            "revenue_change_percent": round(rev_change, 1),
            "transaction_count": curr["txn_count"] if curr else 0,
            "active_members": members["active_members"] if members else 0,
            "total_members": members["total_members"] if members else 0,
            "active_memberships": memberships["active"] if memberships else 0,
            "attendance": attendance["attended"] if attendance else 0,
            "total_bookings": attendance["total_bookings"] if attendance else 0,
            "period_days": days,
        }
