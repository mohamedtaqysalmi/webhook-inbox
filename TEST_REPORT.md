# Test report — webhook-inbox v0.1.0

## Command

```bash
pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy
pytest
```

## What the suite covers

| Area | File(s) | Notes |
|---|---|---|
| Config validation | `tests/test_config.py` | Defaults, overrides, aggregated errors |
| Storage + filters | `tests/test_storage.py` | Clock injection, paging, LIKE escaping |
| Receive/list API | `tests/test_app.py` | Methods, 413, header cap, restart persistence |
| Signatures | `tests/test_signatures.py` | GitHub vector, Stripe tolerance, generic HMAC |
| SSRF | `tests/test_ssrf.py` | Private IPs, localhost, DNS → private, DNS failure |
| Replay + retention | `tests/test_replay.py` | MockTransport success, blocked private, purge |
| Rate limit | `tests/test_rate_limit.py` | Unit window + HTTP 429 |
| HTMX UI | `tests/test_ui.py` | Create redirect, list partial, replay form |

## Network policy in tests

Replay success paths use `httpx.MockTransport`. SSRF DNS cases patch `socket.getaddrinfo`.
No live outbound network is required for CI.

## Coverage gate

`pyproject.toml` sets `fail_under = 85` for the `webhook_inbox` package.

## Manual smoke (operator)

```bash
docker compose up --build
curl -X POST localhost:8000/api/endpoints
curl -X POST localhost:8000/h/<token> -d '{"hello":"world"}'
curl localhost:8000/api/endpoints/<token>/requests
```
