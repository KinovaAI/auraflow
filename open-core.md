# AuraFlow — Open-Core Model

**Status:** Model decided (open-core, AGPLv3 + commercial/cloud). Connector split
and billing-broker details being finalized.

AuraFlow is **open core**. The fundamentals are free and self-hostable under
AGPLv3. Revenue comes from **managed cloud + managed billing + managed AI**, plus a
thin layer of additive enterprise features — never from crippling the free product.

Philosophy (explicit, and load-bearing):

- **The free version is a complete product you can run a real business on.** No
  artificial limits designed to force an upgrade. Trust is the moat.
- **No rug-pulls.** Anything released as open stays open. New commercial features
  are *additive*, not clawed back from the open core.

---

## What's open (AGPLv3, free, self-hostable — single tenant)

The whole engine and a business-ready app:

- Dynamic-DB engine + schema/tenant provisioning
- Tenant isolation (self-host runs a **single tenant** — one studio/org)
- AI + voice core — **bring-your-own API key**
- Base UI + component system
- Connector framework + build-your-own connectors
- Standard / consumer / SMB connectors
- Basic OIDC SSO
- Hash-chained audit log
- **Payments: bring-your-own provider.** The self-hosted app connects the
  operator's *own* Square or Stripe account directly (their keys, their account,
  their money, no platform fee). This is exactly how the reference deployment
  (a single studio) runs its own Square account today.

## What's paid (commercial license + managed services)

Primary revenue is **operated services**, not feature gates:

- **AuraFlow Cloud** — hosted, operated, backed up, SLA.
- **Managed AI** — frontier models without bringing your own keys.
- **AuraFlow Billing (the platform-fee broker)** — turnkey Square billing with the
  1% platform fee. See "Billing & the platform fee" below — this is the *only*
  correct home for the platform fee.
- Enterprise identity — SAML / SCIM / multi-org.
- Advanced RBAC / governance / compliance tooling.
- Premium enterprise connectors — Salesforce / SAP / NetSuite / systems of record.
- Marketplace, dual-license / white-label.

## The three hard lines (decided)

1. **Free self-host = single tenant.** Hosting *other* orgs (multi-tenant) needs a
   commercial license. (AGPLv3's network-use clause + the commercial license make
   this enforceable — a competitor can't take the code, run a multi-tenant SaaS,
   and neither open their changes nor pay.)
2. **Free-tier AI = bring-your-own-key only.** Hosted/managed AI is paid. No hosted
   AI bundled into the free tier.
3. **Connectors:** standard / consumer / SMB = free; enterprise systems of record =
   premium; the connector framework + build-your-own = always free.

---

## Billing & the platform fee (AuraFlow-specific — the important part)

**Goal:** collect a 1% Square platform fee on charges that flow through AuraFlow,
while keeping the platform's Square credentials secure.

**Why the fee CANNOT be "baked into" the open self-host tier:**

1. **Secret exposure.** The platform's Square OAuth client secret / platform token
   cannot live in an AGPL codebase — everyone who self-hosts gets the source, and
   the repo is public. A shared baked-in secret is a shared-with-the-world secret.
2. **Unenforceable in open source.** Even without the secret at runtime, a
   self-hoster can delete the `app_fee_money` line, or connect their *own* Square
   application instead of the platform's, and pay nothing. You cannot force a fee on
   code someone runs on their own box with their own Square account.

**The design that works — the fee lives in a service the platform operates:**

- **Free self-host:** operator uses their own Square/Stripe directly. No fee to the
  platform, no platform secrets in the box.
- **AuraFlow Billing (paid/managed):** a small **hosted broker** the platform runs.
  - It holds the platform's Square OAuth app credentials **encrypted, on platform
    infra only** (same posture as the existing sops+age / pgcrypto-in-DB secrets —
    never shipped in an image or repo).
  - Merchants connect via OAuth *through the broker*; the broker does the
    code→token exchange (the only step needing the platform secret).
  - Payments route through the broker (or are created with the broker enforcing
    `app_fee_money` server-side), so the **1% is applied on platform-controlled
    infrastructure and can't be edited out**.
  - Self-hosters who want turnkey "connect Square in one click, we handle billing"
    opt into this managed component and accept the fee as a term of service.

Net: the 1% fee is a **managed-service monetization hook**, not a property of the
free code — the only way it is simultaneously secure and non-bypassable.

**Secret handling (all tiers):** no live credentials (Square platform secret, AI
keys, encryption keys, JWT/app secrets) are ever committed to the open repo or
baked into distributed images. The open repo ships `.env.example` templates only.

---

## Licensing & contributions

- **License:** GNU AGPLv3 (`LICENSE`).
- **Contributions:** governed by a CLA (`CLA.md`) so the dual/commercial license
  and managed offerings remain possible — standard for open-core.
- **Commercial license:** available for anyone who needs to escape AGPL terms
  (multi-tenant hosting, closed-source embedding, white-label).
