"""AuraFlow — Public self-serve online-membership signup.

One public (unauthenticated) endpoint a facility/customer hits from a signup
link to enroll themselves into an online-membership plan with a free trial.
Organization-independent: the caller supplies `org_slug`, everything else comes
from that studio's plan config. Returns auth tokens so the signup page can drop
the new member straight into their portal.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.services.members.self_serve_service import enroll_online_membership, SignupError
from app.api.v1.endpoints.auth import _issue_tokens

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


async def _resolve_org(org_slug: str):
    async with get_global_db() as db:
        row = await db.fetchrow(
            "SELECT id, schema_name, status, square_location_id "
            "FROM af_global.organizations WHERE slug = $1",
            org_slug,
        )
    if not row:
        raise HTTPException(status_code=404, detail={"error": "Studio not found"})
    return row


@router.get("/square-config")
async def self_serve_square_config(org_slug: str):
    """Publishable Square Web Payments SDK config for a studio's public signup
    page (platform application_id + the studio's own location_id). No secrets."""
    org = await _resolve_org(org_slug)
    return {
        "data": {
            "application_id": settings.SQUARE_OAUTH_APPLICATION_ID,
            "location_id": org["square_location_id"],
            "environment": settings.SQUARE_ENVIRONMENT,
        }
    }


@router.get("/plans")
async def self_serve_plans(org_slug: str):
    """Active online-membership plans a studio offers for self-serve signup.
    Data-driven: the page shows whatever the studio has configured."""
    org = await _resolve_org(org_slug)
    async with get_tenant_db(schema_override=org["schema_name"]) as db:
        rows = await db.fetch(
            """
            SELECT id, name, price_cents, billing_period, trial_days
            FROM membership_types
            WHERE is_active = TRUE AND is_online = TRUE AND price_cents > 0
            ORDER BY price_cents
            """
        )
    return {"data": [dict(r) for r in rows]}


class OnlineMembershipSignupRequest(BaseModel):
    org_slug: str = Field(..., min_length=1, max_length=120)
    membership_type_id: str
    first_name: str = Field(..., min_length=1, max_length=120)
    last_name: str = Field(..., min_length=1, max_length=120)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=200)
    source_id: str = Field(..., min_length=1)  # Square Web Payments SDK card token
    cardholder_name: Optional[str] = None
    phone: Optional[str] = None
    facility_name: Optional[str] = None


@router.post("/online-membership", status_code=201)
@limiter.limit("5/minute")
async def online_membership_signup(request: Request, body: OnlineMembershipSignupRequest):
    """Create the account + membership (free trial → auto-charge) in one call."""
    try:
        result = await enroll_online_membership(
            org_slug=body.org_slug,
            membership_type_id=body.membership_type_id,
            first_name=body.first_name.strip(),
            last_name=body.last_name.strip(),
            email=body.email,
            password=body.password,
            source_id=body.source_id,
            cardholder_name=body.cardholder_name,
            phone=body.phone,
            facility_name=(body.facility_name or "").strip() or None,
        )
    except SignupError as e:
        raise HTTPException(status_code=e.status, detail={"error": str(e), "code": e.code})
    except Exception as e:  # pragma: no cover - unexpected
        logger.error("Self-serve signup failed", org=body.org_slug, error=str(e))
        raise HTTPException(status_code=500, detail={"error": "Signup failed, please try again."})

    tokens = await _issue_tokens(
        result["user_id"], body.email.lower().strip(), False,
        result["org_slug"], "member",
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    result["auth"] = tokens.model_dump()
    return {"data": result}
