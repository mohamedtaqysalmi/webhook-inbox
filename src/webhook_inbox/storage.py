from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

Clock = Callable[[], datetime]

_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS endpoints (
    token      TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requests (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_token    TEXT NOT NULL REFERENCES endpoints(token),
    received_at       TEXT NOT NULL,
    method            TEXT NOT NULL,
    path              TEXT NOT NULL,
    query_string      TEXT NOT NULL,
    headers           TEXT NOT NULL,
    headers_truncated INTEGER NOT NULL,
    body              BLOB NOT NULL,
    source_ip         TEXT
);

CREATE INDEX IF NOT EXISTS idx_requests_endpoint_time
    ON requests(endpoint_token, received_at);
"""


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_timestamp(value: datetime) -> str:
    # Fixed-width UTC strings sort the same way as the instants they represent,
    # so range filters can compare them as plain text.
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime(_TS_FORMAT)


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, _TS_FORMAT).replace(tzinfo=UTC)


def cap_headers(
    headers: Sequence[tuple[str, str]], max_bytes: int
) -> tuple[list[tuple[str, str]], bool]:
    """Keep headers in order until the byte budget is used up.

    Returns the kept headers and whether anything was dropped.
    """
    kept: list[tuple[str, str]] = []
    used = 0
    for name, value in headers:
        size = len(name.encode("utf-8")) + len(value.encode("utf-8"))
        if used + size > max_bytes:
            return kept, True
        kept.append((name, value))
        used += size
    return kept, False


@dataclass(frozen=True)
class StoredRequest:
    id: int
    endpoint_token: str
    received_at: datetime
    method: str
    path: str
    query_string: str
    headers: list[tuple[str, str]]
    headers_truncated: bool
    body: bytes
    source_ip: str | None


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class Storage:
    """SQLite storage. Each call opens its own short-lived connection, which keeps
    it safe to use from FastAPI's worker threads without sharing connection state."""

    def __init__(self, db_path: str, clock: Clock = utc_now) -> None:
        self._db_path = db_path
        self._clock = clock

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self._db_path, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                yield conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_SCHEMA)

    def create_endpoint(self, token: str) -> datetime:
        created_at = self._clock()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO endpoints (token, created_at) VALUES (?, ?)",
                (token, format_timestamp(created_at)),
            )
        return created_at

    def endpoint_exists(self, token: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM endpoints WHERE token = ?", (token,)).fetchone()
        return row is not None

    def add_request(
        self,
        token: str,
        *,
        method: str,
        path: str,
        query_string: str,
        headers: Sequence[tuple[str, str]],
        headers_truncated: bool,
        body: bytes,
        source_ip: str | None,
    ) -> StoredRequest:
        received_at = self._clock()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO requests (endpoint_token, received_at, method, path, query_string,"
                " headers, headers_truncated, body, source_ip) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    token,
                    format_timestamp(received_at),
                    method,
                    path,
                    query_string,
                    json.dumps(list(headers)),
                    int(headers_truncated),
                    body,
                    source_ip,
                ),
            )
            request_id = cursor.lastrowid
        assert request_id is not None
        return StoredRequest(
            id=request_id,
            endpoint_token=token,
            received_at=received_at.astimezone(UTC),
            method=method,
            path=path,
            query_string=query_string,
            headers=list(headers),
            headers_truncated=headers_truncated,
            body=body,
            source_ip=source_ip,
        )

    def get_request(self, token: str, request_id: int) -> StoredRequest | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM requests WHERE endpoint_token = ? AND id = ?",
                (token, request_id),
            ).fetchone()
        return _row_to_request(row) if row else None

    def list_requests(
        self,
        token: str,
        *,
        method: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        text: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StoredRequest]:
        clauses = ["endpoint_token = ?"]
        params: list[object] = [token]
        if method:
            clauses.append("method = ?")
            params.append(method.upper())
        if since:
            clauses.append("received_at >= ?")
            params.append(format_timestamp(since))
        if until:
            clauses.append("received_at <= ?")
            params.append(format_timestamp(until))
        if text:
            clauses.append("CAST(body AS TEXT) LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(text)}%")
        sql = (
            "SELECT * FROM requests WHERE "
            + " AND ".join(clauses)
            + " ORDER BY received_at DESC, id DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_request(row) for row in rows]


def _row_to_request(row: sqlite3.Row) -> StoredRequest:
    return StoredRequest(
        id=row["id"],
        endpoint_token=row["endpoint_token"],
        received_at=parse_timestamp(row["received_at"]),
        method=row["method"],
        path=row["path"],
        query_string=row["query_string"],
        headers=[(name, value) for name, value in json.loads(row["headers"])],
        headers_truncated=bool(row["headers_truncated"]),
        body=bytes(row["body"]),
        source_ip=row["source_ip"],
    )
