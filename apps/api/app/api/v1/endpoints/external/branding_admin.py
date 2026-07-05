"""AuraFlow — External Branding Admin API

Lets a tenant admin update their portal brand_config + allowed_portal_origins
without a redeploy of the customer's Next.js app. The portal re-fetches on
boot (and optionally at runtime) from the public branding endpoint.

PUT /api/v1/external/branding
    Headers: Authorization: Bearer af_live_<tenant-api-key>
    Body:   PortalBrandingUpdate (see below)

Server-side validation MUST catch:
  - Any URL field with a non-https scheme (no http, no data:, no javascript:)
  - Invalid hex color codes
  - Unknown keys outside the schema (silently dropped, not error — forward-compat)

The validation here is the authoritative check. The Next.js template's
zod schema is a defense-in-depth second pass, but the server must never
trust the client's validation.
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.api.v1.dependencies.api_key_auth import get_api_key_context, require_api_scope
from app.db.session import get_global_db

router = APIRouter()


# ── Schemas (mirror of auraflow-portal brand-config-schema.ts) ──────────────

_HEX = r"^#[0-9a-fA-F]{6}$"


class BrandColors(BaseModel):
    primary: str = Field(..., pattern=_HEX)
    on_primary: str = Field(..., pattern=_HEX)
    surface: str = Field(..., pattern=_HEX)
    on_surface: str = Field(..., pattern=_HEX)
    accent: Optional[str] = Field(None, pattern=_HEX)
    on_accent: Optional[str] = Field(None, pattern=_HEX)
    background: Optional[str] = Field(None, pattern=_HEX)
    foreground: Optional[str] = Field(None, pattern=_HEX)
    muted: Optional[str] = Field(None, pattern=_HEX)
    on_muted: Optional[str] = Field(None, pattern=_HEX)
    border: Optional[str] = Field(None, pattern=_HEX)


class BrandFonts(BaseModel):
    heading: Optional[str] = Field(None, min_length=1, max_length=100)
    body: Optional[str] = Field(None, min_length=1, max_length=100)


class Brand(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    # Use str + validator instead of HttpUrl so we can reject non-https at
    # the schema layer with a specific error (HttpUrl accepts http too).
    logo_url: Optional[str] = Field(None, max_length=1000)
    favicon_url: Optional[str] = Field(None, max_length=1000)
    colors: BrandColors
    fonts: Optional[BrandFonts] = None
    radius: Optional[str] = Field("md", pattern=r"^(none|sm|md|lg|full)$")

    @field_validator("logo_url", "favicon_url")
    @classmethod
    def _https_only(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not v.startswith("https://"):
            raise ValueError("URL must start with https:// (no http, no data:, no javascript:)")
        return v


class Features(BaseModel):
    model_config = {"extra": "ignore"}  # silently drop unknown keys (forward compat)
    enableClasspass: Optional[bool] = None
    enableMerch: Optional[bool] = None
    enableWorkshops: Optional[bool] = None
    enablePrivateLessons: Optional[bool] = None
    enableGiftCards: Optional[bool] = None
    enableVideo: Optional[bool] = None
    showStaffSchedule: Optional[bool] = None


class PortalBrandingUpdate(BaseModel):
    """PATCH-style: any top-level key omitted is left unchanged.
    `brand` (if provided) replaces the whole brand block — this avoids the
    deep-merge ambiguity of "what does it mean to update `colors.primary`
    but leave other colors alone when the new `colors` dict is a partial?"
    """
    brand: Optional[Brand] = None
    copy: Optional[dict[str, str]] = Field(
        None,
        description="String overrides keyed by portal copy-token. Unknown keys are kept.",
    )
    features: Optional[Features] = None
    allowed_portal_origins: Optional[list[str]] = Field(
        None,
        description="List of Origin strings (scheme+host, no path) allowed by CORS.",
    )

    @field_validator("copy")
    @classmethod
    def _no_html_in_copy(cls, v: Optional[dict[str, str]]) -> Optional[dict[str, str]]:
        if v is None:
            return None
        for key, value in v.items():
            if not isinstance(value, str):
                raise ValueError(f"copy[{key!r}] must be a string")
            if len(value) > 2000:
                raise ValueError(f"copy[{key!r}] exceeds 2000 chars")
            lowered = value.lower()
            # Hard refusals — no raw HTML tags or js URLs. The portal
            # renders these as text only, but we block at the write layer
            # too in case a customer's template ever inlines one.
            for forbidden in ("<script", "javascript:", "data:text/html"):
                if forbidden in lowered:
                    raise ValueError(f"copy[{key!r}] contains forbidden sequence {forbidden!r}")
        return v

    @field_validator("allowed_portal_origins")
    @classmethod
    def _validate_origins(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return None
        if len(v) > 20:
            raise ValueError("At most 20 origins allowed per tenant")
        out: list[str] = []
        for origin in v:
            if not isinstance(origin, str):
                raise ValueError(f"origin {origin!r} must be a string")
            origin = origin.strip()
            if not origin:
                continue
            if not origin.startswith("https://") and not origin.startswith("http://localhost"):
                raise ValueError(
                    f"origin {origin!r} must be https:// (except http://localhost for dev)"
                )
            if "/" in origin[8:]:  # scheme://host only — no path
                raise ValueError(f"origin {origin!r} must be scheme+host only (no path)")
            out.append(origin)
        return out


@router.get(
    "/branding",
    dependencies=[Depends(require_api_scope("branding:read"))],
    summary="Read this tenant's current portal brand config (authed)",
)
async def get_my_branding(ctx: Annotated[dict, Depends(get_api_key_context)]):
    import json as _json
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT brand_config, allowed_portal_origins FROM af_global.organizations WHERE id = $1",
            ctx["org_id"],
        )
    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")
    raw_bc = row["brand_config"]
    if isinstance(raw_bc, str):
        try:
            bc = _json.loads(raw_bc) if raw_bc else {}
        except (ValueError, TypeError):
            bc = {}
    else:
        bc = raw_bc or {}
    return {
        "brand_config": bc,
        "allowed_portal_origins": list(row["allowed_portal_origins"] or []),
    }


@router.put(
    "/branding",
    dependencies=[Depends(require_api_scope("branding:write"))],
    summary="Update this tenant's portal brand config (authed)",
)
async def update_my_branding(
    body: PortalBrandingUpdate,
    ctx: Annotated[dict, Depends(get_api_key_context)],
):
    """PATCH-style update. Any field omitted is left unchanged.
    `brand` replaces the whole brand block (see PortalBrandingUpdate docstring)."""
    import json as _json

    # Build the merge target
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT brand_config FROM af_global.organizations WHERE id = $1",
            ctx["org_id"],
        )
    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # asyncpg returns JSONB as a raw JSON string (not a parsed dict).
    raw_existing = row["brand_config"]
    if isinstance(raw_existing, str):
        try:
            existing = _json.loads(raw_existing) if raw_existing else {}
        except (ValueError, TypeError):
            existing = {}
    else:
        existing = raw_existing or {}
    merged = dict(existing)

    if body.brand is not None:
        merged["brand"] = body.brand.model_dump(exclude_none=True)
    if body.copy is not None:
        merged["copy"] = body.copy
    if body.features is not None:
        # Merge features — keep any keys the admin didn't touch
        current_feats = dict(merged.get("features", {}))
        current_feats.update(body.features.model_dump(exclude_none=True))
        merged["features"] = current_feats

    # Now write brand_config + (optionally) allowed_portal_origins.
    # JSONB write: cast $N::jsonb and pass json.dumps(d) — auraflow's
    # standard idiom (see services/feature_flags.py, social, ads, etc.).
    async with get_global_db() as db:
        if body.allowed_portal_origins is not None:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET brand_config = $1::jsonb, allowed_portal_origins = $2,
                    updated_at = NOW()
                WHERE id = $3
                """,
                _json.dumps(merged),
                body.allowed_portal_origins,
                ctx["org_id"],
            )
        else:
            await db.execute(
                """
                UPDATE af_global.organizations
                SET brand_config = $1::jsonb, updated_at = NOW()
                WHERE id = $2
                """,
                _json.dumps(merged),
                ctx["org_id"],
            )

    return {
        "brand_config": merged,
        "allowed_portal_origins": body.allowed_portal_origins,
    }
