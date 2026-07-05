"""AuraFlow — Video Library Service

Unified orchestrator for the Video Library feature.
Handles CRUD for videos and categories, access control,
view tracking, and analytics. Delegates to YouTubeService
and MuxService for provider-specific operations.
"""
import uuid
from typing import Optional

from app.core.logging import logger
from app.db.session import get_tenant_db, get_global_db
from app.services.video.youtube_service import YouTubeService
from app.services.video.mux_service import MuxService


class VideoService:

    def __init__(self):
        self.youtube = YouTubeService()
        self.mux = MuxService()

    # ── Connection Status ──────────────────────────────────────────────────

    async def get_connection_status(self, org_id: str) -> dict:
        """Return which video providers are connected for an org."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT youtube_channel_id, youtube_connected_at,
                       youtube_refresh_token_encrypted,
                       mux_environment_id, mux_connected_at,
                       zoom_account_id, zoom_connected_at,
                       zoom_auto_record, zoom_auto_publish
                FROM af_global.organizations WHERE id = $1
                """,
                org_id,
            )
        if not row:
            return {
                "youtube_connected": False,
                "mux_connected": False,
                "zoom_connected": False,
            }
        return {
            "youtube_connected": row["youtube_connected_at"] is not None,
            "youtube_channel_id": row["youtube_channel_id"],
            "youtube_connected_at": row["youtube_connected_at"].isoformat() if row["youtube_connected_at"] else None,
            "youtube_upload_authorized": row["youtube_refresh_token_encrypted"] is not None,
            "mux_connected": row["mux_connected_at"] is not None,
            "mux_connected_at": row["mux_connected_at"].isoformat() if row["mux_connected_at"] else None,
            "zoom_connected": row["zoom_connected_at"] is not None,
            "zoom_account_id": row["zoom_account_id"],
            "zoom_connected_at": row["zoom_connected_at"].isoformat() if row["zoom_connected_at"] else None,
            "zoom_auto_record": row["zoom_auto_record"],
            "zoom_auto_publish": row["zoom_auto_publish"],
        }

    # ── Sync ───────────────────────────────────────────────────────────────

    async def sync_all(self, org_id: str) -> list[dict]:
        """Trigger sync from all connected providers."""
        results = []
        status = await self.get_connection_status(org_id)
        if status["youtube_connected"]:
            results.append(await self.youtube.sync_videos(org_id))
        if status["mux_connected"]:
            results.append(await self.mux.sync_assets(org_id))
        return results

    # ── Video CRUD ─────────────────────────────────────────────────────────

    async def list_videos(
        self,
        category_id: Optional[str] = None,
        source: Optional[str] = None,
        published_only: bool = False,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List videos with optional filters."""
        conditions = []
        params = []
        param_idx = 1

        if category_id:
            conditions.append(f"v.category_id = ${param_idx}")
            params.append(category_id)
            param_idx += 1
        if source:
            conditions.append(f"v.source = ${param_idx}")
            params.append(source)
            param_idx += 1
        if published_only:
            conditions.append("v.is_published = TRUE")
            conditions.append("v.visibility != 'hidden'")
        if search:
            conditions.append(f"v.title ILIKE ${param_idx}")
            params.append(f"%{search}%")
            param_idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        params.append(limit)
        params.append(offset)

        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"""
                SELECT v.*, c.name AS category_name
                FROM videos v
                LEFT JOIN video_categories c ON c.id = v.category_id
                {where}
                ORDER BY v.sort_order, v.created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
                """,
                *params,
            )
            return [dict(r) for r in rows]

    async def get_video(self, video_id: str) -> Optional[dict]:
        """Get a single video with category and access rules."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT v.*, c.name AS category_name
                FROM videos v
                LEFT JOIN video_categories c ON c.id = v.category_id
                WHERE v.id = $1
                """,
                video_id,
            )
            if not row:
                return None
            result = dict(row)

            # Fetch membership access rules
            access_rows = await db.fetch(
                "SELECT membership_type_id FROM video_membership_access WHERE video_id = $1",
                video_id,
            )
            result["membership_type_ids"] = [str(r["membership_type_id"]) for r in access_rows]
            return result

    async def update_video(self, video_id: str, data: dict) -> Optional[dict]:
        """Update video metadata, visibility, and access rules."""
        sets = []
        params = []
        param_idx = 1

        for field in ("title", "description", "category_id", "visibility", "is_published", "sort_order"):
            if field in data and data[field] is not None:
                sets.append(f"{field} = ${param_idx}")
                params.append(data[field])
                param_idx += 1

        if "tags" in data:
            sets.append(f"tags = ${param_idx}")
            params.append(data["tags"])
            param_idx += 1

        if data.get("is_published") and "published_at" not in data:
            sets.append("published_at = NOW()")

        sets.append("updated_at = NOW()")
        params.append(video_id)

        async with get_tenant_db() as db:
            row = await db.fetchrow(
                f"""
                UPDATE videos SET {', '.join(sets)}
                WHERE id = ${param_idx}
                RETURNING *
                """,
                *params,
            )
            if not row:
                return None

            # Update membership access if provided
            if "membership_type_ids" in data:
                await self._set_video_access(db, video_id, data["membership_type_ids"])

            return dict(row)

    async def delete_video(self, video_id: str) -> bool:
        """Soft-delete a video by hiding it."""
        async with get_tenant_db() as db:
            result = await db.execute(
                """
                UPDATE videos
                SET is_published = FALSE, visibility = 'hidden', updated_at = NOW()
                WHERE id = $1
                """,
                video_id,
            )
            return "UPDATE 1" in result

    # ── Access Control ─────────────────────────────────────────────────────

    async def _set_video_access(self, db, video_id: str, membership_type_ids: list[str]) -> None:
        """Replace membership access rules for a video."""
        await db.execute("DELETE FROM video_membership_access WHERE video_id = $1", video_id)
        for mt_id in membership_type_ids:
            await db.execute(
                """
                INSERT INTO video_membership_access (video_id, membership_type_id)
                VALUES ($1, $2) ON CONFLICT DO NOTHING
                """,
                video_id, mt_id,
            )

    async def get_accessible_videos(
        self,
        member_id: str,
        category_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Get videos accessible to a specific member based on their memberships."""
        conditions = [
            "v.is_published = TRUE",
            "v.visibility != 'hidden'",
            "v.visibility != 'staff_only'",
        ]
        params = [member_id]
        param_idx = 2

        if category_id:
            conditions.append(f"v.category_id = ${param_idx}")
            params.append(category_id)
            param_idx += 1

        where = " AND ".join(conditions)
        params.extend([limit, offset])

        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"""
                SELECT DISTINCT v.*, c.name AS category_name
                FROM videos v
                LEFT JOIN video_categories c ON c.id = v.category_id
                WHERE {where}
                  AND (
                    v.visibility = 'all_members'
                    OR (
                      v.visibility = 'specific_memberships'
                      AND EXISTS (
                        SELECT 1 FROM video_membership_access vma
                        JOIN member_memberships mm ON mm.membership_type_id = vma.membership_type_id
                        WHERE vma.video_id = v.id
                          AND mm.member_id = $1
                          AND mm.status = 'active'
                      )
                    )
                  )
                ORDER BY v.sort_order, v.created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
                """,
                *params,
            )
            return [dict(r) for r in rows]

    async def get_accessible_video(self, video_id: str, member_id: str) -> Optional[dict]:
        """Get a single video if the member has access."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT v.*, c.name AS category_name
                FROM videos v
                LEFT JOIN video_categories c ON c.id = v.category_id
                WHERE v.id = $1
                  AND v.is_published = TRUE
                  AND v.visibility != 'hidden'
                  AND v.visibility != 'staff_only'
                  AND (
                    v.visibility = 'all_members'
                    OR (
                      v.visibility = 'specific_memberships'
                      AND EXISTS (
                        SELECT 1 FROM video_membership_access vma
                        JOIN member_memberships mm ON mm.membership_type_id = vma.membership_type_id
                        WHERE vma.video_id = v.id
                          AND mm.member_id = $2
                          AND mm.status = 'active'
                      )
                    )
                  )
                """,
                video_id, member_id,
            )
            return dict(row) if row else None

    # ── Categories ─────────────────────────────────────────────────────────

    async def list_categories(self, include_inactive: bool = False) -> list[dict]:
        """List video categories."""
        condition = "" if include_inactive else "WHERE c.is_active = TRUE"
        async with get_tenant_db() as db:
            rows = await db.fetch(
                f"""
                SELECT c.*, COUNT(v.id) AS video_count
                FROM video_categories c
                LEFT JOIN videos v ON v.category_id = c.id AND v.is_published = TRUE
                {condition}
                GROUP BY c.id
                ORDER BY c.sort_order, c.name
                """,
            )
            return [dict(r) for r in rows]

    async def create_category(self, name: str, description: Optional[str] = None, slug: Optional[str] = None) -> dict:
        """Create a video category."""
        if not slug:
            slug = name.lower().replace(" ", "-").replace("'", "")
        cat_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO video_categories (id, name, description, slug)
                VALUES ($1, $2, $3, $4)
                RETURNING *
                """,
                cat_id, name, description, slug,
            )
            return dict(row)

    async def update_category(self, category_id: str, data: dict) -> Optional[dict]:
        """Update a video category."""
        sets = []
        params = []
        param_idx = 1
        for field in ("name", "description", "slug", "sort_order", "is_active"):
            if field in data:
                sets.append(f"{field} = ${param_idx}")
                params.append(data[field])
                param_idx += 1
        sets.append("updated_at = NOW()")
        params.append(category_id)

        async with get_tenant_db() as db:
            row = await db.fetchrow(
                f"""
                UPDATE video_categories SET {', '.join(sets)}
                WHERE id = ${param_idx}
                RETURNING *
                """,
                *params,
            )
            return dict(row) if row else None

    async def delete_category(self, category_id: str) -> bool:
        """Soft-delete a category and unlink its videos."""
        async with get_tenant_db() as db:
            result = await db.execute(
                "UPDATE video_categories SET is_active = FALSE, updated_at = NOW() WHERE id = $1",
                category_id,
            )
            await db.execute(
                "UPDATE videos SET category_id = NULL, updated_at = NOW() WHERE category_id = $1",
                category_id,
            )
            return "UPDATE 1" in result

    # ── View Tracking ──────────────────────────────────────────────────────

    async def record_view(self, video_id: str, member_id: str, watched_seconds: int = 0, completed: bool = False) -> None:
        """Record a video view event."""
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO video_views (video_id, member_id, watched_seconds, completed)
                VALUES ($1, $2, $3, $4)
                """,
                video_id, member_id, watched_seconds, completed,
            )

    # ── Analytics ──────────────────────────────────────────────────────────

    async def get_video_stats(self, video_id: str) -> dict:
        """Get view stats for a single video."""
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_views,
                    COUNT(DISTINCT member_id) AS unique_viewers,
                    COALESCE(AVG(watched_seconds), 0) AS avg_watch_seconds,
                    COUNT(*) FILTER (WHERE completed) AS completions
                FROM video_views
                WHERE video_id = $1
                """,
                video_id,
            )
            return dict(row) if row else {}

    async def get_library_stats(self) -> dict:
        """Get library-level video statistics."""
        async with get_tenant_db() as db:
            video_row = await db.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_videos,
                    COUNT(*) FILTER (WHERE is_published) AS published_videos,
                    COUNT(*) FILTER (WHERE source = 'youtube') AS youtube_videos,
                    COUNT(*) FILTER (WHERE source = 'mux') AS mux_videos
                FROM videos
                """,
            )
            view_row = await db.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_views,
                    COUNT(DISTINCT member_id) AS unique_viewers
                FROM video_views
                """,
            )
            popular = await db.fetch(
                """
                SELECT v.id, v.title, v.thumbnail_url, v.source,
                       COUNT(vv.id) AS view_count
                FROM videos v
                JOIN video_views vv ON vv.video_id = v.id
                WHERE v.is_published = TRUE
                GROUP BY v.id
                ORDER BY view_count DESC
                LIMIT 5
                """,
            )
            return {
                **(dict(video_row) if video_row else {}),
                "total_views": view_row["total_views"] if view_row else 0,
                "unique_viewers": view_row["unique_viewers"] if view_row else 0,
                "most_popular": [dict(r) for r in popular],
            }
