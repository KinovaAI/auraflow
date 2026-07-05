"""AuraFlow — Payroll CSV Export Service

Generates downloadable CSV from finalized payroll runs.
"""
import csv
import io

from app.core.logging import logger
from app.db.session import get_tenant_db


class PayrollCSVService:

    async def export_payroll_csv(self, run_id: str) -> tuple[str, str]:
        """
        Generate CSV content for any payroll run (draft, finalized, or
        exported). Returns (csv_string, filename). Raises ValueError
        only if the run id is unknown.

        Drafts are exportable so staff can review numbers in CSV form
        before deciding to finalize / push to Gusto / QuickBooks. The
        finalized→exported state machine only matters for downstream
        provider pushes, not for local CSV review.
        """
        async with get_tenant_db() as db:
            run = await db.fetchrow(
                "SELECT * FROM payroll_runs WHERE id = $1", run_id
            )
            if not run:
                raise ValueError("Payroll run not found")

            items = await db.fetch(
                """
                SELECT pli.*, i.display_name AS instructor_name,
                       i.email AS instructor_email,
                       i.tax_classification
                FROM payroll_line_items pli
                JOIN instructors i ON i.id = pli.instructor_id
                WHERE pli.payroll_run_id = $1
                ORDER BY i.display_name
                """,
                run_id,
            )

            # Build CSV. Mirrors what the run-detail page shows: salary
            # (derived from total minus all rate-based components),
            # then the existing hourly / OT / class columns, then the
            # private + workshop columns Don needs for review. Workshop
            # column rolls in training_pay because both are
            # %-of-revenue (just different percent rates).
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Instructor Name",
                "Email",
                "Tax Classification",
                "Salary",
                "Hours Worked",
                "Overtime Hours",
                "Classes Taught",
                "Hourly Pay",
                "Overtime Pay",
                "Class Pay",
                "Privates",
                "Private Revenue",
                "Private Pay",
                "Workshops",
                "Workshop Revenue",
                "Workshop Pay",
                "Total Gross",
            ])
            for item in items:
                priv_count = item["private_sessions_count"] or 0
                priv_rev = item["private_session_revenue_cents"] or 0
                priv_pay = item["private_session_pay_cents"] or 0
                ws_count = item["workshops_count"] or 0
                ws_rev = item["workshop_revenue_cents"] or 0
                ws_pay = (item["workshop_pay_cents"] or 0) + (item["training_pay_cents"] or 0)
                # Salary derived: total - everything else. payroll_line_items
                # has no salary_cents column, so this is the only way to
                # surface it without a schema change.
                salary_cents = (
                    item["total_gross_cents"]
                    - (item["hourly_pay_cents"] or 0)
                    - (item["overtime_pay_cents"] or 0)
                    - (item["class_pay_cents"] or 0)
                    - priv_pay
                    - ws_pay
                )
                writer.writerow([
                    item["instructor_name"],
                    item["instructor_email"] or "",
                    item["tax_classification"] or "",
                    f"{max(0, salary_cents) / 100:.2f}",
                    f"{float(item['hours_worked']):.2f}",
                    f"{float(item['overtime_hours']):.2f}",
                    item["classes_taught"],
                    f"{item['hourly_pay_cents'] / 100:.2f}",
                    f"{item['overtime_pay_cents'] / 100:.2f}",
                    f"{item['class_pay_cents'] / 100:.2f}",
                    priv_count,
                    f"{priv_rev / 100:.2f}",
                    f"{priv_pay / 100:.2f}",
                    ws_count,
                    f"{ws_rev / 100:.2f}",
                    f"{ws_pay / 100:.2f}",
                    f"{item['total_gross_cents'] / 100:.2f}",
                ])

            # Promote to 'exported' ONLY if the run is already
            # finalized. Draft downloads are review-only — flipping a
            # draft to exported here would skip the deliberate
            # finalize step and lose the audit semantics.
            if run["status"] == "finalized":
                await db.execute(
                    """
                    UPDATE payroll_runs
                    SET status = 'exported', exported_at = NOW(),
                        export_method = 'csv', updated_at = NOW()
                    WHERE id = $1
                    """,
                    run_id,
                )

        filename = f"payroll_{run['period_start']}_{run['period_end']}.csv"
        logger.info("Payroll CSV exported", run_id=run_id, filename=filename)
        return output.getvalue(), filename
