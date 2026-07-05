"""AuraFlow — Time Clock & Payroll Service

Clock in/out, break tracking, timesheet approval, overtime calculation,
and payroll compilation with per-instructor line items.
"""
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal

from app.core.logging import logger
from app.db.session import get_tenant_db


class TimeClockService:

    # ── Clock Operations ─────────────────────────────────────────────────────

    async def clock_in(
        self, instructor_id: str, shift_type: str = "regular", notes: str | None = None
    ) -> dict:
        """Clock in an instructor. Fails if already clocked in."""
        async with get_tenant_db() as db:
            # Check for open entry
            open_entry = await db.fetchrow(
                "SELECT id FROM time_entries WHERE instructor_id = $1 AND clock_out IS NULL",
                instructor_id,
            )
            if open_entry:
                raise ValueError("Already clocked in. Clock out first.")

            entry_id = str(uuid.uuid4())
            await db.execute(
                """
                INSERT INTO time_entries (id, instructor_id, clock_in, shift_type, notes)
                VALUES ($1, $2, NOW(), $3, $4)
                """,
                entry_id, instructor_id, shift_type, notes,
            )
            row = await db.fetchrow("SELECT * FROM time_entries WHERE id = $1", entry_id)

        logger.info("Clock in", instructor_id=instructor_id, entry_id=entry_id)
        return _entry_to_dict(row)

    async def clock_out(
        self, instructor_id: str, break_minutes: int = 0, notes: str | None = None
    ) -> dict:
        """Clock out an instructor. Computes total and overtime minutes."""
        async with get_tenant_db() as db:
            open_entry = await db.fetchrow(
                "SELECT * FROM time_entries WHERE instructor_id = $1 AND clock_out IS NULL",
                instructor_id,
            )
            if not open_entry:
                raise ValueError("Not currently clocked in.")

            entry_id = str(open_entry["id"])
            clock_in = open_entry["clock_in"]
            now = datetime.now(timezone.utc)

            # Total minutes worked minus breaks
            raw_minutes = int((now - clock_in).total_seconds() / 60)
            total_break = break_minutes + (open_entry["break_minutes"] or 0)
            total_minutes = max(0, raw_minutes - total_break)

            # Overtime: anything over 480 minutes (8 hours) in a single shift
            overtime_minutes = max(0, total_minutes - 480)

            update_notes = notes if notes else open_entry["notes"]

            await db.execute(
                """
                UPDATE time_entries
                SET clock_out = NOW(),
                    break_minutes = $2,
                    total_minutes = $3,
                    overtime_minutes = $4,
                    notes = $5,
                    updated_at = NOW()
                WHERE id = $1
                """,
                entry_id, total_break, total_minutes, overtime_minutes, update_notes,
            )
            row = await db.fetchrow("SELECT * FROM time_entries WHERE id = $1", entry_id)

        logger.info(
            "Clock out",
            instructor_id=instructor_id,
            entry_id=entry_id,
            total_minutes=total_minutes,
        )
        return _entry_to_dict(row)

    async def get_status(self, instructor_id: str) -> dict | None:
        """Get current clock-in status for an instructor."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM time_entries WHERE instructor_id = $1 AND clock_out IS NULL",
                instructor_id,
            )
        return _entry_to_dict(row) if row else None

    # ── Timesheets ───────────────────────────────────────────────────────────

    async def get_timesheet(
        self, instructor_id: str, start: date, end: date
    ) -> list[dict]:
        """Get time entries for a specific instructor in a date range."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT te.*, i.display_name AS instructor_name
                FROM time_entries te
                JOIN instructors i ON i.id = te.instructor_id
                WHERE te.instructor_id = $1
                  AND te.clock_in >= $2 AND te.clock_in < $3::date + INTERVAL '1 day'
                ORDER BY te.clock_in DESC
                """,
                instructor_id, start, end,
            )
        return [_entry_to_dict(r) for r in rows]

    async def get_all_timesheets(self, start: date, end: date) -> list[dict]:
        """Get all time entries across all instructors (admin view)."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT te.*, i.display_name AS instructor_name
                FROM time_entries te
                JOIN instructors i ON i.id = te.instructor_id
                WHERE te.clock_in >= $1 AND te.clock_in < $2::date + INTERVAL '1 day'
                ORDER BY te.clock_in DESC
                """,
                start, end,
            )
        return [_entry_to_dict(r) for r in rows]

    async def approve_entry(self, entry_id: str, approver_id: str) -> dict | None:
        """Approve a time entry."""
        async with get_tenant_db() as db:
            await db.execute(
                """
                UPDATE time_entries
                SET status = 'approved', approved_by = $2, approved_at = NOW(), updated_at = NOW()
                WHERE id = $1
                """,
                entry_id, approver_id,
            )
            row = await db.fetchrow("SELECT * FROM time_entries WHERE id = $1", entry_id)
        return _entry_to_dict(row) if row else None

    async def reject_entry(self, entry_id: str, approver_id: str, reason: str | None = None) -> dict | None:
        """Reject a time entry."""
        async with get_tenant_db() as db:
            current = await db.fetchrow("SELECT notes FROM time_entries WHERE id = $1", entry_id)
            rejection_note = f"Rejected: {reason}" if reason else "Rejected"
            existing_notes = current["notes"] if current and current["notes"] else ""
            combined = f"{existing_notes}\n{rejection_note}".strip() if existing_notes else rejection_note

            await db.execute(
                """
                UPDATE time_entries
                SET status = 'rejected', approved_by = $2, approved_at = NOW(),
                    notes = $3, updated_at = NOW()
                WHERE id = $1
                """,
                entry_id, approver_id, combined,
            )
            row = await db.fetchrow("SELECT * FROM time_entries WHERE id = $1", entry_id)
        return _entry_to_dict(row) if row else None

    # ── Payroll ──────────────────────────────────────────────────────────────

    async def compile_payroll(
        self, period_start: date, period_end: date, created_by: str | None = None
    ) -> dict:
        """Compile payroll for a date range. Creates run + line items."""
        run_id = str(uuid.uuid4())

        async with get_tenant_db() as db:
            # Create payroll run
            await db.execute(
                """
                INSERT INTO payroll_runs (id, period_start, period_end, created_by)
                VALUES ($1, $2, $3, $4)
                """,
                run_id, period_start, period_end, created_by,
            )

            # Get all active instructors with pay info — include the
            # private/workshop/training pay percent fields so this run
            # mirrors what get_payroll_report computes.
            instructors = await db.fetch(
                """
                SELECT id, display_name, pay_rate_cents, pay_type, salary_cents,
                       private_session_pay_percent, workshop_pay_percent,
                       training_pay_percent
                FROM instructors WHERE is_active = TRUE
                """
            )

            total_gross = 0
            total_hours = Decimal("0")

            for inst in instructors:
                inst_id = str(inst["id"])
                pay_rate = inst["pay_rate_cents"] or 0
                pay_type = inst["pay_type"] or "per_class"

                # Sum approved time entries
                time_row = await db.fetchrow(
                    """
                    SELECT
                        COALESCE(SUM(total_minutes), 0) AS total_mins,
                        COALESCE(SUM(overtime_minutes), 0) AS ot_mins
                    FROM time_entries
                    WHERE instructor_id = $1
                      AND status = 'approved'
                      AND clock_in >= $2 AND clock_in < $3::date + INTERVAL '1 day'
                      AND clock_out IS NOT NULL
                    """,
                    inst_id, period_start, period_end,
                )
                total_mins = time_row["total_mins"]
                ot_mins = time_row["ot_mins"]
                regular_mins = total_mins - ot_mins

                hours_worked = Decimal(str(total_mins)) / 60
                overtime_hours = Decimal(str(ot_mins)) / 60

                # Count classes taught in period
                class_row = await db.fetchrow(
                    """
                    SELECT COUNT(*) AS class_count
                    FROM class_sessions
                    WHERE instructor_id = $1
                      AND starts_at >= $2 AND starts_at < $3::date + INTERVAL '1 day'
                      AND status != 'cancelled'
                    """,
                    inst_id, period_start, period_end,
                )
                classes_taught = class_row["class_count"]

                # Calculate pay
                hourly_pay_cents = 0
                overtime_pay_cents = 0
                class_pay_cents = 0

                salary_cents = inst["salary_cents"] or 0

                if pay_type == "hourly":
                    hourly_pay_cents = int(Decimal(str(regular_mins)) / 60 * pay_rate)
                    overtime_pay_cents = int(Decimal(str(ot_mins)) / 60 * pay_rate * Decimal("1.5"))
                elif pay_type == "per_class":
                    class_pay_cents = classes_taught * pay_rate

                # ── Private Sessions ───────────────────────────────────
                # Same logic as get_payroll_report: count every completed
                # session regardless of payment_status (pack-credit
                # deliveries arrive as 'unpaid' but the studio collected
                # at pack-purchase time). Effective revenue per session
                # falls back to the package per-session rate, then the
                # service's flat catalog rate.
                priv_rows = await db.fetch(
                    """
                    SELECT pb.id,
                           COALESCE(
                               NULLIF(pb.price_cents, 0),
                               CASE
                                   WHEN COALESCE(ps.package_sessions, 0) > 0
                                   THEN ps.package_price_cents / ps.package_sessions
                                   ELSE NULLIF(ps.price_cents, 0)
                               END,
                               0
                           ) AS effective_revenue_cents
                    FROM private_bookings pb
                    LEFT JOIN private_services ps ON ps.id = pb.private_service_id
                    WHERE pb.instructor_id = $1
                      AND pb.starts_at >= $2::date
                      AND pb.starts_at < $3::date + INTERVAL '1 day'
                      AND pb.status = 'completed'
                    """,
                    inst_id, period_start, period_end,
                )
                priv_count = len(priv_rows)
                priv_revenue_cents = sum(
                    (r["effective_revenue_cents"] or 0) for r in priv_rows
                )
                priv_pay_percent = inst["private_session_pay_percent"] or 70
                priv_pay_cents = int(priv_revenue_cents * priv_pay_percent / 100)

                # ── Workshops / Trainings ──────────────────────────────
                # Guests with c.guest_instructor_id IS NOT NULL have
                # c.instructor_id IS NULL by design and never match here
                # — guest 1099s are not on staff payroll.
                workshop_rows = await db.fetch(
                    """
                    SELECT c.id, c.type,
                           COALESCE(SUM(ce.paid_price_cents), 0) AS revenue_cents
                    FROM courses c
                    LEFT JOIN course_enrollments ce ON ce.course_id = c.id
                        AND ce.status IN ('enrolled', 'completed')
                    WHERE c.instructor_id = $1
                      AND c.starts_at >= $2::date
                      AND c.starts_at < $3::date + INTERVAL '1 day'
                      AND c.status IN ('published', 'completed')
                    GROUP BY c.id, c.type
                    """,
                    inst_id, period_start, period_end,
                )
                workshop_count = 0
                workshop_revenue_cents = 0
                training_revenue_cents = 0
                for wr in workshop_rows:
                    rev = wr["revenue_cents"] or 0
                    if wr["type"] == "teacher_training":
                        training_revenue_cents += rev
                    else:
                        workshop_count += 1
                        workshop_revenue_cents += rev

                ws_pay_percent = inst["workshop_pay_percent"] or 60
                tr_pay_percent = inst["training_pay_percent"] or 50
                workshop_pay_cents = int(workshop_revenue_cents * ws_pay_percent / 100)
                training_pay_cents = int(training_revenue_cents * tr_pay_percent / 100)

                line_total = (
                    salary_cents
                    + hourly_pay_cents
                    + overtime_pay_cents
                    + class_pay_cents
                    + priv_pay_cents
                    + workshop_pay_cents
                    + training_pay_cents
                )

                # Skip instructors with no activity AND no salary
                if (total_mins == 0 and classes_taught == 0 and salary_cents == 0
                        and priv_count == 0 and workshop_count == 0
                        and training_revenue_cents == 0):
                    continue

                line_id = str(uuid.uuid4())
                await db.execute(
                    """
                    INSERT INTO payroll_line_items
                        (id, payroll_run_id, instructor_id, hours_worked, overtime_hours,
                         classes_taught, class_pay_cents, hourly_pay_cents,
                         overtime_pay_cents,
                         private_sessions_count, private_session_revenue_cents,
                         private_session_pay_cents,
                         workshops_count, workshop_revenue_cents,
                         workshop_pay_cents, training_pay_cents,
                         total_gross_cents)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                            $10, $11, $12,
                            $13, $14, $15, $16, $17)
                    """,
                    line_id, run_id, inst_id,
                    hours_worked, overtime_hours,
                    classes_taught, class_pay_cents,
                    hourly_pay_cents, overtime_pay_cents,
                    priv_count, priv_revenue_cents, priv_pay_cents,
                    workshop_count, workshop_revenue_cents,
                    workshop_pay_cents, training_pay_cents,
                    line_total,
                )

                total_gross += line_total
                total_hours += hours_worked

            # ── Guest Instructors (1099 workshop contractors) ──────────
            # Same shape as the staff loop above, but line items are
            # keyed on guest_instructor_id (see migration a34_payroll_guest).
            # Guest workshops are courses with c.guest_instructor_id set;
            # the staff loop never touches these because c.instructor_id
            # is NULL on those rows.
            guest_workshops = await db.fetch(
                """
                SELECT gi.id AS guest_id, gi.name,
                       gi.revenue_share_percent_to_guest AS share_pct,
                       c.id AS course_id, c.type,
                       COALESCE(SUM(ce.paid_price_cents), 0) AS revenue_cents
                FROM guest_instructors gi
                JOIN courses c ON c.guest_instructor_id = gi.id
                LEFT JOIN course_enrollments ce ON ce.course_id = c.id
                    AND ce.status IN ('enrolled', 'completed')
                WHERE c.starts_at >= $1::date
                  AND c.starts_at < $2::date + INTERVAL '1 day'
                  AND c.status IN ('published', 'completed', 'in_progress')
                GROUP BY gi.id, gi.name, gi.revenue_share_percent_to_guest,
                         c.id, c.type
                """,
                period_start, period_end,
            )

            by_guest: dict[str, dict] = {}
            for gw in guest_workshops:
                gid = str(gw["guest_id"])
                if gid not in by_guest:
                    by_guest[gid] = {
                        "name": gw["name"],
                        "share_pct": gw["share_pct"] or 60,
                        "workshop_count": 0,
                        "workshop_rev": 0,
                        "training_rev": 0,
                    }
                rev = gw["revenue_cents"] or 0
                if gw["type"] == "teacher_training":
                    by_guest[gid]["training_rev"] += rev
                else:
                    by_guest[gid]["workshop_count"] += 1
                    by_guest[gid]["workshop_rev"] += rev

            for gid, g in by_guest.items():
                workshop_pay = int(g["workshop_rev"] * g["share_pct"] / 100)
                training_pay = int(g["training_rev"] * g["share_pct"] / 100)
                line_total = workshop_pay + training_pay
                if line_total == 0:
                    continue
                line_id = str(uuid.uuid4())
                await db.execute(
                    """
                    INSERT INTO payroll_line_items
                        (id, payroll_run_id, guest_instructor_id,
                         workshops_count, workshop_revenue_cents,
                         workshop_pay_cents, training_pay_cents,
                         total_gross_cents)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    line_id, run_id, gid,
                    g["workshop_count"], g["workshop_rev"],
                    workshop_pay, training_pay, line_total,
                )
                total_gross += line_total

            # Update run totals
            await db.execute(
                """
                UPDATE payroll_runs
                SET total_gross_cents = $2, total_hours = $3, updated_at = NOW()
                WHERE id = $1
                """,
                run_id, total_gross, total_hours,
            )

            run = await db.fetchrow("SELECT * FROM payroll_runs WHERE id = $1", run_id)

        logger.info(
            "Payroll compiled",
            run_id=run_id,
            period=f"{period_start} to {period_end}",
            total_gross=total_gross,
        )
        return _run_to_dict(run)

    async def get_payroll_run(self, run_id: str) -> dict | None:
        """Get a payroll run with its line items."""
        async with get_tenant_db() as db:
            run = await db.fetchrow("SELECT * FROM payroll_runs WHERE id = $1", run_id)
            if not run:
                return None
            # LEFT JOIN both kinds — the line item's owner is whichever
            # of instructor_id / guest_instructor_id is set (XOR'd by
            # migration a34_payroll_guest). Display name comes from the
            # matching table, with "(guest)" suffix for guest rows so
            # the detail page distinguishes them at a glance.
            items = await db.fetch(
                """
                SELECT pli.*,
                       COALESCE(i.display_name, gi.name || ' (guest)') AS instructor_name,
                       (pli.guest_instructor_id IS NOT NULL) AS is_guest_instructor
                FROM payroll_line_items pli
                LEFT JOIN instructors i        ON i.id  = pli.instructor_id
                LEFT JOIN guest_instructors gi ON gi.id = pli.guest_instructor_id
                WHERE pli.payroll_run_id = $1
                ORDER BY pli.total_gross_cents DESC
                """,
                run_id,
            )
        result = _run_to_dict(run)
        result["line_items"] = [_line_item_to_dict(r) for r in items]
        return result

    async def list_payroll_runs(self) -> list[dict]:
        """List all payroll runs, most recent first."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                "SELECT * FROM payroll_runs ORDER BY period_start DESC"
            )
        return [_run_to_dict(r) for r in rows]

    async def finalize_payroll(self, run_id: str) -> dict | None:
        """Finalize a payroll run: lock the run AND mark every line
        item as paid in a single transaction.

        Don's workflow is "everyone gets paid at the same time" — the
        whole run flips together. The previous two-step (Finalize, then
        per-instructor Mark Paid) created confusion and orphan runs.
        Now Approve & Export → finalize_payroll → CSV/Gusto/QB push
        is one click and one transaction.

        Idempotent on paid_at: only sets it where it's NULL, so
        re-finalizing (which shouldn't happen, but defensively) won't
        retroactively rewrite who-paid-when timestamps.
        """
        async with get_tenant_db() as db:
            async with db.transaction():
                await db.execute(
                    """
                    UPDATE payroll_runs
                    SET status = 'finalized', finalized_at = NOW(), updated_at = NOW()
                    WHERE id = $1
                    """,
                    run_id,
                )
                await db.execute(
                    """
                    UPDATE payroll_line_items
                    SET paid_at = NOW()
                    WHERE payroll_run_id = $1 AND paid_at IS NULL
                    """,
                    run_id,
                )
            run = await db.fetchrow("SELECT * FROM payroll_runs WHERE id = $1", run_id)
        return _run_to_dict(run) if run else None


# ── Serialization Helpers ────────────────────────────────────────────────────

def _entry_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "instructor_id", "approved_by"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("clock_in", "clock_out", "approved_at", "created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


def _run_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "created_by"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("period_start", "period_end"):
        if d.get(k):
            d[k] = d[k].isoformat()
    for k in ("finalized_at", "created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    if d.get("total_hours"):
        d["total_hours"] = float(d["total_hours"])
    return d


def _line_item_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "payroll_run_id", "instructor_id", "guest_instructor_id"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("hours_worked", "overtime_hours"):
        if d.get(k):
            d[k] = float(d[k])
    for k in ("created_at", "paid_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d
