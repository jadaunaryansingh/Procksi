"""Deadline reminder scheduler.

Emits `notifications` rows for deadlines coming up in DEFAULT_REMINDER_DAYS
(3 days out, 1 day out, and the day itself) so students and mentors get an
alert in the portal before a deadline passes.

Started as a background task from ``app.main`` on startup — see
``start_deadline_scheduler``. Also runnable by hand for a one-off sweep:

    python -m app.deadline_scheduler

All parsing/selection logic lives in ``app.deadline_scheduler_core`` and is unit
tested; this module is only I/O.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta

from app.deadline_scheduler_core import (
    IST,
    DEFAULT_REMINDER_DAYS,
    build_notification_rows,
    notification_title,
    select_due_deadlines,
)

logger = logging.getLogger("deadline_scheduler")

# How often the background loop sweeps for due deadlines. Reminders are
# day-granular and de-duplicated over a 20h window, so hourly is ample.
POLL_SECONDS = int(os.getenv("PMS_DEADLINE_POLL_SECONDS", str(60 * 60)))
ENABLED = os.getenv("PMS_DEADLINE_SCHEDULER_ENABLED", "1") != "0"

# Don't re-send the same deadline reminder inside this window.
DEDUP_HOURS = 20


def _client():
    """The shared service-role client from app.main.

    Imported lazily so this module can be imported (and its core tested) without
    booting the FastAPI app, and so app.main can import us without a cycle.
    """
    from app.main import service_client

    return service_client


def _active_semester_ids(client) -> list:
    res = client.table("semester_config").select("id").eq("is_active", True).execute()
    return [row["id"] for row in (res.data or []) if row.get("id")]


def _deadlines_for(client, semester_ids: list) -> list:
    res = (
        client.table("deadlines")
        .select("*")
        .in_("semester_id", semester_ids)
        .execute()
    )
    return res.data or []


def _student_emails_for_semester(client, semester_id) -> list:
    """Students in the deadline's own batch — a deadline for one semester must
    not page students from another."""
    if not semester_id:
        return []
    res = client.table("students").select("email").eq("semester_id", semester_id).execute()
    return [r["email"] for r in (res.data or []) if r.get("email")]


def _all_mentor_emails(client) -> list:
    """Mentors are not scoped by semester in this schema, so all of them are
    notified — matching the existing deadline email path in notification_agent."""
    res = client.table("mentors").select("email").execute()
    return [r["email"] for r in (res.data or []) if r.get("email")]


def _already_notified(client, title: str, since: datetime) -> set:
    """Recipients who already got this exact reminder inside the dedup window.

    Keyed on title + recipient_email: `audience` is a free-form segment label
    shared with unrelated producers, not a dedup key.
    """
    try:
        res = (
            client.table("notifications")
            .select("recipient_email")
            .eq("title", title)
            .gte("created_at", since.isoformat())
            .execute()
        )
        return {r["recipient_email"] for r in (res.data or []) if r.get("recipient_email")}
    except Exception as exc:
        # If the dedup probe fails, skip this deadline rather than risk spamming.
        logger.warning("Dedup lookup failed for %r, skipping: %s", title, exc)
        return None


def run_scheduler(now: datetime = None) -> int:
    """One sweep. Returns the number of notification rows inserted."""
    client = _client()
    now = now or datetime.now(IST)

    try:
        semester_ids = _active_semester_ids(client)
    except Exception as exc:
        logger.error("Could not fetch active semesters: %s", exc)
        return 0

    if not semester_ids:
        logger.info("No active semesters; nothing to do.")
        return 0

    try:
        deadlines = _deadlines_for(client, semester_ids)
    except Exception as exc:
        logger.error("Could not fetch deadlines: %s", exc)
        return 0

    due = select_due_deadlines(deadlines, now, DEFAULT_REMINDER_DAYS)
    if not due:
        logger.info("No deadlines land on a reminder day (%s).", DEFAULT_REMINDER_DAYS)
        return 0

    try:
        mentor_emails = _all_mentor_emails(client)
    except Exception as exc:
        logger.warning("Could not fetch mentor emails: %s", exc)
        mentor_emails = []

    cutoff = now - timedelta(hours=DEDUP_HOURS)
    students_by_semester = {}
    pending = []

    for row, days in due:
        semester_id = row.get("semester_id")
        if semester_id not in students_by_semester:
            try:
                students_by_semester[semester_id] = _student_emails_for_semester(client, semester_id)
            except Exception as exc:
                logger.warning("Could not fetch students for semester %s: %s", semester_id, exc)
                students_by_semester[semester_id] = []

        candidates = build_notification_rows(
            row, days, students_by_semester[semester_id], mentor_emails
        )
        if not candidates:
            continue

        seen = _already_notified(client, candidates[0]["title"], cutoff)
        if seen is None:
            continue
        fresh = [n for n in candidates if n["recipient_email"] not in seen]
        if fresh:
            logger.info(
                "Deadline %r due in %s day(s): notifying %d recipient(s).",
                notification_title(row), days, len(fresh),
            )
            pending.extend(fresh)

    if not pending:
        logger.info("All due deadline reminders were already sent.")
        return 0

    try:
        client.table("notifications").insert(pending).execute()
    except Exception as exc:
        logger.error("Failed to insert %d notifications: %s", len(pending), exc)
        return 0

    logger.info("Inserted %d deadline notification(s).", len(pending))
    return len(pending)


async def start_deadline_scheduler() -> None:
    """Background loop. Runs each sweep off the event loop because the Supabase
    client is synchronous and would otherwise block every request handler."""
    if not ENABLED:
        logger.info("Deadline scheduler disabled via PMS_DEADLINE_SCHEDULER_ENABLED=0.")
        return

    logger.info("Deadline scheduler started (every %ss).", POLL_SECONDS)
    while True:
        try:
            await asyncio.to_thread(run_scheduler)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A bad sweep must never kill the loop.
            logger.exception("Deadline scheduler tick failed")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_scheduler()
