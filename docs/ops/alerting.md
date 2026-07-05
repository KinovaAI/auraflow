# Alerting

Sentry captures every unhandled error in API / Celery / Next.js. Out of the
box it emails. This page documents how to wire it to Slack + PagerDuty so
real incidents page on-call within 60 seconds.

## Channels

| Severity | Channel | Who sees it |
|---|---|---|
| `fatal` | PagerDuty → SMS + phone call | on-call engineer |
| `error` (payment-flow, auth-flow) | Slack #on-call + PagerDuty low-urgency | on-call + team |
| `error` (everything else) | Slack #sentry-errors | team |
| `warning` | Slack #sentry-warnings | team (daily digest) |

## Slack setup (one-time)

1. In Slack, install the **Sentry** app (or use an Incoming Webhook and
   point Sentry's Slack integration at it).
2. Create channels: `#sentry-errors`, `#sentry-warnings`, `#on-call`.
3. In Sentry → *Settings → Integrations → Slack*, connect the workspace.
4. Invite `@Sentry` to each channel.

## Sentry alert rules (create via Sentry UI)

### 1. `fatal`-level event → PagerDuty
- **When:** an event's level is `fatal`
- **Then:** send notification via PagerDuty (service: `auraflow-prod`)
- **Environment:** production

### 2. 5xx rate >1% over 5 min → Slack on-call
- **When:** issue frequency >1% of total requests, sustained 5 min
- **Then:** send Slack message to `#on-call`, mention `@on-call`
- **Environment:** production

### 3. Payment flow error >0 over 1 min → Slack + PagerDuty low-urgency
- **When:** an event occurs with any of these transactions:
  `/api/v1/external/transactions`, `/api/v1/retail/transactions`,
  `/webhooks/stripe`, `/api/v1/payments/*`
- **Then:** Slack `#on-call` with `@here`, PagerDuty low-urgency notify
- **Environment:** production

### 4. Celery failure rate >5% over 15 min → Slack
- **When:** `app.workers.tasks.*` transactions show >5% failure rate
- **Then:** Slack `#on-call`
- **Environment:** production

### 5. Auth failure spike → Slack (potential brute force)
- **When:** event count for `auth.login_failed` action >20 over 5 min
- **Then:** Slack `#on-call`
- **Environment:** production

## PagerDuty setup (one-time)

1. Create services in PagerDuty:
   - `auraflow-prod` (high-urgency, 24/7 rotation)
   - `auraflow-prod-low` (low-urgency, business hours)
2. In Sentry → *Settings → Integrations → PagerDuty*, connect each service.
3. Copy the PagerDuty integration keys into Sentry alert rules above.

## Runbook links

Every alert body should include a link to the relevant runbook:

- Payment failures → `docs/ops/runbook-payments.md`
- Auth issues → `docs/ops/runbook-auth.md`
- Webhook backlog → `docs/ops/runbook-webhooks.md`
- Backup failures → `docs/ops/runbook-backups.md`
- Celery backlog → `docs/ops/runbook-celery.md`

(These runbooks are placeholders as of 2026-04-23 and will be written as
incidents surface them.)

## Test your alerting

```bash
# Fire a test fatal event from the prod api container
sudo docker exec auraflow_api python -c "
import sentry_sdk
sentry_sdk.init('${SENTRY_DSN_API}')
sentry_sdk.capture_message('Test fatal alert — please ignore', level='fatal')
"
```

You should see a PagerDuty page within 60 seconds. If not, check Sentry's
**Alerts → Activity** tab for delivery failures.
