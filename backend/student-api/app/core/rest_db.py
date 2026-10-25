"""Async PostgREST data access over HTTPS (port 443).

Why this exists: the student API normally reaches Postgres directly via asyncpg
on port 5432/6543. Many networks (campus/corporate WiFi, some ISPs) silently
drop outbound traffic on those ports, which makes every DB call hang until it
times out. Supabase also exposes the same data through its REST API on 443,
which those networks allow — so this module provides the small slice of CRUD
the auth flow needs, without the `supabase` package (httpx only).

Filters are expressed as simple equality dicts, e.g. ``eq={"email": addr}``,
which map to PostgREST's ``?email=eq.<value>`` syntax.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.core.config import settings

_TIMEOUT = 20.0


def is_configured() -> bool:
    """True when Supabase REST credentials are present."""
    url = (getattr(settings, 'SUPABASE_URL', None) or getattr(settings, 'supabase_url', None) or "").strip()
    key = (getattr(settings, 'SUPABASE_SERVICE_KEY', None) or getattr(settings, 'supabase_service_key', None) or getattr(settings, 'SUPABASE_KEY', None) or getattr(settings, 'supabase_key', None) or "").strip()
    return bool(url and url.startswith(("http://", "https://")) and key)


def _base() -> str:
    url = (getattr(settings, 'SUPABASE_URL', None) or getattr(settings, 'supabase_url', None) or "").strip()
    return url.rstrip("/") + "/rest/v1"


def _headers(extra: Optional[dict] = None) -> dict:
    key = (getattr(settings, 'SUPABASE_SERVICE_KEY', None) or getattr(settings, 'supabase_service_key', None) or getattr(settings, 'SUPABASE_KEY', None) or getattr(settings, 'supabase_key', None) or "").strip()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def _eq_params(eq: Optional[dict]) -> dict:
    return {k: f"eq.{v}" for k, v in (eq or {}).items()}


def _raise(resp: httpx.Response, table: str, op: str) -> None:
    """Raise with PostgREST's error body included.

    ``raise_for_status`` alone only reports the status code, which hides the
    actual cause (missing column, constraint violation, ...).
    """
    if resp.is_error:
        raise httpx.HTTPStatusError(
            f"{op} {table} failed: HTTP {resp.status_code} - {resp.text[:400]}",
            request=resp.request,
            response=resp,
        )


async def select(
    table: str,
    *,
    columns: str = "*",
    eq: Optional[dict] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """SELECT rows. Returns [] when nothing matches or REST not configured."""
    if not is_configured():
        return []
    params: dict[str, Any] = {"select": columns, **_eq_params(eq)}
    if limit is not None:
        params["limit"] = limit
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_base()}/{table}", headers=_headers(), params=params)
        _raise(resp, table, "select")
        return resp.json() or []


async def select_one(table: str, *, columns: str = "*", eq: Optional[dict] = None) -> Optional[dict]:
    if not is_configured():
        return None
    rows = await select(table, columns=columns, eq=eq, limit=1)
    return rows[0] if rows else None


async def insert(table: str, row: dict) -> Optional[dict]:
    """INSERT one row, returning the created row."""
    if not is_configured():
        return None
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_base()}/{table}",
            headers=_headers({"Prefer": "return=representation"}),
            json=row,
        )
        _raise(resp, table, "insert")
        data = resp.json() or []
        return data[0] if isinstance(data, list) and data else None


async def update(table: str, eq: dict, patch: dict) -> list[dict[str, Any]]:
    """UPDATE rows matching ``eq``, returning the updated rows."""
    if not is_configured():
        return []
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.patch(
            f"{_base()}/{table}",
            headers=_headers({"Prefer": "return=representation"}),
            params=_eq_params(eq),
            json=patch,
        )
        _raise(resp, table, "update")
        return resp.json() or []


async def delete(table: str, eq: dict) -> None:
    """DELETE rows matching ``eq``. Missing rows are not an error."""
    if not is_configured():
        return
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.delete(f"{_base()}/{table}", headers=_headers(), params=_eq_params(eq))
        _raise(resp, table, "delete")
