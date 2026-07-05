"""AuraFlow — AI Office Manager Endpoints

Dashboard endpoints for monitoring and managing the AI Office Manager:
substitution requests, inventory alerts, activity log, and summary stats.
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.dependencies.rbac import require_permission
from app.db.session import get_tenant_db

router = APIRouter()


# ── Sub Requests: List ────────────────────────────────────────────────────────

@router.get("/sub-requests")
async def list_sub_requests(
    status: Optional[str] = Query(None, description="Filter by status"),
    date_from: Optional[date] = Query(None, description="Start date filter"),
    date_to: Optional[date] = Query(None, description="End date filter"),
    limit: int = Query(50, le=200),
    rbac=Depends(require_permission("office_management.view_requests")),
):
    """List substitution requests with optional filters."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    conditions = []
    params: list = []
    idx = 1

    if status:
        conditions.append(f"sr.status = ${idx}")
        params.append(status)
        idx += 1

    if date_from:
        conditions.append(f"sr.created_at >= ${idx}::date")
        params.append(date_from.isoformat())
        idx += 1

    if date_to:
        conditions.append(f"sr.created_at < (${idx}::date + INTERVAL '1 day')")
        params.append(date_to.isoformat())
        idx += 1

    where_clause = (" AND " + " AND ".join(conditions)) if conditions else ""

    params.append(limit)
    limit_param = f"${idx}"

    async with get_tenant_db(schema_override=schema) as db:
        rows = await db.fetch(
            f"""
            SELECT sr.id,
                   COALESCE(cs.title, ct.name, 'Class') AS class_title,
                   cs.starts_at AS class_time,
                   oi.display_name AS original_instructor_name,
                   si.display_name AS sub_instructor_name,
                   sr.status,
                   sr.reason,
                   sr.attempt_count,
                   sr.created_at,
                   sr.resolved_at
            FROM sub_requests sr
            LEFT JOIN class_sessions cs ON cs.id = sr.class_session_id
            LEFT JOIN class_types ct ON ct.id = cs.class_type_id
            LEFT JOIN instructors oi ON oi.id = sr.original_instructor_id
            LEFT JOIN instructors si ON si.id = sr.sub_instructor_id
            WHERE TRUE{where_clause}
            ORDER BY sr.created_at DESC
            LIMIT {limit_param}
            """,
            *params,
        )

    return {
        "data": [
            {
                "id": str(r["id"]),
                "class_title": r["class_title"],
                "class_time": r["class_time"].isoformat() if r["class_time"] else None,
                "original_instructor_name": r["original_instructor_name"],
                "sub_instructor_name": r["sub_instructor_name"],
                "status": r["status"],
                "reason": r["reason"],
                "attempt_count": r["attempt_count"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
            }
            for r in rows
        ]
    }


# ── Sub Requests: Detail with Timeline ────────────────────────────────────────

@router.get("/sub-requests/{request_id}")
async def get_sub_request_detail(
    request_id: str,
    rbac=Depends(require_permission("office_management.view_requests")),
):
    """Get a single sub request with attempt timeline."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    async with get_tenant_db(schema_override=schema) as db:
        row = await db.fetchrow(
            """
            SELECT sr.id, sr.class_session_id,
                   COALESCE(cs.title, ct.name, 'Class') AS class_title,
                   cs.starts_at AS class_time,
                   oi.display_name AS original_instructor_name,
                   si.display_name AS sub_instructor_name,
                   sr.status, sr.reason, sr.attempt_count,
                   sr.attempted_instructor_ids,
                   sr.current_attempt_instructor_id,
                   sr.created_at, sr.resolved_at, sr.escalated_at
            FROM sub_requests sr
            LEFT JOIN class_sessions cs ON cs.id = sr.class_session_id
            LEFT JOIN class_types ct ON ct.id = cs.class_type_id
            LEFT JOIN instructors oi ON oi.id = sr.original_instructor_id
            LEFT JOIN instructors si ON si.id = sr.sub_instructor_id
            WHERE sr.id = $1
            """,
            request_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Sub request not found")

        # Build attempt timeline from attempted_instructor_ids
        attempted_ids = row["attempted_instructor_ids"] or []
        timeline = []

        if attempted_ids:
            instructors = await db.fetch(
                """
                SELECT id, display_name
                FROM instructors
                WHERE id = ANY($1)
                """,
                attempted_ids,
            )
            name_map = {str(i["id"]): i["display_name"] for i in instructors}

            for i, iid in enumerate(attempted_ids, 1):
                iid_str = str(iid)
                is_current = iid_str == str(row["current_attempt_instructor_id"]) if row["current_attempt_instructor_id"] else False
                is_accepted = iid_str == str(row["sub_instructor_id"]) if row["sub_instructor_id"] else False

                if is_accepted:
                    attempt_status = "accepted"
                elif is_current and row["status"] == "searching":
                    attempt_status = "waiting"
                else:
                    attempt_status = "declined"

                timeline.append({
                    "attempt_number": i,
                    "instructor_id": iid_str,
                    "instructor_name": name_map.get(iid_str, "Unknown"),
                    "status": attempt_status,
                })

        # Get related SMS messages for richer timeline
        sms_rows = await db.fetch(
            """
            SELECT body, type, status, created_at
            FROM sms_messages
            WHERE type IN ('sub_request', 'sub_confirmation', 'sub_notification')
            ORDER BY created_at DESC
            LIMIT 20
            """,
        )

    return {
        "data": {
            "id": str(row["id"]),
            "class_session_id": str(row["class_session_id"]),
            "class_title": row["class_title"],
            "class_time": row["class_time"].isoformat() if row["class_time"] else None,
            "original_instructor_name": row["original_instructor_name"],
            "sub_instructor_name": row["sub_instructor_name"],
            "status": row["status"],
            "reason": row["reason"],
            "attempt_count": row["attempt_count"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
            "escalated_at": row["escalated_at"].isoformat() if row["escalated_at"] else None,
            "timeline": timeline,
            "sms_log": [
                {
                    "body": s["body"],
                    "type": s["type"],
                    "status": s["status"],
                    "created_at": s["created_at"].isoformat() if s["created_at"] else None,
                }
                for s in sms_rows
            ],
        }
    }


# ── Sub Requests: Cancel ──────────────────────────────────────────────────────

@router.post("/sub-requests/{request_id}/cancel")
async def cancel_sub_request(
    request_id: str,
    rbac=Depends(require_permission("office_management.manage_requests")),
):
    """Cancel an active substitution search."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    async with get_tenant_db(schema_override=schema) as db:
        row = await db.fetchrow(
            "SELECT id, status FROM sub_requests WHERE id = $1",
            request_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Sub request not found")

        if row["status"] not in ("searching",):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel sub request with status '{row['status']}'"
            )

        await db.execute(
            """
            UPDATE sub_requests
            SET status = 'cancelled', resolved_at = NOW()
            WHERE id = $1
            """,
            request_id,
        )

    return {"status": "ok", "message": "Sub request cancelled"}


# ── Inventory Alerts ──────────────────────────────────────────────────────────

@router.get("/inventory-alerts")
async def list_inventory_alerts(
    rbac=Depends(require_permission("office_management.view_inventory")),
):
    """Query products where quantity_on_hand <= reorder_point."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    async with get_tenant_db(schema_override=schema) as db:
        rows = await db.fetch(
            """
            SELECT p.name, p.sku, i.quantity_on_hand, i.reorder_point, p.category
            FROM inventory i
            JOIN products p ON p.id = i.product_id
            WHERE i.quantity_on_hand <= i.reorder_point
              AND p.active = TRUE
            ORDER BY (i.quantity_on_hand::float / GREATEST(i.reorder_point, 1)) ASC
            """,
        )

    return {
        "data": [
            {
                "name": r["name"],
                "sku": r["sku"],
                "quantity_on_hand": r["quantity_on_hand"],
                "reorder_point": r["reorder_point"],
                "category": r["category"],
            }
            for r in rows
        ]
    }


# ── Activity Log ──────────────────────────────────────────────────────────────

@router.get("/activity-log")
async def list_activity_log(
    limit: int = Query(30, le=100),
    rbac=Depends(require_permission("office_management.view_log")),
):
    """Recent AI Office Manager actions: sub requests + SMS + inventory checks."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    async with get_tenant_db(schema_override=schema) as db:
        # Combine sub request events and related SMS messages
        rows = await db.fetch(
            """
            (
                SELECT sr.created_at AS timestamp,
                       'sub_search_started' AS action_type,
                       'Started sub search for ' || COALESCE(cs.title, 'Class')
                           || ' (replacing ' || COALESCE(oi.display_name, 'instructor') || ')' AS description,
                       sr.status
                FROM sub_requests sr
                LEFT JOIN class_sessions cs ON cs.id = sr.class_session_id
                LEFT JOIN instructors oi ON oi.id = sr.original_instructor_id
            )
            UNION ALL
            (
                SELECT sr.resolved_at AS timestamp,
                       CASE sr.status
                           WHEN 'sub_found' THEN 'sub_found'
                           WHEN 'escalated' THEN 'escalated'
                           WHEN 'cancelled' THEN 'cancelled'
                           ELSE 'resolved'
                       END AS action_type,
                       CASE sr.status
                           WHEN 'sub_found' THEN COALESCE(si.display_name, 'Instructor') || ' accepted sub for ' || COALESCE(cs.title, 'Class')
                           WHEN 'escalated' THEN 'Sub search escalated for ' || COALESCE(cs.title, 'Class') || ' — no subs available'
                           WHEN 'cancelled' THEN 'Sub search cancelled for ' || COALESCE(cs.title, 'Class')
                           ELSE 'Sub request resolved for ' || COALESCE(cs.title, 'Class')
                       END AS description,
                       sr.status
                FROM sub_requests sr
                LEFT JOIN class_sessions cs ON cs.id = sr.class_session_id
                LEFT JOIN instructors si ON si.id = sr.sub_instructor_id
                WHERE sr.resolved_at IS NOT NULL
            )
            UNION ALL
            (
                SELECT sm.created_at AS timestamp,
                       'sms_sent' AS action_type,
                       'Sent ' || sm.type || ' SMS: ' || LEFT(sm.body, 80) AS description,
                       sm.status
                FROM sms_messages sm
                WHERE sm.type IN ('sub_request', 'sub_confirmation', 'sub_notification', 'office_manager', 'ai_response')
            )
            ORDER BY timestamp DESC NULLS LAST
            LIMIT $1
            """,
            limit,
        )

    return {
        "data": [
            {
                "timestamp": r["timestamp"].isoformat() if r["timestamp"] else None,
                "action_type": r["action_type"],
                "description": r["description"],
                "status": r["status"],
            }
            for r in rows
        ]
    }


# ── Summary Stats ─────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(
    rbac=Depends(require_permission("office_management.view_stats")),
):
    """Summary statistics for the AI Office Manager dashboard."""
    schema = f"af_tenant_{rbac["org_slug"]}"

    async with get_tenant_db(schema_override=schema) as db:
        # Active sub searches
        active = await db.fetchval(
            "SELECT COUNT(*) FROM sub_requests WHERE status = 'searching'"
        )

        # Subs found this month
        found = await db.fetchval(
            """
            SELECT COUNT(*) FROM sub_requests
            WHERE status = 'sub_found'
              AND resolved_at >= date_trunc('month', CURRENT_DATE)
            """
        )

        # Escalated this month
        escalated = await db.fetchval(
            """
            SELECT COUNT(*) FROM sub_requests
            WHERE status = 'escalated'
              AND escalated_at >= date_trunc('month', CURRENT_DATE)
            """
        )

        # Inventory alerts count
        inventory_alerts = await db.fetchval(
            """
            SELECT COUNT(*) FROM inventory i
            JOIN products p ON p.id = i.product_id
            WHERE i.quantity_on_hand <= i.reorder_point
              AND p.active = TRUE
            """
        )

    return {
        "data": {
            "active_searches": active or 0,
            "subs_found_this_month": found or 0,
            "escalated": escalated or 0,
            "inventory_alerts": inventory_alerts or 0,
        }
    }
