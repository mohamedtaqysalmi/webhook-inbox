# webhook-inbox

A self-hosted inbox to receive, store, inspect and replay webhooks. The plan is FastAPI and SQLite with a small server-rendered HTMX UI, HMAC signature verification helpers, and SSRF protection on replay targets.

**Status: early development.** Receiving, storing and listing webhooks works through a JSON API, and the signature helpers exist as a library. There is no UI, replay or Docker image yet.

## What works

- `POST /api/endpoints` creates an endpoint and returns a random URL token (from `secrets`).
- `/h/{token}` (and any sub-path) accepts any HTTP method. The method, path, query string, headers, body, timestamp and source IP are stored in SQLite.
- `GET /api/endpoints/{token}/requests` lists stored requests, newest first, with filters `method`, `since`, `until`, `q` (case-insensitive text search in the body), `limit` and `offset`. `GET /api/endpoints/{token}/requests/{id}` returns one request with headers and body.
- Request bodies over `WEBHOOK_INBOX_MAX_BODY_BYTES` get a 413, checked while the body is being read. Stored headers are capped at `WEBHOOK_INBOX_MAX_HEADER_BYTES`; anything beyond that is dropped and the request is flagged `headers_truncated`.
- `webhook_inbox.signatures` has `verify_github`, `verify_stripe` (timestamp tolerance, injectable clock) and `verify_hmac`. They use constant-time comparison and raise `SignatureError` with a reason (`missing`, `malformed`, `mismatch`, `expired`). The app does not call them yet.

## What is not built

Replay and SSRF protection for replay targets, retention, rate limiting, the HTMX UI, and Docker files. Also note: anyone who can reach the server can create endpoints, and the token in the URL is the only access control for reading an endpoint's requests. Do not expose it to the internet as it is. The source IP is the direct peer address; `X-Forwarded-For` is not trusted or parsed.

## Running it

```bash
pip install -e .
uvicorn --factory webhook_inbox.app:create_app
```

Then:

```bash
curl -X POST localhost:8000/api/endpoints
curl -X POST localhost:8000/h/<token> -d '{"hello":"world"}'
curl localhost:8000/api/endpoints/<token>/requests
```

Configuration comes from environment variables, validated at startup (see `.env.example`). The app does not read the `.env` file itself.

## Development setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
. .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pre-commit install
```

## Running tests and checks

```bash
pytest
ruff check .
ruff format --check .
mypy
```

Coverage must stay at or above 85%; `pytest` fails otherwise.

## License

MIT, see [LICENSE](LICENSE).
