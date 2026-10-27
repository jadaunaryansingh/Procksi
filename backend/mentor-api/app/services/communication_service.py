"""The Communication Agent.

A deterministic orchestration layer (no LLM) that turns a *named audience segment*
+ a *template* into actual emails: resolve recipients from the DB, render the
template with a context, send via the SMTP layer (``email_service.send_mail``),
and log every dispatch to ``email_logs``.

Design mirrors the Validation Agent: the **pure** bits (template rendering,
recipient de-duplication, message preparation, the template/segment registries)
have no DB/SMTP dependency and are unit-tested directly; the **async** bits
(audience resolution, sending, logging) are thin wrappers. The mailer is injected
so the orchestration can be tested without a live SMTP server.
"""
from __future__ import annotations

import string
import uuid
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

# Heavy deps (SQLAlchemy, ORM models, the SMTP mailer) are imported *lazily* inside
# the async methods that need them, so the pure helpers and the injected-mailer
# send() path stay importable/testable without the full backend stack installed.
if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

# A mailer takes (subject, recipients, body) and sends. Injectable for tests.
Mailer = Callable[..., Awaitable[None]]
Recipient = dict[str, str]  # {"name": ..., "email": ...}


# --------------------------------------------------------------------------- #
# Registries
# --------------------------------------------------------------------------- #
# Audience segments the agent knows how to resolve. ``requires_team`` segments
# need a team_id parameter.
SEGMENTS: dict[str, dict[str, Any]] = {
    "all_students": {"label": "All Enrolled Students", "requires_team": False},
    "team_leaders": {"label": "Team Leaders Only", "requires_team": False},
    "unassigned_students": {"label": "Unallocated Students (no team)", "requires_team": False},
    "incomplete_teams": {"label": "Incomplete Teams (< 3 members)", "requires_team": False},
    "teams_without_mentors": {"label": "Teams without a Mentor", "requires_team": False},
    "mentors": {"label": "All Faculty Mentors", "requires_team": False},
    "specific_team": {"label": "A Specific Team", "requires_team": True},
}

# Canonical lifecycle templates from the PRD. Bodies use {placeholders} filled
# from the request context. ``default_segment`` is the audience the trigger
# normally targets; the admin can override it.
TEMPLATES: dict[str, dict[str, Any]] = {
    "kickoff": {
        "name": "Semester Kickoff",
        "default_segment": "all_students",
        "subject": "Welcome to the Project Semester",
        "body": (
            "Dear Student,\n\n"
            "The project semester has officially begun. Over the coming weeks you will "
            "form teams, select a problem statement, and be paired with a faculty mentor.\n\n"
            "Please watch your inbox and the student portal for the next steps.\n\n"
            "Regards,\nProcksi Admin"
        ),
        "params": [],
    },
    "team_formation": {
        "name": "Team Formation Call",
        "default_segment": "all_students",
        "subject": "Action Required: Form Your Project Team",
        "body": (
            "Dear Student,\n\n"
            "It's time to form your project teams (maximum 3 members per team). "
            "One member should log in to the portal and add the other members' details.\n\n"
            "Please complete team formation before {deadline}.\n\n"
            "Regards,\nProcksi Admin"
        ),
        "params": ["deadline"],
    },
    "problem_statements": {
        "name": "Problem Statements Released",
        "default_segment": "all_students",
        "subject": "Problem Statements Are Now Available",
        "body": (
            "Dear Student,\n\n"
            "The department's problem statements have been released. Please review them "
            "with your team and submit your selection (with a short description) on the "
            "portal before {deadline}.\n\n"
            "Teams submitting a custom proposal should upload it in the same step.\n\n"
            "Regards,\nProcksi Admin"
        ),
        "params": ["deadline"],
    },
    "team_add_request": {
        "name": "Request to Add a Member",
        "default_segment": "specific_team",
        "subject": "Admin Request: Add a Member to Your Team",
        "body": (
            "Dear Team {team_name},\n\n"
            "The admin requests to add {student_name} to your team. "
            "If you agree, please log in to the portal and add this student's details "
            "to finalize your team.\n\n"
            "Regards,\nProcksi Admin"
        ),
        "params": ["team_name", "student_name"],
    },
    "proposal_approved": {
        "name": "Custom Proposal Approved",
        "default_segment": "specific_team",
        "subject": "Proposal Approved – {team_name}",
        "body": (
            "Dear Team {team_name},\n\n"
            "Your custom project proposal has been approved. Please log in to the portal "
            "and enter your final project description to proceed.\n\n"
            "Regards,\nProcksi Admin"
        ),
        "params": ["team_name"],
    },
    "proposal_rejected": {
        "name": "Custom Proposal Rejected",
        "default_segment": "specific_team",
        "subject": "Proposal Update – {team_name}",
        "body": (
            "Dear Team {team_name},\n\n"
            "Your custom project proposal was not approved this time. Please select a "
            "problem statement from the department's standard list on the portal before "
            "the deadline.\n\n"
            "Regards,\nProcksi Admin"
        ),
        "params": ["team_name"],
    },
    "mentor_onboarding": {
        "name": "Faculty Mentor Registration",
        "default_segment": "mentors",
        "subject": "Action Required: Register on the Mentor Portal",
        "body": (
            "Dear Faculty,\n\n"
            "We invite you to join as a Mentor. Please register on the "
            "Mentor Portal and select your domains for mentoring from the listed project "
            "domains. Your guidance is invaluable to our students' success.\n\n"
            "Regards,\nProcksi Admin"
        ),
        "params": [],
    },
}


# --------------------------------------------------------------------------- #
# Pure helpers (no DB / no SMTP — unit-tested directly)
# --------------------------------------------------------------------------- #
class _SafeDict(dict):
    """Leaves unknown {placeholders} intact instead of raising/blanking them."""

    def __missing__(self, key: str) -> str:  # pragma: no cover - trivial
        return "{" + key + "}"


def render_template(text: Optional[str], context: Optional[dict] = None) -> str:
    """Substitute ``{placeholders}`` from ``context``; unknown ones are left visible."""
    if not text:
        return ""
    try:
        return string.Formatter().vformat(text, (), _SafeDict(context or {}))
    except (ValueError, IndexError):
        # Malformed format string (e.g. a stray brace) — return as-is.
        return text


def dedupe_emails(recipients: list[Recipient]) -> list[str]:
    """Unique, order-preserving list of valid-looking emails."""
    seen: set[str] = set()
    out: list[str] = []
    for r in recipients or []:
        email = str(r.get("email", "")).strip()
        key = email.lower()
        if "@" not in email or key in seen:
            continue
        seen.add(key)
        out.append(email)
    return out


def prepare_message(
    *, subject: Optional[str], body: Optional[str],
    context: Optional[dict], recipients: list[Recipient],
) -> dict[str, Any]:
    """Render subject/body and collapse recipients to a clean email list."""
    ctx = context or {}
    return {
        "subject": render_template(subject, ctx),
        "body": render_template(body, ctx),
        "emails": dedupe_emails(recipients),
    }


def resolve_message_fields(
    *, template_code: Optional[str], subject: Optional[str],
    body: Optional[str], segment: Optional[str],
) -> tuple[str, str, Optional[str]]:
    """Apply a template's defaults, letting explicit subject/body/segment override."""
    tmpl = TEMPLATES.get(template_code or "")
    if tmpl:
        subject = subject or tmpl["subject"]
        body = body or tmpl["body"]
        segment = segment or tmpl["default_segment"]
    return subject or "", body or "", segment


def list_templates() -> list[dict]:
    return [{"code": code, **{k: v for k, v in t.items()}} for code, t in TEMPLATES.items()]


def list_segments() -> list[dict]:
    return [{"key": key, **meta} for key, meta in SEGMENTS.items()]


# --------------------------------------------------------------------------- #
# The agent
# --------------------------------------------------------------------------- #
class CommunicationService:
    """Resolve audience -> render -> send -> log."""

    @staticmethod
    async def resolve_segment(
        db: "AsyncSession",
        segment: str,
        *,
        semester_id: Optional[uuid.UUID] = None,
        team_id: Optional[uuid.UUID] = None,
    ) -> list[Recipient]:
        from sqlalchemy import func, select

        from app.models.mentor import Mentor
        from app.models.student import Student
        from app.models.team import Team
        from app.models.team_member import TeamMember

        if segment not in SEGMENTS:
            raise ValueError(f"Unknown audience segment: '{segment}'")
        if SEGMENTS[segment]["requires_team"] and team_id is None:
            raise ValueError(f"Segment '{segment}' requires a team_id")

        if segment == "all_students":
            q = select(Student.name, Student.email).where(Student.status == "active")
            if semester_id:
                q = q.where(Student.semester_id == semester_id)

        elif segment == "team_leaders":
            q = (
                select(Student.name, Student.email)
                .join(TeamMember, TeamMember.student_id == Student.id)
                .where(TeamMember.role == "LEADER")
            )

        elif segment == "unassigned_students":
            assigned = select(TeamMember.student_id)
            q = select(Student.name, Student.email).where(
                Student.status == "active", Student.id.notin_(assigned)
            )
            if semester_id:
                q = q.where(Student.semester_id == semester_id)

        elif segment == "incomplete_teams":
            counts = (
                select(TeamMember.team_id, func.count().label("c"))
                .group_by(TeamMember.team_id)
                .subquery()
            )
            q = (
                select(Student.name, Student.email)
                .join(TeamMember, TeamMember.student_id == Student.id)
                .join(counts, counts.c.team_id == TeamMember.team_id)
                .where(TeamMember.role == "LEADER", counts.c.c < 3)
            )

        elif segment == "teams_without_mentors":
            q = (
                select(Student.name, Student.email)
                .join(TeamMember, TeamMember.student_id == Student.id)
                .join(Team, Team.id == TeamMember.team_id)
                .where(Team.mentor_id.is_(None))
            )
            if semester_id:
                q = q.where(Team.semester_id == semester_id)

        elif segment == "mentors":
            q = select(Mentor.name, Mentor.email)

        elif segment == "specific_team":
            q = (
                select(Student.name, Student.email)
                .join(TeamMember, TeamMember.student_id == Student.id)
                .where(TeamMember.team_id == team_id)
            )
        else:  # pragma: no cover - guarded above
            raise ValueError(f"Unknown audience segment: '{segment}'")

        rows = await db.execute(q)
        return [{"name": r[0], "email": r[1]} for r in rows.all()]

    @classmethod
    async def send(
        cls,
        db: "Optional[AsyncSession]",
        *,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        template_code: Optional[str] = None,
        segment: Optional[str] = None,
        context: Optional[dict] = None,
        recipients: Optional[list[Recipient]] = None,
        admin_id: Optional[uuid.UUID] = None,
        semester_id: Optional[uuid.UUID] = None,
        team_id: Optional[uuid.UUID] = None,
        mailer: Optional[Mailer] = None,
    ) -> dict[str, Any]:
        """Send to a resolved segment (or an explicit recipient list) and log it.

        Pass ``recipients`` directly (and ``db=None``) to send without touching the
        DB — used by tests and by callers that already have the audience.
        """
        subject, body, segment = resolve_message_fields(
            template_code=template_code, subject=subject, body=body, segment=segment
        )

        if recipients is None:
            if db is None:
                raise ValueError("Provide either recipients or a db + segment")
            if not segment:
                raise ValueError("A segment (or template with a default segment) is required")
            recipients = await cls.resolve_segment(
                db, segment, semester_id=semester_id, team_id=team_id
            )

        msg = prepare_message(
            subject=subject, body=body, context=context, recipients=recipients
        )

        # Only resolve the SMTP layer when there is actually something to send.
        if msg["emails"]:
            if mailer is None:
                from app.services.email_service import send_mail

                mailer = send_mail
            await mailer(subject=msg["subject"], recipients=msg["emails"], body=msg["body"])

        if db is not None and admin_id is not None:
            await cls._log(db, msg, admin_id)

        return {
            "sent": len(msg["emails"]),
            "recipients": msg["emails"],
            "subject": msg["subject"],
            "segment": segment,
        }

    @staticmethod
    async def _log(db: AsyncSession, msg: dict, admin_id: uuid.UUID) -> None:
        from app.models.email_log import EmailLog

        db.add(
            EmailLog(
                subject=msg["subject"],
                body=msg["body"],
                recipients=msg["emails"],
                sent_by=admin_id,
            )
        )
        await db.commit()

    @staticmethod
    async def history(db: AsyncSession, *, limit: int = 50) -> list[dict]:
        from app.models.email_log import EmailLog

        rows = await db.execute(
            select(EmailLog).order_by(EmailLog.sent_at.desc()).limit(limit)
        )
        logs = rows.scalars().all()
        return [
            {
                "id": str(log.id),
                "subject": log.subject,
                "recipients": log.recipients,
                "recipient_count": len(log.recipients or []),
                "sent_at": log.sent_at.isoformat() if log.sent_at else None,
            }
            for log in logs
        ]
