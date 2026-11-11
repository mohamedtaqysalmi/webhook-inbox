from datetime import UTC, datetime

from tests.conftest import FakeClock
from webhook_inbox.storage import Storage, cap_headers, format_timestamp, parse_timestamp


def add(storage: Storage, token: str, method: str = "POST", body: bytes = b"{}") -> int:
    return storage.add_request(
        token,
        method=method,
        path=f"/h/{token}",
        query_string="",
        headers=[("content-type", "application/json")],
        headers_truncated=False,
        body=body,
        source_ip="203.0.113.7",
    ).id


def test_roundtrip_with_injected_clock(storage: Storage, clock: FakeClock) -> None:
    storage.create_endpoint("tok")
    request_id = storage.add_request(
        "tok",
        method="POST",
        path="/h/tok/x",
        query_string="a=1",
        headers=[("x-a", "1"), ("x-a", "2")],
        headers_truncated=False,
        body=b"\x00\xffbinary",
        source_ip=None,
    ).id
    stored = storage.get_request("tok", request_id)
    assert stored is not None
    assert stored.received_at == clock.now
    assert stored.headers == [("x-a", "1"), ("x-a", "2")]
    assert stored.body == b"\x00\xffbinary"
    assert stored.source_ip is None
    assert stored.query_string == "a=1"


def test_get_is_scoped_to_endpoint(storage: Storage) -> None:
    storage.create_endpoint("a")
    storage.create_endpoint("b")
    request_id = add(storage, "a")
    assert storage.get_request("b", request_id) is None
    assert storage.get_request("a", 9999) is None


def test_endpoint_exists(storage: Storage) -> None:
    assert not storage.endpoint_exists("nope")
    storage.create_endpoint("yes")
    assert storage.endpoint_exists("yes")


def test_list_newest_first_and_paging(storage: Storage, clock: FakeClock) -> None:
    storage.create_endpoint("tok")
    ids = []
    for _ in range(5):
        ids.append(add(storage, "tok"))
        clock.advance(seconds=1)
    listed = [r.id for r in storage.list_requests("tok")]
    assert listed == ids[::-1]
    page = [r.id for r in storage.list_requests("tok", limit=2, offset=1)]
    assert page == ids[::-1][1:3]


def test_filter_by_method_is_case_insensitive(storage: Storage) -> None:
    storage.create_endpoint("tok")
    add(storage, "tok", method="POST")
    add(storage, "tok", method="GET")
    assert [r.method for r in storage.list_requests("tok", method="get")] == ["GET"]


def test_filter_by_date_range(storage: Storage, clock: FakeClock) -> None:
    storage.create_endpoint("tok")
    times = []
    for _ in range(4):
        times.append(clock.now)
        add(storage, "tok")
        clock.advance(hours=1)
    found = storage.list_requests("tok", since=times[1], until=times[2])
    assert sorted(r.received_at for r in found) == [times[1], times[2]]
    only_after = storage.list_requests("tok", since=times[3])
    assert [r.received_at for r in only_after] == [times[3]]


def test_naive_datetimes_are_treated_as_utc() -> None:
    naive = datetime(2026, 1, 2, 3, 4, 5)
    aware = naive.replace(tzinfo=UTC)
    assert format_timestamp(naive) == format_timestamp(aware)
    assert parse_timestamp(format_timestamp(aware)) == aware


def test_text_search_in_body(storage: Storage) -> None:
    storage.create_endpoint("tok")
    add(storage, "tok", body=b'{"event":"invoice.paid"}')
    add(storage, "tok", body=b'{"event":"user.created"}')
    add(storage, "tok", body=b"100%_done")
    assert len(storage.list_requests("tok", text="INVOICE")) == 1
    assert len(storage.list_requests("tok", text="event")) == 2
    # LIKE wildcards in the search text are matched literally.
    assert len(storage.list_requests("tok", text="%")) == 1
    assert len(storage.list_requests("tok", text="_d")) == 1
    assert storage.list_requests("tok", text="absent") == []


def test_cap_headers_keeps_order_and_flags_truncation() -> None:
    headers = [("a", "1" * 10), ("b", "2" * 10), ("c", "3" * 10)]
    kept, truncated = cap_headers(headers, 100)
    assert kept == headers
    assert not truncated
    kept, truncated = cap_headers(headers, 15)
    assert kept == headers[:1]
    assert truncated
    assert cap_headers(headers, 0) == ([], True)
