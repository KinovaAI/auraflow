"""AuraFlow — AI Service

Claude-powered content generation, churn analysis, member engagement insights,
and marketing draft management.
Gracefully degrades when Anthropic API key is not configured.
"""
import uuid
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ai.token_tracking_service import track_ai_usage


class AIService:

    def _is_configured(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    async def _call_claude(
        self,
        prompt: str,
        system: str = "",
        model: Optional[str] = None,
        max_tokens: int = 1024,
        caller: str = "unknown",
    ) -> str:
        """Call Claude API asynchronously. Returns the response text."""
        if not self._is_configured():
            return "[AI not configured — set ANTHROPIC_API_KEY]"

        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        model = model or settings.ANTHROPIC_MODEL

        try:
            message = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            await track_ai_usage(
                service_name="ai_service",
                function_name=caller,
                model=model,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            )
            return message.content[0].text
        except Exception as e:
            logger.error("Claude API call failed", error=str(e))
            return f"[AI error: {str(e)}]"

    # ── Content Generation ────────────────────────────────────────────────────

    async def generate_class_description(
        self,
        class_name: str,
        class_type: str,
        level: str = "all levels",
        duration_minutes: int = 60,
        studio_name: str = "",
        tone: str = "warm and inviting",
    ) -> dict:
        """Generate a class description for a yoga/fitness class."""
        system = (
            "You are a professional copywriter for yoga and fitness studios. "
            "Write engaging, warm class descriptions that attract students. "
            "Keep descriptions concise (2-3 paragraphs). "
            "Do not use markdown formatting — just plain text with line breaks."
        )
        prompt = (
            f"Write a class description for:\n"
            f"- Class name: {class_name}\n"
            f"- Type: {class_type}\n"
            f"- Level: {level}\n"
            f"- Duration: {duration_minutes} minutes\n"
            f"- Studio: {studio_name or 'a yoga studio'}\n"
            f"- Tone: {tone}\n\n"
            f"Include what students can expect, who the class is for, "
            f"and any benefits. Keep it concise and inviting."
        )
        text = await self._call_claude(prompt, system, model=settings.ANTHROPIC_MODEL_FAST, caller="generate_class_description")
        return {"description": text}

    async def generate_marketing_email(
        self,
        subject_context: str,
        audience: str = "all members",
        tone: str = "friendly and professional",
        studio_name: str = "",
    ) -> dict:
        """Generate marketing email content."""
        system = (
            "You are a marketing copywriter for a yoga/fitness studio. "
            "Write engaging email content. Provide a subject line and body. "
            "Keep the body under 200 words. Use a conversational tone. "
            "Do not use markdown — just plain text. "
            "Separate subject and body with a blank line."
        )
        prompt = (
            f"Write a marketing email for {studio_name or 'our studio'}:\n"
            f"- Topic: {subject_context}\n"
            f"- Audience: {audience}\n"
            f"- Tone: {tone}\n\n"
            f"Format:\nSubject: [subject line]\n\n[email body]"
        )
        text = await self._call_claude(prompt, system, model=settings.ANTHROPIC_MODEL_FAST, caller="generate_marketing_email")

        # Parse subject and body
        lines = text.strip().split("\n", 1)
        subject = lines[0].replace("Subject:", "").strip() if lines else ""
        body = lines[1].strip() if len(lines) > 1 else text

        return {"subject": subject, "body": body, "raw": text}

    async def generate_social_post(
        self,
        topic: str,
        platform: str = "instagram",
        studio_name: str = "",
    ) -> dict:
        """Generate a social media post."""
        system = (
            "You are a social media manager for a yoga/fitness studio. "
            f"Write a {platform} post. Be engaging and authentic. "
            "Include relevant hashtags. Keep it concise."
        )
        prompt = (
            f"Write a {platform} post for {studio_name or 'our studio'}:\n"
            f"Topic: {topic}\n\n"
            f"Include 3-5 relevant hashtags."
        )
        text = await self._call_claude(prompt, system, model=settings.ANTHROPIC_MODEL_FAST, caller="generate_social_post")
        return {"post": text, "platform": platform}

    # ── Analysis ──────────────────────────────────────────────────────────────

    async def analyze_churn_risk(self, member_data: dict) -> dict:
        """Analyze a member's churn risk based on their activity data."""
        system = (
            "You are a data analyst for a yoga studio. "
            "Analyze member data and provide churn risk assessment. "
            "Be concise and actionable. "
            "Respond with: Risk Level (Low/Medium/High), "
            "Key Factors (2-3 bullets), and Recommended Actions (2-3 bullets)."
        )
        prompt = (
            f"Analyze churn risk for this member:\n"
            f"- Total visits: {member_data.get('total_visits', 0)}\n"
            f"- Last visit: {member_data.get('last_visit_at', 'never')}\n"
            f"- Membership status: {member_data.get('membership_status', 'none')}\n"
            f"- Member since: {member_data.get('joined_at', 'unknown')}\n"
            f"- Lifetime revenue: ${member_data.get('lifetime_revenue_cents', 0) / 100:.2f}\n"
            f"- Recent booking cancellations: {member_data.get('recent_cancellations', 0)}\n"
            f"- Days since last visit: {member_data.get('days_since_visit', 'unknown')}\n"
        )
        text = await self._call_claude(prompt, system, model=settings.ANTHROPIC_MODEL_FAST, caller="analyze_churn_risk")
        return {"analysis": text}

    async def suggest_class_schedule(
        self,
        current_schedule_summary: str,
        attendance_data: str,
        studio_context: str = "",
    ) -> dict:
        """Suggest schedule optimizations based on attendance patterns."""
        system = (
            "You are a studio operations consultant. "
            "Analyze the schedule and attendance data to suggest optimizations. "
            "Be specific and actionable. Limit to 5 suggestions."
        )
        prompt = (
            f"Current schedule:\n{current_schedule_summary}\n\n"
            f"Attendance data:\n{attendance_data}\n\n"
            f"Context: {studio_context or 'Yoga studio'}\n\n"
            f"Suggest schedule optimizations to maximize attendance and revenue."
        )
        text = await self._call_claude(prompt, system, caller="suggest_class_schedule")
        return {"suggestions": text}

    # ── Marketing Drafts ──────────────────────────────────────────────────────

    async def generate_and_save_draft(
        self,
        prompt_context: str,
        draft_type: str = "email",
        tone: str = "friendly and professional",
        studio_name: str = "",
        created_by: str | None = None,
    ) -> dict:
        """Generate content via Claude and save as a draft for review."""
        if draft_type == "email":
            result = await self.generate_marketing_email(
                prompt_context, tone=tone, studio_name=studio_name,
            )
            subject = result["subject"]
            body = result["body"]
        elif draft_type == "social":
            result = await self.generate_social_post(
                prompt_context, studio_name=studio_name,
            )
            subject = None
            body = result["post"]
        elif draft_type == "class_description":
            result = await self.generate_class_description(
                class_name=prompt_context, class_type="yoga",
                studio_name=studio_name, tone=tone,
            )
            subject = None
            body = result["description"]
        else:
            # Generic generation
            body = await self._call_claude(
                prompt_context,
                system="You are a helpful copywriter for a yoga/fitness studio.",
                model=settings.ANTHROPIC_MODEL_FAST,
                caller="generate_draft",
            )
            subject = None

        draft_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO marketing_drafts
                    (id, prompt_context, draft_type, subject, body, created_by)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                draft_id, prompt_context, draft_type, subject, body, created_by,
            )
            row = await db.fetchrow(
                "SELECT * FROM marketing_drafts WHERE id = $1", draft_id,
            )

        logger.info("AI draft created", draft_id=draft_id, type=draft_type)
        return _draft_to_dict(row)

    async def list_drafts(
        self, status: str | None = None, limit: int = 50
    ) -> list[dict]:
        """List marketing drafts with optional status filter."""
        async with get_tenant_db() as db:
            if status:
                rows = await db.fetch(
                    """
                    SELECT * FROM marketing_drafts
                    WHERE status = $1
                    ORDER BY created_at DESC LIMIT $2
                    """,
                    status, limit,
                )
            else:
                rows = await db.fetch(
                    """
                    SELECT * FROM marketing_drafts
                    ORDER BY created_at DESC LIMIT $1
                    """,
                    limit,
                )
        return [_draft_to_dict(r) for r in rows]

    async def get_draft(self, draft_id: str) -> dict | None:
        """Get a single draft by ID."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM marketing_drafts WHERE id = $1", draft_id,
            )
        return _draft_to_dict(row) if row else None

    async def update_draft(self, draft_id: str, data: dict) -> dict | None:
        """Update draft subject/body."""
        allowed = {"subject", "body"}
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return await self.get_draft(draft_id)

        set_clauses = []
        params = [draft_id]
        idx = 2
        for key, val in updates.items():
            set_clauses.append(f"{key} = ${idx}")
            params.append(val)
            idx += 1
        set_clauses.append("updated_at = NOW()")

        async with get_tenant_db() as db:
            await db.execute(
                f"UPDATE marketing_drafts SET {', '.join(set_clauses)} WHERE id = $1",
                *params,
            )
            row = await db.fetchrow(
                "SELECT * FROM marketing_drafts WHERE id = $1", draft_id,
            )
        return _draft_to_dict(row) if row else None

    async def approve_draft(self, draft_id: str, reviewed_by: str) -> dict | None:
        """Approve a draft for sending."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE marketing_drafts
                SET status = 'approved', reviewed_by = $2, reviewed_at = NOW(), updated_at = NOW()
                WHERE id = $1 AND status = 'draft'
                RETURNING *
                """,
                draft_id, reviewed_by,
            )
        return _draft_to_dict(row) if row else None

    async def reject_draft(self, draft_id: str, reviewed_by: str) -> dict | None:
        """Reject a draft."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE marketing_drafts
                SET status = 'rejected', reviewed_by = $2, reviewed_at = NOW(), updated_at = NOW()
                WHERE id = $1 AND status = 'draft'
                RETURNING *
                """,
                draft_id, reviewed_by,
            )
        return _draft_to_dict(row) if row else None


# ── Serialization ─────────────────────────────────────────────────────────────

def _draft_to_dict(row) -> dict:
    d = dict(row)
    for k in ("id", "created_by", "reviewed_by", "campaign_id"):
        if d.get(k):
            d[k] = str(d[k])
    for k in ("created_at", "updated_at", "reviewed_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d
