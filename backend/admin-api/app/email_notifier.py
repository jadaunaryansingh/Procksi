import os
import smtplib
import threading
import time
import json
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.main import service_client
from app.team_matching import select_team_rows

from dotenv import load_dotenv, find_dotenv
root_env = find_dotenv() or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
load_dotenv(root_env, override=False)   # override=False: docker-compose env vars always win
if not os.getenv("TWILIO_ACCOUNT_SID"):
    p = r"c:\Users\ARYAN SINGH JADAUN\Desktop\Procksi Latest\.env"
    if os.path.exists(p):
        load_dotenv(p, override=False)

logger = logging.getLogger("email_notifier")

# Enable verbose logging if needed
logging.basicConfig(level=logging.INFO)

# --- Portal URLs (env-overridable, fall back to production live domains) ---
_STUDENT_URL = (os.getenv("STUDENT_PORTAL_URL") or "https://student.procksi.in").rstrip("/")
_PANEL_URL   = (os.getenv("PANEL_PORTAL_URL")   or "https://panel.procksi.in").rstrip("/")
_MENTOR_URL  = (os.getenv("MENTOR_PORTAL_URL")  or "https://mentor.procksi.in").rstrip("/")

def get_supabase_client():
    """Helper to return the initialized Supabase service role client."""
    return service_client

def _send_smtp_chunked(recipients_with_messages: list[dict], chunk_size: int = 50, delay_between_msgs: float = 0.2, delay_between_chunks: float = 3.0):
    """
    Sends SMTP emails using ONE persistent connection for all recipients.
    Reconnects only if Gmail drops the connection mid-send.
    - ONE login total (not one per chunk) — avoids SMTP auth rate limiting
    - NOOP keepalives between chunks to prevent idle disconnection
    - Exponential backoff only on actual disconnects
    recipients_with_messages: list of {"email": str, "msg": MIMEMultipart|str}

    Returns {"sent": [addr, ...], "failed": [{"email": addr, "error": str}, ...]}.
    The counts were previously computed and then thrown away at the final log
    line, which is why a total SMTP outage looked identical to a clean run.
    """
    import ssl as _ssl

    server = (os.getenv("MAIL_SERVER") or "smtp.gmail.com").strip()
    user   = (os.getenv("MAIL_USERNAME") or os.getenv("MASTER_ADMIN_EMAIL") or "").strip()
    pwd    = (os.getenv("MAIL_PASSWORD") or "").replace(" ", "").strip()
    sender = (os.getenv("MAIL_FROM") or user).strip()

    total = len(recipients_with_messages)
    sent_ok: list[str] = []
    failed: list[dict] = []
    if total == 0:
        return {"sent": sent_ok, "failed": failed}

    def _connect():
        """Open ONE authenticated SMTP connection. SSL:465 first, STARTTLS:587 fallback."""
        for use_ssl, try_port in [(True, 465), (False, 587)]:
            try:
                if use_ssl:
                    ctx = _ssl.create_default_context()
                    conn = smtplib.SMTP_SSL(server, try_port, context=ctx, timeout=30)
                else:
                    conn = smtplib.SMTP(server, try_port, timeout=30)
                    conn.ehlo(); conn.starttls(); conn.ehlo()
                if user and pwd:
                    conn.login(user, pwd)
                logger.info(f"SMTP authenticated via {'SSL' if use_ssl else 'STARTTLS'}:{try_port}")
                return conn
            except Exception as e:
                logger.warning(f"SMTP connect ({'SSL' if use_ssl else 'STARTTLS'}:{try_port}) failed: {e}")
        return None

    # Establish the single connection upfront
    s = _connect()
    if s is None:
        logger.error("Could not establish SMTP connection. Aborting bulk send.")
        # Every recipient failed for the same reason -- report them all rather
        # than returning nothing, so the caller can record why.
        return {
            "sent": sent_ok,
            "failed": [{"email": i["email"], "error": "SMTP connection failed"}
                       for i in recipients_with_messages],
        }

    success_count = 0
    for i, item in enumerate(recipients_with_messages):
        global_idx = i + 1
        to_email   = item["email"]
        msg_obj    = item["msg"]

        # Send the message — reconnect once if dropped
        for attempt in range(2):
            try:
                s.sendmail(sender, [to_email],
                           msg_obj.as_string() if hasattr(msg_obj, "as_string") else str(msg_obj))
                success_count += 1
                sent_ok.append(to_email)
                if global_idx % 25 == 0 or global_idx == total:
                    logger.info(f"Batch Email Progress: ({global_idx}/{total}) sent to {to_email}")
                break
            except smtplib.SMTPServerDisconnected:
                if attempt == 0:
                    logger.warning(f"Gmail disconnected at #{global_idx}. Reconnecting...")
                    time.sleep(5)
                    s = _connect()
                    if s is None:
                        logger.error(f"Reconnect failed at #{global_idx}. Skipping remaining.")
                        # Gmail is refusing connections. Report the rest as
                        # failed rather than returning silently.
                        for rest in recipients_with_messages[i:]:
                            failed.append({"email": rest["email"],
                                           "error": "SMTP reconnect failed"})
                        return {"sent": sent_ok, "failed": failed}
                else:
                    logger.error(f"Permanent failure for {to_email} ({global_idx}/{total}) after reconnect.")
                    failed.append({"email": to_email, "error": "disconnected after reconnect"})
            except Exception as e:
                logger.error(f"Send failed for {to_email} ({global_idx}/{total}): {e}")
                failed.append({"email": to_email, "error": str(e)[:300]})
                break

        # Small delay between messages
        if delay_between_msgs > 0:
            time.sleep(delay_between_msgs)

        # Every chunk_size emails: send NOOP to keep connection alive, then pause
        if global_idx % chunk_size == 0 and global_idx < total:
            try:
                s.noop()
                logger.info(f"Chunk keepalive OK at #{global_idx}. Pausing {delay_between_chunks:.0f}s...")
            except Exception:
                logger.warning(f"NOOP failed at #{global_idx}. Reconnecting...")
                time.sleep(3)
                s = _connect()
                if s is None:
                    logger.error("Could not reconnect after NOOP failure. Stopping.")
                    for rest in recipients_with_messages[global_idx:]:
                        failed.append({"email": rest["email"],
                                       "error": "SMTP reconnect failed after keepalive"})
                    break
            time.sleep(delay_between_chunks)

    try:
        s.quit()
    except Exception:
        pass

    logger.info(f"Batch Email Dispatch Completed: {success_count}/{total} emails sent successfully.")
    return {"sent": sent_ok, "failed": failed}


# Global lock — prevents multiple concurrent bulk-send jobs from hammering Gmail simultaneously
_bulk_send_lock = threading.Lock()


def send_smtp_now(subject: str, recipients: list[str], html_body: str) -> dict:
    """Send synchronously and return {"sent": [...], "failed": [...]}.

    The blocking twin of send_smtp_async, for callers that need to record what
    actually happened. send_smtp_async keeps the fire-and-forget behaviour for
    the notification triggers, which run inside a request and must not block it.
    """
    clean = list({r.strip() for r in recipients if r and "@" in str(r)})
    if not clean:
        return {"sent": [], "failed": []}

    sender = (os.getenv("MAIL_FROM") or os.getenv("MAIL_USERNAME") or os.getenv("MASTER_ADMIN_EMAIL") or "").strip()
    sender_name = (os.getenv("MAIL_FROM_NAME") or "Procksi Portal").strip()
    items = []
    for r in clean:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{sender}>" if sender_name else sender
        msg["To"] = r
        msg.attach(MIMEText(html_body, "html"))
        items.append({"email": r, "msg": msg})

    with _bulk_send_lock:
        return _send_smtp_chunked(items) or {"sent": [], "failed": []}


def send_smtp_async(subject: str, recipients: list[str], html_body: str):
    """Sends email asynchronously in a background thread using chunked SMTP dispatch.
    A global lock ensures only ONE bulk send runs at a time — prevents Gmail rate-limit blocks
    caused by multiple concurrent send jobs.

    Fire-and-forget: the result is logged, not returned. Callers that need to
    know the outcome should use send_smtp_now instead.
    """
    def task():
        if not _bulk_send_lock.acquire(blocking=False):
            logger.warning(f"Bulk email send already in progress — skipping duplicate trigger for '{subject}'.")
            return
        try:
            clean_recipients = list(set(r.strip() for r in recipients if r and "@" in str(r)))
            if not clean_recipients:
                logger.info(f"No valid recipient email addresses found for '{subject}'. Skipping send.")
                return

            sender = (os.getenv("MAIL_FROM") or os.getenv("MAIL_USERNAME") or os.getenv("MASTER_ADMIN_EMAIL") or "").strip()
            sender_name = (os.getenv("MAIL_FROM_NAME") or "Procksi Portal").strip()

            items_to_send = []
            for r in clean_recipients:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = f"{sender_name} <{sender}>" if sender_name else sender
                msg["To"] = r
                msg.attach(MIMEText(html_body, "html"))
                items_to_send.append({"email": r, "msg": msg})

            logger.info(f"Starting bulk send: '{subject}' to {len(items_to_send)} recipients.")
            _send_smtp_chunked(items_to_send)
        finally:
            _bulk_send_lock.release()

    thread = threading.Thread(target=task)
    thread.daemon = True
    thread.start()

def get_student_emails_in_team(team_id: str) -> list[str]:
    """Retrieves all member emails of a specific team by looking up student IDs or emails in teams_validation and students table."""
    emails = set()
    try:
        res = service_client.table("teams_validation").select("*").execute()
        rows, how = select_team_rows(res.data, team_id)
        if not rows:
            # This used to fall back to *every* team when the id didn't match,
            # which turned a team-scoped notification (and email) into a
            # platform-wide broadcast. Resolve to nobody instead, and log it —
            # a miss should be visible, not silently mis-delivered.
            logger.warning(
                "No team matched id %r (%s) among %d teams — notifying nobody.",
                team_id, how, len(res.data or []),
            )
            return []

        for row in rows:
            raw_members = row.get("members") or []
            if isinstance(raw_members, str):
                try:
                    members = json.loads(raw_members)
                except Exception:
                    members = []
            else:
                members = raw_members
                
            student_ids = []
            for m in (members or []):
                if isinstance(m, dict):
                    if m.get("email") and "@" in str(m.get("email")):
                        emails.add(str(m.get("email")).strip())
                    sid = m.get("id") or m.get("student_id") or m.get("roll") or m.get("roll_number")
                    if sid:
                        student_ids.append(str(sid).strip())
                elif m:
                    m_str = str(m).strip()
                    if "@" in m_str:
                        emails.add(m_str)
                    else:
                        student_ids.append(m_str)
                    
            if student_ids:
                # Query students by id
                try:
                    std_res = service_client.table("students").select("email").in_("id", student_ids).execute()
                    if std_res.data:
                        for s in std_res.data:
                            if s.get("email"):
                                emails.add(str(s["email"]).strip())
                except Exception as ex1:
                    logger.warning(f"Student lookup by id failed: {ex1}")
                    
                # Also try matching student_id column if id is different
                try:
                    std_roll_res = service_client.table("students").select("email").in_("student_id", student_ids).execute()
                    if std_roll_res.data:
                        for s in std_roll_res.data:
                            if s.get("email"):
                                emails.add(str(s["email"]).strip())
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Error fetching student emails for team {team_id}: {e}")
    return list(emails)

def get_student_email_by_roll(roll: str) -> list[str]:
    """Look up a single student's email address by their Roll Number / Student ID or raw Email."""
    if not roll:
        return []
    roll_str = str(roll).strip()
    if "@" in roll_str:
        return [roll_str]
    try:
        res = service_client.table("students").select("email").eq("id", roll_str).execute()
        if res.data and res.data[0].get("email"):
            return [res.data[0]["email"].strip()]
        
        res_roll = service_client.table("students").select("email").eq("student_id", roll_str).execute()
        if res_roll.data and res_roll.data[0].get("email"):
            return [res_roll.data[0]["email"].strip()]
    except Exception as e:
        logger.error(f"Error fetching email for student {roll}: {e}")
    return []

def get_mentor_emails(mentor_names: list[str]) -> list[str]:
    """Retrieves emails for the given mentor names or emails."""
    emails = set()
    try:
        all_mentors_res = service_client.table("mentors").select("*").execute()
        all_mentors = all_mentors_res.data or []
    except Exception:
        all_mentors = []

    for name in (mentor_names or []):
        if not name:
            continue
        n_str = str(name).strip()
        if "@" in n_str:
            emails.add(n_str)
            continue
        
        matched = False
        for m in all_mentors:
            m_name = str(m.get("name") or "").strip().lower()
            m_id = str(m.get("id") or "").strip().lower()
            m_email = str(m.get("email") or "").strip()
            if n_str.lower() in m_name or m_name in n_str.lower() or n_str.lower() == m_id:
                if m_email and "@" in m_email:
                    emails.add(m_email)
                    matched = True

        if not matched:
            try:
                res = service_client.table("mentors").select("email").ilike("name", f"%{n_str}%").execute()
                if res.data:
                    for m in res.data:
                        if m.get("email"):
                            emails.add(m["email"].strip())
            except Exception as e:
                logger.error(f"Error fetching mentor email for {n_str}: {e}")
    return list(emails)

def get_all_student_emails() -> list[str]:
    """Retrieves all student email addresses registered in the system."""
    emails = set()
    try:
        res = service_client.table("students").select("email").execute()
        if res.data:
            for r in res.data:
                if r.get("email") and "@" in str(r.get("email")):
                    emails.add(str(r.get("email")).strip())
    except Exception as e:
        logger.error(f"Error fetching all student emails: {e}")
    return list(emails)

def get_all_mentor_emails() -> list[str]:
    """Retrieves all mentor email addresses registered in the system."""
    emails = set()
    try:
        res = service_client.table("mentors").select("email").execute()
        if res.data:
            for r in res.data:
                if r.get("email") and "@" in str(r.get("email")):
                    emails.add(str(r.get("email")).strip())
    except Exception as e:
        logger.error(f"Error fetching all mentor emails: {e}")
    return list(emails)





def parse_markdown_formatting(text: str) -> str:
    """Converts **bold**, *italic*, and [link](url) markdown syntax into standard HTML tags for email delivery."""
    if not text:
        return ""
    import re
    # 1. Convert list item bullet markers (* item, - item, + item) at start of line to bullet character
    text = re.sub(r'(?m)^[ \t]*[*+-][ \t]+', '• ', text)
    # 2. Bold: **text** or __text__ -> <strong>text</strong> (multiline support via re.DOTALL)
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text, flags=re.DOTALL)
    text = re.sub(r'__(.*?)__', r'<strong>\1</strong>', text, flags=re.DOTALL)
    # 3. Italic: *text* or _text_ -> <em>text</em> (only when not adjacent to whitespace or word char)
    text = re.sub(r'(?<!\w|\*)\*([^\s*][^*]*?)\*(?!\w|\*)', r'<em>\1</em>', text)
    text = re.sub(r'(?<!\w|_)_([^\s_][^_]*?)_(?!\w|_)', r'<em>\1</em>', text)
    # 4. Markdown links: [title](url) -> <a href="url"...>title</a>
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2" target="_blank" style="color: #4f46e5; font-weight: bold; text-decoration: underline;">\1</a>', text)
    return text


def build_professional_email_wrapper(
    title: str,
    recipient_greeting: str,
    main_html: str,
    badge_text: str = "PROCKSI NOTIFICATION",
    badge_color: str = "#4f46e5",
    action_text: str = None,
    action_url: str = None
) -> str:
    title = parse_markdown_formatting(title)
    recipient_greeting = parse_markdown_formatting(recipient_greeting)
    main_html = parse_markdown_formatting(main_html)

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
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <title>{title}</title>
    <style>
        :root {{
            color-scheme: light dark;
            supported-color-schemes: light dark;
        }}
        @media (prefers-color-scheme: dark) {{
            .email-header-title {{
                color: #ffffff !important;
            }}
            .email-header-subtitle {{
                color: #cbd5e1 !important;
            }}
            .email-badge {{
                color: #a5b4fc !important;
                border-color: rgba(99, 102, 241, 0.6) !important;
                background-color: rgba(99, 102, 241, 0.3) !important;
            }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="table-layout: fixed; background-color: #f8fafc; padding: 30px 10px;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 16px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);">
                    <!-- Header -->
                    <tr>
                        <td style="background-color: #0f172a; padding: 32px 32px 28px 32px; text-align: left; border-bottom: 3px solid #6366f1;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td>
                                        <span class="email-badge" style="display: inline-block; padding: 4px 10px; background-color: rgba(99, 102, 241, 0.2); border: 1px solid rgba(99, 102, 241, 0.4); color: #a5b4fc !important; font-size: 10px; font-weight: 800; border-radius: 6px; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 8px;">
                                            {badge_text}
                                        </span>
                                        <h1 class="email-header-title" style="color: #ffffff !important; font-size: 20px; font-weight: 800; margin: 6px 0 0 0; line-height: 1.3;">
                                            {title}
                                        </h1>
                                        <p class="email-header-subtitle" style="color: #94a3b8 !important; font-size: 12px; margin: 4px 0 0 0; font-weight: 500;">
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


def wrap_communication_email(
    subject: str,
    raw_body: str,
    badge_text: str = None,
    action_text: str = None,
    action_url: str = None,
    include_portal_button: bool = False
) -> str:
    """
    Wraps any communication subject and body into the official Procksi email template design.
    Matches the dark navy header (#0f172a), pill badge, white card body, and signature block.
    """
    if not raw_body:
        raw_body = ""

    if include_portal_button and not action_text:
        action_text = "Open Procksi"
        action_url = _STUDENT_URL

    # If already a complete HTML document, return as-is
    if "<!doctype html" in raw_body.lower() or "<html" in raw_body.lower():
        return parse_markdown_formatting(raw_body)

    lines = [line.strip() for line in raw_body.split("\n") if line.strip()]
    greeting = "Dear Student,"
    body_paragraphs = []

    for line in lines:
        l_lower = line.lower()
        if (l_lower.startswith("dear ") or l_lower.startswith("greetings") or l_lower.startswith("hello")) and len(line) < 60:
            greeting = line
        elif l_lower.startswith("regards,") or l_lower.startswith("best regards,") or l_lower == "procksi admin" or l_lower == "regards" or l_lower == "thank you.":
            continue
        else:
            body_paragraphs.append(line)

    if not body_paragraphs:
        body_paragraphs = lines

    html_paragraphs = []
    for p in body_paragraphs:
        p_formatted = parse_markdown_formatting(p)
        if not p_formatted.startswith("<p") and not p_formatted.startswith("<div"):
            html_paragraphs.append(f'<p style="margin-top: 0; margin-bottom: 16px; line-height: 1.6; color: #334155;">{p_formatted}</p>')
        else:
            html_paragraphs.append(p_formatted)

    html_content = "".join(html_paragraphs)

    if not badge_text:
        s_lower = (subject or "").lower()
        if "welcome" in s_lower:
            badge_text = "WELCOME TO PROCKSI"
        elif "proposal" in s_lower:
            badge_text = "PROPOSAL UPDATE"
        elif "team" in s_lower:
            badge_text = "TEAM FORMATION"
        elif "mentor" in s_lower:
            badge_text = "MENTOR ALLOCATION"
        elif "deadline" in s_lower or "reminder" in s_lower:
            badge_text = "DEADLINE REMINDER"
        elif "schedule" in s_lower or "presentation" in s_lower:
            badge_text = "PRESENTATION SCHEDULE"
        elif "result" in s_lower or "score" in s_lower:
            badge_text = "EVALUATION RESULTS"
        else:
            badge_text = "PROCKSI NOTIFICATION"

    return build_professional_email_wrapper(
        title=subject,
        recipient_greeting=greeting,
        main_html=html_content,
        badge_text=badge_text.upper(),
        action_text=action_text,
        action_url=action_url
    )


_cached_btech_years = {}

def format_year_ordinal(yr) -> str:
    if not yr:
        return ""
    s = str(yr).strip().lower()
    if "1st" in s or s == "1":
        return "1st Year"
    if "2nd" in s or s == "2":
        return "2nd Year"
    if "3rd" in s or s == "3":
        return "3rd Year"
    if "4th" in s or s == "4" or "final" in s:
        return "4th Year"
    import re
    m = re.search(r"([1-4])", s)
    if m:
        digit = m.group(1)
        ord_map = {"1": "1st Year", "2": "2nd Year", "3": "3rd Year", "4": "4th Year"}
        return ord_map.get(digit, f"{digit}th Year")
    return s.title() if "year" in s else f"{s} Year"


def get_btech_year(semester_id: str = None) -> str:
    global _cached_btech_years
    if semester_id and semester_id in _cached_btech_years:
        return _cached_btech_years[semester_id]
    
    try:
        from app.main import service_client
        if semester_id:
            res = service_client.table("semester_config").select("year, academic_year, name").eq("id", semester_id).execute()
            if res.data:
                row = res.data[0]
                raw_yr = row.get("year") or row.get("academic_year") or row.get("name")
                formatted = format_year_ordinal(raw_yr)
                if formatted:
                    _cached_btech_years[semester_id] = formatted
                    return formatted
        
        active_res = service_client.table("semester_config").select("year, academic_year, name").eq("is_active", True).execute()
        if active_res.data:
            row = active_res.data[0]
            raw_yr = row.get("year") or row.get("academic_year") or row.get("name")
            formatted = format_year_ordinal(raw_yr)
            if formatted:
                if semester_id:
                    _cached_btech_years[semester_id] = formatted
                return formatted
    except Exception:
        pass

    return "3rd Year"


def format_clean_team_name(team_id: str, semester_id: str = None) -> str:
    """Formats raw team_id into clean BTech Year and Team No label (e.g. '3rd Year - Team 101').
    Strips raw UUIDs (e.g., 'c1707ba6-d426-4dcb-a23f-aa22c1bb11c9-T101' or 'c1707ba6...') so no raw UUID hex is ever shown.
    """
    if not team_id:
        return "Team"
    t_str = str(team_id).strip()
    import re
    
    # 1. Extract UUID if present
    uuid_match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", t_str)
    extracted_uuid = uuid_match.group(0) if uuid_match else None

    # Get BTech year (1st Year, 2nd Year, 3rd Year, 4th Year)
    btech_year = get_btech_year(extracted_uuid or semester_id)

    # 2. Extract the team number (e.g. '101' or 'T101')
    num_match = (
        re.search(r"[-_]?[Tt](\d+)$", t_str, re.IGNORECASE)
        or re.search(r"[-_]?[Tt][Ee][Aa][Mm][-_]?\s*(\d+)$", t_str, re.IGNORECASE)
        or re.search(r"[-_](\d+)$", t_str)
    )

    if num_match:
        team_num = num_match.group(1)
        return f"{btech_year} - Team {team_num}"
    
    digits = re.sub(r"\D", "", t_str)
    if digits:
        team_num = digits[-3:] if len(digits) >= 3 else digits
        return f"{btech_year} - Team {team_num}"

    return f"{btech_year} - Team 1"



def trigger_ps_reserved_email(team_id: str, title: str, domain: str = "General"):
    """Sends email notifications to team members when a problem statement is reserved."""
    recipients = get_student_emails_in_team(team_id)
    if not recipients:
        return
    
    t_name = format_clean_team_name(team_id)
    subject = f"Problem Statement Reserved - {t_name}"
    body = f"""
    <p>Your team ({t_name}) has successfully reserved the following problem statement for this project semester:</p>
    <div style="background-color: #f8fafc; border-left: 4px solid #6366f1; padding: 16px; margin: 16px 0; border-radius: 6px;">
        <p style="margin: 0 0 8px 0; font-weight: bold; font-size: 16px; color: #1e1b4b;">{title}</p>
        <p style="margin: 0; font-size: 13px; color: #64748b;"><b>Domain:</b> {domain}</p>
    </div>
    <p>Please log in to the Student Portal to proceed with your Project Workspace configuration and milestone tasks.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Topic Reservation Confirmed",
        recipient_greeting="Dear Student Team,",
        main_html=body,
        badge_text="TOPIC RESERVED",
        action_text="Open Student Portal",
        action_url=f"{_STUDENT_URL}/student/team"
    )
    send_smtp_async(subject, recipients, html_body)

def trigger_slot_reminder_email_5m(recipients: list[str], team_id: str, slot_time: str, phone_numbers: list[str] = None):
    """Sends 1st reminder email (at +5m) to assigned panelist/mentor with Twilio fallback."""
    t_name = format_clean_team_name(team_id)
    subject = f"REMINDER: Presentation Slot Started 5 Mins Ago - {t_name}"
    body = f"""
    <p>This is a reminder that your scheduled evaluation presentation for <b>{t_name}</b> started 5 minutes ago ({slot_time}).</p>
    <div style="background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 16px; margin: 16px 0; border-radius: 6px;">
        <p style="margin: 0; font-weight: bold; color: #92400e;">Action Required: Please join your evaluation session on the Panel Portal.</p>
    </div>
    """
    html_body = build_professional_email_wrapper(
        title="Presentation Slot Starting Reminder (+5m)",
        recipient_greeting="Dear Faculty Evaluator,",
        main_html=body,
        badge_text="SLOT REMINDER 5M",
        badge_color="#f59e0b",
        action_text="Open Panel Portal",
        action_url=f"{_PANEL_URL}/panel"
    )
    send_smtp_async(subject, recipients or [], html_body)

def trigger_slot_reminder_email_10m(recipients: list[str], team_id: str, slot_time: str, phone_numbers: list[str] = None):
    """Sends 2nd urgent reminder email (at +10m) to assigned panelist/mentor with Twilio fallback."""
    t_name = format_clean_team_name(team_id)
    subject = f"URGENT: Presentation Slot Delayed by 10 Mins - {t_name}"
    body = f"""
    <p><b>URGENT ALERT:</b> The evaluation presentation for <b>{t_name}</b> scheduled at {slot_time} is delayed by 10 minutes.</p>
    <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 16px; margin: 16px 0; border-radius: 6px;">
        <p style="margin: 0; font-weight: bold; color: #991b1b;">Students and panel members are awaiting session commencement.</p>
    </div>
    <p>Note: An automated phone call reminder will be triggered if the session is not initiated within 5 minutes.</p>
    """
    html_body = build_professional_email_wrapper(
        title="URGENT: Presentation Delayed (+10m)",
        recipient_greeting="Dear Faculty Evaluator,",
        main_html=body,
        badge_text="SLOT DELAYED 10M",
        badge_color="#ef4444",
        action_text="Join Evaluation Now",
        action_url=f"{_PANEL_URL}/panel"
    )
    send_smtp_async(subject, recipients or [], html_body)

def trigger_proposal_submitted_email(team_id: str, title: str):
    """Sends email notifications to team members when a custom proposal is submitted."""
    recipients = get_student_emails_in_team(team_id)
    if not recipients:
        return
    
    t_name = format_clean_team_name(team_id)
    subject = f"Custom Proposal Submitted - {t_name}"
    body = f"""
    <p>Your team ({t_name}) has submitted a custom project proposal for admin review:</p>
    <div style="background-color: #f8fafc; border-left: 4px solid #8b5cf6; padding: 16px; margin: 16px 0; border-radius: 6px;">
        <p style="margin: 0; font-weight: bold; font-size: 16px; color: #4c1d95;">"{title}"</p>
    </div>
    <p>The administration will review your proposal submission. You will be notified automatically by email once a decision has been recorded.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Custom Proposal Under Review",
        recipient_greeting="Dear Student Team,",
        main_html=body,
        badge_text="PROPOSAL SUBMITTED",
        action_text="View Proposal Status",
        action_url=f"{_STUDENT_URL}/student/team"
    )
    send_smtp_async(subject, recipients, html_body)

def trigger_workspace_updated_email(team_id: str, repo_url: str = None, tech_stack: str = None):
    """Sends email notifications when a team updates repository URL or tech stack."""
    recipients = get_student_emails_in_team(team_id)
    if not recipients:
        return
    
    t_name = format_clean_team_name(team_id)
    subject = f"Project Workspace Updated - {t_name}"
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
        action_url=f"{_STUDENT_URL}/student/team"
    )
    send_smtp_async(subject, recipients, html_body)

def trigger_proposal_email(team_id: str, status: str, title: str, remarks: str = None):
    """Sends email notifications to team members when their proposal status changes (approval, rejection, revision, resubmit)."""
    recipients = get_student_emails_in_team(team_id)
    if not recipients:
        return
    
    t_name = format_clean_team_name(team_id)
    st_clean = str(status or "").strip().lower()

    if st_clean in ("approved", "accepted", "valid"):
        status_text = "Approved"
        color_badge = "#10b981"
        main_msg = f'<p>Your custom project proposal <b>"{title}"</b> for <b>{t_name}</b> has been officially <b>APPROVED</b> by the project administration.</p><p>You can now proceed with setting up your project workspace, repository URL, and technology stack.</p>'
        if remarks:
            main_msg += f'<div style="background-color: #f0fdf4; border-left: 4px solid #10b981; padding: 12px; margin: 12px 0; border-radius: 6px;"><p style="margin: 0; color: #166534; font-size: 13px;"><b>Admin Remarks:</b> {remarks}</p></div>'

    elif st_clean in ("rejected",):
        status_text = "Rejected"
        color_badge = "#ef4444"
        main_msg = f'<p>Your custom project proposal <b>"{title}"</b> for <b>{t_name}</b> was <b>NOT APPROVED</b> by the project administration.</p><p>Please log in to the student portal to review feedback and select a standard problem statement from the list before the deadline.</p>'
        if remarks:
            main_msg += f'<div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 12px; margin: 12px 0; border-radius: 6px;"><p style="margin: 0; color: #991b1b; font-size: 13px;"><b>Admin Remarks:</b> {remarks}</p></div>'

    elif st_clean in ("revision", "revision_requested", "revision requested", "resubmit"):
        status_text = "Revision Requested"
        color_badge = "#f59e0b"
        main_msg = f'<p>The project administration has requested a <b>REVISION</b> for your custom proposal <b>"{title}"</b> ({t_name}).</p><p>Please update your proposal according to the administrator comments and resubmit it on the portal.</p>'
        if remarks:
            main_msg += f'<div style="background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 12px; margin: 12px 0; border-radius: 6px;"><p style="margin: 0; color: #92400e; font-size: 13px;"><b>Admin Remarks:</b> {remarks}</p></div>'

    elif st_clean in ("resubmitted", "submitted"):
        status_text = "Resubmitted"
        color_badge = "#6366f1"
        main_msg = f'<p>Your custom project proposal <b>"{title}"</b> for <b>{t_name}</b> has been successfully <b>RESUBMITTED</b> for admin review.</p><p>The administration will review your proposal update shortly.</p>'

    else:
        status_text = status.title()
        color_badge = "#6366f1"
        main_msg = f'<p>Your custom project proposal <b>"{title}"</b> status has been updated to <b>{status_text}</b>.</p>'

    subject = f"Project Proposal {status_text} - {t_name}"
    html_body = build_professional_email_wrapper(
        title=f"Proposal Update: {status_text}",
        recipient_greeting="Dear Student Team,",
        main_html=main_msg,
        badge_text=f"PROPOSAL {status_text.upper()}",
        badge_color=color_badge,
        action_text="View Proposal Status",
        action_url=f"{_STUDENT_URL}/student/team"
    )
    send_smtp_async(subject, recipients, html_body)

def trigger_ps_allocated_email(team_id: str, title: str, description: str, domain: str):
    """Sends email notifications to team members when a project/PS is allocated."""
    recipients = get_student_emails_in_team(team_id)
    if not recipients:
        return
    
    t_name = format_clean_team_name(team_id)
    subject = f"Project/PS Allocated - {t_name}"
    body = f"""
    <p>The administration has officially allocated project / problem statement details for <b>{t_name}</b>:</p>
    <div style="background-color: #f8fafc; border-left: 4px solid #10b981; padding: 16px; margin: 16px 0; border-radius: 6px;">
        <p style="margin: 0 0 6px 0; font-weight: bold; font-size: 16px; color: #065f46;">{title}</p>
        <p style="margin: 0 0 6px 0; font-size: 13px; color: #475569;"><b>Domain:</b> {domain}</p>
        <p style="margin: 0; font-size: 13px; color: #475569;"><b>Description:</b> {description}</p>
    </div>
    <p>Log in to the Student Portal to check your milestones and start submitting updates.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Project Statement Allocated",
        recipient_greeting="Dear Student Team,",
        main_html=body,
        badge_text="PROJECT ALLOCATED",
        action_text="View Allocated Topic",
        action_url=f"{_STUDENT_URL}/student/team"
    )
    send_smtp_async(subject, recipients, html_body)

def trigger_mentor_assigned_email(team_id: str, title: str, mentor_names: list[str], notify_mentor: bool = True):
    """Sends emails to team members and assigned mentor(s) when mentor allocation occurs.

    notify_mentor=False skips the mentor-facing email: a caller processing many
    team rows in one batch (e.g. an auto-assign run) calls this once per team
    for the student side, but sends ONE consolidated mentor email afterward via
    trigger_mentor_assigned_batch_email instead of one per team.
    """
    student_recipients = get_student_emails_in_team(team_id)
    mentor_recipients = get_mentor_emails(mentor_names) if notify_mentor else []

    t_name = format_clean_team_name(team_id)
    m_names_str = ', '.join(mentor_names)
    if student_recipients:
        student_subj = f"Mentor Allocated - {t_name}"
        body = f"""
        <p>Your team ({t_name}) working on project <b>"{title}"</b> has been allocated a faculty mentor:</p>
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 16px; border-radius: 8px; margin: 16px 0;">
            <p style="margin: 0; font-size: 16px; font-weight: bold; color: #166534;">{m_names_str}</p>
        </div>
        <p>Please contact your faculty mentor to schedule your guidance meetings and review project milestones.</p>
        """
        html_body = build_professional_email_wrapper(
            title="Faculty Mentor Allocated",
            recipient_greeting="Dear Student Team,",
            main_html=body,
            badge_text="MENTOR ALLOCATED",
            action_text="View Mentor Details",
            action_url=f"{_STUDENT_URL}/student/team"
        )
        send_smtp_async(student_subj, student_recipients, html_body)
        
    if mentor_recipients:
        mentor_subj = f"New Project Team Allocation - {t_name}"
        m_body = f"""
        <p>You have been allocated to supervise project team <b>"{title}"</b> ({t_name}).</p>
        <p>Log in to the Mentor Portal to view their student details, milestone progress, and start grading evaluations.</p>
        """
        html_body = build_professional_email_wrapper(
            title="New Mentoring Allocation",
            recipient_greeting=f"Dear {m_names_str},",
            main_html=m_body,
            badge_text="FACULTY ALLOCATION",
            action_text="Open Mentor Portal",
            action_url=f"{_MENTOR_URL}/mentor"
        )
        send_smtp_async(mentor_subj, mentor_recipients, html_body)

def trigger_mentor_assigned_batch_email(mentor_name: str, teams: list[dict]):
    """Sends ONE email to a mentor listing every team allocated to them in this
    batch, instead of one email per team. An auto-assign run (or any bulk
    allocation) can hand a single mentor dozens of teams at once; sending a
    separate "New Project Team Allocation" email per team made that
    unreadable, so every team assigned to the same mentor within one
    notification pass is grouped here into a single message.

    teams: list of {"team_id": str, "title": str}
    """
    if not teams:
        return
    mentor_recipients = get_mentor_emails([mentor_name])
    if not mentor_recipients:
        return

    rows_html = "".join(
        f"""
        <tr>
            <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-weight: bold; color: #166534;">{format_clean_team_name(t.get('team_id'))}</td>
            <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; color: #334155;">{t.get('title') or 'Untitled Project'}</td>
        </tr>
        """
        for t in teams
    )
    team_word = "team" if len(teams) == 1 else "teams"
    m_body = f"""
    <p>You have been allocated to supervise the following {len(teams)} project {team_word}:</p>
    <table style="width: 100%; border-collapse: collapse; margin: 16px 0; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
        <thead>
            <tr style="background-color: #f0fdf4;">
                <th style="padding: 10px 12px; text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: #166534;">Team</th>
                <th style="padding: 10px 12px; text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: #166534;">Project Title</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    <p>Log in to the Mentor Portal to view each team's student details, milestone progress, and start grading evaluations.</p>
    """
    html_body = build_professional_email_wrapper(
        title="New Mentoring Allocations",
        recipient_greeting=f"Dear {mentor_name},",
        main_html=m_body,
        badge_text="FACULTY ALLOCATION",
        action_text="Open Mentor Portal",
        action_url=f"{_MENTOR_URL}/mentor"
    )
    send_smtp_async(f"New Project Team Allocation ({len(teams)} {team_word})", mentor_recipients, html_body)

def trigger_team_created_email(team_id: str, title: str):
    """Sends email notifications to team members when a team is formed."""
    recipients = get_student_emails_in_team(team_id)
    if not recipients:
        return
    
    t_name = format_clean_team_name(team_id)
    subject = f"Team Formed - {title}"
    body = f"""
    <p>Your team <b>"{title}"</b> ({t_name}) has been created on Procksi.</p>
    <p>You can now manage team members, select problem statements, and track project deadlines on the Student Portal.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Team Created Successfully",
        recipient_greeting="Dear Student Team,",
        main_html=body,
        badge_text="TEAM FORMED",
        action_text="View Team Portal",
        action_url=f"{_STUDENT_URL}/student/team"
    )
    send_smtp_async(subject, recipients, html_body)

def trigger_team_approved_email(team_id: str, title: str):
    """Sends email notifications to team members when their team is approved/validated."""
    recipients = get_student_emails_in_team(team_id)
    if not recipients:
        return
    
    t_name = format_clean_team_name(team_id)
    subject = f"Team Approved - {t_name}"
    body = f"""
    <p>Your team registration for <b>"{title}"</b> ({t_name}) has been validated and approved by the project administration.</p>
    <p>You can now check milestones, view mentor assignments, or submit custom proposals on the portal.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Team Registration Validated",
        recipient_greeting="Dear Student Team,",
        main_html=body,
        badge_text="TEAM VALIDATED",
        action_text="View Dashboard",
        action_url=f"{_STUDENT_URL}/student/team"
    )
    send_smtp_async(subject, recipients, html_body)

def trigger_slot_scheduled_email(team_id: str, date: str, time: str, room: str, meet_link: str = None):
    """Sends evaluation schedule slot notification to team members."""
    recipients = get_student_emails_in_team(team_id)
    if not recipients:
        return
        
    t_name = format_clean_team_name(team_id)
    subject = f"Evaluation Presentation Scheduled - {t_name}"
    meet_section = f'<p style="margin: 8px 0 0 0;"><b>Meet Link:</b> <a href="{meet_link}" target="_blank">{meet_link}</a></p>' if meet_link and str(meet_link).strip() not in ("", "null", "None") else ''
    
    body = f"""
    <p>Your upcoming evaluation presentation for <b>{t_name}</b> has been scheduled by the administration:</p>
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 8px; margin: 16px 0;">
        <p style="margin: 0 0 6px 0;"><b>Date:</b> {date}</p>
        <p style="margin: 0 0 6px 0;"><b>Time Slot:</b> {time}</p>
        <p style="margin: 0 0 6px 0;"><b>Venue / Room:</b> {room}</p>
        {meet_section}
    </div>
    <p>Please ensure all team members are present on time for evaluation.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Evaluation Slot Scheduled",
        recipient_greeting="Dear Student Team,",
        main_html=body,
        badge_text="PRESENTATION SCHEDULE",
        action_text="View Presentation Details",
        action_url=f"{_STUDENT_URL}/student/team"
    )
    send_smtp_async(subject, recipients, html_body)

def trigger_extra_activity_email(student_roll: str, activity_title: str, status: str, points: int):
    """Sends notification to a student when their extra activity submission is approved or rejected."""
    recipients = get_student_email_by_roll(student_roll)
    if not recipients:
        return
        
    subject = f"Extra Activity Submission {status.title()} - {activity_title}"
    pts_section = f'<p style="font-size: 16px; font-weight: bold; color: #10b981; margin: 8px 0 0 0;">Awarded Points: +{points}</p>' if status.lower() == "approved" else ''
    
    body = f"""
    <p>Your extra activity submission <b>"{activity_title}"</b> has been reviewed by the administration.</p>
    <div style="background-color: #f8fafc; border-left: 4px solid #6366f1; padding: 16px; margin: 16px 0; border-radius: 6px;">
        <p style="margin: 0;"><b>Status:</b> {status.title()}</p>
        {pts_section}
    </div>
    <p>You can check your updated profile point metrics in the Student Portal.</p>
    """
    html_body = build_professional_email_wrapper(
        title=f"Extra Activity: {status.title()}",
        recipient_greeting="Dear Student,",
        main_html=body,
        badge_text="ACTIVITY REVIEW",
        action_text="View Student Profile",
        action_url=f"{_STUDENT_URL}/student/team"
    )
    send_smtp_async(subject, recipients, html_body)

def trigger_absent_email(student_roll: str, student_name: str, team_id: str, reason: str, status: str):
    """Sends absence alert or reschedule alert to a student."""
    recipients = get_student_email_by_roll(student_roll)
    if not recipients:
        return
        
    t_name = format_clean_team_name(team_id)
    if status.lower() == "pending":
        subject = f"Absence Alert: Missed Presentation - {student_roll}"
        body = f"""
        <p>You have been marked <b>Absent</b> by the evaluation panel for your scheduled project presentation ({t_name}).</p>
        <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 16px; margin: 16px 0; border-radius: 6px;">
            <p style="margin: 0 0 4px 0; color: #991b1b; font-weight: bold;">Reason Logged:</p>
            <p style="margin: 0; color: #7f1d1d;">{reason}</p>
        </div>
        <p style="color: #b91c1c; font-weight: bold;">Please contact the project semester coordinator immediately to request a makeup slot.</p>
        """
        html_body = build_professional_email_wrapper(
            title="Absence Logged for Evaluation",
            recipient_greeting=f"Dear {student_name},",
            main_html=body,
            badge_text="ABSENCE ALERT",
            badge_color="#ef4444",
            action_text="Contact Coordinator",
            action_url=f"{_STUDENT_URL}/student/team"
        )
    else:
        subject = f"Absence Update: Rescheduled - {student_roll}"
        body = f"""
        <p>Your missed presentation for {t_name} has been rescheduled by the coordinator.</p>
        <p>Please check your student dashboard to see the updated slot timings, room, and meet links.</p>
        """
        html_body = build_professional_email_wrapper(
            title="Presentation Rescheduled",
            recipient_greeting=f"Dear {student_name},",
            main_html=body,
            badge_text="SLOT RESCHEDULED",
            action_text="View Updated Slot",
            action_url=f"{_STUDENT_URL}/student/team"
        )
    send_smtp_async(subject, recipients, html_body)

def trigger_evaluation_submitted_email(team_id: str, score: float):
    """Sends email notifications to team members when their evaluation is submitted."""
    recipients = get_student_emails_in_team(team_id)
    if not recipients:
        return
    
    t_name = format_clean_team_name(team_id)
    subject = f"Evaluation Score Submitted - {t_name}"
    body = f"""
    <p>A new milestone evaluation score has been submitted for <b>{t_name}</b> by the evaluation panel:</p>
    <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 16px; border-radius: 8px; margin: 16px 0; text-align: center;">
        <p style="margin: 0; font-size: 22px; font-weight: 800; color: #166534;">Total Score: {score}/100</p>
    </div>
    <p>Please log in to the Student Portal to check the detailed criteria breakdowns and feedback comments.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Evaluation Results Available",
        recipient_greeting="Dear Student Team,",
        main_html=body,
        badge_text="EVALUATION SCORE",
        action_text="Check Evaluation Details",
        action_url=f"{_STUDENT_URL}/student/team"
    )
    send_smtp_async(subject, recipients, html_body)


def trigger_results_published_email():
    """Broadcasts an email to all students and mentors when final results are published."""
    student_emails = get_all_student_emails()
    mentor_emails = get_all_mentor_emails()
    
    subject = "Final Project Results Published"
    body = """
    <p>The administration has officially published the final results for the project semester.</p>
    <p>Please log in to your respective portals to view final grades, scores, and semester-end audit reviews.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Semester Results Published",
        recipient_greeting="Dear Students and Faculty Mentors,",
        main_html=body,
        badge_text="FINAL RESULTS",
        action_text="View Published Results",
        action_url=f"{_STUDENT_URL}/student/team"
    )
    if student_emails:
        send_smtp_async(subject, student_emails, html_body)
    if mentor_emails:
        send_smtp_async(subject, mentor_emails, html_body)

def trigger_ps_released_email():
    """Broadcasts an email to all students when problem statement selection is released."""
    student_emails = get_all_student_emails()
    if not student_emails:
        return
    
    subject = "Problem Statements Selection Released"
    body = """
    <p>The problem statements for this semester have been released and are now available for choosing.</p>
    <p>Log in to the Student Portal with your team to review and submit your project preference lists.</p>
    """
    html_body = build_professional_email_wrapper(
        title="Problem Statements Selection Released",
        recipient_greeting="Dear Student,",
        main_html=body,
        badge_text="TOPICS RELEASED",
        action_text="Browse Problem Statements",
        action_url=f"{_STUDENT_URL}/student/team"
    )
    send_smtp_async(subject, student_emails, html_body)

def trigger_student_welcome_email(email: str, name: str):
    """Sends a welcome email to a student when their profile is uploaded."""
    subject = "Welcome to the Project Management System"
    body = """
    <p style="margin-top: 0; margin-bottom: 16px;">Greetings!</p>
    <p style="margin-bottom: 16px; line-height: 1.6;">You have been successfully <strong>enrolled under the Mini Project</strong> for the current semester on the <strong>Procksi</strong> project management platform.</p>
    <p style="margin-bottom: 16px; line-height: 1.6;">Get ready to explore innovative ideas, apply your technical knowledge, strengthen your problem-solving and research skills, and gain hands-on experience by developing meaningful real-world projects.</p>
    <p style="margin-bottom: 16px; line-height: 1.6;">You are expected to actively participate in all project activities and strictly adhere to the instructions and timelines communicated through Procksi.</p>
    <p style="margin-bottom: 24px; line-height: 1.6;">Further instructions regarding the Mini Project will be shared shortly.</p>
    
    <div style="margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px; color: #475569;">
        <p style="margin: 0; font-size: 13px; font-weight: 500;">Best Regards,</p>
        <p style="margin: 4px 0 0 0; font-size: 14px; font-weight: 700; color: #1e293b;">Mr. Preshit Desai & Ms. Anushka Shukla</p>
        <p style="margin: 2px 0 0 0; font-size: 12px; font-weight: 600; color: #4f46e5; text-transform: uppercase; letter-spacing: 0.5px;">Project Coordinators – AIML</p>
        <p style="margin: 12px 0 0 0; font-size: 13px; font-weight: 500;">Thank you.</p>
    </div>
    """
    html_body = build_professional_email_wrapper(
        title="Welcome to Procksi",
        recipient_greeting="Dear Student,",
        main_html=body,
        badge_text="WELCOME TO PROCKSI",
        action_text=None,
        action_url=None
    )
    send_smtp_async(subject, [email], html_body)


def trigger_mentor_welcome_email(email: str, name: str):
    """Sends a welcome email to a mentor when they are added by the coordinator."""
    subject = "Assigned as Mentor - Project Management System"
    # Kept identical in wording to the batch template below, which is the one
    # actually wired up. See the comment there for why this asks the mentor to
    # sign up rather than log in.
    body = f"""
    <p>You have been added as a Mentor on the Procksi by the Project Coordinator.</p>
    <p>To get started, create your account on the Mentor Portal using this email address — <strong>{email}</strong>. Only addresses on the mentor roster can register, so please use this one.</p>
    <p>Once the Project Coordinator approves your account, you will be able to view your allocated student teams, track their milestone progress, and record presentation grades.</p>
    """
    html_body = build_professional_email_wrapper(
        title=f"Welcome, {name}!",
        recipient_greeting=f"Dear {name},",
        main_html=body,
        badge_text="WELCOME TO PROCKSI",
        action_text="Create Your Account",
        action_url=f"{_MENTOR_URL}/signup"
    )
    send_smtp_async(subject, [email], html_body)


def trigger_batch_student_welcome_emails(students: list[dict]):
    """Sends welcome emails to a batch of students sequentially in background using chunked SMTP connections."""
    def task():
        clean_students = []
        seen = set()
        for s in students:
            e = s.get("email")
            n = s.get("name", "Student")
            if e and "@" in str(e) and e.strip().lower() not in seen:
                seen.add(e.strip().lower())
                clean_students.append({"email": e.strip(), "name": n})

        if not clean_students:
            logger.info("No valid student emails found for batch welcome email.")
            return

        sender = (os.getenv("MAIL_FROM") or os.getenv("MAIL_USERNAME") or os.getenv("MASTER_ADMIN_EMAIL") or "").strip()
        sender_name = (os.getenv("MAIL_FROM_NAME") or "Procksi Portal").strip()

        subject = "Welcome to the Project Management System"
        body = """
    <p style="margin-top: 0; margin-bottom: 16px;">Greetings!</p>
    <p style="margin-bottom: 16px; line-height: 1.6;">You have been successfully <strong>enrolled under the Mini Project</strong> for the current semester on the <strong>Procksi</strong> project management platform.</p>
    <p style="margin-bottom: 16px; line-height: 1.6;">Get ready to explore innovative ideas, apply your technical knowledge, strengthen your problem-solving and research skills, and gain hands-on experience by developing meaningful real-world projects.</p>
    <p style="margin-bottom: 16px; line-height: 1.6;">You are expected to actively participate in all project activities and strictly adhere to the instructions and timelines communicated through Procksi.</p>
    <p style="margin-bottom: 24px; line-height: 1.6;">Further instructions regarding the Mini Project will be shared shortly.</p>
    
    <div style="margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px; color: #475569;">
        <p style="margin: 0; font-size: 13px; font-weight: 500;">Best Regards,</p>
        <p style="margin: 4px 0 0 0; font-size: 14px; font-weight: 700; color: #1e293b;">Mr. Preshit Desai & Ms. Anushka Shukla</p>
        <p style="margin: 2px 0 0 0; font-size: 12px; font-weight: 600; color: #4f46e5; text-transform: uppercase; letter-spacing: 0.5px;">Project Coordinators – AIML</p>
        <p style="margin: 12px 0 0 0; font-size: 13px; font-weight: 500;">Thank you.</p>
    </div>
    """
        html_body = build_professional_email_wrapper(
            title="Welcome to Procksi",
            recipient_greeting="Dear Student,",
            main_html=body,
            badge_text="WELCOME TO PROCKSI",
            action_text=None,
            action_url=None
        )

        items_to_send = []
        for item in clean_students:
            st_email = item["email"]
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{sender}>" if sender_name else sender
            msg["To"] = st_email
            msg.attach(MIMEText(html_body, "html"))
            items_to_send.append({"email": st_email, "msg": msg})

        logger.info(f"Starting batch student welcome email dispatch to {len(items_to_send)} students...")
        _send_smtp_chunked(items_to_send, chunk_size=25, delay_between_msgs=0.1, delay_between_chunks=0.5)

    thread = threading.Thread(target=task)
    thread.daemon = True
    thread.start()


def trigger_batch_mentor_welcome_emails(mentors: list[dict]):
    """Sends welcome emails to a batch of mentors sequentially in background using chunked SMTP connections."""
    def task():
        clean_mentors = []
        seen = set()
        for m in mentors:
            e = m.get("email")
            n = m.get("name", "Mentor")
            if e and "@" in str(e) and e.strip().lower() not in seen:
                seen.add(e.strip().lower())
                clean_mentors.append({"email": e.strip(), "name": n})

        if not clean_mentors:
            return

        sender = (os.getenv("MAIL_FROM") or os.getenv("MAIL_USERNAME") or os.getenv("MASTER_ADMIN_EMAIL") or "").strip()
        sender_name = (os.getenv("MAIL_FROM_NAME") or "Procksi Portal").strip()

        items_to_send = []
        for item in clean_mentors:
            m_email = item["email"]
            m_name = item["name"]

            subject = "Assigned as Mentor - Project Management System"
            # The recipient has been added to the mentor roster but has no
            # password yet: the row is created unclaimed (is_active=false,
            # password_hash empty) and signup is what claims it. So this asks
            # them to sign up — telling them to "log in" would send them to a
            # form no credentials work on. Approval is a separate, later step,
            # and is mentioned so a pending account does not read as a fault.
            body = f"""
            <p>You have been added as a Mentor on the Procksi by the Project Coordinator.</p>
            <p>To get started, create your account on the Mentor Portal using this email address — <strong>{m_email}</strong>. Only addresses on the mentor roster can register, so please use this one.</p>
            <p>Once the Project Coordinator approves your account, you will be able to view your allocated student teams, track their milestone progress, and record presentation grades.</p>
            """
            html_body = build_professional_email_wrapper(
                title=f"Welcome, {m_name}!",
                recipient_greeting=f"Dear {m_name},",
                main_html=body,
                badge_text="WELCOME TO PROCKSI",
                # Deep-links to signup, not the portal root: the mentor has no
                # credentials yet, so the button must land where the email tells
                # them to go.
                action_text="Create Your Account",
                action_url=f"{_MENTOR_URL}/signup"
            )

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{sender}>" if sender_name else sender
            msg["To"] = m_email
            msg.attach(MIMEText(html_body, "html"))
            items_to_send.append({"email": m_email, "msg": msg})

        logger.info(f"Starting batch mentor welcome email dispatch to {len(items_to_send)} mentors...")
        _send_smtp_chunked(items_to_send, chunk_size=25, delay_between_msgs=0.1, delay_between_chunks=0.5)

    thread = threading.Thread(target=task)
    thread.daemon = True
    thread.start()


def trigger_all_deadlines_email(deadlines_list: list):
    """Sends an email schedule of all active platform deadlines to all students and mentors."""
    try:
        student_emails = get_all_student_emails()
        mentor_emails = get_all_mentor_emails()
        recipients = list(set(student_emails + mentor_emails))
        if not recipients:
            return

        rows_html = ""
        for d in (deadlines_list or []):
            if not isinstance(d, dict):
                continue
            title = d.get("title") or d.get("name") or d.get("type") or "Platform Milestone"
            desc = d.get("description") or ""

            start_raw = d.get("start_date") or ""
            if start_raw:
                s_str = str(start_raw).replace("T", " ")
                for suffix in ('Z', '+00:00', '+0000'):
                    if s_str.endswith(suffix):
                        s_str = s_str[:-len(suffix)]
                        break
                if '+' in s_str:
                    s_str = s_str.split('+')[0]
                if len(s_str) >= 16:
                    parts = s_str.split(" ")
                    start_raw = f"{parts[0]} at {parts[1][:5]}"
                else:
                    start_raw = s_str
            else:
                start_raw = "Open Now"

            due_raw = d.get("due_date") or d.get("deadline_date") or ""
            if due_raw:
                dt_str = str(due_raw).replace("T", " ")
                for suffix in ('Z', '+00:00', '+0000'):
                    if dt_str.endswith(suffix):
                        dt_str = dt_str[:-len(suffix)]
                        break
                if '+' in dt_str:
                    dt_str = dt_str.split('+')[0]
                if len(dt_str) >= 16:
                    parts = dt_str.split(" ")
                    due_raw = f"{parts[0]} at {parts[1][:5]}"
                else:
                    due_raw = dt_str

            rows_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 12px; font-weight: bold; color: #1e293b;">{title}</td>
                <td style="padding: 12px; font-weight: bold; color: #059669;">{start_raw}</td>
                <td style="padding: 12px; font-weight: bold; color: #4338ca;">{due_raw}</td>
                <td style="padding: 12px; color: #64748b; font-size: 13px;">{desc}</td>
            </tr>
            """

        table_html = f"""
        <p>The academic administration has published/updated the official target deadlines schedule for this semester. Please review your milestone opening and closing dates carefully:</p>
        <div style="overflow-x: auto; margin: 20px 0;">
            <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px;">
                <thead>
                    <tr style="background: #f1f5f9; color: #475569;">
                        <th style="padding: 12px; font-size: 12px; text-transform: uppercase;">Milestone Protocol</th>
                        <th style="padding: 12px; font-size: 12px; text-transform: uppercase;">Start / Opening Date</th>
                        <th style="padding: 12px; font-size: 12px; text-transform: uppercase;">Due / Closing Date</th>
                        <th style="padding: 12px; font-size: 12px; text-transform: uppercase;">Description</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html if rows_html else '<tr><td colspan="4" style="padding:12px;">No active deadlines specified.</td></tr>'}
                </tbody>
            </table>
        </div>
        <p>Please ensure all deliverables are completed prior to their respective closing dates to prevent automatic feature locks.</p>
        """


        subject = "📅 Official Announcement: Platform Deadlines & Schedule"
        html_body = build_professional_email_wrapper(
            title="Official Platform Deadlines Schedule",
            recipient_greeting="Dear Students and Faculty Mentors,",
            main_html=table_html,
            badge_text="DEADLINES SCHEDULE",
            action_text="View Portal Deadlines",
            action_url=f"{_STUDENT_URL}/student/team"
        )
        send_smtp_async(subject, recipients, html_body)
    except Exception as e:
        logger.error(f"Failed to trigger all-deadlines email: {e}")


