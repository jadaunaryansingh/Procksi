import os
import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Set

from dotenv import load_dotenv, find_dotenv
root_env = find_dotenv() or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
load_dotenv(root_env)
if not os.getenv("TWILIO_ACCOUNT_SID"):
    p = r"c:\Users\ARYAN SINGH JADAUN\Desktop\PMS Latest\.env"
    if os.path.exists(p):
        load_dotenv(p)

from app.email_notifier import (
    trigger_slot_reminder_email_5m,
    trigger_slot_reminder_email_10m,
    get_supabase_client
)

logger = logging.getLogger("presentation_reminder")

# In-memory tracking of sent reminders to prevent duplicate triggers
# Format: "slot_id_5m", "slot_id_10m", "slot_id_15m"
_reminder_history: Set[str] = set()

# Twilio Client setup (optional/graceful fallback if credentials not provided)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID") or os.getenv("SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN") or os.getenv("AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER") or os.getenv("PHONE_NO", "")

def get_twilio_client():
    account_sid = os.getenv("TWILIO_ACCOUNT_SID") or os.getenv("SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN") or os.getenv("AUTH_TOKEN", "")
    if not account_sid or not auth_token:
        return None
    try:
        from twilio.rest import Client
        return Client(account_sid, auth_token)
    except Exception as e:
        logger.warning(f"Could not initialize Twilio client: {e}")
        return None

def format_phone(phone_str: str) -> str:
    if not phone_str:
        return ""
    p = str(phone_str).strip()
    if p.startswith("+"):
        return p
    digits = "".join(c for c in p if c.isdigit())
    if len(digits) == 10:
        return f"+91{digits}"
    elif len(digits) > 10:
        return f"+{digits}"
    return p

def make_twilio_reminder_call(to_phone: str, team_id: str, slot_time: str):
    """
    Triggers an automated Twilio voice call to the mentor/panelist's phone number.
    Uses inline TwiML voice response.
    """
    target_phone = format_phone(to_phone)
    if not target_phone:
        logger.warning(f"Cannot trigger Twilio call for team {team_id}: No valid phone number provided for evaluator")
        return False

    client = get_twilio_client()
    from_phone = os.getenv("TWILIO_PHONE_NUMBER") or os.getenv("PHONE_NO", "")
    twiml_msg = (
        f"<Response><Say voice='alice'>"
        f"Hello Professor. This is an urgent automated reminder from the G L A University Project Management System. "
        f"Your scheduled presentation evaluation slot for Team {team_id} started fifteen minutes ago at {slot_time}. "
        f"Please join and initiate your evaluation session on the Panel Portal immediately. Thank you."
        f"</Say></Response>"
    )

    if not client or not from_phone:
        logger.info(
            f"[MOCK TWILIO VOICE CALL] Would dial {target_phone} from {from_phone or '+1-TWILIO-NUM'}: "
            f"Presentation slot for Team {team_id} at {slot_time} delayed by 15+ mins."
        )
        return True

    try:
        call = client.calls.create(
            twiml=twiml_msg,
            to=target_phone,
            from_=from_phone
        )
        logger.info(f"Successfully triggered Twilio voice call to {target_phone} (Call SID: {call.sid}) for Team {team_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to place Twilio voice call to {target_phone}: {e}")
        return False



def parse_time_str(time_str: str) -> datetime | None:
    """Parses time strings like '10:00', '10:00 AM', '12:30 PM - 1:00 PM', '14:30' into datetime today."""
    if not time_str:
        return None
    t_str = str(time_str).strip()
    if " - " in t_str:
        t_str = t_str.split(" - ")[0].strip()
    elif "-" in t_str and not t_str.startswith("202"):
        t_str = t_str.split("-")[0].strip()

    today_str = date.today().isoformat()
    for fmt in ("%H:%M", "%I:%M %p", "%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            if fmt == "%Y-%m-%d %H:%M":
                return datetime.strptime(t_str, fmt)
            dt_time = datetime.strptime(t_str, fmt).time()
            return datetime.combine(date.today(), dt_time)
        except ValueError:
            continue
    return None

async def check_presentation_slot_reminders():
    """
    Periodic job that runs every 60 seconds to inspect active scheduled presentation slots
    and escalate pending evaluations at +5m (Email), +10m (Email), and +15m (Twilio Call).
    """
    sb = get_supabase_client()
    if not sb:
        return

    try:
        today_iso = date.today().isoformat()
        # Fetch today's schedule slots across schedule_slots, slots, or schedule tables
        slots = []
        for tbl_name in ("schedule_slots", "slots", "schedule"):
            try:
                res = sb.table(tbl_name).select("*").execute()
                if res.data:
                    slots = res.data
                    break
            except Exception:
                continue

        if not slots:
            return

        # Fetch existing evaluations, drafts, and results to verify if evaluation has started or completed
        started_teams = set()

        # 1. Check results table
        try:
            results_res = sb.table("results").select("*").execute()
            for r in (results_res.data or []):
                t_val = r.get("team_id") or r.get("teamId") or r.get("team")
                if t_val is not None:
                    started_teams.add(str(t_val))
        except Exception:
            pass

        # 2. Check evaluations table
        try:
            evals_res = sb.table("evaluations").select("team_id").execute()
            for r in (evals_res.data or []):
                if r.get("team_id") is not None:
                    started_teams.add(str(r.get("team_id")))
        except Exception:
            pass

        # 3. Check presentation_evaluations table
        try:
            pevals_res = sb.table("presentation_evaluations").select("team_id").execute()
            for r in (pevals_res.data or []):
                if r.get("team_id") is not None:
                    started_teams.add(str(r.get("team_id")))
        except Exception:
            pass

        # 4. Check evaluation_drafts table
        try:
            drafts_res = sb.table("evaluation_drafts").select("team_id").execute()
            for r in (drafts_res.data or []):
                if r.get("team_id") is not None:
                    started_teams.add(str(r.get("team_id")))
        except Exception:
            pass

        now = datetime.now()

        for slot in slots:
            slot_id = str(slot.get("id") or f"{slot.get('team')}_{slot.get('time')}")
            team_id = str(slot.get("team_id") or slot.get("team") or "").replace("admin-team-", "").strip()
            slot_time_raw = slot.get("time") or slot.get("start_time")
            slot_date_raw = slot.get("date")
            slot_status = str(slot.get("status") or "").lower()

            if not team_id or not slot_time_raw:
                continue

            # Skip if evaluation has ALREADY BEEN STARTED or completed by panel member
            if (
                team_id in started_teams
                or slot_status in ("started", "in_progress", "evaluating", "submitted", "completed", "done")
                or slot.get("is_started") is True
                or slot.get("started_at") is not None
            ):
                continue

            # Parse slot start datetime
            slot_dt = parse_time_str(str(slot_time_raw))
            if not slot_dt:
                continue

            # Calculate minutes elapsed since slot start time
            elapsed_seconds = (now - slot_dt).total_seconds()
            elapsed_minutes = elapsed_seconds / 60.0

            # Only check slots starting in the past 60 minutes
            if elapsed_minutes < 0 or elapsed_minutes > 120:
                continue

            panel_val = slot.get("panel_id") or slot.get("panel")
            mentor_val = slot.get("mentor_id") or slot.get("mentor")

            # Fetch mentor/panelist contact details (emails and phones)
            recip_emails = set()
            recip_phones = set()

            for target_val in (panel_val, mentor_val):
                if not target_val:
                    continue
                t_str = str(target_val).strip()
                try:
                    m_res = sb.table("mentors").select("email, phone").or_(f"id.eq.{t_str},email.eq.{t_str},name.ilike.%{t_str}%").execute()
                    for m in (m_res.data or []):
                        if m.get("email"): recip_emails.add(m["email"].strip())
                        if m.get("phone"): recip_phones.add(m["phone"].strip())
                except Exception:
                    pass

                try:
                    p_res = sb.table("panels").select("*").or_(f"id.eq.{t_str},name.ilike.%{t_str}%").execute()
                    for p in (p_res.data or []):
                        if p.get("email"): recip_emails.add(str(p["email"]).strip())
                        if p.get("phone"): recip_phones.add(str(p["phone"]).strip())
                except Exception:
                    pass

                # Also query panel_mentors / panel_members table to get all faculty assigned to this panel
                try:
                    pm_res = sb.table("panel_mentors").select("mentor_id").eq("panel_id", panel_id).execute()
                    m_ids = [row["mentor_id"] for row in (pm_res.data or []) if row.get("mentor_id")]
                    if m_ids:
                        m_list = sb.table("mentors").select("email, phone").in_("id", m_ids).execute()
                        for m in (m_list.data or []):
                            if m.get("email"): recip_emails.add(m["email"].strip())
                            if m.get("phone"): recip_phones.add(m["phone"].strip())
                except Exception:
                    pass

            # Fallback: if no mentor/panelist email found directly on slot, fetch team's mentor from teams_validation
            if not recip_emails and team_id:
                try:
                    tv_res = sb.table("teams_validation").select("mentor, mentor_id, mentor_email").eq("id", team_id).execute()
                    if tv_res.data:
                        row = tv_res.data[0]
                        m_ident = row.get("mentor_email") or row.get("mentor_id") or row.get("mentor")
                        if m_ident:
                            m_lookup = sb.table("mentors").select("email, phone").or_(f"id.eq.{m_ident},email.eq.{m_ident},name.ilike.%{m_ident}%").execute()
                            for m in (m_lookup.data or []):
                                if m.get("email"): recip_emails.add(m["email"].strip())
                                if m.get("phone"): recip_phones.add(m["phone"].strip())
                except Exception:
                    pass

            clean_emails = list(recip_emails)
            clean_phones = list(recip_phones)
            recip_phone_str = clean_phones[0] if clean_phones else None

            # +5 Mins Reminder (1st Email)
            if 5 <= elapsed_minutes < 10:
                key = f"{slot_id}_5m"
                if key not in _reminder_history:
                    logger.info(f"Triggering +5m email reminder for Team {team_id} (slot {slot_time_raw}) to {clean_emails}")
                    if clean_emails:
                        trigger_slot_reminder_email_5m(clean_emails, team_id, str(slot_time_raw))
                    _reminder_history.add(key)

            # +10 Mins Urgent Reminder (2nd Email)
            elif 10 <= elapsed_minutes < 15:
                key = f"{slot_id}_10m"
                if key not in _reminder_history:
                    logger.info(f"Triggering +10m urgent email reminder for Team {team_id} (slot {slot_time_raw}) to {clean_emails}")
                    if clean_emails:
                        trigger_slot_reminder_email_10m(clean_emails, team_id, str(slot_time_raw))
                    _reminder_history.add(key)

            # +15 Mins Escalation (Twilio Voice Call)
            elif elapsed_minutes >= 15:
                key = f"{slot_id}_15m"
                if key not in _reminder_history:
                    logger.info(f"Triggering +15m Twilio voice call reminder for Team {team_id} (slot {slot_time_raw}) to {recip_phone_str}")
                    make_twilio_reminder_call(recip_phone_str or "", team_id, str(slot_time_raw))
                    _reminder_history.add(key)

    except Exception as e:
        logger.error(f"Error in check_presentation_slot_reminders: {e}")

async def start_presentation_reminder_scheduler():
    """Starts the background loop running every 60 seconds."""
    logger.info("Presentation Schedule Escalation Reminder Service started (+5m Email, +10m Email, +15m Twilio Call).")
    while True:
        try:
            await check_presentation_slot_reminders()
        except Exception as e:
            logger.error(f"Error in presentation reminder loop: {e}")
        await asyncio.sleep(60)
