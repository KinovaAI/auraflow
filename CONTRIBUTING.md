# Contributing to AuraFlow

AuraFlow is open-core (AGPLv3, see `LICENSE`) with a commercial/managed edition.

## Before you start
- By contributing you agree to the **CLA** (`CLA.md`) — required so the project can
  keep offering both AGPLv3 and a commercial license.
- Read `open-core.md` to understand what belongs in the open core vs. the
  commercial edition. **Do not** put commercial-tier functionality (the managed
  billing broker, SAML/SCIM, premium enterprise connectors, managed-AI proxying)
  into this repo.

## Ground rules
- **Never commit secrets.** No live API keys, tokens, Square platform credentials,
  encryption keys, JWT/app secrets, `.env`/`.env.production`, or credential backups.
  Only `.env.example` templates belong here. A secret-scan runs in CI and will
  block the PR.
- **Never commit customer/tenant data** — no real member/patient PII/PHI, no
  production database dumps, no seed data derived from real orgs. Use synthetic
  fixtures only.
- Keep tenant isolation intact; the open build is single-tenant by design.
- Match existing patterns; include tests with behavior changes.

## Workflow
1. Fork, branch from the default branch.
2. Make focused changes with tests.
3. Open a PR; the CLA bot + secret-scan + tests must pass.
4. A maintainer reviews for correctness, security, and open-core boundary fit.

## Security issues
Do not open a public issue for vulnerabilities — see `SECURITY.md`.
