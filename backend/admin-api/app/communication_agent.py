"""Communication Agent endpoints for admin-api (Supabase-backed).

Resolve a named audience segment from the live tables (students / teams_validation
/ mentors) -> render a template -> optionally send via SMTP (if MAIL_* configured)
-> log to communication_history. Deterministic, no LLM.
"""
import json
import logging
import os
import re
import smtplib
import html
import string
import threading
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger("communication_agent")

# --------------------------------------------------------------------------- #
# Registries (mirrors backend/app's Communication Agent)
# --------------------------------------------------------------------------- #
SEGMENTS: dict[str, dict[str, Any]] = {
    # Not offered in the dropdown any more (replaced there by the two
    # validation segments), but kept resolvable: kickoff, team_formation and
    # problem_statements default to it, and those are semester-wide
    # announcements that must still reach students who have no team yet.
    "all_students": {"label": "All Enrolled Students", "requires_team": False},
    "valid_teams": {"label": "Valid Teams", "requires_team": False, "needs": "teams"},
    "invalid_teams": {"label": "Invalid Teams", "requires_team": False, "needs": "teams"},
    "team_leaders": {"label": "Team Leaders Only", "requires_team": False, "needs": "teams"},
    "unassigned_students": {"label": "Unallocated Students (no team)", "requires_team": False},
    "incomplete_teams": {"label": "Incomplete Teams (< 3 members)", "requires_team": False, "needs": "teams"},
    "teams_without_mentors": {"label": "Teams without a Mentor", "requires_team": False, "needs": "teams"},
    "mentors": {"label": "All Faculty Mentors", "requires_team": False, "needs": "mentors"},
    "panel_members": {"label": "All Panel Members", "requires_team": False, "needs": "panels"},
    "specific_team": {"label": "A Specific Team", "requires_team": True, "needs": "teams"},
}

# What each `needs` value means, and why the segment cannot be used without it:
# a batch whose teams are not formed yet has nothing for a team segment to
# resolve to, so offering it would only ever send to nobody.
NEEDS_REASON = {
    "teams": "Teams have not been formed for this batch yet.",
    "mentors": "Mentors have not been allocated for this batch yet.",
    "panels": "Panels have not been decided yet.",
}

TEMPLATES: dict[str, dict[str, Any]] = {
    "kickoff": {
        "name": "Semester Kickoff", "default_segment": "all_students", "params": [],
        "subject": "Welcome to the Project Semester",
        "body": ("Dear Student,\n\nThe project semester has officially begun. Over the coming "
                 "weeks you will form teams, select a problem statement, and be paired with a "
                 "faculty mentor.\n\nPlease watch your inbox and the student portal for the next "
                 "steps.\n\nRegards,\nProcksi Admin"),
    },
    "team_formation": {
        "name": "Team Formation Call", "default_segment": "all_students", "params": ["deadline"],
        "subject": "Action Required: Form Your Project Team",
        "body": ("Dear Student,\n\nIt's time to form your project teams (maximum 3 members per "
                 "team). One member should log in to the portal and add the other members' "
                 "details.\n\nPlease complete team formation before {deadline}.\n\nRegards,\nProcksi Admin"),
    },
    "problem_statements": {
        "name": "Problem Statements Released", "default_segment": "all_students", "params": ["deadline"],
        "subject": "Problem Statements Are Now Available",
        "body": ("Dear Student,\n\nThe department's problem statements have been released. Please "
                 "review them with your team and submit your selection (with a short description) "
                 "on the portal before {deadline}.\n\nRegards,\nProcksi Admin"),
    },
    "team_add_request": {
        "name": "Request to Add a Member", "default_segment": "specific_team",
        "params": ["team_name", "student_name"],
        "subject": "Admin Request: Add a Member to Your Team",
        "body": ("Dear Team {team_name},\n\nThe admin requests to add {student_name} to your team. "
                 "If you agree, please log in to the portal and add this student's details to "
                 "finalize your team.\n\nRegards,\nProcksi Admin"),
    },
    "proposal_approved": {
        "name": "Custom Proposal Approved", "default_segment": "specific_team", "params": ["team_name"],
        "subject": "Proposal Approved - {team_name}",
        "body": ("Dear Team {team_name},\n\nYour custom project proposal has been approved. Please "
                 "log in to the portal and enter your final project description to proceed.\n\n"
                 "Regards,\nProcksi Admin"),
    },
    "proposal_rejected": {
        "name": "Custom Proposal Rejected", "default_segment": "specific_team", "params": ["team_name"],
        "subject": "Proposal Update - {team_name}",
        "body": ("Dear Team {team_name},\n\nYour custom project proposal was not approved this time. "
                 "Please select a problem statement from the department's standard list on the "
                 "portal before the deadline.\n\nRegards,\nProcksi Admin"),
    },
    "proposal_revision": {
        "name": "Custom Proposal Revision Requested", "default_segment": "specific_team", "params": ["team_name"],
        "subject": "Proposal Revision Requested - {team_name}",
        "body": ("Dear Team {team_name},\n\nThe project administration has requested a revision for your custom proposal. "
                 "Please log in to the portal to review administrator comments and submit your updated proposal.\n\n"
                 "Regards,\nProcksi Admin"),
    },
    "proposal_resubmitted": {
        "name": "Proposal Resubmitted Confirmation", "default_segment": "specific_team", "params": ["team_name"],
        "subject": "Proposal Resubmitted - {team_name}",
        "body": ("Dear Team {team_name},\n\nYour revised project proposal has been successfully resubmitted "
                 "for admin review.\n\nRegards,\nProcksi Admin"),
    },
    "mentor_onboarding": {
        "name": "Faculty Mentor Registration", "default_segment": "mentors", "params": [],
        "subject": "Action Required: Register on the Mentor Portal",
        "body": ("Dear Faculty,\n\nWe invite you to join as a Mentor for this semester. Please "
                 "register on the Mentor Portal and select your domains for mentoring from the listed "
                 "project domains. Your guidance is invaluable to our students' success.\n\n"
                 "Access the portal here: [Mentor Portal URL]\n\n"
                 "Thank you."),
    },
}


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_template(text: Optional[str], context: Optional[dict] = None, *, escape_values: bool = False) -> str:
    """Substitute merge fields into an admin-authored template.

    With `escape_values`, every *interpolated value* is HTML-escaped while the
    template's own markup is left intact. The merge context is filled from
    database rows — project_title comes from a student-submitted proposal title,
    copied verbatim into teams_validation on approval — and the result is both
    rendered with dangerouslySetInnerHTML in the admin preview and mailed out as
    HTML. Substituting unescaped meant a proposal title could carry script into
    the admin's session and into recipients' inboxes.
    """
    if not text:
        return ""
    ctx = context or {}
    if escape_values:
        ctx = {key: html.escape(str(value), quote=True) if value is not None else "" for key, value in ctx.items()}
    try:
        return string.Formatter().vformat(text, (), _SafeDict(ctx))
    except (ValueError, IndexError):
        return text


def dedupe_emails(emails: list) -> list[str]:
    seen, out = set(), []
    for e in emails:
        e = str(e or "").strip()
        if "@" in e and e.lower() not in seen:
            seen.add(e.lower())
            out.append(e)
    return out


def _leader_id(team: dict) -> str | None:
    """The student id of a team's leader.

    `leader` holds a display name ("Nishant"), not an id, so looking it up in
    the student map never matched and team_leaders resolved to nobody. The id
    is in `leader_roll`, or on the member entry whose role is LEADER.
    """
    roll = team.get("leader_roll")
    if roll:
        return str(roll)
    members = team.get("members")
    if isinstance(members, list):
        for m in members:
            if isinstance(m, dict) and str(m.get("role") or "").upper() == "LEADER" and m.get("id"):
                return str(m["id"])
    return None


def _member_ids(team: dict) -> list[str]:
    ids = []
    if team.get("leader"):
        ids.append(str(team["leader"]))
    members = team.get("members")
    if isinstance(members, list):
        for m in members:
            if isinstance(m, str):
                ids.append(m)
            elif isinstance(m, dict) and m.get("id"):
                ids.append(str(m["id"]))
    return ids


GREETING_TOKEN = "{recipient_name}"


def _personalise(body: str, first_name: str) -> str:
    """Substitute the greeting token, and failing that the leading "Dear X,".

    Admins write "Dear Student," by habit rather than using the token, so the
    common case has to work without them knowing a token exists.
    """
    if GREETING_TOKEN in body:
        return body.replace(GREETING_TOKEN, first_name)
    return re.sub(r"^([ \t]*Dear[ \t]+)[^,\n]{1,60}(,)",
                  lambda m: f"{m.group(1)}{first_name}{m.group(2)}",
                  body, count=1, flags=re.IGNORECASE)


def _smtp_send(subject: str, recipients: list[str], body: str, include_portal_button: bool = False,
               names: Optional[dict] = None) -> dict:
    """Send via SMTP. Returns {"sent": [...], "failed": [...]} from the dispatcher.

    With ``names`` ({email: first_name}) each recipient gets their own greeting,
    which means a body per address rather than one shared HTML document.
    """
    from app.email_notifier import wrap_communication_email

    if not names:
        wrapped_html = wrap_communication_email(subject, body, include_portal_button=include_portal_button)
        return _smtp_send_multipart(subject, recipients, wrapped_html, is_html=True, attachments=[],
                                    include_portal_button=include_portal_button)

    per_recipient = {
        str(r).strip().lower(): wrap_communication_email(
            subject,
            _personalise(body, names.get(str(r).strip().lower(), "Student")),
            include_portal_button=include_portal_button,
        )
        for r in recipients if r and "@" in str(r)
    }
    return _smtp_send_multipart(subject, recipients, body, is_html=True, attachments=[],
                                include_portal_button=include_portal_button,
                                per_recipient_content=per_recipient)


def _smtp_send_multipart(subject, recipients, content, is_html, attachments, include_portal_button: bool = False,
                         per_recipient_content: Optional[dict] = None) -> dict:
    """Send an HTML/plain email with file attachments using background thread chunked dispatch.

    Uses _send_smtp_chunked from email_notifier (same as notification_agent welcome emails)
    so sending 500+ emails runs in managed 25-connection chunks without timing out the API.
    """
    from app.email_notifier import wrap_communication_email, _send_smtp_chunked

    clean_recips = list(set(r.strip() for r in recipients if r and "@" in str(r)))
    if not clean_recips:
        return {"sent": [], "failed": []}

    # Already wrapped per address when personalising; wrapping again would nest
    # a whole document inside another one.
    wrapped_content = wrap_communication_email(
        subject,
        _personalise(content, "Student") if per_recipient_content else content,
        include_portal_button=include_portal_button,
    )
    sender = (os.getenv("MAIL_FROM") or os.getenv("MAIL_USERNAME") or os.getenv("MASTER_ADMIN_EMAIL") or "").strip()
    sender_name = (os.getenv("MAIL_FROM_NAME") or "Procksi Portal").strip()

    items_to_send = []
    for r in clean_recips:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{sender}>" if sender_name else sender
        msg["To"] = r
        body_for_r = (per_recipient_content or {}).get(str(r).strip().lower()) or wrapped_content
        msg.attach(MIMEText(body_for_r, "html" if is_html else "plain"))

        for name, data in attachments:
            part = MIMEApplication(data, Name=name)
            part["Content-Disposition"] = f'attachment; filename="{name}"'
            msg.attach(part)

        items_to_send.append({"email": r, "msg": msg})

    # Sent inline rather than in a daemon thread. The thread version always
    # returned True the instant it was started, which is why every send was
    # logged "Delivered" even through a total SMTP outage. The caller needs the
    # real outcome to record it, so this blocks until the dispatch finishes.
    logger.info(f"Starting mass email dispatch of '{subject}' to {len(items_to_send)} recipients...")
    result = _send_smtp_chunked(items_to_send, chunk_size=25, delay_between_msgs=0.1, delay_between_chunks=0.5)
    return result or {"sent": [], "failed": []}


# --------------------------------------------------------------------------- #
# Per-team mail-merge helpers
# --------------------------------------------------------------------------- #
def _clean_mentor(value) -> str:
    """Mentor is stored as a name, sometimes a JSON-array string like '["Dr. X"]'."""
    if not value:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    s = str(value).strip()
    if s.startswith("["):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return ", ".join(str(v) for v in parsed)
        except Exception:
            pass
    return s


def _team_recipients(team: dict, student_map: dict) -> list[str]:
    """Emails of a team's members (from the members jsonb, falling back to the roster)."""
    emails = []
    for m in (team.get("members") or []):
        if isinstance(m, dict):
            m_roll = str(m.get("roll") or m.get("student_id") or "")
            e = m.get("email") or student_map.get(str(m.get("id")), {}).get("email") or student_map.get(m_roll, {}).get("email")
            if e:
                emails.append(e)
        elif isinstance(m, str):
            e = student_map.get(m, {}).get("email")
            if e:
                emails.append(e)
    return dedupe_emails(emails)


def team_number(team: dict):
    """Best-effort integer team number for a team row.

    Prefers an explicit team_no/teamNo column, else parses the id suffix
    (e.g. '<uuid>-T2' or 'TEAM-2' -> 2). Returns None if not derivable.
    """
    for k in ("team_no", "teamNo"):
        v = team.get(k)
        if v not in (None, ""):
            try:
                return int(v)
            except (ValueError, TypeError):
                pass
    text = str(team.get("id") or "").strip()
    m = (
        re.search(r"[-_]?[Tt][Ee][Aa][Mm][-_]?\s*(\d+)$", text, re.IGNORECASE)
        or re.search(r"[-_][Tt](\d+)$", text, re.IGNORECASE)
        or re.search(r"(\d+)$", text)
    )
    if m:
        return int(m.group(1))
    return None


def team_label(team: dict) -> str:
    """Human team name for mail-merge: e.g. '2027-T101' showing year and number."""
    from app.email_notifier import format_clean_team_name
    team_id = team.get("id") or ""
    semester_id = team.get("semester_id") or team.get("semesterId")
    return format_clean_team_name(team_id, semester_id=semester_id)


def build_team_context(team: dict) -> dict:
    """Mail-merge fields available in the subject/body template for each team."""
    members = team.get("members") or []
    names = [m.get("name") for m in members if isinstance(m, dict) and m.get("name")]
    lbl = team_label(team)
    return {
        "team_id": lbl,
        "team_name": lbl,
        "project_title": team.get("title", ""),
        "team_title": team.get("title", ""),
        "leader_name": team.get("leader", ""),
        "mentor_name": _clean_mentor(team.get("mentor")),
        "members": ", ".join(names),
        "member_count": team.get("memberCount") or len(members),
        "domain": team.get("domain", ""),
        "semester": team.get("semester_id", ""),
    }


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def file_matches_team(filename: str, team_id: str) -> bool:
    """Match 'TEAM-3_report.pdf' -> team 'TEAM-3' without also matching 'TEAM-31'."""
    nid, nfn = _norm(team_id), _norm(filename)
    if not nid:
        return False
    return re.search(re.escape(nid) + r"(?![0-9])", nfn) is not None


PER_TEAM_FIELDS = [
    "{team_id}", "{team_name}", "{project_title}", "{leader_name}",
    "{mentor_name}", "{members}", "{member_count}", "{domain}", "{semester}",
]


# --------------------------------------------------------------------------- #
# Router
# --------------------------------------------------------------------------- #
class SendRequest(BaseModel):
    segment: Optional[str] = None
    template_code: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    context: dict = {}
    team_id: Optional[str] = None
    semester_id: Optional[str] = None
    include_portal_button: bool = False
    # Optional narrowing of the resolved segment. The dashboard sends the
    # addresses left checked in the audience preview; anything not resolved by
    # the segment itself is ignored, so this can only ever remove recipients,
    # never add someone the segment does not cover.
    only_emails: Optional[list[str]] = None


def _student_map(service_client) -> dict:
    rows = service_client.table("students").select("id,email,name,semester_id").execute().data or []
    return {str(r["id"]): r for r in rows if r.get("id")}


# Segments whose audience is best described by the teams it covers rather than
# by a list of student addresses: showing "Team 4, Team 17, ..." is far easier to
# check at a glance than 464 emails.
TEAM_SEGMENTS = {
    "valid_teams", "invalid_teams", "incomplete_teams",
    "teams_without_mentors", "team_leaders", "specific_team",
}


def _batch_readiness(service_client, semester_id: str | None = None) -> dict[str, bool]:
    """Whether this batch has teams, mentors and panels set up yet.

    Scoped to the semester when one is given, because the answer differs per
    batch: a new intake has students but no teams, while the outgoing one has
    everything. Fails open -- a probe that errors reports ready, so a lookup
    problem cannot silently strip the dashboard of every segment.
    """
    # "Teams exist" is not the same as "teams have been formed": a new batch
    # often carries a couple of placeholder rows while the roster is untouched.
    # Judged by how much of the batch is actually in a team -- 0.4% for a fresh
    # intake against 100% for an established one, so the threshold is not
    # delicate.
    try:
        t_q = service_client.table("teams_validation").select("memberCount")
        if semester_id:
            t_q = t_q.eq("semester_id", semester_id)
        team_rows = t_q.execute().data or []
        in_teams = sum((r.get("memberCount") or 0) for r in team_rows)

        s_q = service_client.table("students").select("id")
        if semester_id:
            s_q = s_q.eq("semester_id", semester_id)
        student_count = len(s_q.execute().data or [])

        has_teams = bool(team_rows) and (
            student_count == 0 or (in_teams / student_count) >= 0.10
        )
    except Exception as exc:  # noqa: BLE001 - readiness is advisory
        logger.warning(f"Readiness probe for teams failed: {exc}")
        has_teams = True

    # A team with no mentor assigned does not make the mentor segments usable,
    # so mentors are judged by the allocations, not by the mentor roster.
    try:
        rows = service_client.table("teams_validation").select("mentor")
        if semester_id:
            rows = rows.eq("semester_id", semester_id)
        has_mentors = any((r.get("mentor") or "").strip() for r in (rows.execute().data or []))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Readiness probe for mentors failed: {exc}")
        has_mentors = True

    # Panels are global rather than per-semester, so they are not scoped.
    has_panels = _panel_users_exist(service_client)

    return {"teams": has_teams, "mentors": has_mentors, "panels": has_panels}


def _panel_users_exist(service_client) -> bool:
    try:
        rows = service_client.table("users").select("id").eq("role", "panel").limit(1).execute()
        return bool(rows.data or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Readiness probe for panels failed: {exc}")
        return True


def resolve_segment_teams(service_client, segment: str, team_id=None, semester_id=None) -> list[dict]:
    """The teams a team-based segment covers, as [{"number": int|None, "id": str}].

    Mirrors the team filtering in resolve_segment so the preview cannot claim a
    different set from the one that gets mailed.
    """
    if segment not in TEAM_SEGMENTS:
        return []

    # Same active-semester gate resolve_segment applies, inline for the same
    # reason it is inline there: there is no shared helper for it.
    active_sem_ids = []
    try:
        active_res = service_client.table("semester_config").select("id").eq("is_active", True).execute()
        active_sem_ids = [s["id"] for s in active_res.data or []]
    except Exception:
        pass
    if not active_sem_ids:
        return []
    if semester_id and semester_id in active_sem_ids:
        active_sem_ids = [semester_id]

    teams = service_client.table("teams_validation").select("*").execute().data or []
    teams = [t for t in teams if t.get("semester_id") in active_sem_ids]

    if segment == "specific_team":
        picked = [t for t in teams if str(t.get("id")) == str(team_id)]
    elif segment in ("valid_teams", "invalid_teams"):
        want_valid = segment == "valid_teams"
        picked = [t for t in teams
                  if (str(t.get("validationStatus") or "").strip().lower() == "valid") == want_valid]
    elif segment == "incomplete_teams":
        picked = [t for t in teams if (t.get("memberCount") or 0) < 3]
    elif segment == "teams_without_mentors":
        picked = [t for t in teams if not t.get("mentor")]
    else:  # team_leaders -- every team has one
        picked = [t for t in teams if t.get("leader")]

    # Each team carries the addresses it contributes, so unchecking a team in the
    # dashboard can remove exactly that team's members from the send.
    smap = _student_map(service_client)
    out = []
    for t in picked:
        if segment == "team_leaders":
            lid = _leader_id(t)
            member_emails = [smap.get(lid, {}).get("email")] if lid else []
        else:
            member_emails = [smap.get(mid, {}).get("email") for mid in _member_ids(t)]
        out.append({
            "number": team_number(t),
            "id": str(t.get("id")),
            "emails": dedupe_emails(member_emails),
        })
    # Numbered teams first and in order; anything unnumbered trails behind.
    out.sort(key=lambda r: (r["number"] is None, r["number"] if r["number"] is not None else 0))
    return out


def resolve_segment(service_client, segment: str, team_id=None, semester_id=None) -> list[str]:
    if segment not in SEGMENTS:
        raise HTTPException(status_code=400, detail=f"Unknown segment: {segment}")
    if SEGMENTS[segment]["requires_team"] and not team_id:
        raise HTTPException(status_code=400, detail=f"Segment '{segment}' requires a team_id")

    # Fetch active semester IDs to enforce active semester restriction
    active_sem_ids = []
    try:
        active_res = service_client.table("semester_config").select("id").eq("is_active", True).execute()
        active_sem_ids = [s["id"] for s in active_res.data or []]
    except Exception:
        pass

    if not active_sem_ids:
        # If no active semester, return empty to prevent sending communications
        return []

    # If an explicit semester_id was provided, ensure it's actually active
    if semester_id and semester_id not in active_sem_ids:
        return []

    # If it's a mentor list, mentors are global but we only want mentors of active semesters
    if segment == "mentors":
        rows = service_client.table("mentors").select("email").execute().data or []
        return dedupe_emails([r.get("email") for r in rows])

    # Panel members live in `users` with role='panel', each carrying the
    # panel_id they evaluate for. The `panels` table has a members column, but
    # it is empty on every row, so it is not a usable source of addresses.
    if segment == "panel_members":
        rows = service_client.table("users").select("email, role").eq("role", "panel").execute().data or []
        return dedupe_emails([r.get("email") for r in rows])

    smap = _student_map(service_client)
    # Filter students to only active semesters
    smap = {k: v for k, v in smap.items() if v.get("semester_id") in active_sem_ids}


    # Fetch teams belonging ONLY to active semesters
    teams = service_client.table("teams_validation").select("*").execute().data or []
    teams = [t for t in teams if t.get("semester_id") in active_sem_ids]

    emails: list = []
    if segment == "team_leaders":
        emails = [smap.get(_leader_id(t), {}).get("email") for t in teams if _leader_id(t)]
    if segment == "all_students":
        return dedupe_emails([r.get("email") for r in smap.values()])

    if segment in ("valid_teams", "invalid_teams"):
        # validationStatus is "Valid" or "Pending" in practice; there is no
        # "Invalid" value. Anything that is not Valid counts as invalid, so a
        # future third state is covered rather than silently dropped.
        want_valid = segment == "valid_teams"
        for t in teams:
            is_valid = str(t.get("validationStatus") or "").strip().lower() == "valid"
            if is_valid == want_valid:
                emails += [smap.get(mid, {}).get("email") for mid in _member_ids(t)]
    elif segment == "incomplete_teams":
        # Same leader-id problem as team_leaders: `leader` is a name, not an id.
        emails = [smap.get(_leader_id(t), {}).get("email")
                  for t in teams if (t.get("memberCount") or 0) < 3 and _leader_id(t)]
    elif segment == "teams_without_mentors":
        for t in teams:
            if not t.get("mentor"):
                emails += [smap.get(mid, {}).get("email") for mid in _member_ids(t)]
    elif segment == "specific_team":
        t = next((t for t in teams if str(t.get("id")) == str(team_id)), None)
        emails = [smap.get(mid, {}).get("email") for mid in _member_ids(t)] if t else []
    elif segment == "unassigned_students":
        assigned = {mid for t in teams for mid in _member_ids(t)}
        emails = [r.get("email") for k, r in smap.items() if k not in assigned]
    return dedupe_emails([e for e in emails if e])


def _first_name(name: Optional[str]) -> str:
    """"Preshit Desai" -> "Preshit". Falls back to "Student" for blanks.

    Titles are stripped: mentor rows are stored as "Dr. Preshit Desai" often
    enough that greeting someone "Dear Dr.," is a real outcome otherwise.
    """
    parts = [p for p in str(name or "").replace(",", " ").split() if p]
    titles = {"dr", "dr.", "prof", "prof.", "mr", "mr.", "ms", "ms.", "mrs", "mrs.", "shri", "smt"}
    while parts and parts[0].lower() in titles:
        parts.pop(0)
    return parts[0] if parts else "Student"


# Segments greeted by role rather than by individual name. Faculty and panel
# mail is institutional, so it reads "Dear Mentor," to everyone on the list.
FIXED_GREETINGS = {"mentors": "Mentor", "panel_members": "Panel"}


def resolve_segment_people(service_client, segment: str, team_id=None, semester_id=None) -> dict[str, str]:
    """Map of ``{email: first_name}`` for a segment, for per-recipient greetings.

    Mirrors resolve_segment's filtering rather than reimplementing it: the
    addresses come from there, and this only attaches names to them, so the two
    cannot disagree about who is in the audience.
    """
    emails = resolve_segment(service_client, segment, team_id, semester_id)
    if not emails:
        return {}
    wanted = {str(e).strip().lower() for e in emails}

    fixed = FIXED_GREETINGS.get(segment)
    if fixed:
        return {e: fixed for e in wanted}

    names: dict[str, str] = {}

    def _absorb(rows):
        for r in rows or []:
            e = str(r.get("email") or "").strip().lower()
            if e in wanted and e not in names:
                names[e] = _first_name(r.get("name"))

    try:
        _absorb(_student_map(service_client).values())
    except Exception as exc:  # noqa: BLE001 - names are a nicety, addresses are not
        logger.warning(f"Could not resolve recipient names for '{segment}': {exc}")

    # Anyone we could not name still gets a valid greeting.
    for e in wanted:
        names.setdefault(e, "Student")
    return names


def _active_sem_ids(service_client) -> list[str]:
    """IDs of active semesters. SMTP is only permitted for these."""
    try:
        res = service_client.table("semester_config").select("id").eq("is_active", True).execute()
        return [s["id"] for s in res.data or []]
    except Exception:
        return []


def _per_team_plan(service_client, *, team_ids, segment, filter_team_id, semester_id, active_sem_ids):
    """Resolve the audience for a per-team send WITHOUT rendering or sending.

    Returns ``(teams, per_team, leftover)`` where:
      - ``teams``     is the id/semester-filtered team list (used for shared-file matching),
      - ``per_team``  is a list of ``(team_dict, recipients)`` that will each get a merged email,
      - ``leftover``  is a sorted list of segment emails belonging to no matched team
                      (delivered later as one grouped, non-merged email).

    Shared by ``send-per-team`` (source of truth) and ``per-team-count`` (live preview),
    so the count can never drift from what actually gets sent. Raises ``HTTPException(400)``
    when no team matches the id/semester filter.
    """
    teams = service_client.table("teams_validation").select("*").execute().data or []
    teams = [t for t in teams if t.get("semester_id") in active_sem_ids]
    if semester_id:
        teams = [t for t in teams if str(t.get("semester_id")) == semester_id]
    if team_ids:
        wanted = {x.strip() for x in team_ids.split(",") if x.strip()}
        teams = [t for t in teams if str(t.get("id")) in wanted]
    if not teams:
        raise HTTPException(status_code=400, detail="No matching teams to send to")

    smap = _student_map(service_client)
    smap = {k: v for k, v in smap.items() if v.get("semester_id") in active_sem_ids}

    allowed_emails = None
    if segment:
        allowed_emails = {e.lower() for e in resolve_segment(
            service_client, segment, team_id=filter_team_id, semester_id=semester_id)}

    per_team, used_emails = [], set()
    for t in teams:
        recips = _team_recipients(t, smap)
        if allowed_emails is not None:
            recips = [r for r in recips if str(r).lower() in allowed_emails]
            if not recips:
                continue  # no one on this team is in the selected segment
            used_emails.update(str(r).lower() for r in recips)
        per_team.append((t, recips))

    leftover = sorted(e for e in allowed_emails if e not in used_emails) if allowed_emails is not None else []
    return teams, per_team, leftover


def send_communication(service_client, payload: SendRequest) -> dict:
    # Verify the target semester is active before sending
    active_sem_ids = []
    try:
        active_res = service_client.table("semester_config").select("id").eq("is_active", True).execute()
        active_sem_ids = [s["id"] for s in active_res.data or []]
    except Exception:
        pass

    if payload.semester_id and payload.semester_id not in active_sem_ids:
        raise HTTPException(status_code=400, detail="Emails can only be sent for active semesters.")

    tmpl = TEMPLATES.get(payload.template_code or "")
    subject = payload.subject or (tmpl["subject"] if tmpl else "")
    body = payload.body or (tmpl["body"] if tmpl else "")
    segment = payload.segment or (tmpl["default_segment"] if tmpl else None)
    if not segment:
        raise HTTPException(status_code=400, detail="A segment or template is required")

    from app.email_notifier import format_clean_team_name
    ctx = dict(payload.context or {})
    if payload.team_id:
        clean_lbl = format_clean_team_name(payload.team_id, semester_id=payload.semester_id)
        ctx["team_name"] = clean_lbl
        ctx["team_id"] = clean_lbl
    elif "team_name" in ctx:
        ctx["team_name"] = format_clean_team_name(ctx["team_name"], semester_id=payload.semester_id)
        if "team_id" not in ctx:
            ctx["team_id"] = ctx["team_name"]

    recipients = resolve_segment(service_client, segment, payload.team_id, payload.semester_id)

    if payload.only_emails is not None:
        # Intersect rather than replace: a client cannot mail anyone outside the
        # segment it selected, even if it asks to.
        allowed = {e.strip().lower() for e in payload.only_emails if e and "@" in str(e)}
        recipients = [r for r in recipients if str(r).strip().lower() in allowed]
    subj = render_template(subject, ctx)
    # _smtp_send wraps this in an HTML document unconditionally, so merge values
    # are always escaped on this path.
    bod = render_template(body, ctx, escape_values=True)

    delivered = False
    send_result = {"sent": [], "failed": []}
    if recipients:
        try:
            names = resolve_segment_people(service_client, segment, payload.team_id, payload.semester_id)
            send_result = _smtp_send(subj, recipients, bod,
                                     include_portal_button=payload.include_portal_button,
                                     names=names)
        except Exception as send_err:
            # The dispatcher raised before it could report per-recipient
            # results; treat every address as failed rather than losing the fact.
            send_result = {"sent": [],
                           "failed": [{"email": r, "error": str(send_err)[:300]} for r in recipients]}
        delivered = bool(send_result.get("sent"))

        # Insert portal notifications for each resolved recipient email address
        try:
            notif_rows = []
            role = "mentor" if segment in ("mentors",) else "student"
            for r_email in recipients:
                notif_rows.append({
                    "recipient_email": r_email,
                    "recipient_role": role,
                    "title": subj,
                    "message": bod,
                    "type": "communication",
                    "read": False
                })
            if notif_rows:
                service_client.table("notifications").insert(notif_rows).execute()
        except Exception as notif_err:
            print(f"Could not write communication notifications: {notif_err}")

    now = datetime.now()
    log = {
        "type": payload.template_code or "custom",
        "recipients": f"{SEGMENTS[segment]['label']} ({len(recipients)})",
        "subject": subj,
        "date": now.strftime("%b %d, %Y"),
        "time": now.strftime("%H:%M"),
        # Honest status. "Delivered" used to be written whenever a thread had
        # been started, so a total outage still read as success.
        "status": (
            "Failed" if (send_result.get("failed") and not send_result.get("sent"))
            else "Partial" if send_result.get("failed")
            else "Delivered" if delivered
            else "Logged"
        ),
    }
    if payload.semester_id:
        log["semester_id"] = payload.semester_id
    # Fan-out to the portal backends and the notifications table.
    #
    # This used to run in the browser: Communication.jsx fired three further
    # requests after /send and swallowed each into console.warn("non-critical").
    # Closing the tab mid-flight abandoned whatever had not run, and the UI
    # reported success regardless. Doing it here means each step's outcome is
    # returned to the caller and recorded.
    #
    # The steps stay independent -- a portal being down must not fail the email,
    # which has already been sent by this point.
    fanout: list[dict] = []

    def _step(name: str, fn):
        try:
            fn()
            fanout.append({"step": name, "ok": True})
        except Exception as exc:
            fanout.append({"step": name, "ok": False, "error": str(exc)[:300]})

    if recipients:
        def _broadcast(url: str, headers: dict):
            import httpx
            payload_body = {
                "type": payload.template_code or "custom",
                "recipients": SEGMENTS[segment]["label"],
                "subject": subj,
                "body": bod,
                "sent_at": datetime.now().isoformat(),
            }
            with httpx.Client(timeout=15) as client:
                resp = client.post(url, json=payload_body, headers=headers)
                resp.raise_for_status()

        # PANEL_API_URL / MENTOR_API_URL come from the Vercel service bindings.
        panel_url = (os.getenv("PANEL_API_URL") or os.getenv("PANEL_PORTAL_API_URL") or "http://panel-backend:8001").rstrip("/")
        mentor_url = (os.getenv("MENTOR_API_URL") or os.getenv("MENTOR_PORTAL_API_URL") or "http://mentor-backend:8003").rstrip("/")
        admin_key = (os.getenv("ADMIN_API_KEY") or "").strip()

        # panel-api guards this with require_admin_key, so the shared key works.
        _step("panel_broadcast", lambda: _broadcast(
            f"{panel_url}/admin/sync/broadcast", {"X-Admin-Api-Key": admin_key}))

        # mentor-api's broadcast is at /api/admin/communication/broadcast, not
        # /api/admin/broadcast -- the browser called the latter and got a 404
        # on every send, hidden by the console.warn("non-critical") it sat in.
        #
        # It is guarded by get_current_admin (a mentor-portal JWT), which this
        # service does not hold, so the call is recorded as unattempted rather
        # than fired blind. Wiring it needs mentor-api to accept the shared
        # admin key the way panel-api already does; that is a separate change.
        fanout.append({
            "step": "mentor_broadcast",
            "ok": False,
            "error": "not attempted: mentor-api /api/admin/communication/broadcast "
                     "requires a mentor-portal JWT, which admin-api does not hold",
        })

    history_id = None
    log_error = None
    try:
        res = service_client.table("communication_history").insert(log).execute()
        rows = getattr(res, "data", None) or []
        if rows:
            history_id = rows[0].get("id")
    except Exception as hist_err:
        # Surfaced in the response instead of silently swallowed: an audit
        # trail that can vanish without trace is worse than no audit trail.
        log_error = str(hist_err)[:300]
        print(f"Could not write communication_history: {hist_err}")

    # Per-recipient outcomes. Best-effort by necessity -- the mail has already
    # gone, so a failure here must not turn a successful send into an error.
    try:
        # Every object needs the same keys: PostgREST rejects a mixed batch with
        # PGRST102, which silently lost the rows for any partly-failed send.
        delivery_rows = (
            [{"communication_id": history_id, "email": e, "status": "sent", "error": None}
             for e in send_result.get("sent", [])]
            + [{"communication_id": history_id, "email": f.get("email"),
                "status": "failed", "error": f.get("error")}
               for f in send_result.get("failed", [])]
        )
        if delivery_rows:
            service_client.table("email_deliveries").insert(delivery_rows).execute()
    except Exception as del_err:
        print(f"Could not write email_deliveries: {del_err}")

    return {"data": {
        "sent": len(recipients),
        "delivered": delivered,
        "delivered_count": len(send_result.get("sent", [])),
        "failed_count": len(send_result.get("failed", [])),
        "failures": send_result.get("failed", [])[:20],
        "status": log["status"],
        "log_error": log_error,
        "fanout": fanout,
        "segment": segment,
        "subject": subj,
        "recipients": recipients[:50],
    }}


def build_communication_router(service_client) -> APIRouter:
    router = APIRouter(prefix="/api/admin/communication", tags=["Communication Agent"])

    @router.get("/segments")
    def segments(semester_id: str | None = None) -> dict:
        """The segments the dashboard may offer, each marked available or not.

        A segment is disabled rather than hidden: an admin looking for "All
        Faculty Mentors" should see it greyed with a reason, not wonder where it
        went. `hidden` segments stay resolvable for templates that default to
        them but are never offered as a choice.
        """
        readiness = _batch_readiness(service_client, semester_id)
        out = []
        for k, v in SEGMENTS.items():
            if v.get("hidden"):
                continue
            needs = v.get("needs")
            available = True if not needs else bool(readiness.get(needs))
            row = {"key": k, **v, "available": available}
            if not available:
                row["unavailable_reason"] = NEEDS_REASON.get(needs, "Not available for this batch yet.")
            out.append(row)
        return {"data": out}

    @router.get("/templates")
    def templates() -> dict:
        return {"data": [{"code": c, **t} for c, t in TEMPLATES.items()]}

    @router.get("/recipients")
    def recipients(segment: str, team_id: str | None = None, semester_id: str | None = None) -> dict:
        """Resolve a segment to the addresses it would reach, without sending.

        The dashboard previously showed only a segment's label, so an admin
        picked an audience with no way to see who was actually in it until the
        mail had already gone.
        """
        if segment not in SEGMENTS:
            raise HTTPException(status_code=400, detail=f"Unknown segment '{segment}'.")
        if SEGMENTS[segment].get("requires_team") and not team_id:
            return {"data": {"segment": segment, "count": 0, "emails": [],
                             "label": SEGMENTS[segment]["label"]}}
        try:
            emails = resolve_segment(service_client, segment, team_id, semester_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not resolve recipients: {exc}") from exc
        # For team-based segments the teams are the useful view: "Team 4, Team
        # 17, ..." is checkable at a glance where 464 addresses are not.
        team_rows = resolve_segment_teams(service_client, segment, team_id, semester_id)
        people = resolve_segment_people(service_client, segment, team_id, semester_id)
        return {"data": {
            "segment": segment,
            "label": SEGMENTS[segment]["label"],
            "count": len(emails),
            "emails": emails,
            "names": people,
            "is_team_segment": segment in TEAM_SEGMENTS,
            "teams": team_rows,
            "team_count": len(team_rows),
        }}

    @router.post("/send")
    def send(payload: SendRequest) -> dict:
        return send_communication(service_client, payload)

    @router.get("/history")
    def history(limit: int = 50) -> dict:
        rows = (service_client.table("communication_history")
                .select("*").order("id", desc=True).limit(limit).execute().data or [])
        return {"data": rows}

    @router.get("/per-team-fields")
    def per_team_fields() -> dict:
        """Merge fields the admin can use in a per-team subject/body template."""
        return {"data": PER_TEAM_FIELDS}

    @router.get("/per-team-count")
    def per_team_count(
        team_ids: Optional[str] = None,
        segment: Optional[str] = None,
        filter_team_id: Optional[str] = None,
        semester_id: Optional[str] = None,
    ) -> dict:
        """Live audience size for a per-team send, without rendering or sending.

        Mirrors ``send-per-team`` exactly (same ``_per_team_plan`` helper), so the
        admin sees the true team/recipient count before hitting Preview. Never raises:
        an empty/invalid filter returns zeros so the UI can render a plain '0 teams'.
        """
        active_sem_ids = _active_sem_ids(service_client)
        empty = {"data": {"teams": 0, "recipients": 0, "leftover_recipients": 0}}
        if not active_sem_ids:
            return empty
        try:
            _teams, per_team, leftover = _per_team_plan(
                service_client, team_ids=team_ids, segment=segment,
                filter_team_id=filter_team_id, semester_id=semester_id, active_sem_ids=active_sem_ids)
        except HTTPException:
            return empty
        recips = sum(len(r) for _, r in per_team)
        return {"data": {
            "teams": len(per_team),
            "recipients": recips + len(leftover),
            "leftover_recipients": len(leftover),
        }}

    @router.post("/send-per-team")
    async def send_per_team(
        subject: str = Form(...),
        body: str = Form(...),
        is_html: bool = Form(True),
        semester_id: Optional[str] = Form(None),
        team_ids: Optional[str] = Form(None),   # CSV of team ids; empty => all (filtered by semester)
        segment: Optional[str] = Form(None),    # recipient filter group (see SEGMENTS); empty => no filter
        filter_team_id: Optional[str] = Form(None),  # team id for the 'specific_team' segment
        include_portal_button: bool = Form(False),
        dry_run: bool = Form(False),
        files: list[UploadFile] = File(default=[]),
    ) -> dict:
        """Mail-merge: render the body per team, attach that team's file(s), one email per team.

        Files are matched to a team when the team id appears in the filename
        (e.g. ``TEAM-3_report.pdf`` -> team ``TEAM-3``). Files matching no team are
        treated as **shared** and attached to every team's email. ``dry_run`` renders
        + maps without sending, for preview.
        """
        uploaded = [(f.filename, await f.read()) for f in files]

        # Fetch active semester IDs - SMTP only works for active semesters
        active_sem_ids = _active_sem_ids(service_client)
        if not active_sem_ids:
            raise HTTPException(status_code=400, detail="No active semester configuration. Cannot send emails.")

        # If semester_id is specified, verify it is active
        if semester_id and semester_id not in active_sem_ids:
            raise HTTPException(status_code=400, detail="Emails can only be sent for active semesters.")

        # Resolve the audience (team filtering + segment intersection + leftover group).
        # Shared with the /per-team-count endpoint so the preview count can't drift.
        teams, per_team, leftover = _per_team_plan(
            service_client, team_ids=team_ids, segment=segment,
            filter_team_id=filter_team_id, semester_id=semester_id, active_sem_ids=active_sem_ids)

        # Files that match no team at all -> shared, attached to everyone.
        shared = [(fn, data) for (fn, data) in uploaded
                  if not any(file_matches_team(fn, t.get("id", "")) for t in teams)]

        results, sent, failed, processed_teams = [], 0, 0, 0
        for t, recips in per_team:
            processed_teams += 1
            ctx = build_team_context(t)
            subj = render_template(subject, ctx)
            bod = render_template(body, ctx, escape_values=is_html)
            team_files = [(fn, data) for (fn, data) in uploaded if file_matches_team(fn, t.get("id", ""))]
            atts = team_files + shared

            status = "dry-run"
            if not dry_run:
                if not recips:
                    status = "skipped (no recipients)"
                else:
                    try:
                        delivered = bool(_smtp_send_multipart(subj, recips, bod, is_html, atts, include_portal_button=include_portal_button).get("sent"))
                        status = "delivered" if delivered else "logged (no SMTP)"
                        sent += 1 if delivered else 0
                    except Exception as e:  # one team's failure must not stop the rest
                        status = f"failed: {str(e)[:80]}"
                        failed += 1
                    try:
                        now = datetime.now()
                        service_client.table("communication_history").insert({
                            "type": "per_team",
                            "recipients": f"{t.get('id')} ({len(recips)})",
                            "subject": subj,
                            "date": now.strftime("%b %d, %Y"),
                            "time": now.strftime("%H:%M"),
                            "status": "Delivered" if status == "delivered" else "Logged",
                            **({"semester_id": semester_id} if semester_id else {}),
                        }).execute()
                    except Exception:
                        pass

            results.append({
                "team_id": t.get("id"),
                "project_title": t.get("title"),
                "subject": subj,
                "recipient_count": len(recips),
                "recipients": recips,
                "attachments": [fn for fn, _ in atts],
                "status": status,
                "body_preview": bod if dry_run else None,
            })

        # Segment members who belong to no team (e.g. mentors, unassigned students)
        # can't be merged per team, so deliver them one grouped, non-merged email.
        if leftover:
            label = SEGMENTS.get(segment, {}).get("label", segment)
            ctx = {"team_name": label, "team_id": segment}
            subj = render_template(subject, ctx)
            bod = render_template(body, ctx, escape_values=is_html)
            atts = shared
            status = "dry-run"
            if not dry_run:
                try:
                    delivered = bool(_smtp_send_multipart(subj, leftover, bod, is_html, atts, include_portal_button=include_portal_button).get("sent"))
                    status = "delivered" if delivered else "logged (no SMTP)"
                    sent += 1 if delivered else 0
                except Exception as e:
                    status = f"failed: {str(e)[:80]}"
                    failed += 1
            results.append({
                "team_id": f"segment:{segment}",
                "project_title": label,
                "subject": subj,
                "recipient_count": len(leftover),
                "recipients": leftover,
                "attachments": [fn for fn, _ in atts],
                "status": status,
                "body_preview": bod if dry_run else None,
            })

        return {"data": {
            "teams": processed_teams,
            "sent": sent,
            "failed": failed,
            "shared_files": [fn for fn, _ in shared],
            "dry_run": dry_run,
            "results": results,
        }}

    @router.post("/remind-pending")
    def remind_pending() -> dict:
        """Find teams that have not submitted github_data, and send SMTP + Portal notifications to their members."""
        try:
            # Fetch active semester IDs
            active_sem_ids = []
            try:
                active_res = service_client.table("semester_config").select("id").eq("is_active", True).execute()
                active_sem_ids = [s["id"] for s in active_res.data or []]
            except Exception:
                pass

            if not active_sem_ids:
                return {
                    "success": False,
                    "message": "No active semester configuration.",
                    "pending_teams_count": 0,
                    "portal_notifications_sent": 0,
                    "emails_sent": 0
                }

            # 1. Fetch all teams
            teams = service_client.table("teams_validation").select("*").execute().data or []
            # Filter teams to active semesters only
            teams = [t for t in teams if t.get("semester_id") in active_sem_ids]

            # 2. Fetch all github_data
            gh_data = service_client.table("github_data").select("*").execute().data or []
            
            submitted_team_nos = {
                g.get("team_id") for g in gh_data 
                if g.get("repository_url") and str(g.get("repository_url")).strip()
            }
            
            # Helper to extract numeric team number
            pending_teams = []
            for t in teams:
                t_no = team_number(t)
                if t_no not in submitted_team_nos:
                    pending_teams.append((t, t_no))
            
            if not pending_teams:
                return {
                    "success": True,
                    "message": "All teams have already submitted their workspace configurations.",
                    "pending_teams_count": 0,
                    "portal_notifications_sent": 0,
                    "emails_sent": 0
                }

            smap = _student_map(service_client)
            notifications = []
            email_recipients = []
            
            for t, t_no in pending_teams:
                t_id = t.get("id")
                # Retrieve member IDs
                member_ids = _member_ids(t)
                
                # Add a portal notification for the entire team
                notifications.append({
                    "recipient_role": "student",
                    "audience": f"team:{t_id}",
                    "title": "Action Required: Submit Project Details",
                    "message": "Your team has not yet submitted your Project Workspace configurations (GitHub Repository URL and Technology Stack). Please log in to the Student Portal and complete this submission immediately.",
                    "type": "workflow"
                })
                
                for mid in member_ids:
                    student = smap.get(str(mid))
                    if student and student.get("email"):
                        email_recipients.append(student.get("email"))
            
            # Send portal notifications
            portal_sent = 0
            if notifications:
                try:
                    service_client.table("notifications").insert(notifications).execute()
                    portal_sent = len(notifications)
                except Exception as n_err:
                    print(f"Failed to insert remind notifications: {n_err}")

            # Send SMTP reminder emails
            email_sent = 0
            smtp_delivered = False
            if email_recipients:
                email_recipients = dedupe_emails(email_recipients)
                subject = "URGENT: Submit Your Project Workspace Details"
                body = (
                    "Dear Student,\n\n"
                    "Our records show that your team has not yet submitted your Project Workspace configurations (GitHub Repository URL and Technology Stack).\n\n"
                    "Please log in to the Student Portal (Preferences Page), fill in the project configurations form, and submit it as soon as possible. Note that once submitted, these details are locked and can only be modified by an administrator.\n\n"
                    "If you have already submitted or formed a custom team, please coordinate with your team leader to ensure the submission has been finalized.\n\n"
                    "Regards,\n"
                    "Procksi Administration"
                )
                try:
                    smtp_delivered = bool(_smtp_send(subject, email_recipients, body).get("sent"))
                    if smtp_delivered:
                        email_sent = len(email_recipients)
                except Exception as s_err:
                    print(f"SMTP failed to send reminders: {s_err}")
            
            # Log communication history
            try:
                now = datetime.now()
                log = {
                    "type": "remind_pending_workspaces",
                    "recipients": f"Pending Team Members ({len(email_recipients)})",
                    "subject": "URGENT: Submit Your Project Workspace Details",
                    "date": now.strftime("%b %d, %Y"),
                    "time": now.strftime("%H:%M"),
                    "status": "Delivered" if smtp_delivered else "Logged (Portal Only)",
                }
                service_client.table("communication_history").insert(log).execute()
            except Exception:
                pass

            return {
                "success": True,
                "message": f"Successfully sent reminders to {len(pending_teams)} pending teams.",
                "pending_teams_count": len(pending_teams),
                "portal_notifications_sent": portal_sent,
                "emails_sent": email_sent,
                "smtp_delivered": smtp_delivered
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Failed to send reminders: {str(e)}")

    @router.post("/send-deadline-email")
    def send_deadline_email():
        """Manually trigger mass email broadcast of current platform deadlines to all students and mentors."""
        try:
            from app.email_notifier import trigger_all_deadlines_email
            
            # Fetch active deadlines from Supabase
            deadlines_res = service_client.table("deadlines").select("*").execute()
            rows = deadlines_res.data if deadlines_res and deadlines_res.data else []
            
            if not rows:
                rows = [
                    {"type": "teamFormation", "title": "Team Formation", "description": "Last day to form or join a team.", "due_date": "2026-04-01"},
                    {"type": "proposalUpload", "title": "Proposal Submission", "description": "Last day to submit the project proposal.", "due_date": "2026-04-15"},
                    {"type": "midTerm", "title": "Mid-Term Evaluation", "description": "Mid-term presentation and marking date.", "due_date": "2026-05-15"},
                    {"type": "finalEvaluation", "title": "Final Evaluation", "description": "Final presentation and result date.", "due_date": "2026-06-20"}
                ]
            
            trigger_all_deadlines_email(rows)
            return {"success": True, "message": "Mass deadline announcement emails successfully dispatched."}
        except Exception as e:
            logger.error(f"Failed to send mass deadline email: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to dispatch deadline emails: {str(e)}")

    class SendMentorAssignmentEmailsRequest(BaseModel):
        # None = every mentor with an assigned team; otherwise scope to just
        # this one mentor (and only the teams assigned to them).
        mentor_name: str | None = None
        # Whether to send the mentor-facing "New Project Team Allocation"
        # batch email (one email listing every team in scope for that mentor).
        notify_mentor: bool = True
        # Whether to also send the student-facing "Mentor Allocated" email for
        # every team in scope.
        notify_teams: bool = False

    @router.post("/send-mentor-assignment-emails")
    def send_mentor_assignment_emails(payload: SendMentorAssignmentEmailsRequest = SendMentorAssignmentEmailsRequest()):
        """Manually trigger mentor-team allocation emails. Mentor-assignment
        emails are deliberately NOT sent automatically (see
        notification_agent.py) - an admin sends this once, on demand, after
        allocation is finalized, choosing:
        - everyone or one specific mentor (mentor_name)
        - the mentor(s) (notify_mentor), the team(s)/students (notify_teams),
          or both

        Mentor emails are always one per mentor listing every team in scope,
        never one per team, however many teams that mentor has."""
        if not payload.notify_mentor and not payload.notify_teams:
            raise HTTPException(status_code=400, detail="Select at least one of mentor or team notifications.")
        try:
            from app.email_notifier import trigger_mentor_assigned_batch_email, trigger_mentor_assigned_email

            teams_res = service_client.table("teams_validation").select("id,title,mentor").execute()
            rows = teams_res.data if teams_res and teams_res.data else []

            mentor_batch: dict[str, list[dict]] = {}
            team_info: dict[str, dict] = {}
            for row in rows:
                mentor = row.get("mentor")
                if not mentor or str(mentor).strip() in ("[]", "null", "", "None"):
                    continue
                mentor_list = mentor if isinstance(mentor, list) else None
                if mentor_list is None:
                    try:
                        parsed = json.loads(mentor) if isinstance(mentor, str) else mentor
                        mentor_list = parsed if isinstance(parsed, list) else [parsed]
                    except Exception:
                        mentor_list = [mentor]

                team_id = row.get("id")
                title = row.get("title") or f"Team {team_id}"
                mentor_names = []
                for m in mentor_list:
                    m_name = (m.get("name") or m.get("mentor_name") or m.get("id")) if isinstance(m, dict) else str(m).strip()
                    if m_name and m_name not in ("null", "None", ""):
                        mentor_names.append(m_name)
                        mentor_batch.setdefault(m_name, []).append({"team_id": team_id, "title": title})
                if mentor_names:
                    team_info[team_id] = {"title": title, "mentor_names": mentor_names}

            if payload.mentor_name:
                if payload.mentor_name not in mentor_batch:
                    return {
                        "success": True,
                        "message": f"No teams are currently assigned to {payload.mentor_name}.",
                        "mentors_emailed": [],
                        "teams_emailed": 0,
                    }
                mentor_batch = {payload.mentor_name: mentor_batch[payload.mentor_name]}
                in_scope_ids = {t["team_id"] for t in mentor_batch[payload.mentor_name]}
                team_info = {tid: info for tid, info in team_info.items() if tid in in_scope_ids}

            sent_mentors = []
            if payload.notify_mentor:
                for m_name, m_teams in mentor_batch.items():
                    try:
                        trigger_mentor_assigned_batch_email(m_name, m_teams)
                        sent_mentors.append(m_name)
                    except Exception as mb_err:
                        logger.error(f"Failed to send mass mentor assignment email to {m_name}: {mb_err}")

            sent_teams = 0
            if payload.notify_teams:
                for team_id, info in team_info.items():
                    try:
                        trigger_mentor_assigned_email(team_id, info["title"], info["mentor_names"], notify_mentor=False)
                        sent_teams += 1
                    except Exception as te_err:
                        logger.error(f"Failed to send team allocation email for {team_id}: {te_err}")

            parts = []
            if payload.notify_mentor:
                parts.append(f"{len(sent_mentors)} mentor(s)")
            if payload.notify_teams:
                parts.append(f"{sent_teams} team(s)")
            return {
                "success": True,
                "message": f"Emailed {' and '.join(parts)}.",
                "mentors_emailed": sent_mentors,
                "teams_emailed": sent_teams,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to send mass mentor assignment emails: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to dispatch mentor assignment emails: {str(e)}")

    @router.post("/send-ps-released-email")
    def send_ps_released_email():
        """Manually trigger mass email broadcast announcing that Problem Statements have been released to all students."""
        try:
            from app.email_notifier import trigger_ps_released_email
            trigger_ps_released_email()
            return {"success": True, "message": "Problem Statement release announcement emails successfully dispatched."}
        except Exception as e:
            logger.error(f"Failed to send PS released email: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to dispatch PS release emails: {str(e)}")

    return router


