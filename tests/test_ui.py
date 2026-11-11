from fastapi.testclient import TestClient


def test_home_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Create endpoint" in response.text


def test_ui_create_and_list(client: TestClient) -> None:
    created = client.post("/ui/endpoints", follow_redirects=False)
    assert created.status_code == 303
    location = created.headers["location"]
    assert location.startswith("/ui/")
    token = location.rsplit("/", 1)[-1]

    inbox = client.get(location)
    assert inbox.status_code == 200
    assert token in inbox.text

    client.post(f"/h/{token}", content=b'{"hello":"ui"}')
    listing = client.get(f"/ui/{token}/requests")
    assert listing.status_code == 200
    assert "POST" in listing.text

    detail = client.get(f"/ui/{token}/requests/1")
    assert detail.status_code == 200
    assert "hello" in detail.text
    assert "Replay" in detail.text


def test_ui_replay_form_records_error(client: TestClient) -> None:
    token = client.post("/api/endpoints").json()["token"]
    request_id = client.post(f"/h/{token}", content=b"x").json()["id"]
    response = client.post(
        f"/ui/{token}/requests/{request_id}/replay",
        data={"target_url": "http://127.0.0.1/hook"},
    )
    assert response.status_code == 200
    assert "private:" in response.text
