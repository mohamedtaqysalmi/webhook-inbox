# webhook-inbox

A self-hosted inbox to receive, store, inspect and replay webhooks. The plan is FastAPI and SQLite with a small server-rendered HTMX UI, HMAC signature verification helpers, and SSRF protection on replay targets.

**Status: early scaffold, nothing usable yet.** The package currently only exposes a version number. The features above are the goal, not what exists today.

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
