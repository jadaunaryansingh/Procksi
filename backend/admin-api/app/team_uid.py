"""
Canonical team-UID resolver for admin-api (supabase-py client).

Rule for all new code: resolve any team identifier to a `teams_validation.uid`
once, then pass ONLY the uid downstream. A team number is display-only and is
reassigned by the renumber tools — never use it for identity or lookup.
"""
from __future__ import annotations

import re
import time

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# tiny process-local cache: identifier -> (uid_or_None, expires_at)
_CACHE: dict[str, tuple[str | None, float]] = {}
_TTL = 30.0


def is_uuid(v) -> bool:
    return bool(v) and bool(_UUID_RE.match(str(v).strip()))


def resolve_team_uid(client, identifier) -> str | None:
    """uuid / teams_validation.id slug / legacy public.teams.id int -> canonical uid.
    Returns None when it cannot be resolved (never a guessed number)."""
    if identifier is None:
        return None
    s = str(identifier).strip()
    if not s:
        return None

    hit = _CACHE.get(s)
    if hit and hit[1] > time.monotonic():
        return hit[0]

    uid: str | None = None
    try:
        if is_uuid(s):
            r = client.table("teams_validation").select("uid").eq("uid", s).limit(1).execute()
            uid = s if r.data else None
        else:
            r = client.table("teams_validation").select("uid").eq("id", s).limit(1).execute()
            if r.data:
                uid = r.data[0]["uid"]
            elif re.fullmatch(r"-?\d+", s):
                r = client.table("team_uid_map").select("uid").eq("old_int_id", int(s)).limit(1).execute()
                if r.data:
                    uid = r.data[0]["uid"]
    except Exception:
        uid = None

    _CACHE[s] = (uid, time.monotonic() + _TTL)
    return uid


def team_by_uid(client, uid: str) -> dict | None:
    if not uid:
        return None
    r = client.table("teams_validation").select("*").eq("uid", uid).limit(1).execute()
    return r.data[0] if r.data else None


def members_for_team(client, uid: str) -> list[dict]:
    """Canonical roster from team_memberships (not the teams_validation.members jsonb,
    not the legacy team_members table)."""
    if not uid:
        return []
    r = (
        client.table("team_memberships")
        .select("student_roll, role, joined_at, semester_id")
        .eq("team_uid", uid)
        .order("role")
        .execute()
    )
    return r.data or []
