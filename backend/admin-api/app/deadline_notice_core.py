"""Pure logic for the 'Deadline Updated' notices.

Deliberately free of third-party imports (no supabase, no dotenv) so it can be
unit-tested without credentials or network. All I/O lives in
``app.notification_agent``.

Why dedup exists here: the admin portal's ``updateDeadlines()`` re-upserts every
deadline row on every publish, and the generic upsert endpoint hands that whole
batch to the notification agent. Without a guard, editing one deadline
re-notified every student about every deadline, and publishing the same values
twice produced byte-identical duplicates. The key is
(recipient, title, message) — the message embeds the target date, so a real
change produces a different message and still goes out.
"""
from __future__ import annotations

from typing import Iterable

from app.deadline_scheduler_core import notification_title


def format_due_label(due_date) -> str:
    """'2026-08-06T06:30:00+00:00' -> '2026-08-06 at 06:30'.

    Anything too short to carry a time is returned as-is; a missing value is "".
    """
    if not due_date:
        return ""
    text = str(due_date).replace("T", " ")
    if len(text) < 16:
        return text
    parts = text.split(" ")
    if len(parts) < 2:
        return text
    return f"{parts[0]} at {parts[1][:5]}"


def build_deadline_update_rows(
    rows: Iterable[dict],
    student_emails: Iterable[str],
    mentor_emails: Iterable[str],
) -> list:
    """One notification per deadline row per recipient.

    ``metadata`` carries the same link the reminder scheduler writes, so the
    student portal can resolve which deadline a notice is about without parsing
    its title. Rows with no due date are skipped — there is nothing to announce.
    """
    students = list(student_emails or [])
    mentors = list(mentor_emails or [])
    notifications = []

    for row in rows or []:
        due_label = format_due_label(row.get("due_date"))
        if not due_label:
            continue

        label = notification_title(row)
        deadline_type = row.get("type")
        metadata = {
            "deadline_id": row.get("id"),
            "deadline_type": str(deadline_type) if deadline_type else None,
            "deadline_label": label,
        }
        message = f"The target deadline for '{label}' is set to {due_label}."

        for role, emails in (("student", students), ("mentor", mentors)):
            for email in emails:
                clean = str(email or "").strip()
                if not clean or "@" not in clean:
                    continue
                notifications.append(
                    {
                        "recipient_email": clean,
                        "recipient_role": role,
                        "audience": "all",
                        "title": f"Deadline Updated: {label}",
                        "message": message,
                        "type": "workflow",
                        "read": False,
                        "metadata": dict(metadata),
                    }
                )
    return notifications


def notice_key(row: dict) -> tuple:
    """Identity of a notice for dedup: who, what, and the exact wording."""
    return (
        (row or {}).get("recipient_email"),
        (row or {}).get("title"),
        (row or {}).get("message"),
    )


def drop_already_sent(candidates: Iterable[dict], existing_keys) -> list:
    """Remove notices the recipient already has verbatim.

    Same deadline re-published unchanged -> identical message -> suppressed.
    Date actually moved -> different message -> still delivered.
    """
    seen = set(existing_keys or ())
    fresh = []
    for row in candidates or []:
        key = notice_key(row)
        if key in seen:
            continue
        # Also guards against duplicates inside a single batch.
        seen.add(key)
        fresh.append(row)
    return fresh
