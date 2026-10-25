"""Pure logic for the deadline reminder scheduler.

Deliberately free of any third-party imports (no supabase, no dotenv) so it can
be unit-tested without credentials or network. All I/O lives in
``app.deadline_scheduler``.

Timezone note: deadlines are authored by admins in IST and stored naive (the
admin portal writes ``<date>T23:59:59``). ``app/api/student_portal.py`` reads
them back by stripping any timezone suffix and relabelling as IST, so the
countdown a student sees is computed in IST. This module uses the same
convention on purpose — if the two ever diverge, students get reminders on a
different day from the one their portal shows.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence

IST = timezone(timedelta(hours=5, minutes=30))

# Notify this many days ahead of a deadline, plus on the day itself.
DEFAULT_REMINDER_DAYS = (3, 1, 0)

# Human labels for the deadline `type` keys the admin portal writes. Mirrors
# DEADLINE_LABELS in apps/student/src/lib/reminders.js so the notification and
# the portal call the same deadline by the same name.
DEADLINE_LABELS = {
    "team": "Team Formation",
    "teamFormation": "Team Formation",
    "proposal": "Proposal Submission",
    "proposalUpload": "Proposal Submission",
    "evaluation": "Mid-Term Evaluation",
    "midTerm": "Mid-Term Evaluation",
    "finalEvaluation": "Final Evaluation",
}

# Trailing UTC designators to drop before relabelling as IST.
_UTC_SUFFIXES = ("Z", "z", "+00:00", "+0000", "-00:00", "-0000")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# fromisoformat only accepts 3- or 6-digit fractional seconds before 3.11.
_FRACTION = re.compile(r"\.(\d+)")


def parse_deadline(value: Any) -> Optional[datetime]:
    """Parse any deadline representation this codebase produces into IST.

    Handles the admin portal's naive ``2026-04-01T23:59:59``, the browser's
    ``new Date(...).toISOString()`` output ``2026-05-15T18:30:00.000Z``,
    PostgREST's ``+00:00`` rendering, a bare ``2026-04-01`` (treated as the end
    of that day — deadlines are "last day to submit"), and a space separator.

    Returns None for anything unparseable; a bad row must never abort the run.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=IST)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, 23, 59, 59, tzinfo=IST)
    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    # A bare date means the end of that day, not midnight at its start.
    if _DATE_ONLY.match(raw):
        raw = f"{raw}T23:59:59"

    # Drop an explicit UTC marker, then any other offset, and treat the wall
    # clock as IST — matching how student_portal.py reads the same column.
    for suffix in _UTC_SUFFIXES:
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break
    else:
        # Only split on an offset sign that follows a time component.
        if "T" in raw or " " in raw:
            head, sep, tail = raw.rpartition("+")
            if sep and ":" in head:
                raw = head

    raw = raw.replace(" ", "T", 1) if " " in raw and "T" not in raw else raw

    # Normalise fractional seconds to 6 digits for older fromisoformat.
    match = _FRACTION.search(raw)
    if match:
        raw = raw[: match.start()] + "." + match.group(1)[:6].ljust(6, "0") + raw[match.end():]

    try:
        parsed = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=IST)


def days_until(due: datetime, now: datetime) -> int:
    """Whole calendar days from ``now`` to ``due``, both evaluated in IST.

    Calendar days, not elapsed 24-hour blocks: a deadline at 09:00 tomorrow is
    "1 day away" even though it is only 23 hours out. The previous
    implementation used ``(due - now).days``, which reported that as 0 and fired
    the day-of reminder a day early.
    """
    return (due.astimezone(IST).date() - now.astimezone(IST).date()).days


def select_due_deadlines(
    rows: Iterable[dict],
    now: datetime,
    reminder_days: Sequence[int] = DEFAULT_REMINDER_DAYS,
) -> list:
    """Return ``[(row, days_remaining), ...]`` for rows landing on a reminder day.

    Rows with a missing or unparseable date are skipped rather than raising.
    Past-due deadlines are never re-announced.
    """
    targets = set(reminder_days)
    due = []
    for row in rows or []:
        parsed = parse_deadline(row.get("due_date") or row.get("deadline"))
        if parsed is None:
            continue
        remaining = days_until(parsed, now)
        if remaining in targets and remaining >= 0:
            due.append((row, remaining))
    return due


def notification_title(row: dict) -> str:
    """Display name for a deadline: explicit title, then name, then a label for
    its type key, then the raw type."""
    for key in ("title", "name"):
        value = (row or {}).get(key)
        if value and str(value).strip():
            return str(value).strip()
    type_key = str((row or {}).get("type") or "").strip()
    if not type_key:
        return "Deadline"
    return DEADLINE_LABELS.get(type_key, type_key)


def _urgency_phrase(days: int) -> str:
    if days <= 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def build_notification_rows(
    row: dict,
    days: int,
    student_emails: Iterable[str],
    mentor_emails: Iterable[str],
) -> list:
    """Build one notification row per recipient.

    Every row carries ``recipient_email``: ``/api/student/notifications`` filters
    on ``recipient_email=eq.<email>``, so a row without it is invisible to the
    student no matter what else it contains.

    ``metadata`` carries the machine-readable link back to the deadline. The
    notifications table has no foreign key to ``deadlines`` — it is a shared bus
    written by four unrelated producers (communication, workflow, allocation,
    mentor_allocation), so a deadline_id column would be null for most rows —
    and it is not defined by any migration or model in this repo, only in the
    live database. The ``metadata`` jsonb column already exists for exactly this
    purpose. Without it the student portal has to identify reminders by parsing
    the title, which breaks the moment anyone rewords one.

    The title keeps encoding the deadline name regardless, because rows written
    before this have no metadata and the portal still has to match those.
    """
    title = notification_title(row)
    when = _urgency_phrase(days)

    due = parse_deadline(row.get("due_date") or row.get("deadline"))
    on_date = f" ({due.strftime('%d %b %Y')})" if due else ""
    message = f"The deadline for {title} is {when}{on_date}."

    deadline_type = row.get("type")
    metadata = {
        "deadline_id": row.get("id"),
        "deadline_type": str(deadline_type) if deadline_type else None,
        "deadline_label": title,
        "days_remaining": days,
    }

    notifications = []
    for role, emails in (("student", student_emails), ("mentor", mentor_emails)):
        for email in emails or []:
            clean = str(email or "").strip()
            if not clean or "@" not in clean:
                continue
            notifications.append(
                {
                    "recipient_email": clean,
                    "recipient_role": role,
                    # Matches what other workflow rows already use; ours were the
                    # only ones leaving this null.
                    "audience": "all",
                    "title": f"Upcoming Deadline: {title}",
                    "message": message,
                    "type": "workflow",
                    "read": False,
                    "metadata": dict(metadata),
                }
            )
    return notifications
