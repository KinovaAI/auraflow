# Permission Overhaul Plan

**Created:** 2026-05-20
**Status:** Planned — not yet started
**Trigger:** Don will run this weekend; do not execute until told.

## The problem

Today AuraFlow gates every API endpoint with `require_role("owner" | "admin" | ...)`. The roles form a rigid 5-level hierarchy (owner > admin > instructor > front_desk > member), and the only way to give a staff member access to one thing is to give them everything below that level.

Concrete example: Brittany Kitchen-Caress is role=`instructor`. To let her edit a workshop and add a flyer, the current system forces her up to `admin` — which also unlocks payroll rates, refunds, and studio settings. There is no way to grant `workshops.edit` without granting `everything an admin can do`.

A separate granular permission system exists in code (`af_global.user_permissions` + `PermissionService` + the `PermissionMatrix` UI on `/dashboard/staff/[userId]`) but is **not enforced anywhere**. Toggling those checkboxes only hides sidebar links. The backend ignores them.

## Don's intent (verbatim, 2026-05-20)

> "The idea of the roles is ONLY TO PRESET BASIC PERMISSIONS NOT TO CONTROL THE FUCKING SYSTEM. The role is supposed to set a general set of actions/permissions that can then be fine tuned by the owner/admin. It is supposed to make admin easier not be the defining role of what someone can do. … I am god and I decide what permissions people get. The backend is to listen to me not some generic fucking role. … The role is to set beginner permissions for a new staff member only. It does not define what they can do it defines the starting point."

Operating principles:
1. **Permissions, not roles, control access.** Every gate is a permission check.
2. **Roles are only seed defaults.** Picking `instructor` when adding a staff member pre-fills a set of permissions; after that the owner edits each box.
3. **Owner is the only role with implicit override.** Everyone else is a pure bag of permission grants.
4. **No more "admin can do X because they're admin."** If they can do X, they have `X` ticked.

## End state

| Layer | After this change |
|---|---|
| `organization_users.role` | Vestigial — kept so `owner` retains implicit bypass, otherwise informational |
| `af_global.user_permissions` | The authoritative source of access — already exists |
| `PermissionService.has_permission(...)` | Called by **every** gated endpoint |
| `require_role(...)` | Removed from API code (search-replace audit) |
| `require_permission("workshops.edit")` | New dependency, replaces every `require_role` site |
| Staff settings UI | Shows ~60–80 per-action toggles, grouped by area, per-user customizable. "Apply template" buttons (instructor / front_desk / manager) are convenience only |

## Permission keys (action-level, not module-level)

Final list will be locked in step 1 below; current proposed set:

**Workshops (`courses` with type='workshop')**
- `workshops.view`, `workshops.create`, `workshops.edit`, `workshops.publish`, `workshops.cancel`, `workshops.delete`
- `workshops.set_pricing`, `workshops.set_payout`, `workshops.manage_enrollments`, `workshops.upload_flyer`

**Classes / Schedule**
- `schedule.view`, `schedule.create_session`, `schedule.edit_session`, `schedule.cancel_session`
- `schedule.check_in_members`, `schedule.book_member`, `schedule.modify_roster`

**Private sessions**
- `private_sessions.view_all`, `private_sessions.view_own`
- `private_sessions.create`, `private_sessions.set_pricing`
- `private_sessions.cancel_as_instructor`, `private_sessions.cancel_as_staff`
- `private_sessions.complete`, `private_sessions.set_availability`

**Members**
- `members.view`, `members.create`, `members.edit`, `members.deactivate`, `members.delete_gdpr`
- `members.add_note`, `members.view_notes`
- `members.view_health_data`, `members.edit_health_data`
- `members.grant_credit`, `members.revoke_credit`, `members.view_credits`
- `members.view_payments`, `members.refund_payment`
- `members.assign_membership`, `members.freeze_membership`, `members.cancel_membership`
- `members.export_csv`, `members.export_gdpr_data`

**Memberships / pricing**
- `memberships.view_types`, `memberships.create_type`, `memberships.edit_type`, `memberships.deactivate_type`
- `memberships.set_pricing`

**Payments**
- `payments.view_all`, `payments.refund`, `payments.update_card_on_file`, `payments.send_payment_link`

**POS / Retail / Gift cards**
- `pos.use`, `pos.refund`
- `inventory.view`, `inventory.edit`
- `gift_cards.create`, `gift_cards.refund`

**Payroll & time clock**
- `time_clock.clock_self`, `time_clock.view_self`
- `time_clock.view_others`, `time_clock.edit_others`
- `payroll.view_self`, `payroll.view_others`, `payroll.set_rates`, `payroll.run_payout`, `payroll.adjust`

**Marketing**
- `marketing.view`, `marketing.send_campaign`, `marketing.create_campaign`, `marketing.edit_campaign`
- `marketing.send_sms`, `marketing.send_email`

**AI / Analytics**
- `ai.use_chatbot`, `ai.view_insights`, `ai.run_office_manager`
- `analytics.view`, `analytics.export`

**Email / Integrations / Settings**
- `email.send_studio`, `email.view_inbox`
- `integrations.view`, `integrations.connect`, `integrations.disconnect`
- `settings.studio`, `settings.billing`, `settings.branding`, `settings.staff_roles`
- `settings.integrations`, `settings.zoom`, `settings.security`

**Staff management**
- `staff.view`, `staff.invite`, `staff.deactivate`, `staff.set_permissions`, `staff.set_role`

**Facilities**
- `facilities.view`, `facilities.edit`

**Import / Data**
- `import.run`, `data.export_full`, `data.bulk_modify`

Estimated total: ~75–80 keys. Finalized in step 1.

## Role-default templates (only used at staff-create time)

These are not enforced — they're **starter packs**. Owner can tick/untick freely after applying one.

| Template | Includes |
|---|---|
| **Owner** | (implicit — everything, no need to grant explicitly) |
| **Manager** | Everything except `payroll.set_rates`, `payroll.run_payout`, `settings.billing`, `staff.set_role`, `settings.security` |
| **Instructor** | view-all on schedule/private_sessions/workshops/members; create + edit + cancel + complete on private_sessions; clock_self + view_self on time_clock + payroll; edit own workshops + upload flyer; view but not refund payments |
| **Front Desk** | members.view/edit/add_note; schedule.check_in_members/book_member; pos.use; payments.view + send_payment_link; gift_cards.create; time_clock.clock_self |
| **Custom** | Empty set — owner ticks every box manually |

Owner picks a template at staff-create time, then edits. Templates are also exposed as "Apply template" buttons on the per-staff settings page to bulk-(re)set if the owner ever wants to reset and start over.

## Implementation phases

### Phase 1 — Lock down the permission key list (½ day, planning only)

- Walk every gated endpoint in `apps/api/app/api/v1/endpoints/*.py` and list the action it performs.
- Group into the categories above; finalize the exact key names.
- Drop / merge any keys that don't map to a real endpoint.
- Output: a frozen `PERMISSION_KEYS = [...]` constant + a `DEFAULT_TEMPLATES = {...}` dict in `app/services/permissions.py`.

### Phase 2 — Backend dependency swap (1 day)

- Add `require_permission(*keys: str)` dependency in `app/api/v1/dependencies/rbac.py`. Owner bypasses; everyone else is checked via `PermissionService.has_permission()` (Redis-cached).
- Replace every `require_role(...)` call site with the corresponding `require_permission(...)`. Approximately 200 endpoints.
- Endpoints with no obvious permission counterpart (auth, webhooks, public flows) keep their current open / role-less gating — they're not staff-facing.
- Keep `require_role` defined for the very few hooks that genuinely need "is this user an instructor at all" (e.g., the instructor portal pages), but stop using it as the gate for action-level decisions.

### Phase 3 — UI rewrite of the staff detail page (½ day)

- Rewrite `apps/web/src/components/staff/permission-matrix.tsx` to list every key grouped by area, with description text under each.
- Add a "Apply template" dropdown (Manager / Instructor / Front Desk / Custom) that bulk-sets the toggles. Owner can adjust afterwards.
- Save endpoint already exists (`PermissionService.set_user_permissions`); just need the UI to actually call it and respect the new key list.
- Add a "Permissions" tab to the staff detail page (parallel to current Profile tab).

### Phase 4 — Migration / backfill (15 minutes)

- For every existing staff member, derive their current role's template permissions and INSERT into `af_global.user_permissions`.
- Don audits the resulting permission set per staff member (especially Brittany — give her `workshops.edit/publish/upload_flyer` on top of the default instructor template).
- Flush Redis perms cache.

### Phase 5 — Cleanup (¼ day)

- Remove the role-hierarchy assumption from sidebar / nav visibility — gate each sidebar item on the matching permission key instead.
- Remove unused defaults from `DEFAULT_ROLE_PERMISSIONS` in `permissions.py` (replaced by `DEFAULT_TEMPLATES`).
- Document the new permission system in `docs/ADMIN-GUIDE.md`.

### Phase 6 — Verification (½ day)

- Behavioral test: create a synthetic staff member with `workshops.edit` and `workshops.upload_flyer` only — verify they can update + add a flyer to a workshop AND cannot touch payroll or settings.
- Repeat for a "front desk" staff member.
- Repeat for the "Brittany pattern" — instructor + workshops.edit/publish/upload_flyer ticked individually.
- Run the existing E2E test suite to confirm nothing regressed.

**Total estimated effort:** ~3 working days.

## Acceptance criteria

When this lands you can:
1. Open Brittany's staff page and tick exactly `workshops.edit`, `workshops.publish`, `workshops.upload_flyer`. She gains access to those specific actions. Nothing else changes.
2. Open another instructor's page and grant only `private_sessions.set_pricing` without unlocking workshops, payroll, or settings.
3. Hand a new staff member the "Front Desk" template, then untick `pos.use` because you don't want them touching retail, leaving the rest of the template intact.
4. Confirm that no staff member except owner can run payouts unless `payroll.run_payout` is explicitly granted to them.

## Risks / gotchas

- **Permission cache.** Permissions are Redis-cached for 5 minutes. After granting a new permission, the owner sees the change immediately (because the set endpoint flushes); the affected staff member sees it on their next request after the cache TTL — or immediately if we explicitly invalidate `perms:{org}:{user}` on grant (already done in `set_user_permissions`).
- **Sidebar drift.** Some sidebar links currently render based on hard-coded role checks rather than reading `user_permissions`. Phase 5 needs to fix that or the UI will show links the user can't actually use.
- **Webhook + public endpoints.** Don't gate webhooks (Stripe, Twilio, etc.) with permission checks — they're signed by external services, not authenticated by user. Leave their current verification intact.
- **Instructor portal vs staff dashboard overlap.** Some endpoints serve both contexts (e.g. an instructor seeing "my private sessions" vs. an admin seeing all). Keep an "own vs all" distinction in the keys: `private_sessions.view_own` vs `private_sessions.view_all`.
- **Owner bypass.** Owner has implicit access to everything; this is the only special role kept. Platform admin (Don across all tenants) also bypasses.

## Out of scope (for this overhaul)

- New roles or new staff types — this is purely about permission control, not new templates.
- Multi-org permission inheritance — a user with permissions in one org keeps those scoped to that org only.
- Time-bound permissions ("Brittany can edit workshops until Friday") — not in scope; can be a later extension.
- Approval workflows ("admin must approve this refund") — separate feature.

## When ready to execute

Don triggers this weekend. On trigger:
1. Branch from `release/*` with `feat/permission-overhaul`.
2. Work through phases 1–6 in order.
3. Deploy off-hours (per the no-business-hours-rebuild rule).
4. Owner audits each staff member's permission grid after backfill.

---

## Execution status — checkpoint 2026-05-21

**Done so far (committed, NOT deployed yet):**
- **Phase 1A** ✅ `app/services/permissions.py` now exports 95+ action-level
  keys plus `DEFAULT_ROLE_PERMISSIONS` templates for owner / manager /
  admin (alias) / instructor / front_desk / member. Added
  `apply_template()` for the "reset to template" UI button.
- **`app/api/v1/dependencies/rbac.py`** — `require_permission(*keys)` now
  accepts multiple keys (OR semantics, useful for endpoints serving both
  staff and members) AND returns the same rbac dict shape as
  `require_role` so endpoint signatures don't need any other changes
  when swapping.
- **Phase 2A** ✅ `app/api/v1/endpoints/courses.py` — all 14 require_role
  sites swapped to require_permission with the matching `workshops.*`
  key. Brittany's path: `workshops.edit` (covers flyer uploads via the
  same PUT endpoint), `workshops.publish`, `workshops.manage_sessions`,
  etc.
- **`app/api/v1/endpoints/staff.py`** — old `module.staff` gate replaced
  with `staff.view` / `staff.edit_profile` / `staff.set_role` /
  `staff.set_permissions`. Owner-only enforcement now comes from
  granting those keys (only the manager + owner templates include
  `staff.set_role` and `staff.set_permissions`; templates can also be
  customized per-user).
- **Phase 3** ✅ `apps/web/src/components/staff/permission-matrix.tsx`
  rewritten to render dynamically from the API's `all_permissions` list.
  Keys auto-group by `<area>.<verb>` prefix with sensible labels.
  Member-portal "own actions" keys are hidden from the matrix (members
  get those automatically). No more hardcoded module.X list in the
  frontend — when the backend's ALL_PERMISSIONS catalog grows the
  matrix picks up the new toggles for free.
- **Phase 4** ✅ `apps/api/scripts/backfill_permissions_from_role_templates.py`
  one-shot migration: wipes existing `af_global.user_permissions` rows
  (clears old `module.*` grants) and re-seeds each staff member from
  their role template. Dry-run by default; `--apply` to write. Owner
  skipped (implicit bypass).

**Remaining work (NOT done — pickup list for next session):**
- **Phase 2B / 2C / 2D**: ~570 more require_role sites across ~63 endpoint
  files need swapping to require_permission. The pattern is fully
  mechanical now — agent enumeration in
  `/tmp/.../a6bae3e687197655a.output` (or re-run the enumeration) gives
  file:line → suggested key. Workshops + staff are the only ones done
  in this checkpoint. Mixed state in the codebase is fine: any endpoint
  still using `require_role` keeps working as it does today.
- **Phase 5**: sidebar / nav visibility — `apps/web/src/components/dashboard/sidebar.tsx`
  currently hides items by role. After full overhaul, hide by
  permission key instead (e.g. show "Workshops" link if user has
  `workshops.view_enrollments` OR any other workshops.* key).
- **Phase 6**: behavioral test + deploy. Migration script MUST run AS
  PART OF the deploy so no staff member loses access. Order:
  `docker compose build api celery_worker celery_beat web` →
  `docker compose up -d --force-recreate ...` →
  `docker exec auraflow_api python /app/scripts/backfill_permissions_from_role_templates.py --apply`
  → spot-check Brittany can edit a workshop, manager can do most things,
  front desk can run kiosk, etc.

**State of the world if deployed today:**
- Owner: works everywhere (implicit bypass — no migration needed)
- Anyone else accessing `/courses/*` or `/staff/*`: will 403 unless the
  backfill script has run (since the new keys aren't in their
  user_permissions rows yet).
- All OTHER endpoints (still using require_role): work exactly as today.
- The staff page renders fine — PermissionMatrix reads `all_permissions`
  from the API and shows the full action-level toggle grid. Owner can
  customize per-user.

So: do not deploy until either (a) the rest of the endpoints are
swapped AND backfill runs, or (b) Brittany's workshops use case is the
ONLY thing being shipped, in which case backfill needs to run and
Brittany's instructor template includes `workshops.edit` +
`workshops.publish` (it does — see permissions.py `_INSTRUCTOR_TEMPLATE`).
