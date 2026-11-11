# Contributing

This project is maintained by one person. Issues and pull requests are welcome, but replies may take a few days.

## Setup

You need Python 3.11 or newer.

```bash
python -m venv .venv
. .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pre-commit install
```

## Checks

CI runs these on Python 3.11 and 3.14. Run them locally before opening a PR:

```bash
ruff check .
ruff format --check .
mypy
pytest
```

`pytest` reports coverage and fails below 85%.

## Branches and commits

- Branch from `main` and name the branch `type/short-description`, for example `feat/replay-endpoint` or `fix/signature-timing`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`).
- `main` only changes through pull requests, which are squash-merged after CI passes.

## Pull requests

- Keep one change per PR and fill in the template: what, why, how you tested it.
- Add or update tests for behavior changes.
- Update `CHANGELOG.md` under Unreleased for anything user-visible.
- For anything large, open an issue first so we can agree on the approach before you spend time on it.
- Never include real secrets or real customer webhook payloads in code, tests or issues.

Security problems go through the process in [SECURITY.md](SECURITY.md), not public issues.