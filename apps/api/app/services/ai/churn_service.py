"""AuraFlow — Churn Detection Service

Rule-based churn risk detection: scans member attendance patterns
and flags at-risk members for outreach.

Also provides ML-enhanced churn scanning via RetentionModel for
multi-factor probability scoring and detailed risk analysis.
"""
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.email.email_service import EmailService
from app.services.marketing.campaign_service import SmsService
from app.services.ai.retention_model import RetentionModel


email_svc = EmailService()
sms_svc = SmsService()
retention_model = RetentionModel()


class ChurnService:

    async def scan_tenant_churn(self, schema_override: str | None = None) -> dict:
        """
        Scan members for churn risk using rule-based detection.

        Rule 1: Member had 3+ visits in prior 30 days but zero in last 14 days.
        Rule 2: Active member with zero visits in last 21 days.

        Returns dict with newly_flagged and cleared counts.
        """
        db_kwargs = {"schema_override": schema_override} if schema_override else {}

        async with get_tenant_db(**db_kwargs) as db:
            # Flag members at risk (not already flagged)
            newly_flagged = await db.fetch(
                """
                WITH recent_visitors AS (
                    -- Members who had 3+ visits in the 14-30 day window
                    SELECT b.member_id, COUNT(*) AS visit_count
                    FROM bookings b
                    WHERE b.status = 'attended'
                      AND b.checked_in_at >= NOW() - INTERVAL '30 days'
                      AND b.checked_in_at < NOW() - INTERVAL '14 days'
                    GROUP BY b.member_id
                    HAVING COUNT(*) >= 3
                ),
                no_recent AS (
                    -- Members with zero visits in last 14 days
                    SELECT rv.member_id
                    FROM recent_visitors rv
                    WHERE NOT EXISTS (
                        SELECT 1 FROM bookings b2
                        WHERE b2.member_id = rv.member_id
                          AND b2.status = 'attended'
                          AND b2.checked_in_at >= NOW() - INTERVAL '14 days'
                    )
                ),
                inactive_21 AS (
                    -- Active members with no visits in 21 days
                    SELECT m.id AS member_id
                    FROM members m
                    WHERE m.is_active = TRUE
                      AND m.total_visits > 0
                      AND (m.last_visit_at IS NULL OR m.last_visit_at < NOW() - INTERVAL '21 days')
                ),
                at_risk AS (
                    SELECT member_id FROM no_recent
                    UNION
                    SELECT member_id FROM inactive_21
                )
                UPDATE members m
                SET churn_risk_flagged_at = NOW(), updated_at = NOW()
                FROM at_risk ar
                WHERE m.id = ar.member_id
                  AND m.churn_risk_flagged_at IS NULL
                  AND m.is_active = TRUE
                RETURNING m.id, m.first_name, m.last_name, m.email
                """
            )

            # Clear flags for members who have returned
            cleared = await db.fetch(
                """
                UPDATE members
                SET churn_risk_flagged_at = NULL, updated_at = NOW()
                WHERE churn_risk_flagged_at IS NOT NULL
                  AND last_visit_at >= NOW() - INTERVAL '7 days'
                RETURNING id
                """
            )

        flagged_count = len(newly_flagged)
        cleared_count = len(cleared)

        if flagged_count > 0:
            logger.info(
                "Churn scan flagged members",
                newly_flagged=flagged_count,
                cleared=cleared_count,
            )

        return {
            "newly_flagged": flagged_count,
            "cleared": cleared_count,
            "flagged_members": [
                {
                    "id": str(r["id"]),
                    "first_name": r["first_name"],
                    "last_name": r["last_name"],
                    "email": r["email"],
                }
                for r in newly_flagged
            ],
        }

    async def get_at_risk_members(self) -> list[dict]:
        """List members currently flagged as churn risk."""
        from app.services.members.phi_helpers import decrypt_phone
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT id, first_name, last_name, email, phone_enc,
                       total_visits, last_visit_at, joined_at,
                       lifetime_revenue_cents, churn_risk_flagged_at
                FROM members
                WHERE churn_risk_flagged_at IS NOT NULL
                  AND is_active = TRUE
                ORDER BY churn_risk_flagged_at DESC
                """
            )
        # Decrypt phone before serializing — _member_risk_to_dict reads
        # row["phone"], so substituting the decrypted value upstream
        # keeps the API response shape stable post plaintext-drop.
        return [
            _member_risk_to_dict({**dict(r), "phone": decrypt_phone(r)})
            for r in rows
        ]

    async def dismiss_churn_flag(self, member_id: str) -> bool:
        """Clear churn risk flag for a member."""
        async with get_tenant_db() as db:
            result = await db.execute(
                """
                UPDATE members
                SET churn_risk_flagged_at = NULL, updated_at = NOW()
                WHERE id = $1
                """,
                member_id,
            )
        return "UPDATE 1" in result

    # ── ML-enhanced methods ─────────────────────────────────────────────

    async def ml_scan_tenant_churn(
        self, schema_override: str | None = None,
    ) -> dict:
        """ML-enhanced churn scan using RetentionModel.

        Scores every active member with the 12-feature weighted model,
        then flags those with churn probability > 0.4 (high / critical).
        Returns summary stats plus the list of newly flagged members.
        """
        db_kwargs = {"schema_override": schema_override} if schema_override else {}

        scores = await retention_model.score_all_members(
            schema_override=schema_override,
        )

        at_risk = [s for s in scores if s["churn_probability"] > 0.4]
        at_risk_ids = [s["member_id"] for s in at_risk]

        # Flag at-risk members in the DB (only those not already flagged)
        newly_flagged_rows = []
        cleared_count = 0

        async with get_tenant_db(**db_kwargs) as db:
            if at_risk_ids:
                newly_flagged_rows = await db.fetch(
                    """
                    UPDATE members
                    SET churn_risk_flagged_at = NOW(), updated_at = NOW()
                    WHERE id = ANY($1::uuid[])
                      AND churn_risk_flagged_at IS NULL
                      AND is_active = TRUE
                    RETURNING id, first_name, last_name, email
                    """,
                    at_risk_ids,
                )

            # Clear flags for low-risk members who were previously flagged
            low_risk_ids = [
                s["member_id"] for s in scores
                if s["churn_probability"] <= 0.2
            ]
            if low_risk_ids:
                cleared = await db.fetch(
                    """
                    UPDATE members
                    SET churn_risk_flagged_at = NULL, updated_at = NOW()
                    WHERE id = ANY($1::uuid[])
                      AND churn_risk_flagged_at IS NOT NULL
                    RETURNING id
                    """,
                    low_risk_ids,
                )
                cleared_count = len(cleared)

        flagged_count = len(newly_flagged_rows)

        if flagged_count > 0:
            logger.info(
                "ML churn scan flagged members",
                newly_flagged=flagged_count,
                cleared=cleared_count,
                total_at_risk=len(at_risk),
            )

        return {
            "model": "retention_v1",
            "total_scored": len(scores),
            "newly_flagged": flagged_count,
            "cleared": cleared_count,
            "total_at_risk": len(at_risk),
            "risk_distribution": {
                "low": sum(1 for s in scores if s["risk_level"] == "low"),
                "medium": sum(1 for s in scores if s["risk_level"] == "medium"),
                "high": sum(1 for s in scores if s["risk_level"] == "high"),
                "critical": sum(1 for s in scores if s["risk_level"] == "critical"),
            },
            "flagged_members": [
                {
                    "id": str(r["id"]),
                    "first_name": r["first_name"],
                    "last_name": r["last_name"],
                    "email": r["email"],
                }
                for r in newly_flagged_rows
            ],
            "at_risk_members": [
                {
                    "member_id": s["member_id"],
                    "first_name": s["first_name"],
                    "last_name": s["last_name"],
                    "churn_probability": s["churn_probability"],
                    "risk_level": s["risk_level"],
                    "top_factors": s["top_factors"][:3],
                }
                for s in at_risk
            ],
        }

    async def get_member_risk_score(
        self, member_id: str, schema_override: str | None = None,
    ) -> dict:
        """Return detailed ML risk score for a single member.

        Wraps RetentionModel.score_member() and adds contextual data
        like days since last visit and current membership status.
        """
        score = await retention_model.score_member(
            member_id, schema_override=schema_override,
        )
        return score

    async def send_winback_outreach(self, member_id: str) -> dict:
        """Send a 'we miss you' email/SMS to a flagged member."""
        from app.services.members.phi_helpers import decrypt_phone
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT id, first_name, last_name, email, phone_enc,
                       total_visits, email_opt_in, sms_opt_in
                FROM members WHERE id = $1
                """,
                member_id,
            )

        if not row:
            raise ValueError("Member not found")
        member = {**dict(row), "phone": decrypt_phone(row)}

        name = f"{member['first_name']} {member['last_name']}"
        sent_channels = []

        # Send email
        if member.get("email_opt_in", True) and member.get("email"):
            try:
                await email_svc.send_email(
                    to_email=member["email"],
                    subject=f"We miss you, {member['first_name']}!",
                    html_content=f"""
                    <h2>We Miss You!</h2>
                    <p>Hi {member['first_name']},</p>
                    <p>It's been a while since we've seen you at the studio.
                    We'd love to welcome you back!</p>
                    <p>You've been an amazing part of our community with
                    {member['total_visits']} classes under your belt.</p>
                    <p>Come back and try something new — we have exciting
                    classes waiting for you.</p>
                    <p style="color: #666; font-size: 12px;">— Your Studio Team</p>
                    """,
                    member_id=str(member["id"]),
                    email_type="winback",
                )
                sent_channels.append("email")
            except Exception as e:
                logger.warning("Winback email failed", member_id=member_id, error=str(e))

        # Send SMS
        if member.get("sms_opt_in", True) and member.get("phone"):
            try:
                await sms_svc.send_sms(
                    to_phone=member["phone"],
                    member_id=str(member["id"]),
                    body=(
                        f"Hi {member['first_name']}! We miss you at the studio. "
                        f"It's been a while — come back and try a class! "
                        f"You've completed {member['total_visits']} classes so far."
                    ),
                )
                sent_channels.append("sms")
            except Exception as e:
                logger.warning("Winback SMS failed", member_id=member_id, error=str(e))

        logger.info("Winback sent", member_id=member_id, channels=sent_channels)
        return {
            "member_id": member_id,
            "name": name,
            "channels": sent_channels,
        }


# ── Serialization ─────────────────────────────────────────────────────────────

def _member_risk_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id",):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("last_visit_at", "joined_at", "churn_risk_flagged_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d
