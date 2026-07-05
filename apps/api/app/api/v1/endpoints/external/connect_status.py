"""AuraFlow — External Stripe Connect status endpoint.

API-key-authed read of a tenant's Connect onboarding state. Lets the
white-label portal know whether payment-processing is currently
available — if not, it can show a "payments temporarily unavailable"
banner instead of letting members start checkouts that will fail.

GET /api/v1/external/connect/status
    Headers: Authorization: Bearer af_live_<tenant-api-key>

Response:
    {
      "ready_for_charges": bool,    # the only field the portal actually needs
      "charges_enabled":   bool,    # raw Stripe flag
      "payouts_enabled":   bool,    # raw Stripe flag
      "has_account":       bool     # has an acct_* id been provisioned at all
    }

Note: this endpoint reads ONLY the locally-cached state from
af_global.organizations (updated by Connect webhooks). It does NOT
hit Stripe — that path lives in StripeService.get_connect_status,
called by the JWT-authed admin endpoint. Portal callers don't need
the cost/latency of a Stripe round-trip for this hot-path check.
"""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.dependencies.api_key_auth import get_api_key_context
from app.services.payments.connect_account import resolve_connect_status

router = APIRouter()


@router.get("/connect/status", summary="Stripe Connect readiness for this tenant")
async def get_connect_status(
    ctx: Annotated[dict, Depends(get_api_key_context)],
):
    status = await resolve_connect_status(ctx["org_id"])
    return {
        "has_account": status["stripe_account_id"] is not None,
        "charges_enabled": status["charges_enabled"],
        "payouts_enabled": status["payouts_enabled"],
        "ready_for_charges": status["ready_for_charges"],
    }
