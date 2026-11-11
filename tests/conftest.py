from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from webhook_inbox.app import create_app
from webhook_inbox.config import Settings
from webhook_inbox.storage import Storage


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture
def storage(db_path: str, clock: FakeClock) -> Storage:
    store = Storage(db_path, clock=clock)
    store.init_schema()
    return store


@pytest.fixture
def settings(db_path: str) -> Settings:
    return Settings(
        db_path=db_path,
        max_body_bytes=1000,
        max_header_bytes=400,
        base_url="http://inbox.test",
    )


@pytest.fixture
def client(settings: Settings, clock: FakeClock) -> Iterator[TestClient]:
    with TestClient(create_app(settings, clock=clock)) as test_client:
        yield test_client
