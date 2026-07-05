"""AuraFlow — AI Manager Service

Autonomous admin that handles incoming messages from members and instructors,
classifies intent, and resolves common requests using Claude with tool-use.
Delegates to existing services (BookingService, MemberService, SubFinderService)
and escalates to human staff when uncertain.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ai.token_tracking_service import track_ai_usage
from app.services.marketing.campaign_service import SmsService
from app.services.email.email_service import EmailService

_sms = SmsService()
_email = EmailService()


# ── Tool Definitions for Claude ──────────────────────────────────────────────

AI_MANAGER_TOOLS = [
    {
        "name": "lookup_member",
        "description": "Search for a member by name, email, or phone number. Returns matching member records.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name, email, or phone to search for"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_member_bookings",
        "description": "Get upcoming bookings for a specific member.",
        "input_schema": {
            "type": "object",
            "properties": {
                "member_id": {"type": "string", "description": "The member's UUID"}
            },
            "required": ["member_id"],
        },
    },
    {
        "name": "cancel_booking",
        "description": "Cancel a specific booking for a member.",
        "input_schema": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string", "description": "The booking UUID to cancel"},
                "reason": {"type": "string", "description": "Reason for cancellation"},
            },
            "required": ["booking_id"],
        },
    },
    {
        "name": "get_schedule",
        "description": "Get upcoming class sessions. Returns sessions with availability info.",
        "input_schema": {
            "type": "object",
            "properties": {
                "class_type": {"type": "string", "description": "Filter by class type name (optional)"},
                "days_ahead": {"type": "integer", "description": "How many days ahead to look (default 7)"},
            },
        },
    },
    {
        "name": "get_member_memberships",
        "description": "Get active memberships for a member, including remaining credits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "member_id": {"type": "string", "description": "The member's UUID"}
            },
            "required": ["member_id"],
        },
    },
    {
        "name": "lookup_billing",
        "description": "Get payment history for a member.",
        "input_schema": {
            "type": "object",
            "properties": {
                "member_id": {"type": "string", "description": "The member's UUID"},
                "limit": {"type": "integer", "description": "Number of recent payments (default 10)"},
            },
            "required": ["member_id"],
        },
    },
    {
        "name": "send_reply",
        "description": "Send an SMS or email reply to the person who contacted us.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The message to send back"},
            },
            "required": ["message"],
        },
    },
]

AI_MANAGER_SYSTEM = """You are the AI Manager for a yoga/fitness studio. You handle incoming messages
from members and instructors, resolving their requests autonomously when possible.

Your capabilities:
- Look up member information (bookings, memberships, billing)
- Cancel bookings when requested
- Check the class schedule
- Send replies to members/instructors

Guidelines:
- Be helpful, warm, and professional
- For booking cancellations: confirm the specific class before cancelling
- For billing questions: look up payment history and explain clearly
- For membership questions: check their membership status and credits
- If a request is complex, sensitive (complaints, refunds), or you're unsure, respond with
  a message and note that the request needs human follow-up
- Keep SMS replies concise (under 160 chars when possible)
- Never share other members' private information
- If the sender is an instructor saying they're sick/unavailable, note this for sub-finding

Respond in JSON format with:
{"response": "Your reply to the person", "resolved": true/false, "needs_escalation": false, "summary": "Brief summary of what happened"}
"""


class AIManagerService:

    def _is_configured(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    # ── Multi-turn Claude with Tools ───────────────────────────────────────

    async def _call_claude_with_tools(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        context: dict,
        max_turns: int = 5,
    ) -> dict:
        """Multi-turn Claude API call with tool-use. Returns final result."""
        if not self._is_configured():
            return {
                "response": "AI Manager is not configured. Please contact staff directly.",
                "resolved": False,
                "needs_escalation": True,
                "summary": "AI not configured",
                "actions": [],
            }

        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        actions_taken = []

        for turn in range(max_turns):
            try:
                response = await client.messages.create(
                    model=settings.ANTHROPIC_MODEL,
                    max_tokens=1024,
                    system=system,
                    tools=tools,
                    messages=messages,
                )
                await track_ai_usage(
                    service_name="ai_manager_service",
                    function_name="call_claude_with_tools",
                    model=settings.ANTHROPIC_MODEL,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )
            except Exception as e:
                logger.error("AI Manager Claude call failed", error=str(e))
                return {
                    "response": "I'm having trouble processing your request. A staff member will follow up.",
                    "resolved": False,
                    "needs_escalation": True,
                    "summary": f"Claude API error: {str(e)}",
                    "actions": actions_taken,
                }

            # Check if Claude wants to use a tool
            if response.stop_reason == "tool_use":
                # Process tool calls
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_result = await self._execute_tool(
                            block.name, block.input, context
                        )
                        actions_taken.append({
                            "tool": block.name,
                            "input": block.input,
                            "result_preview": str(tool_result)[:200],
                        })
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(tool_result, default=str),
                        })

                # Add assistant message and tool results to conversation
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                # Final response — extract text
                text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text

                # Try to parse JSON response
                try:
                    result = json.loads(text)
                    result["actions"] = actions_taken
                    return result
                except json.JSONDecodeError:
                    return {
                        "response": text,
                        "resolved": True,
                        "needs_escalation": False,
                        "summary": text[:200],
                        "actions": actions_taken,
                    }

        # Max turns exceeded
        return {
            "response": "I need more time to help you. A staff member will follow up shortly.",
            "resolved": False,
            "needs_escalation": True,
            "summary": "Max turns exceeded",
            "actions": actions_taken,
        }

    # ── Tool Execution ─────────────────────────────────────────────────────

    async def _execute_tool(
        self, tool_name: str, tool_input: dict, context: dict
    ) -> dict:
        """Execute a tool call and return the result."""
        try:
            if tool_name == "lookup_member":
                return await self._tool_lookup_member(tool_input["query"])
            elif tool_name == "get_member_bookings":
                return await self._tool_get_bookings(tool_input["member_id"])
            elif tool_name == "cancel_booking":
                return await self._tool_cancel_booking(
                    tool_input["booking_id"], tool_input.get("reason")
                )
            elif tool_name == "get_schedule":
                return await self._tool_get_schedule(
                    tool_input.get("class_type"), tool_input.get("days_ahead", 7)
                )
            elif tool_name == "get_member_memberships":
                return await self._tool_get_memberships(tool_input["member_id"])
            elif tool_name == "lookup_billing":
                return await self._tool_lookup_billing(
                    tool_input["member_id"], tool_input.get("limit", 10)
                )
            elif tool_name == "send_reply":
                return await self._tool_send_reply(
                    tool_input["message"], context
                )
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error("Tool execution failed", tool=tool_name, error=str(e))
            return {"error": str(e)}

    async def _tool_lookup_member(self, query: str) -> dict:
        from app.services.members.member_service import MemberService
        svc = MemberService()
        members = await svc.search_members(query, limit=5)
        return {"members": [
            {"id": str(m["id"]), "name": f"{m.get('first_name', '')} {m.get('last_name', '')}".strip(),
             "email": m.get("email"), "phone": m.get("phone"),
             "membership_status": m.get("membership_status")}
            for m in members
        ]}

    async def _tool_get_bookings(self, member_id: str) -> dict:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT b.id, b.status, b.booked_at,
                       cs.title, cs.starts_at, cs.ends_at,
                       ct.name AS class_type_name,
                       i.display_name AS instructor_name
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE b.member_id = $1
                  AND b.status IN ('confirmed', 'waitlisted')
                  AND cs.starts_at > NOW()
                ORDER BY cs.starts_at ASC LIMIT 10
                """,
                member_id,
            )
        return {"bookings": [
            {"id": str(r["id"]), "title": r["title"],
             "starts_at": r["starts_at"].isoformat() if r["starts_at"] else None,
             "status": r["status"], "instructor": r["instructor_name"]}
            for r in rows
        ]}

    async def _tool_cancel_booking(self, booking_id: str, reason: str | None) -> dict:
        from app.services.scheduling.booking_service import BookingService
        svc = BookingService()
        result = await svc.cancel_booking(booking_id, reason=reason)
        if result:
            return {"success": True, "booking_id": booking_id, "status": "cancelled"}
        return {"success": False, "error": "Booking not found or already cancelled"}

    async def _tool_get_schedule(self, class_type: str | None, days_ahead: int) -> dict:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days_ahead)

        async with get_tenant_db() as db:
            conditions = ["cs.starts_at >= $1", "cs.starts_at < $2", "cs.status = 'scheduled'"]
            params: list = [now, end]
            idx = 3

            if class_type:
                conditions.append(f"LOWER(ct.name) LIKE LOWER(${idx})")
                params.append(f"%{class_type}%")
                idx += 1

            rows = await db.fetch(
                f"""
                SELECT cs.title, cs.starts_at, cs.ends_at, cs.capacity,
                       ct.name AS class_type_name,
                       i.display_name AS instructor_name,
                       (SELECT COUNT(*) FROM bookings WHERE class_session_id = cs.id AND status = 'confirmed') AS booked
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE {' AND '.join(conditions)}
                ORDER BY cs.starts_at LIMIT 20
                """,
                *params,
            )

        return {"sessions": [
            {"title": r["title"], "class_type": r["class_type_name"],
             "starts_at": r["starts_at"].isoformat() if r["starts_at"] else None,
             "instructor": r["instructor_name"],
             "spots_remaining": max(0, (r["capacity"] or 0) - (r["booked"] or 0))}
            for r in rows
        ]}

    async def _tool_get_memberships(self, member_id: str) -> dict:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT mm.id, mm.status, mm.starts_at, mm.ends_at,
                       mm.classes_remaining, mt.auto_renew,
                       mt.name AS type_name, mt.type AS membership_type,
                       mt.price_cents, mt.class_count
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE mm.member_id = $1 AND mm.status IN ('active', 'frozen')
                ORDER BY mm.starts_at DESC
                """,
                member_id,
            )
        return {"memberships": [
            {"id": str(r["id"]), "type_name": r["type_name"],
             "status": r["status"], "classes_remaining": r["classes_remaining"],
             "ends_at": r["ends_at"].isoformat() if r["ends_at"] else None}
            for r in rows
        ]}

    async def _tool_lookup_billing(self, member_id: str, limit: int) -> dict:
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT id, amount_cents, status, description, payment_method, created_at
                FROM transactions
                WHERE member_id = $1
                ORDER BY created_at DESC LIMIT $2
                """,
                member_id, limit,
            )
        return {"payments": [
            {"id": str(r["id"]), "amount": f"${r['amount_cents'] / 100:.2f}",
             "status": r["status"], "description": r.get("description"),
             "date": r["created_at"].isoformat() if r["created_at"] else None}
            for r in rows
        ]}

    async def _tool_send_reply(self, message: str, context: dict) -> dict:
        """Send an SMS or email reply back to the sender."""
        phone = context.get("sender_phone")
        member_id = context.get("sender_id")

        if phone:
            await _sms.send_sms(
                to_phone=phone,
                body=message,
                member_id=member_id,
                sms_type="ai_response",
            )
            return {"sent": True, "channel": "sms"}

        return {"sent": False, "error": "No contact method available"}

    # ── Intent Classification ──────────────────────────────────────────────

    async def classify_intent(self, message: str) -> str:
        """Classify the intent of an incoming message."""
        if not self._is_configured():
            return "other"

        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        try:
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL_FAST,
                max_tokens=50,
                system=(
                    "Classify this message from a yoga/fitness studio member or instructor. "
                    "Reply with exactly one word: sub_request, booking_question, "
                    "billing_question, membership_question, general_question, complaint, or other."
                ),
                messages=[{"role": "user", "content": message}],
            )
            await track_ai_usage(
                service_name="ai_manager_service",
                function_name="classify_intent",
                model=settings.ANTHROPIC_MODEL_FAST,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            intent = response.content[0].text.strip().lower().replace(" ", "_")
            valid = {"sub_request", "booking_question", "billing_question",
                     "membership_question", "general_question", "complaint", "other"}
            return intent if intent in valid else "other"
        except Exception as e:
            logger.error("Intent classification failed", error=str(e))
            return "other"

    # ── Main Entry Point ───────────────────────────────────────────────────

    async def handle_incoming_message(
        self,
        channel: str,
        from_identifier: str,
        body: str,
        sender_type: str | None = None,
        sender_id: str | None = None,
        sender_phone: str | None = None,
    ) -> dict:
        """Process an incoming message from a member or instructor."""
        request_id = str(uuid.uuid4())

        # Classify intent
        intent = await self.classify_intent(body)

        # Create resolution request
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO resolution_requests
                    (id, channel, subject, body, intent, sender_type,
                     sender_id, sender_phone, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'processing')
                """,
                request_id, channel, body[:500], body, intent,
                sender_type, sender_id, sender_phone,
            )

        # Handle sub requests specially
        if intent == "sub_request" and sender_type == "instructor":
            result = {
                "response": "I've noted that you need a substitute. Our system will start looking for one now.",
                "resolved": False,
                "needs_escalation": True,
                "summary": f"Instructor sub request: {body[:200]}",
                "actions": [{"tool": "flag_sub_request", "input": {"message": body}}],
            }
        else:
            # Use Claude with tools to resolve
            context = {
                "sender_type": sender_type,
                "sender_id": sender_id,
                "sender_phone": sender_phone or from_identifier,
                "channel": channel,
            }
            messages = [{"role": "user", "content": (
                f"Incoming {channel} message from {sender_type or 'unknown'} "
                f"(phone: {from_identifier}):\n\n{body}\n\n"
                f"Classify and handle this request."
            )}]
            result = await self._call_claude_with_tools(
                messages=messages,
                system=AI_MANAGER_SYSTEM,
                tools=AI_MANAGER_TOOLS,
                context=context,
            )

        # Update the resolution request
        status = "resolved" if result.get("resolved") else "escalated"
        if result.get("needs_escalation"):
            status = "escalated"

        async with get_tenant_db() as db:
            await db.execute(
                """
                UPDATE resolution_requests
                SET status = $2, ai_summary = $3, ai_suggested_action = $4,
                    response_text = $5, actions_taken = $6::jsonb,
                    resolved_at = CASE WHEN $2 = 'resolved' THEN NOW() ELSE NULL END,
                    updated_at = NOW()
                WHERE id = $1
                """,
                request_id, status, result.get("summary"),
                result.get("response"), result.get("response"),
                json.dumps(result.get("actions", []), default=str),
            )

        logger.info("AI Manager processed message",
                     request_id=request_id, intent=intent, status=status)
        return {**result, "request_id": request_id, "intent": intent}

    # ── Resolution CRUD ────────────────────────────────────────────────────

    async def get_resolution(self, request_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM resolution_requests WHERE id = $1",
                request_id,
            )
        if not row:
            return None
        d = dict(row)
        for k in ("id", "member_id", "assigned_to", "sender_id"):
            if d.get(k):
                d[k] = str(d[k])
        for k in ("created_at", "updated_at", "resolved_at"):
            if d.get(k):
                d[k] = d[k].isoformat()
        if isinstance(d.get("actions_taken"), str):
            d["actions_taken"] = json.loads(d["actions_taken"])
        return d

    async def list_resolutions(
        self, status: str | None = None, limit: int = 50
    ) -> list[dict]:
        async with get_tenant_db() as db:
            if status:
                rows = await db.fetch(
                    """
                    SELECT * FROM resolution_requests
                    WHERE status = $1
                    ORDER BY created_at DESC LIMIT $2
                    """,
                    status, limit,
                )
            else:
                rows = await db.fetch(
                    """
                    SELECT * FROM resolution_requests
                    ORDER BY created_at DESC LIMIT $1
                    """,
                    limit,
                )
        results = []
        for row in rows:
            d = dict(row)
            for k in ("id", "member_id", "assigned_to", "sender_id"):
                if d.get(k):
                    d[k] = str(d[k])
            for k in ("created_at", "updated_at", "resolved_at"):
                if d.get(k):
                    d[k] = d[k].isoformat()
            if isinstance(d.get("actions_taken"), str):
                d["actions_taken"] = json.loads(d["actions_taken"])
            results.append(d)
        return results

    async def escalate(self, request_id: str, reason: str | None = None) -> dict | None:
        """Manually escalate a resolution request."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE resolution_requests
                SET status = 'escalated', ai_suggested_action = COALESCE($2, ai_suggested_action),
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                request_id, reason,
            )
        if not row:
            return None
        return await self.get_resolution(request_id)

    async def resolve_manually(self, request_id: str, resolution: str | None = None) -> dict | None:
        """Manually resolve a resolution request."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE resolution_requests
                SET status = 'resolved', response_text = COALESCE($2, response_text),
                    resolved_at = NOW(), updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                request_id, resolution,
            )
        if not row:
            return None
        return await self.get_resolution(request_id)
