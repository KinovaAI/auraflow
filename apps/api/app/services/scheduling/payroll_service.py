"""AuraFlow — Instructor Payroll / Compensation Service

Calculates instructor compensation based on group classes, private sessions,
and workshops taught within a given month.
"""
import uuid
from datetime import date

from app.core.logging import logger
from app.db.session import get_tenant_db


class PayrollService:

    async def get_payroll_report(
        self,
        month: str,
        instructor_id: str | None = None,
    ) -> list[dict]:
        """Calculate payroll for all (or one) instructors for a given month.

        Args:
            month: 'YYYY-MM' format
            instructor_id: optional filter
        """
        from datetime import date as date_type
        year, mon = month.split("-")
        period_start = date_type(int(year), int(mon), 1)
        next_mon = int(mon) + 1
        next_year = int(year)
        if next_mon > 12:
            next_mon = 1
            next_year += 1
        period_end = date_type(next_year, next_mon, 1)

        async with get_tenant_db() as db:
            # Get instructors
            instr_query = "SELECT * FROM instructors WHERE is_active = TRUE"
            instr_params: list = []
            if instructor_id:
                instr_query += " AND id = $1"
                instr_params.append(instructor_id)
            instr_query += " ORDER BY sort_order, display_name"
            instructors = await db.fetch(instr_query, *instr_params)

            results = []
            for instr in instructors:
                iid = str(instr["id"])

                # ── Group Classes ──────────────────────────────────────
                group_rows = await db.fetch(
                    """
                    SELECT id, starts_at, ends_at, drop_in_price_cents,
                           dynamic_price_cents
                    FROM class_sessions
                    WHERE (instructor_id = $1 OR substitute_instructor_id = $1)
                      AND starts_at >= $2::date AND starts_at < $3::date
                      AND status IN ('completed', 'scheduled')
                      AND starts_at < NOW()
                    """,
                    iid, period_start, period_end,
                )
                group_count = len(group_rows)

                # Calculate group revenue (sum of drop-in payments for these
                # sessions). bookings has no drop_in_price_cents column —
                # the price lives on class_sessions only — so just multiply
                # the session's drop_in price by the count of confirmed
                # bookings against it.
                group_revenue_cents = 0
                for sess in group_rows:
                    rev = await db.fetchval(
                        """
                        SELECT COALESCE(cs.drop_in_price_cents, 0)
                               * (SELECT COUNT(*) FROM bookings b
                                  WHERE b.class_session_id = cs.id
                                    AND b.status = 'confirmed')
                        FROM class_sessions cs
                        WHERE cs.id = $1
                        """,
                        str(sess["id"]),
                    )
                    group_revenue_cents += rev or 0

                # Calculate group class pay. Salaried instructors get
                # zero group-class pay — their salary covers it. Only
                # hourly / per_class / percentage compensation models
                # add a line item here. The previous `else` branch
                # silently fell through to classes × pay_rate, which
                # caused salaried instructors with a non-zero pay_rate
                # (e.g. Terri at $1000) to be over-paid by 23×$1000 =
                # $23,000 in a single month report.
                pay_type = instr["pay_type"] or "per_class"
                pay_rate = instr["pay_rate_cents"] or 0
                if pay_type == "per_class":
                    group_class_pay_cents = group_count * pay_rate
                elif pay_type == "hourly":
                    total_minutes = 0
                    for sess in group_rows:
                        if sess["starts_at"] and sess["ends_at"]:
                            delta = sess["ends_at"] - sess["starts_at"]
                            total_minutes += delta.total_seconds() / 60
                    hours = total_minutes / 60
                    group_class_pay_cents = int(hours * pay_rate)
                elif pay_type == "percentage":
                    group_class_pay_cents = int(
                        group_revenue_cents * (pay_rate / 10000)
                    )
                else:
                    # Salary or unknown pay_type → no group-class pay.
                    group_class_pay_cents = 0

                # ── Private Sessions ───────────────────────────────────
                # The instructor is paid for delivering the session, not
                # for collecting payment. Pack-credit sessions arrive as
                # payment_status='unpaid' (the studio collected once,
                # when the pack was sold), but the instructor still
                # earned their cut on delivery. So count every completed
                # session regardless of payment_status.
                #
                # Effective revenue per session:
                #   1. booking.price_cents if non-zero (e.g., paid drop-in)
                #   2. else the service's price_cents (catalog rate)
                #   3. else package_price_cents / package_sessions
                #      (pack-credit sessions on a package service)
                # Note on package services: when private_services has
                # package_sessions > 0, its `price_cents` holds the FULL
                # pack price (e.g. $250 for 8 sessions). Per-session rate
                # is package_price_cents / package_sessions ($31.25). So
                # check the package fields BEFORE falling back to the
                # service's flat price_cents.
                priv_rows = await db.fetch(
                    """
                    SELECT pb.id, pb.price_cents, pb.payment_status,
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
                      AND pb.starts_at >= $2::date AND pb.starts_at < $3::date
                      AND pb.status = 'completed'
                    """,
                    iid, period_start, period_end,
                )
                priv_count = len(priv_rows)
                # Informational splits (no longer affect pay). The booking
                # rows are still tagged paid/unpaid for accounting on the
                # cash side, but pay computes off effective revenue.
                priv_paid_rows = [r for r in priv_rows if r.get("payment_status") == "paid"]
                priv_unpaid_rows = [r for r in priv_rows if r.get("payment_status") != "paid"]
                priv_revenue_cents = sum(
                    (r["effective_revenue_cents"] or 0) for r in priv_rows
                )
                priv_unpaid_cents = sum(
                    (r["effective_revenue_cents"] or 0) for r in priv_unpaid_rows
                )
                priv_pay_percent = instr["private_session_pay_percent"] or 70
                priv_pay_cents = int(priv_revenue_cents * priv_pay_percent / 100)

                # ── Workshops / Teacher Trainings ──────────────────────
                workshop_rows = await db.fetch(
                    """
                    SELECT c.id, c.type,
                           COALESCE(SUM(ce.paid_price_cents), 0) AS revenue_cents
                    FROM courses c
                    LEFT JOIN course_enrollments ce ON ce.course_id = c.id
                        AND ce.status IN ('enrolled', 'completed')
                    WHERE c.instructor_id = $1
                      AND c.starts_at >= $2::date AND c.starts_at < $3::date
                      AND c.status IN ('published', 'completed')
                    GROUP BY c.id, c.type
                    """,
                    iid, period_start, period_end,
                )
                workshop_count = 0
                workshop_revenue_cents = 0
                training_revenue_cents = 0
                for wr in workshop_rows:
                    rev = wr["revenue_cents"] or 0
                    if wr["type"] == "training":
                        training_revenue_cents += rev
                    else:
                        workshop_count += 1
                        workshop_revenue_cents += rev

                ws_pay_percent = instr["workshop_pay_percent"] or 60
                tr_pay_percent = instr["training_pay_percent"] or 50
                workshop_pay_cents = int(
                    workshop_revenue_cents * ws_pay_percent / 100
                )
                training_pay_cents = int(
                    training_revenue_cents * tr_pay_percent / 100
                )

                # Monthly salary
                salary_cents = instr["salary_cents"] or 0

                total_owed_cents = (
                    salary_cents
                    + group_class_pay_cents
                    + priv_pay_cents
                    + workshop_pay_cents
                    + training_pay_cents
                )

                # Check if already marked as paid for this period.
                # Same lookup for both staff and guests further down — for
                # staff, the FK is instructor_id; for guests it's
                # guest_instructor_id (see migration a34_payroll_guest).
                paid_row = await db.fetchrow(
                    """
                    SELECT pli.paid_at
                    FROM payroll_line_items pli
                    JOIN payroll_runs pr ON pr.id = pli.payroll_run_id
                    WHERE pli.instructor_id = $1
                      AND pr.period_start = $2::date
                      AND pli.paid_at IS NOT NULL
                    LIMIT 1
                    """,
                    iid, period_start,
                )

                results.append({
                    "instructor_id": iid,
                    "instructor_name": instr["display_name"],
                    "tax_classification": instr["tax_classification"] or "1099",
                    "pay_type": pay_type,
                    "pay_rate_cents": pay_rate,
                    "salary_cents": salary_cents,
                    "group_classes_count": group_count,
                    "group_revenue_cents": group_revenue_cents,
                    "group_class_pay_cents": group_class_pay_cents,
                    "private_sessions_count": priv_count,
                    "private_sessions_paid_count": len(priv_paid_rows),
                    "private_sessions_unpaid_count": len(priv_unpaid_rows),
                    "private_session_revenue_cents": priv_revenue_cents,
                    "private_session_unpaid_cents": priv_unpaid_cents,
                    "private_session_pay_cents": priv_pay_cents,
                    "workshops_count": workshop_count,
                    "workshop_revenue_cents": workshop_revenue_cents,
                    "workshop_pay_cents": workshop_pay_cents,
                    "training_pay_cents": training_pay_cents,
                    "total_owed_cents": total_owed_cents,
                    "paid_at": str(paid_row["paid_at"]) if paid_row else None,
                    "is_guest_instructor": False,
                })

            # ── Guest Instructors ─────────────────────────────────────────
            # Guest instructors (1099 contractors) teach standalone workshops
            # that have guest_instructor_id set on the course (instructor_id
            # is NULL in that case). Their cut is per-workshop: a fraction of
            # course revenue defined by revenue_share_percent_to_guest on the
            # guest_instructors row (default 60%). The staff loop above only
            # touches the instructors table so guest workshops were invisible
            # in payroll, leaving owners to track guest payouts by hand.
            #
            # Guest rows are surfaced when the report is unfiltered AND
            # when the filter ID happens to be a guest's ID — so mark_paid
            # can call get_payroll_report(month, guest_id) and get back
            # exactly one row for that guest.
            guest_filter_sql = ""
            guest_filter_params: list = [period_start, period_end]
            if instructor_id:
                guest_filter_sql = " AND gi.id = $3"
                guest_filter_params.append(instructor_id)

            # tax_id_encrypted exists because guest tax IDs are HIPAA-
            # encrypted at rest (Fernet on the BYTEA column). We only
            # need a presence flag here so the UI can surface "tax ID
            # missing — collect a W-9 before paying" — never decrypt
            # the value for a payroll report.
            guest_rows = await db.fetch(
                f"""
                SELECT gi.id, gi.name, gi.email, gi.revenue_share_percent_to_guest,
                       (gi.tax_id_encrypted IS NOT NULL) AS has_tax_id,
                       c.id AS course_id, c.title, c.type,
                       COALESCE(SUM(ce.paid_price_cents), 0) AS revenue_cents
                FROM guest_instructors gi
                JOIN courses c ON c.guest_instructor_id = gi.id
                LEFT JOIN course_enrollments ce ON ce.course_id = c.id
                    AND ce.status IN ('enrolled', 'completed')
                WHERE c.starts_at >= $1::date AND c.starts_at < $2::date
                  AND c.status IN ('published', 'completed', 'in_progress')
                  {guest_filter_sql}
                GROUP BY gi.id, gi.name, gi.email, gi.revenue_share_percent_to_guest,
                         gi.tax_id_encrypted, c.id, c.title, c.type
                ORDER BY gi.name, c.starts_at
                """,
                *guest_filter_params,
            )

            if guest_rows:

                # Aggregate per-guest. Each guest gets one row in the report
                # listing the total workshops + total payout for the month.
                by_guest: dict[str, dict] = {}
                for gr in guest_rows:
                    gid = str(gr["id"])
                    if gid not in by_guest:
                        by_guest[gid] = {
                            "id": gid,
                            "name": gr["name"],
                            "share_percent": gr["revenue_share_percent_to_guest"] or 60,
                            "tax_id_on_file": bool(gr["has_tax_id"]),
                            "workshops": [],
                        }
                    by_guest[gid]["workshops"].append({
                        "course_id": str(gr["course_id"]),
                        "title": gr["title"],
                        "type": gr["type"],
                        "revenue_cents": gr["revenue_cents"] or 0,
                    })

                for gid, g in by_guest.items():
                    workshops = g["workshops"]
                    workshop_only = [w for w in workshops if w["type"] != "training"]
                    training_only = [w for w in workshops if w["type"] == "training"]
                    workshop_rev = sum(w["revenue_cents"] for w in workshop_only)
                    training_rev = sum(w["revenue_cents"] for w in training_only)
                    share_pct = g["share_percent"]
                    workshop_pay = int(workshop_rev * share_pct / 100)
                    training_pay = int(training_rev * share_pct / 100)
                    total = workshop_pay + training_pay

                    # Has this guest been marked paid for this period?
                    guest_paid_row = await db.fetchrow(
                        """
                        SELECT pli.paid_at
                        FROM payroll_line_items pli
                        JOIN payroll_runs pr ON pr.id = pli.payroll_run_id
                        WHERE pli.guest_instructor_id = $1
                          AND pr.period_start = $2::date
                          AND pli.paid_at IS NOT NULL
                        LIMIT 1
                        """,
                        gid, period_start,
                    )

                    results.append({
                        # The instructor_id field carries the guest's UUID so
                        # the frontend can still key rows uniquely. mark_paid
                        # detects guest IDs and routes the insert through
                        # payroll_line_items.guest_instructor_id (see migration
                        # a34_payroll_guest).
                        "instructor_id": gid,
                        "instructor_name": f"{g['name']} (guest)",
                        "tax_classification": "1099",
                        "pay_type": "guest_revenue_share",
                        "pay_rate_cents": 0,
                        "salary_cents": 0,
                        "group_classes_count": 0,
                        "group_revenue_cents": 0,
                        "group_class_pay_cents": 0,
                        "private_sessions_count": 0,
                        "private_sessions_paid_count": 0,
                        "private_sessions_unpaid_count": 0,
                        "private_session_revenue_cents": 0,
                        "private_session_unpaid_cents": 0,
                        "private_session_pay_cents": 0,
                        "workshops_count": len(workshop_only),
                        "workshop_revenue_cents": workshop_rev,
                        "workshop_pay_cents": workshop_pay,
                        "training_pay_cents": training_pay,
                        "total_owed_cents": total,
                        "paid_at": str(guest_paid_row["paid_at"]) if guest_paid_row else None,
                        "is_guest_instructor": True,
                        "guest_share_percent": share_pct,
                        "guest_tax_id_on_file": g["tax_id_on_file"],
                        "guest_workshops": [
                            {
                                "title": w["title"],
                                "type": w["type"],
                                "revenue_cents": w["revenue_cents"],
                                "pay_cents": int(w["revenue_cents"] * share_pct / 100),
                            }
                            for w in workshops
                        ],
                    })

        return results

    async def mark_paid(
        self,
        instructor_id: str,
        month: str,
        paid_by: str,
    ) -> dict:
        """Record an instructor (staff or guest) as paid for a given month.

        Creates or updates the payroll_run and payroll_line_item records.
        `instructor_id` here is the ID surfaced in the payroll report —
        it may be either an instructors.id (staff) or a guest_instructors.id
        (guest). The service detects which and writes to the matching
        column on payroll_line_items.

        period_end MUST be the last day of the month, not the first day
        of the following month, so this matches compile_payroll's
        convention. Otherwise mark_paid spawns a parallel orphan run
        (e.g. 4/01-5/01) that the dashboard's "April" list — which
        keys on 4/30 — never surfaces.
        """
        from datetime import timedelta as _td
        year, mon = month.split("-")
        period_start = date(int(year), int(mon), 1)
        next_mon = int(mon) + 1
        next_year = int(year)
        if next_mon > 12:
            next_mon = 1
            next_year += 1
        period_end = date(next_year, next_mon, 1) - _td(days=1)

        # Get the current report data — works for both staff and guest IDs
        # because get_payroll_report falls through to the guest loop when
        # the filter ID matches a guest_instructors row.
        report = await self.get_payroll_report(month, instructor_id)
        if not report:
            return {"error": "Instructor not found or no data"}

        data = report[0]
        is_guest = bool(data.get("is_guest_instructor"))

        async with get_tenant_db() as db:
            # Find existing run by period_start only — compile_payroll
            # may have created it with a slightly different period_end
            # (e.g. last-day-of-month-minus-one for a 30-day rolling
            # window vs. exact end-of-month). Matching exactly on both
            # dates was spawning orphan runs every time a guest line
            # item was added after staff had already been compiled.
            # When found, reuse the exact period_end so the existing
            # row gets updated instead of duplicated.
            run = await db.fetchrow(
                """
                SELECT id, period_end FROM payroll_runs
                WHERE period_start = $1
                ORDER BY created_at ASC
                LIMIT 1
                """,
                period_start,
            )
            if not run:
                run_id = str(uuid.uuid4())
                await db.execute(
                    """
                    INSERT INTO payroll_runs
                        (id, period_start, period_end, status, total_gross_cents)
                    VALUES ($1, $2, $3, 'draft', 0)
                    """,
                    run_id, period_start, period_end,
                )
            else:
                run_id = str(run["id"])
                # Adopt the existing run's period_end so further lookups
                # (e.g. get_payroll_report's paid_at check) stay coherent.
                period_end = run["period_end"]

            # Upsert payroll_line_item — different conflict target + ID
            # column depending on whether this is a staff or guest row.
            # See migration a34_payroll_guest for the partial unique
            # indexes that back these ON CONFLICTs.
            line_id = str(uuid.uuid4())
            common_args = (
                line_id, run_id,
                data["group_classes_count"],
                data["group_class_pay_cents"],
                data["private_sessions_count"],
                data["private_session_revenue_cents"],
                data["private_session_pay_cents"],
                data["workshops_count"],
                data["workshop_revenue_cents"],
                data["workshop_pay_cents"],
                data["training_pay_cents"],
                data["total_owed_cents"],
                paid_by,
            )
            if is_guest:
                await db.execute(
                    """
                    INSERT INTO payroll_line_items
                        (id, payroll_run_id, guest_instructor_id, classes_taught,
                         class_pay_cents, private_sessions_count,
                         private_session_revenue_cents, private_session_pay_cents,
                         workshops_count, workshop_revenue_cents, workshop_pay_cents,
                         training_pay_cents, total_gross_cents, paid_at, paid_by)
                    VALUES ($1, $2, $14, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW(), $13)
                    ON CONFLICT (payroll_run_id, guest_instructor_id)
                        WHERE guest_instructor_id IS NOT NULL
                    DO UPDATE SET
                        classes_taught = EXCLUDED.classes_taught,
                        class_pay_cents = EXCLUDED.class_pay_cents,
                        private_sessions_count = EXCLUDED.private_sessions_count,
                        private_session_revenue_cents = EXCLUDED.private_session_revenue_cents,
                        private_session_pay_cents = EXCLUDED.private_session_pay_cents,
                        workshops_count = EXCLUDED.workshops_count,
                        workshop_revenue_cents = EXCLUDED.workshop_revenue_cents,
                        workshop_pay_cents = EXCLUDED.workshop_pay_cents,
                        training_pay_cents = EXCLUDED.training_pay_cents,
                        total_gross_cents = EXCLUDED.total_gross_cents,
                        paid_at = NOW(),
                        paid_by = EXCLUDED.paid_by
                    """,
                    *common_args, instructor_id,
                )
            else:
                await db.execute(
                    """
                    INSERT INTO payroll_line_items
                        (id, payroll_run_id, instructor_id, classes_taught,
                         class_pay_cents, private_sessions_count,
                         private_session_revenue_cents, private_session_pay_cents,
                         workshops_count, workshop_revenue_cents, workshop_pay_cents,
                         training_pay_cents, total_gross_cents, paid_at, paid_by)
                    VALUES ($1, $2, $14, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW(), $13)
                    ON CONFLICT (payroll_run_id, instructor_id)
                        WHERE instructor_id IS NOT NULL
                    DO UPDATE SET
                        classes_taught = EXCLUDED.classes_taught,
                        class_pay_cents = EXCLUDED.class_pay_cents,
                        private_sessions_count = EXCLUDED.private_sessions_count,
                        private_session_revenue_cents = EXCLUDED.private_session_revenue_cents,
                        private_session_pay_cents = EXCLUDED.private_session_pay_cents,
                        workshops_count = EXCLUDED.workshops_count,
                        workshop_revenue_cents = EXCLUDED.workshop_revenue_cents,
                        workshop_pay_cents = EXCLUDED.workshop_pay_cents,
                        training_pay_cents = EXCLUDED.training_pay_cents,
                        total_gross_cents = EXCLUDED.total_gross_cents,
                        paid_at = NOW(),
                        paid_by = EXCLUDED.paid_by
                    """,
                    *common_args, instructor_id,
                )

            # Update payroll_run total
            total = await db.fetchval(
                """
                SELECT COALESCE(SUM(total_gross_cents), 0)
                FROM payroll_line_items WHERE payroll_run_id = $1
                """,
                run_id,
            )
            await db.execute(
                "UPDATE payroll_runs SET total_gross_cents = $1, updated_at = NOW() WHERE id = $2",
                total, run_id,
            )

        logger.info(
            "Instructor marked as paid",
            instructor_id=instructor_id,
            is_guest=is_guest,
            month=month,
            total_cents=data["total_owed_cents"],
        )
        return {
            "status": "paid",
            "instructor_id": instructor_id,
            "month": month,
            "is_guest_instructor": is_guest,
        }

    async def get_payroll_history(
        self,
        instructor_id: str | None = None,
        limit: int = 12,
    ) -> list[dict]:
        """Get past payroll records (staff + guest)."""
        async with get_tenant_db() as db:
            if instructor_id:
                # The caller may pass either an instructors.id or a
                # guest_instructors.id. Match on whichever column actually
                # references the row, and resolve the display name from
                # the matching table.
                rows = await db.fetch(
                    """
                    SELECT pr.period_start, pr.period_end, pr.status,
                           COALESCE(pli.instructor_id, pli.guest_instructor_id) AS instructor_id,
                           COALESCE(i.display_name, gi.name || ' (guest)') AS instructor_name,
                           (pli.guest_instructor_id IS NOT NULL) AS is_guest_instructor,
                           pli.classes_taught, pli.class_pay_cents,
                           pli.private_sessions_count, pli.private_session_pay_cents,
                           pli.workshops_count, pli.workshop_pay_cents,
                           pli.training_pay_cents, pli.total_gross_cents,
                           pli.paid_at
                    FROM payroll_line_items pli
                    JOIN payroll_runs pr ON pr.id = pli.payroll_run_id
                    LEFT JOIN instructors i       ON i.id  = pli.instructor_id
                    LEFT JOIN guest_instructors gi ON gi.id = pli.guest_instructor_id
                    WHERE pli.instructor_id = $1 OR pli.guest_instructor_id = $1
                    ORDER BY pr.period_start DESC
                    LIMIT $2
                    """,
                    instructor_id, limit,
                )
            else:
                rows = await db.fetch(
                    """
                    SELECT pr.period_start, pr.period_end, pr.status,
                           COALESCE(pli.instructor_id, pli.guest_instructor_id) AS instructor_id,
                           COALESCE(i.display_name, gi.name || ' (guest)') AS instructor_name,
                           (pli.guest_instructor_id IS NOT NULL) AS is_guest_instructor,
                           pli.classes_taught, pli.class_pay_cents,
                           pli.private_sessions_count, pli.private_session_pay_cents,
                           pli.workshops_count, pli.workshop_pay_cents,
                           pli.training_pay_cents, pli.total_gross_cents,
                           pli.paid_at
                    FROM payroll_line_items pli
                    JOIN payroll_runs pr ON pr.id = pli.payroll_run_id
                    LEFT JOIN instructors i       ON i.id  = pli.instructor_id
                    LEFT JOIN guest_instructors gi ON gi.id = pli.guest_instructor_id
                    ORDER BY pr.period_start DESC
                    LIMIT $1
                    """,
                    limit,
                )
        return [dict(r) for r in rows]
