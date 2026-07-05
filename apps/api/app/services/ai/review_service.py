"""AuraFlow — Review Service

Member class reviews with AI-powered sentiment analysis (Claude Haiku)
and AI-drafted staff responses.  Supports rating, text review, moderation,
and aggregate statistics.
"""
import json
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ai.token_tracking_service import track_ai_usage


class ReviewService:

    # ── AI Methods ─────────────────────────────────────────────────────

    async def _analyze_sentiment(self, review_text: str) -> dict:
        """Analyze sentiment of a review using Claude Haiku.

        Returns {sentiment, score, analysis} or defaults on failure.
        """
        if not settings.ANTHROPIC_API_KEY or not review_text:
            return {"sentiment": None, "score": None, "analysis": None}

        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        try:
            message = await client.messages.create(
                model=settings.ANTHROPIC_MODEL_FAST,
                max_tokens=256,
                system=(
                    "Analyze the sentiment of this fitness class review. "
                    "Return ONLY a JSON object (no markdown fences): "
                    '{"sentiment": "positive"|"neutral"|"negative", '
                    '"score": float from -1.0 to 1.0, '
                    '"analysis": "one sentence summary of key themes"}'
                ),
                messages=[{"role": "user", "content": review_text}],
            )
            await track_ai_usage(
                service_name="review_service",
                function_name="analyze_sentiment",
                model=settings.ANTHROPIC_MODEL_FAST,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(raw)
            return {
                "sentiment": result.get("sentiment"),
                "score": float(result.get("score", 0)),
                "analysis": result.get("analysis"),
            }
        except Exception as e:
            logger.warning("Sentiment analysis failed", error=str(e))
            return {"sentiment": None, "score": None, "analysis": None}

    async def _generate_response_draft(self, review: dict) -> str | None:
        """Generate an AI draft response for a review."""
        if not settings.ANTHROPIC_API_KEY or not review.get("review_text"):
            return None

        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        try:
            message = await client.messages.create(
                model=settings.ANTHROPIC_MODEL_FAST,
                max_tokens=256,
                system=(
                    "You are a friendly studio manager responding to a class review. "
                    "Be warm, professional, and address specific feedback mentioned. "
                    "Keep the response under 3 sentences. Do not use emojis. "
                    "Return only the response text, no JSON or formatting."
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Class: {review.get('session_title', 'class')}\n"
                        f"Rating: {review.get('rating', '?')}/5 stars\n"
                        f"Review: {review.get('review_text', '')}"
                    ),
                }],
            )
            await track_ai_usage(
                service_name="review_service",
                function_name="generate_response_draft",
                model=settings.ANTHROPIC_MODEL_FAST,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            )
            return message.content[0].text.strip()
        except Exception as e:
            logger.warning("Response draft generation failed", error=str(e))
            return None

    # ── Submit Review (Member Portal) ──────────────────────────────────

    async def submit_review(self, member_id: str, data: dict) -> dict:
        """Submit a review for a class the member attended."""
        review_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            # Verify member attended this session
            booking = await db.fetchrow(
                """
                SELECT id FROM bookings
                WHERE member_id = $1 AND class_session_id = $2 AND status = 'attended'
                """,
                member_id, data["class_session_id"],
            )
            if not booking:
                raise ValueError("You can only review classes you have attended")

            # Check for duplicate
            existing = await db.fetchrow(
                "SELECT id FROM reviews WHERE member_id = $1 AND class_session_id = $2",
                member_id, data["class_session_id"],
            )
            if existing:
                raise ValueError("You have already reviewed this class")

            # Get session title for AI context
            session = await db.fetchrow(
                "SELECT title FROM class_sessions WHERE id = $1",
                data["class_session_id"],
            )
            session_title = session["title"] if session else "class"

            # Sentiment analysis
            sentiment_data = await self._analyze_sentiment(data.get("review_text", ""))

            # Generate response draft
            draft_context = {
                "session_title": session_title,
                "rating": data["rating"],
                "review_text": data.get("review_text"),
            }
            response_draft = await self._generate_response_draft(draft_context)

            row = await db.fetchrow(
                """
                INSERT INTO reviews
                    (id, member_id, class_session_id, rating, review_text,
                     sentiment, sentiment_score, ai_analysis, response_draft)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING *
                """,
                review_id, member_id, data["class_session_id"],
                data["rating"], data.get("review_text"),
                sentiment_data["sentiment"],
                sentiment_data["score"],
                sentiment_data["analysis"],
                response_draft,
            )

            logger.info(
                "Review submitted",
                review_id=review_id,
                member_id=member_id,
                rating=data["rating"],
                sentiment=sentiment_data["sentiment"],
            )
            return self._review_to_dict(row)

    # ── Staff Review Management ────────────────────────────────────────

    async def list_reviews(
        self,
        sentiment: str | None = None,
        min_rating: int | None = None,
        is_flagged: bool | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List reviews with optional filters."""
        async with get_tenant_db() as db:
            conditions = ["1=1"]
            params: list = []
            idx = 0

            if sentiment:
                idx += 1
                conditions.append(f"r.sentiment = ${idx}")
                params.append(sentiment)

            if min_rating is not None:
                idx += 1
                conditions.append(f"r.rating >= ${idx}")
                params.append(min_rating)

            if is_flagged is not None:
                idx += 1
                conditions.append(f"r.is_flagged = ${idx}")
                params.append(is_flagged)

            idx += 1
            where = " AND ".join(conditions)
            sql = f"""
                SELECT r.*,
                    m.first_name, m.last_name,
                    cs.title AS session_title, cs.starts_at AS session_date
                FROM reviews r
                JOIN members m ON m.id = r.member_id
                JOIN class_sessions cs ON cs.id = r.class_session_id
                WHERE {where}
                ORDER BY r.created_at DESC
                LIMIT ${idx}
            """
            params.append(limit)
            rows = await db.fetch(sql, *params)
            return [self._review_to_dict(r, include_member=True) for r in rows]

    async def get_review(self, review_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT r.*,
                    m.first_name, m.last_name,
                    cs.title AS session_title, cs.starts_at AS session_date
                FROM reviews r
                JOIN members m ON m.id = r.member_id
                JOIN class_sessions cs ON cs.id = r.class_session_id
                WHERE r.id = $1
                """,
                review_id,
            )
            return self._review_to_dict(row, include_member=True) if row else None

    async def get_review_stats(self) -> dict:
        """Aggregate review statistics."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_reviews,
                    COALESCE(AVG(rating), 0) AS avg_rating,
                    COUNT(*) FILTER (WHERE sentiment = 'positive') AS positive_count,
                    COUNT(*) FILTER (WHERE sentiment = 'neutral') AS neutral_count,
                    COUNT(*) FILTER (WHERE sentiment = 'negative') AS negative_count,
                    COUNT(*) FILTER (WHERE response_text IS NOT NULL) AS responded_count
                FROM reviews
                """
            )
            total = row["total_reviews"] or 0
            responded = row["responded_count"] or 0
            return {
                "total_reviews": total,
                "avg_rating": round(float(row["avg_rating"]), 2),
                "positive_count": row["positive_count"],
                "neutral_count": row["neutral_count"],
                "negative_count": row["negative_count"],
                "responded_count": responded,
                "response_rate": round(responded / total * 100, 1) if total > 0 else 0,
            }

    async def respond_to_review(
        self, review_id: str, response_text: str, responded_by: str,
    ) -> dict | None:
        """Staff submits a response to a review."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE reviews
                SET response_text = $2, responded_by = $3, responded_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                review_id, response_text, responded_by,
            )
            if row:
                logger.info("Review response submitted", review_id=review_id)
            return self._review_to_dict(row) if row else None

    async def flag_review(self, review_id: str, reason: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE reviews
                SET is_flagged = TRUE, flag_reason = $2, updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                review_id, reason,
            )
            if row:
                logger.info("Review flagged", review_id=review_id, reason=reason)
            return self._review_to_dict(row) if row else None

    # ── Member Portal ──────────────────────────────────────────────────

    async def get_reviewable_sessions(self, member_id: str) -> list[dict]:
        """Sessions the member attended but hasn't reviewed yet."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT cs.id, cs.title, cs.starts_at
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                WHERE b.member_id = $1
                    AND b.status = 'attended'
                    AND NOT EXISTS (
                        SELECT 1 FROM reviews r
                        WHERE r.member_id = $1
                        AND r.class_session_id = cs.id
                    )
                ORDER BY cs.starts_at DESC
                LIMIT 20
                """,
                member_id,
            )
            return [
                {
                    "id": str(r["id"]),
                    "title": r["title"],
                    "starts_at": r["starts_at"].isoformat() if r["starts_at"] else None,
                }
                for r in rows
            ]

    async def get_member_reviews(self, member_id: str) -> list[dict]:
        """Get reviews submitted by a specific member."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT r.*, cs.title AS session_title, cs.starts_at AS session_date
                FROM reviews r
                JOIN class_sessions cs ON cs.id = r.class_session_id
                WHERE r.member_id = $1
                ORDER BY r.created_at DESC
                """,
                member_id,
            )
            return [self._review_to_dict(r) for r in rows]

    # ── Helpers ────────────────────────────────────────────────────────

    def _review_to_dict(self, row, include_member: bool = False) -> dict:
        d = dict(row)
        for k in ("id", "member_id", "class_session_id", "responded_by"):
            if d.get(k):
                d[k] = str(d[k])
        for k in ("created_at", "updated_at", "responded_at", "session_date"):
            if d.get(k):
                d[k] = d[k].isoformat()
        if d.get("sentiment_score") is not None:
            d["sentiment_score"] = float(d["sentiment_score"])
        if include_member and d.get("first_name"):
            d["member_name"] = f"{d['first_name']} {d['last_name']}"
        return d
