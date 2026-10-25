"""Async PostgREST data access over HTTPS (port 443).

Why this exists: the mentor API normally reaches Postgres directly via asyncpg
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
    url = (getattr(settings, 'supabase_url', None) or getattr(settings, 'SUPABASE_URL', None) or "").strip()
    key = (getattr(settings, 'supabase_service_key', None) or getattr(settings, 'SUPABASE_SERVICE_KEY', None) or getattr(settings, 'supabase_key', None) or getattr(settings, 'SUPABASE_KEY', None) or "").strip()
    return bool(url and url.startswith(("http://", "https://")) and key)


def _base() -> str:
    url = (getattr(settings, 'supabase_url', None) or getattr(settings, 'SUPABASE_URL', None) or "").strip()
    return url.rstrip("/") + "/rest/v1"


def _headers(extra: Optional[dict] = None) -> dict:
    key = (getattr(settings, 'supabase_service_key', None) or getattr(settings, 'SUPABASE_SERVICE_KEY', None) or getattr(settings, 'supabase_key', None) or getattr(settings, 'SUPABASE_KEY', None) or "").strip()
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


def _quote_in_value(value: Any) -> str:
    """Render one member of a PostgREST ``in.(...)`` list.

    Commas separate members and parentheses delimit the list, so any value
    containing them (or leading/trailing space, which PostgREST strips) has to
    be double-quoted or it silently splits into the wrong filter.
    """
    text_value = "" if value is None else str(value)
    needs_quotes = (
        text_value == ""
        or text_value != text_value.strip()
        or any(ch in text_value for ch in ',()"\\')
    )
    if not needs_quotes:
        return text_value
    escaped = text_value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _in_params(in_: Optional[dict]) -> dict:
    return {
        column: "in.(" + ",".join(_quote_in_value(v) for v in values) + ")"
        for column, values in (in_ or {}).items()
    }


def _has_empty_in_list(in_: Optional[dict]) -> bool:
    """True when any ``in_`` list is empty.

    ``col=in.()`` is a syntax error in PostgREST, but the intent — "match
    nothing" — is well defined, so callers short-circuit to an empty result.
    """
    return any(not list(values) for values in (in_ or {}).values())


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
    in_: Optional[dict] = None,
    neq: Optional[dict] = None,
    limit: Optional[int] = None,
    order: Optional[str] = None,
) -> list[dict[str, Any]]:
    """SELECT rows. Returns [] when nothing matches or REST not configured.

    ``order`` is passed to PostgREST verbatim, e.g. "created_at.desc".
    ``in_`` maps ``{"id": [1, 2]}`` to ``?id=in.(1,2)`` — the REST spelling of
    SQL's ``id = ANY(...)``. ``neq`` maps ``{"status": "draft"}`` to
    ``?status=neq.draft``.
    """
    if not is_configured():
        return []
    if _has_empty_in_list(in_):
        return []
    params: dict[str, Any] = {
        "select": columns,
        **_eq_params(eq),
        **_in_params(in_),
        **{k: f"neq.{v}" for k, v in (neq or {}).items()},
    }
    if limit is not None:
        params["limit"] = limit
    if order:
        params["order"] = order
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
