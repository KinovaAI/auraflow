"""AuraFlow — AI Member Engagement Autopilot

Automated, personalized outreach to disengaged members using Claude AI.
Scans for new-dormant, lapsing, and at-risk members, creates personalized
email campaigns, handles replies conversationally, and can book classes
on behalf of members who express interest.

All emails use ANTHROPIC_MODEL_FAST (claude-haiku) to keep costs low.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ai.token_tracking_service import track_ai_usage
from app.services.email.email_service import EmailService
from app.services.scheduling.booking_service import BookingService

email_svc = EmailService()
booking_svc = BookingService()

# ── Constants ──────────────────────────────────────────────────────────────

MAX_CAMPAIGNS_PER_TENANT_PER_DAY = 20
MAX_FOLLOWUPS = 2  # initial + 2 follow-ups = 3 total outbound
MAX_REPLY_EXCHANGES = 10
FOLLOWUP_1_DELAY_DAYS = 3
FOLLOWUP_2_DELAY_DAYS = 4
FINAL_GRACE_DAYS = 7

_ENGAGEMENT_EMAIL_TYPE = "engagement_autopilot"


# ── Main Service ───────────────────────────────────────────────────────────

class EngagementAutopilot:

    def _is_configured(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    async def _call_claude(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1024,
        caller: str = "engagement_autopilot",
    ) -> str:
        """Call Claude (haiku) and track token usage."""
        if not self._is_configured():
            return "[AI not configured — set ANTHROPIC_API_KEY]"

        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        model = settings.ANTHROPIC_MODEL_FAST

        try:
            message = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            await track_ai_usage(
                service_name="engagement_autopilot",
                function_name=caller,
                model=model,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            )
            return message.content[0].text
        except Exception as e:
            logger.error("Engagement autopilot Claude call failed", error=str(e))
            return f"[AI error: {str(e)}]"

    # ── Member Scanning ────────────────────────────────────────────────────

    async def scan_for_engagement_targets(self, schema: str) -> list[dict]:
        """
        Query members matching disengagement patterns:
        - new_dormant: joined last 60 days, 0-1 visits, no active membership, no booking
        - lapsing: had activity but none in last 30 days
        - at_risk: flagged by churn prediction or no visit in 45+ days

        Skips members already in an active campaign, opted out, or recently engaged.
        """
        targets = []

        async with get_tenant_db(schema_override=schema) as db:
            # ── new_dormant ────────────────────────────────────────────
            new_dormant = await db.fetch("""
                SELECT m.id AS member_id, m.first_name, m.last_name, m.email,
                       m.created_at AS join_date, m.email_opt_in,
                       COALESCE(v.visit_count, 0) AS visit_count,
                       mm.status AS membership_status,
                       mt.name AS membership_name
                FROM members m
                LEFT JOIN (
                    SELECT member_id, COUNT(*) AS visit_count
                    FROM bookings
                    WHERE status = 'attended'
                    GROUP BY member_id
                ) v ON v.member_id = m.id
                LEFT JOIN member_memberships mm
                    ON mm.member_id = m.id AND mm.status = 'active'
                LEFT JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE m.created_at >= NOW() - INTERVAL '60 days'
                  AND COALESCE(v.visit_count, 0) <= 1
                  AND mm.id IS NULL
                  AND m.email IS NOT NULL
                  AND m.email_opt_in = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM bookings b
                      WHERE b.member_id = m.id
                        AND b.status IN ('confirmed', 'waitlisted')
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM engagement_campaigns ec
                      WHERE ec.member_id = m.id
                        AND ec.status = 'active'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM engagement_campaigns ec
                      WHERE ec.member_id = m.id
                        AND ec.created_at >= NOW() - INTERVAL '30 days'
                  )
                ORDER BY m.created_at DESC
            """)

            for row in new_dormant:
                days_since_join = (datetime.now(timezone.utc) - row["join_date"]).days
                priority = min(1.0, days_since_join / 60.0) * 0.7
                targets.append({
                    "member_id": str(row["member_id"]),
                    "member_data": dict(row),
                    "engagement_type": "new_dormant",
                    "priority_score": round(priority, 3),
                })

            # ── lapsing ────────────────────────────────────────────────
            lapsing = await db.fetch("""
                SELECT m.id AS member_id, m.first_name, m.last_name, m.email,
                       m.created_at AS join_date, m.email_opt_in,
                       MAX(b.checked_in_at) AS last_visit,
                       COUNT(b.id) AS total_visits,
                       mm.status AS membership_status,
                       mt.name AS membership_name
                FROM members m
                JOIN bookings b ON b.member_id = m.id AND b.status = 'attended'
                LEFT JOIN member_memberships mm
                    ON mm.member_id = m.id AND mm.status = 'active'
                LEFT JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE m.email IS NOT NULL
                  AND m.email_opt_in = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM bookings b2
                      WHERE b2.member_id = m.id
                        AND b2.status = 'attended'
                        AND b2.checked_in_at >= NOW() - INTERVAL '30 days'
                  )
                  AND EXISTS (
                      SELECT 1 FROM bookings b3
                      WHERE b3.member_id = m.id
                        AND b3.status = 'attended'
                        AND b3.checked_in_at >= NOW() - INTERVAL '90 days'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM engagement_campaigns ec
                      WHERE ec.member_id = m.id
                        AND ec.status = 'active'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM engagement_campaigns ec
                      WHERE ec.member_id = m.id
                        AND ec.created_at >= NOW() - INTERVAL '30 days'
                  )
                GROUP BY m.id, m.first_name, m.last_name, m.email,
                         m.created_at, m.email_opt_in, mm.status, mt.name
                ORDER BY MAX(b.checked_in_at) ASC
            """)

            for row in lapsing:
                last_visit = row["last_visit"]
                days_gone = (datetime.now(timezone.utc) - last_visit).days if last_visit else 60
                priority = min(1.0, days_gone / 60.0) * 0.85
                targets.append({
                    "member_id": str(row["member_id"]),
                    "member_data": dict(row),
                    "engagement_type": "lapsing",
                    "priority_score": round(priority, 3),
                })

            # ── at_risk ────────────────────────────────────────────────
            at_risk = await db.fetch("""
                SELECT m.id AS member_id, m.first_name, m.last_name, m.email,
                       m.created_at AS join_date, m.email_opt_in,
                       MAX(b.checked_in_at) AS last_visit,
                       COUNT(b.id) AS total_visits,
                       mm.status AS membership_status,
                       mt.name AS membership_name,
                       cr.risk_score AS churn_risk_score
                FROM members m
                JOIN bookings b ON b.member_id = m.id AND b.status = 'attended'
                LEFT JOIN member_memberships mm
                    ON mm.member_id = m.id AND mm.status = 'active'
                LEFT JOIN membership_types mt ON mt.id = mm.membership_type_id
                LEFT JOIN churn_risk cr
                    ON cr.member_id = m.id AND cr.status = 'active'
                WHERE m.email IS NOT NULL
                  AND m.email_opt_in = TRUE
                  AND (
                      cr.risk_score >= 0.7
                      OR NOT EXISTS (
                          SELECT 1 FROM bookings b2
                          WHERE b2.member_id = m.id
                            AND b2.status = 'attended'
                            AND b2.checked_in_at >= NOW() - INTERVAL '45 days'
                      )
                  )
                  AND EXISTS (
                      SELECT 1 FROM bookings b3
                      WHERE b3.member_id = m.id
                        AND b3.status = 'attended'
                        AND b3.checked_in_at < NOW() - INTERVAL '30 days'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM engagement_campaigns ec
                      WHERE ec.member_id = m.id
                        AND ec.status = 'active'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM engagement_campaigns ec
                      WHERE ec.member_id = m.id
                        AND ec.created_at >= NOW() - INTERVAL '30 days'
                  )
                GROUP BY m.id, m.first_name, m.last_name, m.email,
                         m.created_at, m.email_opt_in, mm.status, mt.name,
                         cr.risk_score
            """)

            for row in at_risk:
                churn_score = row["churn_risk_score"] or 0.5
                priority = min(1.0, float(churn_score)) * 0.95
                targets.append({
                    "member_id": str(row["member_id"]),
                    "member_data": dict(row),
                    "engagement_type": "at_risk",
                    "priority_score": round(priority, 3),
                })

        # Deduplicate (a member could match multiple patterns — keep highest priority)
        seen = {}
        for t in targets:
            mid = t["member_id"]
            if mid not in seen or t["priority_score"] > seen[mid]["priority_score"]:
                seen[mid] = t
        targets = sorted(seen.values(), key=lambda x: x["priority_score"], reverse=True)

        logger.info(
            "Engagement scan complete",
            schema=schema,
            total_targets=len(targets),
        )
        return targets

    # ── Campaign Creation ──────────────────────────────────────────────────

    async def create_campaign(
        self, schema: str, member_id: str, engagement_type: str, member_data: dict
    ) -> Optional[str]:
        """
        Create a personalized outreach campaign for a member.
        Generates the initial email via Claude and stores in engagement_campaigns.
        Returns campaign_id or None on failure.
        """
        async with get_tenant_db(schema_override=schema) as db:
            # Fetch studio name
            studio_row = await db.fetchrow(
                "SELECT name FROM studio_settings LIMIT 1"
            )
            studio_name = studio_row["name"] if studio_row else "our studio"

            # Fetch upcoming classes for recommendation
            upcoming = await db.fetch("""
                SELECT cs.id, cs.start_time, cs.end_time,
                       ct.name AS class_name, ct.category,
                       CONCAT(i.first_name, ' ', i.last_name) AS instructor_name,
                       cs.capacity - COALESCE(booked.cnt, 0) AS spots_left
                FROM class_sessions cs
                JOIN class_templates ct ON ct.id = cs.class_template_id
                LEFT JOIN (
                    SELECT class_session_id, COUNT(*) AS cnt
                    FROM bookings WHERE status = 'confirmed'
                    GROUP BY class_session_id
                ) booked ON booked.class_session_id = cs.id
                LEFT JOIN members i ON i.id = cs.instructor_id
                WHERE cs.start_time > NOW()
                  AND cs.start_time <= NOW() + INTERVAL '7 days'
                  AND cs.status = 'scheduled'
                ORDER BY cs.start_time
                LIMIT 10
            """)
            upcoming_classes = [dict(r) for r in upcoming]

        # Generate email content via Claude
        email_content = await self._generate_outreach_email(
            member_data=member_data,
            engagement_type=engagement_type,
            studio_name=studio_name,
            upcoming_classes=upcoming_classes,
        )

        if not email_content or email_content.get("subject", "").startswith("[AI"):
            logger.warning(
                "Failed to generate engagement email",
                member_id=member_id,
                engagement_type=engagement_type,
            )
            return None

        campaign_id = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        async with get_tenant_db(schema_override=schema) as db:
            # Create campaign
            await db.execute("""
                INSERT INTO engagement_campaigns (
                    id, member_id, engagement_type, status,
                    priority_score, created_at, updated_at
                ) VALUES ($1, $2, $3, 'active', $4, $5, $5)
            """, campaign_id, member_id, engagement_type, 0.0, now)

            # Store the initial outbound message
            await db.execute("""
                INSERT INTO engagement_messages (
                    id, campaign_id, direction, message_type,
                    subject, body_text, body_html, created_at
                ) VALUES ($1, $2, 'outbound', 'initial', $3, $4, $5, $6)
            """, message_id, campaign_id,
                email_content["subject"],
                email_content.get("body_text", ""),
                email_content.get("body_html", ""),
                now,
            )

            # Send the email
            member_email = member_data.get("email")
            if member_email:
                try:
                    result = await email_svc.send_email(
                        to_email=member_email,
                        subject=email_content["subject"],
                        html_content=email_content["body_html"],
                        plain_content=email_content.get("body_text"),
                        member_id=member_id,
                        email_type=_ENGAGEMENT_EMAIL_TYPE,
                    )
                    provider_msg_id = result.get("provider_id")

                    await db.execute("""
                        UPDATE engagement_messages
                        SET email_sent_at = $1, email_message_id = $2
                        WHERE id = $3
                    """, now, provider_msg_id, message_id)

                    await db.execute("""
                        UPDATE engagement_campaigns
                        SET initial_email_sent_at = $1, last_email_sent_at = $1,
                            updated_at = $1
                        WHERE id = $2
                    """, now, campaign_id)

                    logger.info(
                        "Engagement campaign created and initial email sent",
                        campaign_id=campaign_id,
                        member_id=member_id,
                        engagement_type=engagement_type,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to send engagement email",
                        campaign_id=campaign_id,
                        error=str(e),
                    )

        return campaign_id

    # ── Email Generation with Claude ───────────────────────────────────────

    async def _generate_outreach_email(
        self,
        member_data: dict,
        engagement_type: str,
        studio_name: str,
        upcoming_classes: list[dict],
    ) -> dict:
        """
        Generate a personalized outreach email using Claude.
        Returns {subject, body_html, body_text}.
        """
        first_name = member_data.get("first_name", "there")
        last_name = member_data.get("last_name", "")
        join_date = member_data.get("join_date", "")
        visit_count = member_data.get("visit_count", 0) or member_data.get("total_visits", 0)
        last_visit = member_data.get("last_visit", "")
        membership_name = member_data.get("membership_name", "")

        # Format upcoming classes for the prompt
        classes_text = ""
        if upcoming_classes:
            lines = []
            for c in upcoming_classes[:5]:
                start = c.get("start_time", "")
                if hasattr(start, "strftime"):
                    start = start.strftime("%A %b %d at %I:%M %p")
                name = c.get("class_name", "Class")
                instructor = c.get("instructor_name", "")
                spots = c.get("spots_left", "?")
                lines.append(f"- {name} with {instructor} on {start} ({spots} spots left)")
            classes_text = "\n".join(lines)

        type_instructions = {
            "new_dormant": (
                "This is a new member who joined recently but hasn't been active. "
                "Write a warm, welcoming email. Ask what brought them to the studio. "
                "Recommend a specific beginner-friendly class from the schedule this week. "
                "Keep it encouraging and low-pressure."
            ),
            "lapsing": (
                "This member used to attend classes but hasn't been in over 30 days. "
                "Write a 'we miss you' email. Mention their previous activity. "
                "Suggest a class similar to what they used to attend. "
                "Offer to help them get back on schedule."
            ),
            "at_risk": (
                "This member is at high risk of churning. They have previous activity "
                "but have been absent for a long time. Write a personal check-in. "
                "Acknowledge that life gets busy. Ask if there's anything the studio "
                "can do differently. Highlight any new classes or changes. "
                "Address potential barriers (schedule, difficulty, etc)."
            ),
        }

        system = (
            "You are a friendly studio assistant writing personalized emails to members "
            f"of {studio_name}. Write warm, personal, conversational emails — NOT "
            "corporate marketing copy. Use the member's first name. Keep emails short "
            "(3-5 short paragraphs). Do not use excessive exclamation marks. "
            "Every email MUST end with: \"Just reply to this email and I'll help you "
            f'get set up!\\n\\n— {studio_name} Team"\n\n'
            "Respond ONLY with valid JSON in this exact format:\n"
            '{"subject": "...", "body_text": "...", "body_html": "..."}\n\n'
            "For body_html, use simple HTML with <p> tags. No complex styling."
        )

        prompt = (
            f"Write a re-engagement email for this member:\n\n"
            f"Name: {first_name} {last_name}\n"
            f"Joined: {join_date}\n"
            f"Total visits: {visit_count}\n"
            f"Last visit: {last_visit or 'never'}\n"
            f"Membership: {membership_name or 'none'}\n\n"
            f"Engagement type: {engagement_type}\n"
            f"Instructions: {type_instructions.get(engagement_type, '')}\n\n"
            f"Upcoming classes this week:\n{classes_text or 'No classes available'}\n\n"
            f"Studio name: {studio_name}\n"
        )

        raw = await self._call_claude(prompt, system=system, caller="generate_outreach_email")

        try:
            # Strip markdown code fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning("Failed to parse Claude email response", error=str(e), raw=raw[:200])
            return {
                "subject": f"We'd love to see you at {studio_name}!",
                "body_text": raw,
                "body_html": f"<p>{raw}</p>",
            }

    # ── Reply Handling ─────────────────────────────────────────────────────

    async def handle_reply(
        self, schema: str, campaign_id: str, reply_text: str
    ) -> dict:
        """
        Process an inbound reply from a member in an active campaign.
        Uses Claude to understand intent and respond appropriately.
        Returns {action, response_sent, details}.
        """
        async with get_tenant_db(schema_override=schema) as db:
            # Load campaign + member info
            campaign = await db.fetchrow("""
                SELECT ec.*, m.first_name, m.last_name, m.email, m.id AS mid
                FROM engagement_campaigns ec
                JOIN members m ON m.id = ec.member_id
                WHERE ec.id = $1
            """, campaign_id)

            if not campaign:
                logger.warning("Engagement reply for unknown campaign", campaign_id=campaign_id)
                return {"action": "not_found", "response_sent": False}

            if campaign["status"] not in ("active", "replied"):
                logger.info("Engagement reply for non-active campaign", campaign_id=campaign_id)
                return {"action": "campaign_inactive", "response_sent": False}

            # Check reply count limit
            if campaign["reply_count"] >= MAX_REPLY_EXCHANGES:
                await self._escalate_campaign(db, campaign_id, campaign, "max_replies_reached")
                return {"action": "escalated", "response_sent": False, "details": "Max reply exchanges reached"}

            # Store inbound message
            inbound_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            await db.execute("""
                INSERT INTO engagement_messages (
                    id, campaign_id, direction, message_type,
                    body_text, created_at
                ) VALUES ($1, $2, 'inbound', 'reply', $3, $4)
            """, inbound_id, campaign_id, reply_text, now)

            await db.execute("""
                UPDATE engagement_campaigns
                SET status = 'replied', reply_count = reply_count + 1,
                    updated_at = $1
                WHERE id = $2
            """, now, campaign_id)

            # Load conversation history
            messages = await db.fetch("""
                SELECT direction, message_type, subject, body_text
                FROM engagement_messages
                WHERE campaign_id = $1
                ORDER BY created_at
            """, campaign_id)

            # Fetch studio info and upcoming classes for context
            studio_row = await db.fetchrow("SELECT name FROM studio_settings LIMIT 1")
            studio_name = studio_row["name"] if studio_row else "our studio"

            upcoming = await db.fetch("""
                SELECT cs.id AS session_id, cs.start_time,
                       ct.name AS class_name, ct.category,
                       CONCAT(i.first_name, ' ', i.last_name) AS instructor_name,
                       cs.capacity - COALESCE(booked.cnt, 0) AS spots_left
                FROM class_sessions cs
                JOIN class_templates ct ON ct.id = cs.class_template_id
                LEFT JOIN (
                    SELECT class_session_id, COUNT(*) AS cnt
                    FROM bookings WHERE status = 'confirmed'
                    GROUP BY class_session_id
                ) booked ON booked.class_session_id = cs.id
                LEFT JOIN members i ON i.id = cs.instructor_id
                WHERE cs.start_time > NOW()
                  AND cs.start_time <= NOW() + INTERVAL '7 days'
                  AND cs.status = 'scheduled'
                ORDER BY cs.start_time
                LIMIT 10
            """)

            # Fetch membership types for pricing questions
            memberships = await db.fetch("""
                SELECT name, price, billing_period, description
                FROM membership_types
                WHERE is_active = TRUE
                ORDER BY price
            """)

        # Build conversation context for Claude
        conv_lines = []
        for msg in messages:
            role = "Studio" if msg["direction"] == "outbound" else "Member"
            text = msg["body_text"] or ""
            conv_lines.append(f"{role}: {text[:500]}")
        conversation = "\n\n".join(conv_lines)

        classes_info = ""
        if upcoming:
            lines = []
            for c in upcoming:
                start = c["start_time"]
                if hasattr(start, "strftime"):
                    start = start.strftime("%A %b %d at %I:%M %p")
                lines.append(
                    f"- {c['class_name']} with {c['instructor_name']} on {start} "
                    f"(ID: {c['session_id']}, {c['spots_left']} spots left)"
                )
            classes_info = "\n".join(lines)

        pricing_info = ""
        if memberships:
            lines = []
            for mp in memberships:
                lines.append(f"- {mp['name']}: ${mp['price']}/{mp['billing_period']}")
            pricing_info = "\n".join(lines)

        system = (
            f"You are a friendly studio assistant for {studio_name}. "
            "You are responding to a member's email reply in a re-engagement campaign. "
            "Be warm, helpful, and conversational.\n\n"
            "Analyze the member's reply and respond appropriately. "
            "Your response MUST be valid JSON with this format:\n"
            '{"intent": "...", "response_text": "...", "response_html": "...", '
            '"wants_to_book": false, "class_session_id": null, '
            '"needs_human": false, "opted_out": false}\n\n'
            "Possible intents: asking_about_classes, asking_about_pricing, "
            "wants_to_book, not_interested, needs_human, general_chat, grateful\n\n"
            "If the member wants to book a class, set wants_to_book=true and "
            "class_session_id to the matching session ID from the schedule.\n"
            "If the member says they're not interested or want to stop emails, "
            "set opted_out=true and respond gracefully.\n"
            "If you can't help or the request is complex, set needs_human=true.\n\n"
            f"Always sign off with: — {studio_name} Team\n\n"
            f"Available classes this week:\n{classes_info or 'None available'}\n\n"
            f"Membership options:\n{pricing_info or 'Contact studio for pricing'}\n"
        )

        prompt = (
            f"Member: {campaign['first_name']} {campaign['last_name']}\n\n"
            f"Conversation so far:\n{conversation}\n\n"
            f"Latest reply from member:\n{reply_text}\n"
        )

        raw = await self._call_claude(prompt, system=system, max_tokens=1024, caller="handle_reply")

        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            ai_response = json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse reply AI response", raw=raw[:200])
            ai_response = {
                "intent": "general_chat",
                "response_text": raw,
                "response_html": f"<p>{raw}</p>",
                "wants_to_book": False,
                "needs_human": False,
                "opted_out": False,
            }

        action = ai_response.get("intent", "general_chat")
        result = {"action": action, "response_sent": False, "details": {}}

        async with get_tenant_db(schema_override=schema) as db:
            # Handle booking request
            if ai_response.get("wants_to_book") and ai_response.get("class_session_id"):
                booking_result = await self._attempt_booking(
                    schema, str(campaign["mid"]),
                    ai_response["class_session_id"],
                )
                result["details"]["booking"] = booking_result
                if booking_result.get("success"):
                    action = "booked"

            # Handle opt-out
            if ai_response.get("opted_out"):
                await db.execute("""
                    UPDATE engagement_campaigns
                    SET status = 'completed', outcome = 'opted_out',
                        outcome_at = $1, updated_at = $1
                    WHERE id = $2
                """, now, campaign_id)
                result["action"] = "opted_out"

            # Handle escalation
            elif ai_response.get("needs_human"):
                await self._escalate_campaign(db, campaign_id, campaign, "member_request")
                result["action"] = "escalated"

            # Handle booking conversion
            elif action == "booked":
                await db.execute("""
                    UPDATE engagement_campaigns
                    SET status = 'converted', outcome = 'booked',
                        outcome_at = $1, updated_at = $1
                    WHERE id = $2
                """, now, campaign_id)

            # Send AI response email
            response_html = ai_response.get("response_html", "")
            response_text = ai_response.get("response_text", "")
            if response_html and campaign["email"]:
                response_msg_id = str(uuid.uuid4())
                await db.execute("""
                    INSERT INTO engagement_messages (
                        id, campaign_id, direction, message_type,
                        body_text, body_html, created_at
                    ) VALUES ($1, $2, 'outbound', 'ai_response', $3, $4, $5)
                """, response_msg_id, campaign_id, response_text, response_html, now)

                try:
                    send_result = await email_svc.send_email(
                        to_email=campaign["email"],
                        subject=f"Re: Your message to {studio_name}",
                        html_content=response_html,
                        plain_content=response_text,
                        member_id=str(campaign["mid"]),
                        email_type=_ENGAGEMENT_EMAIL_TYPE,
                    )
                    provider_id = send_result.get("provider_id")
                    await db.execute("""
                        UPDATE engagement_messages
                        SET email_sent_at = $1, email_message_id = $2
                        WHERE id = $3
                    """, now, provider_id, response_msg_id)

                    await db.execute("""
                        UPDATE engagement_campaigns
                        SET last_email_sent_at = $1, updated_at = $1
                        WHERE id = $2
                    """, now, campaign_id)

                    result["response_sent"] = True
                except Exception as e:
                    logger.error(
                        "Failed to send engagement reply",
                        campaign_id=campaign_id,
                        error=str(e),
                    )

        logger.info(
            "Engagement reply processed",
            campaign_id=campaign_id,
            action=result["action"],
            response_sent=result["response_sent"],
        )
        return result

    # ── Follow-up Logic ────────────────────────────────────────────────────

    async def process_followups(self, schema: str) -> int:
        """
        Process follow-up emails for active campaigns.
        - Initial sent 3+ days ago, no reply → follow-up #1
        - Follow-up #1 sent 4+ days ago, no reply → follow-up #2
        - Follow-up #2 sent 7+ days ago, no reply → mark complete
        Returns count of follow-ups sent.
        """
        sent_count = 0
        now = datetime.now(timezone.utc)

        async with get_tenant_db(schema_override=schema) as db:
            # Campaigns needing follow-up #1
            need_followup1 = await db.fetch("""
                SELECT ec.id AS campaign_id, ec.member_id, ec.engagement_type,
                       ec.last_email_sent_at, ec.followup_count,
                       m.first_name, m.last_name, m.email
                FROM engagement_campaigns ec
                JOIN members m ON m.id = ec.member_id
                WHERE ec.status = 'active'
                  AND ec.followup_count = 0
                  AND ec.reply_count = 0
                  AND ec.initial_email_sent_at IS NOT NULL
                  AND ec.initial_email_sent_at <= NOW() - INTERVAL '3 days'
                  AND m.email_opt_in = TRUE
            """)

            # Campaigns needing follow-up #2
            need_followup2 = await db.fetch("""
                SELECT ec.id AS campaign_id, ec.member_id, ec.engagement_type,
                       ec.last_email_sent_at, ec.followup_count,
                       m.first_name, m.last_name, m.email
                FROM engagement_campaigns ec
                JOIN members m ON m.id = ec.member_id
                WHERE ec.status = 'active'
                  AND ec.followup_count = 1
                  AND ec.reply_count = 0
                  AND ec.last_email_sent_at <= NOW() - INTERVAL '4 days'
                  AND m.email_opt_in = TRUE
            """)

            # Campaigns that should be closed (follow-up #2 sent 7+ days ago)
            need_closing = await db.fetch("""
                SELECT ec.id AS campaign_id
                FROM engagement_campaigns ec
                WHERE ec.status = 'active'
                  AND ec.followup_count >= 2
                  AND ec.reply_count = 0
                  AND ec.last_email_sent_at <= NOW() - INTERVAL '7 days'
            """)

            # Close expired campaigns
            for row in need_closing:
                await db.execute("""
                    UPDATE engagement_campaigns
                    SET status = 'completed', outcome = 'no_response',
                        outcome_at = $1, updated_at = $1
                    WHERE id = $2
                """, now, row["campaign_id"])

            # Fetch studio name + upcoming classes once
            studio_row = await db.fetchrow("SELECT name FROM studio_settings LIMIT 1")
            studio_name = studio_row["name"] if studio_row else "our studio"

            upcoming = await db.fetch("""
                SELECT cs.start_time, ct.name AS class_name,
                       CONCAT(i.first_name, ' ', i.last_name) AS instructor_name
                FROM class_sessions cs
                JOIN class_templates ct ON ct.id = cs.class_template_id
                LEFT JOIN members i ON i.id = cs.instructor_id
                WHERE cs.start_time > NOW()
                  AND cs.start_time <= NOW() + INTERVAL '7 days'
                  AND cs.status = 'scheduled'
                ORDER BY cs.start_time
                LIMIT 5
            """)

        # Process follow-up #1
        for row in need_followup1:
            try:
                count = await self._send_followup(
                    schema, dict(row), 1, studio_name, [dict(u) for u in upcoming]
                )
                sent_count += count
            except Exception as e:
                logger.error(
                    "Followup 1 failed",
                    campaign_id=row["campaign_id"],
                    error=str(e),
                )

        # Process follow-up #2
        for row in need_followup2:
            try:
                count = await self._send_followup(
                    schema, dict(row), 2, studio_name, [dict(u) for u in upcoming]
                )
                sent_count += count
            except Exception as e:
                logger.error(
                    "Followup 2 failed",
                    campaign_id=row["campaign_id"],
                    error=str(e),
                )

        logger.info(
            "Engagement follow-ups processed",
            schema=schema,
            sent=sent_count,
            closed=len(need_closing),
        )
        return sent_count

    async def _send_followup(
        self,
        schema: str,
        campaign_row: dict,
        followup_num: int,
        studio_name: str,
        upcoming_classes: list[dict],
    ) -> int:
        """Generate and send a single follow-up email. Returns 1 on success, 0 on failure."""
        campaign_id = campaign_row["campaign_id"]
        first_name = campaign_row["first_name"]
        engagement_type = campaign_row["engagement_type"]

        classes_text = ""
        if upcoming_classes:
            lines = []
            for c in upcoming_classes[:3]:
                start = c.get("start_time", "")
                if hasattr(start, "strftime"):
                    start = start.strftime("%A %b %d at %I:%M %p")
                lines.append(f"- {c.get('class_name', 'Class')} on {start}")
            classes_text = "\n".join(lines)

        tone = "softer, shorter, last gentle nudge" if followup_num == 2 else "friendly check-in"

        system = (
            f"You are a friendly studio assistant for {studio_name}. "
            f"Write a {tone} follow-up email (follow-up #{followup_num}) to a member "
            "who hasn't replied to a previous outreach email. Keep it very short "
            "(2-3 paragraphs max). Do not be pushy or guilt-trip. "
            'End with: "Just reply to this email and I\'ll help you get set up!'
            f'\\n\\n— {studio_name} Team"\n\n'
            "Respond ONLY with valid JSON:\n"
            '{"subject": "...", "body_text": "...", "body_html": "..."}'
        )

        prompt = (
            f"Follow-up #{followup_num} for {first_name}.\n"
            f"Engagement type: {engagement_type}\n"
            f"Studio: {studio_name}\n"
            f"Upcoming classes:\n{classes_text or 'Check the schedule'}\n"
        )

        raw = await self._call_claude(prompt, system=system, max_tokens=512, caller="send_followup")

        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            email_content = json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse followup AI response", raw=raw[:200])
            return 0

        now = datetime.now(timezone.utc)
        message_id = str(uuid.uuid4())
        message_type = f"followup_{followup_num}"

        async with get_tenant_db(schema_override=schema) as db:
            await db.execute("""
                INSERT INTO engagement_messages (
                    id, campaign_id, direction, message_type,
                    subject, body_text, body_html, created_at
                ) VALUES ($1, $2, 'outbound', $3, $4, $5, $6, $7)
            """, message_id, campaign_id, message_type,
                email_content.get("subject", ""),
                email_content.get("body_text", ""),
                email_content.get("body_html", ""),
                now,
            )

            try:
                result = await email_svc.send_email(
                    to_email=campaign_row["email"],
                    subject=email_content.get("subject", f"Checking in — {studio_name}"),
                    html_content=email_content.get("body_html", ""),
                    plain_content=email_content.get("body_text"),
                    member_id=str(campaign_row["member_id"]),
                    email_type=_ENGAGEMENT_EMAIL_TYPE,
                )
                provider_id = result.get("provider_id")

                await db.execute("""
                    UPDATE engagement_messages
                    SET email_sent_at = $1, email_message_id = $2
                    WHERE id = $3
                """, now, provider_id, message_id)

                await db.execute("""
                    UPDATE engagement_campaigns
                    SET followup_count = $1, last_email_sent_at = $2, updated_at = $2
                    WHERE id = $3
                """, followup_num, now, campaign_id)

                return 1
            except Exception as e:
                logger.error(
                    "Failed to send follow-up email",
                    campaign_id=campaign_id,
                    followup_num=followup_num,
                    error=str(e),
                )
                return 0

    # ── Booking Assistant ──────────────────────────────────────────────────

    async def _attempt_booking(
        self, schema: str, member_id: str, class_session_id: str
    ) -> dict:
        """
        Attempt to book a member into a class session.
        Returns {success, details}.
        """
        try:
            booking = await booking_svc.book_class({
                "member_id": member_id,
                "class_session_id": class_session_id,
                "source": "engagement_autopilot",
                "notes": "Booked via AI engagement autopilot",
            })
            logger.info(
                "Engagement autopilot booked class",
                member_id=member_id,
                session_id=class_session_id,
                booking_id=booking.get("id"),
            )
            return {"success": True, "booking_id": booking.get("id"), "details": booking}
        except Exception as e:
            logger.warning(
                "Engagement autopilot booking failed",
                member_id=member_id,
                session_id=class_session_id,
                error=str(e),
            )
            return {"success": False, "error": str(e)}

    # ── Campaign Outcome Checking ──────────────────────────────────────────

    async def check_campaign_outcomes(self, schema: str) -> dict:
        """
        Check if members with active campaigns have engaged since the campaign started.
        Marks campaigns as converted when member: books, purchases membership, or visits.
        """
        converted = 0
        now = datetime.now(timezone.utc)

        async with get_tenant_db(schema_override=schema) as db:
            active_campaigns = await db.fetch("""
                SELECT ec.id AS campaign_id, ec.member_id, ec.created_at AS campaign_start
                FROM engagement_campaigns ec
                WHERE ec.status IN ('active', 'replied')
            """)

            for c in active_campaigns:
                mid = c["member_id"]
                started = c["campaign_start"]

                # Check for bookings since campaign started
                has_booking = await db.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM bookings
                        WHERE member_id = $1
                          AND created_at >= $2
                          AND status IN ('confirmed', 'attended')
                    )
                """, mid, started)

                if has_booking:
                    await db.execute("""
                        UPDATE engagement_campaigns
                        SET status = 'converted', outcome = 'booked',
                            outcome_at = $1, updated_at = $1
                        WHERE id = $2
                    """, now, c["campaign_id"])
                    converted += 1
                    continue

                # Check for new membership purchase
                has_membership = await db.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM member_memberships
                        WHERE member_id = $1
                          AND created_at >= $2
                          AND status = 'active'
                    )
                """, mid, started)

                if has_membership:
                    await db.execute("""
                        UPDATE engagement_campaigns
                        SET status = 'converted', outcome = 'purchased_membership',
                            outcome_at = $1, updated_at = $1
                        WHERE id = $2
                    """, now, c["campaign_id"])
                    converted += 1
                    continue

                # Check for attended visit since campaign started
                has_visit = await db.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM bookings
                        WHERE member_id = $1
                          AND checked_in_at >= $2
                          AND status = 'attended'
                    )
                """, mid, started)

                if has_visit:
                    await db.execute("""
                        UPDATE engagement_campaigns
                        SET status = 'converted', outcome = 'visited',
                            outcome_at = $1, updated_at = $1
                        WHERE id = $2
                    """, now, c["campaign_id"])
                    converted += 1

        logger.info(
            "Engagement outcome check complete",
            schema=schema,
            active_campaigns=len(active_campaigns),
            converted=converted,
        )
        return {"checked": len(active_campaigns), "converted": converted}

    # ── Escalation ─────────────────────────────────────────────────────────

    async def _escalate_campaign(
        self, db, campaign_id: str, campaign: dict, reason: str
    ) -> None:
        """Mark a campaign as escalated and notify the studio owner."""
        now = datetime.now(timezone.utc)

        # Find the studio owner
        owner_id = await db.fetchval("""
            SELECT u.id FROM users u
            WHERE u.role = 'owner'
            ORDER BY u.created_at
            LIMIT 1
        """)

        await db.execute("""
            UPDATE engagement_campaigns
            SET status = 'escalated', outcome = 'escalated',
                outcome_at = $1, escalated_to = $2, updated_at = $1
            WHERE id = $3
        """, now, owner_id, campaign_id)

        logger.info(
            "Engagement campaign escalated",
            campaign_id=campaign_id,
            reason=reason,
            escalated_to=owner_id,
        )

    # ── Inbound Reply Matching ─────────────────────────────────────────────

    async def match_reply_to_campaign(
        self, schema: str, from_email: str, subject: str
    ) -> Optional[str]:
        """
        Match an inbound email to an active engagement campaign by sender email.
        Returns campaign_id or None.
        """
        async with get_tenant_db(schema_override=schema) as db:
            campaign = await db.fetchrow("""
                SELECT ec.id
                FROM engagement_campaigns ec
                JOIN members m ON m.id = ec.member_id
                WHERE m.email = $1
                  AND ec.status IN ('active', 'replied')
                ORDER BY ec.updated_at DESC
                LIMIT 1
            """, from_email)

            return str(campaign["id"]) if campaign else None
