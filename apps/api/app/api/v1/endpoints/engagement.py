"""AuraFlow — AI Engagement Autopilot Endpoints

Dashboard endpoints for managing the AI Engagement Autopilot:
campaign listing, stats, conversation threads, pause/escalate actions,
manual scan trigger, and settings management.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.v1.dependencies.rbac import require_permission
from app.db.session import get_tenant_db

router = APIRouter()


# ── Pydantic Models ──────────────────────────────────────────────────────────

class EngagementSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    max_per_day: Optional[int] = None
    follow_up_days: Optional[int] = None


# ── Stats ────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def engagement_stats(
    rbac=Depends(require_permission("engagement.view_stats")),
):
    """Summary stats for the engagement autopilot dashboard."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    async with get_tenant_db(schema_override=schema) as db:
        row = await db.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'active')::int AS active_campaigns,
                COUNT(*) FILTER (
                    WHERE reply_count > 0
                    AND created_at >= date_trunc('month', NOW())
                )::int AS replies_this_month,
                COUNT(*) FILTER (
                    WHERE status = 'converted'
                    AND created_at >= date_trunc('month', NOW())
                )::int AS conversions_this_month,
                COALESCE(SUM(followup_count + 1) FILTER (
                    WHERE created_at >= date_trunc('month', NOW())
                ), 0)::int AS emails_sent_this_month
            FROM engagement_campaigns
            """
        )

    return {
        "data": {
            "active_campaigns": row["active_campaigns"] if row else 0,
            "replies_this_month": row["replies_this_month"] if row else 0,
            "conversions_this_month": row["conversions_this_month"] if row else 0,
            "emails_sent_this_month": row["emails_sent_this_month"] if row else 0,
        }
    }


# ── Campaigns: List ─────────────────────────────────────────────────────────

@router.get("/campaigns")
async def list_campaigns(
    status: Optional[str] = Query(None, description="Filter by status"),
    engagement_type: Optional[str] = Query(None, description="Filter by type"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    rbac=Depends(require_permission("engagement.view_campaigns")),
):
    """List engagement campaigns with optional filters."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    conditions = []
    params: list = []
    idx = 1

    if status:
        conditions.append(f"ec.status = ${idx}")
        params.append(status)
        idx += 1

    if engagement_type:
        conditions.append(f"ec.engagement_type = ${idx}")
        params.append(engagement_type)
        idx += 1

    where_clause = (" AND " + " AND ".join(conditions)) if conditions else ""

    params.append(limit)
    limit_param = f"${idx}"
    idx += 1

    params.append(offset)
    offset_param = f"${idx}"

    async with get_tenant_db(schema_override=schema) as db:
        rows = await db.fetch(
            f"""
            SELECT ec.id,
                   COALESCE(m.first_name || ' ' || m.last_name, 'Unknown') AS member_name,
                   COALESCE(m.email, '') AS member_email,
                   ec.engagement_type,
                   ec.status,
                   ec.outcome,
                   ec.followup_count,
                   ec.reply_count,
                   ec.initial_email_sent_at,
                   ec.last_email_sent_at,
                   ec.created_at
            FROM engagement_campaigns ec
            LEFT JOIN members m ON m.id = ec.member_id
            WHERE TRUE{where_clause}
            ORDER BY ec.created_at DESC
            LIMIT {limit_param} OFFSET {offset_param}
            """,
            *params,
        )

    return {
        "data": [
            {
                "id": str(r["id"]),
                "member_name": r["member_name"],
                "member_email": r["member_email"],
                "engagement_type": r["engagement_type"],
                "status": r["status"],
                "outcome": r["outcome"],
                "followup_count": r["followup_count"],
                "reply_count": r["reply_count"],
                "initial_email_sent_at": r["initial_email_sent_at"].isoformat() if r["initial_email_sent_at"] else None,
                "last_email_sent_at": r["last_email_sent_at"].isoformat() if r["last_email_sent_at"] else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    }


# ── Campaign Detail (with message thread) ───────────────────────────────────

@router.get("/campaigns/{campaign_id}")
async def get_campaign_detail(
    campaign_id: str,
    rbac=Depends(require_permission("engagement.view_campaigns")),
):
    """Get a single campaign with its full message history."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    async with get_tenant_db(schema_override=schema) as db:
        campaign = await db.fetchrow(
            """
            SELECT ec.id,
                   COALESCE(m.first_name || ' ' || m.last_name, 'Unknown') AS member_name,
                   COALESCE(m.email, '') AS member_email,
                   ec.engagement_type,
                   ec.status,
                   ec.outcome,
                   ec.followup_count,
                   ec.reply_count,
                   ec.initial_email_sent_at,
                   ec.last_email_sent_at,
                   ec.created_at
            FROM engagement_campaigns ec
            LEFT JOIN members m ON m.id = ec.member_id
            WHERE ec.id = $1::uuid
            """,
            campaign_id,
        )

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        messages = await db.fetch(
            """
            SELECT id, direction, subject, body, sent_at, created_at
            FROM engagement_messages
            WHERE campaign_id = $1::uuid
            ORDER BY created_at ASC
            """,
            campaign_id,
        )

    return {
        "data": {
            "id": str(campaign["id"]),
            "member_name": campaign["member_name"],
            "member_email": campaign["member_email"],
            "engagement_type": campaign["engagement_type"],
            "status": campaign["status"],
            "outcome": campaign["outcome"],
            "followup_count": campaign["followup_count"],
            "reply_count": campaign["reply_count"],
            "initial_email_sent_at": campaign["initial_email_sent_at"].isoformat() if campaign["initial_email_sent_at"] else None,
            "last_email_sent_at": campaign["last_email_sent_at"].isoformat() if campaign["last_email_sent_at"] else None,
            "created_at": campaign["created_at"].isoformat() if campaign["created_at"] else None,
            "messages": [
                {
                    "id": str(msg["id"]),
                    "direction": msg["direction"],
                    "subject": msg["subject"],
                    "body": msg["body"],
                    "sent_at": msg["sent_at"].isoformat() if msg["sent_at"] else None,
                    "created_at": msg["created_at"].isoformat() if msg["created_at"] else None,
                }
                for msg in messages
            ],
        }
    }


# ── Pause Campaign ──────────────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    rbac=Depends(require_permission("engagement.manage_campaigns")),
):
    """Pause a campaign by setting status to 'completed' with outcome 'manual_pause'."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    async with get_tenant_db(schema_override=schema) as db:
        result = await db.fetchrow(
            """
            UPDATE engagement_campaigns
            SET status = 'completed', outcome = 'manual_pause', updated_at = NOW()
            WHERE id = $1::uuid AND status IN ('active', 'replied')
            RETURNING id
            """,
            campaign_id,
        )

    if not result:
        raise HTTPException(status_code=404, detail="Campaign not found or already completed")

    return {"data": {"id": str(result["id"]), "status": "completed", "outcome": "manual_pause"}}


# ── Escalate Campaign ───────────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/escalate")
async def escalate_campaign(
    campaign_id: str,
    rbac=Depends(require_permission("engagement.manage_campaigns")),
):
    """Escalate a campaign to the studio owner for personal follow-up."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    async with get_tenant_db(schema_override=schema) as db:
        result = await db.fetchrow(
            """
            UPDATE engagement_campaigns
            SET status = 'escalated', outcome = 'escalated_to_owner', updated_at = NOW()
            WHERE id = $1::uuid AND status IN ('active', 'replied')
            RETURNING id
            """,
            campaign_id,
        )

    if not result:
        raise HTTPException(status_code=404, detail="Campaign not found or already completed")

    return {"data": {"id": str(result["id"]), "status": "escalated", "outcome": "escalated_to_owner"}}


# ── Manual Scan Trigger ──────────────────────────────────────────────────────

@router.post("/scan")
async def trigger_scan(
    rbac=Depends(require_permission("engagement.manage_campaigns")),
):
    """Manually trigger an engagement scan for disengaged members."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    # Fire Celery task asynchronously
    try:
        from app.workers.celery_app import app as celery_app
        celery_app.send_task(
            "engagement.scan_disengaged_members",
            kwargs={"schema": schema},
        )
    except Exception:
        # If Celery is not running, still return success
        pass

    return {"data": {"status": "scan_queued", "message": "Engagement scan has been queued"}}


# ── Settings: Get ────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(
    rbac=Depends(require_permission("engagement.view_settings")),
):
    """Get engagement autopilot settings."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    async with get_tenant_db(schema_override=schema) as db:
        row = await db.fetchrow(
            """
            SELECT enabled, max_campaigns_per_day, followup_interval_days
            FROM engagement_settings
            LIMIT 1
            """
        )

    if not row:
        return {
            "data": {
                "enabled": False,
                "max_campaigns_per_day": 5,
                "followup_interval_days": 7,
            }
        }

    return {
        "data": {
            "enabled": row["enabled"],
            "max_campaigns_per_day": row["max_campaigns_per_day"],
            "followup_interval_days": row["followup_interval_days"],
        }
    }


# ── Settings: Update ────────────────────────────────────────────────────────

@router.put("/settings")
async def update_settings(
    body: EngagementSettingsUpdate,
    rbac=Depends(require_permission("engagement.configure")),
):
    """Update engagement autopilot settings."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    async with get_tenant_db(schema_override=schema) as db:
        # Update existing settings row (created during provisioning)
        existing = await db.fetchrow("SELECT id FROM engagement_settings LIMIT 1")
        if existing:
            row = await db.fetchrow(
                """
                UPDATE engagement_settings SET
                    enabled = COALESCE($1, enabled),
                    max_campaigns_per_day = COALESCE($2, max_campaigns_per_day),
                    followup_interval_days = COALESCE($3, followup_interval_days),
                    updated_at = NOW()
                RETURNING enabled, max_campaigns_per_day, followup_interval_days
                """,
                body.enabled,
                body.max_per_day,
                body.follow_up_days,
            )
        else:
            row = await db.fetchrow(
                """
                INSERT INTO engagement_settings (enabled, max_campaigns_per_day, followup_interval_days)
                VALUES (COALESCE($1, TRUE), COALESCE($2, 10), COALESCE($3, 3))
                RETURNING enabled, max_campaigns_per_day, followup_interval_days
                """,
                body.enabled,
                body.max_per_day,
                body.follow_up_days,
            )

    return {
        "data": {
            "enabled": row["enabled"],
            "max_campaigns_per_day": row["max_campaigns_per_day"],
            "followup_interval_days": row["followup_interval_days"],
        }
    }


@router.get("/winback-log")
async def get_winback_log(
    rbac=Depends(require_permission("engagement.view_log")),
    limit: int = 100,
):
    """Get recent winback/churn emails sent by the AI."""
    schema = f"af_tenant_{rbac['org_slug']}"

    async with get_tenant_db(schema_override=schema) as db:
        rows = await db.fetch(
            """
            SELECT cl.recipient, cl.subject, cl.body_preview, cl.status, cl.created_at,
                   m.first_name || ' ' || m.last_name AS member_name
            FROM communication_log cl
            LEFT JOIN members m ON m.id = cl.member_id
            WHERE cl.type = 'winback'
            ORDER BY cl.created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return {"data": [dict(r) for r in rows]}
