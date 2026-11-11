# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-11

### Added

- Replay API and HTMX replay form with result logging.
- SSRF protection for replay targets (private/loopback/link-local blocked by default).
- Retention purge and per-IP rate limiting on create/receive.
- HTMX inbox UI (`/`, `/ui/{token}`) with filters and detail partials.
- Docker image and `docker-compose.yml`.
- GitHub Pages site with client-side signature calculator.
- ADR explaining HTMX over React; QA and test report docs.

### Already in 0.1.0 from earlier work

- Endpoint create/receive/list with body and header limits.
- Signature verification helpers for GitHub, Stripe-style and generic HMAC.
- CI (ruff, mypy, pytest, build) and CodeQL.

## [Unreleased]

### Added

- Project scaffold: package layout, tooling configuration and a version test.
- Community files, CI and CodeQL.
