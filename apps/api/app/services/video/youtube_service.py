"""AuraFlow — YouTube Service (BYOA)

Studios connect their own YouTube API key + channel ID.
We fetch video metadata via YouTube Data API v3 and sync
into the tenant's videos table. OAuth 2.0 for uploads.
"""
import json
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.utils.encryption import encrypt_credential, decrypt_credential

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_UPLOAD_SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"


class YouTubeService:

    # ── Credential Management ──────────────────────────────────────────────

    async def save_credentials(self, org_id: str, api_key: str, channel_id: str) -> None:
        """Encrypt and store YouTube credentials on the org."""
        async with get_global_db() as db:
            encrypted_key = await encrypt_credential(db, api_key)
            await db.execute(
                """
                UPDATE af_global.organizations
                SET youtube_api_key_encrypted = $1,
                    youtube_channel_id = $2,
                    youtube_connected_at = NOW(),
                    updated_at = NOW()
                WHERE id = $3
                """,
                encrypted_key, channel_id, org_id,
            )
        logger.info("YouTube connected", org_id=org_id, channel_id=channel_id)

    async def get_credentials(self, org_id: str) -> Optional[dict]:
        """Decrypt and return YouTube credentials, or None if not connected."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT youtube_api_key_encrypted, youtube_channel_id, youtube_connected_at
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
            if not row or not row["youtube_api_key_encrypted"]:
                return None
            api_key = await decrypt_credential(db, row["youtube_api_key_encrypted"])
            return {
                "api_key": api_key,
                "channel_id": row["youtube_channel_id"],
                "connected_at": row["youtube_connected_at"],
            }

    async def remove_credentials(self, org_id: str) -> None:
        """Clear YouTube credentials from the org."""
        async with get_global_db() as db:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET youtube_api_key_encrypted = NULL,
                    youtube_channel_id = NULL,
                    youtube_connected_at = NULL,
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id,
            )
        logger.info("YouTube disconnected", org_id=org_id)

    # ── YouTube API Calls ──────────────────────────────────────────────────

    async def test_connection(self, api_key: str, channel_id: str) -> dict:
        """Test YouTube credentials by fetching channel info."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{YOUTUBE_API_BASE}/channels",
                params={
                    "key": api_key,
                    "id": channel_id,
                    "part": "snippet,statistics",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                error = resp.json().get("error", {}).get("message", "Unknown error")
                return {"success": False, "error": error}

            data = resp.json()
            items = data.get("items", [])
            if not items:
                return {"success": False, "error": "Channel not found"}

            ch = items[0]["snippet"]
            return {
                "success": True,
                "channel_title": ch.get("title"),
                "channel_thumbnail": ch.get("thumbnails", {}).get("default", {}).get("url"),
                "video_count": items[0].get("statistics", {}).get("videoCount"),
            }

    async def fetch_channel_videos(
        self, api_key: str, channel_id: str, max_results: int = 50
    ) -> list[dict]:
        """Fetch videos from a YouTube channel."""
        videos = []
        page_token = None

        async with httpx.AsyncClient() as client:
            while len(videos) < max_results:
                params = {
                    "key": api_key,
                    "channelId": channel_id,
                    "part": "snippet",
                    "type": "video",
                    "order": "date",
                    "maxResults": min(50, max_results - len(videos)),
                }
                if page_token:
                    params["pageToken"] = page_token

                resp = await client.get(
                    f"{YOUTUBE_API_BASE}/search",
                    params=params,
                    timeout=15,
                )
                if resp.status_code != 200:
                    logger.error("YouTube search failed", status=resp.status_code)
                    break

                data = resp.json()
                video_ids = []
                for item in data.get("items", []):
                    vid_id = item.get("id", {}).get("videoId")
                    if vid_id:
                        video_ids.append(vid_id)

                if video_ids:
                    details = await self._fetch_video_details(client, api_key, video_ids)
                    videos.extend(details)

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        return videos

    async def _fetch_video_details(
        self, client: httpx.AsyncClient, api_key: str, video_ids: list[str]
    ) -> list[dict]:
        """Fetch detailed metadata for a list of video IDs."""
        resp = await client.get(
            f"{YOUTUBE_API_BASE}/videos",
            params={
                "key": api_key,
                "id": ",".join(video_ids),
                "part": "snippet,contentDetails,status",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        results = []
        for item in resp.json().get("items", []):
            snippet = item["snippet"]
            content = item.get("contentDetails", {})
            status = item.get("status", {})

            duration_seconds = self._parse_duration(content.get("duration", ""))
            embeddable = status.get("embeddable", True)

            results.append({
                "youtube_video_id": item["id"],
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "thumbnail_url": (
                    snippet.get("thumbnails", {}).get("high", {}).get("url")
                    or snippet.get("thumbnails", {}).get("medium", {}).get("url")
                    or snippet.get("thumbnails", {}).get("default", {}).get("url")
                ),
                "duration_seconds": duration_seconds,
                "published_at": snippet.get("publishedAt"),
                "embeddable": embeddable,
            })
        return results

    @staticmethod
    def _parse_duration(iso_duration: str) -> int:
        """Parse ISO 8601 duration (PT1H30M15S) into seconds."""
        if not iso_duration or not iso_duration.startswith("PT"):
            return 0
        s = iso_duration[2:]
        hours = minutes = seconds = 0
        for unit, char in [("H", "hours"), ("M", "minutes"), ("S", "seconds")]:
            if unit in s:
                val, s = s.split(unit)
                if char == "hours":
                    hours = int(val)
                elif char == "minutes":
                    minutes = int(val)
                elif char == "seconds":
                    seconds = int(val)
        return hours * 3600 + minutes * 60 + seconds

    # ── Sync ───────────────────────────────────────────────────────────────

    async def _fetch_videos_oauth(self, org_id: str, channel_id: str) -> list[dict]:
        """Fetch videos using OAuth (includes unlisted videos)."""
        refresh_token = await self.get_oauth_credentials(org_id)
        if not refresh_token:
            return []

        access_token = await self._get_access_token(refresh_token)
        videos = []

        # Get uploads playlist (UC → UU)
        uploads_playlist = "UU" + channel_id[2:]

        async with httpx.AsyncClient() as client:
            page_token = None
            while True:
                params = {
                    "playlistId": uploads_playlist,
                    "part": "snippet,contentDetails",
                    "maxResults": 50,
                }
                if page_token:
                    params["pageToken"] = page_token

                resp = await client.get(
                    f"{YOUTUBE_API_BASE}/playlistItems",
                    params=params,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=15,
                )
                if resp.status_code != 200:
                    logger.error("YouTube OAuth playlist fetch failed", status=resp.status_code, body=resp.text[:200])
                    break

                data = resp.json()
                video_ids = []
                for item in data.get("items", []):
                    vid_id = item.get("contentDetails", {}).get("videoId")
                    if vid_id:
                        video_ids.append(vid_id)

                if video_ids:
                    # Fetch full details with OAuth
                    resp2 = await client.get(
                        f"{YOUTUBE_API_BASE}/videos",
                        params={
                            "id": ",".join(video_ids),
                            "part": "snippet,contentDetails,status",
                        },
                        headers={"Authorization": f"Bearer {access_token}"},
                        timeout=15,
                    )
                    if resp2.status_code == 200:
                        for v in resp2.json().get("items", []):
                            videos.append({
                                "youtube_video_id": v["id"],
                                "title": v["snippet"]["title"],
                                "description": v["snippet"].get("description", ""),
                                "thumbnail_url": v["snippet"].get("thumbnails", {}).get("high", {}).get("url")
                                    or v["snippet"].get("thumbnails", {}).get("default", {}).get("url", ""),
                                "duration_seconds": self._parse_duration(
                                    v.get("contentDetails", {}).get("duration", "PT0S")
                                ),
                                "privacy": v.get("status", {}).get("privacyStatus", "unlisted"),
                            })

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        logger.info("YouTube OAuth fetch complete", count=len(videos))
        return videos

    async def sync_videos(self, org_id: str) -> dict:
        """Fetch all YouTube videos and upsert into tenant videos table."""
        creds = await self.get_credentials(org_id)
        if not creds:
            return {"synced": 0, "new": 0, "updated": 0, "source": "youtube"}

        # Try OAuth first (gets unlisted videos), fall back to API key (public only)
        oauth_token = await self.get_oauth_credentials(org_id)
        if oauth_token:
            videos = await self._fetch_videos_oauth(org_id, creds["channel_id"])
        else:
            videos = await self.fetch_channel_videos(creds["api_key"], creds["channel_id"])
        new_count = 0
        updated_count = 0

        async with get_tenant_db() as db:
            for v in videos:
                existing = await db.fetchrow(
                    "SELECT id FROM videos WHERE youtube_video_id = $1",
                    v["youtube_video_id"],
                )
                if existing:
                    await db.execute(
                        """
                        UPDATE videos
                        SET title = $1, description = $2, thumbnail_url = $3,
                            duration_seconds = $4, updated_at = NOW()
                        WHERE youtube_video_id = $5
                        """,
                        v["title"], v["description"], v["thumbnail_url"],
                        v["duration_seconds"], v["youtube_video_id"],
                    )
                    updated_count += 1
                else:
                    await db.execute(
                        """
                        INSERT INTO videos
                            (source, external_id, youtube_video_id, title, description,
                             thumbnail_url, duration_seconds, is_published)
                        VALUES ('youtube', $1, $1, $2, $3, $4, $5, TRUE)
                        """,
                        v["youtube_video_id"], v["title"], v["description"],
                        v["thumbnail_url"], v["duration_seconds"],
                    )
                    new_count += 1

        # Remove videos that no longer exist on YouTube
        removed_count = 0
        youtube_ids = {v["youtube_video_id"] for v in videos}
        async with get_tenant_db() as db:
            db_videos = await db.fetch(
                "SELECT id, youtube_video_id FROM videos WHERE source = 'youtube' AND youtube_video_id IS NOT NULL"
            )
            for dbv in db_videos:
                if dbv["youtube_video_id"] not in youtube_ids:
                    await db.execute("DELETE FROM videos WHERE id = $1", dbv["id"])
                    removed_count += 1

        total = new_count + updated_count
        logger.info("YouTube sync complete", org_id=org_id, new=new_count, updated=updated_count, removed=removed_count)
        return {"synced": total, "new": new_count, "updated": updated_count, "removed": removed_count, "source": "youtube"}

    # ── OAuth 2.0 (for uploads) ─────────────────────────────────────────

    def get_oauth_url(self, org_id: str) -> str:
        """Generate Google OAuth consent URL for YouTube upload authorization."""
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": f"{settings.API_URL}/api/v1/video/connect/youtube/oauth/callback",
            "response_type": "code",
            "scope": YOUTUBE_UPLOAD_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": org_id,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def handle_oauth_callback(self, org_id: str, code: str) -> dict:
        """Exchange authorization code for tokens and store refresh token."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": f"{settings.API_URL}/api/v1/video/connect/youtube/oauth/callback",
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                error = resp.json().get("error_description", "OAuth token exchange failed")
                raise ValueError(error)

            tokens = resp.json()
            refresh_token = tokens.get("refresh_token")
            if not refresh_token:
                raise ValueError("No refresh token received — try revoking access and re-authorizing")

        async with get_global_db() as db:
            encrypted = await encrypt_credential(db, refresh_token)
            await db.execute(
                """
                UPDATE af_global.organizations
                SET youtube_refresh_token_encrypted = $1, updated_at = NOW()
                WHERE id = $2
                """,
                encrypted, org_id,
            )

        logger.info("YouTube OAuth authorized for uploads", org_id=org_id)
        return {"authorized": True}

    async def get_oauth_credentials(self, org_id: str) -> Optional[str]:
        """Get decrypted refresh token, or None if not authorized."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                "SELECT youtube_refresh_token_encrypted FROM af_global.organizations WHERE id = $1",
                org_id,
            )
            if not row or not row["youtube_refresh_token_encrypted"]:
                return None
            return await decrypt_credential(db, row["youtube_refresh_token_encrypted"])

    async def _get_access_token(self, refresh_token: str) -> str:
        """Use refresh token to get a fresh access token."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                raise ValueError("Failed to refresh YouTube access token")
            return resp.json()["access_token"]

    async def upload_video(
        self,
        org_id: str,
        file_content: bytes,
        title: str,
        description: str = "",
        privacy: str = "unlisted",
    ) -> dict:
        """Upload a video to the org's YouTube channel via resumable upload."""
        refresh_token = await self.get_oauth_credentials(org_id)
        if not refresh_token:
            raise ValueError("YouTube not authorized for uploads — complete OAuth setup first")

        access_token = await self._get_access_token(refresh_token)

        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": "10",  # Music (closest to fitness)
            },
            "status": {
                "privacyStatus": privacy,
            },
        }

        async with httpx.AsyncClient() as client:
            # Step 1: Initiate resumable upload
            init_resp = await client.post(
                f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": "video/*",
                    "X-Upload-Content-Length": str(len(file_content)),
                },
                content=json.dumps(metadata),
                timeout=30,
            )
            if init_resp.status_code not in (200, 308):
                error = init_resp.text
                logger.error("YouTube upload init failed", status=init_resp.status_code, error=error)
                raise ValueError(f"YouTube upload init failed: {init_resp.status_code}")

            upload_url = init_resp.headers.get("Location")
            if not upload_url:
                raise ValueError("No upload URL returned by YouTube")

            # Step 2: Upload the actual file
            upload_resp = await client.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "video/*",
                    "Content-Length": str(len(file_content)),
                },
                content=file_content,
                timeout=600,
            )
            if upload_resp.status_code not in (200, 201):
                logger.error("YouTube upload failed", status=upload_resp.status_code)
                raise ValueError(f"YouTube upload failed: {upload_resp.status_code}")

            video_data = upload_resp.json()
            youtube_video_id = video_data["id"]

        # Create video entry in tenant DB
        async with get_tenant_db() as db:
            thumbnail = (
                video_data.get("snippet", {}).get("thumbnails", {}).get("high", {}).get("url")
                or video_data.get("snippet", {}).get("thumbnails", {}).get("default", {}).get("url")
                or ""
            )
            await db.execute(
                """
                INSERT INTO videos
                    (source, external_id, youtube_video_id, title, description,
                     thumbnail_url, is_published)
                VALUES ('youtube', $1, $1, $2, $3, $4, TRUE)
                ON CONFLICT (youtube_video_id) DO UPDATE
                SET title = EXCLUDED.title, description = EXCLUDED.description,
                    thumbnail_url = EXCLUDED.thumbnail_url, updated_at = NOW()
                """,
                youtube_video_id, title, description, thumbnail,
            )
            row = await db.fetchrow(
                "SELECT id FROM videos WHERE youtube_video_id = $1", youtube_video_id
            )

        logger.info("YouTube upload complete", org_id=org_id, video_id=youtube_video_id)
        return {
            "youtube_video_id": youtube_video_id,
            "video_id": str(row["id"]) if row else None,
            "title": title,
        }
