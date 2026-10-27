import os
from datetime import datetime
from typing import Optional
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from app.core.config import settings

_mailer: Optional[FastMail] = None


def _get_mailer() -> Optional[FastMail]:
    """Return a cached FastMail instance, or None if email is not configured."""
    global _mailer
    if _mailer is not None:
        return _mailer
    if not settings.MAIL_FROM or "@" not in settings.MAIL_FROM:
        return None
    _mail_config = ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME,
        MAIL_PASSWORD=settings.MAIL_PASSWORD,
        MAIL_FROM=settings.MAIL_FROM,
        MAIL_PORT=settings.MAIL_PORT,
        MAIL_SERVER=settings.MAIL_SERVER,
        MAIL_STARTTLS=settings.MAIL_STARTTLS,
        MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True,
    )
    _mailer = FastMail(_mail_config)
    return _mailer


async def send_mail(subject: str, recipients: list[str], body: str) -> None:
    mailer = _get_mailer()
    if mailer is None:
        return  # Email not configured — silently skip
    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        body=body,
        subtype=MessageType.plain,
    )
    await mailer.send_message(message)


async def send_awareness_mail(recipients: list[str], body: str) -> None:
    subject = "Important Announcement – Project Management System"
    await send_mail(subject=subject, recipients=recipients, body=body)


async def send_proposal_submission_reminder(
    recipients: list[str], deadline: datetime
) -> None:
    subject = "Reminder: Proposal Submission Deadline Approaching"
    body = (
        f"Dear Student,\n\n"
        f"This is a reminder that the proposal submission deadline is "
        f"{deadline.strftime('%B %d, %Y at %I:%M %p')}.\n\n"
        f"Please ensure your team has submitted the proposal before the deadline.\n\n"
        f"Regards,\nProcksi Admin"
    )
    await send_mail(subject=subject, recipients=recipients, body=body)


async def send_team_formation_reminder(
    recipients: list[str], deadline: datetime
) -> None:
    subject = "Reminder: Team Formation Deadline Approaching"
    body = (
        f"Dear Student,\n\n"
        f"This is a reminder that the team formation deadline is "
        f"{deadline.strftime('%B %d, %Y at %I:%M %p')}.\n\n"
        f"Please ensure you have joined or formed a team before the deadline.\n\n"
        f"Regards,\nProcksi Admin"
    )
    await send_mail(subject=subject, recipients=recipients, body=body)


_BTECH_ORDINALS = {1: "1st Year", 2: "2nd Year", 3: "3rd Year", 4: "4th Year", 5: "5th Year"}


def btech_year_label(academic_level=None, semester_number=None) -> Optional[str]:
    """Resolve a 'Nth Year' label from a semester's academic_level (preferred)
    or its semester_number. Returns None when the year genuinely cannot be
    determined — callers must then omit the year rather than guess, because a
    wrong year in an automated mail (e.g. '3rd Year' shown to 2nd-year students)
    is worse than no year at all.
    """
    def _to_int(v):
        try:
            n = int(str(v).strip())
        except (TypeError, ValueError):
            return None
        return n if n > 0 else None

    level = _to_int(academic_level)
    if level:
        return _BTECH_ORDINALS.get(level, f"{level}th Year")

    sem = _to_int(semester_number)
    if sem:
        year = (sem + 1) // 2
        return _BTECH_ORDINALS.get(year, f"{year}th Year")

    return None


def format_clean_team_name(team_id: str, semester_id: str = None, btech_year: str = None) -> str:
    """Formats a raw team_id into a clean team label.

    With an explicit ``btech_year`` ('2nd Year') the result is '2nd Year - Team 101';
    without one it is just 'Team 101' — the year is never guessed. Raw UUIDs
    (e.g. '7681fe4a-4055-4b4c-8512-62771f4a77f0-T76') are always stripped so no
    UUID is ever shown in an email.
    """
    if not team_id:
        return "Team"
    t_str = str(team_id).strip()
    import re

    # 1. Extract UUID if present
    uuid_match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", t_str)
    extracted_uuid = uuid_match.group(0) if uuid_match else None

    prefix = f"{btech_year} - " if btech_year else ""

    # 2. Extract the team number (e.g. '101' or 'T101'). Strip the UUID first so
    #    trailing hex digits of a bare UUID are never mistaken for a team number
    #    (that is how one team's mail ended up labelled with another's number).
    search_str = t_str.replace(extracted_uuid, "").strip(" -_") if extracted_uuid else t_str
    num_match = (
        re.search(r"[-_]?[Tt](\d+)$", search_str, re.IGNORECASE)
        or re.search(r"[-_]?[Tt][Ee][Aa][Mm][-_]?\s*(\d+)$", search_str, re.IGNORECASE)
        or re.search(r"(\d+)$", search_str)
    )

    if num_match:
        team_num = num_match.group(1)
        return f"{prefix}Team {team_num}"

    if extracted_uuid:
        return btech_year or "Team"

    return t_str


async def send_mentor_allocation_notice(
    recipients: list[str], team_name: str, mentor_name: str
) -> None:
    t_name = format_clean_team_name(team_name)
    subject = f"Mentor Allocated – {t_name}"
    body = (
        f"Dear {t_name},\n\n"
        f"We are pleased to inform you that your team has been assigned a mentor.\n\n"
        f"Mentor: {mentor_name}\n\n"
        f"Please reach out to your mentor to schedule an introductory meeting.\n\n"
        f"Regards,\nProcksi Admin"
    )
    await send_mail(subject=subject, recipients=recipients, body=body)


async def send_presentation_schedule_notice(
    recipients: list[str],
    team_name: str,
    date: str,
    time_slot: str,
    room: str,
) -> None:
    t_name = format_clean_team_name(team_name)
    subject = f"Presentation Schedule – {t_name}"
    body = (
        f"Dear {t_name},\n\n"
        f"Your presentation has been scheduled. Please find the details below:\n\n"
        f"  Date      : {date}\n"
        f"  Time Slot : {time_slot}\n"
        f"  Room      : {room}\n\n"
        f"Please arrive at least 10 minutes before your scheduled time.\n\n"
        f"Regards,\nProcksi Admin"
    )
    await send_mail(subject=subject, recipients=recipients, body=body)


async def send_result_announcement(
    recipients: list[str], team_name: str, total_score: float
) -> None:
    t_name = format_clean_team_name(team_name)
    subject = f"Result Announcement – {t_name}"
    body = (
        f"Dear {t_name},\n\n"
        f"Your final evaluation results are now available.\n\n"
        f"  Total Score : {total_score:.2f}\n\n"
        f"Please log in to the Student Dashboard for a detailed breakdown.\n\n"
        f"Regards,\nProcksi Admin"
    )
    await send_mail(subject=subject, recipients=recipients, body=body)


import os
import smtplib
import threading
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("student_email_service")

def send_html_email_async(subject: str, recipients: list[str], html_body: str):
    """Sends email asynchronously in a background thread."""
    def task():
        try:
            server = (os.getenv("MAIL_SERVER") or "smtp.gmail.com").strip()
            user = (os.getenv("MAIL_USERNAME") or os.getenv("MASTER_ADMIN_EMAIL") or "").strip()
            pwd = (os.getenv("MAIL_PASSWORD") or "").replace(" ", "").strip()
            sender = (os.getenv("MAIL_FROM") or user).strip()
            sender_name = (os.getenv("MAIL_FROM_NAME") or "Procksi Portal").strip()
            port = int(os.getenv("MAIL_PORT", "587"))
            
            clean_recipients = list(set(r.strip() for r in recipients if r and "@" in str(r)))
            if not clean_recipients:
                return
            
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{sender}>" if sender_name else sender
            msg["To"] = ", ".join(clean_recipients)
            msg.attach(MIMEText(html_body, "html"))
            
            with smtplib.SMTP(server, port, timeout=20) as s:
                s.starttls()
                if user and pwd:
                    s.login(user, pwd)
                s.sendmail(sender, clean_recipients, msg.as_string())
                
            logger.info(f"Notification email '{subject}' sent successfully to {clean_recipients}")
        except Exception as err:
            logger.error(f"Failed to send notification email: {err}")

    thread = threading.Thread(target=task)
    thread.daemon = True
    thread.start()

def build_professional_email_wrapper(
    title: str,
    recipient_greeting: str,
    main_html: str,
    badge_text: str = "PROCKSI NOTIFICATION",
    action_text: str = None,
    action_url: str = None
) -> str:
    btn_html = ""
    if action_text and action_url:
        btn_html = f"""
        <div style="margin-top: 24px; text-align: center;">
            <a href="{action_url}" target="_blank" style="display: inline-block; background: linear-gradient(135deg, #4f46e5, #7c3aed); color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: bold; font-size: 14px; box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25);">
                {action_text}
            </a>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="table-layout: fixed; background-color: #f8fafc; padding: 30px 10px;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 16px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); padding: 32px 32px 28px 32px; text-align: left; border-bottom: 3px solid #6366f1;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td>
                                        <span style="display: inline-block; padding: 4px 10px; background-color: rgba(99, 102, 241, 0.2); border: 1px solid rgba(99, 102, 241, 0.4); color: #a5b4fc; font-size: 10px; font-weight: 800; border-radius: 6px; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 8px;">
                                            {badge_text}
                                        </span>
                                        <h1 style="color: #ffffff; font-size: 20px; font-weight: 800; margin: 6px 0 0 0; line-height: 1.3;">
                                            {title}
                                        </h1>
                                        <p style="color: #94a3b8; font-size: 12px; margin: 4px 0 0 0; font-weight: 500;">
                                            Procksi • Project Management Platform
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <!-- Body Content -->
                    <tr>
                        <td style="padding: 32px;">
                            <p style="font-size: 15px; font-weight: 700; color: #0f172a; margin-top: 0; margin-bottom: 16px;">
                                {recipient_greeting}
                            </p>
                            <div style="font-size: 14px; line-height: 1.6; color: #334155;">
                                {main_html}
                            </div>
                            {btn_html}
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f1f5f9; padding: 20px 32px; text-align: center; border-top: 1px solid #e2e8f0;">
                            <p style="font-size: 12px; color: #64748b; margin: 0 0 6px 0; font-weight: 600;">
                                Official Automated Communication • Procksi
                            </p>
                            <p style="font-size: 11px; color: #94a3b8; margin: 0;">
                                If you have questions regarding this notification, please contact your department coordinator.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

def get_student_portal_url() -> str:
    return (os.getenv("STUDENT_PORTAL_URL") or "").rstrip("/")

def notify_team_formed(recipients: list[str], team_name: str, leader_name: str, btech_year: str = None):
    if not recipients:
        return
    t_name = format_clean_team_name(team_name, btech_year=btech_year)
    subject = f"Team Formed Successfully - {t_name}"
    body = f"""
    <p>Your project team <b>{t_name}</b> has been created on Procksi by <b>{leader_name}</b>.</p>
    <p>You can now manage team members, reserve problem statements, and submit project proposals from your Student Dashboard.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Team Formation Complete",
        recipient_greeting="Dear Student Team,",
        main_html=body,
        badge_text="TEAM FORMED",
        action_text="View Team Dashboard",
        action_url=f"{get_student_portal_url()}/student/team"
    )
    send_html_email_async(subject, recipients, html_body)

def notify_team_join_invitation(student_email: str, team_name: str, sender_name: str):
    if not student_email or "@" not in str(student_email):
        return
    t_name = format_clean_team_name(team_name)
    subject = f"Team Invitation - Join {t_name}"
    body = f"""
    <p>You have received an invitation from <b>{sender_name}</b> to join project team <b>"{team_name}"</b> ({t_name}).</p>
    <p>Please log in to your Student Portal to review and accept or decline this invitation.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Team Join Invitation",
        recipient_greeting="Dear Student,",
        main_html=body,
        badge_text="TEAM INVITATION",
        action_text="Open Student Portal",
        action_url=f"{get_student_portal_url()}/student/team"
    )
    send_html_email_async(subject, [student_email], html_body)

def notify_student_proposal_submitted(recipients: list[str], team_id: str, title: str):
    if not recipients:
        return
    t_name = format_clean_team_name(team_id)
    subject = f"Custom Proposal Submitted - {t_name}"
    body = f"""
    <p>Your team ({t_name}) has submitted a custom project proposal for admin review:</p>
    <div style="background-color: #f8fafc; border-left: 4px solid #8b5cf6; padding: 16px; margin: 16px 0; border-radius: 6px;">
        <p style="margin: 0; font-weight: bold; font-size: 16px; color: #4c1d95;">"{title}"</p>
    </div>
    <p>The administration will review your submission. You will be notified automatically by email once a decision is recorded.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Custom Proposal Under Review",
        recipient_greeting="Dear Student Team,",
        main_html=body,
        badge_text="PROPOSAL SUBMITTED",
        action_text="View Proposal Status",
        action_url=f"{get_student_portal_url()}/student/team"
    )
    send_html_email_async(subject, recipients, html_body)

def notify_student_topic_reserved(recipients: list[str], team_id: str, title: str, domain: str = "General"):
    if not recipients:
        return
    t_name = format_clean_team_name(team_id)
    subject = f"Problem Statement Reserved - {t_name}"
    body = f"""
    <p>Your team ({t_name}) has reserved the following problem statement for this project semester:</p>
    <div style="background-color: #f8fafc; border-left: 4px solid #6366f1; padding: 16px; margin: 16px 0; border-radius: 6px;">
        <p style="margin: 0 0 8px 0; font-weight: bold; font-size: 16px; color: #1e1b4b;">{title}</p>
        <p style="margin: 0; font-size: 13px; color: #64748b;"><b>Domain:</b> {domain}</p>
    </div>
    <p>Please log in to the Student Portal to proceed with your Project Workspace configuration.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Topic Reservation Confirmed",
        recipient_greeting="Dear Student Team,",
        main_html=body,
        badge_text="TOPIC RESERVED",
        action_text="Open Student Portal",
        action_url=f"{get_student_portal_url()}/student/team"
    )
    send_html_email_async(subject, recipients, html_body)

def notify_student_workspace_updated(recipients: list[str], team_id: str, repo_url: str = None, tech_stack: str = None):
    if not recipients:
        return
    t_name = format_clean_team_name(team_id)
    subject = f"Project Workspace Details Updated - {t_name}"
    repo_html = f"<p style='margin: 4px 0;'><b>Repository URL:</b> <a href='{repo_url}'>{repo_url}</a></p>" if repo_url else ""
    tech_html = f"<p style='margin: 4px 0;'><b>Tech Stack:</b> {tech_stack}</p>" if tech_stack else ""
    
    body = f"""
    <p>Your Project Workspace details for <b>{t_name}</b> have been updated and locked in the system:</p>
    <div style="background-color: #f8fafc; border-left: 4px solid #10b981; padding: 16px; margin: 16px 0; border-radius: 6px;">
        {repo_html}
        {tech_html}
    </div>
    <p>Your faculty mentor and evaluation panel will inspect this repository during milestone reviews.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Workspace Details Updated",
        recipient_greeting="Dear Student Team,",
        main_html=body,
        badge_text="WORKSPACE LOCKED",
        action_text="View Workspace",
        action_url=f"{get_student_portal_url()}/student/team"
    )
    send_html_email_async(subject, recipients, html_body)


