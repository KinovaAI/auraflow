"""
AuraFlow — Feature Flag Service

Every major platform feature can be toggled per organization.
Flags are cached in Redis to avoid DB hits on every request.
"""
import json
from typing import Optional
from functools import wraps

from app.core.logging import logger


class FeatureFlagService:
    """
    Check and manage feature flags per tenant.

    Usage in endpoints:
        flags = FeatureFlagService()
        if not await flags.is_enabled("video.on_demand_library", org_id):
            raise HTTPException(403, "Feature not available on your plan")
    """

    CACHE_TTL = 300  # 5 minutes

    async def is_enabled(
        self,
        flag_key: str,
        organization_id: Optional[str] = None,
    ) -> bool:
        """Check if a feature flag is enabled for an organization."""
        cache_key = f"flags:{organization_id or 'global'}:{flag_key}"

        from app.core.redis import get_redis
        redis = await get_redis()

        if redis:
            cached = await redis.get(cache_key)
            if cached is not None:
                return cached == b"1"

        # Load from DB
        enabled = await self._load_from_db(flag_key, organization_id)

        if redis:
            await redis.setex(cache_key, self.CACHE_TTL, "1" if enabled else "0")

        return enabled

    async def _load_from_db(
        self,
        flag_key: str,
        organization_id: Optional[str],
    ) -> bool:
        from app.db.session import get_global_db

        async with get_global_db() as db:
            if organization_id:
                # Check org-specific flag first, fall back to platform default
                result = await db.fetchrow(
                    """
                    SELECT is_enabled FROM af_global.feature_flags
                    WHERE (organization_id = $1 OR organization_id IS NULL)
                      AND flag_key = $2
                    ORDER BY organization_id NULLS LAST
                    LIMIT 1
                    """,
                    organization_id, flag_key
                )
            else:
                result = await db.fetchrow(
                    """
                    SELECT is_enabled FROM af_global.feature_flags
                    WHERE organization_id IS NULL AND flag_key = $1
                    """,
                    flag_key
                )

            return result["is_enabled"] if result else False

    async def get_all_flags(self, organization_id: str) -> dict:
        """Get all feature flags for an organization. Used by frontend."""
        cache_key = f"flags:all:{organization_id}"

        from app.core.redis import get_redis
        redis = await get_redis()

        if redis:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)

        from app.db.session import get_global_db
        async with get_global_db() as db:
            rows = await db.fetch(
                """
                SELECT DISTINCT ON (flag_key) flag_key, is_enabled
                FROM af_global.feature_flags
                WHERE organization_id = $1 OR organization_id IS NULL
                ORDER BY flag_key, organization_id NULLS LAST
                """,
                organization_id
            )

        flags = {row["flag_key"]: row["is_enabled"] for row in rows}

        if redis:
            await redis.setex(cache_key, self.CACHE_TTL, json.dumps(flags))

        return flags

    async def set_flag(
        self,
        flag_key: str,
        is_enabled: bool,
        organization_id: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> None:
        """Set a feature flag. Invalidates cache."""
        from app.db.session import get_global_db

        async with get_global_db() as db:
            await db.execute(
                """
                INSERT INTO af_global.feature_flags
                    (organization_id, flag_key, is_enabled, config)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (organization_id, flag_key)
                DO UPDATE SET
                    is_enabled = EXCLUDED.is_enabled,
                    config = EXCLUDED.config,
                    updated_at = NOW()
                """,
                organization_id, flag_key, is_enabled,
                json.dumps(config or {})
            )

        # Invalidate cache
        await self._invalidate_cache(flag_key, organization_id)
        logger.info(
            "Feature flag updated",
            flag=flag_key,
            enabled=is_enabled,
            org_id=organization_id
        )

    async def _invalidate_cache(self, flag_key: str, organization_id: Optional[str]):
        from app.core.redis import get_redis
        redis = await get_redis()
        if redis:
            await redis.delete(f"flags:{organization_id or 'global'}:{flag_key}")
            await redis.delete(f"flags:all:{organization_id}")


# ── FastAPI Dependency ────────────────────────────────────────────────────────
def require_feature(flag_key: str):
    """
    FastAPI dependency that gates an endpoint behind a feature flag.

    Usage:
        @router.get("/on-demand", dependencies=[Depends(require_feature("video.on_demand_library"))])
        async def get_videos(): ...
    """
    from fastapi import Depends, HTTPException
    from app.api.v1.dependencies.auth import get_current_user
    from app.core.tenant_context import get_organization_id

    async def check_feature(
        current_user=Depends(get_current_user)
    ):
        org_id = get_organization_id()
        service = FeatureFlagService()
        enabled = await service.is_enabled(flag_key, org_id)
        if not enabled:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Feature not available",
                    "code": "FEATURE_DISABLED",
                    "feature": flag_key,
                    "message": "This feature is not enabled on your current plan. "
                               "Contact support to upgrade.",
                }
            )
        return True

    return Depends(check_feature)


# Singleton
feature_flags = FeatureFlagService()
