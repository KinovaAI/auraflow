#!/usr/bin/env python3
"""Additive top-up: add MISSING role-template keys to af_global.user_permissions.

This script is strictly additive. It never deletes a row, never flips an
existing is_granted from TRUE to FALSE, and never overrides any value
already in the table. The only thing it does is insert rows for
permission keys the user does NOT yet have, with is_granted=TRUE, so
they retain access to actions their old role-based gates allowed.

Why:
- The permission overhaul replaced require_role with require_permission
  everywhere in the API. Endpoints that used to accept any "owner"/
  "admin"/"instructor"/"front_desk" user now demand a specific action-
  level key like workshops.edit. Existing user_permissions rows already
  configured by the owner via the staff matrix STAY UNTOUCHED. This
  script only fills in gaps so a front_desk hire who already had a few
  custom grants doesn't lose access to the rest of the front-desk
  defaults overnight.

Behavior per user (role != owner):
1. Read their current permission_keys from af_global.user_permissions
   (regardless of is_granted, so a user with an explicit `false` for a
   key is NOT silently re-granted).
2. From DEFAULT_ROLE_PERMISSIONS[role], compute the set of template
   keys NOT already present in (1).
3. Insert ONLY those missing keys with is_granted=TRUE using
   ON CONFLICT DO NOTHING. Existing rows are guaranteed untouched.
4. Flush the Redis cache entry for (org, user) so the next request
   sees the new keys immediately.

Owners are skipped (they have implicit bypass on every permission).

Default is dry-run (--apply to write). Idempotent.

Run from inside the api container:
    sudo docker exec auraflow_api python /app/scripts/backfill_permissions_from_role_templates.py
    sudo docker exec auraflow_api python /app/scripts/backfill_permissions_from_role_templates.py --apply
"""
import argparse
import asyncio
import sys

sys.path.insert(0, "/app")

from app.db.session import get_global_db
from app.services.permissions import DEFAULT_ROLE_PERMISSIONS


async def backfill(apply: bool) -> None:
    async with get_global_db() as db:
        rows = await db.fetch(
            """
            SELECT ou.user_id, ou.organization_id, ou.role,
                   o.name AS org_name, o.slug AS org_slug,
                   u.email
            FROM af_global.organization_users ou
            JOIN af_global.organizations o ON o.id = ou.organization_id
            JOIN af_global.users u ON u.id = ou.user_id
            WHERE ou.is_active = TRUE
              AND o.status IN ('active', 'trial')
            ORDER BY o.slug, ou.role, u.email
            """
        )

    print(f"\nFound {len(rows)} active (user, org) pairs across all tenants\n")

    counts = {
        "owner_skipped": 0,
        "unknown_role": 0,
        "no_change": 0,
        "topped_up": 0,
        "keys_added": 0,
    }
    by_role: dict[str, int] = {}

    from app.core.redis import get_redis
    redis = await get_redis()

    for row in rows:
        role = row["role"]
        user_id = str(row["user_id"])
        org_id = str(row["organization_id"])

        by_role[role] = by_role.get(role, 0) + 1

        if role == "owner":
            counts["owner_skipped"] += 1
            print(f"  SKIP  {row['org_slug']:20} {row['email']:40} owner (implicit bypass)")
            continue

        template = DEFAULT_ROLE_PERMISSIONS.get(role)
        if template is None:
            counts["unknown_role"] += 1
            print(f"  WARN  {row['org_slug']:20} {row['email']:40} unknown role {role!r}")
            continue

        # Read existing keys for this user — ANY is_granted value counts as
        # "already configured" so we never override an explicit owner choice.
        async with get_global_db() as db:
            existing_rows = await db.fetch(
                """
                SELECT permission_key
                FROM af_global.user_permissions
                WHERE organization_id = $1 AND user_id = $2
                """,
                org_id, user_id,
            )
        existing_keys = {r["permission_key"] for r in existing_rows}

        missing_keys = [k for k in template if k not in existing_keys]

        if not missing_keys:
            counts["no_change"] += 1
            print(f"  OK    {row['org_slug']:20} {row['email']:40} role={role:11} already has all {len(template)} template keys")
            continue

        action = "ADD " if apply else "DRY "
        print(
            f"  {action}  {row['org_slug']:20} {row['email']:40} role={role:11} "
            f"+{len(missing_keys)} missing of {len(template)} (existing rows preserved: {len(existing_keys)})"
        )

        if apply:
            async with get_global_db() as db:
                for key in missing_keys:
                    # ON CONFLICT DO NOTHING — never overrides an existing row.
                    await db.execute(
                        """
                        INSERT INTO af_global.user_permissions
                            (organization_id, user_id, permission_key, is_granted, granted_by)
                        VALUES ($1, $2, $3, TRUE, $2)
                        ON CONFLICT (organization_id, user_id, permission_key)
                        DO NOTHING
                        """,
                        org_id, user_id, key,
                    )
            counts["topped_up"] += 1
            counts["keys_added"] += len(missing_keys)

            # Bust Redis cache so the next request sees the new keys.
            if redis:
                await redis.delete(f"perms:{org_id}:{user_id}")

    print(f"\n──── Summary ────")
    print(f"  Total (user, org) pairs scanned: {len(rows)}")
    for role, c in sorted(by_role.items()):
        print(f"    role={role:12}  {c} users")
    print(f"  Owner skipped (bypass):     {counts['owner_skipped']}")
    print(f"  Unknown role (skipped):     {counts['unknown_role']}")
    print(f"  Already complete (no-op):   {counts['no_change']}")
    if apply:
        print(f"  Users topped up:            {counts['topped_up']}")
        print(f"  Total keys added:           {counts['keys_added']}")
    else:
        print(f"  Would top up:               {len(rows) - counts['owner_skipped'] - counts['unknown_role'] - counts['no_change']} users")
        print(f"  (dry run — re-run with --apply to actually write)")
    print(f"\n  Guarantee: zero rows deleted, zero existing values overridden.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Actually write to the DB (default is dry-run)")
    args = parser.parse_args()
    asyncio.run(backfill(apply=args.apply))


if __name__ == "__main__":
    main()
