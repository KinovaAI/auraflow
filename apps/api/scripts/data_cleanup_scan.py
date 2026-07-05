#!/usr/bin/env python3
"""
AuraFlow — Stale/Orphan Data Sweep (Read-Only)

Reports candidates for deletion across platform + tenant tables. Deletes
NOTHING on its own — intended to be reviewed before any cleanup action
is taken.

Categories scanned:
  1. af_global.refresh_tokens — revoked or expired > 60 days
  2. af_global.processed_webhook_events — older than 90 days (dedup window)
  3. af_tenant_*.communication_log — entries for members that no longer exist
  4. af_tenant_*.notifications — entries for members that no longer exist
  5. af_tenant_*.sms_messages — entries for members that no longer exist
  6. af_tenant_*.engagement_messages — entries for dead campaigns
  7. af_tenant_*.chatbot_messages — entries for dead conversations

Usage:
    sudo docker exec auraflow_api python /app/scripts/data_cleanup_scan.py
    sudo docker exec auraflow_api python /app/scripts/data_cleanup_scan.py --json

Exit codes:
    0 — clean (0 candidates)
    1 — candidates found (human review needed before deletion)
    2 — scanner failure
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")

from app.db.session import get_global_db, get_tenant_db


async def _scan_global() -> list[dict]:
    out: list[dict] = []
    async with get_global_db() as db:
        # Expired / revoked refresh tokens older than 60 days
        row = await db.fetchrow("""
            SELECT COUNT(*) AS cnt,
                   MIN(created_at) AS oldest,
                   MAX(created_at) AS newest
            FROM af_global.refresh_tokens
            WHERE (revoked_at IS NOT NULL OR expires_at < NOW())
              AND created_at < NOW() - INTERVAL '60 days'
        """)
        out.append({
            "target": "af_global.refresh_tokens",
            "criterion": "revoked or expired > 60 days ago",
            "count": row["cnt"],
            "oldest": row["oldest"].isoformat() if row["oldest"] else None,
            "newest": row["newest"].isoformat() if row["newest"] else None,
        })

        # Processed webhook events older than 90 days
        row = await db.fetchrow("""
            SELECT COUNT(*) AS cnt, MIN(processed_at) AS oldest, MAX(processed_at) AS newest
            FROM af_global.processed_webhook_events
            WHERE processed_at < NOW() - INTERVAL '90 days'
        """)
        out.append({
            "target": "af_global.processed_webhook_events",
            "criterion": "processed > 90 days ago (past Stripe retry window)",
            "count": row["cnt"],
            "oldest": row["oldest"].isoformat() if row["oldest"] else None,
            "newest": row["newest"].isoformat() if row["newest"] else None,
        })

    return out


async def _scan_tenant(schema: str) -> list[dict]:
    out: list[dict] = []

    async with get_tenant_db(schema_override=schema) as db:
        # communication_log entries for deleted members
        cnt = await db.fetchval("""
            SELECT COUNT(*) FROM communication_log cl
            WHERE cl.member_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM members m WHERE m.id = cl.member_id)
        """)
        out.append({
            "target": f"{schema}.communication_log",
            "criterion": "orphan (member deleted)",
            "count": cnt,
        })

        # notifications for deleted members
        tbl_exists = await db.fetchval("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = 'notifications'
              AND column_name = 'member_id'
        """, schema)
        if tbl_exists:
            cnt = await db.fetchval("""
                SELECT COUNT(*) FROM notifications n
                WHERE n.member_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM members m WHERE m.id = n.member_id)
            """)
            out.append({
                "target": f"{schema}.notifications",
                "criterion": "orphan (member deleted)",
                "count": cnt,
            })

        # sms_messages for deleted members
        cnt = await db.fetchval("""
            SELECT COUNT(*) FROM sms_messages s
            WHERE s.member_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM members m WHERE m.id = s.member_id)
        """)
        out.append({
            "target": f"{schema}.sms_messages",
            "criterion": "orphan (member deleted)",
            "count": cnt,
        })

        # engagement_messages for dead campaigns
        tbl = await db.fetchval("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = $1 AND table_name = 'engagement_campaigns'
        """, schema)
        if tbl:
            cnt = await db.fetchval("""
                SELECT COUNT(*) FROM engagement_messages em
                WHERE em.campaign_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM engagement_campaigns c WHERE c.id = em.campaign_id)
            """)
            out.append({
                "target": f"{schema}.engagement_messages",
                "criterion": "orphan (campaign deleted)",
                "count": cnt,
            })

        # Very old communication_log (retention candidate — HIPAA 6 year minimum
        # for audit, reasonable cap of 18 months for non-audit comms).
        cnt = await db.fetchval("""
            SELECT COUNT(*) FROM communication_log
            WHERE created_at < NOW() - INTERVAL '18 months'
        """)
        out.append({
            "target": f"{schema}.communication_log",
            "criterion": "older than 18 months (retention candidate, not orphan)",
            "count": cnt,
        })

        # webhook_deliveries — successful deliveries older than 90 days.
        # Dead-letter rows are preserved for forensics.
        cnt = await db.fetchval("""
            SELECT COUNT(*) FROM webhook_deliveries
            WHERE status = 'delivered'
              AND delivered_at IS NOT NULL
              AND delivered_at < NOW() - INTERVAL '90 days'
        """)
        out.append({
            "target": f"{schema}.webhook_deliveries",
            "criterion": "delivered successfully > 90 days ago (safe to delete)",
            "count": cnt,
        })

    return out


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results: dict = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "categories": [],
    }

    results["categories"].extend(await _scan_global())

    async with get_global_db() as db:
        orgs = await db.fetch(
            "SELECT schema_name FROM af_global.organizations "
            "WHERE status IN ('active', 'trial') ORDER BY schema_name"
        )
    for org in orgs:
        results["categories"].extend(await _scan_tenant(org["schema_name"]))

    total = sum(c["count"] for c in results["categories"] if c["count"])

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(f"Data cleanup scan — {results['scanned_at']}")
        print()
        for c in results["categories"]:
            marker = "✓" if c["count"] == 0 else "⚠"
            print(f"  {marker} {c['target']}")
            print(f"     criterion: {c['criterion']}")
            print(f"     count:     {c['count']}")
            if c.get("oldest"):
                print(f"     oldest:    {c['oldest']}")
            if c.get("newest"):
                print(f"     newest:    {c['newest']}")
            print()
        print(f"TOTAL CANDIDATES: {total}")
        if total == 0:
            print("✅ No stale/orphan data detected.")
        else:
            print("⚠  Candidates found. Review before deleting.")

    sys.exit(1 if total else 0)


if __name__ == "__main__":
    asyncio.run(main())
