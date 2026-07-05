"""Add portal branding + CORS allowlist columns to af_global.organizations

Phase 0 foundation work for the white-label portal (KinovaAI/auraflow-portal).
Two additive columns, no behavior change in this migration alone — the
columns are read by code that lands in Phase 1 (CORS middleware reading
allowed_portal_origins; /public/tenants/{slug}/branding endpoint reading
brand_config). Until Phase 1 lands, both columns are dormant defaults.

Backward-compat: the existing `primary_color` and `logo_url` columns are
kept untouched. The new `brand_config` jsonb is a strict superset that
the white-label portal template reads; the AuraFlow-hosted apps/web
keeps reading the old columns. A future migration may consolidate.

Revision ID: a21_portal_branding_columns
Revises: a20_external_ref_index
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB


revision = "a21_portal_branding_columns"
down_revision = "a20_external_ref_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CORS allowlist for the white-label portal. Each entry is a fully-
    # qualified Origin (scheme + host, no path), e.g.
    # 'https://portal.your-domain.com'. Empty array (default) means
    # the tenant has no white-label portal yet — only auraflow.fit
    # subdomains can hit /portal/* + /external/* for that org.
    op.add_column(
        "organizations",
        sa.Column(
            "allowed_portal_origins",
            ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        schema="af_global",
    )

    # Structured brand config consumed by the portal template's
    # auraflow.config.ts at build time AND by /public/tenants/{slug}/branding
    # at runtime (so an admin can rebrand without redeploying the customer's
    # Next.js app — the portal re-fetches on cold start).
    #
    # Schema (validated server-side by Phase 1 endpoint):
    #   {
    #     "brand": {
    #       "name":     "string",
    #       "logo_url": "https://… (must be https)",
    #       "favicon_url": "https://…",
    #       "colors": {
    #         "primary":     "#RRGGBB",
    #         "on_primary":  "#RRGGBB",
    #         "surface":     "#RRGGBB",
    #         "on_surface":  "#RRGGBB",
    #         "accent":      "#RRGGBB"
    #       },
    #       "fonts":  { "heading": "string", "body": "string" },
    #       "radius": "sm" | "md" | "lg" | "full"
    #     },
    #     "copy": { "<key>": "<override string>" },
    #     "features": { "enableClasspass": bool, "enableMerch": bool, ... }
    #   }
    #
    # Strict server-side validation (Phase 1): no <script>, no javascript:
    # URLs, no data: URLs in any string field. Keys outside the schema are
    # silently dropped. Validation errors return 422 from the admin update
    # endpoint, never silently stored.
    op.add_column(
        "organizations",
        sa.Column(
            "brand_config",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="af_global",
    )


def downgrade() -> None:
    op.drop_column("organizations", "brand_config", schema="af_global")
    op.drop_column("organizations", "allowed_portal_origins", schema="af_global")
