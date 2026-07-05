"""AuraFlow — AI Meta Ads Controller

Claude-powered autonomous Facebook/Instagram Ads manager. Uses multi-turn
tool-use (same pattern as ai_ads_controller.py) to research, create, optimize,
and manage Meta Ads campaigns for fitness studios.

Key differences from Google Ads controller:
- Interest-based targeting instead of keywords
- Campaign → Ad Set → Ad → Creative hierarchy
- Frequency monitoring (pause at >3.0)
- 50 conversions to exit learning phase (vs 30 for Google)
"""
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ads.meta_ads_service import MetaAdsService

_meta = MetaAdsService()


# ── Tool Definitions for Claude ──────────────────────────────────────────────

AI_META_ADS_TOOLS = [
    # Studio context (shared with Google Ads — read-only)
    {
        "name": "get_studio_info",
        "description": "Get studio name, location, website, and basic info for creating relevant ads.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_class_types",
        "description": "Get all class types with descriptions, pricing, and popularity stats.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_membership_types",
        "description": "Get all membership/package options with pricing tiers.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_recent_attendance",
        "description": "Get attendance stats for the last 30 days — which classes are popular vs underperforming.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_meta_ads_config",
        "description": "Get the owner's Meta Ads preferences: max budget, location targeting, age range, genders, interests, pixel ID, page ID.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # Facebook Ads execution
    {
        "name": "create_campaign",
        "description": "Create a new Meta Ads campaign.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Campaign name"},
                "objective": {
                    "type": "string",
                    "enum": ["OUTCOME_LEADS", "OUTCOME_TRAFFIC", "OUTCOME_AWARENESS", "OUTCOME_ENGAGEMENT", "OUTCOME_SALES"],
                    "description": "Campaign objective (ODAX)",
                },
                "daily_budget_cents": {"type": "integer", "description": "Daily budget in cents"},
            },
            "required": ["name", "objective", "daily_budget_cents"],
        },
    },
    {
        "name": "create_ad_set",
        "description": "Create an ad set with targeting within a campaign. Includes interest, age, gender, and geo targeting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Meta campaign ID"},
                "name": {"type": "string", "description": "Ad set name"},
                "daily_budget_cents": {"type": "integer", "description": "Daily budget in cents"},
                "interests": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}}, "required": ["id", "name"]},
                    "description": "Interest targeting (from search_interests)",
                },
                "age_min": {"type": "integer", "description": "Minimum age (default 18)", "default": 18},
                "age_max": {"type": "integer", "description": "Maximum age (default 65)", "default": 65},
                "genders": {
                    "type": "array", "items": {"type": "integer"},
                    "description": "Gender targeting: 1=male, 2=female, empty=all",
                },
            },
            "required": ["campaign_id", "name", "daily_budget_cents"],
        },
    },
    {
        "name": "create_ad_creative",
        "description": "Create an ad creative with headline, body text, link, and CTA.",
        "input_schema": {
            "type": "object",
            "properties": {
                "headline": {"type": "string", "description": "Ad headline (max 40 chars)"},
                "body_text": {"type": "string", "description": "Ad body/primary text (max 125 chars for best performance)"},
                "link_url": {"type": "string", "description": "Landing page URL"},
                "call_to_action": {
                    "type": "string",
                    "enum": ["LEARN_MORE", "SIGN_UP", "BOOK_NOW", "GET_OFFER", "CONTACT_US"],
                    "description": "CTA button type",
                },
                "description": {"type": "string", "description": "Optional description/link description"},
            },
            "required": ["headline", "body_text", "link_url", "call_to_action"],
        },
    },
    {
        "name": "create_ad",
        "description": "Create an ad linking an ad set to a creative.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ad_set_id": {"type": "string"},
                "creative_id": {"type": "string"},
                "name": {"type": "string", "description": "Ad name"},
            },
            "required": ["ad_set_id", "creative_id", "name"],
        },
    },
    {
        "name": "search_interests",
        "description": "Search for Facebook interest targeting options by keyword. Returns interest IDs and audience sizes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term (e.g., 'yoga', 'fitness', 'pilates')"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "update_ad_set_targeting",
        "description": "Modify targeting for an existing ad set (interests, age, gender, geo).",
        "input_schema": {
            "type": "object",
            "properties": {
                "ad_set_id": {"type": "string"},
                "targeting": {"type": "object", "description": "Updated targeting spec"},
            },
            "required": ["ad_set_id", "targeting"],
        },
    },
    {
        "name": "update_ad_set_budget",
        "description": "Change the daily budget of an ad set (in cents).",
        "input_schema": {
            "type": "object",
            "properties": {
                "ad_set_id": {"type": "string"},
                "daily_budget_cents": {"type": "integer"},
            },
            "required": ["ad_set_id", "daily_budget_cents"],
        },
    },
    {
        "name": "adjust_campaign_budget",
        "description": "Adjust the overall campaign budget allocation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "daily_budget_cents": {"type": "integer"},
            },
            "required": ["campaign_id", "daily_budget_cents"],
        },
    },
    {
        "name": "pause_campaign",
        "description": "Pause a campaign.",
        "input_schema": {
            "type": "object",
            "properties": {"campaign_id": {"type": "string"}},
            "required": ["campaign_id"],
        },
    },
    {
        "name": "enable_campaign",
        "description": "Enable/unpause a campaign.",
        "input_schema": {
            "type": "object",
            "properties": {"campaign_id": {"type": "string"}},
            "required": ["campaign_id"],
        },
    },
    {
        "name": "create_custom_audience",
        "description": "Create a custom audience from a list of member emails (SHA256 hashed automatically).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Audience name"},
                "emails": {"type": "array", "items": {"type": "string"}, "description": "Email addresses"},
            },
            "required": ["name", "emails"],
        },
    },
    {
        "name": "create_lookalike_audience",
        "description": "Create a lookalike audience from a source custom audience.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_audience_id": {"type": "string"},
                "ratio": {"type": "number", "description": "Lookalike ratio 0.01-0.10 (1-10%)", "default": 0.01},
            },
            "required": ["source_audience_id"],
        },
    },
    # Analytics
    {
        "name": "get_campaign_metrics",
        "description": "Get campaign performance metrics (impressions, reach, clicks, conversions, spend, frequency, ROAS) for a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "get_ad_set_metrics",
        "description": "Get ad set level performance metrics for optimization decisions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string"},
                "date_to": {"type": "string"},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "get_monthly_spend_summary",
        "description": "Get total spend vs budget cap for the current month.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # Safety
    {
        "name": "request_human_approval",
        "description": "Request human approval for a significant change. Use when cost exceeds approval threshold or action is risky.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action_type": {"type": "string"},
                "description": {"type": "string"},
                "reasoning": {"type": "string"},
                "changes": {"type": "object"},
            },
            "required": ["action_type", "description", "reasoning", "changes"],
        },
    },
    {
        "name": "log_action",
        "description": "Log an action to the audit trail. Call this for EVERY decision you make.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action_type": {"type": "string", "description": "e.g. create_campaign, adjust_budget, pause_ad_set, etc."},
                "description": {"type": "string", "description": "What was done"},
                "reasoning": {"type": "string", "description": "Why this decision was made"},
                "changes": {"type": "object", "description": "The specific changes made"},
            },
            "required": ["action_type", "description", "reasoning", "changes"],
        },
    },
]

AI_META_ADS_SYSTEM = """You are the AI Meta Ads Controller for a yoga/fitness studio. You autonomously manage their
Facebook & Instagram Ads to attract new members and maximize ROAS (Return on Ad Spend).

## Your Mission
Generate high-quality leads (trial sign-ups, membership purchases, class bookings) through
Facebook & Instagram Ads while staying within the studio's budget and delivering positive ROI.

## Critical Rules — NEVER violate these
1. NEVER exceed the monthly budget cap. Check get_monthly_spend_summary before making budget changes.
2. Changes that increase spending above the approval_threshold_cents MUST go through request_human_approval.
3. Call log_action for EVERY decision you make — full transparency is required.
4. Start conservative: low budgets, broad interests, test multiple creatives.
5. Only switch to value-based optimization after 50+ conversions (Meta's learning phase threshold).
6. Monitor FREQUENCY — pause ad sets with frequency > 3.0 (ad fatigue signal).

## Progressive Strategy
- **Week 1-2 (Learning)**: OUTCOME_LEADS objective, Lowest Cost bidding, 40% of monthly budget.
  Use 2-3 ad sets with different interest targeting. 3-5 ad creatives per ad set.
  Focus on broad audiences to gather data.
- **Week 3-4 (Optimizing)**: If 25+ conversions, increase to 70% budget.
  Pause underperforming ad sets (CTR < 0.8%, frequency > 3.0).
  Create lookalike audiences from converters. Refine targeting.
- **Month 2+ (Scaling)**: If 50+ conversions, switch to OUTCOME_SALES with value optimization.
  Full budget. Test lookalike audiences. Consider scaling winners.

## Ad Creative Guidelines for Fitness Studios
- Headlines: short (40 chars max), action-oriented — "Start Your Yoga Journey", "First Class Free"
- Body text: ~125 chars for best performance, highlight unique value props
- CTAs: BOOK_NOW for classes, SIGN_UP for trials, LEARN_MORE for awareness
- Emphasize: community, experienced instructors, welcoming atmosphere, results
- Include offers: "First Class Free", "Trial Week", "$X/month intro offer"
- Use location callouts: "Your [City] Yoga Studio", "[Neighborhood] Fitness"

## Default Interest Targeting (start with these)
- Yoga, Pilates, Fitness and wellness, Meditation, Barre, HIIT, Wellness, Gym, CrossFit
- Also search for interests specific to the studio's class types

## Optimization Cycle (run 4x daily)
1. Check monthly spend vs cap
2. Review campaign performance (last 7 days)
3. Review ad set performance — pause ad sets with frequency > 3.0 or CTR < 0.5% after 1000+ impressions
4. Check for audience fatigue — if reach is flattening, expand targeting
5. Adjust budgets: increase on winners, decrease on underperformers
6. Log all decisions with clear reasoning

Always think like a social media marketing expert who specializes in local fitness studio advertising.
"""


class AIMetaAdsController:
    """Claude-powered autonomous Meta Ads controller."""

    def _is_configured(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY and settings.META_APP_ID)

    # ── Multi-turn Claude with Tools ──────────────────────────────────────────

    async def _call_claude_with_tools(
        self,
        messages: list[dict],
        system: str,
        org_id: str,
        max_turns: int = 15,
    ) -> dict:
        """Multi-turn Claude API call with tool-use for ad management."""
        if not self._is_configured():
            return {
                "summary": "AI Meta Ads Controller not configured — missing ANTHROPIC_API_KEY or META_APP_ID",
                "actions": [],
                "completed": False,
            }

        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        actions_taken = []

        for turn in range(max_turns):
            try:
                response = await client.messages.create(
                    model=settings.ANTHROPIC_MODEL,
                    max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                    system=system,
                    tools=AI_META_ADS_TOOLS,
                    messages=messages,
                )
            except Exception as e:
                logger.error("AI Meta Ads Controller Claude call failed", error=str(e))
                return {
                    "summary": f"AI error: {str(e)}",
                    "actions": actions_taken,
                    "completed": False,
                }

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_result = await self._execute_tool(
                            block.name, block.input, org_id
                        )
                        actions_taken.append({
                            "tool": block.name,
                            "input": block.input,
                            "result_preview": str(tool_result)[:300],
                        })
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(tool_result, default=str),
                        })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                # Final response
                text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text

                return {
                    "summary": text,
                    "actions": actions_taken,
                    "completed": True,
                }

        return {
            "summary": "Max turns exceeded — optimization cycle ended early",
            "actions": actions_taken,
            "completed": False,
        }

    # ── Tool Execution ────────────────────────────────────────────────────────

    async def _execute_tool(self, tool_name: str, tool_input: dict, org_id: str) -> dict:
        """Execute a tool call and return the result."""
        try:
            # Studio context (shared implementations)
            if tool_name == "get_studio_info":
                return await self._tool_get_studio_info(org_id)
            elif tool_name == "get_class_types":
                return await self._tool_get_class_types()
            elif tool_name == "get_membership_types":
                return await self._tool_get_membership_types()
            elif tool_name == "get_recent_attendance":
                return await self._tool_get_recent_attendance()
            elif tool_name == "get_meta_ads_config":
                config = await _meta.get_config(org_id)
                return config or {"error": "No config found — run setup first"}

            # Facebook Ads execution
            elif tool_name == "create_campaign":
                return await _meta.create_campaign(
                    org_id, tool_input["name"],
                    tool_input["objective"],
                    tool_input["daily_budget_cents"],
                )
            elif tool_name == "create_ad_set":
                config = await _meta.get_config(org_id)
                geo_lat = config.get("target_latitude") if config else None
                geo_lng = config.get("target_longitude") if config else None
                geo_radius = config.get("target_radius_miles", 15) if config else 15

                return await _meta.create_ad_set(
                    org_id, tool_input["campaign_id"], tool_input["name"],
                    tool_input["daily_budget_cents"],
                    interests=tool_input.get("interests"),
                    age_min=tool_input.get("age_min", 18),
                    age_max=tool_input.get("age_max", 65),
                    genders=tool_input.get("genders"),
                    geo_latitude=geo_lat,
                    geo_longitude=geo_lng,
                    geo_radius_miles=geo_radius,
                )
            elif tool_name == "create_ad_creative":
                config = await _meta.get_config(org_id)
                page_id = config.get("default_page_id", "") if config else ""
                if not page_id:
                    return {"error": "No Facebook Page ID configured — set default_page_id in config"}
                return await _meta.create_ad_creative(
                    org_id, page_id,
                    tool_input["headline"], tool_input["body_text"],
                    tool_input["link_url"], tool_input["call_to_action"],
                    description=tool_input.get("description"),
                )
            elif tool_name == "create_ad":
                return await _meta.create_ad(
                    org_id, tool_input["ad_set_id"],
                    tool_input["creative_id"], tool_input["name"],
                )
            elif tool_name == "search_interests":
                return {"interests": await _meta.search_interests(org_id, tool_input["query"])}
            elif tool_name == "update_ad_set_targeting":
                return await _meta.update_ad_set_targeting(
                    org_id, tool_input["ad_set_id"], tool_input["targeting"]
                )
            elif tool_name == "update_ad_set_budget":
                return await _meta.update_ad_set_budget(
                    org_id, tool_input["ad_set_id"], tool_input["daily_budget_cents"]
                )
            elif tool_name == "adjust_campaign_budget":
                # For Meta, campaign budget is managed at the ad set level
                # Log the intent and note that ad set budgets should be adjusted individually
                return {"note": "Meta uses ad set level budgets. Adjust individual ad set budgets instead."}
            elif tool_name == "pause_campaign":
                return await _meta.update_campaign_status(org_id, tool_input["campaign_id"], "PAUSED")
            elif tool_name == "enable_campaign":
                return await _meta.update_campaign_status(org_id, tool_input["campaign_id"], "ACTIVE")
            elif tool_name == "create_custom_audience":
                return await _meta.create_custom_audience(
                    org_id, tool_input["name"], tool_input["emails"]
                )
            elif tool_name == "create_lookalike_audience":
                return await _meta.create_lookalike_audience(
                    org_id, tool_input["source_audience_id"],
                    tool_input.get("ratio", 0.01),
                )

            # Analytics
            elif tool_name == "get_campaign_metrics":
                return {"metrics": await _meta.get_campaign_performance(
                    org_id, tool_input["date_from"], tool_input["date_to"]
                )}
            elif tool_name == "get_ad_set_metrics":
                return {"metrics": await _meta.get_ad_set_performance(
                    org_id, tool_input["date_from"], tool_input["date_to"]
                )}
            elif tool_name == "get_monthly_spend_summary":
                return await _meta.check_budget_remaining(org_id)

            # Safety
            elif tool_name == "request_human_approval":
                action_id = await _meta.log_ai_action(
                    tool_input["action_type"], tool_input["description"],
                    tool_input["reasoning"], tool_input["changes"],
                    requires_approval=True,
                )
                return {"action_id": action_id, "status": "pending_approval"}
            elif tool_name == "log_action":
                action_id = await _meta.log_ai_action(
                    tool_input["action_type"], tool_input["description"],
                    tool_input["reasoning"], tool_input["changes"],
                    requires_approval=False,
                )
                return {"action_id": action_id, "logged": True}

            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error("AI Meta Ads tool execution failed", tool=tool_name, error=str(e))
            return {"error": str(e)}

    # ── Studio Context Tools (shared with Google Ads) ────────────────────────

    async def _tool_get_studio_info(self, org_id: str) -> dict:
        """Get studio information for ad context."""
        from app.db.session import get_global_db
        async with get_global_db() as db:
            org = await db.fetchrow(
                """
                SELECT name, slug, website_url, phone, address_line1, city, state, zip_code
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
        if not org:
            return {"error": "Organization not found"}

        async with get_tenant_db() as db:
            studio = await db.fetchrow(
                "SELECT name, description, address, phone, website_url FROM studios LIMIT 1"
            )

        info = {
            "org_name": org["name"],
            "website": org.get("website_url") or (studio["website_url"] if studio else None),
            "phone": org.get("phone") or (studio["phone"] if studio else None),
            "address": org.get("address_line1"),
            "city": org.get("city"),
            "state": org.get("state"),
            "zip_code": org.get("zip_code"),
        }
        if studio:
            info["studio_name"] = studio["name"]
            info["studio_description"] = studio.get("description")
        return info

    async def _tool_get_class_types(self) -> dict:
        """Get class types for ad creative/targeting generation."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT ct.name, ct.description, ct.duration_minutes, ct.difficulty_level,
                       ct.drop_in_price_cents,
                       (SELECT COUNT(*) FROM class_sessions cs
                        WHERE cs.class_type_id = ct.id AND cs.starts_at > NOW() - INTERVAL '30 days') AS recent_sessions
                FROM class_types ct
                WHERE ct.is_active = TRUE
                ORDER BY recent_sessions DESC
                """
            )
        return {"class_types": [
            {
                "name": r["name"],
                "description": r.get("description", ""),
                "duration_minutes": r["duration_minutes"],
                "difficulty": r.get("difficulty_level"),
                "drop_in_price": f"${r['drop_in_price_cents'] / 100:.0f}" if r.get("drop_in_price_cents") else None,
                "popularity": "high" if r["recent_sessions"] > 10 else "medium" if r["recent_sessions"] > 3 else "low",
            }
            for r in rows
        ]}

    async def _tool_get_membership_types(self) -> dict:
        """Get membership types for ad copy."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT name, description, type, price_cents, billing_interval,
                       class_count, is_active
                FROM membership_types
                WHERE is_active = TRUE
                ORDER BY price_cents ASC
                """
            )
        return {"memberships": [
            {
                "name": r["name"],
                "description": r.get("description", ""),
                "type": r["type"],
                "price": f"${r['price_cents'] / 100:.0f}",
                "billing": r.get("billing_interval", "monthly"),
                "class_count": r.get("class_count"),
            }
            for r in rows
        ]}

    async def _tool_get_recent_attendance(self) -> dict:
        """Get attendance data for optimization."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT ct.name AS class_type,
                       COUNT(b.id) AS bookings,
                       COUNT(CASE WHEN b.status = 'attended' THEN 1 END) AS attended,
                       COUNT(CASE WHEN b.status = 'no_show' THEN 1 END) AS no_shows,
                       AVG(cs.capacity) AS avg_capacity
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                WHERE cs.starts_at >= NOW() - INTERVAL '30 days'
                GROUP BY ct.name
                ORDER BY bookings DESC
                """
            )
        return {"attendance": [
            {
                "class_type": r["class_type"],
                "total_bookings": r["bookings"],
                "attended": r["attended"],
                "no_shows": r["no_shows"],
                "avg_capacity": round(float(r["avg_capacity"] or 0)),
                "fill_rate": f"{r['attended'] / r['avg_capacity'] * 100:.0f}%" if r["avg_capacity"] else "N/A",
            }
            for r in rows
        ]}

    # ── Public Methods ────────────────────────────────────────────────────────

    async def initial_campaign_setup(self, org_id: str) -> dict:
        """AI creates the full initial campaign structure when Meta Ads is first enabled."""
        messages = [{"role": "user", "content": """
You are setting up Facebook & Instagram Ads for this fitness studio for the first time. Your task:

1. First, get the studio info, class types, membership types, and the meta ads config
2. Search for relevant interests (yoga, fitness, pilates, etc. based on the studio's classes)
3. Based on the studio's classes, location, and pricing, create an optimal campaign structure:
   - 1 Lead Generation campaign (OUTCOME_LEADS) with appropriate daily budget
   - 2-3 ad sets organized by theme (e.g., by class type, by audience age/interest)
   - Each ad set with relevant interest targeting using the IDs from search_interests
   - 3-5 ad creatives with compelling copy (headlines + body text + CTAs)
   - Create ads linking the ad sets to creatives
4. IMPORTANT: Leave the campaign PAUSED — the owner will review and enable it
5. Log every action you take with clear reasoning

Be strategic: focus on the studio's strongest offerings and local market.
Think about what imagery and messaging would resonate on Facebook/Instagram.
"""}]

        result = await self._call_claude_with_tools(
            messages=messages,
            system=AI_META_ADS_SYSTEM,
            org_id=org_id,
            max_turns=20,
        )

        logger.info("AI Meta initial campaign setup complete", org_id=org_id, actions=len(result["actions"]))
        return result

    async def run_optimization_cycle(self, org_id: str) -> dict:
        """AI analyzes performance and makes optimization adjustments."""
        now = datetime.now(timezone.utc)
        date_to = now.strftime("%Y-%m-%d")
        date_from = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        messages = [{"role": "user", "content": f"""
Run an optimization cycle for this studio's Meta Ads. Today is {date_to}.

Follow this process:
1. Check monthly spend vs budget cap
2. If over 95% of budget, pause campaigns and log the reason
3. Get campaign metrics for the last 7 days ({date_from} to {date_to})
4. Get ad set metrics — identify underperformers:
   - Frequency > 3.0 → pause (audience fatigue)
   - CTR < 0.5% after 1000+ impressions → pause
   - Cost per lead too high relative to conversion value
5. Make data-driven adjustments:
   - Pause fatigued ad sets (frequency > 3.0)
   - Increase budget on high-performing ad sets (low cost per lead, good CTR)
   - Consider creating new ad sets with refined targeting
   - Consider lookalike audiences if you have enough converters
6. Log every decision with your reasoning

Be conservative with changes. Only make adjustments backed by sufficient data.
Remember: Meta needs ~50 conversions to exit the learning phase — avoid making too many
changes during learning as it resets the phase.
"""}]

        result = await self._call_claude_with_tools(
            messages=messages,
            system=AI_META_ADS_SYSTEM,
            org_id=org_id,
            max_turns=15,
        )

        logger.info("AI Meta optimization cycle complete", org_id=org_id, actions=len(result["actions"]))
        return result

    async def generate_performance_report(self, org_id: str, days: int = 30) -> dict:
        """AI generates a human-readable performance report."""
        now = datetime.now(timezone.utc)
        date_to = now.strftime("%Y-%m-%d")
        date_from = (now - timedelta(days=days)).strftime("%Y-%m-%d")

        messages = [{"role": "user", "content": f"""
Generate a performance report for the last {days} days ({date_from} to {date_to}).

1. Get campaign metrics for the period
2. Get ad set metrics for top performers
3. Get monthly spend summary
4. Summarize in a clear, non-technical format the studio owner can understand:
   - Total spend, reach, clicks, conversions, cost per lead
   - Best performing ad sets and creatives
   - Audience insights (which interests/demographics work best)
   - Ad fatigue status (frequency trends)
   - What's working and what's not
   - Recommendations for the coming period
"""}]

        result = await self._call_claude_with_tools(
            messages=messages,
            system=AI_META_ADS_SYSTEM,
            org_id=org_id,
            max_turns=10,
        )
        return result
