# HIPAA 2C Phase C — PHI Plaintext Read-Path Audit

**Status (2026-04-22): all 12 hits migrated.** Tier A, B, and C are
done. Plaintext columns can drop after the next bake window — see
"Drop sequence" at the bottom.

Original research-only inventory (2026-04-24) of every code path that
read PHI columns (`phone`, `date_of_birth`, `address_line1`, `city`,
`state`, `postal_code`, `emergency_contact_*`, `notes`) directly from
`members` instead of routing through `MemberService.get_member`, which
is the only path that dual-reads the `*_enc` shadow columns.

Each of these is a **Phase C blocker**: when plaintext columns drop,
these queries will all return NULL for those fields. They need to
either (a) switch to reading `*_enc` + decrypting, or (b) call
through the service layer.

## Migration outcome (12 / 12 hits resolved)

Every site now SELECTs both `m.phone` and `m.phone_enc` and routes the
value through `decrypt_phone()` (workers, AI, inbox, sub-finder) or
`_row_with_decrypted_phi()` (member service list/get). When plaintext
drops, the helpers fall through to the encrypted column transparently.

### Tier A — done

| File:line (post-migration) | Resolution |
|---|---|
| `member_service.py` list_members | `m.phone ILIKE` clause removed. Search by name/email only. `list_members` rows pass through `_row_with_decrypted_phi` so callers see decrypted phone. |
| `booking_service.py:42` `_get_notification_data` | Adds `m.phone_enc` to SELECT, decrypts before SMS send. |
| `booking_service.py:494` `get_session_roster` | Adds `m.phone_enc`, decrypts each row before returning. |
| `reminders.py` | Adds `m.phone_enc`, decrypts via helper before SMS dispatch. (Also migrated to `claim_row_once` to fix duplicate-send race.) |
| `birthday_emails.py` | Now filters on derived `birthday_month` + `birthday_day` SMALLINT cols. Full DOB stays encrypted in `date_of_birth_enc`. (Migration `a26_birthday_derived` adds + backfills.) |
| `payment_escalation.py` | Day-3 + Day-7 SMS sites use `decrypt_phone(row)`. |
| `membership_expiration.py` | 1-day urgent SMS uses `decrypt_phone(row)`. |

### Tier B — done

| File:line (post-migration) | Resolution |
|---|---|
| `chatbot_service.py` `_tool_get_member_details` | Decrypts via helper. The other tool, `_tool_lookup_member`, calls `MemberService.search_members` which is already PHI-safe. |
| `voice_call_service.py` waitlist escalation | Decrypts before voice-call init and before SMS fallback. |
| `sub_finder_service.py` `_notify_members_of_sub` | Decrypts each booked member before SMS. |
| `studio_inbox_service.py` `_get_member_context` | AI inbox context decrypts member phone before passing to LLM. |

### Tier C — resolved by drop

`m.phone ILIKE` clause removed from `list_members`. A blind-index
column was considered but rejected: even an HMAC of the phone is a PHI
derivative under §164.514, and front-desk staff can search by name or
email which are already trigram-fuzzy. Kept the search comment in the
service explaining the intentional drop so future changes don't
silently re-add a plaintext-or-blind-index search criterion.

## Search for other PHI sources

- `member_notes.note` — Phase B already dual-writes; direct reads of the
  plaintext `note` column outside `MemberService.list_notes` would also
  break. Audit pending for list_notes callers.
- `af_global.users.phone` — Phase A added `phone_enc` shadow. Current
  status: no live callers of plaintext `users.phone` found in code.

## Drop sequence (still pending)

Migrations are merged but plaintext columns are **not yet dropped**.
Do these in order, after a clean bake (recommend ≥7 days of canary +
PHI scanner green):

1. Deploy api + celery_worker + celery_beat with Phase C migrations.
   Apply Alembic `a26_birthday_derived` to add + backfill the derived
   month/day columns. (After-hours: Pacific evening only.)
2. Bake. Watch synthetic canary, PHI consistency scanner, and Sentry
   for any plaintext-fallback hits.
3. Drop plaintext PHI columns in one Alembic migration wrapped in
   `BEGIN`/`COMMIT`. Keep a `pg_dump` of `members` first.
4. Remove the `_row_with_decrypted_phi` fallback-to-plaintext branch
   from `MemberService` and the `decrypt_phone` plaintext fallback
   from `phi_helpers.py` — there's no plaintext to fall back to.
