"""AuraFlow — Public Tenant Branding API

Unauthenticated read of a tenant's brand_config (consumed by white-label
portal deploys at boot, so the customer's Next.js app can re-read theme
tokens without redeploying when the admin updates branding).

GET /api/v1/public/tenants/{slug}/branding

Response shape (the schema is mirrored in
auraflow-portal/packages/template/src/lib/brand-config-schema.ts —
keep both in sync; the SDK validates the response client-side as a
defense-in-depth XSS measure):

    {
      "tenant_slug": "example-studio",
      "brand": {
        "name": "Your Studio",
        "logo_url": "https://...",
        "favicon_url": "https://...",
        "colors": { "primary": "#RRGGBB", "on_primary": "#RRGGBB", ... },
        "fonts": { "heading": "Inter", "body": "Inter" },
        "radius": "md"
      },
      "copy":     { "<key>": "<override string>" },
      "features": { "enableClasspass": true, ... }
    }

Returns 404 for unknown / cancelled tenants. Returns 200 with empty
defaults if brand_config is unset (tenant exists but never branded the
portal — fine, the template falls back to its own defaults).

The corresponding ADMIN write endpoint lives in /external/branding —
api-key-authed, schema-validated server-side. See branding_admin.py.
"""
import json
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.db.session import get_global_db

router = APIRouter()


@router.get("/tenants/{slug}/branding", summary="Public read of a tenant's portal brand config")
async def get_tenant_branding(slug: str):
    async with get_global_db() as db:
        row = await db.fetchrow(
            """
            SELECT slug, name, status, brand_config, primary_color, logo_url
            FROM af_global.organizations
            WHERE slug = $1
            """,
            slug,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if row["status"] in ("suspended", "cancelled"):
        raise HTTPException(status_code=404, detail="Tenant not found")  # generic — don't leak status

    # asyncpg returns JSONB as a raw JSON string (not a parsed dict).
    raw_bc = row["brand_config"]
    if isinstance(raw_bc, str):
        try:
            bc = json.loads(raw_bc) if raw_bc else {}
        except (ValueError, TypeError):
            bc = {}
    else:
        bc = raw_bc or {}

    # ALWAYS overlay the legacy primary_color + logo_url columns onto
    # whatever brand_config has — but only as fallbacks for fields that
    # the brand_config didn't set. So a tenant using ONLY the existing
    # AuraFlow admin Settings UI (which writes to the legacy columns)
    # gets their logo+color reflected automatically. A tenant using the
    # new PUT /external/branding endpoint can override.
    #
    # Precedence:
    #   brand_config.brand.logoUrl       wins over   organizations.logo_url
    #   brand_config.brand.colors.primary wins over  organizations.primary_color
    #
    # Default-name + default-other-colors only kick in when nothing is set.
    brand = dict(bc.get("brand") or {})
    colors = dict(brand.get("colors") or {})

    # Legacy logo_url fallback
    if not brand.get("logoUrl") and not brand.get("logo_url") and row["logo_url"]:
        brand["logoUrl"] = row["logo_url"]
    # Legacy primary_color fallback
    if not colors.get("primary") and row["primary_color"]:
        colors["primary"] = row["primary_color"]

    # Defaults for any colors still missing — keeps the schema complete
    # so the portal's CSS-vars generator never sees undefined values.
    colors.setdefault("primary", "#4F46E5")
    colors.setdefault("on_primary", "#ffffff")
    colors.setdefault("surface", "#ffffff")
    colors.setdefault("on_surface", "#1a1a1a")
    brand["colors"] = colors
    brand.setdefault("name", row["name"])
    brand.setdefault("radius", "md")

    return {
        "tenant_slug": row["slug"],
        "brand": brand,
        "copy": bc.get("copy", {}),
        "features": bc.get("features", {}),
    }
