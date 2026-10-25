from datetime import datetime
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from app.core.config import settings

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


async def send_mail(subject: str, recipients: list[str], body: str) -> None:
    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        body=body,
        subtype=MessageType.plain,
    )
    await _mailer.send_message(message)


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
        f"Regards,\nPMS Admin"
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
        f"Regards,\nPMS Admin"
    )
    await send_mail(subject=subject, recipients=recipients, body=body)


async def send_mentor_allocation_notice(
    recipients: list[str], team_name: str, mentor_name: str
) -> None:
    subject = f"Mentor Allocated – {team_name}"
    body = (
        f"Dear Team {team_name},\n\n"
        f"We are pleased to inform you that your team has been assigned a mentor.\n\n"
        f"Mentor: {mentor_name}\n\n"
        f"Please reach out to your mentor to schedule an introductory meeting.\n\n"
        f"Regards,\nPMS Admin"
    )
    await send_mail(subject=subject, recipients=recipients, body=body)


async def send_presentation_schedule_notice(
    recipients: list[str],
    team_name: str,
    date: str,
    time_slot: str,
    room: str,
) -> None:
    subject = f"Presentation Schedule – {team_name}"
    body = (
        f"Dear Team {team_name},\n\n"
        f"Your presentation has been scheduled. Please find the details below:\n\n"
        f"  Date      : {date}\n"
        f"  Time Slot : {time_slot}\n"
        f"  Room      : {room}\n\n"
        f"Please arrive at least 10 minutes before your scheduled time.\n\n"
        f"Regards,\nPMS Admin"
    )
    await send_mail(subject=subject, recipients=recipients, body=body)


async def send_result_announcement(
    recipients: list[str], team_name: str, total_score: float
) -> None:
    subject = f"Result Announcement – {team_name}"
    body = (
        f"Dear Team {team_name},\n\n"
        f"Your final evaluation results are now available.\n\n"
        f"  Total Score : {total_score:.2f}\n\n"
        f"Please log in to the Student Dashboard for a detailed breakdown.\n\n"
        f"Regards,\nPMS Admin"
    )
    await send_mail(subject=subject, recipients=recipients, body=body)
