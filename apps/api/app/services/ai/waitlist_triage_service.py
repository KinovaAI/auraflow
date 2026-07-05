"""AuraFlow — Waitlist Triage Service

AI-powered waitlist prioritization using deterministic scoring based on
membership value, visit history, lifetime revenue, tenure, and attendance
consistency.  No LLM call required — uses a weighted formula for instant,
cost-free scoring.
"""
import uuid
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db


class WaitlistTriageService:

    # ── Scoring weights (must sum to 1.0) ──────────────────────────────
    WEIGHT_MEMBERSHIP = 0.30
    WEIGHT_VISITS = 0.20
    WEIGHT_REVENUE = 0.20
    WEIGHT_TENURE = 0.15
    WEIGHT_CONSISTENCY = 0.10
    WEIGHT_CANCEL_PENALTY = 0.05  # subtracted

    def _compute_priority_score(self, data: dict) -> tuple[float, dict]:
        """Compute a 0-100 priority score from member metrics.

        Returns (score, breakdown_dict).
        """
        # Membership tier value (price relative to max in system)
        max_price = max(data.get("max_membership_price", 1), 1)
        membership_raw = min(data.get("membership_price_cents", 0) / max_price, 1.0)

        # Visit count (cap at 200)
        visits_raw = min(data.get("total_visits", 0) / 200, 1.0)

        # Lifetime revenue (cap at $500 = 50000 cents)
        revenue_raw = min(data.get("lifetime_revenue_cents", 0) / 50000, 1.0)

        # Tenure in months (cap at 24)
        joined = data.get("joined_at")
        if joined:
            months = (datetime.now(timezone.utc) - joined).days / 30.44
            tenure_raw = min(months / 24, 1.0)
        else:
            tenure_raw = 0.0

        # Attendance consistency: attended / total recent bookings
        attended = data.get("recent_attended", 0)
        issues = data.get("recent_issues", 0)
        total = attended + issues
        consistency_raw = (attended / total) if total > 0 else 0.5

        # Recent cancellations penalty
        cancel_penalty = min(data.get("recent_issues", 0) * 0.05, 0.25)

        score = (
            self.WEIGHT_MEMBERSHIP * membership_raw
            + self.WEIGHT_VISITS * visits_raw
            + self.WEIGHT_REVENUE * revenue_raw
            + self.WEIGHT_TENURE * tenure_raw
            + self.WEIGHT_CONSISTENCY * consistency_raw
            - self.WEIGHT_CANCEL_PENALTY * cancel_penalty
        ) * 100

        score = max(0, min(100, round(score, 1)))

        factors = {
            "membership_value": round(membership_raw * 100, 1),
            "total_visits": round(visits_raw * 100, 1),
            "lifetime_revenue": round(revenue_raw * 100, 1),
            "tenure": round(tenure_raw * 100, 1),
            "attendance_consistency": round(consistency_raw * 100, 1),
            "cancellation_penalty": round(cancel_penalty * 100, 1),
        }
        return score, factors

    async def get_session_waitlist_with_scores(
        self, session_id: str, schema_override: str | None = None,
    ) -> list[dict]:
        """Get all waitlisted bookings for a session with priority scores."""
        db_kwargs = {"schema_override": schema_override} if schema_override else {}
        async with get_tenant_db(**db_kwargs) as db:
            # Get max membership price for normalization
            max_row = await db.fetchrow(
                "SELECT COALESCE(MAX(price_cents), 1) AS max_price FROM membership_types"
            )
            max_price = max_row["max_price"] if max_row else 1

            rows = await db.fetch(
                """
                SELECT
                    b.id AS booking_id, b.waitlist_position, b.booked_at,
                    m.id AS member_id, m.first_name, m.last_name, m.email,
                    m.total_visits, m.lifetime_revenue_cents, m.joined_at,
                    COALESCE(mt.price_cents, 0) AS membership_price_cents,
                    COALESCE(mt.name, 'None') AS membership_name,
                    (SELECT COUNT(*) FROM bookings b2
                     WHERE b2.member_id = m.id AND b2.status = 'attended'
                     AND b2.checked_in_at >= NOW() - INTERVAL '90 days'
                    ) AS recent_attended,
                    (SELECT COUNT(*) FROM bookings b3
                     WHERE b3.member_id = m.id
                     AND b3.status IN ('cancelled', 'no_show')
                     AND b3.booked_at >= NOW() - INTERVAL '90 days'
                    ) AS recent_issues
                FROM bookings b
                JOIN members m ON m.id = b.member_id
                LEFT JOIN member_memberships mm
                    ON mm.member_id = m.id AND mm.status = 'active'
                LEFT JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE b.class_session_id = $1 AND b.status = 'waitlisted'
                ORDER BY b.waitlist_position ASC NULLS LAST, b.booked_at ASC
                """,
                session_id,
            )

            results = []
            for row in rows:
                data = dict(row)
                data["max_membership_price"] = max_price
                score, factors = self._compute_priority_score(data)
                results.append({
                    "booking_id": str(data["booking_id"]),
                    "member_id": str(data["member_id"]),
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "email": data["email"],
                    "waitlist_position": data["waitlist_position"],
                    "booked_at": data["booked_at"].isoformat() if data.get("booked_at") else None,
                    "total_visits": data["total_visits"] or 0,
                    "lifetime_revenue_cents": data["lifetime_revenue_cents"] or 0,
                    "membership_name": data["membership_name"],
                    "priority_score": score,
                    "factors": factors,
                })

            # Sort by priority score descending
            results.sort(key=lambda x: x["priority_score"], reverse=True)
            return results

    async def rerank_waitlist(
        self, session_id: str, schema_override: str | None = None,
    ) -> list[dict]:
        """Re-order waitlist_position values by AI priority score."""
        scored = await self.get_session_waitlist_with_scores(
            session_id, schema_override=schema_override,
        )
        if not scored:
            return []

        db_kwargs = {"schema_override": schema_override} if schema_override else {}
        async with get_tenant_db(**db_kwargs) as db:
            for rank, entry in enumerate(scored, start=1):
                await db.execute(
                    "UPDATE bookings SET waitlist_position = $1 WHERE id = $2",
                    rank, entry["booking_id"],
                )
                entry["waitlist_position"] = rank

        logger.info(
            "Waitlist re-ranked by AI score",
            session_id=session_id,
            count=len(scored),
        )
        return scored

    async def promote_by_priority(self, db, session_id: str) -> dict | None:
        """Promote the highest-priority waitlisted member.

        Called by BookingService._promote_waitlist() when studio uses
        waitlist_mode='ai_priority'.  The db connection is passed in
        so it can be used within the caller's transaction context.
        """
        # Get max membership price
        max_row = await db.fetchrow(
            "SELECT COALESCE(MAX(price_cents), 1) AS max_price FROM membership_types"
        )
        max_price = max_row["max_price"] if max_row else 1

        rows = await db.fetch(
            """
            SELECT
                b.id AS booking_id,
                m.total_visits, m.lifetime_revenue_cents, m.joined_at,
                COALESCE(mt.price_cents, 0) AS membership_price_cents,
                (SELECT COUNT(*) FROM bookings b2
                 WHERE b2.member_id = m.id AND b2.status = 'attended'
                 AND b2.checked_in_at >= NOW() - INTERVAL '90 days'
                ) AS recent_attended,
                (SELECT COUNT(*) FROM bookings b3
                 WHERE b3.member_id = m.id
                 AND b3.status IN ('cancelled', 'no_show')
                 AND b3.booked_at >= NOW() - INTERVAL '90 days'
                ) AS recent_issues
            FROM bookings b
            JOIN members m ON m.id = b.member_id
            LEFT JOIN member_memberships mm
                ON mm.member_id = m.id AND mm.status = 'active'
            LEFT JOIN membership_types mt ON mt.id = mm.membership_type_id
            WHERE b.class_session_id = $1 AND b.status = 'waitlisted'
            """,
            session_id,
        )

        if not rows:
            return None

        # Score each and find highest
        best_id = None
        best_score = -1
        for row in rows:
            data = dict(row)
            data["max_membership_price"] = max_price
            score, _ = self._compute_priority_score(data)
            if score > best_score:
                best_score = score
                best_id = str(data["booking_id"])

        if not best_id:
            return None

        promoted = await db.fetchrow(
            """
            UPDATE bookings
            SET status = 'confirmed', waitlist_position = NULL
            WHERE id = $1
            RETURNING *
            """,
            best_id,
        )
        if promoted:
            logger.info(
                "Waitlist AI-promoted",
                booking_id=best_id,
                session_id=session_id,
                score=best_score,
            )
        return dict(promoted) if promoted else None

    async def get_waitlist_mode(self, session_id: str) -> str:
        """Get the waitlist mode for the studio owning a session."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT COALESCE(s.waitlist_mode, 'fifo') AS waitlist_mode
                FROM studios s
                JOIN class_sessions cs ON cs.studio_id = s.id
                WHERE cs.id = $1
                """,
                session_id,
            )
            return row["waitlist_mode"] if row else "fifo"

    async def set_waitlist_mode(self, studio_id: str, mode: str) -> dict:
        """Toggle waitlist mode for a studio."""
        if mode not in ("fifo", "ai_priority"):
            raise ValueError("mode must be 'fifo' or 'ai_priority'")

        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE studios SET waitlist_mode = $1, updated_at = NOW()
                WHERE id = $2
                RETURNING id, name, waitlist_mode
                """,
                mode, studio_id,
            )
            if not row:
                raise ValueError("Studio not found")
            logger.info("Waitlist mode changed", studio_id=studio_id, mode=mode)
            return {"studio_id": str(row["id"]), "name": row["name"], "mode": row["waitlist_mode"]}

    async def get_sessions_with_waitlist(self) -> list[dict]:
        """Get upcoming sessions that have waitlisted bookings."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT cs.id, cs.title, cs.starts_at, cs.capacity,
                    cs.waitlist_capacity,
                    (SELECT COUNT(*) FROM bookings b
                     WHERE b.class_session_id = cs.id AND b.status = 'confirmed'
                    ) AS booked_count,
                    (SELECT COUNT(*) FROM bookings b
                     WHERE b.class_session_id = cs.id AND b.status = 'waitlisted'
                    ) AS waitlist_count
                FROM class_sessions cs
                WHERE cs.starts_at > NOW()
                AND cs.status = 'scheduled'
                AND EXISTS (
                    SELECT 1 FROM bookings b
                    WHERE b.class_session_id = cs.id AND b.status = 'waitlisted'
                )
                ORDER BY cs.starts_at ASC
                LIMIT 50
                """
            )
            return [
                {
                    "id": str(r["id"]),
                    "title": r["title"],
                    "starts_at": r["starts_at"].isoformat() if r["starts_at"] else None,
                    "capacity": r["capacity"],
                    "waitlist_capacity": r["waitlist_capacity"],
                    "booked_count": r["booked_count"],
                    "waitlist_count": r["waitlist_count"],
                }
                for r in rows
            ]
