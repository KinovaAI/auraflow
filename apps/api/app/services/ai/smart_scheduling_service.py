"""AuraFlow — Smart Scheduling Service

AI-powered schedule analysis using Claude. Analyzes 90-day attendance data
to identify underperforming slots, high-demand gaps, and optimal
instructor-class pairings.
"""
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ai.token_tracking_service import track_ai_usage


class SmartSchedulingService:

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
                service_name="smart_scheduling_service",
                function_name="analyze_schedule",
                model=settings.ANTHROPIC_MODEL,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            )
            return message.content[0].text
        except Exception as e:
            logger.error("Claude API call failed in SmartSchedulingService", error=str(e))
            return f"[AI error: {str(e)}]"

    async def analyze_schedule(self) -> dict:
        """Analyze 90-day attendance data and suggest optimal class times
        and instructor pairings.

        Returns a dict with raw data summaries and Claude-generated
        recommendations for schedule optimization.
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=90)

        async with get_tenant_db() as db:
            # 1. Class sessions with attendance counts for last 90 days
            session_data = await db.fetch(
                """
                SELECT
                    ct.name AS class_type,
                    cs.starts_at,
                    EXTRACT(DOW FROM cs.starts_at)::int AS day_of_week,
                    EXTRACT(HOUR FROM cs.starts_at)::int AS hour,
                    cs.capacity,
                    COUNT(b.id) AS booked_count,
                    COUNT(CASE WHEN b.status = 'attended' THEN 1 END) AS attended,
                    COUNT(CASE WHEN b.status = 'no_show' THEN 1 END) AS no_shows,
                    COUNT(CASE WHEN b.status IN ('cancelled', 'late_cancel') THEN 1 END) AS cancellations
                FROM class_sessions cs
                JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN bookings b ON b.class_session_id = cs.id
                WHERE cs.starts_at >= $1 AND cs.starts_at < $2
                  AND cs.status != 'cancelled'
                GROUP BY ct.name, cs.starts_at, cs.capacity
                ORDER BY cs.starts_at
                """,
                start, end,
            )

            # 2. Average attendance by day_of_week and hour
            heatmap = await db.fetch(
                """
                SELECT
                    EXTRACT(DOW FROM cs.starts_at)::int AS day_of_week,
                    EXTRACT(HOUR FROM cs.starts_at)::int AS hour,
                    COUNT(DISTINCT cs.id) AS session_count,
                    ROUND(COUNT(b.id)::numeric / NULLIF(COUNT(DISTINCT cs.id), 0), 1) AS avg_booked,
                    COALESCE(AVG(cs.capacity), 0) AS avg_capacity,
                    COUNT(CASE WHEN b.status = 'attended' THEN 1 END) AS total_attended,
                    ROUND(
                        COUNT(CASE WHEN b.status = 'attended' THEN 1 END)::numeric
                        / NULLIF(COUNT(DISTINCT cs.id), 0), 1
                    ) AS avg_attendance_per_session
                FROM class_sessions cs
                LEFT JOIN bookings b ON b.class_session_id = cs.id
                WHERE cs.starts_at >= $1 AND cs.starts_at < $2
                  AND cs.status != 'cancelled'
                GROUP BY day_of_week, hour
                ORDER BY day_of_week, hour
                """,
                start, end,
            )

            # 3. Instructor-class_type pairings with attendance rates
            instructor_pairings = await db.fetch(
                """
                SELECT
                    i.display_name AS instructor,
                    ct.name AS class_type,
                    COUNT(DISTINCT cs.id) AS sessions_taught,
                    ROUND(COUNT(b.id)::numeric / NULLIF(COUNT(DISTINCT cs.id), 0), 1) AS avg_booked,
                    COALESCE(AVG(cs.capacity), 0) AS avg_capacity,
                    COUNT(CASE WHEN b.status = 'attended' THEN 1 END) AS total_attended,
                    ROUND(
                        COUNT(CASE WHEN b.status = 'attended' THEN 1 END)::numeric
                        / NULLIF(COUNT(DISTINCT cs.id), 0), 1
                    ) AS avg_attendance_per_session,
                    ROUND(
                        COUNT(CASE WHEN b.status = 'attended' THEN 1 END)::numeric * 100
                        / NULLIF(SUM(cs.capacity), 0), 1
                    ) AS fill_rate_percent
                FROM class_sessions cs
                JOIN class_types ct ON ct.id = cs.class_type_id
                JOIN instructors i ON i.id = cs.instructor_id
                LEFT JOIN bookings b ON b.class_session_id = cs.id
                WHERE cs.starts_at >= $1 AND cs.starts_at < $2
                  AND cs.status != 'cancelled'
                GROUP BY i.display_name, ct.name
                HAVING COUNT(DISTINCT cs.id) >= 2
                ORDER BY avg_attendance_per_session DESC
                """,
                start, end,
            )

        # Format data for Claude
        day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

        heatmap_lines = []
        for r in heatmap:
            day = day_names[r["day_of_week"]]
            hour = f"{r['hour']:02d}:00"
            avg_att = float(r["avg_attendance_per_session"] or 0)
            avg_cap = float(r["avg_capacity"] or 0)
            fill = round(avg_att / avg_cap * 100, 1) if avg_cap > 0 else 0
            heatmap_lines.append(
                f"  {day} {hour}: {r['session_count']} sessions, "
                f"avg {avg_att:.1f} attendees / {avg_cap:.0f} capacity ({fill}% fill)"
            )

        pairing_lines = []
        for r in instructor_pairings:
            avg_att = float(r["avg_attendance_per_session"] or 0)
            fill = float(r["fill_rate_percent"] or 0)
            pairing_lines.append(
                f"  {r['instructor']} + {r['class_type']}: "
                f"{r['sessions_taught']} sessions, avg {avg_att:.1f} attendees, "
                f"{fill:.0f}% fill rate"
            )

        total_sessions = len(session_data)
        overall_attended = sum(r["attended"] for r in session_data)
        overall_capacity = sum(r["capacity"] for r in session_data) or 1
        overall_fill = round(overall_attended / overall_capacity * 100, 1)

        system = (
            "You are an expert studio operations consultant specializing in "
            "yoga and fitness studio scheduling optimization. Analyze the "
            "attendance data and provide actionable recommendations. "
            "Be specific with day/time references. Use plain text, no markdown."
        )

        # Build text blocks for the prompt
        heatmap_text = "\n".join(heatmap_lines) if heatmap_lines else "  No data"
        pairing_text = "\n".join(pairing_lines) if pairing_lines else "  No data"

        prompt = (
            f"Analyze this 90-day schedule data for a yoga/fitness studio.\n\n"
            f"OVERVIEW:\n"
            f"  Total sessions: {total_sessions}\n"
            f"  Overall fill rate: {overall_fill}%\n"
            f"  Total attendees: {overall_attended}\n\n"
            f"ATTENDANCE BY DAY & TIME:\n{heatmap_text}\n\n"
            f"INSTRUCTOR-CLASS PAIRINGS:\n{pairing_text}\n\n"
            f"Please provide:\n"
            f"1. UNDERPERFORMING SLOTS: Time slots with low fill rates that "
            f"should be considered for removal or restructuring.\n"
            f"2. HIGH-DEMAND OPPORTUNITIES: Times that could support additional "
            f"classes based on consistent high demand.\n"
            f"3. BEST INSTRUCTOR-CLASS PAIRINGS: Which instructor-class combos "
            f"are strongest and which could be improved.\n"
            f"4. SCHEDULE OPTIMIZATION: Concrete suggestions for improving the "
            f"overall schedule to maximize attendance and revenue.\n"
            f"5. QUICK WINS: 2-3 changes that could be implemented immediately "
            f"for the biggest impact."
        )

        analysis = await self._call_claude(prompt, system)

        logger.info(
            "Schedule analysis completed",
            total_sessions=total_sessions,
            overall_fill_rate=overall_fill,
        )

        return {
            "analysis": analysis,
            "summary": {
                "period_days": 90,
                "total_sessions": total_sessions,
                "overall_fill_rate_percent": overall_fill,
                "total_attended": overall_attended,
                "total_capacity": overall_capacity,
            },
            "heatmap": [
                {
                    "day_of_week": int(r["day_of_week"]),
                    "day_name": day_names[r["day_of_week"]],
                    "hour": int(r["hour"]),
                    "session_count": r["session_count"],
                    "avg_booked": float(r["avg_booked"]),
                    "avg_capacity": float(r["avg_capacity"]),
                    "avg_attendance": float(r["avg_attendance_per_session"] or 0),
                }
                for r in heatmap
            ],
            "instructor_pairings": [
                {
                    "instructor": r["instructor"],
                    "class_type": r["class_type"],
                    "sessions_taught": r["sessions_taught"],
                    "avg_booked": float(r["avg_booked"]),
                    "avg_capacity": float(r["avg_capacity"]),
                    "avg_attendance": float(r["avg_attendance_per_session"] or 0),
                    "fill_rate_percent": float(r["fill_rate_percent"] or 0),
                }
                for r in instructor_pairings
            ],
        }
