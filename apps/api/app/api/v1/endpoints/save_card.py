"""Public hosted card-save flow.

Replaces the legacy "click Manage Billing → opens an external hosted
payment portal in a new tab" behavior for every client website that
integrates with our API. The public URL `https://app.auraflow.fit/save-card?token=<jwt>`
opens a Square Web Payments SDK card form, tokenizes the card, and saves
it to the member's Square customer record. On success the page redirects
back to the studio's `return_url`.

The JWT is short-lived (15 min) and carries member_id + org_id + return_url,
all signed with APP_SECRET. The page itself is public — the JWT is the
only thing protecting member-scoped writes, so the TTL is intentionally
tight.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_global_db, get_tenant_db
from app.services.payments.square_service import square_service
from app.services.payments.square_oauth_service import square_oauth_service


router = APIRouter()


TOKEN_TTL_MINUTES = 15
TOKEN_PURPOSE = "save_card"


def issue_save_card_token(
    member_id: str,
    org_id: str,
    schema_name: str,
    return_url: str,
) -> str:
    """Sign a short-lived JWT for the public card-save page."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=TOKEN_TTL_MINUTES)
    return jwt.encode(
        {
            "purpose": TOKEN_PURPOSE,
            "member_id": member_id,
            "org_id": org_id,
            "schema_name": schema_name,
            "return_url": return_url,
            "iat": now,
            "exp": exp,
        },
        settings.APP_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def _decode_token(token: str) -> dict:
    """Decode + validate the save-card JWT. Raises HTTPException on
    expired/invalid/wrong-purpose tokens."""
    try:
        claims = jwt.decode(
            token,
            settings.APP_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=410, detail="This link has expired. Please return to the studio website and click 'Manage Billing' again.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Invalid or tampered link.")
    if claims.get("purpose") != TOKEN_PURPOSE:
        raise HTTPException(status_code=400, detail="Wrong token purpose.")
    for required in ("member_id", "org_id", "schema_name", "return_url"):
        if not claims.get(required):
            raise HTTPException(status_code=400, detail=f"Token missing {required}.")
    return claims


# ── GET /save-card/config ────────────────────────────────────────────
# Public endpoint the card-save page calls on load. Returns just enough
# data to mount the Square Web Payments SDK form for THIS studio + member.

@router.get("/save-card/config")
async def save_card_config(token: str):
    claims = _decode_token(token)
    org_id = claims["org_id"]
    schema = claims["schema_name"]
    member_id = claims["member_id"]

    async with get_global_db() as db:
        org = await db.fetchrow(
            "SELECT name, square_location_id FROM af_global.organizations WHERE id = $1",
            org_id,
        )
    if not org or not org["square_location_id"]:
        raise HTTPException(status_code=503, detail="Studio Square account is not configured.")

    async with get_tenant_db(schema_override=schema) as tdb:
        member = await tdb.fetchrow(
            "SELECT first_name, last_name FROM members WHERE id = $1",
            member_id,
        )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")

    return {
        "data": {
            "application_id": settings.SQUARE_OAUTH_APPLICATION_ID,
            "location_id": org["square_location_id"],
            "environment": settings.SQUARE_ENVIRONMENT,
            "studio_name": org["name"],
            "member_name": f"{member['first_name']} {member['last_name']}".strip(),
            "return_url": claims["return_url"],
        }
    }


# ── POST /save-card/submit ───────────────────────────────────────────
# Receives the Square Web Payments SDK nonce + token, saves the card to
# the member's Square customer (creating the customer record on first
# save if needed), returns success so the page can redirect home.

class SaveCardSubmitRequest(BaseModel):
    token: str
    source_id: str   # Square Web Payments SDK nonce (cnon:...)
    cardholder_name: Optional[str] = None


@router.post("/save-card/submit")
async def save_card_submit(body: SaveCardSubmitRequest):
    claims = _decode_token(body.token)
    org_id = claims["org_id"]
    schema = claims["schema_name"]
    member_id = claims["member_id"]

    # Resolve the studio's Square OAuth access token
    merchant_token = await square_oauth_service.get_merchant_access_token(org_id)
    if not merchant_token:
        raise HTTPException(status_code=503, detail="Studio Square account is not connected.")

    async with get_tenant_db(schema_override=schema) as tdb:
        member = await tdb.fetchrow(
            "SELECT id, email, first_name, last_name, square_customer_id FROM members WHERE id = $1",
            member_id,
        )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")

    # Ensure Square customer exists. Cards must be attached to a customer.
    customer_id = member["square_customer_id"]
    if not customer_id:
        cust_resp = await square_service.create_customer(
            merchant_access_token=merchant_token,
            email=member["email"],
            first_name=member["first_name"],
            last_name=member["last_name"],
        )
        customer_id = cust_resp["customer_id"]
        async with get_tenant_db(schema_override=schema) as tdb:
            await tdb.execute(
                "UPDATE members SET square_customer_id = $1, updated_at = NOW() WHERE id = $2",
                customer_id, member_id,
            )

    try:
        card = await square_service.create_card(
            merchant_access_token=merchant_token,
            customer_id=customer_id,
            source_id=body.source_id,
            cardholder_name=body.cardholder_name,
        )
    except Exception as e:
        logger.error("save-card: Square create_card failed", member_id=member_id, error=str(e))
        raise HTTPException(status_code=400, detail="We couldn't save that card. Please double-check the number and try again.")

    logger.info(
        "save-card: card saved",
        member_id=member_id, org_id=org_id,
        card_brand=card.get("card_brand"), last_4=card.get("last_4"),
    )

    return {
        "data": {
            "saved": True,
            "card_brand": card.get("card_brand"),
            "last_4": card.get("last_4"),
            "return_url": claims["return_url"],
        }
    }
