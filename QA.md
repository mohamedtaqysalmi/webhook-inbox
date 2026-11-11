# QA checklist — webhook-inbox

## Scope for v0.1.0

Self-hosted FastAPI + SQLite inbox: create endpoints, store requests, list/filter,
HMAC signature helpers, replay with SSRF checks, retention, rate/body limits,
HTMX UI, Docker Compose, GitHub Pages signature calculator.

## Functional

- [x] `POST /api/endpoints` returns token + URL
- [x] `/h/{token}` stores method, path, query, headers, body, timestamp, source IP
- [x] List/filter API (`method`, `since`, `until`, `q`, paging)
- [x] Body over limit → 413 while streaming
- [x] Header byte cap + `headers_truncated`
- [x] Replay API + UI form; private targets blocked by default
- [x] Retention deletes old requests
- [x] Rate limit on create/receive
- [x] HTMX UI create → inbox → detail → replay
- [x] `docker compose up --build` documented

## Security

- [x] SSRF rules documented in `SECURITY.md`
- [x] Signature helpers use constant-time compare
- [x] No secrets in repo; `.env.example` only
- [x] CodeQL workflow present

## Quality

- [x] pytest with coverage gate ≥ 85%
- [x] ruff + mypy strict in CI
- [x] ADR for HTMX vs React
- [x] Pages site with client-side signature calculator
- [x] Changelog + release notes path

## Manual checks before sharing

- [ ] Open Pages URL in a private window on phone and desktop
- [ ] Run Compose locally and POST a sample webhook
- [ ] Confirm Lighthouse scores (target 90+) on the Pages URL after deploy
- [ ] Confirm GitHub Pages source is `/docs` on `main`

## Why this exists

I need a Hookdeck-like catcher I can run next to local services without paying for
a tunnel SaaS or losing request history when a tunnel dies.

## What I would do differently next

Pin resolved IPs during replay, add an auth gate on endpoint creation, and ship a
short screen recording on the Pages site instead of the static three-step diagram.
