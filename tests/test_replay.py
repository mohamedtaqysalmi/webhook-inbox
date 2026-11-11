import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeClock
from webhook_inbox.app import create_app
from webhook_inbox.config import Settings
from webhook_inbox.replay import ReplayResult, replay_stored_request
from webhook_inbox.storage import Storage


def new_endpoint(client: TestClient) -> str:
    token: str = client.post("/api/endpoints").json()["token"]
    return token


@pytest.fixture
def private_settings(db_path: str) -> Settings:
    return Settings(
        db_path=db_path,
        max_body_bytes=1000,
        max_header_bytes=400,
        base_url="http://inbox.test",
        rate_limit_per_minute=0,
        retention_days=0,
        replay_timeout_seconds=2.0,
        allow_private_replay_targets=True,
    )


@pytest.fixture
def private_client(private_settings: Settings, clock: FakeClock) -> Iterator[TestClient]:
    with TestClient(create_app(private_settings, clock=clock)) as test_client:
        yield test_client


def test_replay_stored_request_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.content == b'{"ok":true}'
        assert request.headers.get("x-custom") == "yes"
        return httpx.Response(202, json={"accepted": True}, headers=[("X-Out", "1")])

    transport = httpx.MockTransport(handler)

    async def run() -> None:
        async with httpx.AsyncClient(transport=transport) as client:
            result = await replay_stored_request(
                method="POST",
                url="http://127.0.0.1/hook",
                headers=[("X-Custom", "yes"), ("Host", "inbox.test"), ("Content-Length", "11")],
                body=b'{"ok":true}',
                allow_private=True,
                timeout_seconds=2.0,
                client=client,
            )
        assert result.status_code == 202
        assert result.error is None
        assert result.response_body_preview == '{"accepted":true}'
        assert ["x-out", "1"] in [[n.lower(), v] for n, v in result.response_headers]

    asyncio.run(run())


def test_replay_ssrf_failure_is_recorded_as_error() -> None:
    result = asyncio.run(
        replay_stored_request(
            method="POST",
            url="http://127.0.0.1/secret",
            headers=[],
            body=b"x",
            allow_private=False,
            timeout_seconds=1.0,
        )
    )
    assert result.status_code is None
    assert result.error is not None
    assert result.error.startswith("private:")


def test_api_replay_blocks_private_target(client: TestClient) -> None:
    token = new_endpoint(client)
    request_id = client.post(f"/h/{token}", content=b"payload").json()["id"]
    response = client.post(
        f"/api/endpoints/{token}/requests/{request_id}/replay",
        json={"url": "http://127.0.0.1/hook"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status_code"] is None
    assert body["error"].startswith("private:")
    listed = client.get(f"/api/endpoints/{token}/requests/{request_id}/replays").json()["items"]
    assert len(listed) == 1
    assert listed[0]["error"].startswith("private:")


def test_api_replay_requires_url(client: TestClient) -> None:
    token = new_endpoint(client)
    request_id = client.post(f"/h/{token}", content=b"payload").json()["id"]
    assert (
        client.post(
            f"/api/endpoints/{token}/requests/{request_id}/replay",
            json={"url": ""},
        ).status_code
        == 422
    )


def test_api_replay_success_with_stub(
    private_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = new_endpoint(private_client)
    request_id = private_client.post(f"/h/{token}", content=b"hello").json()["id"]

    async def fake_replay(**_kwargs: object) -> ReplayResult:
        return ReplayResult(
            target_url="http://127.0.0.1/hook",
            status_code=200,
            error=None,
            response_headers=[("content-type", "text/plain")],
            response_body_preview="pong",
            duration_ms=3,
        )

    monkeypatch.setattr("webhook_inbox.app.replay_stored_request", fake_replay)
    response = private_client.post(
        f"/api/endpoints/{token}/requests/{request_id}/replay",
        json={"url": "http://127.0.0.1/hook"},
    )
    assert response.status_code == 201
    assert response.json()["status_code"] == 200
    assert response.json()["response_body_preview"] == "pong"


def test_retention_deletes_old_requests(db_path: str, clock: FakeClock) -> None:
    store = Storage(db_path, clock=clock)
    store.init_schema()
    store.create_endpoint("tok")
    store.add_request(
        "tok",
        method="POST",
        path="/h/tok",
        query_string="",
        headers=[],
        headers_truncated=False,
        body=b"old",
        source_ip=None,
    )
    clock.advance(days=10)
    store.add_request(
        "tok",
        method="POST",
        path="/h/tok",
        query_string="",
        headers=[],
        headers_truncated=False,
        body=b"new",
        source_ip=None,
    )
    deleted = store.delete_requests_older_than(7)
    assert deleted == 1
    remaining = store.list_requests("tok")
    assert [r.body for r in remaining] == [b"new"]


def test_app_purges_on_list(tmp_path: Path, clock: FakeClock) -> None:
    settings = Settings(
        db_path=str(tmp_path / "ret.db"),
        max_body_bytes=1000,
        max_header_bytes=400,
        base_url="http://inbox.test",
        rate_limit_per_minute=0,
        retention_days=7,
        replay_timeout_seconds=2.0,
        allow_private_replay_targets=False,
    )
    with TestClient(create_app(settings, clock=clock)) as client:
        token = new_endpoint(client)
        client.post(f"/h/{token}", content=b"old")
        clock.advance(days=8)
        client.post(f"/h/{token}", content=b"fresh")
        items = client.get(f"/api/endpoints/{token}/requests").json()["items"]
        assert len(items) == 1
