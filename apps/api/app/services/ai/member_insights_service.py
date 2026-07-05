"""AuraFlow — Member Insights Service

AI-powered member profile summaries using Claude. Aggregates booking history,
membership details, payment data, milestones, and churn risk into a
natural language insight with actionable recommendations.
"""
from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ai.token_tracking_service import track_ai_usage


class MemberInsightsService:

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
                model=settings.ANTHROPIC_MODEL_FAST,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            await track_ai_usage(
                service_name="member_insights_service",
                function_name="get_insight",
                model=settings.ANTHROPIC_MODEL_FAST,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            )
            return message.content[0].text
        except Exception as e:
            logger.error("Claude API call failed in MemberInsightsService", error=str(e))
            return f"[AI error: {str(e)}]"

    async def get_insight(self, member_id: str) -> dict:
        """Generate an AI-powered member profile summary.

        Queries member info, booking history, membership status, payment
        history, milestones, and churn risk, then sends everything to Claude
        for a natural language insight with highlights and recommendations.

        Returns:
            dict with summary, highlights, and recommendations.
        """
        async with get_tenant_db() as db:
            # 1. Member basic info
            member = await db.fetchrow(
                """
                SELECT id, first_name, last_name, email, phone_enc,
                       joined_at, is_active, total_visits, last_visit_at,
                       lifetime_revenue_cents, churn_risk_flagged_at
                FROM members
                WHERE id = $1
                """,
                member_id,
            )

            if not member:
                return None

            # 2. Booking history: count, favorite classes, attendance rate
            booking_stats = await db.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_bookings,
                    COUNT(*) FILTER (WHERE b.status = 'attended') AS attended,
                    COUNT(*) FILTER (WHERE b.status = 'no_show') AS no_shows,
                    COUNT(*) FILTER (WHERE b.status IN ('cancelled', 'late_cancel')) AS cancellations,
                    MIN(cs.starts_at) AS first_booking,
                    MAX(cs.starts_at) AS last_booking
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                WHERE b.member_id = $1
                """,
                member_id,
            )

            # Favorite class types
            favorite_classes = await db.fetch(
                """
                SELECT ct.name AS class_type, COUNT(*) AS count
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                JOIN class_types ct ON ct.id = cs.class_type_id
                WHERE b.member_id = $1 AND b.status = 'attended'
                GROUP BY ct.name
                ORDER BY count DESC
                LIMIT 5
                """,
                member_id,
            )

            # 3. Membership info
            membership = await db.fetchrow(
                """
                SELECT mm.status, mm.starts_at, mm.ends_at, mm.cancelled_at,
                       mt.name AS plan_name, mt.type AS plan_type,
                       mt.price_cents
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE mm.member_id = $1
                ORDER BY mm.created_at DESC
                LIMIT 1
                """,
                member_id,
            )

            # 4. Payment history
            payment_stats = await db.fetchrow(
                """
                SELECT
                    COALESCE(SUM(amount_cents), 0) AS total_spent_cents,
                    COUNT(*) AS payment_count,
                    COALESCE(AVG(amount_cents), 0) AS avg_payment_cents,
                    MAX(created_at) AS last_payment_at
                FROM transactions
                WHERE member_id = $1
                  AND status IN ('completed', 'partially_refunded')
                """,
                member_id,
            )

            # 5. Milestones achieved
            milestones = await db.fetch(
                """
                SELECT milestone_type, achieved_at
                FROM member_milestones
                WHERE member_id = $1
                ORDER BY achieved_at DESC
                LIMIT 10
                """,
                member_id,
            )

        # Build profile data for Claude
        name = f"{member['first_name']} {member.get('last_name', '')}".strip()
        joined = member["joined_at"].strftime("%B %Y") if member["joined_at"] else "unknown"
        last_visit = (
            member["last_visit_at"].strftime("%B %d, %Y")
            if member["last_visit_at"]
            else "never"
        )
        total_visits = member["total_visits"] or 0
        lifetime_rev = member["lifetime_revenue_cents"] or 0
        is_churn_risk = member["churn_risk_flagged_at"] is not None

        total_bookings = booking_stats["total_bookings"] if booking_stats else 0
        attended = booking_stats["attended"] if booking_stats else 0
        no_shows = booking_stats["no_shows"] if booking_stats else 0
        cancellations = booking_stats["cancellations"] if booking_stats else 0
        attendance_rate = (
            round(attended / total_bookings * 100, 1)
            if total_bookings > 0
            else 0
        )

        fav_classes_text = ", ".join(
            f"{r['class_type']} ({r['count']}x)" for r in favorite_classes
        ) if favorite_classes else "none yet"

        membership_text = "No active membership"
        if membership:
            membership_text = (
                f"{membership['plan_name']} ({membership['status']}), "
                f"${membership['price_cents'] / 100:.2f}/period"
            )
            if membership["ends_at"]:
                membership_text += f", renews {membership['ends_at'].strftime('%B %d, %Y')}"

        total_spent = payment_stats["total_spent_cents"] if payment_stats else 0
        payment_count = payment_stats["payment_count"] if payment_stats else 0
        avg_payment = payment_stats["avg_payment_cents"] if payment_stats else 0

        # Calculate monthly spend average
        if member["joined_at"]:
            from datetime import datetime, timezone
            months_active = max(
                1,
                (datetime.now(timezone.utc) - member["joined_at"]).days / 30,
            )
            avg_monthly = int(total_spent / months_active)
        else:
            avg_monthly = 0

        milestones_text = ", ".join(
            r["milestone_type"] for r in milestones
        ) if milestones else "none"

        system = (
            "You are a member engagement specialist for a yoga/fitness studio. "
            "Provide a warm, insightful profile summary. Be specific and "
            "actionable. Use plain text, no markdown. Keep it concise."
        )

        prompt = (
            f"Create a member insight profile for the studio owner.\n\n"
            f"MEMBER: {name}\n"
            f"  Joined: {joined}\n"
            f"  Status: {'active' if member['is_active'] else 'inactive'}\n"
            f"  Last visit: {last_visit}\n"
            f"  Total visits: {total_visits}\n"
            f"  Churn risk flagged: {'YES' if is_churn_risk else 'no'}\n\n"
            f"BOOKINGS:\n"
            f"  Total bookings: {total_bookings}\n"
            f"  Attended: {attended} ({attendance_rate}% rate)\n"
            f"  No-shows: {no_shows}\n"
            f"  Cancellations: {cancellations}\n"
            f"  Favorite classes: {fav_classes_text}\n\n"
            f"MEMBERSHIP:\n"
            f"  {membership_text}\n\n"
            f"SPENDING:\n"
            f"  Lifetime: ${total_spent / 100:,.2f}\n"
            f"  Payments: {payment_count}\n"
            f"  Avg payment: ${avg_payment / 100:,.2f}\n"
            f"  Avg monthly: ${avg_monthly / 100:,.2f}\n\n"
            f"MILESTONES: {milestones_text}\n\n"
            f"Provide:\n"
            f"1. SUMMARY: A 2-3 sentence profile overview\n"
            f"2. HIGHLIGHTS: 3-4 notable things about this member\n"
            f"3. RECOMMENDATIONS: 2-3 specific engagement actions\n"
            f"\nFormat each section with a label followed by the content."
        )

        insight_text = await self._call_claude(prompt, system)

        # Parse sections from the response (best-effort)
        highlights = []
        recommendations = []
        summary_text = insight_text

        sections = insight_text.split("\n\n")
        for section in sections:
            lower = section.lower()
            if "highlight" in lower:
                highlights = [
                    line.strip().lstrip("- ").lstrip("* ")
                    for line in section.split("\n")[1:]
                    if line.strip() and not line.lower().startswith("highlight")
                ]
            elif "recommend" in lower or "action" in lower:
                recommendations = [
                    line.strip().lstrip("- ").lstrip("* ")
                    for line in section.split("\n")[1:]
                    if line.strip() and not line.lower().startswith("recommend")
                ]
            elif "summary" in lower:
                summary_lines = [
                    line.strip()
                    for line in section.split("\n")[1:]
                    if line.strip()
                ]
                if summary_lines:
                    summary_text = " ".join(summary_lines)

        logger.info(
            "Member insight generated",
            member_id=member_id,
            total_visits=total_visits,
        )

        return {
            "member_id": str(member["id"]),
            "member_name": name,
            "summary": summary_text,
            "highlights": highlights or [insight_text],
            "recommendations": recommendations,
            "raw_insight": insight_text,
            "data": {
                "joined": joined,
                "is_active": member["is_active"],
                "total_visits": total_visits,
                "last_visit": last_visit,
                "attendance_rate_percent": attendance_rate,
                "favorite_classes": [
                    {"class_type": r["class_type"], "count": r["count"]}
                    for r in favorite_classes
                ],
                "membership": membership_text,
                "lifetime_spent_cents": total_spent,
                "avg_monthly_cents": avg_monthly,
                "milestones_count": len(milestones),
                "is_churn_risk": is_churn_risk,
            },
        }
