"""AuraFlow — Milestone Celebration Service

Detects member visit milestones and anniversaries after check-in,
records them, and sends celebration notifications.
Optionally generates personalized video celebrations for major milestones
via HeyGen / D-ID.
"""
import uuid
from datetime import date

from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.email.email_service import EmailService
from app.services.marketing.campaign_service import SmsService
from app.services.ai.video_generation_service import (
    VideoGenerationService,
    MAJOR_MILESTONES,
)

email_svc = EmailService()
sms_svc = SmsService()
video_svc = VideoGenerationService()

VISIT_MILESTONES = [1, 10, 25, 50, 100, 250, 500]


class MilestoneService:

    async def check_milestones(
        self,
        member_id: str,
        total_visits: int,
        joined_at=None,
    ) -> list[dict]:
        """
        Check if a member has hit any new milestones after a check-in.
        Called from BookingService.check_in(). Returns list of triggered milestones.
        """
        triggered = []

        # Check visit milestones
        for threshold in VISIT_MILESTONES:
            if total_visits == threshold:
                milestone_type = f"visit_{threshold}"
                result = await self._record_milestone(member_id, milestone_type)
                if result:
                    triggered.append(result)

        # Check anniversary (within 3 days of anniversary date)
        if joined_at:
            today = date.today()
            join_date = joined_at.date() if hasattr(joined_at, 'date') else joined_at
            years = today.year - join_date.year
            if years >= 1:
                anniversary = join_date.replace(year=today.year)
                days_diff = abs((today - anniversary).days)
                if days_diff <= 3:
                    milestone_type = f"anniversary_{years}yr"
                    result = await self._record_milestone(member_id, milestone_type)
                    if result:
                        triggered.append(result)

        # Send notifications for triggered milestones
        if triggered:
            await self._send_milestone_notifications(member_id, triggered)

        return triggered

    async def _record_milestone(self, member_id: str, milestone_type: str) -> dict | None:
        """
        Record a milestone. Returns the milestone dict if new,
        None if already recorded (UNIQUE constraint).
        """
        milestone_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            try:
                await db.execute(
                    """
                    INSERT INTO member_milestones (id, member_id, milestone_type)
                    VALUES ($1, $2, $3)
                    """,
                    milestone_id, member_id, milestone_type,
                )
                logger.info(
                    "Milestone achieved",
                    member_id=member_id,
                    milestone=milestone_type,
                )
                return {"id": milestone_id, "milestone_type": milestone_type}
            except Exception:
                # UNIQUE constraint violation — already recorded
                return None

    async def _send_milestone_notifications(
        self, member_id: str, milestones: list[dict]
    ):
        """Send celebration email/SMS for triggered milestones."""
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
            return
        member = {**dict(row), "phone": decrypt_phone(row)}

        for ms in milestones:
            mt = ms["milestone_type"]
            message = self._format_milestone_message(
                member["first_name"], member["total_visits"], mt
            )

            # Send email
            if member.get("email_opt_in", True) and member.get("email"):
                try:
                    await email_svc.send_email(
                        to_email=member["email"],
                        subject=f"Congratulations, {member['first_name']}! 🎉",
                        html_content=f"""
                        <h2>Milestone Achieved!</h2>
                        <p>{message}</p>
                        <p>Keep up the amazing work!</p>
                        <p style="color: #666; font-size: 12px;">— Your Studio Team</p>
                        """,
                        member_id=str(member["id"]),
                        email_type="milestone",
                    )
                except Exception as e:
                    logger.warning(
                        "Milestone email failed",
                        member_id=member_id,
                        error=str(e),
                    )

            # Send SMS
            if member.get("sms_opt_in", True) and member.get("phone"):
                try:
                    await sms_svc.send_sms(
                        to_phone=member["phone"],
                        body=message,
                        member_id=str(member["id"]),
                        sms_type="milestone",
                    )
                except Exception as e:
                    logger.warning(
                        "Milestone SMS failed",
                        member_id=member_id,
                        error=str(e),
                    )

            # Generate video for major milestones (visit_50, visit_100, visit_250, visit_500)
            if mt in MAJOR_MILESTONES:
                try:
                    video_result = await video_svc.generate_milestone_video(
                        member_name=f"{member['first_name']} {member.get('last_name', '')}".strip(),
                        milestone_type=mt,
                        total_visits=member["total_visits"],
                    )
                    if video_result.get("video_id"):
                        async with get_tenant_db() as db:
                            await db.execute(
                                """
                                UPDATE member_milestones
                                SET video_url = $2,
                                    video_provider = $3,
                                    video_id = $4,
                                    video_status = $5
                                WHERE id = $1
                                """,
                                ms["id"],
                                video_result.get("video_url"),
                                video_result.get("provider"),
                                video_result.get("video_id"),
                                video_result.get("status", "processing"),
                            )
                        logger.info(
                            "Milestone video generation triggered",
                            milestone_id=ms["id"],
                            provider=video_result.get("provider"),
                            video_id=video_result.get("video_id"),
                        )
                except Exception as e:
                    logger.warning(
                        "Milestone video generation failed",
                        milestone_id=ms["id"],
                        milestone_type=mt,
                        error=str(e),
                    )

            # Mark as notified
            async with get_tenant_db() as db:
                await db.execute(
                    """
                    UPDATE member_milestones
                    SET notified_at = NOW()
                    WHERE id = $1
                    """,
                    ms["id"],
                )

    def _format_milestone_message(
        self, first_name: str, total_visits: int, milestone_type: str
    ) -> str:
        """Format a human-readable milestone message."""
        if milestone_type == "visit_1":
            return (
                f"Welcome {first_name}! You just completed your first class. "
                f"We're so glad you're here!"
            )
        elif milestone_type.startswith("visit_"):
            count = milestone_type.replace("visit_", "")
            return (
                f"Amazing, {first_name}! You just hit {count} classes! "
                f"Your dedication is inspiring."
            )
        elif milestone_type.startswith("anniversary_"):
            years = milestone_type.replace("anniversary_", "").replace("yr", "")
            return (
                f"Happy {years}-year anniversary, {first_name}! "
                f"You've been part of our community for {years} year(s) "
                f"and completed {total_visits} classes. Thank you!"
            )
        return f"Congratulations {first_name} on reaching a new milestone!"

    async def get_member_milestones(self, member_id: str) -> list[dict]:
        """Get all milestones for a member."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM member_milestones
                WHERE member_id = $1
                ORDER BY achieved_at DESC
                """,
                member_id,
            )
        return [_milestone_to_dict(r) for r in rows]


# ── Serialization ─────────────────────────────────────────────────────────────

def _milestone_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "member_id"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("achieved_at", "notified_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d
