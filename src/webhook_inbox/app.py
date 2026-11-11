from __future__ import annotations

import base64
import secrets
from datetime import datetime
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from webhook_inbox.config import Settings
from webhook_inbox.storage import Clock, Storage, StoredRequest, cap_headers, utc_now

ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


class BodyTooLarge(Exception):
    pass


def _summary(item: StoredRequest) -> dict[str, Any]:
    return {
        "id": item.id,
        "received_at": item.received_at.isoformat(),
        "method": item.method,
        "path": item.path,
        "query_string": item.query_string,
        "source_ip": item.source_ip,
        "body_size": len(item.body),
    }


def _detail(item: StoredRequest) -> dict[str, Any]:
    try:
        body, encoding = item.body.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        body, encoding = base64.b64encode(item.body).decode("ascii"), "base64"
    return {
        **_summary(item),
        "headers": [[name, value] for name, value in item.headers],
        "headers_truncated": item.headers_truncated,
        "body": body,
        "body_encoding": encoding,
    }


async def _read_limited_body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise BodyTooLarge
    chunks: list[bytes] = []
    total = 0
    # Count while streaming so a chunked upload without Content-Length is stopped too.
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise BodyTooLarge
        chunks.append(chunk)
    return b"".join(chunks)


def create_app(settings: Settings | None = None, clock: Clock = utc_now) -> FastAPI:
    # With no settings given, read and validate the environment now so a bad
    # config stops the process at startup instead of on the first request.
    settings = settings or Settings.from_env()
    storage = Storage(settings.db_path, clock=clock)
    storage.init_schema()

    app = FastAPI(title="webhook-inbox", version="0.0.1")

    def require_endpoint(token: str) -> None:
        if not storage.endpoint_exists(token):
            raise HTTPException(status_code=404, detail="endpoint not found")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/endpoints", status_code=201)
    def create_endpoint() -> dict[str, str]:
        token = secrets.token_urlsafe(24)
        created_at = storage.create_endpoint(token)
        return {
            "token": token,
            "url": f"{settings.base_url}/h/{token}",
            "created_at": created_at.isoformat(),
        }

    @app.api_route("/h/{token}", methods=ALL_METHODS)
    @app.api_route("/h/{token}/{subpath:path}", methods=ALL_METHODS)
    async def receive(token: str, request: Request, subpath: str = "") -> JSONResponse:
        await run_in_threadpool(require_endpoint, token)
        try:
            body = await _read_limited_body(request, settings.max_body_bytes)
        except BodyTooLarge:
            return JSONResponse(
                status_code=413,
                content={
                    "detail": f"request body exceeds the limit of {settings.max_body_bytes} bytes"
                },
            )
        raw_headers = [
            (name.decode("latin-1"), value.decode("latin-1")) for name, value in request.headers.raw
        ]
        headers, truncated = cap_headers(raw_headers, settings.max_header_bytes)
        stored = await run_in_threadpool(
            lambda: storage.add_request(
                token,
                method=request.method,
                path=request.url.path,
                query_string=request.url.query,
                headers=headers,
                headers_truncated=truncated,
                body=body,
                source_ip=request.client.host if request.client else None,
            )
        )
        return JSONResponse(status_code=200, content={"status": "received", "id": stored.id})

    @app.get("/api/endpoints/{token}/requests")
    def list_requests(
        token: str,
        method: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        require_endpoint(token)
        items = storage.list_requests(
            token,
            method=method,
            since=since,
            until=until,
            text=q,
            limit=limit,
            offset=offset,
        )
        return {"items": [_summary(item) for item in items], "limit": limit, "offset": offset}

    @app.get("/api/endpoints/{token}/requests/{request_id}")
    def get_request(token: str, request_id: int) -> dict[str, Any]:
        require_endpoint(token)
        item = storage.get_request(token, request_id)
        if item is None:
            raise HTTPException(status_code=404, detail="request not found")
        return _detail(item)

    return app
