from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeClock
from webhook_inbox.app import create_app
from webhook_inbox.config import ConfigError, Settings


def new_endpoint(client: TestClient) -> str:
    response = client.post("/api/endpoints")
    assert response.status_code == 201
    token: str = response.json()["token"]
    return token


def test_healthz(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_create_endpoint_returns_unguessable_url(client: TestClient) -> None:
    first = client.post("/api/endpoints").json()
    second = client.post("/api/endpoints").json()
    assert first["token"] != second["token"]
    assert len(first["token"]) >= 32
    assert first["url"] == f"http://inbox.test/h/{first['token']}"
    assert first["created_at"].startswith("2026-03-01T12:00:00")


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_receives_any_method(client: TestClient, method: str) -> None:
    token = new_endpoint(client)
    response = client.request(method, f"/h/{token}", content=b"hello")
    assert response.status_code == 200
    items = client.get(f"/api/endpoints/{token}/requests").json()["items"]
    assert [item["method"] for item in items] == [method]


def test_stores_request_details(client: TestClient, clock: FakeClock) -> None:
    token = new_endpoint(client)
    clock.advance(minutes=5)
    response = client.post(
        f"/h/{token}/orders/17?expand=items",
        json={"ok": True},
        headers={"X-Custom": "yes"},
    )
    request_id = response.json()["id"]

    detail = client.get(f"/api/endpoints/{token}/requests/{request_id}").json()
    assert detail["method"] == "POST"
    assert detail["path"] == f"/h/{token}/orders/17"
    assert detail["query_string"] == "expand=items"
    assert detail["received_at"].startswith("2026-03-01T12:05:00")
    assert detail["body"] == '{"ok":true}'
    assert detail["body_encoding"] == "utf-8"
    assert detail["source_ip"] == "testclient"
    assert detail["headers_truncated"] is False
    assert ["x-custom", "yes"] in detail["headers"]


def test_binary_body_is_returned_as_base64(client: TestClient) -> None:
    token = new_endpoint(client)
    request_id = client.post(f"/h/{token}", content=b"\xff\xfe\x00").json()["id"]
    detail = client.get(f"/api/endpoints/{token}/requests/{request_id}").json()
    assert detail["body_encoding"] == "base64"
    assert detail["body"] == "//4A"


def test_unknown_token_is_404(client: TestClient) -> None:
    assert client.post("/h/nope", content=b"x").status_code == 404
    assert client.get("/api/endpoints/nope/requests").status_code == 404
    assert client.get("/api/endpoints/nope/requests/1").status_code == 404


def test_unknown_request_is_404(client: TestClient) -> None:
    token = new_endpoint(client)
    assert client.get(f"/api/endpoints/{token}/requests/123").status_code == 404


def test_body_at_limit_is_accepted(client: TestClient) -> None:
    token = new_endpoint(client)
    assert client.post(f"/h/{token}", content=b"a" * 1000).status_code == 200


def test_body_over_limit_is_413_via_content_length(client: TestClient) -> None:
    token = new_endpoint(client)
    response = client.post(f"/h/{token}", content=b"a" * 1001)
    assert response.status_code == 413
    assert "1000 bytes" in response.json()["detail"]
    assert client.get(f"/api/endpoints/{token}/requests").json()["items"] == []


def test_body_over_limit_is_413_when_streamed_without_content_length(
    client: TestClient,
) -> None:
    token = new_endpoint(client)

    def chunks() -> Iterator[bytes]:
        for _ in range(11):
            yield b"a" * 100

    response = client.post(f"/h/{token}", content=chunks())
    assert response.status_code == 413
    assert client.get(f"/api/endpoints/{token}/requests").json()["items"] == []


def test_headers_are_capped(client: TestClient) -> None:
    token = new_endpoint(client)
    request_id = client.post(f"/h/{token}", content=b"x", headers={"X-Big": "v" * 600}).json()["id"]
    detail = client.get(f"/api/endpoints/{token}/requests/{request_id}").json()
    assert detail["headers_truncated"] is True
    assert all(name != "x-big" for name, _ in detail["headers"])


def test_list_filters(client: TestClient, clock: FakeClock) -> None:
    token = new_endpoint(client)
    client.post(f"/h/{token}", content=b"alpha")
    clock.advance(hours=1)
    client.put(f"/h/{token}", content=b"beta")
    clock.advance(hours=1)
    client.post(f"/h/{token}", content=b"alphabet")

    def ids(**params: str | int) -> list[int]:
        body = client.get(f"/api/endpoints/{token}/requests", params=params).json()
        return [item["id"] for item in body["items"]]

    assert ids() == [3, 2, 1]
    assert ids(method="POST") == [3, 1]
    assert ids(q="alpha") == [3, 1]
    assert ids(since="2026-03-01T13:00:00Z", until="2026-03-01T13:30:00Z") == [2]
    assert ids(since="2026-03-01T13:00:00Z") == [3, 2]
    assert ids(limit=1, offset=1) == [2]


def test_list_rejects_bad_params(client: TestClient) -> None:
    token = new_endpoint(client)
    for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}, {"since": "yesterday"}):
        assert client.get(f"/api/endpoints/{token}/requests", params=params).status_code == 422


def test_requests_do_not_leak_between_endpoints(client: TestClient) -> None:
    a, b = new_endpoint(client), new_endpoint(client)
    client.post(f"/h/{a}", content=b"for a")
    assert client.get(f"/api/endpoints/{b}/requests").json()["items"] == []


def test_data_survives_app_restart(settings: Settings, clock: FakeClock) -> None:
    with TestClient(create_app(settings, clock=clock)) as first:
        token = new_endpoint(first)
        first.post(f"/h/{token}", content=b"kept")
    with TestClient(create_app(settings, clock=clock)) as second:
        items = second.get(f"/api/endpoints/{token}/requests").json()["items"]
    assert len(items) == 1


def test_invalid_environment_stops_startup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WEBHOOK_INBOX_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("WEBHOOK_INBOX_MAX_BODY_BYTES", "-5")
    with pytest.raises(ConfigError):
        create_app()


def test_valid_environment_starts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WEBHOOK_INBOX_DB_PATH", str(tmp_path / "env.db"))
    with TestClient(create_app()) as env_client:
        assert env_client.get("/healthz").status_code == 200
