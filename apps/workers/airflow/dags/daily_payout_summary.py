"""AuraFlow — Daily Payout Summary DAG

Runs daily at 7:00 AM UTC. For each active tenant, summarizes
yesterday's transactions and emails the studio owner.
"""
from datetime import datetime, timedelta

from airflow.decorators import dag, task

from helpers.db import get_tenant_conn, fetch_one, execute
from helpers.tenants import get_active_tenants, get_owner_email
from helpers.email_sender import send_payout_email


def _fmt_dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _build_daily_email(tenant_name: str, report_date: str, s: dict) -> str:
    """Render the daily payout summary HTML email."""
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">
      <div style="background: #4f46e5; color: white; padding: 24px; border-radius: 8px 8px 0 0;">
        <h1 style="margin: 0; font-size: 20px;">Daily Payout Summary</h1>
        <p style="margin: 4px 0 0; opacity: 0.9;">{tenant_name} &mdash; {report_date}</p>
      </div>
      <div style="border: 1px solid #e5e7eb; border-top: none; padding: 24px; border-radius: 0 0 8px 8px;">
        <table style="width: 100%; border-collapse: collapse;">
          <tr>
            <td style="padding: 8px 0; color: #6b7280;">Transactions</td>
            <td style="padding: 8px 0; text-align: right; font-weight: 600;">{s['txn_count']}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #6b7280;">Gross Revenue</td>
            <td style="padding: 8px 0; text-align: right; font-weight: 600;">{_fmt_dollars(s['gross_revenue'])}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #6b7280;">Platform Fees</td>
            <td style="padding: 8px 0; text-align: right; color: #ef4444;">&minus;{_fmt_dollars(s['total_fees'])}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #6b7280;">Refunds</td>
            <td style="padding: 8px 0; text-align: right; color: #ef4444;">&minus;{_fmt_dollars(s['refunds'])}</td>
          </tr>
          <tr style="border-top: 2px solid #e5e7eb;">
            <td style="padding: 12px 0; font-weight: 700;">Net Revenue</td>
            <td style="padding: 12px 0; text-align: right; font-weight: 700; color: #059669;">{_fmt_dollars(s['net_revenue'])}</td>
          </tr>
        </table>
        <div style="margin-top: 16px; padding: 12px; background: #f9fafb; border-radius: 6px;">
          <span style="color: #6b7280; font-size: 13px;">
            Drop-ins: {s['drop_in_count']} &bull; Memberships: {s['membership_count']}
          </span>
        </div>
        <p style="margin-top: 20px; font-size: 12px; color: #9ca3af;">
          This is an automated report from AuraFlow. Log in to your dashboard for full details.
        </p>
      </div>
    </div>
    """


@dag(
    dag_id="daily_payout_summary",
    schedule="0 7 * * *",
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["payments", "reporting"],
    default_args={
        "owner": "auraflow",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
)
def daily_payout_summary():

    @task()
    def get_tenants() -> list[dict]:
        tenants = get_active_tenants()
        # Convert UUIDs to strings for JSON serialization
        for t in tenants:
            t["id"] = str(t["id"])
        return tenants

    @task()
    def compute_daily_summary(tenant: dict) -> dict:
        schema = tenant["schema_name"]
        tz = tenant.get("timezone") or "UTC"

        with get_tenant_conn(schema) as conn:
            row = fetch_one(
                conn,
                """
                SELECT
                    COUNT(*) as txn_count,
                    COALESCE(SUM(amount_cents) FILTER (WHERE status = 'completed'), 0) as gross_revenue,
                    COALESCE(SUM(fee_cents) FILTER (WHERE status = 'completed'), 0) as total_fees,
                    COALESCE(SUM(net_amount_cents) FILTER (WHERE status = 'completed'), 0) as net_revenue,
                    COALESCE(SUM(amount_cents) FILTER (WHERE status = 'refunded'), 0) as refunds,
                    COUNT(*) FILTER (WHERE type = 'drop_in' AND status = 'completed') as drop_in_count,
                    COUNT(*) FILTER (WHERE type = 'membership' AND status = 'completed') as membership_count
                FROM transactions
                WHERE created_at >= (now() AT TIME ZONE %s - INTERVAL '1 day')::date
                  AND created_at < (now() AT TIME ZONE %s)::date
                  AND status IN ('completed', 'refunded')
                """,
                (tz, tz),
            )

        summary = dict(row) if row else {
            "txn_count": 0, "gross_revenue": 0, "total_fees": 0,
            "net_revenue": 0, "refunds": 0, "drop_in_count": 0,
            "membership_count": 0,
        }
        summary["tenant"] = tenant

        # Store in payout_summaries table
        if summary["txn_count"] > 0:
            with get_tenant_conn(schema) as conn:
                execute(
                    conn,
                    """
                    INSERT INTO payout_summaries
                        (report_date, period, gross_revenue_cents, fee_cents,
                         net_revenue_cents, refund_cents, transaction_count,
                         drop_in_count, membership_count)
                    VALUES (
                        (now() AT TIME ZONE %s - INTERVAL '1 day')::date,
                        'daily', %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (report_date, period) DO UPDATE SET
                        gross_revenue_cents = EXCLUDED.gross_revenue_cents,
                        fee_cents = EXCLUDED.fee_cents,
                        net_revenue_cents = EXCLUDED.net_revenue_cents,
                        refund_cents = EXCLUDED.refund_cents,
                        transaction_count = EXCLUDED.transaction_count,
                        drop_in_count = EXCLUDED.drop_in_count,
                        membership_count = EXCLUDED.membership_count
                    """,
                    (
                        tz,
                        summary["gross_revenue"],
                        summary["total_fees"],
                        summary["net_revenue"],
                        summary["refunds"],
                        summary["txn_count"],
                        summary["drop_in_count"],
                        summary["membership_count"],
                    ),
                )

        return summary

    @task()
    def send_summary_emails(summaries: list[dict]):
        for s in summaries:
            if s["txn_count"] == 0:
                continue

            tenant = s["tenant"]
            owner_email = get_owner_email(tenant["id"])
            if not owner_email:
                continue

            tz = tenant.get("timezone") or "UTC"
            # Use yesterday's date for the report
            report_date = (datetime.utcnow() - timedelta(days=1)).strftime("%B %d, %Y")

            html = _build_daily_email(tenant["name"], report_date, s)
            send_payout_email(
                to_email=owner_email,
                subject=f"Daily Payout Summary — {report_date}",
                html_content=html,
            )

    tenants = get_tenants()
    summaries = compute_daily_summary.expand(tenant=tenants)
    send_summary_emails(summaries)


daily_payout_summary()
