"""AuraFlow — AI Ads Controller

Claude-powered autonomous Google Ads manager. Uses multi-turn tool-use
(same pattern as ai_manager_service.py) to research, create, optimize,
and manage Google Ads campaigns for fitness studios.

The AI operates within strict safety rails:
- Never exceeds monthly budget cap
- Changes above approval threshold require human approval
- Starts conservative and ramps up gradually
- Full audit trail for every decision
"""
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ads.google_ads_service import GoogleAdsService

_ads = GoogleAdsService()


# ── Tool Definitions for Claude ──────────────────────────────────────────────

AI_ADS_TOOLS = [
    # Studio context (read-only)
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
        "name": "get_ads_config",
        "description": "Get the owner's Google Ads preferences: max budget, location targeting, class focus, brand voice, negative keywords.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # Google Ads execution
    {
        "name": "create_search_campaign",
        "description": "Create a new Google Ads Search campaign with location targeting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Campaign name"},
                "daily_budget_cents": {"type": "integer", "description": "Daily budget in cents"},
            },
            "required": ["name", "daily_budget_cents"],
        },
    },
    {
        "name": "create_ad_group",
        "description": "Create an ad group within a campaign for organizing ads and keywords.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Google campaign ID"},
                "name": {"type": "string", "description": "Ad group name"},
                "cpc_bid_cents": {"type": "integer", "description": "Max CPC bid in cents (default 200)", "default": 200},
            },
            "required": ["campaign_id", "name"],
        },
    },
    {
        "name": "create_responsive_search_ad",
        "description": "Create a responsive search ad with multiple headline and description variations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ad_group_resource": {"type": "string", "description": "Ad group resource name"},
                "headlines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-15 headline variations (max 30 chars each)",
                },
                "descriptions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-4 description variations (max 90 chars each)",
                },
                "final_url": {"type": "string", "description": "Landing page URL"},
            },
            "required": ["ad_group_resource", "headlines", "descriptions", "final_url"],
        },
    },
    {
        "name": "add_keywords",
        "description": "Add keywords to an ad group. Each keyword should have text and match_type (BROAD, PHRASE, or EXACT).",
        "input_schema": {
            "type": "object",
            "properties": {
                "ad_group_resource": {"type": "string"},
                "keywords": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "match_type": {"type": "string", "enum": ["BROAD", "PHRASE", "EXACT"]},
                        },
                        "required": ["text"],
                    },
                },
            },
            "required": ["ad_group_resource", "keywords"],
        },
    },
    {
        "name": "remove_keywords",
        "description": "Remove underperforming keywords by their resource names.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword_resources": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["keyword_resources"],
        },
    },
    {
        "name": "get_keyword_suggestions",
        "description": "Get keyword ideas from Google Ads Keyword Planner based on seed keywords.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seed_keywords": {"type": "array", "items": {"type": "string"}},
                "url": {"type": "string", "description": "Optional URL for content-based suggestions"},
            },
            "required": ["seed_keywords"],
        },
    },
    {
        "name": "adjust_campaign_budget",
        "description": "Change the daily budget of a campaign (in cents).",
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
        "name": "adjust_bidding_strategy",
        "description": "Change the bidding strategy of a campaign.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "strategy": {
                    "type": "string",
                    "enum": ["MAXIMIZE_CLICKS", "MAXIMIZE_CONVERSIONS", "TARGET_ROAS"],
                },
                "target_roas": {"type": "number", "description": "Required if strategy is TARGET_ROAS"},
            },
            "required": ["campaign_id", "strategy"],
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
    # Analytics
    {
        "name": "get_campaign_metrics",
        "description": "Get campaign performance metrics (impressions, clicks, conversions, cost, ROAS) for a date range.",
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
        "name": "get_keyword_metrics",
        "description": "Get keyword-level performance metrics for optimization.",
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
        "name": "get_search_terms_report",
        "description": "See what users actually searched to find the ads — useful for adding negatives.",
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
        "description": "Request human approval for a significant change. Use this when the change cost exceeds the approval threshold or is risky.",
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
                "action_type": {"type": "string", "description": "e.g. create_campaign, adjust_budget, add_keywords, pause_ad, etc."},
                "description": {"type": "string", "description": "What was done"},
                "reasoning": {"type": "string", "description": "Why this decision was made"},
                "changes": {"type": "object", "description": "The specific changes made"},
            },
            "required": ["action_type", "description", "reasoning", "changes"],
        },
    },
]

AI_ADS_SYSTEM = """You are the AI Ads Controller for a yoga/fitness studio. You autonomously manage their Google Ads
to attract new members and maximize ROAS (Return on Ad Spend).

## Your Mission
Generate high-quality leads (trial sign-ups, membership purchases, class bookings) through
Google Ads while staying within the studio's budget and delivering positive ROI.

## Critical Rules — NEVER violate these
1. NEVER exceed the monthly budget cap. Check get_monthly_spend_summary before making budget changes.
2. Changes that increase spending above the approval_threshold_cents MUST go through request_human_approval.
3. Call log_action for EVERY decision you make — full transparency is required.
4. Start conservative: low bids, broad keywords, small budget allocation.
5. Only use TARGET_ROAS bidding after 30+ conversions have been recorded.
6. Monitor search terms and aggressively add negative keywords for irrelevant traffic.

## Progressive Strategy
- **Week 1-2 (Learning)**: Maximize Clicks, use 40% of monthly budget divided by days remaining.
  Focus on broad keywords to gather data. 3+ ad groups per campaign.
- **Week 3-4 (Optimizing)**: If 15+ conversions, switch to Maximize Conversions. Increase to 70% budget.
  Prune underperforming keywords (CTR < 1% after 100+ impressions). Refine ad copy.
- **Month 2+ (Scaling)**: If 30+ conversions, switch to Target ROAS. Full budget. Consider Performance Max.

## Ad Copy Guidelines for Fitness Studios
- Highlight unique class types (yoga, HIIT, Pilates, etc.)
- Emphasize community, experienced instructors, welcoming atmosphere
- Include offers: "First Class Free", "Trial Week", introductory pricing
- Use location-specific keywords: "yoga near [city]", "[city] fitness classes"
- Use the studio's brand voice if provided

## Negative Keywords to Always Add
- "free" (unless offering a free trial), "jobs", "hiring", "salary", "certification",
  "training" (if not relevant), "youtube", "video", "online" (if studio-only)

## Optimization Cycle (run 4x daily)
1. Check monthly spend vs cap
2. Review campaign performance (last 7 days)
3. Review keyword performance — pause keywords with CTR < 0.5% and 200+ impressions
4. Review search terms — add irrelevant terms as negatives
5. Adjust bids and budgets based on performance
6. Log all decisions with clear reasoning

Always think like a marketing expert who specializes in local fitness studio advertising.
"""


class AIAdsController:
    """Claude-powered autonomous Google Ads controller."""

    def _is_configured(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY and settings.GOOGLE_ADS_DEVELOPER_TOKEN)

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
                "summary": "AI Ads Controller not configured — missing ANTHROPIC_API_KEY or GOOGLE_ADS_DEVELOPER_TOKEN",
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
                    tools=AI_ADS_TOOLS,
                    messages=messages,
                )
            except Exception as e:
                logger.error("AI Ads Controller Claude call failed", error=str(e))
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
            # Studio context
            if tool_name == "get_studio_info":
                return await self._tool_get_studio_info(org_id)
            elif tool_name == "get_class_types":
                return await self._tool_get_class_types()
            elif tool_name == "get_membership_types":
                return await self._tool_get_membership_types()
            elif tool_name == "get_recent_attendance":
                return await self._tool_get_recent_attendance()
            elif tool_name == "get_ads_config":
                config = await _ads.get_config(org_id)
                return config or {"error": "No config found — run setup first"}

            # Google Ads execution
            elif tool_name == "create_search_campaign":
                config = await _ads.get_config(org_id)
                proximity = None
                if config and config.get("target_latitude") and config.get("target_longitude"):
                    proximity = {
                        "latitude": config["target_latitude"],
                        "longitude": config["target_longitude"],
                        "radius_miles": config.get("target_radius_miles", 15),
                    }
                return await _ads.create_search_campaign(
                    org_id, tool_input["name"],
                    tool_input["daily_budget_cents"],
                    proximity=proximity,
                )
            elif tool_name == "create_ad_group":
                return await _ads.create_ad_group(
                    org_id, tool_input["campaign_id"], tool_input["name"],
                    cpc_bid_micros=tool_input.get("cpc_bid_cents", 200) * 10000,
                )
            elif tool_name == "create_responsive_search_ad":
                return await _ads.create_responsive_search_ad(
                    org_id, tool_input["ad_group_resource"],
                    tool_input["headlines"], tool_input["descriptions"],
                    tool_input["final_url"],
                )
            elif tool_name == "add_keywords":
                return await _ads.add_keywords(
                    org_id, tool_input["ad_group_resource"], tool_input["keywords"]
                )
            elif tool_name == "remove_keywords":
                return await _ads.remove_keywords(org_id, tool_input["keyword_resources"])
            elif tool_name == "get_keyword_suggestions":
                return {"suggestions": await _ads.get_keyword_suggestions(
                    org_id, tool_input["seed_keywords"], tool_input.get("url")
                )}
            elif tool_name == "adjust_campaign_budget":
                return await _ads.update_campaign_budget(
                    org_id, tool_input["campaign_id"], tool_input["daily_budget_cents"]
                )
            elif tool_name == "adjust_bidding_strategy":
                return await _ads.update_bidding_strategy(
                    org_id, tool_input["campaign_id"], tool_input["strategy"],
                    tool_input.get("target_roas"),
                )
            elif tool_name == "pause_campaign":
                return await _ads.update_campaign_status(org_id, tool_input["campaign_id"], "PAUSED")
            elif tool_name == "enable_campaign":
                return await _ads.update_campaign_status(org_id, tool_input["campaign_id"], "ENABLED")

            # Analytics
            elif tool_name == "get_campaign_metrics":
                return {"metrics": await _ads.get_campaign_performance(
                    org_id, tool_input["date_from"], tool_input["date_to"]
                )}
            elif tool_name == "get_keyword_metrics":
                return {"metrics": await _ads.get_keyword_performance(
                    org_id, tool_input["date_from"], tool_input["date_to"]
                )}
            elif tool_name == "get_search_terms_report":
                return {"search_terms": await _ads.get_search_terms_report(
                    org_id, tool_input["date_from"], tool_input["date_to"]
                )}
            elif tool_name == "get_monthly_spend_summary":
                return await _ads.check_budget_remaining(org_id)

            # Safety
            elif tool_name == "request_human_approval":
                action_id = await _ads.log_ai_action(
                    tool_input["action_type"], tool_input["description"],
                    tool_input["reasoning"], tool_input["changes"],
                    requires_approval=True,
                )
                return {"action_id": action_id, "status": "pending_approval"}
            elif tool_name == "log_action":
                action_id = await _ads.log_ai_action(
                    tool_input["action_type"], tool_input["description"],
                    tool_input["reasoning"], tool_input["changes"],
                    requires_approval=False,
                )
                return {"action_id": action_id, "logged": True}

            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error("AI Ads tool execution failed", tool=tool_name, error=str(e))
            return {"error": str(e)}

    # ── Studio Context Tools ──────────────────────────────────────────────────

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
        """Get class types for ad keyword/copy generation."""
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
        """AI creates the full initial campaign structure when Google Ads is first enabled."""
        messages = [{"role": "user", "content": """
You are setting up Google Ads for this fitness studio for the first time. Your task:

1. First, get the studio info, class types, membership types, and the ads config
2. Based on the studio's classes, location, and pricing, create an optimal campaign structure:
   - 1 Search campaign with appropriate daily budget (stay within monthly cap)
   - 2-3 ad groups organized by theme (e.g., by class type, by intent)
   - Responsive search ads with compelling copy for each ad group
   - Relevant keywords for each ad group (mix of broad, phrase, exact match)
3. Set up negative keywords to avoid wasted spend
4. IMPORTANT: Leave the campaign PAUSED — the owner will review and enable it
5. Log every action you take with clear reasoning

Be strategic: focus on the studio's strongest offerings and local market.
"""}]

        result = await self._call_claude_with_tools(
            messages=messages,
            system=AI_ADS_SYSTEM,
            org_id=org_id,
            max_turns=20,
        )

        logger.info("AI initial campaign setup complete", org_id=org_id, actions=len(result["actions"]))
        return result

    async def run_optimization_cycle(self, org_id: str) -> dict:
        """AI analyzes performance and makes optimization adjustments."""
        now = datetime.now(timezone.utc)
        date_to = now.strftime("%Y-%m-%d")
        date_from = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        messages = [{"role": "user", "content": f"""
Run an optimization cycle for this studio's Google Ads. Today is {date_to}.

Follow this process:
1. Check monthly spend vs budget cap
2. If over 95% of budget, pause campaigns and log the reason
3. Get campaign metrics for the last 7 days ({date_from} to {date_to})
4. Get keyword metrics — identify underperformers (CTR < 0.5% with 200+ impressions)
5. Get search terms report — find irrelevant searches to add as negatives
6. Make data-driven adjustments:
   - Pause keywords with poor CTR after sufficient data
   - Add promising new keywords from search terms
   - Adjust budgets based on campaign performance
   - Consider bidding strategy changes if enough conversion data exists
7. Log every decision with your reasoning

Be conservative with changes. Only make adjustments backed by sufficient data.
"""}]

        result = await self._call_claude_with_tools(
            messages=messages,
            system=AI_ADS_SYSTEM,
            org_id=org_id,
            max_turns=15,
        )

        logger.info("AI optimization cycle complete", org_id=org_id, actions=len(result["actions"]))
        return result

    async def generate_performance_report(self, org_id: str, days: int = 30) -> dict:
        """AI generates a human-readable performance report."""
        now = datetime.now(timezone.utc)
        date_to = now.strftime("%Y-%m-%d")
        date_from = (now - timedelta(days=days)).strftime("%Y-%m-%d")

        messages = [{"role": "user", "content": f"""
Generate a performance report for the last {days} days ({date_from} to {date_to}).

1. Get campaign metrics for the period
2. Get keyword metrics for top performers
3. Get monthly spend summary
4. Summarize in a clear, non-technical format the studio owner can understand:
   - Total spend, clicks, conversions, ROAS
   - Best performing keywords and ads
   - What's working and what's not
   - Recommendations for the coming period
"""}]

        result = await self._call_claude_with_tools(
            messages=messages,
            system=AI_ADS_SYSTEM,
            org_id=org_id,
            max_turns=10,
        )
        return result
