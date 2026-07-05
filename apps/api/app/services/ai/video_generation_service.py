"""AuraFlow — Video Generation Service

Generates personalized milestone celebration videos using HeyGen (primary)
and D-ID (fallback) APIs. Uses Claude Haiku to craft warm, personalized scripts.
Gracefully degrades when API keys are not configured.
"""
from typing import Optional

from app.core.config import settings
from app.core.logging import logger
from app.services.ai.token_tracking_service import track_ai_usage


# Major milestones that warrant video generation
MAJOR_MILESTONES = {"visit_50", "visit_100", "visit_250", "visit_500"}


class VideoGenerationService:

    def _is_heygen_configured(self) -> bool:
        return bool(settings.HEYGEN_API_KEY)

    def _is_did_configured(self) -> bool:
        return bool(settings.DID_API_KEY)

    def _is_any_configured(self) -> bool:
        return self._is_heygen_configured() or self._is_did_configured()

    # ── Public API ──────────────────────────────────────────────────────────

    async def generate_milestone_video(
        self,
        member_name: str,
        milestone_type: str,
        total_visits: int,
        studio_name: str = "the studio",
    ) -> dict:
        """Generate a personalized milestone celebration video.

        Tries HeyGen first, falls back to D-ID if HeyGen fails or is not
        configured. Returns a dict with video_url, provider, video_id, status.
        """
        if not self._is_any_configured():
            logger.warning("Video generation skipped — no provider API keys configured")
            return {
                "video_url": None,
                "provider": None,
                "video_id": None,
                "status": "not_configured",
            }

        # Generate the celebration script via Claude Haiku
        script = await self._build_milestone_script(
            member_name, milestone_type, total_visits, studio_name,
        )

        # Try HeyGen first
        if self._is_heygen_configured():
            try:
                result = await self._generate_heygen_video(script)
                logger.info(
                    "HeyGen video generation initiated",
                    video_id=result.get("video_id"),
                    member_name=member_name,
                    milestone=milestone_type,
                )
                return result
            except Exception as e:
                logger.warning(
                    "HeyGen video generation failed, trying D-ID fallback",
                    error=str(e),
                    milestone=milestone_type,
                )

        # Fallback to D-ID
        if self._is_did_configured():
            try:
                result = await self._generate_did_video(script)
                logger.info(
                    "D-ID video generation initiated",
                    video_id=result.get("video_id"),
                    member_name=member_name,
                    milestone=milestone_type,
                )
                return result
            except Exception as e:
                logger.error(
                    "D-ID video generation also failed",
                    error=str(e),
                    milestone=milestone_type,
                )

        return {
            "video_url": None,
            "provider": None,
            "video_id": None,
            "status": "failed",
        }

    async def check_video_status(self, provider: str, video_id: str) -> dict:
        """Poll the video provider for generation status.

        Returns {status, video_url, provider, video_id}.
        status is one of: processing, completed, failed.
        """
        import httpx

        if provider == "heygen":
            return await self._check_heygen_status(video_id)
        elif provider == "d-id":
            return await self._check_did_status(video_id)
        else:
            return {
                "status": "failed",
                "video_url": None,
                "provider": provider,
                "video_id": video_id,
                "error": f"Unknown provider: {provider}",
            }

    # ── HeyGen ──────────────────────────────────────────────────────────────

    async def _generate_heygen_video(self, script: str) -> dict:
        """Create a video via HeyGen V2 API."""
        import httpx

        payload = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": settings.HEYGEN_AVATAR_ID,
                        "avatar_style": "normal",
                    },
                    "voice": {
                        "type": "text",
                        "input_text": script,
                        "voice_id": "en-US-JennyNeural",
                    },
                    "background": {
                        "type": "color",
                        "value": "#f5f0eb",
                    },
                }
            ],
            "dimension": {"width": 1280, "height": 720},
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.heygen.com/v2/video/generate",
                headers={
                    "X-Api-Key": settings.HEYGEN_API_KEY,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        video_id = data.get("data", {}).get("video_id")
        if not video_id:
            raise ValueError(f"HeyGen did not return a video_id: {data}")

        return {
            "video_url": None,  # Not ready yet — must poll
            "provider": "heygen",
            "video_id": video_id,
            "status": "processing",
        }

    async def _check_heygen_status(self, video_id: str) -> dict:
        """Poll HeyGen for video completion status."""
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://api.heygen.com/v1/video_status.get",
                params={"video_id": video_id},
                headers={"X-Api-Key": settings.HEYGEN_API_KEY},
            )
            response.raise_for_status()
            data = response.json()

        status_data = data.get("data", {})
        heygen_status = status_data.get("status", "")
        video_url = status_data.get("video_url")

        # Map HeyGen statuses to our standard statuses
        if heygen_status == "completed":
            status = "completed"
        elif heygen_status in ("failed", "error"):
            status = "failed"
        else:
            status = "processing"

        return {
            "status": status,
            "video_url": video_url,
            "provider": "heygen",
            "video_id": video_id,
        }

    # ── D-ID ────────────────────────────────────────────────────────────────

    async def _generate_did_video(self, script: str) -> dict:
        """Create a talking-head video via D-ID Talks API."""
        import httpx
        import base64

        # D-ID uses Basic auth with the API key as the password
        auth_str = base64.b64encode(f":{settings.DID_API_KEY}".encode()).decode()

        payload = {
            "source_url": "https://create-images-results.d-id.com/DefaultPresenters/Noelle_f/image.jpeg",
            "script": {
                "type": "text",
                "input": script,
                "provider": {
                    "type": "microsoft",
                    "voice_id": "en-US-JennyNeural",
                },
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.d-id.com/talks",
                headers={
                    "Authorization": f"Basic {auth_str}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        video_id = data.get("id")
        if not video_id:
            raise ValueError(f"D-ID did not return an id: {data}")

        return {
            "video_url": None,  # Not ready yet — must poll
            "provider": "d-id",
            "video_id": video_id,
            "status": "processing",
        }

    async def _check_did_status(self, video_id: str) -> dict:
        """Poll D-ID for video completion status."""
        import httpx
        import base64

        auth_str = base64.b64encode(f":{settings.DID_API_KEY}".encode()).decode()

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"https://api.d-id.com/talks/{video_id}",
                headers={"Authorization": f"Basic {auth_str}"},
            )
            response.raise_for_status()
            data = response.json()

        did_status = data.get("status", "")
        video_url = data.get("result_url")

        # Map D-ID statuses to our standard statuses
        if did_status == "done":
            status = "completed"
        elif did_status in ("error", "rejected"):
            status = "failed"
        else:
            status = "processing"

        return {
            "status": status,
            "video_url": video_url,
            "provider": "d-id",
            "video_id": video_id,
        }

    # ── Script Generation ───────────────────────────────────────────────────

    async def _build_milestone_script(
        self,
        member_name: str,
        milestone_type: str,
        total_visits: int,
        studio_name: str,
    ) -> str:
        """Use Claude Haiku to generate a warm, personalized celebration script.

        Falls back to a static template if Anthropic is not configured.
        """
        if not settings.ANTHROPIC_API_KEY:
            return self._static_milestone_script(
                member_name, milestone_type, total_visits, studio_name,
            )

        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Describe the milestone for the prompt
        if milestone_type.startswith("visit_"):
            count = milestone_type.replace("visit_", "")
            milestone_desc = f"reaching {count} total classes"
        elif milestone_type.startswith("anniversary_"):
            years = milestone_type.replace("anniversary_", "").replace("yr", "")
            milestone_desc = f"their {years}-year membership anniversary"
        else:
            milestone_desc = "a special milestone"

        prompt = (
            f"Write a short, warm celebration script (15-30 seconds when spoken aloud, "
            f"roughly 40-75 words) for a personalized video congratulating a yoga/fitness "
            f"studio member on a milestone.\n\n"
            f"Details:\n"
            f"- Member name: {member_name}\n"
            f"- Milestone: {milestone_desc}\n"
            f"- Total visits so far: {total_visits}\n"
            f"- Studio name: {studio_name}\n\n"
            f"The tone should be genuine, uplifting, and personal. Address the member "
            f"by their first name. Mention the specific achievement. Keep it concise — "
            f"this will be spoken by a video avatar. Do not include stage directions, "
            f"emojis, or formatting. Just the spoken words."
        )

        try:
            message = await client.messages.create(
                model=settings.ANTHROPIC_MODEL_FAST,
                max_tokens=256,
                system=(
                    "You write short, heartfelt celebration scripts for fitness studio "
                    "milestone videos. Keep scripts between 40 and 75 words. "
                    "Output only the spoken text — no labels, no quotes, no formatting."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            await track_ai_usage(
                service_name="video_generation_service",
                function_name="build_milestone_script",
                model=settings.ANTHROPIC_MODEL_FAST,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            )
            script = message.content[0].text.strip()
            logger.info(
                "Milestone script generated via Claude",
                member_name=member_name,
                milestone=milestone_type,
                word_count=len(script.split()),
            )
            return script
        except Exception as e:
            logger.warning(
                "Claude script generation failed, using static template",
                error=str(e),
            )
            return self._static_milestone_script(
                member_name, milestone_type, total_visits, studio_name,
            )

    def _static_milestone_script(
        self,
        member_name: str,
        milestone_type: str,
        total_visits: int,
        studio_name: str,
    ) -> str:
        """Fallback static script when Claude is unavailable."""
        first_name = member_name.split()[0] if member_name else "there"

        if milestone_type.startswith("visit_"):
            count = milestone_type.replace("visit_", "")
            return (
                f"Congratulations, {first_name}! You've just completed your "
                f"{count}th class at {studio_name}. That is an incredible "
                f"achievement, and we are so proud of your dedication. "
                f"Thank you for being such an important part of our community. "
                f"Here's to many more classes together!"
            )
        elif milestone_type.startswith("anniversary_"):
            years = milestone_type.replace("anniversary_", "").replace("yr", "")
            return (
                f"Happy {years}-year anniversary, {first_name}! "
                f"Can you believe it's been {years} years since you joined "
                f"{studio_name}? With {total_visits} classes under your belt, "
                f"you've shown incredible commitment. Thank you for being "
                f"part of our family. Here's to many more years together!"
            )
        else:
            return (
                f"Congratulations, {first_name}! You've reached an amazing "
                f"milestone at {studio_name}. We're so grateful to have you "
                f"in our community. Keep up the wonderful work!"
            )
