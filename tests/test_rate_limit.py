from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import FakeClock
from webhook_inbox.app import create_app
from webhook_inbox.config import Settings
from webhook_inbox.rate_limit import RateLimiter


def test_rate_limiter_allows_then_blocks() -> None:
    ticks = iter([0.0, 0.1, 0.2, 0.3])
    limiter = RateLimiter(2, clock=lambda: next(ticks))
    assert limiter.allow("a")
    assert limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")


def test_rate_limiter_disabled() -> None:
    limiter = RateLimiter(0)
    assert limiter.enabled is False
    assert limiter.allow("a")


def test_app_returns_429_when_limited(tmp_path: Path, clock: FakeClock) -> None:
    settings = Settings(
        db_path=str(tmp_path / "r.db"),
        max_body_bytes=1000,
        max_header_bytes=400,
        base_url="http://inbox.test",
        rate_limit_per_minute=2,
        retention_days=0,
        replay_timeout_seconds=2.0,
        allow_private_replay_targets=False,
    )
    with TestClient(create_app(settings, clock=clock)) as client:
        assert client.post("/api/endpoints").status_code == 201
        assert client.post("/api/endpoints").status_code == 201
        blocked = client.post("/api/endpoints")
        assert blocked.status_code == 429
        assert blocked.json()["detail"] == "rate limit exceeded"
