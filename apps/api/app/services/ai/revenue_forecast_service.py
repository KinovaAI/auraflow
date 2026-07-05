"""AuraFlow — Revenue Forecast Service

AI-powered revenue projections using historical transaction data, membership
renewals, acquisition/churn rates, and Claude-generated natural language
summaries with confidence levels.
"""
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ai.token_tracking_service import track_ai_usage


class RevenueForecastService:

    def _is_configured(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    async def _call_claude(self, prompt: str, system: str = "") -> str:
        """Call Claude API. Returns the response text."""
        if not self._is_configured():
            return "[AI not configured -- set ANTHROPIC_API_KEY]"

        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        try:
            message = await client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            await track_ai_usage(
                service_name="revenue_forecast_service",
                function_name="forecast",
                model=settings.ANTHROPIC_MODEL,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            )
            return message.content[0].text
        except Exception as e:
            logger.error("Claude API call failed in RevenueForecastService", error=str(e))
            return f"[AI error: {str(e)}]"

    async def forecast(self, days: int = 90) -> dict:
        """Generate 30/60/90-day revenue projections with Claude summary.

        Queries historical revenue, active memberships, acquisition rates,
        and churn to build projections, then sends the data to Claude for
        a human-readable summary with strategic insights.

        Returns:
            dict with projections, summary, and chart_data.
        """
        now = datetime.now(timezone.utc)
        lookback_start = now - timedelta(days=180)

        async with get_tenant_db() as db:
            # 1. Daily revenue for past 180 days
            daily_revenue = await db.fetch(
                """
                SELECT
                    date_trunc('day', created_at) AS day,
                    COALESCE(SUM(amount_cents), 0) AS revenue_cents,
                    COUNT(*) AS txn_count
                FROM transactions
                WHERE status IN ('completed', 'partially_refunded')
                  AND created_at >= $1 AND created_at < $2
                GROUP BY day
                ORDER BY day
                """,
                lookback_start, now,
            )

            # 2. Active memberships with renewal dates and amounts
            now_plus_30 = now + timedelta(days=30)
            now_plus_60 = now + timedelta(days=60)
            now_plus_90 = now + timedelta(days=90)
            memberships = await db.fetchrow(
                """
                SELECT
                    COUNT(*) AS active_count,
                    COALESCE(SUM(mt.price_cents), 0) AS monthly_recurring_cents,
                    COUNT(*) FILTER (
                        WHERE mm.ends_at IS NOT NULL
                          AND mm.ends_at <= $1
                    ) AS renewals_next_30d,
                    COUNT(*) FILTER (
                        WHERE mm.ends_at IS NOT NULL
                          AND mm.ends_at <= $2
                    ) AS renewals_next_60d,
                    COUNT(*) FILTER (
                        WHERE mm.ends_at IS NOT NULL
                          AND mm.ends_at <= $3
                    ) AS renewals_next_90d
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE mm.status = 'active'
                """,
                now_plus_30, now_plus_60, now_plus_90,
            )

            # 3. New member acquisition rate (30d, 60d, 90d windows)
            now_minus_30 = now - timedelta(days=30)
            now_minus_60 = now - timedelta(days=60)
            now_minus_90 = now - timedelta(days=90)
            acquisition = await db.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE joined_at >= $2) AS new_30d,
                    COUNT(*) FILTER (WHERE joined_at >= $3) AS new_60d,
                    COUNT(*) FILTER (WHERE joined_at >= $4) AS new_90d
                FROM members
                WHERE joined_at >= $4
                  AND joined_at < $1
                """,
                now, now_minus_30, now_minus_60, now_minus_90,
            )

            # 4. Churn rate (memberships cancelled in last 30/60/90 days)
            churn = await db.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE cancelled_at >= $1) AS churned_30d,
                    COUNT(*) FILTER (WHERE cancelled_at >= $2) AS churned_60d,
                    COUNT(*) FILTER (WHERE cancelled_at >= $3) AS churned_90d,
                    COUNT(*) FILTER (WHERE status = 'active') AS currently_active
                FROM member_memberships
                """,
                now_minus_30, now_minus_60, now_minus_90,
            )

        # Calculate trend-based projections
        # Split 180-day history into two 90-day halves for trend detection
        mid = lookback_start + timedelta(days=90)
        first_half_rev = sum(
            r["revenue_cents"] for r in daily_revenue
            if r["day"] < mid
        )
        second_half_rev = sum(
            r["revenue_cents"] for r in daily_revenue
            if r["day"] >= mid
        )

        # Average daily revenue from recent 90 days
        recent_days = [r for r in daily_revenue if r["day"] >= mid]
        recent_day_count = max(len(recent_days), 1)
        avg_daily_recent = second_half_rev / recent_day_count

        # Growth trend multiplier
        if first_half_rev > 0:
            growth_rate = (second_half_rev - first_half_rev) / first_half_rev
        else:
            growth_rate = 0.0

        # Recurring membership revenue (monthly)
        monthly_recurring = memberships["monthly_recurring_cents"] if memberships else 0
        daily_recurring = monthly_recurring / 30

        # Churn impact: estimate percentage of memberships that will churn
        active_count = churn["currently_active"] if churn else 0
        churned_30d = churn["churned_30d"] if churn else 0
        churn_rate_30d = (churned_30d / active_count) if active_count > 0 else 0

        # Build projections for 30, 60, 90 day periods
        projections = []
        for period_days in [30, 60, 90]:
            if period_days > days:
                continue

            # Base: recent daily average extrapolated
            base_projection = int(avg_daily_recent * period_days)

            # Recurring membership revenue (adjusted for churn)
            periods = period_days / 30
            churn_factor = max(0, 1 - (churn_rate_30d * periods * 0.5))
            recurring_projection = int(daily_recurring * period_days * churn_factor)

            # Growth adjustment
            growth_adjustment = 1 + (growth_rate * period_days / 180)
            adjusted_total = int(
                (base_projection * 0.4 + recurring_projection * 0.6)
                * growth_adjustment
            )

            # Confidence decreases with longer forecasts
            confidence_map = {30: "high", 60: "medium", 90: "low"}
            confidence_pct = {30: 85, 60: 70, 90: 55}

            projections.append({
                "period_days": period_days,
                "amount_cents": adjusted_total,
                "confidence": confidence_map.get(period_days, "low"),
                "confidence_percent": confidence_pct.get(period_days, 50),
                "breakdown": {
                    "base_trend_cents": base_projection,
                    "recurring_cents": recurring_projection,
                    "growth_adjustment": round(growth_adjustment, 3),
                    "churn_factor": round(churn_factor, 3),
                },
            })

        # Build chart data: daily revenue for sparkline + forecast line
        chart_data = []
        for r in daily_revenue:
            chart_data.append({
                "date": r["day"].isoformat() if r["day"] else None,
                "revenue_cents": r["revenue_cents"],
                "type": "actual",
            })

        # Add forecast points (weekly)
        forecast_weeks = min(days, 90) // 7
        for w in range(1, forecast_weeks + 1):
            forecast_date = now + timedelta(weeks=w)
            weekly_rev = int(avg_daily_recent * 7 * (1 + growth_rate * w / 26))
            chart_data.append({
                "date": forecast_date.isoformat(),
                "revenue_cents": weekly_rev,
                "type": "forecast",
            })

        # Format data for Claude summary
        new_30d = acquisition["new_30d"] if acquisition else 0
        new_60d = acquisition["new_60d"] if acquisition else 0
        new_90d = acquisition["new_90d"] if acquisition else 0

        total_180d_rev = first_half_rev + second_half_rev
        total_days_with_data = len(daily_revenue) or 1

        system = (
            "You are a financial analyst for a yoga/fitness studio. "
            "Provide a clear, concise revenue forecast summary. "
            "Be specific with numbers and actionable with advice. "
            "Use plain text, no markdown formatting. "
            "Keep the summary under 250 words."
        )

        prompt = (
            f"Summarize this revenue forecast for a studio owner.\n\n"
            f"HISTORICAL (180 days):\n"
            f"  Total revenue: ${total_180d_rev / 100:,.2f}\n"
            f"  Avg daily: ${avg_daily_recent / 100:,.2f}\n"
            f"  First 90 days: ${first_half_rev / 100:,.2f}\n"
            f"  Recent 90 days: ${second_half_rev / 100:,.2f}\n"
            f"  Growth trend: {growth_rate * 100:+.1f}%\n"
            f"  Days with transactions: {total_days_with_data}\n\n"
            f"MEMBERSHIPS:\n"
            f"  Active: {active_count}\n"
            f"  Monthly recurring: ${monthly_recurring / 100:,.2f}\n"
            f"  Renewals next 30d: {memberships['renewals_next_30d'] if memberships else 0}\n"
            f"  Renewals next 60d: {memberships['renewals_next_60d'] if memberships else 0}\n\n"
            f"ACQUISITION & CHURN:\n"
            f"  New members (30d): {new_30d}\n"
            f"  New members (60d): {new_60d}\n"
            f"  New members (90d): {new_90d}\n"
            f"  Churned (30d): {churned_30d}\n"
            f"  30-day churn rate: {churn_rate_30d * 100:.1f}%\n\n"
            f"PROJECTIONS:\n"
        )

        for p in projections:
            prompt += (
                f"  {p['period_days']}-day: ${p['amount_cents'] / 100:,.2f} "
                f"({p['confidence']} confidence)\n"
            )

        prompt += (
            f"\nProvide a concise summary including:\n"
            f"1. Revenue health assessment\n"
            f"2. Key risks (churn, seasonal patterns)\n"
            f"3. Top 2-3 actions to improve revenue\n"
            f"4. Whether the growth trend is sustainable"
        )

        summary = await self._call_claude(prompt, system)

        logger.info(
            "Revenue forecast generated",
            forecast_days=days,
            projections_count=len(projections),
            avg_daily_cents=int(avg_daily_recent),
        )

        return {
            "projections": projections,
            "summary": summary,
            "chart_data": chart_data,
            "metrics": {
                "avg_daily_revenue_cents": int(avg_daily_recent),
                "monthly_recurring_cents": monthly_recurring,
                "active_memberships": active_count,
                "growth_rate_percent": round(growth_rate * 100, 1),
                "churn_rate_30d_percent": round(churn_rate_30d * 100, 1),
                "new_members_30d": new_30d,
                "total_180d_revenue_cents": total_180d_rev,
            },
        }
