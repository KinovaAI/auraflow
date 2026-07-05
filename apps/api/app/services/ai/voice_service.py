"""AuraFlow — Voice Service

Speech-to-text via OpenAI Whisper API for voice check-in and voice commands.
Members can check in verbally; staff can navigate the app by voice.
"""
import io
import json
from difflib import SequenceMatcher

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ai.token_tracking_service import track_ai_usage


class VoiceService:

    def _is_configured(self) -> bool:
        return bool(settings.OPENAI_API_KEY)

    # ── Transcription ──────────────────────────────────────────────────────

    async def transcribe_audio(
        self,
        audio_data: bytes,
        filename: str = "audio.webm",
        language: str = "en",
    ) -> str:
        """Transcribe audio using OpenAI Whisper API."""
        if not self._is_configured():
            raise ValueError("Voice service not configured — set OPENAI_API_KEY")

        import httpx
        import asyncio

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                        data={"model": "whisper-1", "language": language},
                        files={"file": (filename, audio_data)},
                    )
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 5))
                        if attempt < max_retries:
                            logger.warning("OpenAI rate limited, retrying", attempt=attempt, retry_after=retry_after)
                            await asyncio.sleep(min(retry_after, 10))
                            continue
                        raise ValueError("Voice service is temporarily busy. Please try again in a moment.")
                    response.raise_for_status()
                    result = response.json()
                    break
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries:
                    await asyncio.sleep(5)
                    continue
                logger.error("OpenAI transcription failed", status=e.response.status_code, error=str(e))
                raise ValueError("Voice transcription failed. Please try again.")

        transcript = result.get("text", "").strip()
        logger.info("Audio transcribed", length=len(audio_data), transcript_len=len(transcript))
        return transcript

    # ── Text-Based Check-In (Browser Speech Recognition) ────────────────

    async def process_text_checkin(self, transcript: str) -> dict:
        """Process a text transcript for check-in (no audio transcription needed).

        Same logic as process_voice_checkin but skips the Whisper API call.
        Used with browser SpeechRecognition API.
        """
        if not transcript:
            return {"status": "no_match", "transcript": "", "message": "No text provided"}

        name = self._extract_name(transcript)
        if not name:
            return {"status": "no_match", "transcript": transcript,
                    "message": "Could not extract a name from the text"}

        matches = await self._fuzzy_match_member(name)

        if not matches:
            return {"status": "no_match", "transcript": transcript,
                    "name_extracted": name, "message": f"No member found matching '{name}'"}

        if len(matches) == 1 and matches[0]["score"] >= 0.80:
            member = matches[0]
            booking = await self._find_todays_booking(member["id"])

            if booking:
                from app.services.scheduling.booking_service import BookingService
                svc = BookingService()
                result = await svc.check_in(str(booking["id"]))
                return {
                    "status": "checked_in",
                    "transcript": transcript,
                    "member": {
                        "id": member["id"],
                        "name": member["name"],
                        "email": member.get("email"),
                    },
                    "booking": {
                        "id": str(booking["id"]),
                        "class_title": booking.get("title"),
                        "starts_at": booking["starts_at"].isoformat() if booking.get("starts_at") else None,
                    },
                }
            else:
                return {
                    "status": "no_booking",
                    "transcript": transcript,
                    "member": {
                        "id": member["id"],
                        "name": member["name"],
                    },
                    "message": f"{member['name']} has no upcoming booking today",
                }

        return {
            "status": "ambiguous",
            "transcript": transcript,
            "name_extracted": name,
            "candidates": [
                {"id": m["id"], "name": m["name"], "score": round(m["score"], 2)}
                for m in matches[:5]
            ],
        }

    # ── Voice Check-In ─────────────────────────────────────────────────────

    async def process_voice_checkin(self, audio_data: bytes, filename: str = "audio.webm") -> dict:
        """Transcribe audio, extract member name, fuzzy match, and check in.

        Returns:
            - If confident match: {"status": "checked_in", "member": {...}, "booking": {...}}
            - If ambiguous: {"status": "ambiguous", "candidates": [...]}
            - If no match: {"status": "no_match", "transcript": "..."}
        """
        transcript = await self.transcribe_audio(audio_data, filename)
        if not transcript:
            return {"status": "no_match", "transcript": "", "message": "Could not understand audio"}

        # Extract the name from the transcript
        name = self._extract_name(transcript)
        if not name:
            return {"status": "no_match", "transcript": transcript,
                    "message": "Could not extract a name from the audio"}

        # Fuzzy match against members
        matches = await self._fuzzy_match_member(name)

        if not matches:
            return {"status": "no_match", "transcript": transcript,
                    "name_extracted": name, "message": f"No member found matching '{name}'"}

        if len(matches) == 1 and matches[0]["score"] >= 0.80:
            # Confident match — try to check in
            member = matches[0]
            booking = await self._find_todays_booking(member["id"])

            if booking:
                # Check in
                from app.services.scheduling.booking_service import BookingService
                svc = BookingService()
                result = await svc.check_in(str(booking["id"]))
                return {
                    "status": "checked_in",
                    "transcript": transcript,
                    "member": {
                        "id": member["id"],
                        "name": member["name"],
                        "email": member.get("email"),
                    },
                    "booking": {
                        "id": str(booking["id"]),
                        "class_title": booking.get("title"),
                        "starts_at": booking["starts_at"].isoformat() if booking.get("starts_at") else None,
                    },
                }
            else:
                return {
                    "status": "no_booking",
                    "transcript": transcript,
                    "member": {
                        "id": member["id"],
                        "name": member["name"],
                    },
                    "message": f"{member['name']} has no upcoming booking today",
                }

        # Multiple matches or low confidence
        return {
            "status": "ambiguous",
            "transcript": transcript,
            "name_extracted": name,
            "candidates": [
                {"id": m["id"], "name": m["name"], "score": round(m["score"], 2)}
                for m in matches[:5]
            ],
        }

    # ── Voice Commands ─────────────────────────────────────────────────────

    async def process_voice_command(self, audio_data: bytes, filename: str = "audio.webm") -> dict:
        """Transcribe audio and parse a navigation/action command.

        Returns:
            {"action": "navigate", "path": "/members/{id}/billing", "description": "..."}
        """
        transcript = await self.transcribe_audio(audio_data, filename)
        if not transcript:
            return {"action": "error", "message": "Could not understand audio"}

        # Use Claude to parse the command
        if not settings.ANTHROPIC_API_KEY:
            return {"action": "error", "message": "AI not configured",
                    "transcript": transcript}

        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        try:
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL_FAST,
                max_tokens=200,
                system=(
                    "You parse voice commands for a yoga studio management app. "
                    "Extract the intent and return JSON. Possible actions:\n"
                    "- navigate: go to a page (target: dashboard, members, schedule, billing, settings, analytics)\n"
                    "- search_member: look up a member (member_name: the name)\n"
                    "- open_member: open a specific member's page (member_name, section: profile/billing/bookings)\n"
                    "\nAlways respond with valid JSON: {\"action\": \"...\", ...}"
                ),
                messages=[{"role": "user", "content": f"Voice command: {transcript}"}],
            )
            await track_ai_usage(
                service_name="voice_service",
                function_name="process_voice_command",
                model=settings.ANTHROPIC_MODEL_FAST,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            text = response.content[0].text.strip()
            result = json.loads(text)
        except (json.JSONDecodeError, Exception) as e:
            logger.error("Voice command parse failed", error=str(e))
            result = {"action": "unknown", "transcript": transcript}

        # If the command references a member name, try to resolve it
        member_name = result.get("member_name")
        if member_name:
            matches = await self._fuzzy_match_member(member_name)
            if matches and matches[0]["score"] >= 0.70:
                member = matches[0]
                result["member_id"] = member["id"]
                result["member_resolved"] = member["name"]

                # Build navigation path
                section = result.get("section", "profile")
                if result.get("action") == "open_member":
                    result["path"] = f"/members/{member['id']}/{section}"
            else:
                result["member_candidates"] = [
                    {"id": m["id"], "name": m["name"]} for m in (matches or [])[:3]
                ]

        result["transcript"] = transcript
        return result

    # ── Internal Helpers ───────────────────────────────────────────────────

    def _extract_name(self, transcript: str) -> str | None:
        """Extract a person's name from a check-in transcript."""
        text = transcript.strip().lower()

        # Common check-in patterns
        prefixes = [
            "checking in", "check in", "this is", "my name is",
            "i'm", "i am", "hi i'm", "hi i am", "hello i'm",
            "hello i am", "hey it's", "hey its", "it's",
        ]

        for prefix in prefixes:
            if prefix in text:
                name = text.split(prefix, 1)[1].strip()
                # Remove trailing phrases like "for class", "checking in", etc.
                for suffix in ["checking in", "for", "here for", "at"]:
                    if name.endswith(suffix):
                        name = name[: -len(suffix)].strip()
                    elif f" {suffix} " in name:
                        name = name.split(f" {suffix} ")[0].strip()
                if name:
                    return name.title()

        # If no pattern matched, treat the whole transcript as the name
        # (if it's short enough to plausibly be a name)
        words = text.split()
        if 1 <= len(words) <= 4:
            return text.title()

        return None

    async def _fuzzy_match_member(self, name: str, threshold: float = 0.5) -> list[dict]:
        """Fuzzy match a name against all active members."""
        from app.services.members.phi_helpers import decrypt_phone
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT id, first_name, last_name, email, phone_enc
                FROM members
                WHERE is_active = TRUE
                """,
            )

        name_lower = name.lower().strip()
        results = []

        for row in rows:
            full_name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
            full_name_lower = full_name.lower()

            # Try full name match
            score = SequenceMatcher(None, name_lower, full_name_lower).ratio()

            # Also try last-name-first match
            reverse_name = f"{row['last_name'] or ''} {row['first_name'] or ''}".strip().lower()
            reverse_score = SequenceMatcher(None, name_lower, reverse_name).ratio()

            # Also try first-name-only match (for short inputs)
            first_score = SequenceMatcher(
                None, name_lower, (row["first_name"] or "").lower()
            ).ratio() * 0.8  # Slight penalty for partial match

            best_score = max(score, reverse_score, first_score)

            if best_score >= threshold:
                results.append({
                    "id": str(row["id"]),
                    "name": full_name,
                    "email": row.get("email"),
                    "phone": decrypt_phone(row),
                    "score": best_score,
                })

        # Sort by score descending
        results.sort(key=lambda x: -x["score"])
        return results

    async def _find_todays_booking(self, member_id: str) -> dict | None:
        """Find a confirmed booking for today for this member."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT b.id, b.status, cs.title, cs.starts_at, cs.ends_at
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                WHERE b.member_id = $1
                  AND b.status = 'confirmed'
                  AND cs.starts_at::date = CURRENT_DATE
                ORDER BY cs.starts_at ASC
                LIMIT 1
                """,
                member_id,
            )
        return dict(row) if row else None
