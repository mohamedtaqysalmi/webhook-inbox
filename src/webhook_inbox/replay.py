"""Replay a stored request to an external URL with SSRF checks."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import httpx

from webhook_inbox.ssrf import ReplayTargetError, validate_replay_url

Clock = Callable[[], float]


@dataclass(frozen=True)
class ReplayResult:
    target_url: str
    status_code: int | None
    error: str | None
    response_headers: list[tuple[str, str]]
    response_body_preview: str
    duration_ms: int


def _preview(body: bytes, limit: int = 2048) -> str:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body[:limit].hex()
        return text[:limit]
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _filter_request_headers(headers: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """Drop hop-by-hop and host headers that must not be forwarded blindly."""
    blocked = {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "upgrade",
    }
    return [(name, value) for name, value in headers if name.lower() not in blocked]


async def replay_stored_request(
    *,
    method: str,
    url: str,
    headers: Sequence[tuple[str, str]],
    body: bytes,
    allow_private: bool,
    timeout_seconds: float,
    client: httpx.AsyncClient | None = None,
    clock: Clock | None = None,
) -> ReplayResult:
    """Send the stored method/headers/body to `url` after SSRF validation.

    `client` and a monotonic `clock` are injectable for tests.
    """
    mono: Clock = clock or time.monotonic
    try:
        target = validate_replay_url(url, allow_private=allow_private)
    except ReplayTargetError as exc:
        return ReplayResult(
            target_url=url.strip(),
            status_code=None,
            error=f"{exc.reason}: {exc}",
            response_headers=[],
            response_body_preview="",
            duration_ms=0,
        )

    outbound_headers = _filter_request_headers(headers)
    started = mono()
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False)
    try:
        response = await http.request(
            method,
            target,
            content=body,
            headers=outbound_headers,
        )
        duration_ms = int((mono() - started) * 1000)
        response_headers = [(k, v) for k, v in response.headers.multi_items()]
        return ReplayResult(
            target_url=target,
            status_code=response.status_code,
            error=None,
            response_headers=response_headers,
            response_body_preview=_preview(response.content),
            duration_ms=duration_ms,
        )
    except httpx.HTTPError as exc:
        duration_ms = int((mono() - started) * 1000)
        return ReplayResult(
            target_url=target,
            status_code=None,
            error=f"http: {exc}",
            response_headers=[],
            response_body_preview="",
            duration_ms=duration_ms,
        )
    finally:
        if owns_client:
            await http.aclose()
