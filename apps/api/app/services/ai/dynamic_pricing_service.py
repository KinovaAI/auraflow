"""AuraFlow — Dynamic Pricing Service

Rule-based pricing engine with AI-powered price suggestions.
Rules (peak hour, fill rate, day-of-week, seasonal, last-minute) apply
deterministic multipliers.  Claude generates human-reviewable suggestions
for upcoming sessions based on historical fill-rate data.
"""
import json
import uuid
from datetime import datetime, timezone, timedelta

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ai.token_tracking_service import track_ai_usage


class DynamicPricingService:

    # ── Pricing Rules CRUD ─────────────────────────────────────────────

    async def get_pricing_rules(
        self, studio_id: str, schema_override: str | None = None,
    ) -> list[dict]:
        db_kwargs = {"schema_override": schema_override} if schema_override else {}
        async with get_tenant_db(**db_kwargs) as db:
            rows = await db.fetch(
                """
                SELECT * FROM pricing_rules
                WHERE studio_id = $1
                ORDER BY created_at DESC
                """,
                studio_id,
            )
            return [self._rule_to_dict(r) for r in rows]

    async def create_pricing_rule(self, data: dict) -> dict:
        rule_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO pricing_rules (id, studio_id, name, rule_type, config, is_active)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                RETURNING *
                """,
                rule_id,
                data["studio_id"],
                data["name"],
                data["rule_type"],
                json.dumps(data.get("config", {})),
                data.get("is_active", True),
            )
            logger.info("Pricing rule created", rule_id=rule_id, rule_type=data["rule_type"])
            return self._rule_to_dict(row)

    async def update_pricing_rule(self, rule_id: str, data: dict) -> dict | None:
        async with get_tenant_db() as db:
            parts = []
            vals = []
            idx = 1

            for key in ("name", "rule_type", "is_active"):
                if key in data:
                    idx += 1
                    parts.append(f"{key} = ${idx}")
                    vals.append(data[key])

            if "config" in data:
                idx += 1
                parts.append(f"config = ${idx}::jsonb")
                vals.append(json.dumps(data["config"]))

            if not parts:
                return None

            parts.append("updated_at = NOW()")
            sql = f"UPDATE pricing_rules SET {', '.join(parts)} WHERE id = $1 RETURNING *"
            row = await db.fetchrow(sql, rule_id, *vals)
            return self._rule_to_dict(row) if row else None

    async def delete_pricing_rule(self, rule_id: str) -> bool:
        async with get_tenant_db() as db:
            result = await db.execute(
                "DELETE FROM pricing_rules WHERE id = $1", rule_id,
            )
            return "DELETE 1" in result

    # ── Dynamic Price Calculation ──────────────────────────────────────

    async def calculate_dynamic_price(self, session_id: str) -> dict:
        """Evaluate active pricing rules against a session and return suggested price."""
        async with get_tenant_db() as db:
            session = await db.fetchrow(
                """
                SELECT cs.*, s.id AS studio_id,
                    (SELECT COUNT(*) FROM bookings b
                     WHERE b.class_session_id = cs.id AND b.status = 'confirmed'
                    ) AS booked_count
                FROM class_sessions cs
                JOIN studios s ON s.id = cs.studio_id
                WHERE cs.id = $1
                """,
                session_id,
            )
            if not session:
                raise ValueError("Session not found")

            base_price = session["drop_in_price_cents"] or 0
            if base_price == 0:
                return {
                    "session_id": session_id,
                    "base_price_cents": 0,
                    "dynamic_price_cents": 0,
                    "multiplier": 1.0,
                    "rules_applied": [],
                    "note": "No drop-in price set",
                }

            rules = await db.fetch(
                "SELECT * FROM pricing_rules WHERE studio_id = $1 AND is_active = TRUE",
                str(session["studio_id"]),
            )

            compound_multiplier = 1.0
            applied_rules = []

            for rule in rules:
                config = rule["config"] if isinstance(rule["config"], dict) else json.loads(rule["config"])
                m = self._evaluate_rule(rule["rule_type"], config, session)
                if m != 1.0:
                    compound_multiplier *= m
                    applied_rules.append({
                        "rule_id": str(rule["id"]),
                        "name": rule["name"],
                        "rule_type": rule["rule_type"],
                        "multiplier": m,
                    })

            dynamic_price = round(base_price * compound_multiplier)

            return {
                "session_id": session_id,
                "base_price_cents": base_price,
                "dynamic_price_cents": dynamic_price,
                "multiplier": round(compound_multiplier, 3),
                "rules_applied": applied_rules,
            }

    def _evaluate_rule(
        self, rule_type: str, config: dict, session: dict,
    ) -> float:
        """Return multiplier for a single rule (1.0 = no change)."""
        starts_at = session["starts_at"]
        if not starts_at:
            return 1.0

        if rule_type == "peak_hour":
            peak_hours = config.get("peak_hours", [])
            if starts_at.hour in peak_hours:
                return config.get("multiplier", 1.0)

        elif rule_type == "fill_rate":
            cap = session["capacity"] or 1
            fill_pct = (session["booked_count"] / cap) * 100
            threshold = config.get("fill_threshold_pct", 80)
            if fill_pct >= threshold:
                return config.get("multiplier", 1.0)

        elif rule_type == "day_of_week":
            days = config.get("days", [])
            day_name = starts_at.strftime("%A").lower()
            if day_name in [d.lower() for d in days]:
                return config.get("multiplier", 1.0)

        elif rule_type == "seasonal":
            start = config.get("start_date")
            end = config.get("end_date")
            if start and end:
                today = datetime.now(timezone.utc).strftime("%m-%d")
                if start <= today <= end:
                    return config.get("multiplier", 1.0)

        elif rule_type == "last_minute":
            hours_before = config.get("hours_before", 2)
            delta = starts_at - datetime.now(timezone.utc)
            if delta.total_seconds() > 0 and delta.total_seconds() / 3600 <= hours_before:
                return config.get("multiplier", 1.0)

        return 1.0

    # ── AI Price Suggestions ───────────────────────────────────────────

    async def ai_suggest_prices(
        self, studio_id: str, days_ahead: int = 7,
        schema_override: str | None = None,
    ) -> list[dict]:
        """Use Claude to analyze demand and suggest prices for upcoming sessions."""
        if not settings.ANTHROPIC_API_KEY:
            return []

        db_kwargs = {"schema_override": schema_override} if schema_override else {}
        async with get_tenant_db(**db_kwargs) as db:
            # Historical fill rates by hour and day-of-week (last 30 days)
            history = await db.fetch(
                """
                SELECT
                    EXTRACT(DOW FROM cs.starts_at) AS dow,
                    EXTRACT(HOUR FROM cs.starts_at) AS hour,
                    AVG(
                        (SELECT COUNT(*) FROM bookings b
                         WHERE b.class_session_id = cs.id
                         AND b.status IN ('confirmed', 'attended'))::float
                        / GREATEST(cs.capacity, 1) * 100
                    ) AS avg_fill_pct,
                    COUNT(*) AS session_count
                FROM class_sessions cs
                WHERE cs.studio_id = $1
                    AND cs.starts_at >= NOW() - INTERVAL '30 days'
                    AND cs.starts_at < NOW()
                GROUP BY dow, hour
                ORDER BY dow, hour
                """,
                studio_id,
            )

            # Upcoming sessions needing pricing
            cutoff = datetime.now(timezone.utc) + timedelta(days=days_ahead)
            upcoming = await db.fetch(
                """
                SELECT cs.id, cs.title, cs.starts_at, cs.capacity,
                       cs.drop_in_price_cents,
                    (SELECT COUNT(*) FROM bookings b
                     WHERE b.class_session_id = cs.id AND b.status = 'confirmed'
                    ) AS booked_count
                FROM class_sessions cs
                WHERE cs.studio_id = $1
                    AND cs.starts_at > NOW()
                    AND cs.starts_at <= $2
                    AND cs.status = 'scheduled'
                    AND cs.drop_in_price_cents IS NOT NULL
                    AND cs.drop_in_price_cents > 0
                ORDER BY cs.starts_at ASC
                LIMIT 30
                """,
                studio_id, cutoff,
            )

            if not upcoming:
                return []

            # Build context for Claude
            dow_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            fill_summary = "\n".join(
                f"  {dow_names[int(r['dow'])]} {int(r['hour']):02d}:00 — "
                f"avg fill {r['avg_fill_pct']:.0f}% ({r['session_count']} sessions)"
                for r in history
            )

            sessions_summary = "\n".join(
                f"  {r['id']} | {r['title']} | {r['starts_at'].strftime('%a %b %d %I:%M%p')} | "
                f"${r['drop_in_price_cents']/100:.2f} | {r['booked_count']}/{r['capacity']} booked"
                for r in upcoming
            )

            import anthropic
            client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

            try:
                message = await client.messages.create(
                    model=settings.ANTHROPIC_MODEL_FAST,
                    max_tokens=2048,
                    system=(
                        "You are a revenue optimization analyst for a fitness studio. "
                        "Analyze historical fill rates and suggest optimal drop-in prices. "
                        "Higher fill-rate timeslots can support higher prices; lower fill-rate "
                        "timeslots benefit from discounts to attract more bookings. "
                        "Return ONLY a JSON array (no markdown fences) with objects: "
                        '{"session_id": "uuid", "suggested_price_cents": int, "reason": "short explanation"}'
                    ),
                    messages=[{
                        "role": "user",
                        "content": (
                            f"Historical fill rates (last 30 days):\n{fill_summary}\n\n"
                            f"Upcoming sessions:\n{sessions_summary}\n\n"
                            "Suggest optimal drop-in prices for each session."
                        ),
                    }],
                )
                await track_ai_usage(
                    service_name="dynamic_pricing_service",
                    function_name="ai_suggest_prices",
                    model=settings.ANTHROPIC_MODEL_FAST,
                    input_tokens=message.usage.input_tokens,
                    output_tokens=message.usage.output_tokens,
                )
                raw = message.content[0].text.strip()
                # Parse JSON
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                suggestions = json.loads(raw)
            except Exception as e:
                logger.error("AI pricing suggestion failed", error=str(e))
                return []

            # Save suggestions to price_adjustments_log
            saved = []
            session_map = {str(r["id"]): r for r in upcoming}
            for s in suggestions:
                sid = s.get("session_id")
                if sid not in session_map:
                    continue
                original = session_map[sid]["drop_in_price_cents"]
                adj_id = str(uuid.uuid4())
                row = await db.fetchrow(
                    """
                    INSERT INTO price_adjustments_log
                        (id, class_session_id, original_price_cents,
                         adjusted_price_cents, reason, ai_explanation, status)
                    VALUES ($1, $2, $3, $4, $5, $6, 'suggested')
                    RETURNING *
                    """,
                    adj_id, sid, original,
                    s.get("suggested_price_cents", original),
                    s.get("reason", ""),
                    s.get("reason", ""),
                )
                if row:
                    d = self._adjustment_to_dict(row)
                    d["session_title"] = session_map[sid]["title"]
                    d["starts_at"] = session_map[sid]["starts_at"].isoformat()
                    saved.append(d)

            logger.info(
                "AI pricing suggestions generated",
                studio_id=studio_id,
                count=len(saved),
            )
            return saved

    async def get_suggestions(
        self, studio_id: str, status: str = "suggested",
    ) -> list[dict]:
        """List price suggestions for sessions belonging to a studio."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT pal.*, cs.title AS session_title, cs.starts_at
                FROM price_adjustments_log pal
                JOIN class_sessions cs ON cs.id = pal.class_session_id
                JOIN studios s ON s.id = cs.studio_id
                WHERE s.id = $1 AND pal.status = $2
                ORDER BY pal.created_at DESC
                LIMIT 50
                """,
                studio_id, status,
            )
            results = []
            for r in rows:
                d = self._adjustment_to_dict(r)
                d["session_title"] = r["session_title"]
                d["starts_at"] = r["starts_at"].isoformat() if r["starts_at"] else None
                results.append(d)
            return results

    async def approve_price_suggestion(
        self, adjustment_id: str, approved_by: str,
    ) -> dict | None:
        """Approve a suggestion and apply it to the session."""
        async with get_tenant_db() as db:
            adj = await db.fetchrow(
                "SELECT * FROM price_adjustments_log WHERE id = $1 AND status = 'suggested'",
                adjustment_id,
            )
            if not adj:
                return None

            # Update adjustment status
            await db.execute(
                "UPDATE price_adjustments_log SET status = 'approved' WHERE id = $1",
                adjustment_id,
            )
            # Apply to session
            await db.execute(
                "UPDATE class_sessions SET dynamic_price_cents = $1 WHERE id = $2",
                adj["adjusted_price_cents"], str(adj["class_session_id"]),
            )
            logger.info(
                "Price suggestion approved",
                adjustment_id=adjustment_id,
                session_id=str(adj["class_session_id"]),
                price=adj["adjusted_price_cents"],
            )
            updated = await db.fetchrow(
                "SELECT * FROM price_adjustments_log WHERE id = $1", adjustment_id,
            )
            return self._adjustment_to_dict(updated) if updated else None

    async def reject_price_suggestion(self, adjustment_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE price_adjustments_log SET status = 'rejected'
                WHERE id = $1 AND status = 'suggested'
                RETURNING *
                """,
                adjustment_id,
            )
            return self._adjustment_to_dict(row) if row else None

    async def get_price_history(self, session_id: str) -> list[dict]:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT * FROM price_adjustments_log
                WHERE class_session_id = $1
                ORDER BY created_at DESC
                """,
                session_id,
            )
            return [self._adjustment_to_dict(r) for r in rows]

    # ── Helpers ────────────────────────────────────────────────────────

    def _rule_to_dict(self, row) -> dict:
        d = dict(row)
        for k in ("id", "studio_id"):
            if d.get(k):
                d[k] = str(d[k])
        for k in ("created_at", "updated_at"):
            if d.get(k):
                d[k] = d[k].isoformat()
        # Ensure config is a dict, not a JSON string
        if isinstance(d.get("config"), str):
            try:
                d["config"] = json.loads(d["config"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    def _adjustment_to_dict(self, row) -> dict:
        d = dict(row)
        for k in ("id", "class_session_id"):
            if d.get(k):
                d[k] = str(d[k])
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        # Ensure JSONB fields are dicts/lists
        for k in ("rules_applied",):
            if isinstance(d.get(k), str):
                try:
                    d[k] = json.loads(d[k])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d
