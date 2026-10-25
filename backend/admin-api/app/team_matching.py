"""Resolve a team id to its row(s) in `teams_validation`.

`teams_validation.id` is a free-text primary key and the same team is referred to
as TEAM-3, Team 3, SEM-2026-T3 or plain 3 depending on which part of the system
is asking. Plain string equality therefore missed often, and the old fallback
turned a miss into "every team" — broadcasting team-scoped notifications and
emails to the whole platform.

Matching runs in tiers, most precise first, and a miss resolves to *nothing*:

  1. exact    — string equality on id / team_id / teamId (previous behaviour)
  2. normalized — case- and separator-insensitive equality
  3. numeric  — same trailing team number (TEAM-3 == 3 == SEM-2026-T3)

Tiers 2 and 3 only accept an unambiguous single match; two teams reducing to the
same value is reported as ambiguous rather than guessed at. Callers are expected
to log anything that is not a match so misses are visible instead of silent.

Dependency-free so it can be unit tested without credentials or network.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

MATCH_EXACT = "exact"
MATCH_NORMALIZED = "normalized"
MATCH_NUMERIC = "numeric"
MATCH_NONE = "no-match"
MATCH_AMBIGUOUS = "ambiguous"

# Keys a team id can live under, in precedence order.
_ID_KEYS = ("id", "team_id", "teamId")

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_team_key(value: Any) -> str:
    """Lowercase and strip separators: 'TEAM - 3' and 'team_3' both -> 'team3'."""
    return _NON_ALNUM.sub("", _clean(value).lower())


def team_number(value: Any) -> Optional[int]:
    """Extract the team's number, mirroring `extract_numeric_id` in student-api.

    TEAM-3 -> 3, SEM-2026-T1 -> 1, T7 -> 7, Team 007 -> 7, 3 -> 3.
    Returns None when there is no number to extract.
    """
    text = _clean(value)
    if not text:
        return None

    # '-T12' / 'T12' — the team marker wins over any earlier number (a semester
    # prefix like SEM-2026-T1 must resolve to 1, not 2026).
    match = re.search(r"(?:^|[^a-z0-9])t(\d+)\s*$", text, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # Trailing digits after a separator: 'TEAM-3', 'Team 3', 'team_3'.
    match = re.search(r"[^0-9](\d+)\s*$", text)
    if match:
        return int(match.group(1))

    # A bare number.
    if text.isdigit():
        return int(text)

    # Anything else: fall back to the last run of digits.
    digits = re.findall(r"\d+", text)
    return int(digits[-1]) if digits else None


def _candidate_values(row: dict) -> list:
    return [row.get(key) for key in _ID_KEYS if _clean(row.get(key))]


def select_team_rows(rows: Iterable[dict], team_id: Any) -> tuple:
    """Return ``(matching_rows, how)`` for `team_id`.

    `how` is one of MATCH_EXACT / MATCH_NORMALIZED / MATCH_NUMERIC /
    MATCH_AMBIGUOUS / MATCH_NONE. Anything other than a match returns an empty
    list — never every row.
    """
    all_rows = [r for r in (rows or []) if isinstance(r, dict)]
    wanted = _clean(team_id)
    if not wanted or not all_rows:
        return [], MATCH_NONE

    # 1. Exact — trusted as-is, including duplicates.
    exact = [r for r in all_rows if any(_clean(v) == wanted for v in _candidate_values(r))]
    if exact:
        return exact, MATCH_EXACT

    # 2. Normalized — case and separators ignored.
    wanted_key = normalize_team_key(wanted)
    if wanted_key:
        normalized = [
            r for r in all_rows
            if any(normalize_team_key(v) == wanted_key for v in _candidate_values(r))
        ]
        if len(normalized) == 1:
            return normalized, MATCH_NORMALIZED
        if len(normalized) > 1:
            return [], MATCH_AMBIGUOUS

    # 3. Numeric — TEAM-3 / 3 / SEM-2026-T3 all reduce to 3.
    wanted_number = team_number(wanted)
    if wanted_number is not None:
        numeric = [
            r for r in all_rows
            if any(team_number(v) == wanted_number for v in _candidate_values(r))
        ]
        if len(numeric) == 1:
            return numeric, MATCH_NUMERIC
        if len(numeric) > 1:
            return [], MATCH_AMBIGUOUS

    return [], MATCH_NONE
