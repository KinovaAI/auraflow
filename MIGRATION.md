# Moving AuraFlow to a fresh public (AGPLv3) repo — securely

**Will "fresh repo, no history" work?** Yes — a brand-new repo with a single
initial commit severs all old history, so nothing in past commits can leak. **But
history is only one leak vector.** Copying the *current* working tree can still ship
secrets and customer data. And the public repo should be the open-core *subset*,
not a 1:1 copy of the private repo. Do the following.

## 0. It's a subset, not a copy
Per `open-core.md`, the public repo excludes commercial-tier code: the managed
billing broker + platform Square credentials handling, SAML/SCIM, premium
enterprise connectors, and managed-AI proxying. Decide the boundary first; those
stay in the private/commercial repo.

## 1. Start from a clean checkout (no `.git`)
```bash
# copy the working tree only — NOT the old .git history
rsync -a --exclude '.git' /home/don/repos/auraflow-phase2/ /home/don/repos/auraflow-open/src/
```

## 2. Purge secrets and credentials from the working tree
Remove everything that isn't meant to be public. At minimum:
- `.env`, `.env.*`, `*.env`, and **all** `.env.production*` / `*.bak*` backups
- any `secrets/`, keyfiles, `*.pem`, `*.key`, service-account JSON, sops/age keys
- Square platform credentials, AI API keys, JWT/app secrets, encryption keys
- CI secrets, deploy keys, `docker-compose` files that embed real values
Replace with **`.env.example`** templates (keys present, values blank/placeholder).

## 3. Scan the tree for hardcoded secrets (do NOT skip)
Secrets hide in source, migrations, seed data, tests, and comments — not just env
files. Run a scanner and fix every hit before the first commit:
```bash
# gitleaks (filesystem mode) and/or trufflehog
gitleaks detect --no-git --source /home/don/repos/auraflow-open/src -v
trufflehog filesystem /home/don/repos/auraflow-open/src
```
Grep sweep as a backstop (Square/Stripe/OpenAI/Anthropic key shapes, tokens):
```bash
grep -rInE 'sk-[A-Za-z0-9]|EAAA|sq0(atp|csp)|pi_[A-Za-z0-9]|-----BEGIN|password|secret|api[_-]?key' src \
  | grep -vE '\.example|placeholder|YOUR_|<.*>'
```

## 4. Remove customer / tenant data (HIPAA-relevant)
No real member/patient PII/PHI, no production DB dumps, no seed data derived from
real orgs (e.g. your production tenant data). Replace with synthetic fixtures. This is
non-negotiable given the health-adjacent data AuraFlow handles.

## 5. Add the open-core governance files
Drop in `LICENSE` (AGPLv3), `open-core.md`, `CLA.md`, `CONTRIBUTING.md`,
`SECURITY.md`, plus AGPLv3 source headers on source files. **Do not** put the AGPL
`LICENSE` into the private repo — it belongs only in the public one.

## 6. Initialize the fresh repo (single clean commit)
```bash
cd /home/don/repos/auraflow-open/src
git init
git add -A
git commit -m "Initial public release — AuraFlow open core (AGPLv3)"
# create the NEW github repo (e.g. KinovaAI/auraflow), then:
git remote add origin git@github.com:KinovaAI/auraflow.git
git push -u origin main
```

## 7. Wire CI guardrails before/at publish
- Secret-scan (gitleaks) on every PR and push — block on hit.
- CLA bot (require CLA acceptance on PRs).
- Never re-introduce `.env*`/secrets: add them to `.gitignore` on day one.

## 8. Belt-and-suspenders
- Assume anything ever pushed to the *private* repo could still exist elsewhere;
  **rotate** any credential that was ever committed there, regardless.
- Keep the private repo private; the public repo is a curated export, kept in sync
  by deliberate, reviewed pushes — not a mirror.

---
**Bottom line:** the fresh-repo-no-history plan is correct and eliminates the
history-leak risk. Add the working-tree scrub (steps 2–4) + a secret-scanning CI
gate (steps 3, 7) and it's genuinely secure — and rotate anything the old private
repo ever held (step 8).
