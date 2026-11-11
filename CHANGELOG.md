# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project scaffold: package layout, tooling configuration and a version test.
- Community files, CI (ruff, mypy, pytest, build on Python 3.11 and 3.14) and CodeQL.
- FastAPI app: `POST /api/endpoints` creates an endpoint with an unguessable token, `/h/{token}` accepts any HTTP method and stores method, path, query, headers, body, timestamp and source IP in SQLite.
- `GET /api/endpoints/{token}/requests` with method, date range and body text filters, and `GET /api/endpoints/{token}/requests/{id}`.
- Body size limit enforced while streaming (413) and a cap on stored header bytes.
- Environment configuration validated at startup, documented in `.env.example`.
- Signature verification helpers for GitHub, Stripe-style and generic HMAC, with constant-time comparison.
