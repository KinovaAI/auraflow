# AuraFlow Managed Billing Broker — design

**Goal:** let open, self-hosted AuraFlow instances (single tenant) charge their
members via Square while routing a **1% platform fee** to KinovaAI — without ever
exposing the platform's Square credentials and without the fee being bypassable.

**Where it lives:** the existing commercial platform, `auraflow-phase2` on the
`auraflow` VPS (`api.auraflow.fit`). It reuses what's already there (Square OAuth,
`billing_dispatcher`, `app_fee` payments, encrypted per-account tokens). The broker
is a new **external-facing API surface** on that platform. It never ships in the
open repo.

---

## Two billing modes (open core)

The open self-host picks one via config:

- **`self` (free, default):** the operator connects their *own* Square or Stripe
  account directly (their keys, their money, **no fee**). Exactly how the reference
  studio runs today. Nothing calls the broker.
- **`managed` (opt-in, 1% fee):** the operator connects their Square account
  *through the broker*; charges are proxied to the broker, which applies the 1%.

Config in the open build:
```
AURAFLOW_BILLING_MODE = self | managed
# managed mode only:
AURAFLOW_BROKER_URL     = https://api.auraflow.fit
AURAFLOW_BROKER_API_KEY = <issued per self-host client>
```

## Why "proxied" and not "mint a token to the self-host"

A thinner design (broker mints the merchant's Square token to the self-host, which
then charges directly) does **not** work:

- The self-host would hold a token scoped to the platform's Square app and could
  simply create payments with `app_fee_money = 0` (open source — they edit the
  line). Fee unenforceable.
- The platform would be on the hook to Square for a merchant it can't control.

So in `managed` mode the merchant token stays on the VPS and **the broker creates
every payment**, computing the 1% `app_fee_money` server-side. The self-host cannot
remove it.

---

## Broker components (on `auraflow-phase2`)

### 1. Billing-client records (new)
`af_global.billing_clients` — decoupled from tenant schemas (these clients run
their own AuraFlow elsewhere; they only use our billing):
```
id, name, contact_email,
square_merchant_id, square_access_token_encrypted, square_refresh_token_encrypted,
square_token_expires_at, square_location_id,
api_key_hash, status ('pending'|'active'|'suspended'), created_at
```
- Tokens encrypted with the existing pgcrypto/`APP_SECRET` path — **only on the VPS**.
- `api_key_hash` authenticates the self-host; keys are per-client and revocable.

### 2. Square connect (OAuth) — reuses `square_oauth_service`
- Self-host admin → "Connect Square (managed)" → redirect to Square OAuth for the
  platform app → callback hits the broker → broker does the code→token exchange
  (the only step needing the platform app secret) → stores the merchant token on
  `billing_clients`. Self-host never sees the secret or the token.

### 3. Broker payment API (new `/broker/*`, api-key auth)
Mirrors the shapes the open client already understands:
- `POST /broker/customers` — ensure a Square customer for a member → returns `customer_id`
- `POST /broker/cards` — save a card on file (Web Payments nonce) → returns `card_id`
- `POST /broker/charge` — charge `{customer_id, card_id, amount_cents, description}`
  → broker calls `square_service.create_payment_with_app_fee(..., app_fee_cents =
  1% computed HERE)` with the client's merchant token → returns payment result
- `POST /broker/refund`, `GET /broker/payments/{id}` — parity
- Recurring: the self-host owns its own renewal schedule (open code) and calls
  `/broker/charge` on each cycle — so the fee applies every cycle, and the broker
  stays stateless about schedules.

The self-host stores the returned `customer_id` / `card_id` locally and passes them
back; the broker validates they belong to the calling client's merchant.

### 4. Fee + security invariants
- `app_fee` is **always** computed in the broker (never accepted from the client).
- Platform Square app secret + all merchant tokens live only on the VPS, encrypted.
- Per-client API keys, revocable; suspend a client → charges stop.
- Rate-limited; every call audit-logged (reuse the hash-chained audit log).

---

## Open-core client (in the public repo)

A `BrokerBillingProvider` implementing the same interface as the existing
Square/Stripe providers, selected by `AURAFLOW_BILLING_MODE`:
- `ensure_customer` / `save_card` / `charge` / `refund` → thin HTTPS calls to
  `/broker/*` with the broker API key.
- In `self` mode this provider is never constructed; the operator's own
  Square/Stripe path runs unchanged.
- This slots cleanly under the existing `billing_dispatcher` abstraction (the open
  build keeps the dispatcher; it just gains a third provider).

---

## What reuses existing code (little is net-new)
- `square_oauth_service` — OAuth connect + token refresh (already exists).
- `square_service.create_payment_with_app_fee` — the fee-bearing charge (exists).
- `billing_dispatcher` — provider abstraction (exists; add broker provider).
- Encrypted token storage pattern (exists on `af_global.organizations`).
Net-new: `billing_clients` table + `/broker/*` endpoints + API-key auth + the
open-side `BrokerBillingProvider` + a small self-host "connect managed billing" UI.

---

## Phased build

1. **Broker core (commercial/private):** `billing_clients` table, API-key auth,
   `/broker/{customers,cards,charge,refund}` with server-side fee, audit + rate limit.
2. **Connect flow:** managed-Square OAuth connect + token storage/refresh for clients.
3. **Open client:** `BrokerBillingProvider` + `AURAFLOW_BILLING_MODE` config + docs.
4. **Self-host UI:** "Connect managed billing" screen in the open build.
5. **Ops:** client onboarding/keys, suspension, monitoring, reconciliation of fees.

## Open decisions for Don
- **Client onboarding:** self-serve signup for a broker API key, or manual/approved?
- **Fee handling if a charge is disputed/refunded** — refund the 1% too (usually yes).
- **Minimums / who eats Square's own processing fee** (Square's ~2.6% is the
  merchant's regardless; the 1% `app_fee` is on top, to us).
