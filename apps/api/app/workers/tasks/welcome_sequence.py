"""AuraFlow — Welcome Sequence Task

Runs daily at 10 AM UTC via Celery Beat. Sends drip emails to new members:
- Day 3: "How's it going?" check-in
- Day 7: "Book your next class" engagement
Day 0 welcome is sent inline when membership activates (webhook_handler.py).
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.email.email_service import EmailService
from app.workers.celery_app import app

email_svc = EmailService()

SEQUENCE_STEPS = [
    {
        "day": 1,
        "type": "welcome_day1",
        "subject": "Welcome to the studio — we're glad you're here!",
        "html": """
        <h2>Welcome!</h2>
        <p>Hi {name},</p>
        <p>We're thrilled you've joined <strong>{type_name}</strong>.
        This is the start of something great, and we can't wait to see you
        in the studio.</p>
        <p>Here's what to know for your first visit:</p>
        <ul>
            <li>Arrive 10–15 minutes early so we can show you around</li>
            <li>Bring a water bottle and wear comfortable clothes</li>
            <li>No experience needed — our instructors will guide you</li>
        </ul>
        <p>If you have any questions, just reply to this email or stop by
        the front desk. We're here for you!</p>
        <p style="color: #666; font-size: 12px;">— The AuraFlow Team</p>
        """,
    },
    {
        "day": 3,
        "type": "welcome_day3",
        "subject": "How's your first week going?",
        "html": """
        <h2>How's it going?</h2>
        <p>Hi {name},</p>
        <p>You joined {type_name} a few days ago — we hope you're enjoying it!</p>
        <p>If you haven't booked a class yet, now is a great time to try one.
        Check out the schedule in your member portal.</p>
        <p>Have questions? Don't hesitate to reach out to the front desk.</p>
        <p style="color: #666; font-size: 12px;">— AuraFlow</p>
        """,
    },
    {
        "day": 7,
        "type": "welcome_day7",
        "subject": "Your first week — what's next?",
        "html": """
        <h2>One week in!</h2>
        <p>Hi {name},</p>
        <p>It's been a week since you started your <strong>{type_name}</strong> membership.
        We hope you're settling in!</p>
        <p>Here are some tips to get the most out of your membership:</p>
        <ul>
            <li>Try a different class type to find your favorites</li>
            <li>Book a few days ahead — popular classes fill up fast</li>
            <li>Check the member portal for personalized class suggestions</li>
        </ul>
        <p>See you in class!</p>
        <p style="color: #666; font-size: 12px;">— AuraFlow</p>
        """,
    },
    {
        "day": 14,
        "type": "welcome_day14",
        "subject": "Halfway through your first month!",
        "html": """
        <h2>Two weeks in — how's it going?</h2>
        <p>Hi {name},</p>
        <p>You're halfway through your first month with
        <strong>{type_name}</strong>. We hope you're starting to feel
        at home!</p>
        <p>By now you may have tried a few classes. If there's a style or
        instructor you love, consider booking a recurring spot so you
        never miss out.</p>
        <p>We'd love to hear how things are going — feel free to reply
        to this email or chat with us at the front desk.</p>
        <p style="color: #666; font-size: 12px;">— The AuraFlow Team</p>
        """,
    },
    {
        "day": 30,
        "type": "welcome_day30",
        "subject": "One month in — we'd love your feedback!",
        "html": """
        <h2>Happy one-month anniversary!</h2>
        <p>Hi {name},</p>
        <p>It's been a full month since you started your
        <strong>{type_name}</strong> membership. Congratulations on
        sticking with it!</p>
        <p>We're always looking to improve, and your perspective as a
        new member is invaluable. We'd really appreciate it if you
        could take a moment to share your thoughts:</p>
        <ul>
            <li>What's been your favorite class or instructor so far?</li>
            <li>Is there anything we could do better?</li>
            <li>Would you recommend us to a friend?</li>
        </ul>
        <p>Just reply to this email — we read every response.</p>
        <p>Thank you for being part of our community!</p>
        <p style="color: #666; font-size: 12px;">— The AuraFlow Team</p>
        """,
    },
]


async def _run_sequence_for_tenant(schema_name: str) -> int:
    """Run welcome sequence for a single tenant."""
    sent_count = 0
    now = datetime.now(timezone.utc)

    async with get_tenant_db(schema_override=schema_name) as db:
        for step in SEQUENCE_STEPS:
            window_start = now - timedelta(hours=step["day"] * 24 + 24)
            window_end = now - timedelta(hours=step["day"] * 24)

            rows = await db.fetch(
                """
                SELECT mm.id AS membership_id, mm.created_at AS mm_created_at,
                       mt.name AS type_name,
                       m.id AS member_id, m.first_name, m.last_name,
                       m.email, m.email_opt_in
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                JOIN members m ON m.id = mm.member_id
                WHERE mm.created_at BETWEEN $1 AND $2
                  AND mm.status IN ('active', 'frozen')
                  AND m.email_opt_in = TRUE
                  AND m.email IS NOT NULL
                """,
                window_start, window_end,
            )

            for row in rows:
                member_id = str(row["member_id"])

                # Dedup check
                existing = await db.fetchval(
                    """
                    SELECT COUNT(*) FROM communication_log
                    WHERE member_id = $1 AND type = $2
                    """,
                    member_id, step["type"],
                )
                if existing > 0:
                    continue

                name = f"{row['first_name']} {row['last_name']}"
                type_name = row["type_name"]

                try:
                    html = step["html"].format(name=name, type_name=type_name)
                    await email_svc.send_email(
                        to_email=row["email"],
                        subject=step["subject"],
                        html_content=html,
                        member_id=member_id,
                        email_type=step["type"],
                    )
                    sent_count += 1
                except Exception as e:
                    logger.warning(
                        "Welcome sequence send failed",
                        member_id=member_id,
                        step=step["type"],
                        error=str(e),
                    )

    return sent_count


async def _run_all_welcome_sequences() -> int:
    """Run welcome sequences across all tenants."""
    total = 0
    async with get_global_db() as db:
        schemas = await db.fetch(
            "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
        )

    for row in schemas:
        try:
            count = await _run_sequence_for_tenant(row["schema_name"])
            total += count
        except Exception as e:
            logger.error(
                "Welcome sequence failed for tenant",
                schema=row["schema_name"],
                error=str(e),
            )

    return total


@app.task(name="app.workers.tasks.welcome_sequence.run_welcome_sequence")
def run_welcome_sequence():
    """Celery task: run welcome drip sequence for all tenants."""
    loop = asyncio.new_event_loop()
    try:
        total = loop.run_until_complete(_run_all_welcome_sequences())
        logger.info("Welcome sequence emails sent", total=total)
        return {"emails_sent": total}
    finally:
        loop.close()
