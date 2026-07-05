"""AuraFlow — Weekly Payout Report DAG

Runs every Monday at 8:00 AM UTC. Generates a weekly revenue report
with day-by-day breakdown and week-over-week comparison.
"""
from datetime import datetime, timedelta

from airflow.decorators import dag, task

from helpers.db import get_tenant_conn, fetch_all, fetch_one
from helpers.tenants import get_active_tenants, get_owner_email
from helpers.email_sender import send_payout_email


def _fmt_dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _pct_change(current: int, previous: int) -> str:
    if previous == 0:
        return "+100%" if current > 0 else "0%"
    pct = ((current - previous) / previous) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


def _build_weekly_email(
    tenant_name: str,
    week_start: str,
    week_end: str,
    this_week: dict,
    last_week: dict,
    daily_breakdown: list[dict],
) -> str:
    """Render the weekly payout report HTML email."""
    # Daily rows
    daily_rows = ""
    for day in daily_breakdown:
        daily_rows += f"""
        <tr>
          <td style="padding: 6px 8px; border-bottom: 1px solid #f3f4f6;">{day['date']}</td>
          <td style="padding: 6px 8px; border-bottom: 1px solid #f3f4f6; text-align: right;">{day['txn_count']}</td>
          <td style="padding: 6px 8px; border-bottom: 1px solid #f3f4f6; text-align: right;">{_fmt_dollars(day['gross_revenue'])}</td>
          <td style="padding: 6px 8px; border-bottom: 1px solid #f3f4f6; text-align: right;">{_fmt_dollars(day['net_revenue'])}</td>
        </tr>
        """

    rev_change = _pct_change(this_week["gross_revenue"], last_week["gross_revenue"])
    net_change = _pct_change(this_week["net_revenue"], last_week["net_revenue"])
    txn_change = _pct_change(this_week["txn_count"], last_week["txn_count"])

    rev_color = "#059669" if this_week["gross_revenue"] >= last_week["gross_revenue"] else "#ef4444"
    net_color = "#059669" if this_week["net_revenue"] >= last_week["net_revenue"] else "#ef4444"

    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 640px; margin: 0 auto;">
      <div style="background: #4f46e5; color: white; padding: 24px; border-radius: 8px 8px 0 0;">
        <h1 style="margin: 0; font-size: 20px;">Weekly Payout Report</h1>
        <p style="margin: 4px 0 0; opacity: 0.9;">{tenant_name} &mdash; {week_start} to {week_end}</p>
      </div>
      <div style="border: 1px solid #e5e7eb; border-top: none; padding: 24px; border-radius: 0 0 8px 8px;">

        <h2 style="font-size: 16px; margin: 0 0 12px;">Week Summary</h2>
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px;">
          <tr style="background: #f9fafb;">
            <th style="padding: 8px; text-align: left; font-size: 13px; color: #6b7280;"></th>
            <th style="padding: 8px; text-align: right; font-size: 13px; color: #6b7280;">This Week</th>
            <th style="padding: 8px; text-align: right; font-size: 13px; color: #6b7280;">Last Week</th>
            <th style="padding: 8px; text-align: right; font-size: 13px; color: #6b7280;">Change</th>
          </tr>
          <tr>
            <td style="padding: 8px;">Gross Revenue</td>
            <td style="padding: 8px; text-align: right; font-weight: 600;">{_fmt_dollars(this_week['gross_revenue'])}</td>
            <td style="padding: 8px; text-align: right; color: #6b7280;">{_fmt_dollars(last_week['gross_revenue'])}</td>
            <td style="padding: 8px; text-align: right; color: {rev_color}; font-weight: 600;">{rev_change}</td>
          </tr>
          <tr>
            <td style="padding: 8px;">Net Revenue</td>
            <td style="padding: 8px; text-align: right; font-weight: 600;">{_fmt_dollars(this_week['net_revenue'])}</td>
            <td style="padding: 8px; text-align: right; color: #6b7280;">{_fmt_dollars(last_week['net_revenue'])}</td>
            <td style="padding: 8px; text-align: right; color: {net_color}; font-weight: 600;">{net_change}</td>
          </tr>
          <tr>
            <td style="padding: 8px;">Transactions</td>
            <td style="padding: 8px; text-align: right; font-weight: 600;">{this_week['txn_count']}</td>
            <td style="padding: 8px; text-align: right; color: #6b7280;">{last_week['txn_count']}</td>
            <td style="padding: 8px; text-align: right;">{txn_change}</td>
          </tr>
          <tr>
            <td style="padding: 8px;">Fees</td>
            <td style="padding: 8px; text-align: right; color: #ef4444;">&minus;{_fmt_dollars(this_week['total_fees'])}</td>
            <td style="padding: 8px; text-align: right; color: #6b7280;">&minus;{_fmt_dollars(last_week['total_fees'])}</td>
            <td style="padding: 8px; text-align: right;"></td>
          </tr>
          <tr>
            <td style="padding: 8px;">Refunds</td>
            <td style="padding: 8px; text-align: right; color: #ef4444;">&minus;{_fmt_dollars(this_week['refunds'])}</td>
            <td style="padding: 8px; text-align: right; color: #6b7280;">&minus;{_fmt_dollars(last_week['refunds'])}</td>
            <td style="padding: 8px; text-align: right;"></td>
          </tr>
        </table>

        <h2 style="font-size: 16px; margin: 0 0 12px;">Daily Breakdown</h2>
        <table style="width: 100%; border-collapse: collapse;">
          <tr style="background: #f9fafb;">
            <th style="padding: 6px 8px; text-align: left; font-size: 13px; color: #6b7280;">Date</th>
            <th style="padding: 6px 8px; text-align: right; font-size: 13px; color: #6b7280;">Txns</th>
            <th style="padding: 6px 8px; text-align: right; font-size: 13px; color: #6b7280;">Gross</th>
            <th style="padding: 6px 8px; text-align: right; font-size: 13px; color: #6b7280;">Net</th>
          </tr>
          {daily_rows}
        </table>

        <p style="margin-top: 20px; font-size: 12px; color: #9ca3af;">
          This is an automated report from AuraFlow. Log in to your dashboard for full details.
        </p>
      </div>
    </div>
    """


@dag(
    dag_id="weekly_payout_report",
    schedule="0 8 * * 1",
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["payments", "reporting"],
    default_args={
        "owner": "auraflow",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
)
def weekly_payout_report():

    @task()
    def get_tenants() -> list[dict]:
        tenants = get_active_tenants()
        for t in tenants:
            t["id"] = str(t["id"])
        return tenants

    @task()
    def compute_weekly_report(tenant: dict) -> dict:
        schema = tenant["schema_name"]
        tz = tenant.get("timezone") or "UTC"

        summary_query = """
            SELECT
                COUNT(*) as txn_count,
                COALESCE(SUM(amount_cents) FILTER (WHERE status = 'completed'), 0) as gross_revenue,
                COALESCE(SUM(fee_cents) FILTER (WHERE status = 'completed'), 0) as total_fees,
                COALESCE(SUM(net_amount_cents) FILTER (WHERE status = 'completed'), 0) as net_revenue,
                COALESCE(SUM(amount_cents) FILTER (WHERE status = 'refunded'), 0) as refunds
            FROM transactions
            WHERE created_at >= %s AND created_at < %s
              AND status IN ('completed', 'refunded')
        """

        daily_query = """
            SELECT
                (created_at AT TIME ZONE %s)::date as txn_date,
                COUNT(*) as txn_count,
                COALESCE(SUM(amount_cents) FILTER (WHERE status = 'completed'), 0) as gross_revenue,
                COALESCE(SUM(net_amount_cents) FILTER (WHERE status = 'completed'), 0) as net_revenue
            FROM transactions
            WHERE created_at >= %s AND created_at < %s
              AND status IN ('completed', 'refunded')
            GROUP BY txn_date
            ORDER BY txn_date
        """

        # Date ranges: this week = last 7 days, last week = 7 days before that
        today = datetime.utcnow().date()
        this_week_end = today
        this_week_start = today - timedelta(days=7)
        last_week_end = this_week_start
        last_week_start = last_week_end - timedelta(days=7)

        with get_tenant_conn(schema) as conn:
            this_week = fetch_one(conn, summary_query, (this_week_start, this_week_end))
            last_week = fetch_one(conn, summary_query, (last_week_start, last_week_end))
            daily = fetch_all(conn, daily_query, (tz, this_week_start, this_week_end))

        empty = {"txn_count": 0, "gross_revenue": 0, "total_fees": 0, "net_revenue": 0, "refunds": 0}
        this_week = dict(this_week) if this_week else empty
        last_week = dict(last_week) if last_week else empty

        daily_breakdown = []
        for d in daily:
            daily_breakdown.append({
                "date": d["txn_date"].strftime("%a %b %d"),
                "txn_count": d["txn_count"],
                "gross_revenue": d["gross_revenue"],
                "net_revenue": d["net_revenue"],
            })

        # Store weekly summary
        if this_week["txn_count"] > 0:
            with get_tenant_conn(schema) as conn:
                from helpers.db import execute
                execute(
                    conn,
                    """
                    INSERT INTO payout_summaries
                        (report_date, period, gross_revenue_cents, fee_cents,
                         net_revenue_cents, refund_cents, transaction_count)
                    VALUES (%s, 'weekly', %s, %s, %s, %s, %s)
                    ON CONFLICT (report_date, period) DO UPDATE SET
                        gross_revenue_cents = EXCLUDED.gross_revenue_cents,
                        fee_cents = EXCLUDED.fee_cents,
                        net_revenue_cents = EXCLUDED.net_revenue_cents,
                        refund_cents = EXCLUDED.refund_cents,
                        transaction_count = EXCLUDED.transaction_count
                    """,
                    (
                        this_week_start,
                        this_week["gross_revenue"],
                        this_week["total_fees"],
                        this_week["net_revenue"],
                        this_week["refunds"],
                        this_week["txn_count"],
                    ),
                )

        return {
            "tenant": tenant,
            "this_week": this_week,
            "last_week": last_week,
            "daily_breakdown": daily_breakdown,
            "week_start": this_week_start.strftime("%B %d"),
            "week_end": (this_week_end - timedelta(days=1)).strftime("%B %d, %Y"),
        }

    @task()
    def send_weekly_emails(reports: list[dict]):
        for r in reports:
            if r["this_week"]["txn_count"] == 0:
                continue

            tenant = r["tenant"]
            owner_email = get_owner_email(tenant["id"])
            if not owner_email:
                continue

            html = _build_weekly_email(
                tenant_name=tenant["name"],
                week_start=r["week_start"],
                week_end=r["week_end"],
                this_week=r["this_week"],
                last_week=r["last_week"],
                daily_breakdown=r["daily_breakdown"],
            )
            send_payout_email(
                to_email=owner_email,
                subject=f"Weekly Payout Report — {r['week_start']} to {r['week_end']}",
                html_content=html,
            )

    tenants = get_tenants()
    reports = compute_weekly_report.expand(tenant=tenants)
    send_weekly_emails(reports)


weekly_payout_report()
