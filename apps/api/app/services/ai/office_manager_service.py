"""AuraFlow — AI Office Manager Service

Claude-powered office manager that handles inbound SMS from instructors and
staff, classifies intent (callout, sub response, inventory question, general),
and orchestrates automated workflows:
  - Instructor substitution via SMS relay with 15-minute timeouts
  - Low-inventory alerts
  - General message forwarding to studio owner

Integrates with the existing SubFinderService for candidate scoring and the
SmsService for message delivery. All AI calls are tracked via track_ai_usage.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.ai.token_tracking_service import track_ai_usage
from app.services.marketing.campaign_service import SmsService

_sms = SmsService()


class OfficeManagerService:
    """AI-powered office manager for inbound SMS processing."""

    def _is_configured(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    # ── Entry Point ───────────────────────────────────────────────────────────

    async def handle_inbound_sms(
        self,
        from_number: str,
        body: str,
        schema: str,
    ) -> dict:
        """Main entry point for inbound SMS. Classifies intent and routes."""
        classification = await self._classify_sms(from_number, body, schema)
        intent = classification.get("intent", "general")
        instructor_id = classification.get("instructor_id")
        instructor_name = classification.get("instructor_name")

        logger.info(
            "Office Manager SMS classified",
            intent=intent,
            from_number=from_number,
            schema=schema,
            instructor_id=instructor_id,
        )

        if intent == "callout" and instructor_id:
            return await self._handle_callout(
                schema=schema,
                instructor_id=instructor_id,
                instructor_name=instructor_name or "Instructor",
                body=body,
                from_number=from_number,
            )

        if intent == "sub_response_yes" and instructor_id:
            return await self._handle_sub_response_from_sms(
                schema=schema,
                instructor_id=instructor_id,
                accepted=True,
            )

        if intent == "sub_response_no" and instructor_id:
            return await self._handle_sub_response_from_sms(
                schema=schema,
                instructor_id=instructor_id,
                accepted=False,
            )

        if intent == "inventory_question":
            return await self.check_inventory_levels(schema)

        # General or unclassified — forward to studio owner
        return await self._forward_to_owner(
            schema=schema,
            from_number=from_number,
            from_name=instructor_name or from_number,
            body=body,
        )

    # ── SMS Classification ────────────────────────────────────────────────────

    async def _classify_sms(
        self, from_number: str, body: str, schema: str
    ) -> dict:
        """Use Claude to classify an inbound SMS. Returns intent + sender info."""
        # Look up the sender by phone number
        sender_info = await self._lookup_sender(from_number, schema)
        instructor_id = sender_info.get("instructor_id")
        instructor_name = sender_info.get("instructor_name")

        # Check for simple YES/NO sub responses first (fast path)
        body_upper = body.strip().upper()
        if body_upper in ("YES", "Y", "YEP", "YEAH", "OK", "SURE") and instructor_id:
            # Check if there's an active sub request for this instructor
            active = await self._find_active_sub_request_for_instructor(
                schema, instructor_id
            )
            if active:
                return {
                    "intent": "sub_response_yes",
                    "instructor_id": instructor_id,
                    "instructor_name": instructor_name,
                    "sub_request_id": str(active["id"]),
                }

        if body_upper in ("NO", "NOPE", "NAH", "CANT", "CAN'T", "PASS") and instructor_id:
            active = await self._find_active_sub_request_for_instructor(
                schema, instructor_id
            )
            if active:
                return {
                    "intent": "sub_response_no",
                    "instructor_id": instructor_id,
                    "instructor_name": instructor_name,
                    "sub_request_id": str(active["id"]),
                }

        if not self._is_configured():
            return {
                "intent": "general",
                "instructor_id": instructor_id,
                "instructor_name": instructor_name,
            }

        # Use Claude for classification
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        sender_context = ""
        if instructor_id:
            sender_context = f"The sender is instructor '{instructor_name}' (ID: {instructor_id})."
        else:
            sender_context = "The sender is not a recognized instructor."

        try:
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL_FAST,
                max_tokens=100,
                system=(
                    "You classify SMS messages sent to a yoga/fitness studio. "
                    "Reply with a JSON object: {\"intent\": \"<intent>\"}\n"
                    "Valid intents:\n"
                    "- callout: instructor saying they can't teach a class (sick, emergency, unavailable)\n"
                    "- sub_response_yes: accepting a substitute teaching request\n"
                    "- sub_response_no: declining a substitute teaching request\n"
                    "- inventory_question: asking about product stock or supplies\n"
                    "- general: anything else (questions, scheduling, etc.)\n"
                    f"\n{sender_context}"
                ),
                messages=[{"role": "user", "content": body}],
            )
            await track_ai_usage(
                service_name="office_manager",
                function_name="classify_sms",
                model=settings.ANTHROPIC_MODEL_FAST,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            text = response.content[0].text.strip()
            # Parse JSON response
            try:
                result = json.loads(text)
                intent = result.get("intent", "general")
            except json.JSONDecodeError:
                # Try to extract intent from plain text
                text_lower = text.lower()
                if "callout" in text_lower:
                    intent = "callout"
                elif "inventory" in text_lower:
                    intent = "inventory_question"
                else:
                    intent = "general"

            valid_intents = {
                "callout", "sub_response_yes", "sub_response_no",
                "inventory_question", "general",
            }
            if intent not in valid_intents:
                intent = "general"

        except Exception as e:
            logger.error("Office Manager classification failed", error=str(e))
            intent = "general"

        return {
            "intent": intent,
            "instructor_id": instructor_id,
            "instructor_name": instructor_name,
        }

    # ── Callout Handling ──────────────────────────────────────────────────────

    async def _handle_callout(
        self,
        schema: str,
        instructor_id: str,
        instructor_name: str,
        body: str,
        from_number: str,
    ) -> dict:
        """Handle an instructor calling out sick. Identify class and start sub search."""
        # Identify which class they're referring to
        class_session = await self._identify_class_from_text(
            schema, instructor_id, body
        )

        if not class_session:
            # Can't identify class — ask for clarification or escalate
            await _sms.send_sms(
                to_phone=from_number,
                body=(
                    f"Got it, {instructor_name}. I couldn't match that to a specific class. "
                    "Could you reply with the class name and time? "
                    "e.g. 'Vinyasa Flow at 9am'"
                ),
                sms_type="office_manager",
            )
            # Also alert the owner
            await self._alert_owner(
                schema,
                f"{instructor_name} is calling out but I couldn't identify the class. "
                f"Their message: \"{body}\"",
            )
            return {
                "status": "needs_clarification",
                "message": "Could not identify class from text",
            }

        session_id = str(class_session["id"])
        session_title = class_session.get("title") or class_session.get("class_type_name") or "Class"
        starts_at = class_session["starts_at"]
        time_str = starts_at.strftime("%I:%M %p").lstrip("0")

        # Acknowledge the instructor
        await _sms.send_sms(
            to_phone=from_number,
            body=(
                f"Got it, {instructor_name}. I'll find a sub for your "
                f"{session_title} at {time_str}. Rest up!"
            ),
            sms_type="office_manager",
        )

        # Start the sub search
        result = await self.start_sub_search(
            schema=schema,
            class_session_id=session_id,
            original_instructor_id=instructor_id,
            reason=body,
        )

        return {
            "status": "sub_search_started",
            "sub_request_id": result.get("sub_request_id"),
            "class_session_id": session_id,
            "class_title": session_title,
        }

    # ── Sub Search ────────────────────────────────────────────────────────────

    async def start_sub_search(
        self,
        schema: str,
        class_session_id: str,
        original_instructor_id: str,
        reason: str | None = None,
    ) -> dict:
        """Create a sub_request record and start contacting eligible subs."""
        request_id = str(uuid.uuid4())

        async with get_tenant_db(schema_override=schema) as db:
            # Verify session exists
            session = await db.fetchrow(
                """
                SELECT cs.*, ct.name AS class_type_name,
                       i.display_name AS instructor_name, i.phone AS instructor_phone
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE cs.id = $1
                """,
                class_session_id,
            )
            if not session:
                logger.error("Sub search: session not found", session_id=class_session_id)
                return {"error": "Session not found"}

            # Create sub_request record
            await db.execute(
                """
                INSERT INTO sub_requests
                    (id, class_session_id, original_instructor_id, reason, status)
                VALUES ($1, $2, $3, $4, 'searching')
                """,
                request_id, class_session_id, original_instructor_id, reason,
            )

        # Find eligible substitutes
        candidates = await self._find_eligible_subs(
            schema, class_session_id, original_instructor_id
        )

        if not candidates:
            # No subs available — escalate immediately
            await self._escalate_no_sub_found(schema, request_id)
            return {
                "sub_request_id": request_id,
                "status": "escalated",
                "message": "No eligible substitutes found",
            }

        # Store candidate list
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                """
                UPDATE sub_requests
                SET attempted_instructor_ids = $2
                WHERE id = $1
                """,
                request_id,
                [str(c["id"]) for c in candidates],
            )

        # Send request to first candidate
        first_candidate = candidates[0]
        await self._send_sub_request_sms(
            schema=schema,
            sub_request_id=request_id,
            instructor_id=str(first_candidate["id"]),
            instructor_name=first_candidate["display_name"],
            instructor_phone=first_candidate["phone"],
            session=session,
        )

        logger.info(
            "Sub search started",
            request_id=request_id,
            session_id=class_session_id,
            candidates=len(candidates),
        )
        return {
            "sub_request_id": request_id,
            "status": "searching",
            "candidates": len(candidates),
        }

    async def _find_eligible_subs(
        self,
        schema: str,
        class_session_id: str,
        original_instructor_id: str,
    ) -> list[dict]:
        """Find instructors eligible to sub: same class type, active, no conflicts."""
        async with get_tenant_db(schema_override=schema) as db:
            # Get session details
            session = await db.fetchrow(
                """
                SELECT cs.starts_at, cs.ends_at, cs.class_type_id,
                       ct.category, ct.name AS class_type_name
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                WHERE cs.id = $1
                """,
                class_session_id,
            )
            if not session:
                return []

            session_start = session["starts_at"]
            session_end = session["ends_at"]
            class_type_id = session["class_type_id"]
            category = session["category"] or ""
            day_of_week = session_start.weekday()

            # Get all active instructors except the original (must have phone)
            instructors = await db.fetch(
                """
                SELECT id, display_name, phone, specialties, certifications
                FROM instructors
                WHERE is_active = TRUE
                  AND id != $1
                  AND phone IS NOT NULL
                  AND phone != ''
                """,
                original_instructor_id,
            )

            # Get schedule conflicts
            conflicts = await db.fetch(
                """
                SELECT instructor_id
                FROM class_sessions
                WHERE status != 'cancelled'
                  AND starts_at < $2 AND ends_at > $1
                  AND id != $3
                """,
                session_start, session_end, class_session_id,
            )
            conflict_ids = {str(c["instructor_id"]) for c in conflicts}

            # Check who already teaches this class type (experience indicator)
            type_teachers = await db.fetch(
                """
                SELECT instructor_id, COUNT(*) AS class_count
                FROM class_sessions
                WHERE class_type_id = $1
                  AND status != 'cancelled'
                  AND instructor_id != $2
                GROUP BY instructor_id
                ORDER BY class_count DESC
                """,
                class_type_id, original_instructor_id,
            )
            type_teacher_counts = {
                str(t["instructor_id"]): t["class_count"] for t in type_teachers
            }

            # Get availability for the day of week
            availability = await db.fetch(
                """
                SELECT instructor_id, start_time, end_time
                FROM instructor_availability
                WHERE day_of_week = $1 AND is_blocked = FALSE
                """,
                day_of_week,
            )
            avail_by_instructor = {}
            for a in availability:
                iid = str(a["instructor_id"])
                if iid not in avail_by_instructor:
                    avail_by_instructor[iid] = []
                avail_by_instructor[iid].append(a)

        # Score and filter candidates
        candidates = []
        session_time = session_start.time()

        for inst in instructors:
            iid = str(inst["id"])

            # Must not have a schedule conflict
            if iid in conflict_ids:
                continue

            score = 0
            specialties = inst["specialties"] or []

            # Teaches this exact class type (highest signal)
            class_count = type_teacher_counts.get(iid, 0)
            if class_count > 0:
                score += 30 + min(class_count, 10)  # Experienced first

            # Specialty match
            if category and category.lower() in [s.lower() for s in specialties]:
                score += 20

            # Has availability for this time slot
            slots = avail_by_instructor.get(iid, [])
            for slot in slots:
                if slot["start_time"] <= session_time <= slot["end_time"]:
                    score += 25
                    break

            # Base score for being free
            score += 10

            candidates.append({**dict(inst), "_score": score})

        # Sort by score desc (most qualified first)
        candidates.sort(key=lambda c: (-c["_score"], c["display_name"]))
        return candidates

    async def _send_sub_request_sms(
        self,
        schema: str,
        sub_request_id: str,
        instructor_id: str,
        instructor_name: str,
        instructor_phone: str,
        session: dict,
    ) -> None:
        """Send SMS asking an instructor to sub. Schedule 15-min timeout."""
        starts_at = session["starts_at"]
        title = session.get("title") or session.get("class_type_name") or "Class"
        orig_name = session.get("instructor_name") or "Another instructor"
        time_str = starts_at.strftime("%I:%M %p").lstrip("0")
        date_str = starts_at.strftime("%A, %b %d")

        body = (
            f"Hi {instructor_name}, {orig_name} can't teach "
            f"{title} on {date_str} at {time_str}. "
            f"Can you sub? Reply YES or NO"
        )

        await _sms.send_sms(
            to_phone=instructor_phone,
            body=body,
            sms_type="sub_request",
        )

        # Update the sub_request with current attempt
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                """
                UPDATE sub_requests
                SET current_attempt_instructor_id = $2,
                    attempt_count = attempt_count + 1
                WHERE id = $1
                """,
                sub_request_id, instructor_id,
            )

        # Schedule 15-minute timeout check via Celery
        try:
            from app.workers.tasks.office_manager import check_sub_request_timeout
            check_sub_request_timeout.apply_async(
                args=[schema, sub_request_id, instructor_id],
                countdown=900,  # 15 minutes
            )
        except Exception as e:
            logger.error(
                "Failed to schedule sub request timeout",
                error=str(e),
                sub_request_id=sub_request_id,
            )

        logger.info(
            "Sub request SMS sent",
            sub_request_id=sub_request_id,
            instructor=instructor_name,
            phone=instructor_phone,
        )

    # ── Sub Response Handling ─────────────────────────────────────────────────

    async def handle_sub_response(
        self,
        schema: str,
        sub_request_id: str,
        instructor_id: str,
        accepted: bool,
    ) -> dict:
        """Process a substitute instructor's YES/NO response."""
        async with get_tenant_db(schema_override=schema) as db:
            request = await db.fetchrow(
                "SELECT * FROM sub_requests WHERE id = $1",
                sub_request_id,
            )
            if not request:
                return {"error": "Sub request not found"}

            if request["status"] not in ("searching",):
                return {"error": f"Sub request already {request['status']}"}

            # Verify this is the instructor we're waiting on
            if str(request["current_attempt_instructor_id"]) != instructor_id:
                return {"error": "Not the current attempt instructor"}

        if accepted:
            return await self._accept_sub(schema, sub_request_id, instructor_id)
        else:
            return await self._decline_sub(schema, sub_request_id, instructor_id)

    async def _accept_sub(
        self, schema: str, sub_request_id: str, instructor_id: str
    ) -> dict:
        """Handle a sub accepting the request."""
        async with get_tenant_db(schema_override=schema) as db:
            request = await db.fetchrow(
                "SELECT * FROM sub_requests WHERE id = $1", sub_request_id
            )
            session_id = str(request["class_session_id"])
            original_instructor_id = str(request["original_instructor_id"])

            # Update the class session with the substitute instructor
            await db.execute(
                """
                UPDATE class_sessions
                SET substitute_instructor_id = $1, updated_at = NOW()
                WHERE id = $2
                """,
                instructor_id, session_id,
            )

            # Mark the sub_request as resolved
            await db.execute(
                """
                UPDATE sub_requests
                SET status = 'sub_found',
                    sub_instructor_id = $2,
                    resolved_at = NOW()
                WHERE id = $1
                """,
                sub_request_id, instructor_id,
            )

            # Get details for notifications
            sub_instructor = await db.fetchrow(
                "SELECT display_name, phone FROM instructors WHERE id = $1",
                instructor_id,
            )
            original_instructor = await db.fetchrow(
                "SELECT display_name, phone FROM instructors WHERE id = $1",
                original_instructor_id,
            )
            session = await db.fetchrow(
                """
                SELECT cs.title, cs.starts_at, ct.name AS class_type_name
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                WHERE cs.id = $1
                """,
                session_id,
            )

        sub_name = sub_instructor["display_name"] if sub_instructor else "A substitute"
        orig_name = original_instructor["display_name"] if original_instructor else "Instructor"
        title = (session.get("title") or session.get("class_type_name") or "Class") if session else "Class"
        time_str = session["starts_at"].strftime("%I:%M %p").lstrip("0") if session else ""

        # Confirm to the sub
        if sub_instructor and sub_instructor["phone"]:
            await _sms.send_sms(
                to_phone=sub_instructor["phone"],
                body=f"You're confirmed to teach {title} at {time_str}. Thank you!",
                sms_type="sub_confirmation",
            )

        # Notify the original instructor
        if original_instructor and original_instructor["phone"]:
            await _sms.send_sms(
                to_phone=original_instructor["phone"],
                body=f"Great news! {sub_name} will cover your {title} at {time_str}. Feel better!",
                sms_type="sub_confirmation",
            )

        # Notify the studio owner
        await self._alert_owner(
            schema,
            f"Sub found: {sub_name} will cover {orig_name}'s {title} at {time_str}.",
        )

        # Also update the sub_finder_requests table if it exists (backward compat)
        try:
            from app.services.ai.sub_finder_service import SubFinderService
            # The sub_finder_service uses its own table, this is a parallel system
        except ImportError:
            pass

        logger.info(
            "Sub accepted",
            sub_request_id=sub_request_id,
            sub=sub_name,
            session_id=session_id,
        )

        return {
            "status": "sub_found",
            "sub_instructor": sub_name,
            "class_title": title,
        }

    async def _decline_sub(
        self, schema: str, sub_request_id: str, instructor_id: str
    ) -> dict:
        """Handle a sub declining. Try the next instructor."""
        async with get_tenant_db(schema_override=schema) as db:
            request = await db.fetchrow(
                "SELECT * FROM sub_requests WHERE id = $1", sub_request_id
            )
            session_id = str(request["class_session_id"])
            original_instructor_id = str(request["original_instructor_id"])
            attempted = request["attempted_instructor_ids"] or []

            # Get session details for the next SMS
            session = await db.fetchrow(
                """
                SELECT cs.*, ct.name AS class_type_name,
                       i.display_name AS instructor_name
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE cs.id = $1
                """,
                session_id,
            )

        # Find the next untried instructor
        candidates = await self._find_eligible_subs(
            schema, session_id, original_instructor_id
        )

        # Filter out already-attempted instructors
        attempted_set = {str(a) for a in attempted}
        attempted_set.add(instructor_id)  # Add the one who just declined

        remaining = [c for c in candidates if str(c["id"]) not in attempted_set]

        # Update attempted list
        async with get_tenant_db(schema_override=schema) as db:
            await db.execute(
                """
                UPDATE sub_requests
                SET attempted_instructor_ids = $2,
                    current_attempt_instructor_id = NULL
                WHERE id = $1
                """,
                sub_request_id,
                list(attempted_set),
            )

        if not remaining:
            # No more candidates — escalate
            await self._escalate_no_sub_found(schema, sub_request_id)
            return {"status": "escalated", "message": "No more candidates available"}

        # Try the next candidate
        next_candidate = remaining[0]
        await self._send_sub_request_sms(
            schema=schema,
            sub_request_id=sub_request_id,
            instructor_id=str(next_candidate["id"]),
            instructor_name=next_candidate["display_name"],
            instructor_phone=next_candidate["phone"],
            session=session,
        )

        return {
            "status": "searching",
            "next_instructor": next_candidate["display_name"],
            "remaining": len(remaining) - 1,
        }

    # ── Sub Response from SMS ─────────────────────────────────────────────────

    async def _handle_sub_response_from_sms(
        self,
        schema: str,
        instructor_id: str,
        accepted: bool,
    ) -> dict:
        """Handle YES/NO SMS by finding the active sub_request for this instructor."""
        active = await self._find_active_sub_request_for_instructor(
            schema, instructor_id
        )
        if not active:
            return {"error": "No active sub request found for this instructor"}

        return await self.handle_sub_response(
            schema=schema,
            sub_request_id=str(active["id"]),
            instructor_id=instructor_id,
            accepted=accepted,
        )

    async def _find_active_sub_request_for_instructor(
        self, schema: str, instructor_id: str
    ) -> Optional[dict]:
        """Find an active sub_request where this instructor is the current attempt."""
        async with get_tenant_db(schema_override=schema) as db:
            row = await db.fetchrow(
                """
                SELECT * FROM sub_requests
                WHERE current_attempt_instructor_id = $1
                  AND status = 'searching'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                instructor_id,
            )
        return dict(row) if row else None

    # ── Escalation ────────────────────────────────────────────────────────────

    async def _escalate_no_sub_found(
        self, schema: str, sub_request_id: str
    ) -> None:
        """No sub found — alert the studio owner urgently."""
        async with get_tenant_db(schema_override=schema) as db:
            request = await db.fetchrow(
                "SELECT * FROM sub_requests WHERE id = $1", sub_request_id
            )
            if not request:
                return

            session = await db.fetchrow(
                """
                SELECT cs.title, cs.starts_at, ct.name AS class_type_name,
                       i.display_name AS instructor_name
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE cs.id = $1
                """,
                str(request["class_session_id"]),
            )

            # Mark as escalated
            await db.execute(
                """
                UPDATE sub_requests
                SET status = 'escalated', escalated_at = NOW()
                WHERE id = $1
                """,
                sub_request_id,
            )

        title = "Class"
        time_str = ""
        orig_name = "An instructor"
        if session:
            title = session.get("title") or session.get("class_type_name") or "Class"
            time_str = session["starts_at"].strftime("%I:%M %p").lstrip("0") if session.get("starts_at") else ""
            orig_name = session.get("instructor_name") or "An instructor"

        await self._alert_owner(
            schema,
            f"URGENT: No sub found for {title} at {time_str}. "
            f"{orig_name} is out. Please handle manually.",
        )

        logger.warning(
            "Sub search escalated — no sub found",
            sub_request_id=sub_request_id,
        )

    # ── Class Identification ──────────────────────────────────────────────────

    async def _identify_class_from_text(
        self,
        schema: str,
        instructor_id: str,
        text: str,
    ) -> Optional[dict]:
        """Use Claude + DB to match free-text to an actual class_session."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        async with get_tenant_db(schema_override=schema) as db:
            # Get today's classes for this instructor
            rows = await db.fetch(
                """
                SELECT cs.id, cs.title, cs.starts_at, cs.ends_at,
                       ct.name AS class_type_name, ct.category
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                WHERE cs.instructor_id = $1
                  AND cs.starts_at >= $2
                  AND cs.starts_at < $3
                  AND cs.status = 'scheduled'
                ORDER BY cs.starts_at ASC
                """,
                instructor_id, today_start, today_end,
            )

        if not rows:
            # Try tomorrow if it's late in the day
            if now.hour >= 18:
                tomorrow_start = today_end
                tomorrow_end = tomorrow_start + timedelta(days=1)
                async with get_tenant_db(schema_override=schema) as db:
                    rows = await db.fetch(
                        """
                        SELECT cs.id, cs.title, cs.starts_at, cs.ends_at,
                               ct.name AS class_type_name, ct.category
                        FROM class_sessions cs
                        LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                        WHERE cs.instructor_id = $1
                          AND cs.starts_at >= $2
                          AND cs.starts_at < $3
                          AND cs.status = 'scheduled'
                        ORDER BY cs.starts_at ASC
                        """,
                        instructor_id, tomorrow_start, tomorrow_end,
                    )

        if not rows:
            return None

        # If only one class today, return it directly
        if len(rows) == 1:
            return dict(rows[0])

        # Multiple classes — use Claude to pick the best match
        if not self._is_configured():
            # Without AI, return the first upcoming class
            for row in rows:
                if row["starts_at"] > now:
                    return dict(row)
            return dict(rows[0])

        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        classes_desc = []
        for i, row in enumerate(rows):
            time_str = row["starts_at"].strftime("%I:%M %p")
            name = row.get("title") or row.get("class_type_name") or "Class"
            classes_desc.append(f"{i}: {name} at {time_str}")

        try:
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL_FAST,
                max_tokens=20,
                system=(
                    "An instructor sent a message about missing a class. "
                    "Pick the class index (number only) that best matches. "
                    "Reply with just the number."
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Instructor message: \"{text}\"\n\n"
                        f"Their classes today:\n" + "\n".join(classes_desc)
                    ),
                }],
            )
            await track_ai_usage(
                service_name="office_manager",
                function_name="identify_class",
                model=settings.ANTHROPIC_MODEL_FAST,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            idx_text = response.content[0].text.strip()
            # Extract first number
            idx = int("".join(c for c in idx_text if c.isdigit())[:2])
            if 0 <= idx < len(rows):
                return dict(rows[idx])
        except Exception as e:
            logger.error("Class identification failed", error=str(e))

        # Fallback: next upcoming class
        for row in rows:
            if row["starts_at"] > now:
                return dict(row)
        return dict(rows[0])

    # ── Inventory Check ───────────────────────────────────────────────────────

    async def check_inventory_levels(self, schema: str) -> dict:
        """Query products at or below reorder point. Alert owner if any found."""
        async with get_tenant_db(schema_override=schema) as db:
            rows = await db.fetch(
                """
                SELECT p.name, p.sku, i.quantity_on_hand, i.reorder_point
                FROM inventory i
                JOIN products p ON p.id = i.product_id
                WHERE i.quantity_on_hand <= i.reorder_point
                ORDER BY i.quantity_on_hand ASC
                """,
            )

        if not rows:
            return {
                "status": "ok",
                "message": "All inventory levels are above reorder points.",
                "low_items": [],
            }

        low_items = [
            {
                "name": r["name"],
                "sku": r["sku"],
                "on_hand": r["quantity_on_hand"],
                "reorder_point": r["reorder_point"],
            }
            for r in rows
        ]

        # Build alert message
        lines = ["Low inventory alert:"]
        for item in low_items[:10]:  # Limit SMS length
            lines.append(
                f"- {item['name']}: {item['on_hand']} left (reorder at {item['reorder_point']})"
            )
        if len(low_items) > 10:
            lines.append(f"...and {len(low_items) - 10} more items")

        alert_msg = "\n".join(lines)
        await self._alert_owner(schema, alert_msg)

        return {
            "status": "low_inventory",
            "message": alert_msg,
            "low_items": low_items,
        }

    # ── Helper: Look Up Sender ────────────────────────────────────────────────

    async def _lookup_sender(
        self, from_number: str, schema: str
    ) -> dict:
        """Look up who a phone number belongs to (instructor or member).

        Routes through phone_hash so this lookup survives the Phase C
        plaintext-phone drop. The legacy plaintext WHERE branch stays as
        a bake-window fallback for any row whose phone_hash hasn't been
        backfilled yet — once plaintext drops, only the hash branch
        will return rows, which is the intended end state.
        """
        from app.services.members.phone_hash import hash_phone, normalize_phone
        normalized = normalize_phone(from_number)
        legacy_normalized = from_number.lstrip("+").lstrip("1") if from_number.startswith("+1") else from_number
        phash = hash_phone(from_number)

        async with get_tenant_db(schema_override=schema) as db:
            instructor = await db.fetchrow(
                """
                SELECT id, display_name, phone
                FROM instructors
                WHERE is_active = TRUE
                  AND (phone_hash = $1 OR phone = $2 OR phone = $3 OR phone = $4)
                """,
                phash, from_number, legacy_normalized, normalized,
            )
            if instructor:
                return {
                    "instructor_id": str(instructor["id"]),
                    "instructor_name": instructor["display_name"],
                    "phone": instructor["phone"],
                    "type": "instructor",
                }

            # Members lookup — phone_hash only. members.phone is dropped
            # in Phase C; the plaintext fallback would SQL-error post-drop.
            member = await db.fetchrow(
                """
                SELECT id, first_name, last_name, phone_enc
                FROM members
                WHERE is_active = TRUE
                  AND phone_hash = $1
                """,
                phash,
            )
            if member:
                from app.services.members.phi_helpers import decrypt_phone
                name = f"{member['first_name'] or ''} {member['last_name'] or ''}".strip()
                return {
                    "member_id": str(member["id"]),
                    "member_name": name,
                    "phone": decrypt_phone(member),
                    "type": "member",
                }

        return {"type": "unknown", "phone": from_number}

    # ── Helper: Get Studio Owner Phone ────────────────────────────────────────

    async def _get_owner_phone(self, schema: str) -> Optional[str]:
        """Look up the studio owner's phone number."""
        async with get_tenant_db(schema_override=schema) as db:
            # Try studio_user_roles first (owner role)
            try:
                row = await db.fetchrow(
                    """
                    SELECT i.phone
                    FROM studio_user_roles sur
                    JOIN instructors i ON i.user_id = sur.user_id
                    WHERE sur.role = 'owner'
                      AND i.phone IS NOT NULL
                      AND i.phone != ''
                    LIMIT 1
                    """,
                )
                if row and row["phone"]:
                    return row["phone"]
            except Exception:
                pass

            # Fallback: look in instructors for someone marked as owner or first instructor
            try:
                row = await db.fetchrow(
                    """
                    SELECT phone FROM instructors
                    WHERE is_active = TRUE
                      AND phone IS NOT NULL
                      AND phone != ''
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                )
                if row and row["phone"]:
                    return row["phone"]
            except Exception:
                pass

        # Fallback: check the global org contact
        try:
            async with get_global_db() as db:
                row = await db.fetchrow(
                    """
                    SELECT u.phone
                    FROM af_global.organizations o
                    JOIN af_global.users u ON u.id = o.owner_user_id
                    WHERE o.schema_name = $1
                      AND u.phone IS NOT NULL
                    """,
                    schema,
                )
                if row and row["phone"]:
                    return row["phone"]
        except Exception:
            pass

        return None

    async def _alert_owner(self, schema: str, message: str) -> None:
        """Send an SMS alert to the studio owner."""
        phone = await self._get_owner_phone(schema)
        if phone:
            await _sms.send_sms(
                to_phone=phone,
                body=message,
                sms_type="office_manager_alert",
            )
            logger.info("Owner alerted", schema=schema, message_preview=message[:100])
        else:
            logger.warning(
                "Cannot alert owner — no phone found",
                schema=schema,
                message_preview=message[:100],
            )

    async def _forward_to_owner(
        self,
        schema: str,
        from_number: str,
        from_name: str,
        body: str,
    ) -> dict:
        """Forward an unclassified message to the studio owner."""
        msg = f"SMS from {from_name} ({from_number}): {body}"
        if len(msg) > 1500:
            msg = msg[:1497] + "..."
        await self._alert_owner(schema, msg)
        return {"status": "forwarded", "message": "Message forwarded to studio owner"}

    # ── Timeout Handling ──────────────────────────────────────────────────────

    async def handle_sub_timeout(
        self,
        schema: str,
        sub_request_id: str,
        instructor_id: str,
    ) -> dict:
        """Called by Celery after 15 min if no response. Move to next candidate."""
        async with get_tenant_db(schema_override=schema) as db:
            request = await db.fetchrow(
                "SELECT * FROM sub_requests WHERE id = $1", sub_request_id
            )
            if not request:
                return {"error": "Sub request not found"}

            # Only process if still searching and waiting on this instructor
            if request["status"] != "searching":
                return {"status": request["status"], "message": "Already resolved"}

            if str(request["current_attempt_instructor_id"]) != instructor_id:
                return {"status": "skipped", "message": "No longer waiting on this instructor"}

        logger.info(
            "Sub request timeout — moving to next",
            sub_request_id=sub_request_id,
            instructor_id=instructor_id,
        )

        # Treat as a decline
        return await self._decline_sub(schema, sub_request_id, instructor_id)
