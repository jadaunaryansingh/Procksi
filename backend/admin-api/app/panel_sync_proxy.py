"""
Server-side proxy for admin-portal -> panel-api "/admin/sync/*" calls.

Incident 2026-09-03 §2.8: the admin frontend used to call panel-api directly
with a shared `X-Admin-Api-Key` header, and that key was baked into the
public admin JS bundle via `VITE_ADMIN_API_KEY` (Vite inlines build-time env
vars into client code). Anyone who downloaded the bundle could extract the
key and hit panel-api's admin-sync surface directly — reset panel passwords,
rewrite the evaluation rubric, bulk-edit teams, post fake alerts.

This proxy removes the client-held secret entirely. The browser authenticates
to admin-api with its normal admin session (enforced app-wide by
`require_admin` in main.py, which every route here inherits by default); only
this server process ever reads ADMIN_API_KEY, and it never leaves the
process. The call to panel-api happens over the docker-compose network by
container name, not over the public internet.
"""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/api/panel-sync", tags=["panel-sync-proxy"])

# Internal, compose-network address — never the public panel.glapms.in host.
PANEL_API_INTERNAL_URL = os.getenv("PANEL_API_INTERNAL_URL", "http://panel-backend:8001").rstrip("/")
_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

# Headers that must not be copied verbatim between hops (RFC 7230 §6.1, plus
# Host/Content-Length which httpx recomputes for the outgoing request).
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-length", "host",
}


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_panel_sync(path: str, request: Request) -> Response:
    """Forward an already-admin-authenticated request to panel-api's /admin/sync/<path>."""
    if not _ADMIN_API_KEY:
        return Response(
            content=b'{"detail":"ADMIN_API_KEY not configured on admin-api"}',
            status_code=500,
            media_type="application/json",
        )

    body = await request.body()
    outgoing_headers = {"X-Admin-Api-Key": _ADMIN_API_KEY}
    content_type = request.headers.get("content-type")
    if content_type:
        outgoing_headers["Content-Type"] = content_type

    async with httpx.AsyncClient(timeout=30.0) as client:
        upstream = await client.request(
            request.method,
            f"{PANEL_API_INTERNAL_URL}/admin/sync/{path}",
            params=request.query_params,
            content=body,
            headers=outgoing_headers,
        )

    response_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
