"""AuraFlow — ML-Enhanced Retention Prediction Model

Replaces simple rule-based churn detection with a multi-factor weighted
scoring model using 12 features.  Uses a logistic sigmoid for probability
estimation -- no external ML libraries needed (numpy-free math).

Feature weights were calibrated against typical studio churn patterns:
declining visit frequency and days since last visit are the strongest
predictors, followed by cancellation/no-show behavior and payment failures.
"""
import math
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db


class RetentionModel:
    """ML-enhanced retention prediction using weighted feature scoring.

    Uses a logistic-style weighted model with 12 features for
    churn probability estimation. No external ML libraries needed --
    uses numpy-free math for fast, deterministic scoring.
    """

    # ── Feature weights (calibrated from typical studio data patterns) ──
    # Positive weights push toward higher churn probability.
    WEIGHTS = {
        "visit_frequency_trend": -1.8,       # declining visits = higher churn
        "days_since_last_visit": 2.2,        # more days = higher churn
        "booking_cancellation_rate": 1.4,    # high cancel rate = higher churn
        "no_show_rate": 1.6,                 # high no-show = higher churn
        "membership_value_tier": -0.9,       # premium membership = lower churn
        "tenure_months": -0.7,               # longer tenure = lower churn
        "payment_failure_count": 1.5,        # payment failures = higher churn
        "class_variety_score": -0.6,         # variety = lower churn
        "peak_hour_attendance": -0.5,        # peak hours = more engaged
        "social_engagement": -0.4,           # reviews/referrals = lower churn
        "consecutive_weeks_active": -1.2,    # activity streak = lower churn
        "revenue_trend": -1.0,               # declining spend = higher churn
    }
    BIAS = -0.5  # intercept -- slight lean toward "not churning" by default

    # ── Risk tier thresholds ──────────────────────────────────────────────
    _THRESHOLDS = (0.2, 0.4, 0.7)  # low | medium | high | critical

    # ── SQL: Single CTE-based feature extraction query ────────────────────
    _FEATURE_SQL = """
    WITH params AS (
        SELECT $1::uuid AS target_member_id
    ),

    -- Visit counts split into two 14-day windows for trend detection
    visit_windows AS (
        SELECT
            b.member_id,
            COUNT(*) FILTER (
                WHERE b.checked_in_at >= NOW() - INTERVAL '14 days'
            ) AS visits_last_14,
            COUNT(*) FILTER (
                WHERE b.checked_in_at >= NOW() - INTERVAL '28 days'
                  AND b.checked_in_at < NOW() - INTERVAL '14 days'
            ) AS visits_prior_14
        FROM bookings b
        WHERE b.status = 'attended'
          AND b.checked_in_at >= NOW() - INTERVAL '28 days'
          AND ($1::uuid IS NULL OR b.member_id = $1::uuid)
        GROUP BY b.member_id
    ),

    -- Booking outcomes in last 90 days
    booking_stats AS (
        SELECT
            b.member_id,
            COUNT(*) AS total_bookings_90d,
            COUNT(*) FILTER (WHERE b.status = 'cancelled') AS cancellations_90d,
            COUNT(*) FILTER (WHERE b.status = 'no_show') AS no_shows_90d,
            COUNT(*) FILTER (WHERE b.status = 'attended') AS attended_90d
        FROM bookings b
        WHERE b.booked_at >= NOW() - INTERVAL '90 days'
          AND ($1::uuid IS NULL OR b.member_id = $1::uuid)
        GROUP BY b.member_id
    ),

    -- Current active membership price relative to max available
    membership_info AS (
        SELECT
            mm.member_id,
            COALESCE(MAX(mt.price_cents), 0) AS current_price_cents
        FROM member_memberships mm
        JOIN membership_types mt ON mt.id = mm.membership_type_id
        WHERE mm.status = 'active'
          AND ($1::uuid IS NULL OR mm.member_id = $1::uuid)
        GROUP BY mm.member_id
    ),
    max_membership AS (
        SELECT COALESCE(MAX(price_cents), 1) AS max_price FROM membership_types
    ),

    -- Failed payments in last 90 days
    payment_failures AS (
        SELECT
            member_id,
            COUNT(*) AS fail_count
        FROM failed_payment_attempts
        WHERE created_at >= NOW() - INTERVAL '90 days'
          AND ($1::uuid IS NULL OR member_id = $1::uuid)
        GROUP BY member_id
    ),

    -- Class variety: distinct class_type_ids attended / total available
    class_variety AS (
        SELECT
            b.member_id,
            COUNT(DISTINCT cs.class_type_id) AS distinct_types_attended
        FROM bookings b
        JOIN class_sessions cs ON cs.id = b.class_session_id
        WHERE b.status = 'attended'
          AND b.checked_in_at >= NOW() - INTERVAL '90 days'
          AND ($1::uuid IS NULL OR b.member_id = $1::uuid)
        GROUP BY b.member_id
    ),
    total_class_types AS (
        SELECT COUNT(*) AS total_types FROM class_types WHERE is_active = TRUE
    ),

    -- Peak-hour attendance: fraction of visits during 17:00-20:00
    peak_hours AS (
        SELECT
            b.member_id,
            COUNT(*) AS total_attended,
            COUNT(*) FILTER (
                WHERE EXTRACT(HOUR FROM b.checked_in_at) BETWEEN 17 AND 19
            ) AS peak_attended
        FROM bookings b
        WHERE b.status = 'attended'
          AND b.checked_in_at >= NOW() - INTERVAL '90 days'
          AND ($1::uuid IS NULL OR b.member_id = $1::uuid)
        GROUP BY b.member_id
    ),

    -- Social engagement: reviews count (referrals tracked via referral_source on other members)
    social AS (
        SELECT
            r.member_id,
            COUNT(*) AS review_count
        FROM reviews r
        WHERE ($1::uuid IS NULL OR r.member_id = $1::uuid)
        GROUP BY r.member_id
    ),
    referral_counts AS (
        SELECT
            m2.id AS member_id,
            COUNT(m3.id) AS referral_count
        FROM members m2
        LEFT JOIN members m3 ON m3.referral_source = m2.email
        WHERE m2.is_active = TRUE
          AND ($1::uuid IS NULL OR m2.id = $1::uuid)
        GROUP BY m2.id
    ),

    -- Consecutive weeks with at least 1 visit (going back from current week)
    weekly_visits AS (
        SELECT
            b.member_id,
            DATE_TRUNC('week', b.checked_in_at) AS visit_week
        FROM bookings b
        WHERE b.status = 'attended'
          AND b.checked_in_at >= NOW() - INTERVAL '52 weeks'
          AND ($1::uuid IS NULL OR b.member_id = $1::uuid)
        GROUP BY b.member_id, DATE_TRUNC('week', b.checked_in_at)
    ),
    weeks_numbered AS (
        SELECT
            member_id,
            visit_week,
            ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY visit_week DESC) AS rn,
            EXTRACT(EPOCH FROM (
                DATE_TRUNC('week', NOW()) - visit_week
            )) / 604800 AS weeks_ago
        FROM weekly_visits
    ),
    streak AS (
        SELECT
            member_id,
            COUNT(*) AS consecutive_weeks
        FROM weeks_numbered
        WHERE weeks_ago = rn - 1  -- consecutive from current week
        GROUP BY member_id
    ),

    -- Revenue trend: spending last 30d vs prior 30d
    revenue_windows AS (
        SELECT
            t.member_id,
            COALESCE(SUM(t.amount_cents) FILTER (
                WHERE t.created_at >= NOW() - INTERVAL '30 days'
            ), 0) AS revenue_last_30,
            COALESCE(SUM(t.amount_cents) FILTER (
                WHERE t.created_at >= NOW() - INTERVAL '60 days'
                  AND t.created_at < NOW() - INTERVAL '30 days'
            ), 0) AS revenue_prior_30
        FROM transactions t
        WHERE t.status = 'completed'
          AND t.created_at >= NOW() - INTERVAL '60 days'
          AND ($1::uuid IS NULL OR t.member_id = $1::uuid)
        GROUP BY t.member_id
    )

    SELECT
        m.id AS member_id,
        m.first_name,
        m.last_name,
        m.email,
        m.joined_at,
        m.last_visit_at,
        m.total_visits,
        m.lifetime_revenue_cents,
        m.is_active,

        -- Raw feature data
        COALESCE(vw.visits_last_14, 0)          AS visits_last_14,
        COALESCE(vw.visits_prior_14, 0)         AS visits_prior_14,

        COALESCE(bs.total_bookings_90d, 0)      AS total_bookings_90d,
        COALESCE(bs.cancellations_90d, 0)       AS cancellations_90d,
        COALESCE(bs.no_shows_90d, 0)            AS no_shows_90d,
        COALESCE(bs.attended_90d, 0)            AS attended_90d,

        COALESCE(mi.current_price_cents, 0)     AS membership_price_cents,
        mm_max.max_price                        AS max_membership_price,

        COALESCE(pf.fail_count, 0)              AS payment_failures_90d,

        COALESCE(cv.distinct_types_attended, 0) AS distinct_types_attended,
        tct.total_types                         AS total_class_types,

        COALESCE(ph.total_attended, 0)          AS peak_total_attended,
        COALESCE(ph.peak_attended, 0)           AS peak_hour_attended,

        COALESCE(so.review_count, 0)            AS review_count,
        COALESCE(rc.referral_count, 0)          AS referral_count,

        COALESCE(st.consecutive_weeks, 0)       AS consecutive_weeks,

        COALESCE(rw.revenue_last_30, 0)         AS revenue_last_30,
        COALESCE(rw.revenue_prior_30, 0)        AS revenue_prior_30

    FROM members m
    CROSS JOIN max_membership mm_max
    CROSS JOIN total_class_types tct
    LEFT JOIN visit_windows vw       ON vw.member_id = m.id
    LEFT JOIN booking_stats bs       ON bs.member_id = m.id
    LEFT JOIN membership_info mi     ON mi.member_id = m.id
    LEFT JOIN payment_failures pf    ON pf.member_id = m.id
    LEFT JOIN class_variety cv       ON cv.member_id = m.id
    LEFT JOIN peak_hours ph          ON ph.member_id = m.id
    LEFT JOIN social so              ON so.member_id = m.id
    LEFT JOIN referral_counts rc     ON rc.member_id = m.id
    LEFT JOIN streak st              ON st.member_id = m.id
    LEFT JOIN revenue_windows rw     ON rw.member_id = m.id
    WHERE m.is_active = TRUE
      AND ($1::uuid IS NULL OR m.id = $1::uuid)
    ORDER BY m.last_name, m.first_name
    """

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    async def score_member(
        self, member_id: str, schema_override: str | None = None,
    ) -> dict:
        """Compute the full ML retention score for a single member.

        Returns dict with member info, churn_probability, risk_level,
        feature_vector, and top_factors.
        """
        async with get_tenant_db(
            **({"schema_override": schema_override} if schema_override else {})
        ) as db:
            row = await db.fetchrow(self._FEATURE_SQL, member_id)

        if not row:
            raise ValueError(f"Active member {member_id} not found")

        features = self.get_feature_vector_from_row(row)
        probability = self._compute_probability(features)
        risk_level = self._classify_risk(probability)
        top_factors = self._extract_top_factors(features)

        return {
            "member_id": str(row["member_id"]),
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "email": row["email"],
            "churn_probability": round(probability, 4),
            "risk_level": risk_level,
            "feature_vector": {k: round(v, 4) for k, v in features.items()},
            "top_factors": top_factors,
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }

    async def score_all_members(
        self, schema_override: str | None = None,
    ) -> list[dict]:
        """Score every active member. Pass member_id=None to get all."""
        async with get_tenant_db(
            **({"schema_override": schema_override} if schema_override else {})
        ) as db:
            rows = await db.fetch(self._FEATURE_SQL, None)

        results = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for row in rows:
            features = self.get_feature_vector_from_row(row)
            probability = self._compute_probability(features)
            risk_level = self._classify_risk(probability)
            top_factors = self._extract_top_factors(features)

            results.append({
                "member_id": str(row["member_id"]),
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "email": row["email"],
                "churn_probability": round(probability, 4),
                "risk_level": risk_level,
                "feature_vector": {k: round(v, 4) for k, v in features.items()},
                "top_factors": top_factors,
                "scored_at": now_iso,
            })

        # Sort by churn probability descending (highest risk first)
        results.sort(key=lambda x: x["churn_probability"], reverse=True)

        logger.info(
            "ML retention scoring complete",
            total_members=len(results),
            critical=sum(1 for r in results if r["risk_level"] == "critical"),
            high=sum(1 for r in results if r["risk_level"] == "high"),
            medium=sum(1 for r in results if r["risk_level"] == "medium"),
            low=sum(1 for r in results if r["risk_level"] == "low"),
        )
        return results

    async def get_feature_vector(
        self, member_id: str, schema_override: str | None = None,
    ) -> dict:
        """Return the raw normalized feature vector for a member."""
        async with get_tenant_db(
            **({"schema_override": schema_override} if schema_override else {})
        ) as db:
            row = await db.fetchrow(self._FEATURE_SQL, member_id)

        if not row:
            raise ValueError(f"Active member {member_id} not found")

        return self.get_feature_vector_from_row(row)

    async def get_dashboard_stats(
        self, schema_override: str | None = None,
    ) -> dict:
        """Aggregate retention dashboard: risk distribution, top factors, trends."""
        scores = await self.score_all_members(schema_override=schema_override)

        distribution = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        factor_impact = {}  # factor_name -> cumulative weighted contribution

        for s in scores:
            distribution[s["risk_level"]] += 1
            for f in s["top_factors"]:
                name = f["feature"]
                factor_impact[name] = factor_impact.get(name, 0) + abs(f["contribution"])

        # Top factors across the whole tenant, sorted by total impact
        top_factors_global = sorted(
            [{"feature": k, "total_impact": round(v, 4)} for k, v in factor_impact.items()],
            key=lambda x: x["total_impact"],
            reverse=True,
        )[:10]

        total = len(scores)
        avg_probability = (
            round(sum(s["churn_probability"] for s in scores) / total, 4)
            if total > 0 else 0.0
        )

        at_risk_members = [
            {
                "member_id": s["member_id"],
                "first_name": s["first_name"],
                "last_name": s["last_name"],
                "churn_probability": s["churn_probability"],
                "risk_level": s["risk_level"],
                "top_factors": s["top_factors"][:2],
            }
            for s in scores
            if s["churn_probability"] > 0.4
        ]

        return {
            "total_members_scored": total,
            "average_churn_probability": avg_probability,
            "risk_distribution": distribution,
            "at_risk_count": len(at_risk_members),
            "top_factors_global": top_factors_global,
            "at_risk_members": at_risk_members[:25],  # top 25 most at-risk
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ──────────────────────────────────────────────────────────────────────
    # Feature normalization
    # ──────────────────────────────────────────────────────────────────────

    def get_feature_vector_from_row(self, row) -> dict:
        """Normalize a raw DB row into a 0-1 feature vector.

        All features are normalized so that higher values push the churn
        score in the direction indicated by the weight sign:
        - Positive features (e.g. days_since_last_visit) are high when
          the member is at risk.
        - Negative features (e.g. visit_frequency_trend) are high when
          the member is healthy, so the negative weight reduces churn prob.
        """
        features = {}

        # 1. visit_frequency_trend: visits_last_14 / visits_prior_14
        #    1.0 = stable or improving, 0.0 = sharp decline
        prior = row["visits_prior_14"] or 0
        recent = row["visits_last_14"] or 0
        if prior == 0 and recent == 0:
            features["visit_frequency_trend"] = 0.5  # no data, neutral
        elif prior == 0:
            features["visit_frequency_trend"] = 1.0  # new activity, good
        else:
            features["visit_frequency_trend"] = min(recent / prior, 2.0) / 2.0

        # 2. days_since_last_visit: 0-1, capped at 60 days
        last_visit = row["last_visit_at"]
        if last_visit:
            days = (datetime.now(timezone.utc) - last_visit).total_seconds() / 86400
            features["days_since_last_visit"] = min(days / 60.0, 1.0)
        else:
            features["days_since_last_visit"] = 1.0  # never visited = max risk

        # 3. booking_cancellation_rate
        total_bookings = row["total_bookings_90d"] or 0
        cancellations = row["cancellations_90d"] or 0
        features["booking_cancellation_rate"] = (
            cancellations / total_bookings if total_bookings > 0 else 0.0
        )

        # 4. no_show_rate
        no_shows = row["no_shows_90d"] or 0
        features["no_show_rate"] = (
            no_shows / total_bookings if total_bookings > 0 else 0.0
        )

        # 5. membership_value_tier: current price / max price
        max_price = max(row["max_membership_price"] or 1, 1)
        features["membership_value_tier"] = (
            min((row["membership_price_cents"] or 0) / max_price, 1.0)
        )

        # 6. tenure_months: capped at 36
        joined = row["joined_at"]
        if joined:
            months = (datetime.now(timezone.utc) - joined).total_seconds() / (30.44 * 86400)
            features["tenure_months"] = min(months / 36.0, 1.0)
        else:
            features["tenure_months"] = 0.0

        # 7. payment_failure_count: 0-1, cap at 5 failures
        features["payment_failure_count"] = min(
            (row["payment_failures_90d"] or 0) / 5.0, 1.0
        )

        # 8. class_variety_score
        total_types = max(row["total_class_types"] or 1, 1)
        features["class_variety_score"] = min(
            (row["distinct_types_attended"] or 0) / total_types, 1.0
        )

        # 9. peak_hour_attendance
        peak_total = row["peak_total_attended"] or 0
        features["peak_hour_attendance"] = (
            (row["peak_hour_attended"] or 0) / peak_total
            if peak_total > 0 else 0.0
        )

        # 10. social_engagement: reviews + referrals, capped at 10
        social = (row["review_count"] or 0) + (row["referral_count"] or 0)
        features["social_engagement"] = min(social / 10.0, 1.0)

        # 11. consecutive_weeks_active: capped at 12 weeks
        features["consecutive_weeks_active"] = min(
            (row["consecutive_weeks"] or 0) / 12.0, 1.0
        )

        # 12. revenue_trend: last_30 / prior_30
        rev_prior = row["revenue_prior_30"] or 0
        rev_recent = row["revenue_last_30"] or 0
        if rev_prior == 0 and rev_recent == 0:
            features["revenue_trend"] = 0.5
        elif rev_prior == 0:
            features["revenue_trend"] = 1.0
        else:
            features["revenue_trend"] = min(rev_recent / rev_prior, 2.0) / 2.0

        return features

    # ──────────────────────────────────────────────────────────────────────
    # Scoring internals
    # ──────────────────────────────────────────────────────────────────────

    def _compute_probability(self, features: dict) -> float:
        """Logistic sigmoid: P(churn) = 1 / (1 + exp(-(w*x + b)))."""
        z = self.BIAS
        for name, weight in self.WEIGHTS.items():
            z += weight * features.get(name, 0.0)
        # Clamp z to prevent math overflow
        z = max(-20.0, min(20.0, z))
        return 1.0 / (1.0 + math.exp(-z))

    def _classify_risk(self, probability: float) -> str:
        """Map churn probability to a risk tier label."""
        if probability < self._THRESHOLDS[0]:
            return "low"
        elif probability < self._THRESHOLDS[1]:
            return "medium"
        elif probability < self._THRESHOLDS[2]:
            return "high"
        return "critical"

    def _extract_top_factors(self, features: dict) -> list[dict]:
        """Return features ranked by their absolute contribution to the score.

        Each entry includes the feature name, its normalized value,
        the weight, and the signed contribution (weight * value).
        """
        contributions = []
        for name, weight in self.WEIGHTS.items():
            value = features.get(name, 0.0)
            contribution = weight * value
            direction = (
                "increases_risk" if contribution > 0 else "decreases_risk"
            )
            contributions.append({
                "feature": name,
                "value": round(value, 4),
                "weight": weight,
                "contribution": round(contribution, 4),
                "direction": direction,
            })

        # Sort by absolute contribution, largest impact first
        contributions.sort(key=lambda x: abs(x["contribution"]), reverse=True)
        return contributions[:5]  # top 5
