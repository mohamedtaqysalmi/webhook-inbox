# webhook-inbox

A self-hosted inbox to receive, store, inspect and replay webhooks. FastAPI and SQLite, small HTMX UI, HMAC signature helpers, SSRF-checked replay, retention and rate/body limits.

**Site:** [mohamedtaqysalmi.github.io/webhook-inbox](https://mohamedtaqysalmi.github.io/webhook-inbox/)

## What works

- `POST /api/endpoints` creates an endpoint and returns a random URL token.
- `/h/{token}` (and sub-paths) accepts any HTTP method and stores method, path, query, headers, body, timestamp and source IP in SQLite.
- `GET /api/endpoints/{token}/requests` lists requests with `method`, `since`, `until`, `q`, `limit`, `offset`. Detail route returns headers and body.
- `POST /api/endpoints/{token}/requests/{id}/replay` with `{"url":"..."}` replays the stored request after SSRF checks; results are logged.
- Body over `WEBHOOK_INBOX_MAX_BODY_BYTES` → 413 while streaming. Headers capped by `WEBHOOK_INBOX_MAX_HEADER_BYTES`.
- Per-IP rate limit on create/receive. Retention deletes rows older than `WEBHOOK_INBOX_RETENTION_DAYS`.
- HTMX UI at `/` and `/ui/{token}` for create, inspect and replay.
- `webhook_inbox.signatures`: `verify_github`, `verify_stripe`, `verify_hmac` (library helpers).
- Docker image + `docker compose up --build`.

## Why HTMX (not React)

The inbox is server-owned state (SQLite + filters + replay). HTMX partials avoid a separate Node build for a table/detail/form UI. Full write-up: [docs/adr/0001-htmx-ui.md](docs/adr/0001-htmx-ui.md).

## Running it

```bash
pip install -e .
uvicorn --factory webhook_inbox.app:create_app
```

Or:

```bash
docker compose up --build
```

Then open `http://localhost:8000` or:

```bash
curl -X POST localhost:8000/api/endpoints
curl -X POST localhost:8000/h/<token> -d '{"hello":"world"}'
curl localhost:8000/api/endpoints/<token>/requests
# Replay a stored request to an external URL:
curl -X POST localhost:8000/api/endpoints/<token>/requests/<request_id>/replay \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/webhook"}'
```

Configuration is environment variables validated at startup (see `.env.example`).

## Security notes

Replay targets are validated (public IPs only by default). Endpoint tokens are secrets. Details: [SECURITY.md](SECURITY.md).

## Development

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1   # or: source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pytest
ruff check .
ruff format --check .
mypy
```

Coverage must stay at or above 85%.

## License

MIT, see [LICENSE](LICENSE).
