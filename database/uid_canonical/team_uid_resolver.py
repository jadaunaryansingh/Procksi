"""
Canonical team-UID resolver — drop a copy into each backend service
(admin-api / panel-api / mentor-api / student-api / backend-app) under app/.

Rule for all new code: resolve any team identifier to a `teams_validation.uid`
(uuid) exactly once at the edge, then pass ONLY the uid downstream. Never parse a
team number out of a string for identity again — a number is display only.

`client` is a supabase-py client (service role).
"""
from __future__ import annotations
import re
from functools import lru_cache

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def is_uuid(v) -> bool:
    return bool(v) and bool(_UUID_RE.match(str(v).strip()))


def resolve_team_uid(client, identifier) -> str | None:
    """Return the canonical teams_validation.uid for any of:
      * a uuid (returned as-is once existence is confirmed)
      * a teams_validation.id text slug  (e.g. '<sem>-T3')
      * a legacy integer public.teams.id  (via public.team_uid_map)
      * a bare-number string of a legacy id
    Returns None if it cannot be resolved (caller decides whether that's fatal).
    """
    if identifier is None:
        return None
    s = str(identifier).strip()
    if not s:
        return None

    if is_uuid(s):
        r = client.table("teams_validation").select("uid").eq("uid", s).limit(1).execute()
        return s if r.data else None

    # text slug
    r = client.table("teams_validation").select("uid").eq("id", s).limit(1).execute()
    if r.data:
        return r.data[0]["uid"]

    # legacy integer id -> crosswalk
    if re.fullmatch(r"-?\d+", s):
        r = client.table("team_uid_map").select("uid").eq("old_int_id", int(s)).limit(1).execute()
        if r.data:
            return r.data[0]["uid"]

    return None


def team_by_uid(client, uid: str) -> dict | None:
    if not uid:
        return None
    r = client.table("teams_validation").select("*").eq("uid", uid).limit(1).execute()
    return r.data[0] if r.data else None


def team_display_number(team_row: dict) -> int | None:
    """Human-facing team number. NOT an identifier. Safe to show, never to join on."""
    if not team_row:
        return None
    n = team_row.get("team_number")
    if n is not None:
        return int(n)
    m = re.search(r"Team\s*(\d+)", str(team_row.get("title") or ""))
    return int(m.group(1)) if m else None


def members_for_team(client, uid: str) -> list[dict]:
    """Canonical roster from team_memberships (NOT teams_validation.members jsonb,
    NOT the legacy team_members table)."""
    if not uid:
        return []
    r = (client.table("team_memberships")
         .select("student_roll, role, joined_at, semester_id")
         .eq("team_uid", uid).order("role").execute())
    return r.data or []
