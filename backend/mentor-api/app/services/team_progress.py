"""Derive a team's progress snapshot from records the portal already stores.

Why this exists: ``GET /api/mentor/teams/{id}/progress`` used to return a
hardcoded ``{"week": 0, "risk": "No Data", "progress": 0}`` for every team, so
the entire Progress Intelligence page rendered empty regardless of what the team
had actually done. Nothing was ever computed.

There is no dedicated "progress" table, and there is no weekly progress-report
feed — so progress here is *derived* from the gates a team genuinely passes
through, each of which is already recorded:

  * team formation      -> teams_validation (members present)
  * proposal            -> proposals (status)
  * each presentation   -> presentation_cycles + presentation_submissions
                           + presentation_evaluations

Pure logic: no DB, no FastAPI, no clock of its own (``now`` is injected), so the
whole thing is unit-testable without credentials or a reachable database.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

COMPLETED = "Completed"
IN_PROGRESS = "In Progress"
PENDING = "Pending"

# Proposal states the admin portal writes, lowercased.
_APPROVED_PROPOSAL = {"approved", "accepted", "finalized"}
_REJECTED_PROPOSAL = {"rejected", "declined"}

# A repository with no commits in this many days is called out as a blocker.
STALE_REPO_DAYS = 30

# Risk thresholds, in percentage points behind the expected pace.
_AT_RISK_DEFICIT = 25
_ATTENTION_DEFICIT = 10

# Upper bound on timeline buckets so a long semester stays readable.
_MAX_TIMELINE_POINTS = 10


def _parse_dt(value: Any) -> Optional[datetime]:
    """Parse a PostgREST timestamp into an aware UTC datetime, or None.

    Accepts the ``...Z`` suffix that ``datetime.fromisoformat`` rejects before
    Python 3.11, and treats a naive result as UTC so comparisons never raise.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            # Date-only values are common on deadline columns.
            try:
                parsed = datetime.strptime(text[:10], "%Y-%m-%d")
            except ValueError:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _members(validation: Optional[dict]) -> List[Any]:
    """Team members from a teams_validation row (the column is JSON or text)."""
    raw = (validation or {}).get("members")
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _cycle_label(cycle: dict, index: int) -> str:
    return (
        (cycle.get("title") or "").strip()
        or (cycle.get("type") or "").strip().title()
        or f"Presentation {index + 1}"
    )


def _milestone(name: str, pct: int, status: str, due: Optional[datetime],
               done_at: Optional[datetime]) -> Dict[str, Any]:
    return {
        "name": name,
        "pct": pct,
        "status": status,
        "due": due.isoformat() if due else None,
        "completedAt": done_at.isoformat() if done_at else None,
        "_due": due,
        "_done_at": done_at,
    }


def build_milestones(
    *,
    validation: Optional[dict],
    proposal: Optional[dict],
    cycles: Iterable[dict],
    evaluations: Iterable[dict],
    submissions: Iterable[dict],
) -> List[Dict[str, Any]]:
    """The ordered gate list a team passes through, with per-gate completion."""
    milestones: List[Dict[str, Any]] = []

    formed = bool(_members(validation))
    milestones.append(_milestone(
        "Team Formation",
        100 if formed else 0,
        COMPLETED if formed else PENDING,
        None,
        _parse_dt((validation or {}).get("created_at")) if formed else None,
    ))

    status = str((proposal or {}).get("status") or "").strip().lower()
    submitted_at = _parse_dt(
        (proposal or {}).get("submitted_at") or (proposal or {}).get("submittedDate")
    )
    if proposal and status in _APPROVED_PROPOSAL:
        milestones.append(_milestone("Proposal", 100, COMPLETED, None, submitted_at))
    elif proposal and status in _REJECTED_PROPOSAL:
        # A rejected proposal still needs redoing, so it is not partial credit.
        milestones.append(_milestone("Proposal", 0, IN_PROGRESS, None, None))
    elif proposal:
        milestones.append(_milestone("Proposal", 50, IN_PROGRESS, None, None))
    else:
        milestones.append(_milestone("Proposal", 0, PENDING, None, None))

    evaluated_cycles = {
        str(e.get("cycle_id")): _parse_dt(e.get("evaluated_at"))
        for e in evaluations or []
    }
    submitted_cycles = {
        str(s.get("cycle_id")): _parse_dt(s.get("submitted_at"))
        for s in submissions or []
    }

    ordered = sorted(
        cycles or [],
        key=lambda c: (_parse_dt(c.get("deadline")) or _parse_dt(c.get("created_at"))
                       or datetime.max.replace(tzinfo=timezone.utc)),
    )
    for index, cycle in enumerate(ordered):
        cycle_id = str(cycle.get("id"))
        name = _cycle_label(cycle, index)
        due = _parse_dt(cycle.get("deadline"))
        if cycle_id in evaluated_cycles:
            milestones.append(_milestone(name, 100, COMPLETED, due, evaluated_cycles[cycle_id]))
        elif cycle_id in submitted_cycles:
            milestones.append(_milestone(name, 50, IN_PROGRESS, due, None))
        else:
            milestones.append(_milestone(name, 0, PENDING, due, None))

    return milestones


def overall_progress(milestones: List[Dict[str, Any]]) -> int:
    """Mean completion across the gates, 0-100."""
    if not milestones:
        return 0
    return round(sum(m["pct"] for m in milestones) / len(milestones))


def _timeline_anchor(cycles: Iterable[dict], milestones: List[Dict[str, Any]],
                     semester_start: Optional[datetime] = None) -> Optional[datetime]:
    """When this team's semester clock started.

    The earliest of everything that could mark a beginning — the semester
    itself, the first presentation cycle the admin opened, or the first thing
    the team actually completed. Without this fallback chain a team whose
    records carry no timestamps reports week 0, which reads like missing data
    rather than "nothing is dated yet".
    """
    candidates = [_parse_dt(c.get("created_at")) for c in cycles or []]
    candidates += [m["_done_at"] for m in milestones]
    candidates.append(semester_start)
    real = [c for c in candidates if c]
    return min(real) if real else None


def current_week(anchor: Optional[datetime], now: datetime) -> int:
    """1-based week index within the semester; 0 when there is no anchor."""
    if not anchor:
        return 0
    days = (now - anchor).days
    return max(1, days // 7 + 1)


def expected_progress(anchor: Optional[datetime], milestones: List[Dict[str, Any]],
                      now: datetime) -> Optional[int]:
    """Where a team pacing evenly would be by ``now``, or None if undated.

    Measured against the span from the semester anchor to the last gate
    deadline, which is the only schedule the data actually commits to.
    """
    due_dates = [m["_due"] for m in milestones if m["_due"]]
    if not anchor or not due_dates:
        return None
    end = max(due_dates)
    span = (end - anchor).total_seconds()
    if span <= 0:
        return 100
    elapsed = (now - anchor).total_seconds()
    return max(0, min(100, round(elapsed / span * 100)))


def assess_risk(progress: int, expected: Optional[int],
                overdue: List[str], has_data: bool) -> Dict[str, str]:
    """Risk band, as the label + Tailwind colour key the UI expects."""
    if not has_data:
        return {"risk": "No Data", "riskColor": "slate"}
    deficit = 0 if expected is None else expected - progress
    if overdue and deficit >= _AT_RISK_DEFICIT:
        return {"risk": "At Risk", "riskColor": "rose"}
    if overdue or deficit >= _ATTENTION_DEFICIT:
        return {"risk": "Needs Attention", "riskColor": "amber"}
    return {"risk": "On Track", "riskColor": "emerald"}


def build_timeline(milestones: List[Dict[str, Any]], anchor: Optional[datetime],
                   now: datetime) -> List[Dict[str, Any]]:
    """Cumulative progress per week, from real completion timestamps.

    Only gates with a recorded completion time contribute, so this is a record
    of what happened rather than an interpolation.
    """
    if not anchor or not milestones:
        return []
    total = len(milestones)
    current = current_week(anchor, now)
    if current <= 0:
        return []

    step = max(1, -(-current // _MAX_TIMELINE_POINTS))  # ceil division
    weeks = list(range(step, current + 1, step))
    if weeks and weeks[-1] != current:
        weeks.append(current)
    if not weeks:
        weeks = [current]

    # A gate can be complete without a recorded completion time (an approved
    # proposal with no submitted_at, say). We know it is done *now* but not
    # when, so it lands in the final bucket — otherwise the chart's last point
    # contradicts the headline percentage.
    undated_done = sum(
        m["pct"] for m in milestones
        if m["status"] == COMPLETED and not m["_done_at"]
    )

    points = []
    for index, week in enumerate(weeks):
        cutoff = anchor + timedelta(days=7 * week)
        earned = sum(
            m["pct"] for m in milestones
            if m["_done_at"] and m["_done_at"] <= cutoff
        )
        if index == len(weeks) - 1:
            earned += undated_done
        points.append({"week": f"W{week}", "progress": round(earned / total)})
    return points


def _github_notes(github: Optional[dict], now: datetime) -> tuple[List[str], List[str]]:
    """Repository facts worth surfacing, split into achievements and blockers."""
    achievements: List[str] = []
    blockers: List[str] = []
    if not github:
        blockers.append("No repository analysis on record.")
        return achievements, blockers

    quality = github.get("quality_score")
    if isinstance(quality, (int, float)) and quality > 0:
        achievements.append(f"Repository quality score {int(quality)}/100.")

    commits = github.get("commit_count_30d")
    if isinstance(commits, int) and commits > 0:
        achievements.append(f"{commits} commits in the last 30 days.")
    elif commits == 0:
        blockers.append("No commits recorded in the last 30 days.")

    last_commit = _parse_dt(github.get("last_commit_at"))
    if last_commit:
        idle_days = (now - last_commit).days
        if idle_days >= STALE_REPO_DAYS:
            blockers.append(f"Repository has been idle for {idle_days} days.")
    return achievements, blockers


def build_summary(progress: int, week: int, milestones: List[Dict[str, Any]],
                  overdue: List[str]) -> str:
    """A factual one-liner — every clause is backed by a counted record."""
    if not milestones:
        return "No progress data available for this team."
    done = sum(1 for m in milestones if m["status"] == COMPLETED)
    total = len(milestones)
    week_part = f"Week {week}: " if week else ""
    summary = f"{week_part}{done} of {total} milestones complete ({progress}%)."
    if overdue:
        summary += f" Overdue: {', '.join(overdue)}."
    else:
        next_up = next((m["name"] for m in milestones if m["status"] != COMPLETED), None)
        if next_up:
            summary += f" Next up: {next_up}."
    return summary


def compute_team_progress(
    *,
    validation: Optional[dict] = None,
    proposal: Optional[dict] = None,
    cycles: Optional[Iterable[dict]] = None,
    evaluations: Optional[Iterable[dict]] = None,
    submissions: Optional[Iterable[dict]] = None,
    github: Optional[dict] = None,
    semester_start: Optional[Any] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Full progress payload for one team, shaped for ProgressIntelligence.jsx."""
    now = now or datetime.now(timezone.utc)
    cycles = list(cycles or [])

    milestones = build_milestones(
        validation=validation,
        proposal=proposal,
        cycles=cycles,
        evaluations=evaluations or [],
        submissions=submissions or [],
    )
    progress = overall_progress(milestones)
    anchor = _timeline_anchor(cycles, milestones, _parse_dt(semester_start))
    week = current_week(anchor, now)
    expected = expected_progress(anchor, milestones, now)

    overdue = [
        m["name"] for m in milestones
        if m["status"] != COMPLETED and m["_due"] and m["_due"] < now
    ]

    achievements = [f"{m['name']} complete." for m in milestones if m["status"] == COMPLETED]
    blockers = [f"{name} is past its deadline." for name in overdue]
    repo_wins, repo_blocks = _github_notes(github, now)
    achievements += repo_wins
    blockers += repo_blocks

    has_data = bool(validation or proposal or cycles or github)
    risk = assess_risk(progress, expected, overdue, has_data)

    return {
        "week": week,
        "progress": progress,
        "expectedProgress": expected,
        "summary": build_summary(progress, week, milestones, overdue),
        "achievements": achievements,
        "blockers": blockers,
        "milestones": [
            {k: v for k, v in m.items() if not k.startswith("_")} for m in milestones
        ],
        "timeline": build_timeline(milestones, anchor, now),
        **risk,
    }
