"""
Email utility for sending alerts via SMTP.

Two sender identities are supported:
  - Default (student emails): SMTP_USER / SMTP_FROM / SMTP_PASS / SMTP_FROM_NAME
  - Mentor emails:            SMTP_MENTOR_USER / SMTP_MENTOR_FROM / SMTP_MENTOR_PASS /
                              SMTP_MENTOR_FROM_NAME  (fall back to default vars if not set)

Pass `use_mentor_sender=True` to send_alert_email / send_email_with_attachment
whenever the recipient is a mentor or admin.
"""
from __future__ import annotations

import os
import smtplib
import threading
import time
from email.message import EmailMessage
from typing import Optional, Sequence


class EmailConfigError(RuntimeError):
    pass


_SEND_LOCK = threading.Lock()
_LAST_SEND_TS = 0.0


def _is_weekly_or_leaderboard_subject(subject: str) -> bool:
    """Allow-list subjects for weekly-only email mode."""
    lowered = (subject or "").lower()
    return ("weekly" in lowered) or ("leaderboard" in lowered)


def _enforce_email_mode(subject: str) -> None:
    """Optionally restrict email sending scope via env flag."""
    weekly_only = (_get_env("EMAIL_ONLY_WEEKLY_REPORTS", "false") or "false").lower() == "true"
    if weekly_only and not _is_weekly_or_leaderboard_subject(subject):
        raise EmailConfigError(
            "Email sending is restricted to weekly reports and leaderboard emails "
            "(set EMAIL_ONLY_WEEKLY_REPORTS=false to disable restriction)"
        )


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    return value if value not in ("", None) else default


def _resolve_smtp_config(use_mentor_sender: bool = False):
    """
    Return (host, port, user, password, sender_email, sender_name, use_tls).

    When use_mentor_sender=True the SMTP_MENTOR_* variables are preferred;
    any that are absent fall back to the regular SMTP_* variables so that
    a single SMTP account can still be used if the mentor-specific ones are
    not configured.
    """
    host = _get_env("SMTP_HOST")
    port = int(_get_env("SMTP_PORT", "587") or "587")
    use_tls = (_get_env("SMTP_USE_TLS", "true") or "true").lower() == "true"

    if use_mentor_sender:
        user = _get_env("SMTP_MENTOR_USER") or _get_env("SMTP_USER")
        password = _get_env("SMTP_MENTOR_PASS") or _get_env("SMTP_PASS")
        sender_email = _get_env("SMTP_MENTOR_FROM") or _get_env("SMTP_FROM") or user
        sender_name = _get_env("SMTP_MENTOR_FROM_NAME") or _get_env("SMTP_FROM_NAME", "ProjectFlow")
    else:
        user = _get_env("SMTP_USER")
        password = _get_env("SMTP_PASS")
        sender_email = _get_env("SMTP_FROM") or user
        sender_name = _get_env("SMTP_FROM_NAME", "ProjectFlow")

    return host, port, user, password, sender_email, sender_name, use_tls


def _wait_for_send_slot() -> None:
    """Apply minimum spacing between SMTP sends within this process."""
    global _LAST_SEND_TS

    min_interval = float(_get_env("SMTP_MIN_INTERVAL_SECONDS", "0.35") or "0.35")
    if min_interval <= 0:
        return

    with _SEND_LOCK:
        now = time.monotonic()
        elapsed = now - _LAST_SEND_TS
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _LAST_SEND_TS = time.monotonic()


def _is_retryable_smtp_error(exc: Exception) -> bool:
    """Return True for transient/rate-limit SMTP failures."""
    if isinstance(exc, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, TimeoutError)):
        return True

    if isinstance(exc, smtplib.SMTPResponseException):
        code = int(getattr(exc, "smtp_code", 0) or 0)
        return code in {421, 429, 450, 451, 452, 454}

    error_text = str(exc).lower()
    return "rate limit" in error_text or "too many" in error_text


def _send_message_with_retry(
    *,
    host: str,
    port: int,
    use_tls: bool,
    auth: Optional[tuple[str, str]],
    msg: EmailMessage
) -> None:
    """Send SMTP message with pacing and retry/backoff for transient failures."""
    max_retries = int(_get_env("SMTP_MAX_RETRIES", "3") or "3")
    base_delay = float(_get_env("SMTP_RETRY_BASE_DELAY_SECONDS", "1.0") or "1.0")

    attempt = 0
    while True:
        try:
            _wait_for_send_slot()

            if use_tls:
                with smtplib.SMTP(host, port, timeout=10) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    if auth:
                        server.login(*auth)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=10) as server:
                    server.ehlo()
                    if auth:
                        server.login(*auth)
                    server.send_message(msg)
            return
        except Exception as exc:
            if attempt >= max_retries or not _is_retryable_smtp_error(exc):
                raise

            sleep_seconds = base_delay * (2 ** attempt)
            time.sleep(sleep_seconds)
            attempt += 1


def send_alert_email(
    *,
    subject: str,
    body_text: str,
    to_email: str,
    reply_to: Optional[str] = None,
    bcc: Optional[Sequence[str]] = None,
    html_body: Optional[str] = None,
    use_mentor_sender: bool = False,
) -> None:
    _enforce_email_mode(subject)

    host, port, user, password, sender_email, sender_name, use_tls = _resolve_smtp_config(use_mentor_sender)

    if not host or not sender_email:
        raise EmailConfigError("SMTP_HOST and SMTP_FROM (or SMTP_USER) must be set")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg.set_content(body_text)
    
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    if user and password:
        auth = (user, password)
    else:
        auth = None

    _send_message_with_retry(
        host=host,
        port=port,
        use_tls=use_tls,
        auth=auth,
        msg=msg
    )


def send_email_with_attachment(
    *,
    subject: str,
    body_text: str,
    to_email: str,
    attachment_bytes: bytes,
    attachment_filename: str,
    reply_to: Optional[str] = None,
    additional_attachments: Optional[list] = None,
    html_body: Optional[str] = None,
    use_mentor_sender: bool = False,
) -> None:
    """
    Send an email with PDF attachment(s).

    Args:
        subject: Email subject
        body_text: Email body text
        to_email: Recipient email address
        attachment_bytes: Primary attachment bytes
        attachment_filename: Primary attachment filename
        reply_to: Optional reply-to address
        additional_attachments: Optional list of dicts with 'bytes' and 'filename' keys
        html_body: Optional HTML email body
        use_mentor_sender: If True, use SMTP_MENTOR_* credentials instead of default
    """
    _enforce_email_mode(subject)

    host, port, user, password, sender_email, sender_name, use_tls = _resolve_smtp_config(use_mentor_sender)

    if not host or not sender_email:
        raise EmailConfigError("SMTP_HOST and SMTP_FROM (or SMTP_USER) must be set")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body_text)

    if html_body:
        msg.add_alternative(html_body, subtype="html")

    # Add primary PDF attachment
    msg.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="pdf",
        filename=attachment_filename,
    )
    
    # Add additional attachments if provided
    if additional_attachments:
        for attachment in additional_attachments:
            msg.add_attachment(
                attachment["bytes"],
                maintype="application",
                subtype="pdf",
                filename=attachment["filename"],
            )

    if user and password:
        auth = (user, password)
    else:
        auth = None

    _send_message_with_retry(
        host=host,
        port=port,
        use_tls=use_tls,
        auth=auth,
        msg=msg
    )
