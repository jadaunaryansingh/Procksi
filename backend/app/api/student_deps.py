import os
import asyncio
import json
import urllib.request
import urllib.error
import uuid
import logging


def _allowed_email_suffix() -> str:
    """'@' + ALLOWED_EMAIL_DOMAIN. Unset rejects every address (fail closed)."""
    return "@" + os.getenv("ALLOWED_EMAIL_DOMAIN", "").strip().lstrip("@").lower()


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

import time

security = HTTPBearer()

# Map token -> (timestamp, student_obj)
PROFILE_CACHE = {}
PROFILE_CACHE_TTL = 10 # 10 seconds cache for concurrent page loading requests

# Map token -> asyncio.Task
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
            detail={"success": False, "error": {"code": "AUTH_UNAUTHORIZED", "message": "Invalid or expired Supabase token"}}
        )
    except Exception as e:
        # Catch connection/timeout issues and present a clear message
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"success": False, "error": {"code": "AUTH_SERVICE_UNAVAILABLE", "message": f"Auth service error: {str(e)}"}}
        )

    # 2. Extract user ID and email from the response
    auth_id = user_data.get("id")
    student_email = user_data.get("email")
    if not auth_id or not student_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"success": False, "error": {"code": "AUTH_UNAUTHORIZED", "message": "Invalid user token response"}}
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
        # Auto-provision: create a student record on first login using
        # metadata from the Supabase auth user profile.
        logger.info("Student record not found for %s — auto-provisioning.", student_email)
        user_meta = user_data.get("user_metadata", {})
        new_student = {
            "email": student_email,
            "name": user_meta.get("full_name")
                    or user_meta.get("name")
                    or student_email.split("@")[0].replace(".", " ").title(),
            "year": user_meta.get("year", 3),
            "branch": user_meta.get("branch", "B.Tech CS"),
            "section": user_meta.get("section", "A"),
            "status": "Active",
        }
        try:
            student_data = await supabase_client.upsert_student(new_student)
        except Exception as e:
            logger.error("Failed to auto-provision student %s: %s", student_email, e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"success": False, "error": {"code": "PROVISION_FAILED", "message": f"Could not create student record: {str(e)}"}}
            )

    if student_data.get("status", "Active").lower() != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"success": False, "error": {"code": "AUTH_FORBIDDEN", "message": "Student account is inactive."}}
        )

    # 4. Construct lightweight mock objects to preserve SQLAlchemy compatibility
    class RESTObject:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def __repr__(self):
            return f"<RESTObject {self.__dict__}>"

    # Build Student instance
    student_obj = RESTObject(
        id=student_data.get("id"),
        student_id=student_data.get("student_id") or student_data.get("id"),
        name=student_data.get("name"),
        email=student_data.get("email"),
        year=student_data.get("year"),
        branch=student_data.get("branch"),
        section=student_data.get("section"),
        status=student_data.get("status", "active").lower(),
        semester_id=student_data.get("semester_id"),
        team_membership=None
    )

    # 5. Populate Team and Mentor relations from teams_validation
    try:
        team_data = await supabase_client.get_team_by_student_id(student_obj.id)
    except Exception as e:
        logger.error(f"Failed to fetch team for student {student_obj.id}: {e}")
        team_data = None

    if team_data:
        # Load mentor if assigned
        mentor_obj = None
        if team_data.get("mentor") and team_data.get("mentor") != "--":
            try:
                mentor_data = await supabase_client.get_mentor_by_name(team_data["mentor"])
                if mentor_data:
                    mentor_obj = RESTObject(
                        id=mentor_data.get("id"),
                        name=mentor_data.get("name"),
                        email=mentor_data.get("email"),
                        expertise=mentor_data.get("domain")
                    )
            except Exception as e:
                logger.error(f"Failed to fetch mentor {team_data['mentor']}: {e}")
            
            if not mentor_obj:
                mentor_obj = RESTObject(
                    id="M-TEMP",
                    name=team_data["mentor"],
                    email=None,
                    expertise=None
                )

        # Parse members array
        raw_members = team_data.get("members", [])
        if isinstance(raw_members, str):
            try:
                raw_members = json.loads(raw_members)
            except Exception:
                raw_members = []

        leader_name = team_data.get("leader", "")
        members_list = []

        # Convert members array into student and team member mock objects
        for m in raw_members:
            m_id = m.get("id") or m.get("roll")
            if not m_id:
                continue
            m_role = "LEADER" if (m.get("name") == leader_name or m_id == team_data.get("leader")) else "MEMBER"
            
            m_student_obj = RESTObject(
                id=m_id,
                student_id=m.get("roll") or m_id,
                name=m.get("name", "Unknown"),
                email=m.get("email") or f"{m_id}{_allowed_email_suffix()}",
                branch=m.get("branch", "B.Tech CS"),
                section="A",
                year=3
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
            team_int_id = int(raw_id.split("-")[1]) if "-" in str(raw_id) else int(raw_id)
        except Exception:
            team_int_id = raw_id

        domain_val = team_data.get("domain", "")
        domain_list = [domain_val] if isinstance(domain_val, str) else (domain_val or [])

        team_obj = RESTObject(
            id=team_int_id,
            name=team_data.get("title", ""),
            project_title=team_data.get("title", ""),
            description=team_data.get("description", ""),
            domain=domain_list,
            required_skills=[],
            mentor_id=mentor_obj.id if mentor_obj else None,
            semester_id=team_data.get("semester_id"),
            is_validated=team_data.get("validationStatus") == "Valid",
            is_overridden=False,
            status=team_data.get("validationStatus", "pending").lower(),
            mentor=mentor_obj,
            members=members_list
        )

        student_role = "LEADER" if (student_obj.name == leader_name or student_obj.id == team_data.get("leader")) else "MEMBER"
        student_obj.team_membership = RESTObject(
            id=student_obj.id,
            team_id=team_int_id,
            student_id=student_obj.id,
            role=student_role,
            team=team_obj,
            student=student_obj
        )

    # Cache the resolved student profile before returning
    PROFILE_CACHE[token] = (time.time(), student_obj)
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
    now = time.time()
    
    # 1. Check completed cache first
    if token in PROFILE_CACHE:
        cache_time, cached_student = PROFILE_CACHE[token]
        if now - cache_time < PROFILE_CACHE_TTL:
            logger.info("Retrieved current student profile from cache (0.000s hit).")
            return cached_student
        else:
            del PROFILE_CACHE[token]

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
