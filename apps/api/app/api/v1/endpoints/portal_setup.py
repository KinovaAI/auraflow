"""AuraFlow — Portal Setup admin endpoints (Phase 5 onboarding wizard).

Powers the white-label portal onboarding wizard at
app.auraflow.fit /dashboard/settings/portal-setup. JWT-authed,
owner/admin only.

  GET  /admin/portal-setup/status
       Returns the wizard's checklist: brand_config status, api_key
       status, allowed_portal_origins, Stripe Connect readiness,
       and the recommended next-step.

  POST /admin/portal-setup/api-key
       Mint a portal-purpose api_key (full scopes for the portal proxy).
       Returns the raw key ONCE; never persisted in plaintext.

  POST /admin/portal-setup/origins
       Body: {"origin": "https://portal.studio.com"}
       Adds a domain to allowed_portal_origins. Validates https-only +
       scheme+host shape (no path).

  DELETE /admin/portal-setup/origins
       Body: {"origin": "https://portal.studio.com"}
       Removes a domain.

  GET  /admin/portal-setup/deploy-config
       Returns the env-var snippet the customer pastes into Vercel /
       docker-compose / their host. Includes the api_key ONLY if it was
       just minted in the same session (server-side flag).

The wizard UI calls these in order. Each step is independent — partial
completion is fine; the status endpoint reflects whatever's set.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.api.v1.dependencies.auth import get_current_user
from app.api.v1.dependencies.rbac import require_permission
from app.core.tenant_context import get_organization_id
from app.db.session import get_global_db, get_tenant_db
from app.services.external.api_key_service import create_key

router = APIRouter()


# ── Status ──────────────────────────────────────────────────────────────────

@router.get(
    "/portal-setup/status",
    summary="Onboarding-wizard checklist for the white-label portal",
    dependencies=[Depends(require_permission("settings.view_features"))],
)
async def portal_setup_status(
    user: Annotated[dict, Depends(get_current_user)],
):
    """Returns the wizard checklist + the recommended next-step copy.

    The portal-dev frontend uses this to render the wizard's progress
    bar and to gate the "deploy" step until prerequisites are met."""
    import json as _json
    org_id = get_organization_id()

    async with get_global_db() as db:
        org = await db.fetchrow(
            """
            SELECT slug, name, brand_config, allowed_portal_origins,
                   logo_url, primary_color,
                   stripe_account_id, stripe_charges_enabled
            FROM af_global.organizations WHERE id = $1
            """,
            org_id,
        )

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    raw_bc = org["brand_config"]
    if isinstance(raw_bc, str):
        try:
            bc = _json.loads(raw_bc) if raw_bc else {}
        except (ValueError, TypeError):
            bc = {}
    else:
        bc = raw_bc or {}

    brand = bc.get("brand") or {}
    has_logo = bool(brand.get("logoUrl") or brand.get("logo_url") or org["logo_url"])
    has_color = bool((brand.get("colors") or {}).get("primary") or org["primary_color"])
    has_origins = bool(org["allowed_portal_origins"])
    has_connect = bool(org["stripe_account_id"]) and bool(org["stripe_charges_enabled"])

    # API key check — count active portal-purpose keys in this tenant
    async with get_tenant_db() as db:
        api_key_count = await db.fetchval(
            "SELECT COUNT(*) FROM api_keys WHERE is_active = TRUE",
        ) or 0
    has_api_key = api_key_count > 0

    # Decide the recommended next-step
    if not has_logo or not has_color:
        next_step = "brand"
        next_step_label = "Set your studio logo and primary color"
    elif not has_api_key:
        next_step = "api_key"
        next_step_label = "Mint your portal API key"
    elif not has_origins:
        next_step = "origins"
        next_step_label = "Add your portal domain"
    elif not has_connect:
        next_step = "stripe"
        next_step_label = "Connect Stripe to accept payments"
    else:
        next_step = "deploy"
        next_step_label = "Deploy your portal"

    # Surface current brand for hydrating the wizard's color pickers.
    # Falls back to legacy columns if brand_config is partial — mirrors
    # the logic in /public/tenants/{slug}/branding.
    cur_brand = dict(bc.get("brand") or {})
    cur_colors = dict(cur_brand.get("colors") or {})
    current_brand = {
        "name": cur_brand.get("name") or org["name"],
        "logo_url": cur_brand.get("logoUrl") or cur_brand.get("logo_url") or org["logo_url"],
        "primary_color": cur_colors.get("primary") or org["primary_color"] or "#4F46E5",
        "on_primary_color": cur_colors.get("on_primary") or "#ffffff",
        "surface_color": cur_colors.get("surface") or "#fafafa",
        "on_surface_color": cur_colors.get("on_surface") or "#1a1a1a",
    }

    return {
        "tenant_slug": org["slug"],
        "tenant_name": org["name"],
        "current_brand": current_brand,
        "checklist": {
            "brand": {"done": has_logo and has_color,
                      "has_logo": has_logo, "has_color": has_color},
            "api_key": {"done": has_api_key, "active_count": api_key_count},
            "origins": {"done": has_origins,
                        "origins": list(org["allowed_portal_origins"] or [])},
            "stripe_connect": {"done": has_connect,
                               "account_id": org["stripe_account_id"],
                               "charges_enabled": bool(org["stripe_charges_enabled"])},
        },
        "next_step": next_step,
        "next_step_label": next_step_label,
        "ready_to_deploy": (
            has_logo and has_color and has_api_key and has_origins
        ),
    }


# ── Brand editor ────────────────────────────────────────────────────────────

_HEX_RE = r"^#[0-9a-fA-F]{6}$"


class BrandUpdateRequest(BaseModel):
    """Partial — anything omitted is left unchanged.

    Writes to BOTH brand_config (the new white-label shape) AND the
    legacy logo_url/primary_color columns (so the existing AuraFlow
    admin UI also reflects it). brand_config is the source of truth;
    the legacy columns are kept in sync for backward compat.

    Four core brand colors are exposed here:
      primary     - button/link/accent color (the "studio color")
      on_primary  - text color on top of primary (usually white or dark)
      surface     - card/panel background (e.g. tan, off-white, cream)
      on_surface  - body text / primary foreground
    The derived tokens (muted, border, etc.) are computed from these by
    the portal's brand-css.ts at render time — customers don't need to
    set each one unless they really want fine control.
    """
    name: str | None = Field(None, min_length=1, max_length=100)
    primary_color: str | None = Field(None, pattern=_HEX_RE)
    on_primary_color: str | None = Field(None, pattern=_HEX_RE)
    surface_color: str | None = Field(None, pattern=_HEX_RE)
    on_surface_color: str | None = Field(None, pattern=_HEX_RE)
    logo_url: str | None = Field(None, max_length=1000)

    @field_validator("logo_url")
    @classmethod
    def _https_only(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not v.startswith("https://"):
            raise ValueError("logo_url must be https://")
        return v


@router.put(
    "/portal-setup/brand",
    summary="Update brand_config.brand (name, primary color, logo URL)",
    dependencies=[Depends(require_permission("settings.manage_features"))],
)
async def update_brand(
    body: BrandUpdateRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Writes to brand_config (authoritative for portal) AND to the
    legacy organizations.logo_url + primary_color columns (so existing
    UI stays consistent). No-op if all fields are None."""
    import json as _json
    org_id = get_organization_id()

    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT name, brand_config, logo_url, primary_color FROM af_global.organizations WHERE id = $1",
            org_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")

    raw_bc = row["brand_config"]
    if isinstance(raw_bc, str):
        try:
            bc = _json.loads(raw_bc) if raw_bc else {}
        except (ValueError, TypeError):
            bc = {}
    else:
        bc = raw_bc or {}

    brand = dict(bc.get("brand") or {})
    colors = dict(brand.get("colors") or {})

    # Apply updates — only fields the caller provided
    if body.name is not None:
        brand["name"] = body.name
    if body.primary_color is not None:
        colors["primary"] = body.primary_color
    if body.on_primary_color is not None:
        colors["on_primary"] = body.on_primary_color
    if body.surface_color is not None:
        colors["surface"] = body.surface_color
    if body.on_surface_color is not None:
        colors["on_surface"] = body.on_surface_color
    if body.logo_url is not None:
        brand["logoUrl"] = body.logo_url

    # Fill in sensible defaults so the portal never sees a half-built config
    colors.setdefault("primary", row["primary_color"] or "#4F46E5")
    colors.setdefault("on_primary", "#ffffff")
    colors.setdefault("surface", "#fafafa")
    colors.setdefault("on_surface", "#1a1a1a")
    brand["colors"] = colors
    brand.setdefault("name", row["name"])
    brand.setdefault("radius", "md")
    bc["brand"] = brand

    # Dual-write: brand_config (new) + legacy columns (for backward compat
    # with any AuraFlow code that still reads them)
    legacy_logo = body.logo_url if body.logo_url is not None else row["logo_url"]
    legacy_color = body.primary_color if body.primary_color is not None else row["primary_color"]

    async with get_global_db() as db:
        await db.execute(
            """
            UPDATE af_global.organizations
            SET brand_config = $1::jsonb,
                logo_url = $2,
                primary_color = $3,
                updated_at = NOW()
            WHERE id = $4
            """,
            _json.dumps(bc),
            legacy_logo,
            legacy_color,
            org_id,
        )

    return {
        "brand": brand,
        "legacy_logo_url": legacy_logo,
        "legacy_primary_color": legacy_color,
    }


# ── API key ─────────────────────────────────────────────────────────────────

@router.post(
    "/portal-setup/api-key",
    summary="Mint a portal-purpose api_key (returned ONCE)",
    dependencies=[Depends(require_permission("settings.manage_features"))],
)
async def mint_portal_api_key(
    user: Annotated[dict, Depends(get_current_user)],
):
    """Mint an api_key purposed for the white-label portal deploy.
    Same shape as POST /external/api-keys but with a fixed name and
    full scopes the portal needs."""
    from uuid import UUID
    user_id = user.get("sub")
    result = await create_key(
        name="white-label-portal",
        scopes=["*:*"],
        rate_limit_rpm=120,
        created_by=UUID(user_id) if user_id else None,
    )
    return {
        "raw_key": result["raw_key"],
        "key_prefix": result["key_prefix"],
        "warning": (
            "Copy this key now — it will not be shown again. Paste it into "
            "your portal deployment as the AURAFLOW_API_KEY env var."
        ),
    }


# ── Origins ─────────────────────────────────────────────────────────────────

class OriginRequest(BaseModel):
    origin: str = Field(..., min_length=1, max_length=200)

    @field_validator("origin")
    @classmethod
    def _https_or_localhost(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not (v.startswith("https://") or v.startswith("http://localhost")):
            raise ValueError(
                "Origin must be https:// (http://localhost allowed for dev)"
            )
        if "/" in v[8:]:
            raise ValueError("Origin must be scheme + host only (no path)")
        return v


@router.post(
    "/portal-setup/origins",
    summary="Add a domain to the allowed_portal_origins allowlist",
    dependencies=[Depends(require_permission("settings.manage_features"))],
)
async def add_portal_origin(
    body: OriginRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    org_id = get_organization_id()
    async with get_global_db() as db:
        # Append-if-not-already-present (no duplicate origins)
        await db.execute(
            """
            UPDATE af_global.organizations
            SET allowed_portal_origins = (
                SELECT ARRAY(
                    SELECT DISTINCT unnest(allowed_portal_origins || $1::text[])
                )
            ),
            updated_at = NOW()
            WHERE id = $2
            """,
            [body.origin], org_id,
        )
        row = await db.fetchrow(
            "SELECT allowed_portal_origins FROM af_global.organizations WHERE id = $1",
            org_id,
        )
    return {"allowed_portal_origins": list(row["allowed_portal_origins"] or [])}


@router.delete(
    "/portal-setup/origins",
    summary="Remove a domain from the allowed_portal_origins allowlist",
    dependencies=[Depends(require_permission("settings.manage_features"))],
)
async def remove_portal_origin(
    body: OriginRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    org_id = get_organization_id()
    async with get_global_db() as db:
        await db.execute(
            """
            UPDATE af_global.organizations
            SET allowed_portal_origins = array_remove(allowed_portal_origins, $1),
                updated_at = NOW()
            WHERE id = $2
            """,
            body.origin, org_id,
        )
        row = await db.fetchrow(
            "SELECT allowed_portal_origins FROM af_global.organizations WHERE id = $1",
            org_id,
        )
    return {"allowed_portal_origins": list(row["allowed_portal_origins"] or [])}


# ── Deploy config ───────────────────────────────────────────────────────────

@router.get(
    "/portal-setup/deploy-config",
    summary="Env-var snippet for the customer's portal deploy",
    dependencies=[Depends(require_permission("settings.view_features"))],
)
async def get_deploy_config(
    user: Annotated[dict, Depends(get_current_user)],
):
    """Returns the env vars the customer needs to set on their portal
    host. Does NOT include the api_key (they got it once at mint time).

    Two formats: a .env-style block they can paste into Vercel /
    docker-compose, plus a Vercel deploy button URL with vars pre-filled.
    """
    org_id = get_organization_id()
    async with get_global_db() as db:
        org = await db.fetchrow(
            "SELECT slug FROM af_global.organizations WHERE id = $1",
            org_id,
        )
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    api_base = "https://api.auraflow.fit"
    env_block = (
        f"NEXT_PUBLIC_AURAFLOW_API_URL={api_base}\n"
        f"NEXT_PUBLIC_AURAFLOW_TENANT_SLUG={org['slug']}\n"
        f"AURAFLOW_API_KEY=<paste the api_key from the previous step>\n"
    )

    # Vercel deploy button — opens the new-project flow with env vars
    # pre-filled. Customer still has to paste the api_key value.
    vercel_url = (
        "https://vercel.com/new/clone"
        "?repository-url=https://github.com/KinovaAI/auraflow-portal"
        "&root-directory=packages/template"
        "&env=NEXT_PUBLIC_AURAFLOW_API_URL,NEXT_PUBLIC_AURAFLOW_TENANT_SLUG,AURAFLOW_API_KEY"
        f"&envDescription=API base URL, your tenant slug ({org['slug']}), "
        "and the api_key you minted in the previous step"
    )

    return {
        "env_block": env_block,
        "vercel_deploy_url": vercel_url,
        "github_repo": "https://github.com/KinovaAI/auraflow-portal",
        "docker_compose_snippet": (
            "services:\n"
            "  app:\n"
            "    build:\n"
            "      context: .\n"
            "      args:\n"
            f"        NEXT_PUBLIC_AURAFLOW_API_URL: {api_base}\n"
            f"        NEXT_PUBLIC_AURAFLOW_TENANT_SLUG: {org['slug']}\n"
            "    environment:\n"
            f"      - NEXT_PUBLIC_AURAFLOW_API_URL={api_base}\n"
            f"      - NEXT_PUBLIC_AURAFLOW_TENANT_SLUG={org['slug']}\n"
            "      - AURAFLOW_API_KEY=<paste-here>\n"
        ),
    }
