# Security Policy

## Reporting a vulnerability
Please report security issues **privately** — do not open a public issue or PR.

- Email: **security@kinovaai.tech** (confirm this address before publishing).
- Include: affected version/commit, steps to reproduce, impact, and any PoC.
- We aim to acknowledge within 3 business days and to coordinate a fix + disclosure
  timeline with you.

## Scope notes for self-hosters
- The open, self-hosted build ships **no platform credentials**. You supply your
  own payment provider keys, AI API keys, encryption key, and app/JWT secrets via
  environment (see `.env.example`). Keep them out of version control.
- The 1% platform-fee / managed-billing broker is **not** part of this repo; it
  runs on KinovaAI-operated infrastructure. Nothing in this repository can access,
  modify, or authenticate against the platform's Square account.
- Rotate any secret immediately if it is ever committed or exposed.

## Supported versions
Security fixes target the latest released minor version. Older versions may receive
fixes at maintainers' discretion.
