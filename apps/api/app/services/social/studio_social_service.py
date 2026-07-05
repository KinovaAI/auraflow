"""AuraFlow — Per-Tenant Studio Social Media Service

Each studio connects their own Facebook Page + Instagram Business account.
Credentials (long-lived page access tokens) are stored pgcrypto-encrypted
inside the tenant schema.  AI generates daily posts from today's schedule
and responds to DMs / comments using Claude.

Tables live in the tenant schema:
  studio_social_accounts  — OAuth connections
  studio_social_posts     — drafts / scheduled / published posts
  studio_social_messages  — DMs, comments, mentions
"""
import json
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.utils.encryption import decrypt_credential, encrypt_credential

GRAPH_API = "https://graph.facebook.com/v19.0"


class StudioSocialService:
    """Per-tenant social media management with AI content & messaging."""

    # ── Account Connection ────────────────────────────────────────────

    async def connect_facebook(
        self, schema: str, access_token: str, page_id: str
    ) -> dict:
        """Exchange short-lived token for long-lived token, verify page
        access, and store encrypted in tenant schema."""

        # Exchange for long-lived token via Graph API
        long_lived_token = access_token
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GRAPH_API}/oauth/access_token",
                    params={
                        "grant_type": "fb_exchange_token",
                        "client_id": settings.META_APP_ID,
                        "client_secret": settings.META_APP_SECRET,
                        "fb_exchange_token": access_token,
                    },
                )
                data = resp.json()
                if "access_token" in data:
                    long_lived_token = data["access_token"]
                    logger.info("Exchanged for long-lived Facebook token", schema=schema)
                else:
                    logger.warning(
                        "Could not exchange token, using short-lived",
                        schema=schema,
                        error=data.get("error", {}),
                    )

                # Verify page access and get page name
                page_resp = await client.get(
                    f"{GRAPH_API}/{page_id}",
                    params={
                        "fields": "name,access_token",
                        "access_token": long_lived_token,
                    },
                )
                page_data = page_resp.json()
                if "error" in page_data:
                    raise ValueError(
                        f"Cannot access page: {page_data['error'].get('message', 'Unknown error')}"
                    )

                page_name = page_data.get("name", "Facebook Page")
                # Use page-specific token if available
                page_token = page_data.get("access_token", long_lived_token)

        except httpx.HTTPError as e:
            logger.error(f"Facebook API error during connect: {e}", schema=schema)
            # Fall back — store what we have, user can fix later
            page_name = "Facebook Page"
            page_token = long_lived_token

        async with get_tenant_db(schema_override=schema) as db:
            token_enc = await encrypt_credential(db, page_token)

            # Upsert — one Facebook account per tenant
            row = await db.fetchrow("""
                INSERT INTO studio_social_accounts
                    (platform, page_id, page_name, access_token_enc, is_active)
                VALUES ('facebook', $1, $2, $3, TRUE)
                ON CONFLICT (platform, page_id)
                DO UPDATE SET
                    page_name = EXCLUDED.page_name,
                    access_token_enc = EXCLUDED.access_token_enc,
                    is_active = TRUE,
                    connected_at = NOW()
                RETURNING *
            """, page_id, page_name, token_enc)

        logger.info("Facebook page connected", schema=schema, page_id=page_id)
        result = dict(row)
        result.pop("access_token_enc", None)
        return result

    async def connect_instagram(
        self, schema: str, instagram_business_id: str
    ) -> dict:
        """Add Instagram Business account alongside existing Facebook
        connection.  Instagram Graph API requires a Facebook Page token."""

        async with get_tenant_db(schema_override=schema) as db:
            # Find the active Facebook account to link
            fb_account = await db.fetchrow("""
                SELECT id, page_id, access_token_enc
                FROM studio_social_accounts
                WHERE platform = 'facebook' AND is_active = TRUE
                LIMIT 1
            """)
            if not fb_account:
                raise ValueError(
                    "Connect Facebook first — Instagram requires a linked Facebook Page"
                )

            token = await decrypt_credential(db, fb_account["access_token_enc"])
            token_enc = await encrypt_credential(db, token)

            # Verify Instagram Business Account
            ig_name = "Instagram"
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{GRAPH_API}/{instagram_business_id}",
                        params={
                            "fields": "name,username",
                            "access_token": token,
                        },
                    )
                    ig_data = resp.json()
                    if "error" not in ig_data:
                        ig_name = ig_data.get("username") or ig_data.get("name", "Instagram")
            except httpx.HTTPError:
                pass

            row = await db.fetchrow("""
                INSERT INTO studio_social_accounts
                    (platform, page_id, page_name, access_token_enc,
                     instagram_business_id, is_active)
                VALUES ('instagram', $1, $2, $3, $4, TRUE)
                ON CONFLICT (platform, page_id)
                DO UPDATE SET
                    page_name = EXCLUDED.page_name,
                    access_token_enc = EXCLUDED.access_token_enc,
                    instagram_business_id = EXCLUDED.instagram_business_id,
                    is_active = TRUE,
                    connected_at = NOW()
                RETURNING *
            """, fb_account["page_id"], ig_name, token_enc, instagram_business_id)

        logger.info(
            "Instagram connected",
            schema=schema,
            ig_id=instagram_business_id,
        )
        result = dict(row)
        result.pop("access_token_enc", None)
        return result

    async def disconnect(self, schema: str, account_id: str) -> bool:
        """Deactivate a social account connection."""
        async with get_tenant_db(schema_override=schema) as db:
            result = await db.execute("""
                UPDATE studio_social_accounts
                SET is_active = FALSE
                WHERE id = $1
            """, account_id)
        return "UPDATE 1" in result

    async def get_status(self, schema: str) -> dict:
        """Return connection status for both platforms."""
        async with get_tenant_db(schema_override=schema) as db:
            accounts = await db.fetch("""
                SELECT id, platform, page_id, page_name,
                       instagram_business_id, is_active, connected_at
                FROM studio_social_accounts
                WHERE is_active = TRUE
                ORDER BY platform
            """)
        result = {
            "facebook": None,
            "instagram": None,
        }
        for acc in accounts:
            result[acc["platform"]] = dict(acc)
        return result

    # ── Posts CRUD ────────────────────────────────────────────────────

    async def create_post(
        self,
        schema: str,
        content: str,
        platform: str,
        media_urls: list[str] | None = None,
        scheduled_at: str | None = None,
    ) -> dict:
        """Create a draft or scheduled social media post."""
        status = "scheduled" if scheduled_at else "draft"

        async with get_tenant_db(schema_override=schema) as db:
            # Find active account for platform
            account = await db.fetchrow("""
                SELECT id FROM studio_social_accounts
                WHERE platform = $1 AND is_active = TRUE LIMIT 1
            """, platform)
            if not account:
                raise ValueError(f"No active {platform} account. Connect {platform} first.")

            row = await db.fetchrow("""
                INSERT INTO studio_social_posts
                    (account_id, platform, content, media_urls, status, scheduled_at)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6::timestamptz)
                RETURNING *
            """, account["id"], platform, content,
                json.dumps(media_urls) if media_urls else None,
                status, scheduled_at)

        return dict(row) if row else {}

    async def generate_ai_post(self, schema: str) -> dict:
        """Use Claude to generate a daily post based on studio context:
        today's classes, events, milestones, studio vibe."""
        if not settings.ANTHROPIC_API_KEY:
            return {
                "content": "[AI not configured] Enable AI to generate social posts.",
                "image_prompt": None,
                "ai_generated": True,
            }

        # Gather studio context
        context_parts = []
        async with get_tenant_db(schema_override=schema) as db:
            # Studio name / info
            org = await db.fetchrow("""
                SELECT name, settings
                FROM studio_info
                LIMIT 1
            """) if await db.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = 'studio_info')"
            ) else None

            studio_name = "the studio"
            if org:
                studio_name = org.get("name", "the studio") or "the studio"
                context_parts.append(f"Studio name: {studio_name}")

            # Today's schedule
            classes = await db.fetch("""
                SELECT c.name, cs.start_time, cs.end_time, i.first_name AS instructor
                FROM class_schedules cs
                JOIN classes c ON c.id = cs.class_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE cs.start_time::date = CURRENT_DATE
                ORDER BY cs.start_time
                LIMIT 10
            """) if await db.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = 'class_schedules')"
            ) else []

            if classes:
                schedule = []
                for c in classes:
                    time_str = c["start_time"].strftime("%I:%M %p") if c["start_time"] else ""
                    instructor = f" with {c['instructor']}" if c.get("instructor") else ""
                    schedule.append(f"- {c['name']} at {time_str}{instructor}")
                context_parts.append("Today's class schedule:\n" + "\n".join(schedule))

            # Upcoming events/workshops
            events = await db.fetch("""
                SELECT name, start_date, description
                FROM courses
                WHERE start_date >= CURRENT_DATE AND start_date <= CURRENT_DATE + INTERVAL '7 days'
                ORDER BY start_date LIMIT 5
            """) if await db.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = 'courses')"
            ) else []

            if events:
                event_list = []
                for e in events:
                    date_str = e["start_date"].strftime("%B %d") if e["start_date"] else ""
                    event_list.append(f"- {e['name']} on {date_str}")
                context_parts.append("Upcoming events/workshops:\n" + "\n".join(event_list))

            # Recent member milestones
            milestones = await db.fetch("""
                SELECT m.first_name, COUNT(a.id) AS visit_count
                FROM members m
                JOIN attendance a ON a.member_id = m.id
                WHERE a.checked_in_at >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY m.id, m.first_name
                HAVING COUNT(a.id) >= 10
                ORDER BY COUNT(a.id) DESC
                LIMIT 3
            """) if await db.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = 'attendance')"
            ) else []

            if milestones:
                m_list = [f"- {m['first_name']}: {m['visit_count']} visits this month" for m in milestones]
                context_parts.append("Member highlights:\n" + "\n".join(m_list))

        context = "\n\n".join(context_parts) if context_parts else f"Studio: {studio_name}"

        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL_FAST,
            max_tokens=600,
            system=(
                f"You are the social media manager for {studio_name}, a yoga/fitness studio. "
                "Write warm, authentic social media posts that build community. "
                "Include 1-2 relevant emojis. For Instagram, add 5-8 hashtags. "
                "Keep the tone friendly, motivational, and approachable. "
                "Never use the word 'journey'. Be specific about today's offerings."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Write an engaging social media post for today based on this context:\n\n"
                    f"{context}\n\n"
                    "Also suggest a brief image description (for AI image generation) on a separate "
                    "line starting with 'IMAGE PROMPT:'"
                ),
            }],
        )

        # Track AI usage
        from app.services.ai.token_tracking_service import track_ai_usage
        await track_ai_usage(
            service_name="studio_social",
            function_name="generate_ai_post",
            model=settings.ANTHROPIC_MODEL_FAST,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        full_text = response.content[0].text if response.content else ""

        # Split content and image prompt
        content = full_text
        image_prompt = None
        if "IMAGE PROMPT:" in full_text:
            parts = full_text.split("IMAGE PROMPT:", 1)
            content = parts[0].strip()
            image_prompt = parts[1].strip()

        return {
            "content": content,
            "image_prompt": image_prompt,
            "ai_generated": True,
        }

    async def publish_post(self, schema: str, post_id: str) -> dict:
        """Publish a post to Facebook or Instagram via Graph API."""
        async with get_tenant_db(schema_override=schema) as db:
            post = await db.fetchrow(
                "SELECT * FROM studio_social_posts WHERE id = $1", post_id
            )
            if not post:
                raise ValueError("Post not found")

            account = await db.fetchrow(
                "SELECT * FROM studio_social_accounts WHERE id = $1 AND is_active = TRUE",
                post["account_id"],
            )
            if not account:
                raise ValueError("Social account not found or inactive")

            access_token = await decrypt_credential(db, account["access_token_enc"])

        try:
            async with httpx.AsyncClient() as client:
                if post["platform"] == "facebook":
                    resp = await client.post(
                        f"{GRAPH_API}/{account['page_id']}/feed",
                        params={
                            "message": post["content"],
                            "access_token": access_token,
                        },
                    )
                elif post["platform"] == "instagram":
                    ig_id = account["instagram_business_id"]
                    if not ig_id:
                        raise ValueError("Instagram Business ID not configured")

                    media_urls = post.get("media_urls") or []
                    if isinstance(media_urls, str):
                        media_urls = json.loads(media_urls)
                    if not media_urls:
                        raise ValueError("Instagram posts require at least one media URL")

                    # Create media container
                    resp = await client.post(
                        f"{GRAPH_API}/{ig_id}/media",
                        params={
                            "image_url": media_urls[0],
                            "caption": post["content"],
                            "access_token": access_token,
                        },
                    )
                    container_id = resp.json().get("id")
                    if not container_id:
                        raise ValueError(
                            f"Failed to create Instagram media container: {resp.json()}"
                        )
                    # Publish container
                    resp = await client.post(
                        f"{GRAPH_API}/{ig_id}/media_publish",
                        params={
                            "creation_id": container_id,
                            "access_token": access_token,
                        },
                    )
                else:
                    raise ValueError(f"Unknown platform: {post['platform']}")

                resp_data = resp.json()
                if "error" in resp_data:
                    raise ValueError(resp_data["error"].get("message", "API error"))

                platform_post_id = resp_data.get("id", "")

                async with get_tenant_db(schema_override=schema) as db:
                    row = await db.fetchrow("""
                        UPDATE studio_social_posts
                        SET status = 'published',
                            platform_post_id = $2,
                            published_at = NOW()
                        WHERE id = $1 RETURNING *
                    """, post_id, platform_post_id)

                logger.info(
                    "Published social post",
                    schema=schema,
                    platform=post["platform"],
                    post_id=platform_post_id,
                )
                return dict(row) if row else {}

        except httpx.HTTPError as e:
            async with get_tenant_db(schema_override=schema) as db:
                await db.execute(
                    "UPDATE studio_social_posts SET status = 'failed' WHERE id = $1",
                    post_id,
                )
            logger.error(f"Failed to publish post: {e}", schema=schema)
            raise ValueError(f"Publish failed: {str(e)[:200]}")

    async def list_posts(
        self, schema: str, status: str | None = None, limit: int = 20
    ) -> list[dict]:
        async with get_tenant_db(schema_override=schema) as db:
            if status:
                rows = await db.fetch("""
                    SELECT * FROM studio_social_posts
                    WHERE status = $1
                    ORDER BY created_at DESC LIMIT $2
                """, status, limit)
            else:
                rows = await db.fetch("""
                    SELECT * FROM studio_social_posts
                    ORDER BY created_at DESC LIMIT $1
                """, limit)
        return [dict(r) for r in rows]

    async def delete_post(self, schema: str, post_id: str) -> bool:
        async with get_tenant_db(schema_override=schema) as db:
            result = await db.execute(
                "DELETE FROM studio_social_posts WHERE id = $1 AND status != 'published'",
                post_id,
            )
        return "DELETE 1" in result

    # ── Messages ─────────────────────────────────────────────────────

    async def fetch_messages(self, schema: str) -> int:
        """Fetch new DMs and comments from Facebook/Instagram Graph API.
        Returns number of new messages stored."""
        async with get_tenant_db(schema_override=schema) as db:
            accounts = await db.fetch("""
                SELECT * FROM studio_social_accounts WHERE is_active = TRUE
            """)

        if not accounts:
            return 0

        total = 0
        for account in accounts:
            try:
                async with get_tenant_db(schema_override=schema) as db:
                    access_token = await decrypt_credential(db, account["access_token_enc"])

                async with httpx.AsyncClient() as client:
                    if account["platform"] == "facebook":
                        total += await self._fetch_facebook_messages(
                            schema, account, access_token, client
                        )
                        total += await self._fetch_facebook_comments(
                            schema, account, access_token, client
                        )
                    elif account["platform"] == "instagram" and account.get("instagram_business_id"):
                        total += await self._fetch_instagram_comments(
                            schema, account, access_token, client
                        )

            except Exception as e:
                logger.error(
                    f"Failed to fetch messages for account {account['id']}: {e}",
                    schema=schema,
                )

        return total

    async def _fetch_facebook_messages(
        self, schema: str, account: dict, token: str, client: httpx.AsyncClient
    ) -> int:
        """Fetch Facebook Page conversations / DMs."""
        count = 0
        try:
            resp = await client.get(
                f"{GRAPH_API}/{account['page_id']}/conversations",
                params={
                    "fields": "id,messages.limit(5){id,from,message,created_time}",
                    "access_token": token,
                },
            )
            data = resp.json()
            conversations = data.get("data", [])

            async with get_tenant_db(schema_override=schema) as db:
                for convo in conversations:
                    convo_id = convo.get("id")
                    for msg in convo.get("messages", {}).get("data", []):
                        # Skip messages from our own page
                        sender_id = msg.get("from", {}).get("id", "")
                        if sender_id == account["page_id"]:
                            continue

                        # Check if already stored
                        exists = await db.fetchval(
                            "SELECT 1 FROM studio_social_messages WHERE conversation_id = $1 AND sender_id = $2 AND message_text = $3",
                            convo_id, sender_id, msg.get("message", ""),
                        )
                        if exists:
                            continue

                        await db.execute("""
                            INSERT INTO studio_social_messages
                                (account_id, platform, conversation_id, sender_id,
                                 sender_name, message_text, message_type, received_at)
                            VALUES ($1, 'facebook', $2, $3, $4, $5, 'message', $6::timestamptz)
                        """,
                            account["id"], convo_id, sender_id,
                            msg.get("from", {}).get("name", ""),
                            msg.get("message", ""),
                            msg.get("created_time"),
                        )
                        count += 1

        except Exception as e:
            logger.debug(f"Facebook messages fetch error: {e}")
        return count

    async def _fetch_facebook_comments(
        self, schema: str, account: dict, token: str, client: httpx.AsyncClient
    ) -> int:
        """Fetch comments on recent Facebook posts."""
        count = 0
        try:
            async with get_tenant_db(schema_override=schema) as db:
                recent_posts = await db.fetch("""
                    SELECT id, platform_post_id FROM studio_social_posts
                    WHERE platform = 'facebook' AND status = 'published'
                      AND platform_post_id IS NOT NULL
                    ORDER BY published_at DESC LIMIT 10
                """)

            for post in recent_posts:
                resp = await client.get(
                    f"{GRAPH_API}/{post['platform_post_id']}/comments",
                    params={
                        "fields": "id,from,message,created_time",
                        "access_token": token,
                        "limit": 25,
                    },
                )
                comments = resp.json().get("data", [])

                async with get_tenant_db(schema_override=schema) as db:
                    for comment in comments:
                        sender_id = comment.get("from", {}).get("id", "")
                        if sender_id == account["page_id"]:
                            continue

                        exists = await db.fetchval(
                            "SELECT 1 FROM studio_social_messages WHERE conversation_id = $1 AND sender_id = $2",
                            comment.get("id"), sender_id,
                        )
                        if exists:
                            continue

                        await db.execute("""
                            INSERT INTO studio_social_messages
                                (account_id, platform, conversation_id, sender_id,
                                 sender_name, message_text, message_type, post_id, received_at)
                            VALUES ($1, 'facebook', $2, $3, $4, $5, 'comment', $6, $7::timestamptz)
                        """,
                            account["id"], comment.get("id"), sender_id,
                            comment.get("from", {}).get("name", ""),
                            comment.get("message", ""),
                            post["id"],
                            comment.get("created_time"),
                        )
                        count += 1

        except Exception as e:
            logger.debug(f"Facebook comments fetch error: {e}")
        return count

    async def _fetch_instagram_comments(
        self, schema: str, account: dict, token: str, client: httpx.AsyncClient
    ) -> int:
        """Fetch comments on recent Instagram media."""
        count = 0
        try:
            ig_id = account["instagram_business_id"]
            resp = await client.get(
                f"{GRAPH_API}/{ig_id}/media",
                params={
                    "fields": "id,comments{id,from,text,timestamp,username}",
                    "access_token": token,
                    "limit": 10,
                },
            )
            media_items = resp.json().get("data", [])

            async with get_tenant_db(schema_override=schema) as db:
                for media in media_items:
                    for comment in media.get("comments", {}).get("data", []):
                        comment_id = comment.get("id")
                        exists = await db.fetchval(
                            "SELECT 1 FROM studio_social_messages WHERE conversation_id = $1",
                            comment_id,
                        )
                        if exists:
                            continue

                        await db.execute("""
                            INSERT INTO studio_social_messages
                                (account_id, platform, conversation_id, sender_id,
                                 sender_name, message_text, message_type, received_at)
                            VALUES ($1, 'instagram', $2, $3, $4, $5, 'comment', $6::timestamptz)
                        """,
                            account["id"], comment_id,
                            comment.get("from", {}).get("id", comment.get("username", "")),
                            comment.get("username", comment.get("from", {}).get("username", "")),
                            comment.get("text", ""),
                            comment.get("timestamp"),
                        )
                        count += 1

        except Exception as e:
            logger.debug(f"Instagram comments fetch error: {e}")
        return count

    async def handle_message_with_ai(self, schema: str, message_id: str) -> dict:
        """Use Claude to craft a response to a social message/comment.
        Classification determines the action:
          - schedule/class/pricing questions -> look up data, respond
          - complaints -> flag for human review
          - general -> respond helpfully
        """
        async with get_tenant_db(schema_override=schema) as db:
            msg = await db.fetchrow(
                "SELECT * FROM studio_social_messages WHERE id = $1", message_id
            )
        if not msg:
            raise ValueError("Message not found")

        if not settings.ANTHROPIC_API_KEY:
            return {"status": "error", "detail": "AI not configured"}

        # Gather studio context for answering questions
        context_parts = []
        async with get_tenant_db(schema_override=schema) as db:
            # Studio name
            studio_name = "our studio"
            org = await db.fetchrow("SELECT name FROM studio_info LIMIT 1") if await db.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = 'studio_info')"
            ) else None
            if org:
                studio_name = org.get("name", "our studio") or "our studio"

            # Today's schedule
            if await db.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = 'class_schedules')"
            ):
                classes = await db.fetch("""
                    SELECT c.name, cs.start_time, cs.end_time
                    FROM class_schedules cs
                    JOIN classes c ON c.id = cs.class_id
                    WHERE cs.start_time::date = CURRENT_DATE
                    ORDER BY cs.start_time LIMIT 15
                """)
                if classes:
                    sched = "\n".join(
                        f"- {c['name']} at {c['start_time'].strftime('%I:%M %p')}"
                        for c in classes
                    )
                    context_parts.append(f"Today's schedule:\n{sched}")

            # Membership/pricing info
            if await db.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = 'membership_plans')"
            ):
                plans = await db.fetch("""
                    SELECT name, price, billing_interval, description
                    FROM membership_plans
                    WHERE is_active = TRUE
                    ORDER BY price LIMIT 10
                """)
                if plans:
                    pricing = "\n".join(
                        f"- {p['name']}: ${p['price']}/{p.get('billing_interval', 'month')}"
                        for p in plans
                    )
                    context_parts.append(f"Membership options:\n{pricing}")

        context = "\n\n".join(context_parts) if context_parts else ""

        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL_FAST,
            max_tokens=400,
            system=(
                f"You are the social media assistant for {studio_name}, a yoga/fitness studio. "
                "Respond to the following social media message.\n\n"
                "RULES:\n"
                "- If asking about classes/schedule: provide info from the context below\n"
                "- If asking about pricing/memberships: share the options\n"
                "- If this is a complaint or angry message: respond with 'FLAG_FOR_HUMAN' only\n"
                "- For compliments: thank them warmly\n"
                "- For general questions: be helpful and friendly\n"
                "- Keep responses concise (1-3 sentences)\n"
                f"- Sign off as {studio_name}\n\n"
                f"STUDIO INFO:\n{context}"
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Message from {msg['sender_name'] or 'someone'} "
                    f"(type: {msg['message_type']}):\n\n"
                    f"{msg['message_text']}"
                ),
            }],
        )

        # Track usage
        from app.services.ai.token_tracking_service import track_ai_usage
        await track_ai_usage(
            service_name="studio_social",
            function_name="handle_message_with_ai",
            model=settings.ANTHROPIC_MODEL_FAST,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        ai_text = response.content[0].text if response.content else ""
        flagged = "FLAG_FOR_HUMAN" in ai_text

        async with get_tenant_db(schema_override=schema) as db:
            if flagged:
                row = await db.fetchrow("""
                    UPDATE studio_social_messages
                    SET ai_status = 'flagged',
                        ai_response = 'Flagged for human review — possible complaint'
                    WHERE id = $1 RETURNING *
                """, message_id)
            else:
                row = await db.fetchrow("""
                    UPDATE studio_social_messages
                    SET ai_status = 'resolved', ai_response = $2, responded_at = NOW()
                    WHERE id = $1 RETURNING *
                """, message_id, ai_text)

        result = dict(row) if row else {}

        # Auto-send response if not flagged and we have a conversation ID
        if not flagged and msg.get("conversation_id") and ai_text:
            try:
                await self.respond_to_message(schema, message_id, ai_text)
            except Exception as e:
                logger.warning(f"Auto-reply delivery failed: {e}", schema=schema)

        return result

    async def list_messages(
        self, schema: str, status: str | None = None, limit: int = 20
    ) -> list[dict]:
        async with get_tenant_db(schema_override=schema) as db:
            if status:
                rows = await db.fetch("""
                    SELECT * FROM studio_social_messages
                    WHERE ai_status = $1
                    ORDER BY received_at DESC NULLS LAST, created_at DESC
                    LIMIT $2
                """, status, limit)
            else:
                rows = await db.fetch("""
                    SELECT * FROM studio_social_messages
                    ORDER BY received_at DESC NULLS LAST, created_at DESC
                    LIMIT $1
                """, limit)
        return [dict(r) for r in rows]

    async def respond_to_message(
        self, schema: str, message_id: str, response_text: str
    ) -> dict:
        """Send a manual response via Graph API."""
        async with get_tenant_db(schema_override=schema) as db:
            msg = await db.fetchrow(
                "SELECT * FROM studio_social_messages WHERE id = $1", message_id
            )
            if not msg:
                raise ValueError("Message not found")

            account = await db.fetchrow(
                "SELECT * FROM studio_social_accounts WHERE id = $1",
                msg["account_id"],
            )
            if not account:
                raise ValueError("Social account not found")

            access_token = await decrypt_credential(db, account["access_token_enc"])

        # Send reply via Graph API
        if msg["message_type"] == "message" and msg.get("conversation_id"):
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{GRAPH_API}/{msg['conversation_id']}/messages",
                        params={
                            "message": response_text,
                            "access_token": access_token,
                        },
                    )
            except httpx.HTTPError as e:
                logger.error(f"Failed to send social reply: {e}", schema=schema)
        elif msg["message_type"] == "comment" and msg.get("conversation_id"):
            # Reply to comment
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{GRAPH_API}/{msg['conversation_id']}/comments",
                        params={
                            "message": response_text,
                            "access_token": access_token,
                        },
                    )
            except httpx.HTTPError as e:
                logger.error(f"Failed to reply to comment: {e}", schema=schema)

        async with get_tenant_db(schema_override=schema) as db:
            row = await db.fetchrow("""
                UPDATE studio_social_messages
                SET ai_status = 'resolved', ai_response = $2, responded_at = NOW()
                WHERE id = $1 RETURNING *
            """, message_id, response_text)

        return dict(row) if row else {}

    # ── Engagement Stats ─────────────────────────────────────────────

    async def get_engagement_stats(self, schema: str) -> dict:
        """Aggregate engagement stats across published posts and messages."""
        async with get_tenant_db(schema_override=schema) as db:
            # Post engagement
            posts = await db.fetch("""
                SELECT engagement FROM studio_social_posts
                WHERE status = 'published' AND engagement IS NOT NULL
                  AND engagement != '{}'::jsonb
            """)

            total_likes = 0
            total_comments = 0
            total_shares = 0
            for p in posts:
                eng = p["engagement"] if isinstance(p["engagement"], dict) else json.loads(p["engagement"]) if p["engagement"] else {}
                total_likes += eng.get("likes", 0)
                total_comments += eng.get("comments", 0)
                total_shares += eng.get("shares", 0)

            # Message counts
            msg_stats = await db.fetchrow("""
                SELECT
                    COUNT(*) AS total_messages,
                    COUNT(*) FILTER (WHERE ai_status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE ai_status = 'resolved') AS resolved,
                    COUNT(*) FILTER (WHERE ai_status = 'flagged') AS flagged
                FROM studio_social_messages
            """)

            # Post counts
            post_stats = await db.fetchrow("""
                SELECT
                    COUNT(*) AS total_posts,
                    COUNT(*) FILTER (WHERE status = 'published') AS published,
                    COUNT(*) FILTER (WHERE status = 'draft') AS drafts,
                    COUNT(*) FILTER (WHERE status = 'scheduled') AS scheduled,
                    COUNT(*) FILTER (WHERE ai_generated = TRUE) AS ai_generated
                FROM studio_social_posts
            """)

        return {
            "engagement": {
                "likes": total_likes,
                "comments": total_comments,
                "shares": total_shares,
            },
            "messages": dict(msg_stats) if msg_stats else {},
            "posts": dict(post_stats) if post_stats else {},
        }

    # ── Sync Engagement from Platform ─────────────────────────────────

    async def sync_engagement(self, schema: str) -> int:
        """Pull latest engagement metrics for published posts."""
        async with get_tenant_db(schema_override=schema) as db:
            posts = await db.fetch("""
                SELECT sp.id, sp.platform, sp.platform_post_id, sa.access_token_enc
                FROM studio_social_posts sp
                JOIN studio_social_accounts sa ON sa.id = sp.account_id
                WHERE sp.status = 'published' AND sp.platform_post_id IS NOT NULL
                ORDER BY sp.published_at DESC LIMIT 50
            """)

        updated = 0
        for post in posts:
            try:
                async with get_tenant_db(schema_override=schema) as db:
                    token = await decrypt_credential(db, post["access_token_enc"])

                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{GRAPH_API}/{post['platform_post_id']}",
                        params={
                            "fields": "likes.summary(true),comments.summary(true),shares",
                            "access_token": token,
                        },
                    )
                    data = resp.json()
                    engagement = {
                        "likes": data.get("likes", {}).get("summary", {}).get("total_count", 0),
                        "comments": data.get("comments", {}).get("summary", {}).get("total_count", 0),
                        "shares": data.get("shares", {}).get("count", 0),
                    }

                async with get_tenant_db(schema_override=schema) as db:
                    await db.execute("""
                        UPDATE studio_social_posts
                        SET engagement = $2::jsonb
                        WHERE id = $1
                    """, post["id"], json.dumps(engagement))
                updated += 1

            except Exception as e:
                logger.debug(f"Engagement sync failed for post {post['id']}: {e}")

        return updated

    # ── Helpers for Celery ────────────────────────────────────────────

    @staticmethod
    async def get_all_active_accounts() -> list[dict]:
        """Return all tenant schemas with active social accounts.
        Used by Celery polling task."""
        from app.db.session import get_global_db

        async with get_global_db() as db:
            schemas = await db.fetch(
                "SELECT schema_name FROM af_global.organizations WHERE status IN ('active', 'trial')"
            )

        results = []
        for row in schemas:
            schema = row["schema_name"]
            try:
                async with get_tenant_db(schema_override=schema) as db:
                    accounts = await db.fetch("""
                        SELECT id, platform FROM studio_social_accounts
                        WHERE is_active = TRUE
                    """)
                    if accounts:
                        results.append({
                            "schema": schema,
                            "accounts": [dict(a) for a in accounts],
                        })
            except Exception:
                pass

        return results
