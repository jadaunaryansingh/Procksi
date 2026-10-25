import asyncio
import json
import urllib.request
import urllib.error
import urllib.parse
import uuid
import logging

logger = logging.getLogger(__name__)
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.student import Student
from app.models.team_member import TeamMember
from app.models.team import Team
from app.models.mentor import Mentor

import os

from app.core.ttl_cache import TTLCache

security = HTTPBearer()

# Short-lived cache of resolved student profiles, keyed by access token, so the
# burst of calls a single page load makes resolves the profile once.
#
# Must be bounded: Supabase access tokens rotate, so a plain dict accumulated one
# orphaned entry (a full student object with team, members and mentors) per
# rotation, forever. TTLCache sweeps expired entries on write and caps total size.
PROFILE_CACHE_TTL = 10  # seconds
PROFILE_CACHE_MAX = int(os.getenv("PMS_PROFILE_CACHE_MAX", "2048"))
PROFILE_CACHE = TTLCache(ttl=PROFILE_CACHE_TTL, max_entries=PROFILE_CACHE_MAX)

# Map token -> asyncio.Task. Bounded by construction: every entry is removed in
# the `finally` of the request that created it.
PENDING_PROFILE_TASKS = {}

async def _fetch_student_profile_uncached(token: str) -> Student:
    """
    Performs the actual network requests to fetch and construct the student profile.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase settings are not configured on the backend."
        )

    # 1. Verify the Supabase JWT by querying Supabase's user endpoint
    user_url = f"{settings.SUPABASE_URL}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": settings.SUPABASE_KEY
    }
    
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(user_url, headers=headers)
            response.raise_for_status()
            user_data = response.json()
    except httpx.HTTPStatusError as e:
        # Supabase returned HTTP error (e.g. 401 Unauthorized for invalid/expired token)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )
    except Exception as e:
        logger.error(f"Auth service verification exception: {type(e).__name__} - {str(e) or repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"success": False, "error": {"code": "AUTH_SERVICE_UNAVAILABLE", "message": f"Auth service error: {type(e).__name__} - {str(e) or repr(e)}"}}
        )

    # 2. Extract user ID and email from the response
    auth_id = user_data.get("id")
    student_email = user_data.get("email")
    if not auth_id or not student_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )

    # 3. Retrieve student profile from DB using Supabase REST Client
    from app.core.supabase_client import supabase_client
    
    try:
        student_data = await supabase_client.get_student_by_email(student_email)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"success": False, "error": {"code": "DB_UNAVAILABLE", "message": f"Database error: {str(e)}"}}
        )

    if not student_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student record not found"
        )

    if student_data.get("status", "Active").lower() != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"success": False, "error": {"code": "AUTH_FORBIDDEN", "message": "Student account is inactive."}}
        )

    # Check if student's semester is active
    sem_id = student_data.get("semester_id")
    if sem_id:
        try:
            sem_res = await supabase_client._request(f"semester_config?id=eq.{sem_id}&limit=1")
            if sem_res and len(sem_res) > 0:
                if not sem_res[0].get("is_active"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={"success": False, "error": {"code": "AUTH_FORBIDDEN", "message": "Your academic batch is not active."}}
                    )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to check active status for semester {sem_id}: {e}")

    # 4. Construct lightweight mock objects to preserve SQLAlchemy compatibility
    class RESTObject:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def __repr__(self):
            return f"<RESTObject {self.__dict__}>"

    # Derive clean student name if missing or set to email address
    raw_name = student_data.get("name") or user_data.get("user_metadata", {}).get("full_name") or user_data.get("user_metadata", {}).get("name")
    if not raw_name or "@" in str(raw_name):
        email_prefix = student_email.split("@")[0]
        raw_name = " ".join([word.capitalize() for word in email_prefix.replace(".", " ").replace("_", " ").split()])

    # Build Student instance
    student_obj = RESTObject(
        id=student_data.get("id"),
        student_id=student_data.get("student_id") or student_data.get("id"),
        name=raw_name,
        email=student_data.get("email") or student_email,
        year=student_data.get("year"),
        branch=student_data.get("branch"),
        section=student_data.get("section"),
        status=student_data.get("status", "active").lower(),
        semester_id=student_data.get("semester_id"),
        avatar_url=student_data.get("avatar_url"),
        phone=student_data.get("phone"),
        bio=student_data.get("bio"),
        skills=student_data.get("skills"),
        team_membership=None
    )

    # 5. Populate Team and Mentor relations from teams_validation
    try:
        team_data = await supabase_client.get_team_by_student_id(student_obj.id, student_obj.semester_id)
    except Exception as e:
        logger.error(f"Failed to fetch team for student {student_obj.id}: {e}")
        team_data = None

    if team_data:
        # Load mentors if assigned
        mentor_obj = None
        mentors_list = []
        if team_data.get("mentor") and team_data.get("mentor") != "--":
            raw_mentor = team_data.get("mentor") or ""
            # Parse mentor field — could be a plain string, comma-separated, or JSON array
            mentor_names: list[str] = []
            try:
                import json as _json
                parsed = _json.loads(raw_mentor)
                if isinstance(parsed, list):
                    mentor_names = [str(m).strip() for m in parsed if str(m).strip()]
                else:
                    mentor_names = [str(parsed).strip()]
            except Exception:
                mentor_names = [n.strip() for n in raw_mentor.split(",") if n.strip()]
            
            for m_name in mentor_names:
                try:
                    mentor_data = await supabase_client.get_mentor_by_name(m_name)
                    if mentor_data:
                        m_obj = RESTObject(
                            id=mentor_data.get("id"),
                            name=mentor_data.get("name"),
                            email=mentor_data.get("email"),
                            phone=mentor_data.get("phone"),
                            expertise=mentor_data.get("domain")
                        )
                    else:
                        m_obj = RESTObject(
                            id=f"M-TEMP-{m_name}",
                            name=m_name,
                            email=None,
                            phone=None,
                            expertise=None
                        )
                    mentors_list.append(m_obj)
                except Exception as e:
                    logger.error(f"Failed to fetch mentor {m_name}: {e}")
            
            if mentors_list:
                mentor_obj = mentors_list[0]

        # Parse members array
        raw_members = team_data.get("members", [])
        if isinstance(raw_members, str):
            try:
                raw_members = json.loads(raw_members)
            except Exception:
                raw_members = []

        leader_name = team_data.get("leader", "")
        members_list = []
        member_ids = []
        for m in raw_members:
            if isinstance(m, dict):
                m_id = m.get("id") or m.get("roll") or m.get("student_id")
            else:
                m_id = str(m)
            if m_id:
                member_ids.append(str(m_id))

        students_by_id = {}
        if member_ids:
            try:
                import urllib.parse
                quoted_ids = ",".join(f'"{mid}"' for mid in member_ids)
                students_info = await supabase_client._request(f"students?or=(id.in.({quoted_ids}),student_id.in.({quoted_ids}))&select=id,name,email,branch,section,year,student_id,avatar_url")
                for s_info in (students_info or []):
                    if s_info.get("id"):
                        students_by_id[str(s_info.get("id"))] = s_info
                    if s_info.get("student_id"):
                        students_by_id[str(s_info.get("student_id"))] = s_info
            except Exception as e:
                logger.error(f"Failed to fetch student details in bulk: {e}")

        for m in raw_members:
            if isinstance(m, dict):
                m_id = m.get("id") or m.get("roll") or m.get("student_id")
                m_name = m.get("name") or "Unknown"
                m_email = m.get("email") or None
                m_branch = m.get("branch", "B.Tech CS")
                m_roll = m.get("roll") or m_id
            else:
                m_id = str(m)
                m_name = "Unknown"
                m_email = None
                m_branch = "B.Tech CS"
                m_roll = m_id

            if not m_id:
                continue

            s_db = students_by_id.get(str(m_id)) or students_by_id.get(str(m_roll)) or {}
            m_email = s_db.get("email") or m_email or (f"{m_roll}@gla.ac.in" if str(m_roll).isalnum() else None)
            m_name = s_db.get("name") or m_name
            m_branch = s_db.get("branch") or m_branch
            m_section = s_db.get("section") or "A"
            m_year = s_db.get("year") or 3
            m_avatar = s_db.get("avatar_url")
            m_roll = s_db.get("student_id") or m_roll

            m_role = "LEADER" if (m_name == leader_name or m_id == team_data.get("leader")) else "MEMBER"
            
            m_student_obj = RESTObject(
                id=m_id,
                student_id=m_roll,
                name=m_name,
                email=m_email,
                branch=m_branch,
                section=m_section,
                year=m_year,
                avatar_url=m_avatar
            )
            
            m_member_obj = RESTObject(
                id=m_id,
                team_id=team_data.get("id"),
                student_id=m_id,
                role=m_role,
                student=m_student_obj
            )
            members_list.append(m_member_obj)

        # Map string ID (e.g. TEAM-3) to integer ID if possible
        raw_id = team_data.get("id")
        try:
            from app.core.supabase_client import extract_numeric_id
            team_int_id = extract_numeric_id(raw_id) if raw_id else None
            logger.info(f"Successfully converted raw team ID '{raw_id}' to numeric ID '{team_int_id}'")
        except Exception as e:
            logger.exception(f"Failed to extract numeric team ID from '{raw_id}': {e}")
            team_int_id = raw_id

        domain_val = team_data.get("domain", "")
        domain_list = [domain_val] if isinstance(domain_val, str) else (domain_val or [])

        tv_title = team_data.get("title", "")
        from app.core.supabase_client import get_clean_team_name
        display_number = team_data.get("team_number")
        display_name = f"Team {display_number}" if display_number is not None else get_clean_team_name(team_id=raw_id, raw_name=tv_title, tv_id=raw_id)

        team_obj = RESTObject(
            id=raw_id,
            uid=team_data.get("uid"),
            team_number=display_number,
            name=display_name,
            project_title=tv_title or display_name,
            description=team_data.get("description", ""),
            domain=domain_list,
            required_skills=[],
            mentor_id=mentor_obj.id if mentor_obj else None,
            semester_id=team_data.get("semester_id"),
            is_validated=team_data.get("validationStatus") == "Valid",
            is_overridden=False,
            status=team_data.get("validationStatus", "pending").lower(),
            mentor=mentor_obj,
            mentors=mentors_list,   # FIX (Bug 1): full list of resolved mentor objects
            members=members_list
        )

        def _eval_is_leader(my_ids, team_d):
            my_identifiers = [str(x).strip().lower() for x in my_ids if str(x).strip()]
            leader_val = str(team_d.get("leader") or team_d.get("leader_id") or "").strip().lower()
            if leader_val:
                if any(my_id in leader_val or leader_val in my_id for my_id in my_identifiers):
                    return True
                raw_mem = team_d.get("members", [])
                if isinstance(raw_mem, str):
                    try:
                        import json
                        raw_mem = json.loads(raw_mem)
                    except Exception:
                        raw_mem = []
                if isinstance(raw_mem, list):
                    for m in raw_mem:
                        if isinstance(m, dict):
                            m_ids = [str(m.get(k) or "").strip().lower() for k in ["id", "student_id", "roll", "name", "email"] if m.get(k)]
                            if any(l_id in leader_val for l_id in m_ids) and not any(my_id in m_ids for my_id in my_identifiers):
                                return False
            raw_mem = team_d.get("members", [])
            if isinstance(raw_mem, str):
                try:
                    import json
                    raw_mem = json.loads(raw_mem)
                except Exception:
                    raw_mem = []
            if isinstance(raw_mem, list):
                for idx, m in enumerate(raw_mem):
                    if isinstance(m, dict):
                        m_ids = [str(m.get(k) or "").strip().lower() for k in ["id", "student_id", "roll", "name", "email"] if m.get(k)]
                        if any(my_id in m_ids for my_id in my_identifiers):
                            m_role = str(m.get("role") or "").strip().upper()
                            if m.get("isLeader") or m_role == "LEADER":
                                return True
                            if m_role == "MEMBER":
                                return False
                            return (idx == 0)
            return False

        # Role comes from team_memberships (the relational source of truth) when we
        # can read it; the name/position heuristic is only a fallback for teams
        # that still live purely in the teams_validation.members jsonb.
        team_uid_val = team_data.get("uid")
        student_role = None
        if team_uid_val:
            try:
                mm = await supabase_client._request(
                    f"team_memberships?team_uid=eq.{team_uid_val}"
                    f"&student_roll=eq.{urllib.parse.quote(str(student_obj.id))}&select=role&limit=1"
                )
                if mm and mm[0].get("role"):
                    student_role = str(mm[0]["role"]).upper()
            except Exception as e:
                logger.warning(f"team_memberships role lookup failed for {student_obj.id}: {e}")
        if student_role is None:
            my_ids_to_check = [student_obj.id, getattr(student_obj, "student_id", None), getattr(student_obj, "name", None), getattr(student_obj, "email", None)]
            student_role = "LEADER" if _eval_is_leader(my_ids_to_check, team_data) else "MEMBER"

        student_obj.team_membership = RESTObject(
            id=student_obj.id,
            team_id=raw_id,            # legacy slug — kept for callers not yet on uid
            team_uid=team_uid_val,     # canonical identity
            student_id=student_obj.id,
            role=student_role,
            team=team_obj,
            student=student_obj
        )

    # Cache the resolved student profile before returning
    PROFILE_CACHE.set(token, student_obj)
    return student_obj


async def get_current_student(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Student:
    """
    Authenticate a student by verifying their Supabase JWT and returning the Student record.
    Uses Supabase's user profile endpoint to validate the JWT.
    Coalesces concurrent requests for the same token to avoid thundering herd.
    """
    token = credentials.credentials

    # 1. Check completed cache first. Expiry and eviction are handled by TTLCache.
    cached_student = PROFILE_CACHE.get(token)
    if cached_student is not None:
        logger.info("Retrieved current student profile from cache (0.000s hit).")
        return cached_student

    # 2. Check if a task is already running for this token
    if token in PENDING_PROFILE_TASKS:
        logger.info("Awaiting concurrent student profile retrieval task (thundering herd avoided).")
        return await PENDING_PROFILE_TASKS[token]

    # 3. Create a new task to fetch the profile
    async def _fetch():
        try:
            return await _fetch_student_profile_uncached(token)
        except Exception:
            raise

    task = asyncio.create_task(_fetch())
    PENDING_PROFILE_TASKS[token] = task
    try:
        student_obj = await task
        return student_obj
    finally:
        PENDING_PROFILE_TASKS.pop(token, None)
