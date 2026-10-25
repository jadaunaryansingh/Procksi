"""
chat_report.py — the engine behind the student portal's /report command.

Two rules shape everything here.

FIRST: numbers are computed, never generated. Every count, percentage and
duration in the output is derived in Python from rows in the database. The
language model is used for exactly one thing — reading the team's conversation
and extracting the tasks people agreed to in prose ("@Aryan can you finish the
login page by Friday"). That extraction is judgement, so a model does it; the
arithmetic that follows is not, so it does not.

The reason is blunt: this report is shown to students in a system that feeds
their evaluation. A model asked to invent "4 tasks overdue" will do so
confidently, and the student has no way to tell. So the model only ever returns
task records that quote the message they came from, and the caller can check
every one of them against the thread.

SECOND: absent data is reported as absent. When the repository analyser has no
report for this team — which is currently true for 175 of 176 teams — the
GitHub sections say so. They do not fall back to zero, which reads as "you
wrote no code" rather than "we do not know".
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _config(name: str, default: str = "") -> str:
    """
    Read one setting, whichever way this backend holds its configuration.

    The four portals do not agree: student and mentor use a pydantic Settings
    object, admin and panel read the environment directly. This module is
    copied into all four, so it asks both and takes whichever answers.
    """
    try:
        from app.core.config import settings  # type: ignore
        value = getattr(settings, name, None)
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)

# Extraction is a structure-following job rather than a reasoning one, so the
# cheapest capable model is the right default. Overridable for deployments that
# point at NVIDIA NIM instead of OpenAI.
_OPENAI_MODEL = "gpt-4.1-mini"

# A team's whole project conversation is well within context, but a runaway
# thread should not be able to run up a bill or a latency spike.
_MAX_MESSAGES_TO_SCAN = 400

# PMSbot's identity in conversation_messages. 'bot' is a sender_role of its own
# so a report can never be mistaken for something a person typed, and the id is
# fixed so every portal renders the same author.
BOT_SENDER_ROLE = "bot"
BOT_SENDER_ID = "pmsbot"
BOT_DISPLAY_NAME = "PMSbot"


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic metrics
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _display_name(sender_id: str, members: List[dict]) -> str:
    needle = str(sender_id or "").strip().lower()
    for m in members:
        if str(m.get("email") or "").strip().lower() == needle:
            return m.get("name") or m.get("roll") or needle
    return needle or "unknown"


def _looks_like_question(body: str) -> bool:
    """A question is a message that asks something. '?' catches nearly all of
    them in practice; the phrase list catches the polite ones that do not."""
    text = str(body or "").strip().lower()
    if "?" in text:
        return True
    return any(text.startswith(p) for p in (
        "can you", "could you", "would you", "please confirm", "let me know",
        "any update", "when can", "who is", "what is",
    ))


def human_messages(messages: List[dict]) -> List[dict]:
    """
    Drop PMSbot's own posts.

    Reports are stored in the thread like any other message, so without this
    every report would be counted as team communication by the next one — and
    worse, the extractor would read its own task list back and re-report it as
    something the team agreed in chat.
    """
    return [m for m in (messages or [])
            if str(m.get("sender_role") or "").strip().lower() != BOT_SENDER_ROLE]


def compute_communication(messages: List[dict], members: List[dict]) -> Dict[str, Any]:
    """
    Section 2.4, entirely from `conversation_messages`.

    Response time is measured between consecutive messages by different people:
    the gap from a message to the first reply by somebody else. A thread that
    nobody answers contributes no response time — it contributes an unanswered
    message instead, which is the more useful signal.
    """
    ordered = sorted(
        [m for m in human_messages(messages) if m.get("created_at")],
        key=lambda m: _parse_ts(m.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
    )

    per_person: Dict[str, Dict[str, Any]] = {}
    response_gaps: List[float] = []
    unanswered: List[dict] = []
    open_questions: List[dict] = []

    for idx, msg in enumerate(ordered):
        sender = str(msg.get("sender_id") or "").strip().lower()
        name = _display_name(sender, members)
        entry = per_person.setdefault(name, {"messages_sent": 0, "questions_asked": 0, "replies_given": 0})
        entry["messages_sent"] += 1

        body = msg.get("body") or ""
        is_question = _looks_like_question(body)
        if is_question:
            entry["questions_asked"] += 1

        # The first later message from somebody else counts as the reply.
        reply = next(
            (r for r in ordered[idx + 1:]
             if str(r.get("sender_id") or "").strip().lower() != sender),
            None,
        )
        if reply is None:
            unanswered.append(msg)
            if is_question:
                open_questions.append(msg)
            continue

        sent_at, replied_at = _parse_ts(msg.get("created_at")), _parse_ts(reply.get("created_at"))
        if sent_at and replied_at and replied_at >= sent_at:
            response_gaps.append((replied_at - sent_at).total_seconds())

    avg_seconds = (sum(response_gaps) / len(response_gaps)) if response_gaps else None

    return {
        "messages_sent_total": len(ordered),
        "by_person": per_person,
        "unanswered_messages": len(unanswered),
        "pending_questions": [{
            "id": m.get("id"),
            "from": _display_name(str(m.get("sender_id") or ""), members),
            "asked_at": m.get("created_at"),
            "excerpt": (m.get("body") or "")[:160],
        } for m in open_questions[-5:]],
        "average_response_time_seconds": round(avg_seconds) if avg_seconds is not None else None,
        "average_response_time_human": _humanise_seconds(avg_seconds),
        "measured_replies": len(response_gaps),
    }


def _humanise_seconds(seconds: Optional[float]) -> Optional[str]:
    if seconds is None:
        return None
    if seconds < 90:
        return f"{int(seconds)}s"
    if seconds < 5400:
        return f"{round(seconds / 60)} min"
    if seconds < 172800:
        return f"{round(seconds / 3600, 1)} hours"
    return f"{round(seconds / 86400, 1)} days"


def summarise_tasks(tasks: List[dict], members: List[dict]) -> Dict[str, Any]:
    """
    Sections 2.2 (task half) and 2.3, computed from the extracted task list.

    Deliberately arithmetic over the model's output rather than more model
    output: once the tasks exist as records, counting them is not a judgement
    call and must not be treated as one.
    """
    now = datetime.now(timezone.utc)
    per_person: Dict[str, Dict[str, Any]] = {
        (m.get("name") or m.get("roll") or "unknown"): {
            "assigned": 0, "completed": 0, "open": 0, "overdue": 0, "high_priority_open": 0,
        }
        for m in members
    }
    unassigned = {"assigned": 0, "completed": 0, "open": 0, "overdue": 0, "high_priority_open": 0}

    completion_days: List[float] = []
    on_time = late = 0

    for task in tasks:
        who = task.get("assignee") or None
        bucket = per_person.get(who) if who in per_person else (unassigned if who is None else per_person.setdefault(who, {
            "assigned": 0, "completed": 0, "open": 0, "overdue": 0, "high_priority_open": 0,
        }))
        bucket["assigned"] += 1

        due = _parse_ts(task.get("due_date"))
        done_at = _parse_ts(task.get("completed_at"))
        is_done = str(task.get("status") or "").lower() in ("done", "completed", "complete")

        if is_done:
            bucket["completed"] += 1
            raised = _parse_ts(task.get("raised_at"))
            if raised and done_at and done_at >= raised:
                completion_days.append((done_at - raised).total_seconds() / 86400)
            if due and done_at:
                if done_at <= due:
                    on_time += 1
                else:
                    late += 1
        else:
            bucket["open"] += 1
            if str(task.get("priority") or "").lower() == "high":
                bucket["high_priority_open"] += 1
            if due and due < now:
                bucket["overdue"] += 1

    open_counts = {name: data["open"] for name, data in per_person.items()}
    busiest = max(open_counts, key=open_counts.get) if open_counts else None
    quietest = min(open_counts, key=open_counts.get) if open_counts else None
    spread = (max(open_counts.values()) - min(open_counts.values())) if open_counts else 0

    total_done = sum(b["completed"] for b in list(per_person.values()) + [unassigned])
    total_tasks = sum(b["assigned"] for b in list(per_person.values()) + [unassigned])

    return {
        "total": total_tasks,
        "completed": total_done,
        "open": total_tasks - total_done,
        "overdue": sum(b["overdue"] for b in list(per_person.values()) + [unassigned]),
        "by_person": per_person,
        "unassigned": unassigned,
        "average_completion_days": round(sum(completion_days) / len(completion_days), 1) if completion_days else None,
        "on_time_percentage": round(on_time * 100 / (on_time + late)) if (on_time + late) else None,
        "workload": {
            "most_loaded": busiest,
            "least_loaded": quietest,
            # Two open tasks apart is noise on a five-person student team;
            # three or more is worth a human looking at it.
            "imbalance": spread,
            "imbalanced": spread >= 3,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# LLM task extraction
# ─────────────────────────────────────────────────────────────────────────────

_EXTRACTION_SYSTEM = """You read a student project team's chat and extract the tasks they agreed to.

Return ONLY a JSON object of the form {"tasks": [...]}. Each task:
  title        short imperative description of the work
  assignee     the person the task was given to, exactly as named in the roster, or null
  raised_at    ISO timestamp of the message that created the task
  due_date     ISO date if one was stated or clearly implied, else null
  priority     "high" | "normal" — high only if urgency was stated
  status       "done" if a later message says it was finished, else "open"
  completed_at ISO timestamp of the message reporting completion, else null
  evidence     the exact sentence from the chat that this task came from
  message_id   id of the message the task came from

Rules:
- Extract only work that was actually asked for or committed to. Ideas, questions
  and discussion are not tasks.
- Never invent an assignee, a date or a status. If the chat does not say, use null.
- Every task MUST quote real text from the chat in `evidence`. If you cannot
  quote it, do not return it.
- Return {"tasks": []} if the conversation contains no tasks."""


def _get_client():
    """Mirrors ai_service._get_client: build only when a key is configured, so
    a portal runs normally with no AI configured at all."""
    nvidia = _config("NVIDIA_API_KEY")
    openai_key = _config("OPENAI_API_KEY")
    if not (nvidia or openai_key):
        return None, None
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("/report: openai package unavailable")
        return None, None

    if nvidia:
        base = _config("AI_BASE_URL", "https://integrate.api.nvidia.com/v1")
        return AsyncOpenAI(api_key=nvidia, base_url=base), _config("AI_MODEL", "meta/llama-3.1-8b-instruct")
    return AsyncOpenAI(api_key=openai_key), _OPENAI_MODEL


def _transcript(messages: List[dict], members: List[dict]) -> str:
    lines = []
    for m in human_messages(messages)[-_MAX_MESSAGES_TO_SCAN:]:
        who = _display_name(str(m.get("sender_id") or ""), members)
        role = m.get("sender_role") or "?"
        when = m.get("created_at") or ""
        body = re.sub(r"\s+", " ", str(m.get("body") or "")).strip()
        if body:
            lines.append(f"[id={m.get('id')}] [{when}] {who} ({role}): {body}")
    return "\n".join(lines)


async def extract_tasks(messages: List[dict], members: List[dict]) -> Dict[str, Any]:
    """
    @returns {"tasks": [...], "available": bool, "reason": str|None}

    `available` is False when no model is configured or the call failed. The
    caller reports that honestly rather than presenting an empty task list,
    which would read as "your team agreed no work".
    """
    client, model = _get_client()
    if client is None:
        return {"tasks": [], "available": False, "reason": "No AI model is configured for this deployment."}

    transcript = _transcript(messages, members)
    if not transcript.strip():
        return {"tasks": [], "available": True, "reason": None}

    roster = ", ".join(m.get("name") or m.get("roll") or "?" for m in members) or "(unknown)"

    try:
        response = await client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": _EXTRACTION_SYSTEM},
                {"role": "user", "content": f"Team roster: {roster}\n\nConversation:\n{transcript}"},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        tasks = parsed.get("tasks") if isinstance(parsed, dict) else None
        if not isinstance(tasks, list):
            return {"tasks": [], "available": False, "reason": "The model returned an unexpected shape."}

        # Drop anything that does not quote the thread. The prompt forbids
        # invention, but the guarantee has to be enforced here, not requested
        # there — an unquoted task is exactly the kind we must never show.
        bodies = " ".join(str(m.get("body") or "").lower() for m in human_messages(messages))
        kept = []
        for t in tasks:
            if not isinstance(t, dict):
                continue
            evidence = re.sub(r"\s+", " ", str(t.get("evidence") or "")).strip()
            if not evidence:
                continue
            probe = evidence.lower()[:40]
            if probe and probe not in bodies:
                logger.info("/report: dropped task with unverifiable evidence: %r", evidence[:80])
                continue
            kept.append({
                "title": str(t.get("title") or "").strip(),
                "assignee": (str(t.get("assignee")).strip() if t.get("assignee") else None),
                "raised_at": t.get("raised_at"),
                "due_date": t.get("due_date"),
                "priority": (str(t.get("priority") or "normal").lower()),
                "status": (str(t.get("status") or "open").lower()),
                "completed_at": t.get("completed_at"),
                "evidence": evidence,
                "message_id": t.get("message_id"),
            })
        return {"tasks": [t for t in kept if t["title"]], "available": True, "reason": None}

    except Exception as exc:
        logger.warning("/report: task extraction failed: %s", exc)
        return {"tasks": [], "available": False, "reason": "The analysis model could not be reached."}


# ─────────────────────────────────────────────────────────────────────────────
# Posting a report into the thread
# ─────────────────────────────────────────────────────────────────────────────

_NO_WEEKLY_REPORTS = (
    "No repository reports have been generated yet. Weekly reports come from "
    "the ProjectFlow analyser, which is not currently returning results."
)


def build_weekly_github(rows: List[dict], *, requested_by: str = "",
                        team_labels: Optional[Dict[str, str]] = None,
                        unavailable_reason: Optional[str] = None) -> Dict[str, Any]:
    """
    The Weekly GitHub payload, from `github_agent_analysis` rows.

    Every portal asks the same question of the same table and differs only in
    which teams it may ask about, so the row shape is built once here.

    `team_labels` maps a row's team reference to a human name. A mentor or
    student report covers one team and needs no labels; a panel's covers every
    team it evaluates, and without them the list is a column of dates.
    """
    weeks = []
    for r in (rows or []):
        ref = str(r.get("team_ref") or r.get("team_id") or "")
        weeks.append({
            "id": r.get("id"),
            "generated_at": r.get("created_at"),
            "commit_count_30d": r.get("commit_count_30d"),
            "repository_url": r.get("repository_url"),
            "team_label": (team_labels or {}).get(ref),
        })

    return {
        "command": "report",
        "option": "weekly-github",
        "step": "result",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": requested_by,
        "weeks_available": len(weeks),
        "weeks": weeks,
        # An empty list is reported as absence, never as "no activity". The
        # analyser has produced a report for 1 of 176 teams; a bare empty list
        # would read as an accusation.
        "unavailable_reason": None if weeks else (unavailable_reason or _NO_WEEKLY_REPORTS),
    }


def render_report_text(payload: Dict[str, Any]) -> str:
    """
    Plain-text rendering of a report, stored in conversation_messages.body.

    The structured payload goes in `metadata` and the portals render it as a
    card, but `body` is not a placeholder: it is what a notification, an export,
    a database query, or a client that does not know about reports will show. It
    has to stand on its own.
    """
    option = str(payload.get("option") or "")
    lines: List[str] = []

    if option == "weekly-github":
        weeks = payload.get("weeks") or []
        lines.append("Weekly GitHub report")
        if not weeks:
            lines.append("")
            lines.append(str(payload.get("unavailable_reason")
                             or "No repository reports are available."))
        else:
            lines.append("")
            lines.append(f"{len(weeks)} report{'' if len(weeks) == 1 else 's'} available:")
            for w in weeks[:10]:
                when = str(w.get("generated_at") or "")[:10]
                commits = w.get("commit_count_30d")
                label = f"{w.get('team_label')} · " if w.get("team_label") else ""
                lines.append(f"  • {label}{when} — "
                             f"{commits if commits is not None else '—'} commits in 30 days")
        return "\n".join(lines)

    health = payload.get("health") or {}
    tasks = payload.get("tasks") or []
    workload = payload.get("workload") or {}
    communication = payload.get("communication") or {}
    extraction = payload.get("extraction") or {}
    github = payload.get("github") or {}

    # "team-analysis" for three portals, "thread-analysis" for the panel, whose
    # report covers its own conversations rather than a team's.
    lines.append((option.replace("-", " ").strip().capitalize()) or "Report")
    lines.append("")
    lines.append("Overall health")
    lines.append(f"  Tasks: {health.get('tasks_completed', 0)}/{health.get('tasks_total', 0)} complete"
                 f", {health.get('tasks_overdue', 0)} overdue")
    lines.append(f"  Milestones: {health.get('milestones_completed', 0)}/{health.get('milestones_total', 0)} complete"
                 f", {health.get('milestones_overdue', 0)} overdue")

    lines.append("")
    lines.append("Tasks agreed in chat")
    if not extraction.get("available"):
        lines.append(f"  Not available: {extraction.get('reason') or 'unknown reason'}")
    elif not tasks:
        lines.append(f"  None found in {extraction.get('messages_scanned', 0)} messages.")
    else:
        for t in tasks:
            due = f", due {t.get('due_date')}" if t.get("due_date") else ""
            who = t.get("assignee") or "unassigned"
            lines.append(f"  • {t.get('title')} — {who}{due} [{t.get('status')}]")

    if tasks and workload:
        lines.append("")
        lines.append("Workload")
        lines.append(f"  Most loaded: {workload.get('most_loaded') or '—'}")
        lines.append(f"  Least loaded: {workload.get('least_loaded') or '—'}")
        if workload.get("imbalanced"):
            lines.append(f"  {workload.get('most_loaded')} has {workload.get('imbalance')} more open "
                         f"tasks than {workload.get('least_loaded')}.")

    lines.append("")
    lines.append("Communication")
    lines.append(f"  Messages: {communication.get('messages_sent_total', 0)}")
    lines.append(f"  Average reply time: {communication.get('average_response_time_human') or '—'}")
    lines.append(f"  Unanswered: {communication.get('unanswered_messages', 0)}")

    lines.append("")
    lines.append("Repository")
    if not github.get("available"):
        lines.append(f"  Not available: {github.get('reason') or 'unknown reason'}")
    else:
        lines.append(f"  Total commits: {github.get('total_commits') if github.get('total_commits') is not None else '—'}")
        lines.append(f"  Contributors: {len(github.get('contributors') or [])}")

    lines.append("")
    lines.append("Every figure above is counted from the database. Tasks are read from "
                 "the chat by a language model and each one quotes the message it came from.")
    return "\n".join(lines)


def build_bot_message(conversation_id: int, payload: Dict[str, Any],
                      requested_by: Optional[str] = None) -> Dict[str, Any]:
    """
    The conversation_messages row for a report.

    `requested_by` is seeded into read_by so the person who ran the command does
    not come back to an unread badge for output they just watched appear. Nobody
    else is seeded: for them this is a new message, and it should say so.
    """
    seed = [BOT_SENDER_ID]
    if requested_by and str(requested_by).strip():
        seed.append(str(requested_by).strip())

    return {
        "conversation_id": int(conversation_id),
        "sender_role": BOT_SENDER_ROLE,
        "sender_id": BOT_SENDER_ID,
        "body": render_report_text(payload),
        "read_by": seed,
        "metadata": {"kind": "report", "report": payload},
    }
