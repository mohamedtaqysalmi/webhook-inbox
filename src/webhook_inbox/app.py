from __future__ import annotations

import base64
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from webhook_inbox.config import Settings
from webhook_inbox.rate_limit import RateLimiter
from webhook_inbox.replay import replay_stored_request
from webhook_inbox.storage import Clock, Storage, StoredReplay, StoredRequest, cap_headers, utc_now

ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class BodyTooLarge(Exception):
    pass


class ReplayRequest(BaseModel):
    url: str = Field(min_length=1)


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


def _replay_payload(item: StoredReplay) -> dict[str, Any]:
    return {
        "id": item.id,
        "request_id": item.request_id,
        "target_url": item.target_url,
        "started_at": item.started_at.isoformat(),
        "finished_at": item.finished_at.isoformat(),
        "status_code": item.status_code,
        "error": item.error,
        "response_headers": [[name, value] for name, value in item.response_headers],
        "response_body_preview": item.response_body_preview,
        "duration_ms": item.duration_ms,
    }


def _body_text(item: StoredRequest) -> str:
    try:
        return item.body.decode("utf-8")
    except UnicodeDecodeError:
        return base64.b64encode(item.body).decode("ascii")


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


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, limiter: RateLimiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._limiter.enabled:
            return await call_next(request)
        path = request.url.path
        if path.startswith("/h/") or path == "/api/endpoints":
            client = request.client.host if request.client else "unknown"
            if not self._limiter.allow(client):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "rate limit exceeded"},
                    headers={"Retry-After": "60"},
                )
        return await call_next(request)


def create_app(settings: Settings | None = None, clock: Clock = utc_now) -> FastAPI:
    # With no settings given, read and validate the environment now so a bad
    # config stops the process at startup instead of on the first request.
    settings = settings or Settings.from_env()
    storage = Storage(settings.db_path, clock=clock)
    storage.init_schema()
    storage.delete_requests_older_than(settings.retention_days)

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    limiter = RateLimiter(settings.rate_limit_per_minute)

    app = FastAPI(title="webhook-inbox", version="0.1.0")
    app.add_middleware(RateLimitMiddleware, limiter=limiter)

    def require_endpoint(token: str) -> None:
        if not storage.endpoint_exists(token):
            raise HTTPException(status_code=404, detail="endpoint not found")

    def maybe_purge() -> None:
        storage.delete_requests_older_than(settings.retention_days)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "home.html")

    @app.post("/ui/endpoints")
    def ui_create_endpoint() -> RedirectResponse:
        token = secrets.token_urlsafe(24)
        storage.create_endpoint(token)
        return RedirectResponse(url=f"/ui/{token}", status_code=303)

    @app.get("/ui/{token}", response_class=HTMLResponse)
    def ui_inbox(token: str, request: Request) -> HTMLResponse:
        require_endpoint(token)
        maybe_purge()
        return templates.TemplateResponse(
            request,
            "inbox.html",
            {
                "token": token,
                "hook_url": f"{settings.base_url}/h/{token}",
            },
        )

    @app.get("/ui/{token}/requests", response_class=HTMLResponse)
    def ui_list_requests(
        token: str,
        request: Request,
        method: str | None = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> HTMLResponse:
        require_endpoint(token)
        maybe_purge()
        items = storage.list_requests(token, method=method or None, text=q, limit=limit)
        return templates.TemplateResponse(
            request,
            "partials/request_list.html",
            {
                "token": token,
                "items": items,
                "hook_url": f"{settings.base_url}/h/{token}",
            },
        )

    @app.get("/ui/{token}/requests/{request_id}", response_class=HTMLResponse)
    def ui_request_detail(token: str, request_id: int, request: Request) -> HTMLResponse:
        require_endpoint(token)
        item = storage.get_request(token, request_id)
        if item is None:
            raise HTTPException(status_code=404, detail="request not found")
        replays = storage.list_replays(token, request_id)
        return templates.TemplateResponse(
            request,
            "partials/request_detail.html",
            {
                "token": token,
                "item": item,
                "body_text": _body_text(item),
                "replays": replays,
            },
        )

    @app.post("/ui/{token}/requests/{request_id}/replay", response_class=HTMLResponse)
    async def ui_replay(
        token: str,
        request_id: int,
        request: Request,
        target_url: Annotated[str, Form()],
    ) -> HTMLResponse:
        require_endpoint(token)
        item = storage.get_request(token, request_id)
        if item is None:
            raise HTTPException(status_code=404, detail="request not found")
        started = clock()
        result = await replay_stored_request(
            method=item.method,
            url=target_url,
            headers=item.headers,
            body=item.body,
            allow_private=settings.allow_private_replay_targets,
            timeout_seconds=settings.replay_timeout_seconds,
        )
        finished = clock()
        if finished <= started:
            finished = started + timedelta(milliseconds=max(result.duration_ms, 1))
        replay = storage.add_replay(
            token,
            request_id,
            target_url=result.target_url,
            started_at=started,
            finished_at=finished,
            status_code=result.status_code,
            error=result.error,
            response_headers=result.response_headers,
            response_body_preview=result.response_body_preview,
            duration_ms=result.duration_ms,
        )
        return templates.TemplateResponse(
            request,
            "partials/replay_result.html",
            {"replay": replay},
        )

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
        await run_in_threadpool(maybe_purge)
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
        maybe_purge()
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

    @app.post("/api/endpoints/{token}/requests/{request_id}/replay", status_code=201)
    async def replay_request(token: str, request_id: int, payload: ReplayRequest) -> dict[str, Any]:
        require_endpoint(token)
        item = storage.get_request(token, request_id)
        if item is None:
            raise HTTPException(status_code=404, detail="request not found")
        target_url = payload.url.strip()
        started = clock()
        result = await replay_stored_request(
            method=item.method,
            url=target_url,
            headers=item.headers,
            body=item.body,
            allow_private=settings.allow_private_replay_targets,
            timeout_seconds=settings.replay_timeout_seconds,
        )
        finished = clock()
        if finished <= started:
            finished = started + timedelta(milliseconds=max(result.duration_ms, 1))
        replay = storage.add_replay(
            token,
            request_id,
            target_url=result.target_url,
            started_at=started,
            finished_at=finished,
            status_code=result.status_code,
            error=result.error,
            response_headers=result.response_headers,
            response_body_preview=result.response_body_preview,
            duration_ms=result.duration_ms,
        )
        return _replay_payload(replay)

    @app.get("/api/endpoints/{token}/requests/{request_id}/replays")
    def list_request_replays(token: str, request_id: int) -> dict[str, Any]:
        require_endpoint(token)
        if storage.get_request(token, request_id) is None:
            raise HTTPException(status_code=404, detail="request not found")
        return {
            "items": [_replay_payload(item) for item in storage.list_replays(token, request_id)]
        }

    return app
