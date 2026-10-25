"""Minimal read-only Postgres access for the static checks.

Uses psycopg 3. ``prepare_threshold=None`` keeps it compatible with the Supabase
transaction pooler (pgbouncer) that the project's DATABASE_URL points at.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import unquote

import psycopg
from psycopg.rows import dict_row

_URL_RE = re.compile(
    r"^\w+(?:\+\w+)?://(?P<user>[^:@/]+):(?P<pw>.*)@(?P<host>[^:/@]+)(?::(?P<port>\d+))?/(?P<db>[^?]+)",
)


def _kwargs_from_url(dsn: str, *, decode: bool) -> dict[str, Any] | None:
    """Regex-split the URL ourselves so a password containing a raw ``%`` (which
    breaks strict URL parsing) still works. ``decode`` re-runs percent-decoding
    for the case where the password really was encoded."""
    m = _URL_RE.match(dsn)
    if not m:
        return None
    g = m.groupdict()
    pw = unquote(g["pw"]) if decode else g["pw"]
    out: dict[str, Any] = {
        "user": g["user"], "password": pw, "host": g["host"], "dbname": g["db"],
        "sslmode": "require",
    }
    if g.get("port"):
        out["port"] = int(g["port"])
    sm = re.search(r"[?&]sslmode=([^&]+)", dsn)
    if sm:
        out["sslmode"] = sm.group(1)
    return out


@contextmanager
def connect(dsn: str, timeout: float = 15.0) -> Iterator[psycopg.Connection]:
    common = dict(
        autocommit=True,
        prepare_threshold=None,
        connect_timeout=int(timeout),
        application_name="pms_security_audit",
    )
    attempts = [
        lambda: psycopg.connect(dsn, **common),
        lambda: psycopg.connect(**(_kwargs_from_url(dsn, decode=False) or {}), **common),
        lambda: psycopg.connect(**(_kwargs_from_url(dsn, decode=True) or {}), **common),
    ]
    conn = None
    last: Exception | None = None
    for attempt in attempts:
        try:
            conn = attempt()
            break
        except (psycopg.OperationalError, TypeError) as exc:
            last = exc
    if conn is None:
        raise last or RuntimeError("could not connect")
    try:
        # Defensive: this tool must never write.
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
        yield conn
    finally:
        conn.close()


def q(conn: psycopg.Connection, sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params if params else None)
        try:
            return list(cur.fetchall())
        except psycopg.ProgrammingError:
            return []


def q1(conn: psycopg.Connection, sql: str, params: tuple | list | None = None) -> dict[str, Any] | None:
    rows = q(conn, sql, params)
    return rows[0] if rows else None


def parse_pg_roles(text: str | None) -> list[str]:
    """`pg_policies.roles` renders as ``{anon,authenticated}`` — turn it into a list."""
    if not text:
        return []
    return [r.strip().strip('"') for r in text.strip("{}").split(",") if r.strip()]
