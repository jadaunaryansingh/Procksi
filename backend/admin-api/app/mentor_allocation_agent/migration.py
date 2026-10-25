"""
migration.py — schema for the Mentor Allocation Agent (idempotent).

Creates ``mentor_preferences`` and adds the allocation-tracking columns to
``teams_validation``. Already applied to the live DB; safe to re-run.

Run with any environment that has ``asyncpg`` (e.g. the student-api venv):

    MENTOR_ALLOC_DSN="postgresql://...:5432/postgres" \\
      python -m app.mentor_allocation_agent.migration

If MENTOR_ALLOC_DSN is unset it falls back to DATABASE_URL.
"""
from __future__ import annotations

import asyncio
import os

DDL = [
    """create table if not exists public.mentor_preferences (
        id           bigint generated always as identity primary key,
        team_id      text not null,
        mentor_id    text not null,
        mentor_name  text,
        rank         integer not null,
        match_score  numeric,
        status       text default 'pending',   -- pending | allotted | skipped_full | rejected
        semester_id  text,
        created_at   timestamptz default now(),
        unique (team_id, rank),
        unique (team_id, mentor_id)
    )""",
    "alter table public.teams_validation add column if not exists mentor_source text",
    "alter table public.teams_validation add column if not exists mentor_locked_by_admin boolean default false",
    "alter table public.teams_validation add column if not exists keywords text",
]


async def run(dsn: str) -> None:
    import asyncpg  # imported lazily so the package doesn't hard-depend on it
    conn = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        for sql in DDL:
            await conn.execute(sql)
            print("OK:", " ".join(sql.split())[:72])
    finally:
        await conn.close()


def main() -> None:
    dsn = os.getenv("MENTOR_ALLOC_DSN") or os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set MENTOR_ALLOC_DSN or DATABASE_URL to the Postgres connection string.")
    # SQLAlchemy-style driver prefixes aren't understood by asyncpg.connect
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")
    asyncio.run(run(dsn))


if __name__ == "__main__":
    main()
