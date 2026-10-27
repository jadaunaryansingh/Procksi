import asyncio
import logging
import json
import uuid
import urllib.parse
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, date, time, timezone, timedelta
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status, Body, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.api.deps import get_db
from app.api.student_deps import get_current_student
from app.core.rate_limit import limiter
from app.models.student import Student
from app.models.team_member import TeamMember
from app.models.team import Team
from app.models.mentor import Mentor
from app.models.deadline import Deadline
from app.models.proposal import Proposal
from app.models.schedule import Schedule
from app.models.evaluation import Evaluation
from app.models.result import Result
from app.models.announcement import Announcement
from app.models.milestone import Milestone
from app.schemas.common import ok

router = APIRouter(prefix="/api/student", tags=["Student Portal"])


def parse_numeric_team_id(team_id) -> int:
    if team_id is None:
        return 0
    s = str(team_id).strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    if "-T" in s:
        part = s.split("-T")[-1]
        if part.isdigit():
            return int(part)
    match = re.search(r'(\d+)\s*$', s)
    if match:
        return int(match.group(1))
    digits = re.findall(r'\d+', s)
    if digits:
        return int(digits[-1])
    return 0

DATA_STORE_PATH = Path(__file__).resolve().parent.parent / "data_store.json"


def _read_store() -> dict:
    if not DATA_STORE_PATH.exists():
        return {
            "problem_statements": [],
            "announcements": [],
            "notifications": [],
            "extra_activities": {},
            "preferences": {},
            "results_published": False
        }
    try:
        with open(DATA_STORE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {
            "problem_statements": [],
            "announcements": [],
            "notifications": [],
            "extra_activities": {},
            "preferences": {},
            "results_published": False
        }


def _write_store(data: dict):
    try:
        with open(DATA_STORE_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Failed to write to data store: {e}")


def _require_web_url(value: Optional[str], field_label: str) -> Optional[str]:
    """Reject anything that is not an http(s) URL.

    These values are stored and later bound into admin/mentor `href` and iframe
    `src` attributes. React does not neutralise `javascript:` in an attribute, so
    an unvalidated string here becomes script execution in the reviewer's origin
    the moment they open the record. Validating on write keeps bad data out of the
    database rather than relying on every render site to remember to defend.
    """
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        raise HTTPException(
            status_code=400,
            detail=f"{field_label} must be a valid http(s) URL.",
        )
    return cleaned


class ProposalPayload(BaseModel):
    title: str
    description: str
    domain: str
    techStack: str
    github: str
    proposalFile: str
    members: Optional[List[Dict[str, Any]]] = None


class SimpleProposalPayload(BaseModel):
    title: str
    description: str
    proposalFile: Optional[str] = None


class ExtraActivityPayload(BaseModel):
    title: str
    description: str
    date: str
    proof_url: Optional[str] = None


class AvatarUpdatePayload(BaseModel):
    avatar_url: str


class MilestoneUpdatePayload(BaseModel):
    github_url: Optional[str] = None
    file_url: Optional[str] = None
    submission_data: Optional[Dict[str, Any]] = None

class ProfileUpdatePayload(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    skills: Optional[str] = None


# ---------------------------------------------------------------------------
# Task 2.1: Student Profile Endpoint — GET /api/student/me
# ---------------------------------------------------------------------------
@router.get("/me")
async def get_my_profile(
    student: Student = Depends(get_current_student)
):
    """
    Return the full profile of the currently authenticated student.
    Includes simplified team details and assigned mentor name and email.
    """
    team_data = None
    mentor_data = None

    # Check if student's semester config is active and fetch team size bounds
    is_sem_active = True
    lock_teams = False
    lock_marks = False
    results_published = False
    team_size_min = 1
    team_size_max = 3
    sem_id = student.semester_id
    try:
        from app.core.supabase_client import supabase_client
        sem_res = None
        if sem_id:
            sem_res = await supabase_client._request(f"semester_config?id=eq.{sem_id}&limit=1")
        if not sem_res or len(sem_res) == 0:
            sem_res = await supabase_client._request("semester_config?is_active=eq.true&limit=1")
        if sem_res and len(sem_res) > 0:
            if sem_id:
                is_sem_active = bool(sem_res[0].get("is_active"))
            lock_teams = bool(sem_res[0].get("lock_teams"))
            lock_marks = bool(sem_res[0].get("lock_marks"))
            results_published = bool(sem_res[0].get("results_published"))
            is_locked = bool(sem_res[0].get("is_locked"))
            if sem_res[0].get("team_size_min") is not None:
                team_size_min = int(sem_res[0].get("team_size_min"))
            if sem_res[0].get("team_size_max") is not None:
                team_size_max = int(sem_res[0].get("team_size_max"))
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to check active status for semester in get_my_profile: {e}")

    # Build team response object with members (only name and roll_number)
    if hasattr(student, 'team_membership') and student.team_membership:
        team_obj = student.team_membership.team
        if team_obj:
            members_list = []
            for member in team_obj.members:
                m_avatar = getattr(member.student, "avatar_url", None) or f"https://ui-avatars.com/api/?name={member.student.name.replace(' ', '+')}&background=random"
                members_list.append({
                    "name": member.student.name,
                    "roll_number": member.student.student_id or member.student.id,
                    "avatar_url": m_avatar
                })
            
            from app.core.supabase_client import get_clean_team_name
            clean_team_name = get_clean_team_name(team_id=team_obj.id, raw_name=team_obj.name)
            team_data = {
                "id": str(team_obj.id),
                "name": clean_team_name,
                "project_title": team_obj.project_title,
                "members": members_list
            }
            
            # Form mentor response object (only name and email)
            if hasattr(team_obj, 'mentor') and team_obj.mentor:
                mentor_data = {
                    "name": team_obj.mentor.name,
                    "email": team_obj.mentor.email
                }

    avatar_url = getattr(student, "avatar_url", None) or f"https://ui-avatars.com/api/?name={student.name.replace(' ', '+')}&background=random"

    team_membership_data = None
    if hasattr(student, 'team_membership') and student.team_membership:
        team_membership_data = {
            "id": str(student.team_membership.id),
            "role": student.team_membership.role,
            "student_id": str(student.team_membership.student_id),
            "team_id": str(student.team_membership.team_id)
        }

    profile_data = {
        "id": str(student.id),
        "name": student.name,
        "email": student.email,
        "roll_number": student.student_id or student.id,
        "branch": student.branch,
        "section": student.section,
        "year": student.year,
        "avatar_url": avatar_url,
        "phone": student.phone,
        "bio": getattr(student, "bio", None),
        "skills": getattr(student, "skills", None),
        "team": team_data,
        "mentor": mentor_data,
        "isSemesterActive": is_sem_active,
        "lock_teams": lock_teams,
        "lockTeams": lock_teams,
        "lock_marks": lock_marks,
        "lockMarks": lock_marks,
        "results_published": results_published,
        "resultsPublished": results_published,
        "is_locked": is_locked,
        "isLocked": is_locked,
        "team_size_min": team_size_min,
        "team_size_max": team_size_max,
        "teamSizeMin": team_size_min,
        "teamSizeMax": team_size_max,
        "team_membership": team_membership_data
    }

    return ok(data=profile_data)


@router.patch("/me")
async def update_my_profile(
    payload: ProfileUpdatePayload,
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    """Update student profile details."""
    from sqlalchemy.future import select
    result = await db.execute(select(Student).where(Student.id == student.id))
    db_student = result.scalars().first()
    
    if not db_student:
        return error("Student not found", status_code=404)

    if payload.name is not None and payload.name.strip():
        db_student.name = payload.name.strip()
    if payload.phone is not None:
        db_student.phone = payload.phone.strip() if payload.phone else None
    if payload.bio is not None:
        db_student.bio = payload.bio.strip() if payload.bio else None
    if payload.skills is not None:
        db_student.skills = payload.skills.strip() if payload.skills else None
        
    await db.commit()
    return ok(message="Profile updated successfully")


@router.patch("/avatar")
async def update_student_avatar(
    payload: AvatarUpdatePayload,
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    """Update student profile picture avatar URL."""
    from sqlalchemy.future import select
    result = await db.execute(select(Student).where(Student.id == student.id))
    db_student = result.scalars().first()
    
    if not db_student:
        return error("Student not found", status_code=404)

    db_student.avatar_url = payload.avatar_url
    await db.commit()
    return ok(data={"avatar_url": db_student.avatar_url}, message="Avatar updated successfully")


# ---------------------------------------------------------------------------
# Task 2.2: Team Endpoints — GET /api/student/team and /team/members
# ---------------------------------------------------------------------------
@router.get("/team")
async def get_student_team(
    student: Student = Depends(get_current_student)
):
    """Expose read-only team data for the authenticated student, including GitHub stats."""
    if not student.team_membership or not student.team_membership.team:
        return ok(data=None)
    
    team_obj = student.team_membership.team
    members = []
    
    # 1. Fetch github details from database
    github_data = {
        "repository_url": None,
        "status": "none",
        "scores": {"quality": 0, "security": 0, "originality": 0, "architecture": 0, "documentation": 0},
        "tech_stack": [],
        "commit_count": 0,
        "contribution_distribution": []
    }
    
    raw_rep = None
    try:
        from app.core.supabase_client import supabase_client
        team_id_str = str(team_obj.id)
        numeric_team_id = parse_numeric_team_id(team_id_str)

        # Get authoritative team data for current student & semester
        tv_data = await supabase_client.get_team_by_student_id(str(student.id), student.semester_id)

        # Resolve everything by the team's immutable uuid. team_ref (slug) and
        # numeric_team_id (a reassignable display number) are only fallbacks — the
        # number is exactly how one team's dashboard ended up showing another
        # team's repository.
        team_uid = (tv_data or {}).get("uid") or getattr(team_obj, "uid", None)
        team_ref = (tv_data or {}).get("id")
        if team_uid:
            gh_filter = f"team_uid=eq.{team_uid}"
        elif team_ref:
            gh_filter = f"team_ref=eq.{team_ref}"
        else:
            gh_filter = f"team_id=eq.{numeric_team_id}"

        # The submitted repository lives in github_data.repository_url.
        #
        # This previously read tv_data["repo_url"] / ["repository_url"] and
        # team_obj.repository_url — none of which exist. teams_validation has no
        # repo column, and the team object assembled in student_deps carries no
        # such attribute, so the value was ALWAYS None: the portal showed an empty
        # "GitHub Code Repository URL" field even for teams that had submitted
        # one, and the analysis block below never ran for anybody.
        current_repo_url = None
        try:
            gd_rows = await supabase_client._request(
                f"github_data?{gh_filter}&select=repository_url&limit=1"
            )
            if gd_rows:
                current_repo_url = (gd_rows[0].get("repository_url") or "").strip() or None
        except Exception as gd_err:
            import logging as _logging
            _logging.getLogger(__name__).warning(f"Could not read submitted repository: {gd_err}")

        repo_url = current_repo_url
        gh = None
        if repo_url:
            gh_rows = await supabase_client._request(
                f"github_agent_analysis?{gh_filter}"
                "&select=repository_url,analysis_status,quality_score,security_score,"
                "originality_score,architecture_score,documentation_score,tech_stack,"
                "commit_count_30d,raw_report&limit=1"
            )
            if gh_rows:
                analysis_repo = (gh_rows[0].get("repository_url") or "").strip().lower()
                if not analysis_repo or analysis_repo.rstrip("/") == current_repo_url.lower().rstrip("/"):
                    gh = gh_rows[0]

        if gh and repo_url:
            raw_rep = gh.get("raw_report")
            if isinstance(raw_rep, str):
                try:
                    raw_rep = json.loads(raw_rep)
                except Exception:
                    raw_rep = None

            tech = gh.get("tech_stack")
            if isinstance(tech, str):
                try:
                    tech = json.loads(tech)
                except Exception:
                    pass

            commits_data = raw_rep.get("commits", {}) if isinstance(raw_rep, dict) else {}
            contrib_dist = []
            if isinstance(commits_data, dict):
                contrib_dist = commits_data.get("contributionDistribution", []) or []

            if not contrib_dist and isinstance(raw_rep, dict):
                indiv_scores = raw_rep.get("individualStudentScores") or []
                contrib_dist = [
                    {
                        "contributorName": s.get("name") or s.get("github") or "Unknown",
                        "commits": s.get("commits") or 0,
                        "percentage": s.get("contributionPercentage") or s.get("contributionScore") or 0,
                        "linesAdded": s.get("linesAdded") or 0,
                        "linesDeleted": s.get("linesDeleted") or 0
                    }
                    for s in indiv_scores
                ]

            github_data = {
                "repository_url": repo_url,
                "status": gh.get("analysis_status") or "completed",
                "scores": {
                    "quality": gh.get("quality_score") or 0,
                    "security": gh.get("security_score") or 0,
                    "originality": gh.get("originality_score") or 0,
                    "architecture": gh.get("architecture_score") or 0,
                    "documentation": gh.get("documentation_score") or 0
                },
                "tech_stack": tech or [],
                "commit_count": gh.get("commit_count_30d") or 0,
                "contribution_distribution": contrib_dist
            }
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error querying github analysis in get_student_team: {e}")

    # 2. Build members list with corresponding github stats mapped
    if hasattr(team_obj, "members") and team_obj.members:
        for member in team_obj.members:
            s = member.student
            
            # Map github stats
            member_stats = {
                "commits": 0,
                "contribution_percentage": 0,
                "lines_added": 0,
                "lines_deleted": 0
            }
            if github_data["status"] == "completed" and raw_rep and isinstance(raw_rep, dict):
                indiv_scores = raw_rep.get("individualStudentScores") or []
                m_name_clean = s.name.strip().lower().replace(" ", "")
                m_email_clean = s.email.strip().lower().replace(" ", "")
                
                match_score = None
                for s_score in indiv_scores:
                    s_name = str(s_score.get("name") or "").strip().lower().replace(" ", "")
                    s_email = str(s_score.get("email") or "").strip().lower().replace(" ", "")
                    
                    if (m_email_clean and s_email and m_email_clean == s_email) or \
                       (m_name_clean and s_name and (m_name_clean in s_name or s_name in m_name_clean)):
                        match_score = s_score
                        break
                
                if match_score:
                    member_stats = {
                        "commits": match_score.get("commits") or 0,
                        "contribution_percentage": match_score.get("contributionPercentage") or match_score.get("contributionScore") or 0,
                        "lines_added": match_score.get("linesAdded") or 0,
                        "lines_deleted": match_score.get("linesDeleted") or 0
                    }
                    
            members.append({
                "id": str(member.id),
                "student_id": str(s.id),
                "role": member.role,
                "student": {
                    "id": str(s.id),
                    "name": s.name,
                    "email": s.email,
                    "branch": s.branch,
                    "section": getattr(s, "section", "A")
                },
                "github_stats": member_stats
            })
            
    team_year = getattr(team_obj, "year", None)
    if not team_year and members and len(members) > 0:
        team_year = members[0].get("student", {}).get("year")

    leader_name = getattr(team_obj, "leader", None) or getattr(team_obj, "leader_id", None)
    try:
        from app.core.supabase_client import supabase_client
        tv_data = await supabase_client.get_team_by_student_id(str(student.id), student.semester_id)
        if tv_data and tv_data.get("leader"):
            leader_name = tv_data.get("leader")
    except Exception:
        pass

    team_size_min = 1
    team_size_max = 3
    sem_id = getattr(team_obj, "semester_id", None) or getattr(student, "semester_id", None)
    try:
        from app.core.supabase_client import supabase_client
        sem_res = None
        if sem_id:
            sem_res = await supabase_client._request(f"semester_config?id=eq.{sem_id}&limit=1")
        if not sem_res or len(sem_res) == 0:
            sem_res = await supabase_client._request("semester_config?is_active=eq.true&limit=1")
        if sem_res and len(sem_res) > 0:
            if sem_res[0].get("team_size_min") is not None:
                team_size_min = int(sem_res[0].get("team_size_min"))
            if sem_res[0].get("team_size_max") is not None:
                team_size_max = int(sem_res[0].get("team_size_max"))
    except Exception as e:
        import logging
    from app.core.supabase_client import get_clean_team_name
    clean_team_name = get_clean_team_name(
        team_id=team_obj.id,
        raw_name=team_obj.name,
        tv_id=tv_data.get("id") if tv_data else None
    )

    data = {
        "id": str(team_obj.id),
        "name": clean_team_name,
        "project_title": team_obj.project_title,
        "description": getattr(team_obj, "description", "") or "",
        "leader": leader_name or "",
        "leader_id": leader_name or "",
        "semester_id": team_obj.semester_id,
        "year": team_year or 3,
        "created_at": team_obj.created_at.isoformat() if hasattr(team_obj, "created_at") and team_obj.created_at else None,
        "members": members,
        "github": github_data,
        "status": getattr(team_obj, "status", "pending"),
        "validationStatus": getattr(team_obj, "status", "pending"),
        "team_size_min": team_size_min,
        "team_size_max": team_size_max,
        "teamSizeMin": team_size_min,
        "teamSizeMax": team_size_max,
    }
    return ok(data=data)


@router.get("/team/members")
async def get_student_team_members(
    student: Student = Depends(get_current_student)
):
    """Return an array of all members in the same team."""
    if not student.team_membership or not student.team_membership.team:
        return ok(data=[])
    
    team_obj = student.team_membership.team
    members = []
    for member in team_obj.members:
        s = member.student
        avatar_url = getattr(s, "avatar_url", None) or f"https://ui-avatars.com/api/?name={s.name.replace(' ', '+')}&background=random"
        members.append({
            "id": str(s.id),
            "name": s.name,
            "email": s.email,
            "roll_number": s.student_id or s.id,
            "branch": s.branch,
            "section": s.section,
            "avatar_url": avatar_url
        })
    return ok(data=members)


# ---------------------------------------------------------------------------
# Task 2.3: Proposals Endpoints — GET list, POST submit, GET detail
# ---------------------------------------------------------------------------
@router.get("/proposals")
async def get_student_proposals(
    student: Student = Depends(get_current_student)
):
    """Returns all proposals submitted by the student's team."""
    if not student.team_membership or not student.team_membership.team:
        return ok(data=[])
    
    from app.core.supabase_client import supabase_client, extract_numeric_id

    def _is_uuid(val: str) -> bool:
        try:
            uuid.UUID(str(val))
            return True
        except (ValueError, AttributeError, TypeError):
            return False

    team_obj = student.team_membership.team
    team_uid_val = str(
        getattr(student.team_membership, "team_uid", "")
        or getattr(team_obj, "uid", "")
        or ""
    ).strip()

    rows = []
    if _is_uuid(team_uid_val):
        # Canonical path: exact uuid match. Cannot leak across teams, so no
        # post-filter is needed.
        rows = await supabase_client._request(
            f"proposals?team_uid=eq.{team_uid_val}"
        ) or []
    else:
        # Fallback for a team that has no uid yet: the old unambiguous-variant
        # search, still guarded against cross-team leakage.
        raw_team_id_str = str(student.team_membership.team_id)
        num_id = extract_numeric_id(raw_team_id_str)
        id_variants = list(dict.fromkeys(filter(None, [
            raw_team_id_str,
            f"TEAM-{num_id}" if num_id else None,
        ])))
        seen_ids = set()
        for variant in id_variants:
            try:
                result = await supabase_client._request(f"proposals?teamId=eq.{variant}")
                for r in (result or []):
                    if r.get("id") not in seen_ids:
                        seen_ids.add(r.get("id"))
                        rows.append(r)
            except Exception:
                pass
        valid_ids_lower = {v.strip().lower() for v in id_variants}
        rows = [
            r for r in rows
            if str(r.get("teamId") or "").strip().lower() in valid_ids_lower
        ]
    
    proposals = []
    for r in rows:
        proposals.append({
            "id": r.get("id"),
            "title": r.get("title"),
            "description": r.get("aiRationale") or r.get("description"),
            "status": r.get("status"),
            "submitted_at": r.get("submittedDate") or r.get("submitted_at"),
            "feedback": r.get("remarks") or r.get("feedback"),
            "proposalFile": r.get("proposalFile") or r.get("proposal_file")
        })
    return ok(data=proposals)


@router.get("/proposals/{proposal_id}")
async def get_student_proposal_detail(
    proposal_id: str,
    student: Student = Depends(get_current_student)
):
    """Returns full details of one specific proposal."""
    if not student.team_membership or not student.team_membership.team:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student is not assigned to a team"
        )
    
    from app.core.supabase_client import supabase_client
    rows = await supabase_client._request(f"proposals?id=eq.{proposal_id}&limit=1")
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposal not found"
        )
    
    r = rows[0]
    from app.core.supabase_client import extract_numeric_id

    # Ownership check: prefer the exact team_uid match; fall back to the legacy
    # teamId string / number comparison only when the proposal row has no team_uid.
    team_uid_val = str(
        getattr(student.team_membership, "team_uid", "")
        or getattr(student.team_membership.team, "uid", "")
        or ""
    ).strip()
    row_uid = str(r.get("team_uid") or "").strip()
    team_id = student.team_membership.team_id
    team_id_str = str(team_id)
    if team_id_str.isdigit():
        team_id_str = f"TEAM-{team_id}"
    db_team_id = r.get("teamId") or ""

    if team_uid_val and row_uid:
        owns = (row_uid == team_uid_val)
    else:
        owns = (db_team_id == team_id_str) or (
            extract_numeric_id(db_team_id) == extract_numeric_id(team_id_str)
            and extract_numeric_id(db_team_id) != 0
        )
    if not owns:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
        
    data = {
        "id": r.get("id"),
        "title": r.get("title"),
        "description": r.get("aiRationale") or r.get("description"),
        "status": r.get("status"),
        "submitted_at": r.get("submittedDate") or r.get("submitted_at"),
        "feedback": r.get("remarks") or r.get("feedback"),
        "proposalFile": r.get("proposalFile") or r.get("proposal_file")
    }
    return ok(data=data)


@router.post("/proposals", status_code=201)
async def submit_student_proposal(
    payload: SimpleProposalPayload,
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    """Submit a project proposal (Leader-only, deadline enforced)."""
    from app.services.governance_service import GovernanceService
    await GovernanceService.enforce_deadline(db, student.semester_id, "proposalUpload")

    if not student.team_membership or not student.team_membership.team:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student is not assigned to any team"
        )
        
    # 1. Check if user is leader
    if student.team_membership.role != "LEADER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the team leader can submit proposals"
        )
        
    # Canonical team identity.
    from app.core.supabase_client import supabase_client, extract_numeric_id
    raw_team_id = student.team_membership.team_id
    raw_team_id_str = str(raw_team_id)
    team_uid_val = str(
        getattr(student.team_membership, "team_uid", "")
        or getattr(student.team_membership.team, "uid", "")
        or ""
    ).strip()

    existing_rows = []
    if team_uid_val:
        existing_rows = await supabase_client._request(
            f"proposals?team_uid=eq.{team_uid_val}"
        ) or []
    else:
        num_id = extract_numeric_id(raw_team_id_str)
        id_variants = list(dict.fromkeys(filter(None, [
            raw_team_id_str, (f"TEAM-{num_id}" if num_id else None)
        ])))
        for variant in id_variants:
            rows_found = await supabase_client._request(f"proposals?teamId=eq.{variant}")
            if rows_found:
                existing_rows = rows_found
                break

    # FIX (Bug 2): Determine if the most-recent proposal was rejected or needs revision.
    # Sort by submitted date descending to find the true latest proposal.
    sorted_rows = sorted(
        existing_rows,
        key=lambda p: p.get("submittedDate") or p.get("submitted_at") or "",
        reverse=True
    )
    latest_status = (sorted_rows[0].get("status") or "").strip().lower() if sorted_rows else ""
    is_resubmission = latest_status in (
        "rejected", "revision requested", "revision_requested",
        "Rejected".lower(), "Revision Requested".lower()
    )

    # 2. Enforce deadline — skip entirely when re-submitting after rejection/revision.
    if not is_resubmission:
        from app.models.deadline import Deadline
        due_date = datetime.strptime("2026-12-31 23:59:59", "%Y-%m-%d %H:%M:%S")  # far future default
        try:
            stmt = select(Deadline).where(
                Deadline.semester_id == student.semester_id,
                Deadline.type.in_(["proposal", "proposalUpload"])
            )
            res = await db.execute(stmt)
            deadline_row = res.scalars().first()
            if deadline_row:
                due_date = deadline_row.due_date
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to query deadline for semester {student.semester_id}: {e}")

        from datetime import timezone, timedelta
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=ist_tz)
        else:
            due_date = due_date.astimezone(ist_tz)

        if datetime.now(ist_tz) > due_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Proposal submission deadline has passed"
            )
        
    # 3. Check for conflict — ONLY block if there is still a Pending/Approved proposal.
    # A Rejected or Revision Requested proposal MUST NOT block re-submission.
    for p in existing_rows:
        p_status = (p.get("status") or "").strip().lower()
        if p_status in ("pending", "approved"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active proposal already exists for this team"
            )
    
    # The student's own semester is already validated as active in student_deps.
    # Do NOT collapse to "the first active semester" — multiple batches
    # (different B.Tech years) are active at once.
    real_semester_id = student.semester_id

    # Insert new proposal. team_uid is the canonical link; teamId is kept as the
    # legacy alias for readers not yet migrated.
    proposal_id = f"PROP-{uuid.uuid4().hex[:8].upper()}"
    new_prop = {
        "id": proposal_id,
        "teamId": raw_team_id_str,
        **({"team_uid": team_uid_val} if team_uid_val else {}),
        "title": payload.title,
        "aiRationale": payload.description,
        "status": "Pending",
        "submittedDate": datetime.utcnow().strftime("%Y-%m-%d"),
        "semester_id": real_semester_id,
        **({"proposalFile": _require_web_url(payload.proposalFile, "Proposal file link")} if payload.proposalFile else {})
    }
    
    await supabase_client._request("proposals", method="POST", body=[new_prop])
    
    try:
        from app.services.email_service import notify_student_proposal_submitted
        recip_emails = [m.student.email for m in student.team_membership.team.members if m.student and m.student.email] if (student.team_membership and student.team_membership.team) else []
        if student.email and student.email not in recip_emails:
            recip_emails.append(student.email)
        notify_student_proposal_submitted(recip_emails, raw_team_id_str, payload.title)
    except Exception:
        pass

    return ok(data=new_prop)





# ---------------------------------------------------------------------------
# Task 2.4: Schedule Endpoint — GET /api/student/schedule
# ---------------------------------------------------------------------------
@router.get("/schedule")
async def get_student_schedule(
    student: Student = Depends(get_current_student)
):
    """
    Return all presentation slots scheduled for the student's team,
    including date, time, room, mode, and panel member details.
    """
    team_id = student.team_membership.team_id if (hasattr(student, 'team_membership') and student.team_membership) else None
    if not team_id:
        return ok(data=[])

    from app.core.supabase_client import supabase_client
    import re

    # 1. Fetch scheduled presentation slots for the team
    slots = await supabase_client.get_schedule_slots_by_team(team_id)
    if not slots:
        return ok(data=[])

    # 2. Parse and sort slots chronologically
    def get_sort_key(s):
        try:
            date_val = datetime.strptime(s.get("date", ""), "%Y-%m-%d").date()
            time_range = s.get("time", "")
            start_time_str = time_range.split("-")[0].strip()
            match = re.match(r"(\d+):(\d+)\s*(am|pm)", start_time_str.lower())
            if match:
                h, m, period = match.groups()
                h = int(h)
                m = int(m)
                if period == "pm" and h != 12:
                    h += 12
                elif period == "am" and h == 12:
                    h = 0
                return (date_val, time(h, m))
        except Exception:
            pass
        return (date.max, time.max)

    slots = sorted(slots, key=get_sort_key)

    # 3. Fetch all panels, mentors, evaluations, results, and presentation cycles
    panels_res, mentors_res, evaluations, results, cycles_res = await asyncio.gather(
        supabase_client._request("panels"),
        supabase_client._request("mentors"),
        supabase_client.get_evaluations_by_team(team_id),
        supabase_client.get_results_by_team(team_id),
        supabase_client._request(f"presentation_cycles?semester_id=eq.{student.semester_id}") if getattr(student, "semester_id", None) else asyncio.sleep(0, [])
    )

    mentor_by_name = {m["name"]: m for m in mentors_res if m.get("name")}
    panel_by_name = {p["name"]: p for p in panels_res if p.get("name")}

    cycle_type_map = {}
    if cycles_res and isinstance(cycles_res, list):
        for c in cycles_res:
            cid = c.get("id")
            ctype = c.get("type")
            if cid and ctype:
                cycle_type_map[str(cid)] = str(ctype)

    # 4. Map each schedule slot to the target format
    result_schedules = []
    for idx, s in enumerate(slots):
        # Derive evaluation type from cycle_id if available, otherwise fall back to index-based logic
        slot_cycle_id = s.get("cycle_id")
        evaluation_type = None
        if slot_cycle_id and str(slot_cycle_id) in cycle_type_map:
            evaluation_type = cycle_type_map[str(slot_cycle_id)]

        if not evaluation_type:
            if len(slots) == 1:
                evaluation_type = "mid"
            elif len(slots) == 2:
                evaluation_type = "mid" if idx == 0 else "final"
            else:
                evaluation_type = "proposal" if idx == 0 else ("mid" if idx == 1 else "final")

        panel_name = s.get("panel")
        panel_id = None
        panel_members = []

        if panel_name:
            panel_row = panel_by_name.get(panel_name)
            if panel_row:
                panel_id = panel_row.get("id")
                members = panel_row.get("members", [])
                if isinstance(members, str):
                    try:
                        members = json.loads(members)
                    except Exception:
                        members = []
                
                if members:
                    for member_name in members:
                        mentor = mentor_by_name.get(member_name)
                        panel_members.append({
                            "name": member_name,
                            "email": mentor.get("email") if mentor else None,
                            "designation": "Panel Member"
                        })
            
            # If panel members list is empty, default to panel itself (coordinator)
            if not panel_members:
                mentor = mentor_by_name.get(panel_name)
                panel_members.append({
                    "name": panel_name,
                    "email": mentor.get("email") if mentor else None,
                    "designation": "Panel Member"
                })

        # Derive status
        status = "scheduled"
        has_evaluation = False
        if evaluations:
            for e in evaluations:
                e_cycle_id = e.get("cycle_id")
                # If slot has a cycle_id, match by cycle_id.
                if slot_cycle_id:
                    if str(e_cycle_id) == str(slot_cycle_id):
                        has_evaluation = True
                        break
                # If slot has no cycle_id, match by panel_id and cycle_id is None.
                else:
                    if not e_cycle_id and str(e.get("panel_id")) == str(panel_id):
                        has_evaluation = True
                        break

        has_evaluation_in_results = False
        if results:
            if evaluation_type == "mid" and results.get("midMarks") is not None:
                has_evaluation_in_results = True
            elif evaluation_type == "final" and results.get("finalMarks") is not None:
                has_evaluation_in_results = True
            elif evaluation_type == "proposal" and results.get("proposalMarks") is not None:
                has_evaluation_in_results = True

        if has_evaluation or has_evaluation_in_results:
            status = "completed"

        meet_link = s.get("meetLink") or s.get("meet_link") or None
        if meet_link and "jit.si" in str(meet_link).lower():
            code = str(meet_link).split("/")[-1].replace("procksi-evaluation-", "")
            meet_link = f"https://meet.google.com/{code}" if code else "https://meet.google.com/new"
            
        room_val = s.get("room") or s.get("venue") or ""
        room_lower = str(room_val).lower()
        is_online = room_lower in ("online", "virtual", "zoom", "teams")

        result_schedules.append({
            "id": s.get("id"),
            "date": s.get("date"),
            "time_slot": s.get("time"),
            "room": room_val or "TBD",
            "meet_link": meet_link,
            "mode": "online" if (meet_link or is_online) else "offline",
            "panel_members": panel_members,
            "evaluation_type": evaluation_type,
            "status": status
        })

    return ok(data=result_schedules)


# ---------------------------------------------------------------------------
# Task 2.5: Evaluations Endpoint — GET /api/student/evaluations
# ---------------------------------------------------------------------------
@router.get("/evaluations")
async def get_student_evaluations(
    student: Student = Depends(get_current_student)
):
    """
    Return all evaluation scores for the authenticated student,
    supporting both dynamic cycles and legacy (proposal, mid, final).
    """
    team_id = student.team_membership.team_id if (student.team_membership and student.team_membership.team) else None
    if not team_id:
        return ok(data={
            "proposal": None,
            "mid": None,
            "final": None,
            "cycles": []
        })

    team_id_str = str(team_id)
    if team_id_str.isdigit():
        team_id_str = f"TEAM-{team_id}"
    from app.core.supabase_client import supabase_client
    
    sem_id = student.semester_id
    
    cycles_res, slots, results, evaluations, panels_res, mentors_res = await asyncio.gather(
        supabase_client._request(f"presentation_cycles?semester_id=eq.{sem_id}&order=created_at.asc") if sem_id else asyncio.sleep(0, []),
        supabase_client.get_schedule_slots_by_team(team_id_str),
        supabase_client.get_results_by_team(team_id_str),
        supabase_client.get_evaluations_by_team(team_id),
        supabase_client._request("panels"),
        supabase_client._request("mentors")
    )

    cycles = cycles_res or []
    panel_by_name = {p["name"]: p for p in panels_res if p.get("name")}
    mentor_by_name = {m["name"]: m for m in mentors_res if m.get("name")}

    results_published = False
    if sem_id:
        try:
            sem_res = await supabase_client._request(f"semester_config?id=eq.{sem_id}&limit=1")
            if sem_res:
                results_published = bool(sem_res[0].get("results_published"))
        except Exception:
            pass

    rubrics_by_cycle = {}
    if cycles:
        cycle_ids = [c.get("id") for c in cycles if c.get("id")]
        if cycle_ids:
            cycle_ids_str = ",".join([str(cid) for cid in cycle_ids])
            rubrics_data = await supabase_client._request(f"presentation_rubrics?cycle_id=in.({cycle_ids_str})")
            for r in (rubrics_data or []):
                cid = r.get("cycle_id")
                rubrics_by_cycle.setdefault(cid, []).append(r)

    cycle_list = []
    
    for cycle in cycles:
        cid = cycle.get("id")
        weightage = float(cycle.get("weightage") or 0)
        cycle_title = cycle.get("title") or cycle.get("name") or "Presentation"
        cycle_type = cycle.get("type") or "mid"
        
        cycle_rubrics = rubrics_by_cycle.get(cid, [])
        cycle_max_marks = sum(float(rub.get("max_marks") or 0) for rub in cycle_rubrics)
        if cycle_max_marks <= 0:
            cycle_max_marks = 40.0
            
        cycle_eval = next((e for e in evaluations if e.get("cycle_id") == cid), None)
        
        score = None
        remarks = None
        panel_members = []
        schedule_date = None
        
        slot = next((s for s in slots if s.get("cycle_id") == cid), None)
        if slot:
            schedule_date = slot.get("date")
            panel_name = slot.get("panel")
            if panel_name:
                panel_row = panel_by_name.get(panel_name)
                if panel_row:
                    members = panel_row.get("members", [])
                    if isinstance(members, str):
                        try:
                            members = json.loads(members)
                        except Exception:
                            members = []
                    for m_name in members:
                        m_details = mentor_by_name.get(m_name)
                        panel_members.append({
                            "name": m_name,
                            "email": m_details.get("email") if m_details else None,
                            "designation": "Panel Member"
                        })
                if not panel_members:
                    m_details = mentor_by_name.get(panel_name)
                    panel_members.append({
                        "name": panel_name,
                        "email": m_details.get("email") if m_details else None,
                        "designation": "Panel Member"
                    })
                    
        if cycle_eval:
            remarks = cycle_eval.get("remarks")
            normalized_score_val = cycle_eval.get("total_score")
            if normalized_score_val is not None:
                score = round((float(normalized_score_val) / 100.0) * cycle_max_marks)
                if score == int(score):
                    score = int(score)
            elif cycle_eval.get("scores_json"):
                scores_json = cycle_eval["scores_json"]
                try:
                    if isinstance(scores_json, str):
                        scores_dict = json.loads(scores_json)
                    else:
                        scores_dict = scores_json
                    if isinstance(scores_dict, dict) and scores_dict:
                        total_raw = sum(int(v) for v in scores_dict.values())
                        val = (total_raw / 40.0) * cycle_max_marks
                        score = int(val) if val == int(val) else round(val, 2)
                except Exception:
                    pass
                    
        if not results_published and not cycle_eval:
            score = None
            
        cycle_list.append({
            "cycle_id": cid,
            "type": cycle_type,
            "presentation": cycle_title,
            "weightage": weightage,
            "score": score,
            "max_score": cycle_max_marks,
            "schedule_date": schedule_date,
            "panel_members": panel_members,
            "remarks": remarks
        })

    proposal_data = next((c for c in cycle_list if c["type"] == "proposal"), None)
    mid_data = next((c for c in cycle_list if c["type"] == "mid"), None)
    final_data = next((c for c in cycle_list if c["type"] == "final"), None)

    if not proposal_data and len(cycle_list) > 0:
        proposal_data = cycle_list[0]
    if not mid_data and len(cycle_list) > 1:
        mid_data = cycle_list[1]
    if not final_data and len(cycle_list) > 2:
        final_data = cycle_list[2]

    if not cycle_list:
        def get_sort_key(s):
            try:
                date_val = datetime.strptime(s.get("date", ""), "%Y-%m-%d").date()
                time_range = s.get("time", "")
                start_time_str = time_range.split("-")[0].strip()
                match = re.match(r"(\d+):(\d+)\s*(am|pm)", start_time_str.lower())
                if match:
                    h, m, period = match.groups()
                    h = int(h)
                    m = int(m)
                    if period == "pm" and h != 12:
                        h += 12
                    elif period == "am" and h == 12:
                        h = 0
                    return (date_val, time(h, m))
            except Exception:
                pass
            return (date.max, time.max)

        sorted_slots = sorted(slots, key=get_sort_key)
        
        legacy_data = {
            "proposal": None,
            "mid": None,
            "final": None
        }
        
        if results_published and results and results.get("proposalMarks") is not None:
            legacy_data["proposal"] = {
                "score": results["proposalMarks"],
                "max_score": 20,
                "schedule_date": "2026-03-15",
                "panel_members": [{"name": "Faculty Coordinator", "email": None, "designation": "Coordinator"}],
                "remarks": "Approved scope."
            }

        for idx, s in enumerate(sorted_slots):
            if len(sorted_slots) == 1:
                evaluation_type = "mid"
            elif len(sorted_slots) == 2:
                evaluation_type = "mid" if idx == 0 else "final"
            else:
                evaluation_type = "proposal" if idx == 0 else ("mid" if idx == 1 else "final")

            score = None
            if results_published and results:
                if evaluation_type == "proposal":
                    score = results.get("proposalMarks")
                elif evaluation_type == "mid":
                    score = results.get("midMarks")
                elif evaluation_type == "final":
                    score = results.get("finalMarks")

            remarks = None
            scores_json = None
            panel_name = s.get("panel")
            panel_id = None
            panel_members = []

            if panel_name:
                panel_row = panel_by_name.get(panel_name)
                if panel_row:
                    panel_id = panel_row.get("id")
                    members = panel_row.get("members", [])
                    if isinstance(members, str):
                        try:
                            members = json.loads(members)
                        except Exception:
                            members = []
                    for m_name in members:
                        m_details = mentor_by_name.get(m_name)
                        panel_members.append({
                            "name": m_name,
                            "email": m_details.get("email") if m_details else None,
                            "designation": "Panel Member"
                        })
                if not panel_members:
                    m_details = mentor_by_name.get(panel_name)
                    panel_members.append({
                        "name": panel_name,
                        "email": m_details.get("email") if m_details else None,
                        "designation": "Panel Member"
                    })

            legacy_eval = next((e for e in evaluations if str(e.get("panel_id")) == str(panel_id)), None) if panel_id else None
            if legacy_eval:
                remarks = legacy_eval.get("remarks")
                scores_json = legacy_eval.get("scores_json")

            if score is None and scores_json:
                try:
                    if isinstance(scores_json, str):
                        scores_dict = json.loads(scores_json)
                    else:
                        scores_dict = scores_json
                    
                    if isinstance(scores_dict, dict) and scores_dict:
                        total_raw = sum(int(v) for v in scores_dict.values())
                        max_score = 30
                        if evaluation_type == "proposal":
                            max_score = 20
                        elif evaluation_type == "final":
                            max_score = 50
                        
                        val = (total_raw / 40.0) * max_score
                        score = int(val) if val == int(val) else round(val, 2)
                except Exception:
                    pass

            legacy_data[evaluation_type] = {
                "score": score,
                "max_score": 20 if evaluation_type == "proposal" else (30 if evaluation_type == "mid" else 50),
                "schedule_date": s.get("date"),
                "panel_members": panel_members,
                "remarks": remarks
            }
            
        proposal_data = legacy_data["proposal"]
        mid_data = legacy_data["mid"]
        final_data = legacy_data["final"]
        
        if proposal_data:
            cycle_list.append({"type": "proposal", "presentation": "Proposal Review", "max_score": 20, **proposal_data})
        if mid_data:
            cycle_list.append({"type": "mid", "presentation": "Mid-Term Presentation", "max_score": 30, **mid_data})
        if final_data:
            cycle_list.append({"type": "final", "presentation": "Final Presentation", "max_score": 50, **final_data})

    return ok(data={
        "proposal": proposal_data,
        "mid": mid_data,
        "final": final_data,
        "cycles": cycle_list
    })


# ---------------------------------------------------------------------------
# Task 2.6: Results Endpoint — GET /api/student/results
# ---------------------------------------------------------------------------
@router.get("/results/semesters")
async def get_student_result_semesters(
    student: Student = Depends(get_current_student)
):
    from app.core.supabase_client import supabase_client
    student_roll = student.id
    
    try:
        all_tv = await supabase_client._request("teams_validation")
        student_semesters = set()
        
        for tv in (all_tv or []):
            members = tv.get("members") or []
            if isinstance(members, str):
                try:
                    import json as _json
                    members = _json.loads(members)
                except Exception:
                    members = []
            
            is_member = False
            for m in members:
                m_id = str(m.get("id") or m.get("roll") or "")
                if m_id == str(student_roll) or m_id == str(student.student_id):
                    is_member = True
                    break
            
            if is_member and tv.get("semester_id"):
                student_semesters.add(tv["semester_id"])
                
        if student.semester_id:
            student_semesters.add(student.semester_id)
            
        if not student_semesters:
            return ok(data=[])
            
        sems = await supabase_client._request("semester_config")
        results_sems = []
        for s in (sems or []):
            if s.get("id") in student_semesters:
                results_sems.append({
                    "id": s["id"],
                    "year": s.get("year"),
                    "semester_type": s.get("semester_type"),
                    "branch": s.get("branch"),
                    "is_active": s.get("is_active"),
                    "results_published": s.get("results_published")
                })
        
        return ok(data=results_sems)
    except Exception as e:
        print("ERROR IN GET RESULT SEMESTERS:", e)
        return ok(data=[])


@router.get("/results")
async def get_student_results(
    semester_id: Optional[str] = None,
    student: Student = Depends(get_current_student)
):
    """Return the final aggregated result for the student, cycle-aware."""
    from app.core.supabase_client import supabase_client

    sem_id = semester_id or student.semester_id
    if not sem_id:
        try:
            active_sems = await supabase_client._request("semester_config?is_active=eq.true&limit=1")
            if active_sems:
                sem_id = active_sems[0].get("id")
        except Exception:
            pass

    if not sem_id:
        return ok(data=None)

    results_published = False
    sem_data = None
    try:
        sem_res = await supabase_client._request(f"semester_config?id=eq.{sem_id}&limit=1")
        if sem_res:
            sem_data = sem_res[0]
            results_published = bool(sem_data.get("results_published"))
    except Exception:
        pass

    if not results_published:
        return ok(data=None)

    # ── Find team string id for this semester ──────────────────────────────
    target_team_id_str = None
    try:
        all_tv = await supabase_client._request(f"teams_validation?semester_id=eq.{sem_id}")
        student_roll = student.id
        for tv in (all_tv or []):
            members = tv.get("members") or []
            if isinstance(members, str):
                try:
                    members = _json.loads(members)
                except Exception:
                    members = []

            is_member = False
            for m in members:
                m_id = str(m.get("id") or m.get("roll") or "")
                if m_id == str(student_roll) or m_id == str(student.student_id):
                    is_member = True
                    break
            if is_member:
                target_team_id_str = tv["id"]
                break
    except Exception as e:
        print("ERROR FINDING TEAM FOR SEMESTER:", e)

    if not target_team_id_str:
        raw_team_id = student.team_membership.team_id if (student.team_membership and student.team_membership.team) else None
        if raw_team_id:
            target_team_id_str = str(raw_team_id)

    if not target_team_id_str:
        return ok(data=None)

    from app.core.supabase_client import extract_numeric_id
    num_id = extract_numeric_id(target_team_id_str)
    canonical_team_id = f"TEAM-{num_id}" if num_id else target_team_id_str

    override_reason = None

    # ── Try cycle-based evaluation scores first ────────────────────────────
    try:
        cycles = await supabase_client._request(
            f"presentation_cycles?semester_id=eq.{sem_id}&order=created_at.asc"
        )
        evaluations = await supabase_client.get_evaluations_by_team(target_team_id_str)

        if cycles and evaluations:
            cycle_ids = [c.get("id") for c in cycles if c.get("id")]
            rubrics_data = []
            if cycle_ids:
                cycle_ids_str = ",".join([str(cid) for cid in cycle_ids])
                rubrics_data = await supabase_client._request(f"presentation_rubrics?cycle_id=in.({cycle_ids_str})")
            
            rubrics_by_cycle = {}
            for r in (rubrics_data or []):
                cid = r.get("cycle_id")
                rubrics_by_cycle.setdefault(cid, []).append(r)

            cycle_scores = []
            total_score = 0.0
            all_cycles_evaluated = True

            for cycle in cycles:
                cid = cycle.get("id")
                weightage = float(cycle.get("weightage") or 0)
                cycle_title = cycle.get("title") or cycle.get("name") or "Presentation"

                # Find evaluation for this cycle
                cycle_eval = next((e for e in evaluations if e.get("cycle_id") == cid), None)

                # Compute exact max marks for this cycle
                cycle_rubrics = rubrics_by_cycle.get(cid, [])
                cycle_max_marks = sum(float(rub.get("max_marks") or 0) for rub in cycle_rubrics)
                if cycle_max_marks <= 0:
                    try:
                        # Fallback: check semester config
                        sem_res = await supabase_client._request(f"semester_config?id=eq.{sem_id}&limit=1")
                        if sem_res and sem_res[0].get("evaluation_parameters"):
                            params = sem_res[0]["evaluation_parameters"]
                            cycle_max_marks = sum(float(p.get("max_marks") or 0) for p in params)
                    except Exception:
                        pass
                if cycle_max_marks <= 0:
                    cycle_max_marks = 40.0  # legacy fallback

                if cycle_eval:
                    normalized_score_val = float(cycle_eval.get("total_score") or 0)
                    actual_raw_score = round((normalized_score_val / 100.0) * cycle_max_marks)
                    weighted = round((normalized_score_val / 100.0) * weightage, 2)
                    cycle_scores.append({
                        "cycle_id": cid,
                        "presentation": cycle_title,
                        "weightage": weightage,
                        "raw_score": actual_raw_score,
                        "max_score": cycle_max_marks,
                        "weighted_score": weighted
                    })
                    total_score += weighted
                else:
                    all_cycles_evaluated = False
                    cycle_scores.append({
                        "cycle_id": cid,
                        "presentation": cycle_title,
                        "weightage": weightage,
                        "raw_score": None,
                        "max_score": cycle_max_marks,
                        "weighted_score": None
                    })

            if any(cs["raw_score"] is not None for cs in cycle_scores):
                # Grade from weighted total (out of 100 since weightages sum to 100)
                grade = "F"
                if total_score >= 85:
                    grade = "A+"
                elif total_score >= 70:
                    grade = "A"
                elif total_score >= 50:
                    grade = "B"
                elif total_score >= 40:
                    grade = "C"

                return ok(data={
                    "team": canonical_team_id,
                    "total_score": round(total_score, 2),
                    "grade": grade,
                    "override_reason": override_reason,
                    "semester_id": sem_id,
                    "cycle_scores": cycle_scores,
                    # Legacy fields for backward compat
                    "proposal_score": None,
                    "mid_score": None,
                    "final_score": None,
                })
    except Exception as e:
        print("ERROR COMPUTING CYCLE SCORES:", e)

    # ── Fall back to legacy results table ─────────────────────────────────
    results = None
    for variant in list(dict.fromkeys(filter(None, [
        target_team_id_str,
        f"TEAM-{num_id}" if num_id else None,
    ]))):
        results = await supabase_client._request(f"results?team=eq.{variant}&limit=1")
        if results:
            results = results[0]
            break

    if not results:
        return ok(data=None)

    proposal_score = results.get("proposalMarks") or 0.0
    mid_score = results.get("midMarks") or 0.0
    final_score = results.get("finalMarks") or 0.0
    total_score = results.get("totalScore") or (proposal_score + mid_score + final_score)
    override_reason = results.get("override_reason")

    grade = "F"
    if total_score >= 85:
        grade = "A+"
    elif total_score >= 70:
        grade = "A"
    elif total_score >= 50:
        grade = "B"
    elif total_score >= 40:
        grade = "C"

    return ok(data={
        "team": results.get("team"),
        "title": results.get("title"),
        "domain": results.get("domain"),
        "branch": results.get("branch"),
        "proposal_score": proposal_score,
        "mid_score": mid_score,
        "final_score": final_score,
        "total_score": total_score,
        "grade": grade,
        "override_reason": override_reason,
        "semester_id": sem_id,
        "cycle_scores": None,
    })


# ---------------------------------------------------------------------------
# Task 2.7: Mentor Endpoint — GET /api/student/mentor
# ---------------------------------------------------------------------------
@router.get("/mentor")
async def get_student_mentor(
    student: Student = Depends(get_current_student)
):
    """Return the details of the mentor(s) assigned to the student's team.
    Returns a list when multiple mentors are assigned.
    """
    if not (student.team_membership and student.team_membership.team):
        return ok(data=None)

    team_obj = student.team_membership.team

    # --- Helper: serialize one mentor object ---
    def _serialize(m):
        domain_raw = getattr(m, 'expertise', '') or ''
        domains = [d.strip() for d in str(domain_raw).split(',') if d.strip()] or [str(domain_raw)]
        return {
            "id": str(getattr(m, 'id', '') or ''),
            "name": getattr(m, 'name', ''),
            "email": getattr(m, 'email', '') or '',
            "phone": getattr(m, 'phone', '') or '',
            "department": "Faculty",
            "expertise": domains,
            "skills": domains,
            "domains": domains,
            "availability": "Contact via email"
        }

    # FIX (Bug 1) Fast path: use mentors list resolved in student_deps
    if hasattr(team_obj, 'mentors') and team_obj.mentors:
        serialized = [_serialize(m) for m in team_obj.mentors]
        return ok(data=serialized)

    # Fallback fast path: single mentor
    if hasattr(team_obj, 'mentor') and team_obj.mentor:
        return ok(data=[_serialize(team_obj.mentor)])

    # Slow path: query teams_validation directly with all ID variants
    raw_team_id = student.team_membership.team_id
    raw_team_id_str = str(raw_team_id)
    from app.core.supabase_client import supabase_client, extract_numeric_id
    num_id = extract_numeric_id(raw_team_id_str)
    
    team_res = None
    for variant in list(dict.fromkeys(filter(None, [
        raw_team_id_str, f"TEAM-{num_id}" if num_id else None
    ]))):
        res = await supabase_client._request(f"teams_validation?id=eq.{variant}&limit=1")
        if res:
            team_res = res
            break
    
    if not team_res:
        return ok(data=None)
        
    team_data = team_res[0]
    raw_mentor = team_data.get("mentor") or ""
    if not raw_mentor or raw_mentor.strip() == "--":
        return ok(data=None)

    # Parse mentor names list
    mentor_names = []
    try:
        import json as _json
        parsed = _json.loads(raw_mentor)
        if isinstance(parsed, list):
            mentor_names = [str(m).strip() for m in parsed if str(m).strip()]
        else:
            mentor_names = [str(parsed).strip()]
    except Exception:
        mentor_names = [n.strip() for n in raw_mentor.split(",") if n.strip()]

    if not mentor_names:
        return ok(data=None)

    # FIX (Bug 1): Resolve all mentor names, not just the first one
    serialized_mentors = []
    for m_name in mentor_names:
        mentor_row = await supabase_client.get_mentor_by_name(m_name)
        if not mentor_row:
            serialized_mentors.append({
                "id": None,
                "name": m_name,
                "email": "",
                "phone": "",
                "department": "Faculty",
                "expertise": ["Mentoring"],
                "skills": [],
                "domains": [],
                "availability": "Contact via email"
            })
            continue

        domain_raw = mentor_row.get("domain") or ""
        domains = [d.strip() for d in domain_raw.split(",") if d.strip()] or [domain_raw]
        skills_raw = mentor_row.get("skills") or domain_raw or ""
        skills = [s.strip() for s in skills_raw.split(",") if s.strip()] if isinstance(skills_raw, str) else (skills_raw or [])
        expertise_raw = mentor_row.get("expertise") or domain_raw or ""
        expertise = [e.strip() for e in expertise_raw.split(",") if e.strip()] if isinstance(expertise_raw, str) else (expertise_raw or [])

        serialized_mentors.append({
            "id": mentor_row.get("id"),
            "name": mentor_row.get("name"),
            "email": mentor_row.get("email"),
            "phone": mentor_row.get("phone") or "",
            "department": mentor_row.get("department") or "Faculty",
            "expertise": expertise,
            "skills": skills,
            "domains": domains,
            "availability": mentor_row.get("availability") or "Contact via email"
        })

    return ok(data=serialized_mentors)


# ---------------------------------------------------------------------------
# Task 2.8: Announcements & Deadlines Endpoints
# ---------------------------------------------------------------------------
@router.get("/announcements")
async def get_student_announcements(
    student: Student = Depends(get_current_student)
):
    """Return active announcements ordered by created_at desc (via Supabase REST
    over HTTPS, so it works on networks that block the direct Postgres port)."""
    from app.core.supabase_client import supabase_client
    rows = await supabase_client._request("announcements?is_active=eq.true&order=created_at.desc")

    data = []
    for a in (rows or []):
        data.append({
            "id": str(a.get("id")),
            "title": a.get("title"),
            "body": a.get("body"),
            "type": a.get("type"),
            "created_at": a.get("created_at"),  # REST already returns an ISO string
        })
    return ok(data=data)


@router.get("/deadlines")
async def get_student_deadlines(
    student: Student = Depends(get_current_student)
):
    """Return all active deadlines for the student's semester (via Supabase REST
    over HTTPS, so it works on networks that block the direct Postgres port)."""
    import logging
    logger = logging.getLogger(__name__)

    # Load from Supabase REST. A null semester (unassigned) uses IS NULL, mirroring
    # the old `Deadline.semester_id == None` behaviour.
    from app.core.supabase_client import supabase_client
    sid = student.semester_id
    sem_filter = f"semester_id=eq.{urllib.parse.quote(str(sid))}" if sid else "semester_id=is.null"

    CANONICAL_TYPE_MAP = {
        "team": "teamFormation",
        "team_formation": "teamFormation",
        "teamFormation": "teamFormation",
        "proposal": "proposalUpload",
        "proposal_submission": "proposalUpload",
        "proposal_upload": "proposalUpload",
        "proposalUpload": "proposalUpload",
        "evaluation": "midTerm",
        "mid_term": "midTerm",
        "midterm": "midTerm",
        "midTerm": "midTerm",
        "final": "finalEvaluation",
        "final_evaluation": "finalEvaluation",
        "finalEvaluation": "finalEvaluation",
        "github": "githubRepoSubmission",
        "github_submission": "githubRepoSubmission",
        "github_repo_submission": "githubRepoSubmission",
        "githubRepoSubmission": "githubRepoSubmission",
        "problem_statement_selection": "problemStatementSelection",
        "problemStatementSelection": "problemStatementSelection",
        "extra_activities": "extraActivities",
        "extraActivities": "extraActivities",
    }

    # Query published deadlines from DB only
    db_deadlines = {}

    try:
        rows = await supabase_client._request(f"deadlines?{sem_filter}")
        if not rows and sid:
            rows = await supabase_client._request("deadlines?semester_id=is.null")
        if not rows:
            rows = await supabase_client._request("deadlines?select=*")

        for d in (rows or []):
            raw_type = d.get("type") or d.get("name") or d.get("key") or d.get("title")
            if raw_type:
                canon_type = CANONICAL_TYPE_MAP.get(str(raw_type).strip(), str(raw_type).strip())
                due_val = d.get("due_date") or d.get("deadline_date") or d.get("date")
                if due_val:
                    # Include only admin published deadlines from DB. start_date
                    # is carried through so the window below can hide a deadline
                    # once it has closed.
                    db_deadlines[canon_type] = (due_val, d.get("start_date"))
    except Exception as e:
        logger.error(f"Failed to query published deadlines via REST: {e}")

    # Which problem statement (if any) this student's team has reserved. The
    # "Problem Statement Selection" deadline is only shown to teams that have
    # actually selected one -- everyone else has nothing to be reminded about.
    ps_selected = None
    try:
        membership = getattr(student, "team_membership", None)
        raw_team_id = getattr(membership, "team_id", None) if membership else None
        if raw_team_id:
            from app.core.supabase_client import extract_numeric_id
            raw_team_id_str = str(raw_team_id)
            num_id = extract_numeric_id(raw_team_id_str)
            for variant in list(dict.fromkeys(filter(None, [
                raw_team_id_str, f"TEAM-{num_id}" if num_id else None
            ]))):
                res = await supabase_client._request(
                    f"teams_validation?id=eq.{variant}&select=problem_statement_id&limit=1"
                )
                if res:
                    ps_selected = (res[0] or {}).get("problem_statement_id")
                    break
    except Exception as exc:
        # Fail open: if we cannot tell, keep the old behaviour and show it.
        logger.warning("Could not resolve PS selection for deadline filtering: %s", exc)
        ps_selected = None

    data = []
    for type_key, due_entry in db_deadlines.items():
        due_raw, start_raw = due_entry if isinstance(due_entry, tuple) else (due_entry, None)
        if not due_raw:
            continue

        # Only students whose team has reserved a problem statement should see
        # the Problem Statement Selection reminder.
        if type_key == "problemStatementSelection" and not ps_selected:
            continue

        try:
            due_str = str(due_raw)
            for suffix in ('Z', '+00:00', '+0000'):
                if due_str.endswith(suffix):
                    due_str = due_str[:-len(suffix)]
                    break
            if '+' in due_str:
                due_str = due_str.split('+')[0]
            
            ist_tz = timezone(timedelta(hours=5, minutes=30))
            due_date = datetime.fromisoformat(due_str).replace(tzinfo=ist_tz)
            
            # If time component is midnight 00:00 or default UTC conversion 05:30, 
            # extend to 23:59:59 IST of that target date so it remains active throughout the day
            if due_date.hour in (0, 5) and due_date.minute in (0, 30):
                due_date = due_date.replace(hour=23, minute=59, second=59)
        except Exception as exc:
            # Log it. A bare `continue` here hid a NameError (timedelta was not
            # imported at module scope) that skipped EVERY row, so this endpoint
            # returned {"data": []} with success=true and the portal showed
            # "No active deadline" while the deadline existed in the database.
            logger.warning("Skipping deadline %r — could not parse %r: %s", type_key, due_raw, exc)
            continue

        ist_tz = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist_tz)

        # A deadline is only shown for the duration it is actually open. Once
        # due_date passes it stops being returned, so its alert disappears
        # instead of sitting in the window as "Past Due" indefinitely -- the
        # Problem Statement Selection deadline was still showing nine days on.
        if now > due_date:
            continue

        # Likewise, a deadline that has not opened yet is not something the
        # student can act on, so it is not surfaced either.
        if start_raw:
            try:
                start_str = str(start_raw)
                for suffix in ('Z', '+00:00', '+0000'):
                    if start_str.endswith(suffix):
                        start_str = start_str[:-len(suffix)]
                        break
                if '+' in start_str:
                    start_str = start_str.split('+')[0]
                start_date = datetime.fromisoformat(start_str).replace(tzinfo=ist_tz)
                if now < start_date:
                    continue
            except Exception as exc:
                # An unparseable start_date must not hide an open deadline.
                logger.warning("Ignoring start_date %r for %r: %s", start_raw, type_key, exc)

        delta = due_date - now
        days_remaining = max(0, delta.days)

        data.append({
            "id": f"deadline-{type_key}",
            "name": type_key,
            "deadline_date": due_date.isoformat(),
            "days_remaining": days_remaining,
            # Retained for API compatibility; always False now that closed
            # deadlines are filtered out above.
            "is_past": False
        })

    return ok(data=data)


# ---------------------------------------------------------------------------
# Task 5.6-B: Milestones Table & API
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Procksi Chat
#
# A student has four standing threads, all scoped to THEIR OWN team:
#   coordinator  admin  <-> team
#   mentor       assigned mentor <-> team
#   panel        assigned evaluation panel <-> team
#   team         the team's own group chat
# plus read-only broadcasts, which carry no team and reach every portal.
#
# Threads are created lazily on the first message, so a student who never writes
# leaves no rows behind. Every read and write re-derives the team from the
# session; a conversation_id from the client is never trusted.
# ---------------------------------------------------------------------------

STUDENT_THREAD_KINDS = ("coordinator", "mentor", "panel", "team")


async def _student_team_id(student) -> Optional[str]:
    """
    Resolve the student's team as the ADMIN portal identifies it.

    The two portals keep teams in different tables with unrelated id schemes:
    the student side uses `teams`/`team_members` with integer ids (57, 61, ...),
    while the admin side — and therefore `conversations.team_id` — uses
    `teams_validation` with string ids like `<semester>-T34`. The T-suffix is
    neither the integer id nor the team number, so no id arithmetic bridges them.

    The student's roll number is the only stable link: it appears inside each
    teams_validation row's `members` JSON array.
    """
    from app.core.supabase_client import supabase_client

    # The roll number lives in students.id; the students.student_id column is
    # NULL for every row in this database, so it cannot be relied on.
    roll = str(getattr(student, "id", "") or getattr(student, "student_id", "") or "").strip()
    if not roll:
        logging.getLogger(__name__).warning(
            f"Procksi Chat: no roll on session object; attrs={sorted(vars(student).keys()) if hasattr(student, '__dict__') else type(student).__name__}"
        )
        return None

    # Match on roll first. Some rows were imported with the roll under a
    # different key, or with only the student's name, so fall back to those
    # rather than reporting "not on a team" for a student who plainly is.
    name = str(getattr(student, "name", "") or "").strip()
    attempts = [json.dumps([{"roll": roll}]), json.dumps([{"id": roll}])]
    if name:
        attempts.append(json.dumps([{"name": name}]))

    rows = []
    for needle in attempts:
        try:
            rows = await supabase_client._request(
                f"teams_validation?select=id&members=cs.{urllib.parse.quote(needle, safe='')}&limit=1"
            ) or []
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Team lookup failed for {needle}: {exc}")
            continue
        if rows:
            break
    resolved = str(rows[0]["id"]) if rows else None
    if resolved is None:
        # A student with no matching team is worth surfacing; a successful
        # resolution runs on every chat request and would only be noise.
        logging.getLogger(__name__).warning(
            f"Procksi Chat: no team matched roll={roll!r} email={getattr(student, 'email', None)!r}"
        )
    return resolved


def _student_sender_id(student) -> str:
    return str(getattr(student, "email", None) or getattr(student, "id", "") or "").strip()


def _is_unread_for(message: dict, viewer_needle: str) -> bool:
    """A message counts as unread when somebody else wrote it and the viewer is
    not yet in its read_by. Comparison is case-insensitive because the portals
    sign with whatever casing the login supplied."""
    if not viewer_needle:
        return False
    if str(message.get("sender_id") or "").strip().lower() == viewer_needle:
        return False
    readers = message.get("read_by") if isinstance(message.get("read_by"), list) else []
    return not any(str(r or "").strip().lower() == viewer_needle for r in readers)


async def _mark_messages_read(rows: list, viewer_id: str) -> None:
    """
    Record that the viewer has now seen these messages, mutating `rows` so the
    response reflects it.

    Opening a thread is what "read" means here, so this runs on the read path
    and needs no separate call from the client. Messages the viewer wrote, or
    has already read, are skipped — so the 5s poll writes nothing once it has
    caught up.
    """
    from app.core.supabase_client import supabase_client

    viewer = str(viewer_id or "").strip()
    if not viewer:
        return
    needle = viewer.lower()

    for m in rows:
        if not _is_unread_for(m, needle):
            continue
        readers = m.get("read_by") if isinstance(m.get("read_by"), list) else []
        updated = list(readers) + [viewer]
        try:
            await supabase_client._request(
                f"conversation_messages?id=eq.{int(m['id'])}",
                method="PATCH", body={"read_by": updated},
            )
            m["read_by"] = updated
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Procksi Chat could not mark message read: {exc}")


async def _student_sender_names(messages: list) -> dict:
    """
    Map each student sender's login id to their real name.

    Students sign messages with their email address, so a thread otherwise reads
    as a wall of "student". Only student senders are looked up; staff are shown
    by role, and their personal addresses are not exposed to students.
    """
    from app.core.supabase_client import supabase_client

    ids = {
        str(m.get("sender_id") or "").strip()
        for m in messages if m.get("sender_role") == "student"
    }
    ids.discard("")
    if not ids:
        return {}

    names: dict = {}
    quoted = ",".join(f'"{i}"' for i in ids)
    for column in ("email", "id"):
        try:
            rows = await supabase_client._request(
                f"students?{column}=in.({urllib.parse.quote(quoted, safe='')})&select=id,name,email"
            ) or []
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Procksi Chat sender name lookup failed: {exc}")
            continue
        for r in rows:
            name = str(r.get("name") or "").strip()
            if not name:
                continue
            for key in (r.get("email"), r.get("id")):
                key = str(key or "").strip().lower()
                if key:
                    names[key] = name
    return names


def is_team_leader(my_ids, team_d) -> bool:
    """
    Whether the caller leads this team.

    `teams_validation.leader` stores a display NAME, not an id, so the match
    walks several identifiers and falls back to the members array — an entry
    flagged isLeader/role=LEADER, or failing that the first member, which is
    the convention older rows were written with.

    Extracted from the problem-statement reservation endpoint so that "leader"
    means exactly one thing across the portal: a student who may reserve a
    problem statement is the same student who may post in All Teams.
    """
    if not team_d:
        return False
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


async def _team_row(team_id: str) -> dict:
    from app.core.supabase_client import supabase_client
    rows = await supabase_client._request(
        f"teams_validation?id=eq.{team_id}&select=id,team_number,title,mentor,semester_id&limit=1"
    ) or []
    return rows[0] if rows else {}


# The standing groups a role belongs to. Membership is derived here rather than
# stored, so a student added to a team next week is in "All Teams" without
# anyone editing a list — and a person who holds two roles matches each group
# through the role that qualifies them, never twice.
GROUP_KEYS_FOR_ROLE = {
    "student": ("teams", "everyone"),
    "mentor": ("mentors", "everyone"),
    "panel": ("panels", "everyone"),
}


# Groups a student may read but not write to unless they lead their team.
# "All Teams" reaches every student in the programme, so it is addressed by a
# team rather than by its individual members: one voice per team, and that
# voice is the leader's.
LEADER_ONLY_GROUP_KEYS = ("teams",)

# "Everyone" reaches every student, mentor and panel at once. That is an
# announcement, not a conversation — a reply there would go to the whole
# programme — so it is listed with the announcements and only the coordinator
# writes to it.
ANNOUNCEMENT_GROUP_KEYS = ("everyone",)


async def _student_is_team_leader(student) -> bool:
    """Whether this student leads their own team."""
    from app.core.supabase_client import supabase_client

    try:
        team = await supabase_client.get_team_by_student_id(
            str(student.id), getattr(student, "semester_id", None)
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Procksi Chat leader lookup failed: {exc}")
        return False

    if team:
        return is_team_leader([
            str(student.id),
            str(getattr(student, "student_id", "") or ""),
            str(getattr(student, "name", "") or "").strip(),
            str(getattr(student, "email", "") or "").strip(),
        ], team)

    membership = getattr(student, "team_membership", None)
    return str(getattr(membership, "role", "MEMBER") or "MEMBER").upper() == "LEADER"


async def _student_groups(student) -> tuple:
    """
    The standing group threads a student belongs to, split into
    (announcement_groups, groups).

    "Everyone" comes back in the first list: it reaches the whole programme, so
    it belongs with the announcements rather than among the group chats.

    Each row carries `can_post`, so the client can present a thread as
    read-only rather than letting someone type a message the server will
    refuse. The server refuses it regardless — this flag is presentation.
    """
    from app.core.supabase_client import supabase_client

    keys = GROUP_KEYS_FOR_ROLE["student"]
    try:
        rows = await supabase_client._request(
            f"conversations?group_key=in.({','.join(keys)})&select=*&order=updated_at.desc"
        ) or []
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Procksi Chat groups unavailable: {exc}")
        return [], []

    # Only looked up when a leader-gated group is actually present, so the
    # common conversation-list request does not pay for a team query.
    leader = None
    announcements, groups = [], []
    for row in rows:
        key = row.get("group_key")
        if key in ANNOUNCEMENT_GROUP_KEYS:
            row["can_post"] = False
            announcements.append(row)
            continue
        if key not in LEADER_ONLY_GROUP_KEYS:
            row["can_post"] = True
            groups.append(row)
            continue
        if leader is None:
            leader = await _student_is_team_leader(student)
        row["can_post"] = leader
        groups.append(row)
    return announcements, groups


async def _student_threads(student) -> tuple:
    """(threads, broadcasts, groups) visible to this student."""
    from app.core.supabase_client import supabase_client

    team_id = await _student_team_id(student)
    broadcasts = await supabase_client._request(
        "conversations?recipient_type=is.null&kind=is.null&select=*&order=updated_at.desc"
    ) or []
    announcement_groups, groups = await _student_groups(student)
    # "Everyone" is an announcement in every sense that matters here: read-only,
    # programme-wide, written by the coordinator.
    broadcasts = [*announcement_groups, *broadcasts]

    if not team_id:
        return [], broadcasts, groups

    existing = await supabase_client._request(
        f"conversations?team_id=eq.{team_id}&select=*"
    ) or []
    by_kind = {c.get("kind"): c for c in existing}

    team = await _team_row(team_id)
    mentor_name = (team.get("mentor") or "").strip() or None

    labels = {
        "coordinator": ("Project Coordinator", True, None),
        "mentor": ("Mentor", bool(mentor_name),
                   None if mentor_name else "No mentor assigned yet."),
        "panel": ("Evaluation Panel", False, "No panel assigned yet."),
        "team": ("My Team", True, None),
    }

    threads = []
    for kind in STUDENT_THREAD_KINDS:
        row = by_kind.get(kind)
        label, available, note = labels[kind]
        threads.append({
            "id": row.get("id") if row else None,
            "kind": kind,
            "subject": label,
            "available": available,
            "note": note,
            "updated_at": row.get("updated_at") if row else None,
        })
    return threads, broadcasts, groups


@router.get("/chat/conversations")
async def get_student_chat_conversations(student: Student = Depends(get_current_student)):
    try:
        threads, broadcasts, groups = await _student_threads(student)
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Procksi Chat conversations unavailable: {exc}")
        return ok(data={"threads": [], "broadcasts": [], "groups": []})

    return ok(data={
        "threads": threads,
        "broadcasts": [{
            "id": b.get("id"),
            "subject": b.get("subject"),
            # Set only on "Everyone", which is an announcement that happens to
            # be a standing group; the client labels it accordingly.
            "group_key": b.get("group_key"),
            "updated_at": b.get("updated_at"),
        } for b in broadcasts],
        "groups": [{
            "id": g.get("id"),
            "subject": g.get("subject"),
            "group_key": g.get("group_key"),
            "can_post": g.get("can_post", True),
            "updated_at": g.get("updated_at"),
        } for g in groups],
    })


@router.get("/chat/unread")
async def get_student_chat_unread(student: Student = Depends(get_current_student)):
    """
    Unread totals for the sidebar badge.

    Deliberately separate from /chat/conversations: the badge is polled from the
    layout on every page, so it must not drag the thread list, team lookup and
    roster along with it.
    """
    from app.core.supabase_client import supabase_client

    empty = {"unread": 0, "by_conversation": {}}
    try:
        threads, broadcasts, groups = await _student_threads(student)
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Procksi Chat unread unavailable: {exc}")
        return ok(data=empty)

    ids = [t["id"] for t in threads if t.get("id") is not None]
    ids += [b["id"] for b in broadcasts if b.get("id") is not None]
    ids += [g["id"] for g in groups if g.get("id") is not None]
    if not ids:
        return ok(data=empty)

    needle = _student_sender_id(student).strip().lower()
    joined = ",".join(str(int(i)) for i in ids)
    try:
        rows = await supabase_client._request(
            f"conversation_messages?conversation_id=in.({joined})&select=conversation_id,sender_id,read_by"
        ) or []
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Procksi Chat unread query failed: {exc}")
        return ok(data=empty)

    by_conversation: dict = {}
    for m in rows:
        if not _is_unread_for(m, needle):
            continue
        key = str(m.get("conversation_id"))
        by_conversation[key] = by_conversation.get(key, 0) + 1

    return ok(data={"unread": sum(by_conversation.values()), "by_conversation": by_conversation})


async def _assert_student_may_post(student, conversation_id: int) -> None:
    """
    Reading a group is not permission to write in it.

    All Teams reaches every student in the programme, so it is addressed by
    team rather than by person: only the team leader speaks for their team
    there. This runs on the write path, not the read path, so a member still
    sees everything.
    """
    from app.core.supabase_client import supabase_client

    try:
        rows = await supabase_client._request(
            f"conversations?id=eq.{int(conversation_id)}&select=group_key&limit=1"
        ) or []
    except Exception as exc:
        # A lookup failure must not silently open the gate.
        logging.getLogger(__name__).warning(f"Procksi Chat post check failed: {exc}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Could not verify this conversation. Please retry.")

    group_key = (rows[0].get("group_key") if rows else None)

    if group_key in ANNOUNCEMENT_GROUP_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Everyone is an announcement channel. Only the coordinator can post there.",
        )

    if group_key not in LEADER_ONLY_GROUP_KEYS:
        return

    if not await _student_is_team_leader(student):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only your team leader can post in All Teams. You can still read it.",
        )


async def _assert_student_may_access(student, conversation_id: int) -> None:
    threads, broadcasts, groups = await _student_threads(student)
    allowed = {int(t["id"]) for t in threads if t.get("id") is not None}
    allowed |= {int(b["id"]) for b in broadcasts if b.get("id") is not None}
    allowed |= {int(g["id"]) for g in groups if g.get("id") is not None}
    if int(conversation_id) not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="This conversation is not available to you.")


@router.get("/chat/messages")
async def get_student_chat_messages(
    conversation_id: int,
    student: Student = Depends(get_current_student),
):
    from app.core.supabase_client import supabase_client
    await _assert_student_may_access(student, conversation_id)

    rows = await supabase_client._request(
        f"conversation_messages?conversation_id=eq.{int(conversation_id)}&order=created_at.asc"
    ) or []
    await _mark_messages_read(rows, _student_sender_id(student))
    names = await _student_sender_names(rows)
    return ok(data=[{
        "id": m.get("id"),
        "conversation_id": m.get("conversation_id"),
        "sender_role": m.get("sender_role"),
        "sender_id": m.get("sender_id"),
        # Drives the delivery ticks: a reader other than the sender means read.
        "read_by": m.get("read_by") or [],
        # In a team thread the role alone does not say who is speaking, and the
        # address a student signs with is not their name.
        "sender_name": names.get(str(m.get("sender_id") or "").strip().lower()),
        "body": m.get("body"),
        # ProcksiBot's reports carry their structured payload here. Nothing else
        # writes it, so it is null for every message a person typed.
        "metadata": m.get("metadata"),
        "created_at": m.get("created_at"),
    } for m in rows])


class StudentChatMessagePayload(BaseModel):
    body: str
    conversation_id: Optional[int] = None
    kind: Optional[str] = None


@router.post("/chat/messages")
async def post_student_chat_message(
    payload: StudentChatMessagePayload,
    student: Student = Depends(get_current_student),
):
    """Send into an existing thread, or open one of this team's four threads."""
    from app.core.supabase_client import supabase_client

    body = (payload.body or "").strip()
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message body is required.")

    conversation_id = payload.conversation_id

    if conversation_id is None:
        # Opening a thread for the first time. Only the four kinds are creatable,
        # and only ever against the student's own team.
        kind = (payload.kind or "").strip()
        if kind not in STUDENT_THREAD_KINDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown conversation kind.")

        team_id = await _student_team_id(student)
        if not team_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are not on a team yet.")

        threads, _, _ = await _student_threads(student)
        target = next((t for t in threads if t["kind"] == kind), None)
        if target is None or not target["available"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=target["note"] if target else "Conversation unavailable.")

        team = await _team_row(team_id)
        label = target["subject"]
        created = await supabase_client._request(
            "conversations",
            method="POST",
            body={
                "channel": "panel_team" if kind == "panel" else "mentor_student",
                "subject": f"{label} - Team {team.get('team_number') or ''}".strip(),
                "created_by": _student_sender_id(student),
                "status": "open",
                "kind": kind,
                "team_id": team_id,
                # The admin portal lists conversations filtered by the semester
                # it currently has selected. A row created here without a
                # semester is invisible to the coordinator, who then tries to
                # open the same thread and collides with the unique index on
                # (team_id, kind).
                "semester_id": team.get("semester_id"),
                # recipient_type/recipient_id are deliberately NOT set. They mean
                # "a thread the coordinator addressed to this recipient", and
                # stamping them on a mentor or team-group thread would make the
                # admin match it as its own and send coordinator messages into
                # the wrong conversation. (team_id, kind) is the shared identity.
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            headers={"Prefer": "return=representation"},
        )
        row = (created or [{}])[0] if isinstance(created, list) else (created or {})
        conversation_id = row.get("id")
        if not conversation_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Conversation was created but could not be read back.")
    else:
        await _assert_student_may_access(student, conversation_id)
        await _assert_student_may_post(student, conversation_id)

    sender_id = _student_sender_id(student)
    await supabase_client._request(
        "conversation_messages",
        method="POST",
        body={
            "conversation_id": int(conversation_id),
            "sender_role": "student",
            "sender_id": sender_id,
            "body": body,
            "read_by": [sender_id],
        },
    )
    try:
        await supabase_client._request(
            f"conversations?id=eq.{int(conversation_id)}",
            method="PATCH",
            body={"updated_at": datetime.now(timezone.utc).isoformat()},
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Could not bump conversation timestamp: {exc}")

    return ok(data={"sent": True, "conversation_id": int(conversation_id)})


@router.get("/milestones")
async def get_student_milestones(
    student: Student = Depends(get_current_student)
):
    """Return all milestones for the student's team ordered by deadline asc."""
    team_id = student.team_membership.team_id if (student.team_membership and student.team_membership.team) else None
    if not team_id:
        return ok(data=[])
        
    from app.core.supabase_client import supabase_client, extract_numeric_id
    team_int_id = extract_numeric_id(team_id) if team_id else None
    
    # Fetch milestones from Supabase
    if team_int_id is None:
        return ok(data=[])
        
    milestones = await supabase_client._request(f"milestones?team_id=eq.{team_int_id}&order=deadline.asc")
    
    data = []
    for m in (milestones or []):
        data.append({
            "id": str(m.get("id")),
            "title": m.get("title"),
            "description": m.get("description"),
            "deadline": m.get("deadline"),
            "status": m.get("status"),
            "github_url": m.get("github_url"),
            "file_url": m.get("file_url"),
            "form_schema": m.get("form_schema"),
            "submission_data": m.get("submission_data"),
            "created_at": m.get("created_at")
        })
    return ok(data=data)


@router.patch("/milestones/{milestone_id}")
async def update_student_milestone(
    milestone_id: str,
    payload: MilestoneUpdatePayload,
    student: Student = Depends(get_current_student)
):
    """Allows student to update github_url, file_url and submission_data for their milestones."""
    team_id = student.team_membership.team_id if (student.team_membership and student.team_membership.team) else None
    if not team_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student is not assigned to a team"
        )

    from app.core.supabase_client import supabase_client, extract_numeric_id
    team_int_id = extract_numeric_id(team_id) if team_id else None
    
    # Fetch milestone from Supabase
    milestones = await supabase_client._request(f"milestones?id=eq.{milestone_id}&limit=1")
    if not milestones or len(milestones) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Milestone not found"
        )
        
    milestone = milestones[0]
    
    if milestone.get("team_id") != team_int_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This milestone belongs to another team."
        )
        
    if milestone.get("status") == "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Milestone is already approved and cannot be updated."
        )

    # Sync github and file type fields from submission_data to top level columns if form_schema exists
    form_schema = milestone.get("form_schema")
    if isinstance(form_schema, str):
        try:
            form_schema = json.loads(form_schema)
        except Exception:
            form_schema = None

    if isinstance(form_schema, list) and payload.submission_data:
        for field in form_schema:
            field_id = field.get("id")
            field_type = field.get("type")
            if field_id and field_type == "github":
                payload.github_url = payload.submission_data.get(field_id)
            elif field_id and field_type == "file":
                payload.file_url = payload.submission_data.get(field_id)

    # Prepare update data
    update_data = {}
    if payload.github_url is not None:
        update_data["github_url"] = _require_web_url(payload.github_url, "Repository link")
    if payload.file_url is not None:
        update_data["file_url"] = _require_web_url(payload.file_url, "File link")
    if payload.submission_data is not None:
        update_data["submission_data"] = payload.submission_data
        
    # Update status
    has_submission = (update_data.get("github_url") is not None and update_data.get("github_url") != "") or \
                     (update_data.get("file_url") is not None and update_data.get("file_url") != "") or \
                     (update_data.get("submission_data") is not None and len(update_data.get("submission_data")) > 0) or \
                     (milestone.get("github_url") is not None and milestone.get("github_url") != "") or \
                     (milestone.get("file_url") is not None and milestone.get("file_url") != "") or \
                     (milestone.get("submission_data") is not None and len(milestone.get("submission_data")) > 0)
                     
    if has_submission:
        update_data["status"] = "submitted"
    else:
        update_data["status"] = "not_started"
        
    # Update in Supabase
    await supabase_client._request(
        f"milestones?id=eq.{milestone_id}",
        method="PATCH",
        body=update_data
    )
    
    # Fetch updated milestone
    updated_milestones = await supabase_client._request(f"milestones?id=eq.{milestone_id}&limit=1")
    updated_milestone = updated_milestones[0]
    
    data = {
        "id": str(updated_milestone.get("id")),
        "title": updated_milestone.get("title"),
        "description": updated_milestone.get("description"),
        "deadline": updated_milestone.get("deadline"),
        "status": updated_milestone.get("status"),
        "github_url": updated_milestone.get("github_url"),
        "file_url": updated_milestone.get("file_url"),
        "form_schema": updated_milestone.get("form_schema"),
        "submission_data": updated_milestone.get("submission_data"),
        "created_at": updated_milestone.get("created_at")
    }
    return ok(data=data)


# ---------------------------------------------------------------------------
# Preserved Original Student Portal Endpoints (For Backwards Compatibility)
# ---------------------------------------------------------------------------
PS_TEAM_CAPACITY = 2


def is_ps_reservation_allowed(
    team_count: int,
    current_team_title: str | None,
    ps_title: str,
    capacity: int = PS_TEAM_CAPACITY,
) -> bool:
    if current_team_title and current_team_title.strip().lower() == ps_title.strip().lower():
        return True
    return team_count < capacity


async def reserve_ps_atomically(supabase_client, team_id: str, ps_id: str) -> dict:
    rows = await supabase_client._request(
        "rpc/reserve_problem_statement_atomic",
        method="POST",
        body={
            "p_team_id": str(team_id),
            "p_problem_statement_id": str(ps_id),
            "p_capacity": PS_TEAM_CAPACITY,
        },
    )
    return (rows or [{}])[0]

def is_placeholder_title(title: str | None, team_name: str | None = None) -> bool:
    if not title:
        return True
    clean = title.strip().lower()
    if not clean or clean == "custom team" or clean.startswith("pending") or clean.startswith("admin-team"):
        return True
    if team_name and clean == team_name.strip().lower():
        return True
    if re.match(r"^team\s*-?\s*\d+$", clean, re.IGNORECASE):
        return True
    if re.match(r"^\d{4}(?:-\d{4})?[-_\s]+\d+$", clean, re.IGNORECASE):
        return True
    return False

async def get_project_title_counts() -> dict:
    from app.core.supabase_client import supabase_client
    title_holders: dict[str, set[str]] = {}
    team_holders_by_id: dict[str, str] = {}
    team_holders_by_uid: dict[str, str] = {}

    def add_holder(title, holder_key):
        if title and not is_placeholder_title(title):
            key = title.strip().lower()
            title_holders.setdefault(key, set()).add(holder_key)

    # teams_validation is authoritative when the same team also has an approved proposal.
    try:
        teams = await supabase_client._request("teams_validation?select=id,uid,title")
        for t in (teams or []):
            team_id = str(t.get("id") or "").strip()
            team_uid = str(t.get("uid") or "").strip()
            holder_key = f"uid:{team_uid}" if team_uid else f"id:{team_id}"
            if not team_id and not team_uid:
                continue
            if team_id:
                team_holders_by_id[team_id] = holder_key
            if team_uid:
                team_holders_by_uid[team_uid] = holder_key
            add_holder(t.get("title"), holder_key)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to fetch allocated titles from teams_validation: {e}")
        raise RuntimeError("Unable to verify problem-statement capacity") from e

    # Approved proposals are a fallback for teams missing from teams_validation.
    try:
        proposals = await supabase_client._request(
            "proposals?status=eq.Approved&select=id,teamId,team_uid,title"
        )
        for p in (proposals or []):
            team_uid = str(p.get("team_uid") or "").strip()
            team_id = str(p.get("teamId") or "").strip()
            if (team_uid and team_uid in team_holders_by_uid) or (
                team_id and team_id in team_holders_by_id
            ):
                continue
            proposal_id = str(p.get("id") or "").strip()
            holder_key = (
                f"uid:{team_uid}" if team_uid
                else f"id:{team_id}" if team_id
                else f"proposal:{proposal_id}"
            )
            if proposal_id or team_id or team_uid:
                add_holder(p.get("title"), holder_key)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to fetch allocated titles from proposals: {e}")
        raise RuntimeError("Unable to verify problem-statement capacity") from e

    return {title: len(holders) for title, holders in title_holders.items()}


@router.get("/problem-statements")
async def get_problem_statements(
    student: Student = Depends(get_current_student)
):
    from app.core.supabase_client import supabase_client
    statements = await supabase_client.get_problem_statements()
    
    # Filter problem statements by the student's year (3rd year / 4th year)
    # Statements with a null/None year are treated as common and visible to all.
    student_year = student.year
    if student_year:
        try:
            student_year_num = int(student_year)
            statements = [s for s in (statements or []) if s.get("year") is None or s.get("year") == student_year_num]
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Error filtering problem statements by year: {e}")

    title_counts = await get_project_title_counts()
    current_team = getattr(getattr(student, "team_membership", None), "team", None)
    current_team_title = str(getattr(current_team, "project_title", None) or "").strip().lower()
    # Do not filter out already booked/allocated problem statements;
    # instead, flag them with a `team_count` and an `is_allocated` boolean
    # meaning "at capacity" (PS_TEAM_CAPACITY teams already hold it).
    for s in (statements or []):
        title = s.get("title")
        count = title_counts.get(title.strip().lower(), 0) if title else 0
        s["team_count"] = count
        s["is_allocated"] = count >= PS_TEAM_CAPACITY
        s["is_held_by_current_team"] = bool(title and current_team_title == title.strip().lower())
        
    # AI-Based Domain Classification for unclassified statements
    unclassified_ps = []
    for s in (statements or []):
        dom = s.get("domain")
        # Identify missing or generic domains
        if not dom or str(dom).strip() == "" or str(dom).strip().lower() in ["general", "all", "unspecified"]:
            unclassified_ps.append(s)

    if unclassified_ps:
        import os
        import json
        import asyncio
        import logging
        from app.core.supabase_client import supabase_client
        api_key = os.getenv("OPENAI_API_KEY")
        
        if api_key:
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=api_key)
                
                # Batch processing
                batch_payload = [{"id": ps["id"], "title": ps.get("title", ""), "description": str(ps.get("description", ""))[:300]} for ps in unclassified_ps]
                
                prompt = (
                    "You are a technical domain classifier. I will provide a JSON array of problem statements. "
                    "For each problem statement, identify exactly ONE best technical domain from this list (or a similar valid technical domain): "
                    "Artificial Intelligence, Machine Learning, Data Science, Web Development, Mobile Development, "
                    "Cyber Security, Blockchain, Cloud Computing, Internet of Things (IoT), Embedded Systems, Robotics, "
                    "Computer Vision, NLP, Database Systems, Networking, DevOps, AR/VR, Healthcare Technology, FinTech, EdTech, Automation. "
                    "Return ONLY a JSON array of strings, where each string is the domain for the corresponding problem statement in the exact same order. "
                    "Do NOT include any explanations or other keys. Return ONLY the JSON array.\n\n"
                    f"Problem Statements: {json.dumps(batch_payload)}"
                )
                
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=800
                )
                
                content = response.choices[0].message.content.strip()
                if content.startswith("```json"): content = content[7:]
                if content.startswith("```"): content = content[3:]
                if content.endswith("```"): content = content[:-3]
                
                domains = json.loads(content.strip())
                
                if isinstance(domains, list) and len(domains) == len(unclassified_ps):
                    # Background task to patch DB so response is not blocked on saving
                    async def patch_db(updates):
                        for item in updates:
                            try:
                                await supabase_client._request(
                                    f"problem_statements?id=eq.{item['id']}",
                                    method="PATCH",
                                    body={"domain": item['domain']}
                                )
                            except Exception as e:
                                logging.getLogger(__name__).warning(f"Failed to patch domain for {item['id']}: {e}")
                    
                    db_updates = []
                    for i, ps in enumerate(unclassified_ps):
                        domain_str = str(domains[i]).strip()
                        ps["domain"] = domain_str  # Update API response immediately
                        db_updates.append({"id": ps["id"], "domain": domain_str})
                    
                    asyncio.create_task(patch_db(db_updates))
            except Exception as e:
                logging.getLogger(__name__).warning(f"Domain classification failed: {e}")

    return ok(data=statements)


class AISuggestionsRequest(BaseModel):
    id: int | str | None = None
    title: str
    description: str | None = ""
    domain: str | None = "General"
    difficulty: str | None = "Medium"


@router.post("/problem-statements/generate-ai-suggestions")
@limiter.limit("10/minute")
async def generate_ai_suggestions_student(
    request: Request,
    payload: AISuggestionsRequest,
    student: Student = Depends(get_current_student),
):
    import os
    import json
    import logging
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return ok(data={
            "title": payload.title,
            "description": payload.description or "",
            "domain": payload.domain or "General",
            "difficulty": payload.difficulty or "Medium"
        })
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        
        system_prompt = (
            "You are a Senior Software Architect. "
            "Given a raw project statement, refine and format it into a concise, crisp JSON object.\n"
            "Keep all explanations concise, direct, short, and to the point (no long essays or bloated text).\n"
            "The JSON output MUST have the following keys:\n"
            " - 'title': Concise, clear title (string)\n"
            " - 'domain': Accurate domain category\n"
            " - 'difficulty': 'Easy', 'Medium', or 'Hard'\n"
            " - 'main_description': Concise 2-3 sentence project overview\n"
            " - 'objective': 2-4 short bullet points covering core goals\n"
            " - 'tech_stack': Comma-separated or short bullet list of key technologies & datasets\n"
            " - 'deliverables': 2-3 short bullet points of deliverables\n"
            " - 'ai_suggestions': 2-3 short technical guidance tips\n\n"
            "Return ONLY valid JSON with no markdown tags or code blocks."
        )
        
        user_prompt = f"Raw Title: {payload.title}\nRaw Description: {payload.description}\nDomain: {payload.domain}\nDifficulty: {payload.difficulty}"
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=600
        )
        
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        data = json.loads(content)
        
        def format_field(val):
            if isinstance(val, list):
                return "\n".join([f"- {str(item).strip()}" for item in val if item])
            elif isinstance(val, str):
                val_str = val.strip()
                if val_str.startswith("[") and val_str.endswith("]"):
                    try:
                        parsed = json.loads(val_str)
                        if isinstance(parsed, list):
                            return "\n".join([f"- {str(item).strip()}" for item in parsed if item])
                    except Exception:
                        pass
                return val_str
            return str(val or "")

        full_desc_parts = [data.get("main_description", payload.description or payload.title)]
        if data.get("objective"):
            full_desc_parts.append(f"\n\n### Key Objectives & Core Modules\n{format_field(data['objective'])}")
        if data.get("tech_stack"):
            full_desc_parts.append(f"\n\n### Tech Stack & Input Datasets\n{format_field(data['tech_stack'])}")
        if data.get("deliverables"):
            full_desc_parts.append(f"\n\n### Expected Outcomes & Deliverables\n{format_field(data['deliverables'])}")
        if data.get("ai_suggestions"):
            full_desc_parts.append(f"\n\n### System Architecture & Technical Strategy\n{format_field(data['ai_suggestions'])}")
            
        full_desc = "".join(full_desc_parts)
            
        usage = getattr(response, "usage", None)
        prompt_tokens = usage.prompt_tokens if usage else 250
        completion_tokens = usage.completion_tokens if usage else 350
        total_tokens = usage.total_tokens if usage else (prompt_tokens + completion_tokens)

        cost_usd = round((prompt_tokens * 0.00000015) + (completion_tokens * 0.00000060), 6)
        cost_inr = round(cost_usd * 83.5, 4)

        cost_info = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
            "cost_inr": cost_inr,
            "model": "gpt-4o-mini"
        }

        enriched_res = {
            "title": data.get("title", payload.title),
            "description": full_desc,
            "domain": data.get("domain", payload.domain or "General"),
            "difficulty": data.get("difficulty", payload.difficulty or "Medium"),
            "raw_parsed": data,
            "cost_info": cost_info
        }

        if payload.title:
            try:
                from app.core.supabase_client import supabase_client
                clean_title = payload.title.strip()

                # Both writes below are scoped to rows the caller's own team
                # actually holds — never a broad ILIKE match against the shared
                # problem_statements catalog or another team's teams_validation
                # row (that used to let any authenticated student overwrite any
                # team's project data by sending a common title; audit finding
                # M-2 in full_security_audit.md).
                team_membership = getattr(student, "team_membership", None)
                team_uid_val = str(
                    getattr(team_membership, "team_uid", "")
                    or getattr(getattr(team_membership, "team", None), "uid", "")
                    or ""
                ).strip()
                current_team = getattr(team_membership, "team", None)
                current_team_title = str(getattr(current_team, "project_title", None) or "").strip().lower()

                # 1. Update problem_statements — only the exact row by id, and
                #    only if it's the PS the caller's own team currently holds.
                if payload.id is not None and current_team_title and current_team_title == clean_title.lower():
                    await supabase_client.client.table("problem_statements").update({
                        "description": enriched_res["description"],
                        "domain": enriched_res["domain"],
                        "difficulty": enriched_res["difficulty"]
                    }).eq("id", payload.id).execute()

                # 2. Update teams_validation — only the caller's own team row.
                if team_uid_val:
                    await supabase_client.client.table("teams_validation").update({
                        "description": enriched_res["description"]
                    }).eq("id", team_uid_val).execute()
            except Exception as db_err:
                print("Error updating enriched PS from student portal:", db_err)

        return ok(data=enriched_res)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Student OpenAI AI suggestion error: {e}")
        return ok(data={
            "title": payload.title,
            "description": payload.description or "",
            "domain": payload.domain or "General",
            "difficulty": payload.difficulty or "Medium"
        })



@router.get("/preferences")
async def get_preferences(
    student: Student = Depends(get_current_student)
):
    from app.core.supabase_client import supabase_client
    student_id_str = str(student.id)
    prefs_record = await supabase_client.get_student_preferences(student_id_str)
    if prefs_record:
        return ok(data=prefs_record.get("preferences", []))
    return ok(data=[])


@router.post("/preferences")
async def save_preferences(
    payload: List[Dict[str, Any]] = Body(...),
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    from app.services.governance_service import GovernanceService
    await GovernanceService.enforce_deadline(db, student.semester_id, "proposalUpload")

    if len(payload) != 1:
        raise HTTPException(status_code=400, detail="You must reserve exactly one problem statement.")
        
    pref = payload[0]
    title = pref.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="Invalid problem statement")

    if not student.team_membership or not student.team_membership.team:
        raise HTTPException(status_code=400, detail="Student is not assigned to a team.")

    from app.core.supabase_client import supabase_client
    sid = str(student.id)
    s_roll = str(getattr(student, 'student_id', sid))
    s_name = str(getattr(student, 'name', '')).strip()
    s_email = str(getattr(student, 'email', '')).strip()

    my_team_data = await supabase_client.get_team_by_student_id(sid, student.semester_id)
    
    caller_is_leader = is_team_leader([sid, s_roll, s_name, s_email], my_team_data) if my_team_data else (getattr(student.team_membership, "role", "MEMBER").upper() == "LEADER")

    if not caller_is_leader:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the team leader is authorized to reserve a problem statement for the team."
        )
        
    team_id = student.team_membership.team_id
    team_obj = student.team_membership.team
    
    t_title = team_obj.project_title
    if t_title and t_title.strip() and t_title.strip().lower() != "custom team" and not re.match(r"^team\s*-?\s*\d+$", t_title.strip(), re.IGNORECASE):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your team has already been allocated a project."
        )

    title_counts = await get_project_title_counts()
    team_count = title_counts.get(title.strip().lower(), 0)
    if not is_ps_reservation_allowed(team_count, t_title, title):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The project '{title}' has already been reserved by the maximum number of teams."
        )

    team_obj.project_title = title.strip()
    team_obj.description = pref.get("description", team_obj.description)
    from sqlalchemy.exc import IntegrityError
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"The project '{title}' was just reserved by another team. Please select a different one."
        )

    from app.core.supabase_client import supabase_client
    team_id_str = str(team_id)
    if team_id_str.isdigit():
        team_id_str = f"TEAM-{team_id}"
    await supabase_client.update_team_proposal_details(
        team_id=team_id_str,
        title=title.strip(),
        description=team_obj.description or "",
        domain=""
    )

    try:
        from app.services.email_service import notify_student_topic_reserved
        recip_emails = [m.student.email for m in team_obj.members if m.student and m.student.email] if team_obj.members else []
        if student.email and student.email not in recip_emails:
            recip_emails.append(student.email)
        notify_student_topic_reserved(recip_emails, str(team_id), title.strip(), pref.get("domain", "General"))
    except Exception:
        pass

    return ok(message="Problem Statement reserved successfully")


@router.get("/announcements")
async def get_student_announcements(
    student: Student = Depends(get_current_student)
):
    """Retrieve real active announcements from database for student's semester batch."""
    from app.core.supabase_client import supabase_client
    try:
        query = "announcements?order=created_at.desc&limit=20"
        if student.semester_id:
            query = f"announcements?semester_id=eq.{student.semester_id}&order=created_at.desc&limit=20"
        rows = await supabase_client._request(query)
        return ok(data=rows or [])
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to fetch announcements: {e}")
        return ok(data=[])


@router.get("/notifications")
async def get_student_notifications(
    student: Student = Depends(get_current_student)
):
    """Retrieve real active notifications from database for authenticated student."""
    from app.core.supabase_client import supabase_client
    student_email_str = str(student.email)
    # Only select the fields the frontend actually needs — never expose
    # recipient_email, recipient_role, audience, action_url, or metadata.
    _SAFE_NOTIF_FIELDS = {"id", "title", "message", "type", "read", "created_at"}
    try:
        rows = await supabase_client._request(
            f"notifications?recipient_email=eq.{student_email_str}&order=created_at.desc&limit=20"
        )
        safe_rows = [
            {k: v for k, v in row.items() if k in _SAFE_NOTIF_FIELDS}
            for row in (rows or [])
        ]
        return ok(data=safe_rows)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to fetch notifications for student: {e}")
        return ok(data=[])




@router.get("/extra-activities")
async def get_extra_activities(
    student: Student = Depends(get_current_student)
):
    # FIX (Bug 6): Retrieve from Supabase instead of local data_store.json
    from app.core.supabase_client import supabase_client
    student_id_str = str(student.id)
    try:
        # Only select columns that actually exist in the table
        rows = await supabase_client._request(
            f"extra_activities?student_id=eq.{urllib.parse.quote(student_id_str)}"
            f"&select=id,student_id,title,description,date,status,points,proof_url,created_at"
            f"&order=created_at.desc"
        )
        return ok(data=rows or [])
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to fetch extra activities: {e}")
        return ok(data=[])


@router.post("/extra-activities")
async def add_extra_activity(
    payload: ExtraActivityPayload,
    student: Student = Depends(get_current_student)
):
    # FIX (Bug 6): Insert into Supabase extra_activities table instead of local file
    from app.core.supabase_client import supabase_client
    import logging as _log
    logger = _log.getLogger(__name__)
    student_id_str = str(student.id)
    student_name = getattr(student, "name", "") or ""
    student_roll = str(getattr(student, "student_id", student_id_str) or student_id_str)

    # Build the record using only the columns that actually exist in the table:
    # id (auto), student_id, title, description, date, status, points, proof_url, created_at (auto)
    new_act: dict = {
        "student_id": student_id_str,
        "title": payload.title,
        "description": payload.description,
        "date": payload.date,
        "status": "Pending Review",
        "points": 0,
        "proof_url": _require_web_url(payload.proof_url, "Proof link"),
    }

    try:
        result = await supabase_client._request(
            "extra_activities",
            method="POST",
            body=[new_act],
            headers={"Prefer": "return=representation"}
        )
        inserted = result[0] if isinstance(result, list) and result else new_act
        return ok(data=inserted, message="Activity added for review")
    except Exception as e:
        err_str = str(e)
        logger.error(f"Failed to insert extra activity: {err_str}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save extra activity: {err_str}"
        )



@router.get("/notifications")
async def get_notifications(
    student: Student = Depends(get_current_student)
):
    from app.core.supabase_client import supabase_client
    import urllib.parse
    email = urllib.parse.quote(student.email)
    _SAFE_NOTIF_FIELDS = {"id", "title", "message", "type", "read", "created_at"}
    res = await supabase_client._request(
        f"notifications?recipient_email=eq.{email}&order=created_at.desc"
    )
    safe_res = [
        {k: v for k, v in row.items() if k in _SAFE_NOTIF_FIELDS}
        for row in (res if isinstance(res, list) else [])
    ]
    return ok(data=safe_res)



@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    student: Student = Depends(get_current_student)
):
    from app.core.supabase_client import supabase_client
    import urllib.parse
    email = urllib.parse.quote(student.email)
    try:
        await supabase_client._request(
            f"notifications?recipient_email=eq.{email}&read=eq.false",
            method="PATCH",
            body={"read": True}
        )
    except Exception as e:
        pass # ignore if none exist or error
    return ok(message="All notifications marked as read")

@router.post("/notifications/{notif_id}/read")
async def mark_notification_read(
    notif_id: str,
    student: Student = Depends(get_current_student)
):
    from app.core.supabase_client import supabase_client
    import urllib.parse
    email = urllib.parse.quote(student.email)
    try:
        # Scope the write to the caller's own recipient_email, matching
        # get_student_notifications/mark_all_notifications_read above —
        # otherwise any authenticated student could mark any other
        # student's notification as read by guessing/enumerating ids.
        await supabase_client._request(
            f"notifications?id=eq.{notif_id}&recipient_email=eq.{email}",
            method="PATCH",
            body={"read": True}
        )
    except Exception as e:
        pass
    return ok(message="Notification marked as read")


@router.get("/available-students")
async def get_available_students(
    student: Student = Depends(get_current_student)
):
    from app.core.supabase_client import supabase_client
    raw_data = await supabase_client.sync_unassigned_students()
    # Strip only the email field — keep id, roll, name, branch etc. so the
    # invite flow (add-member?student_id=...) continues to work correctly.
    _STRIP_FIELDS = {"email"}

    filtered = []
    for s in (raw_data or []):
        name_lower = str(s.get("name") or "").lower()
        # Filter out dummy/test/admin records
        if any(kw in name_lower for kw in ["admin", "procksi", "test student", "dummy"]):
            continue

        # Normalize legacy branch strings if needed
        b = s.get("branch") or "BTech CSE"
        if b == "B.Tech CS":
            b = "BTech CSE"

        safe_s = {k: v for k, v in s.items() if k not in _STRIP_FIELDS}
        safe_s["branch"] = b
        filtered.append(safe_s)

    sem_id = getattr(student, "semester_id", None)
    if not sem_id:
        try:
            active_sems = await supabase_client._request("semester_config?is_active=eq.true&limit=1")
            if active_sems:
                sem_id = active_sems[0].get("id")
        except Exception:
            pass

    if sem_id:
        sem_str = str(sem_id).strip().lower()
        filtered = [
            s for s in filtered
            if not s.get("semester_id") or str(s.get("semester_id")).strip().lower() == sem_str
        ]
    return ok(data=filtered)


async def check_team_not_locked(team_id: str, student: Student):
    from app.core.supabase_client import supabase_client
    import logging as _logging
    import urllib.parse
    _log = _logging.getLogger(__name__)

    # 1. Check Semester Config lock
    if getattr(student, "semester_id", None):
        try:
            sem_res = await supabase_client._request(f"semester_config?id=eq.{urllib.parse.quote(student.semester_id)}&limit=1")
            if sem_res and sem_res[0].get("is_locked"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Semester is locked. No changes are allowed."
                )
        except HTTPException:
            raise
        except Exception as e:
            _log.warning(f"Error checking semester lock config: {e}")

    # Normalize team_id
    team_id_str = str(team_id)
    if team_id_str.isdigit():
        team_id_str = f"TEAM-{team_id}"

    # 2. Fetch Team from teams_validation
    is_team_explicitly_unlocked = False
    try:
        team_res = await supabase_client._request(f"teams_validation?id=eq.{urllib.parse.quote(team_id_str)}&limit=1")
        if team_res:
            t = team_res[0]
            v_status = (t.get("validationStatus") or t.get("validationstatus") or "").strip().capitalize()
            # FIX (Bug 3): If admin marked the team as Invalid or Pending, it is
            # explicitly unlocked for roster edits — bypass all lock checks.
            if v_status in ("Invalid", "Pending"):
                is_team_explicitly_unlocked = True
            elif v_status in ["Locked", "Valid"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Team is locked (Validation Status: {v_status}). No changes are allowed."
                )
    except HTTPException:
        raise
    except Exception as e:
        _log.warning(f"Error checking team validation status: {e}")

    # 3. Check Team Formation Deadline (only if not explicitly unlocked by admin)
    if not is_team_explicitly_unlocked and getattr(student, "semester_id", None):
        from app.core.database import async_session_factory
        from app.models.deadline import Deadline
        from sqlalchemy import select
        from datetime import timezone
        
        due_date = datetime.strptime("2026-12-31 23:59:59", "%Y-%m-%d %H:%M:%S")
        try:
            async with async_session_factory() as session:
                stmt = select(Deadline).where(
                    Deadline.semester_id == student.semester_id,
                    Deadline.type.in_(["team", "teamFormation"])
                )
                res = await session.execute(stmt)
                deadline_row = res.scalars().first()
                if deadline_row:
                    due_date = deadline_row.due_date
        except Exception as e:
            _log.warning(f"Error checking teamFormation deadline: {e}")

        from datetime import timezone, timedelta
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=ist_tz)
        else:
            due_date = due_date.astimezone(ist_tz)

        if datetime.now(ist_tz) > due_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Team formation deadline has passed"
            )

    # 4. Fetch Proposal from proposals table
    try:
        proposal = await supabase_client.get_proposal_by_team_id(team_id_str)
        if proposal:
            p_status = (proposal.get("status") or "").strip().capitalize()
            if p_status in ["Approved", "Pending"]:
                display_status = "Approval Pending" if p_status == "Pending" else p_status
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Team is locked because the proposal is {display_status}. No changes are allowed."
                )
    except HTTPException:
        raise
    except Exception as e:
        _log.warning(f"Error checking proposal status: {e}")


@router.post("/team/remove-member")
async def remove_team_member(
    student_id: str,
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    from app.services.governance_service import GovernanceService
    await GovernanceService.enforce_deadline(db, student.semester_id, "teamFormation")

    from app.core.supabase_client import supabase_client
    team_data = await supabase_client.get_team_by_student_id(str(student.id), student.semester_id)
    team_id = (
        student.team_membership.team_id if (hasattr(student, 'team_membership') and student.team_membership)
        else (team_data.get("id") if team_data else None)
    )
    if not team_id:
        raise HTTPException(status_code=400, detail="Student is not in a team")

    # Leader-only, matching /team/disband and /team/project-details. Without this
    # any member could remove a teammate — including removing the leader.
    if getattr(student.team_membership, "role", None) != "LEADER":
        raise HTTPException(status_code=403, detail="Only the team leader can remove members")

    await check_team_not_locked(team_id, student)

    # Confirm the target is actually in the caller's team before removing them.
    #
    # remove_student_from_team falls back to scanning every team for the given
    # student when the team lookup misses, and removes them from whichever team
    # contains them. Without this check that fallback escapes the "own team only"
    # confinement entirely on any team-id format mismatch, letting a leader remove
    # a student from someone else's team.
    target_id = str(student_id).strip()
    team_members = (team_data or {}).get("members") or []
    if not isinstance(team_members, list):
        team_members = []

    def _member_id(member):
        if isinstance(member, dict):
            return str(member.get("id") or member.get("student_id") or member.get("roll") or "").strip()
        return str(member or "").strip()

    if team_members and not any(_member_id(m) == target_id for m in team_members):
        raise HTTPException(status_code=404, detail="That student is not a member of your team")

    from app.core.supabase_client import supabase_client
    try:
        await supabase_client.remove_student_from_team(team_id, student_id)
        return ok(message="Member removed successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/team/add-member")
async def add_team_member(
    student_id: str,
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    from app.services.governance_service import GovernanceService
    await GovernanceService.enforce_deadline(db, student.semester_id, "teamFormation")

    from app.core.supabase_client import supabase_client
    team_data = await supabase_client.get_team_by_student_id(str(student.id), student.semester_id)
    team_id = (
        student.team_membership.team_id if (hasattr(student, 'team_membership') and student.team_membership)
        else (team_data.get("id") if team_data else None)
    )
    if not team_id:
        raise HTTPException(status_code=400, detail="Student is not in a team")

    # Leader-only, matching /team/disband and /team/project-details.
    if getattr(student.team_membership, "role", None) != "LEADER":
        raise HTTPException(status_code=403, detail="Only the team leader can add members")

    await check_team_not_locked(team_id, student)

    from app.core.supabase_client import supabase_client
    import urllib.parse
    import uuid

    try:
        # 1. Fetch student info
        invited_info = await supabase_client._request(f"unassigned_students?id=eq.{urllib.parse.quote(student_id)}&limit=1")
        if not invited_info:
            invited_info = await supabase_client._request(f"unassigned_students?roll=eq.{urllib.parse.quote(student_id)}&limit=1")
            
        if not invited_info:
            invited_info = await supabase_client._request(f"students?id=eq.{urllib.parse.quote(student_id)}&limit=1")
            if not invited_info:
                invited_info = await supabase_client._request(f"students?student_id=eq.{urllib.parse.quote(student_id)}&limit=1")
                
        if not invited_info:
            raise HTTPException(status_code=404, detail="Student to invite not found")
            
        target_student = invited_info[0]
        target_student_id = str(target_student.get("id"))

        # 2. Check if they are in a team
        existing_team = await supabase_client.get_team_by_student_id(target_student_id, student.semester_id)
        if existing_team:
            raise HTTPException(status_code=400, detail="Student is already assigned to a team")

        # 3. Check if a pending join request already exists
        team_id_str = str(team_id)
        if team_id_str.isdigit():
            team_id_str = f"TEAM-{team_id}"
            
        existing_requests = await supabase_client._request(
            f"team_join_requests?student_id=eq.{urllib.parse.quote(target_student_id)}&team_id=eq.{urllib.parse.quote(team_id_str)}&status=eq.pending"
        )
        if existing_requests:
            raise HTTPException(status_code=400, detail="A join request is already pending for this student")
            
        # Get team name and team leader object
        team_res = await supabase_client._request(f"teams_validation?id=eq.{urllib.parse.quote(team_id_str)}&limit=1")
        team_name = team_res[0].get("title", "Custom Team") if team_res else "Custom Team"
        team_obj = team_res[0] if team_res else None

        req_row = {
            "id": str(uuid.uuid4()),
            "team_id": team_id_str,
            "team_name": team_name,
            "student_id": target_student_id,
            "student_name": target_student.get("name", ""),
            "student_branch": target_student.get("branch", "B.Tech CS"),
            "leader_id": str(student.id),
            "status": "pending",
            "requested_at": datetime.utcnow().isoformat(),
            "initiated_by": "leader"
        }

        await supabase_client._request("team_join_requests", method="POST", body=[req_row])
        return ok(message="Invitation sent successfully. Awaiting student approval.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/join-requests")
async def get_my_join_requests(
    student: Student = Depends(get_current_student)
):
    from app.core.supabase_client import supabase_client
    import urllib.parse
    sid = str(student.id)
    roll = str(getattr(student, 'student_id', sid))
    name = str(getattr(student, 'name', ''))
    ids_to_try = list(dict.fromkeys([sid, roll, name]))

    my_team = await supabase_client.get_team_by_student_id(sid, student.semester_id)
    my_team_id = str(my_team.get("id")) if (my_team and isinstance(my_team, dict)) else None

    try:
        requests_list = []
        for lookup_id in ids_to_try:
            if not lookup_id:
                continue
            raw_student = await supabase_client._request(
                f"team_join_requests?student_id=eq.{urllib.parse.quote(lookup_id)}&status=eq.pending"
            )
            if raw_student and isinstance(raw_student, list):
                requests_list.extend(raw_student)
            raw_leader = await supabase_client._request(
                f"team_join_requests?leader_id=eq.{urllib.parse.quote(lookup_id)}&status=eq.pending"
            )
            if raw_leader and isinstance(raw_leader, list):
                requests_list.extend(raw_leader)

        if my_team_id:
            raw_team = await supabase_client._request(
                f"team_join_requests?team_id=eq.{urllib.parse.quote(my_team_id)}&status=eq.pending"
            )
            if raw_team and isinstance(raw_team, list):
                requests_list.extend(raw_team)

        is_me_leader_flag = False
        if my_team:
            leader_val = str(my_team.get("leader_id") or my_team.get("leaderRaw") or my_team.get("leader") or "").lower()
            members = my_team.get("members", []) or []
            if leader_val in [sid.lower(), roll.lower(), name.lower()]:
                is_me_leader_flag = True
            elif isinstance(members, list):
                for m in members:
                    if isinstance(m, dict):
                        m_id = str(m.get("id") or m.get("student_id") or m.get("roll") or "").lower()
                        if m_id in [sid.lower(), roll.lower()] and (m.get("isLeader") or m.get("role") in ["LEADER", "leader"]):
                            is_me_leader_flag = True
                            break

        # Collect team details for each request
        team_ids_to_fetch = list(set([str(it.get("team_id")) for it in requests_list if it.get("team_id")]))
        teams_info_map = {}
        for tid in team_ids_to_fetch:
            try:
                t_rows = await supabase_client._request(f"teams_validation?id=eq.{urllib.parse.quote(tid)}&limit=1")
                if t_rows and len(t_rows) > 0:
                    teams_info_map[tid] = t_rows[0]
            except Exception:
                pass

        seen_ids = set()
        merged = []
        for item in requests_list:
            item_id_key = str(item.get("id") or "").strip()
            if item_id_key and item_id_key not in seen_ids:
                seen_ids.add(item_id_key)
                
                tid = str(item.get("team_id"))
                t_info = teams_info_map.get(tid, {})
                item["team_members"] = t_info.get("members") or []
                item["team_leader"] = t_info.get("leader") or item.get("leader_id") or ""
                item["project_title"] = t_info.get("title") or t_info.get("name") or item.get("team_name") or ""

                initiated_by = item.get("initiated_by", "leader")
                
                sid_val = str(item.get("student_id") or "").strip().lower()
                leader_val = str(item.get("leader_id") or "").strip().lower()
                
                student_match_list = [val for val in [sid.lower(), roll.lower(), name.lower()] if val and val != "none"]
                
                is_me_student = sid_val in student_match_list if sid_val and sid_val != "none" else False
                is_me_leader = (
                    (leader_val in student_match_list if leader_val and leader_val != "none" else False)
                    or (my_team_id and str(item.get("team_id")).lower() == my_team_id.lower() and is_me_leader_flag)
                )
                
                if initiated_by == "student":
                    is_me_recipient = is_me_leader
                else:
                    is_me_recipient = is_me_student
                    
                item["is_recipient"] = is_me_recipient
                merged.append(item)
        return ok(data=merged)
    except Exception:
        return ok(data=[])


@router.post("/join-requests/{request_id}/accept")
async def accept_join_request(
    request_id: str,
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    from app.services.governance_service import GovernanceService
    await GovernanceService.enforce_deadline(db, student.semester_id, "teamFormation")

    from app.core.supabase_client import supabase_client
    sid = str(student.id)
    roll = str(getattr(student, 'student_id', sid))

    req_data = await supabase_client._request(f"team_join_requests?id=eq.{request_id}&limit=1")
    if not req_data:
        raise HTTPException(status_code=404, detail="Join request not found")
    req = req_data[0]

    if req.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Request is no longer pending")

    stored_leader_id = str(req.get("leader_id", "")).lower()
    invitee_id = str(req.get("student_id", "")).lower()
    team_id = str(req.get("team_id", ""))

    my_team = await supabase_client.get_team_by_student_id(sid, student.semester_id)
    my_team_id = str(my_team.get("id")) if (my_team and isinstance(my_team, dict)) else None

    is_authorized = False
    if sid.lower() in [invitee_id, stored_leader_id] or roll.lower() in [invitee_id, stored_leader_id]:
        is_authorized = True
    elif my_team_id and my_team_id.lower() == team_id.lower():
        is_authorized = True

    if not is_authorized:
        raise HTTPException(status_code=403, detail="You are not authorized to accept this request")

    await check_team_not_locked(team_id, student)

    try:
        await supabase_client.accept_join_request(
            request_id=request_id,
            student_id=req.get("student_id"),
            team_id=team_id
        )
        
        try:
            import asyncio
            asyncio.create_task(trigger_join_request_accepted_emails(invitee_id, stored_leader_id, team_id))
        except Exception as email_err:
            print(f"Join request accept email trigger failed: {email_err}")

        return ok(message=f"Join request accepted. Student has been added to the team.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/join-requests/{request_id}/decline")
async def decline_join_request(
    request_id: str,
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    from app.services.governance_service import GovernanceService
    await GovernanceService.enforce_deadline(db, student.semester_id, "teamFormation")

    from app.core.supabase_client import supabase_client
    sid = str(student.id)
    roll = str(getattr(student, 'student_id', sid))

    req_data = await supabase_client._request(f"team_join_requests?id=eq.{request_id}&limit=1")
    if not req_data:
        raise HTTPException(status_code=404, detail="Join request not found")
    req = req_data[0]

    if req.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Request is no longer pending")

    stored_leader_id = str(req.get("leader_id", "")).lower()
    invitee_id = str(req.get("student_id", "")).lower()
    team_id = str(req.get("team_id", ""))

    my_team = await supabase_client.get_team_by_student_id(sid, student.semester_id)
    my_team_id = str(my_team.get("id")) if (my_team and isinstance(my_team, dict)) else None

    is_authorized = False
    if sid.lower() in [invitee_id, stored_leader_id] or roll.lower() in [invitee_id, stored_leader_id]:
        is_authorized = True
    elif my_team_id and my_team_id.lower() == team_id.lower():
        is_authorized = True


    if not is_authorized:
        raise HTTPException(status_code=403, detail="You are not authorized to decline this request")

    team_id = str(req.get("team_id", ""))

    await check_team_not_locked(team_id, student)

    try:
        await supabase_client.decline_join_request(
            request_id=request_id,
            student_id=invitee_id
        )
        return ok(message="Join request declined.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proposal")
async def submit_team_proposal(
    payload: ProposalPayload,
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    """Singular proposal submit endpoint (kept for legacy support)."""
    from app.services.governance_service import GovernanceService
    await GovernanceService.enforce_deadline(db, student.semester_id, "proposalUpload")

    team_id = student.team_membership.team_id if student.team_membership else None
    if not team_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student is not assigned to any team."
        )

    await check_team_not_locked(team_id, student)

    from app.core.supabase_client import supabase_client
    import urllib.parse as _urlparse

    # Leader-only, and block when an active proposal already exists — both of
    # which POST /proposals enforces and this legacy endpoint did not.
    #
    # Without the guard this delegates straight to save_proposal(), which only
    # PATCHes when get_proposal_by_team_id() returns a row. That lookup is cached
    # and uses limit=1 with no ordering, so a miss INSERTS a second proposal —
    # which is how teams 10 and 104 each ended up with an Approved copy plus a
    # Pending duplicate sitting in the admin review queue. A hit is no better: it
    # rewrites the Approved row back to Pending, silently un-approving it.
    if getattr(student.team_membership, "role", None) != "LEADER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the team leader can submit proposals"
        )

    existing_props = await supabase_client._request(
        f"proposals?teamId=eq.{_urlparse.quote(str(team_id))}"
    ) or []
    for _p in existing_props:
        if (_p.get("status") or "").strip().lower() in ("pending", "approved"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active proposal already exists for this team"
            )

    # The student's own batch is authoritative. Only fall back to an active
    # semester if the student somehow has none — and never blindly pick "the
    # first active" when the student already has one (multiple batches are
    # active at once).
    real_semester_id = student.semester_id
    if not real_semester_id:
        try:
            active_sems = await supabase_client._request("semester_config?is_active=eq.true&select=id")
            if active_sems and len(active_sems) == 1:
                real_semester_id = active_sems[0].get("id")
        except Exception:
            pass

    try:
        await supabase_client.save_proposal(
            team_id=team_id,
            semester_id=real_semester_id,
            title=payload.title,
            description=payload.description
        )

        await supabase_client.update_team_proposal_details(
            team_id=team_id,
            title=payload.title,
            description=payload.description,
            domain=payload.domain,
            members=payload.members
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit proposal: {str(e)}"
        )

    return ok(message="Proposal submitted successfully")


# ---------------------------------------------------------------------------
# Admin → Student Portal sync: Publish Results Flag
# ---------------------------------------------------------------------------
class PublishResultsPayload(BaseModel):
    published: bool = True


@router.post("/admin/publish-results")
async def admin_publish_results(
    payload: PublishResultsPayload,
    x_admin_api_key: str = Header(default=""),
):
    """
    Called by the Admin Portal when clicking 'Publish Final Results'.
    Server-to-server: authenticated with the shared ADMIN_API_KEY header, not a
    student session. Was completely unauthenticated before incident 2026-09-03.
    """
    import hmac
    import os
    expected = os.getenv("ADMIN_API_KEY", "")
    if not expected or not x_admin_api_key or not hmac.compare_digest(x_admin_api_key, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Invalid or missing X-Admin-Api-Key header")
    store = _read_store()
    store["results_published"] = payload.published
    _write_store(store)
    return ok(data={"results_published": payload.published}, message="Results publication status updated")


# NOTE: /join-requests/debug removed in incident 2026-09-03 remediation — it was
# an unauthenticated IDOR that dumped team_join_requests for any student id.

# ---------------------------------------------------------------------------
# Presentation Cycles (Dynamic)
# ---------------------------------------------------------------------------

@router.get("/presentation-cycles")
async def get_active_presentation_cycles(
    semester_id: Optional[str] = None,
    student: Student = Depends(get_current_student)
):
    from app.core.supabase_client import supabase_client
    sem_id = semester_id or student.semester_id
    if not sem_id:
        try:
            active_sems = await supabase_client._request("semester_config?is_active=eq.true&limit=1")
            if active_sems:
                sem_id = active_sems[0].get("id")
        except Exception:
            pass

    if not sem_id:
        return ok(data=[])
    try:
        cycles = await supabase_client._request(f"presentation_cycles?semester_id=eq.{sem_id}&order=created_at.asc")
        
        target_team_id_str = None
        try:
            all_tv = await supabase_client._request(f"teams_validation?semester_id=eq.{sem_id}")
            student_roll = student.id
            for tv in (all_tv or []):
                members = tv.get("members") or []
                if isinstance(members, str):
                    try:
                        import json as _json
                        members = _json.loads(members)
                    except Exception:
                        members = []
                
                is_member = False
                for m in members:
                    m_id = str(m.get("id") or m.get("roll") or "")
                    if m_id == str(student_roll) or m_id == str(student.student_id):
                        is_member = True
                        break
                if is_member:
                    target_team_id_str = tv["id"]
                    break
        except Exception:
            pass

        if not target_team_id_str:
            team_id = student.team_membership.team_id if (hasattr(student, 'team_membership') and student.team_membership) else None
            if team_id:
                from app.core.supabase_client import extract_numeric_id
                num_id = extract_numeric_id(str(team_id))
                target_team_id_str = f"TEAM-{num_id}" if num_id else str(team_id)
                
        if target_team_id_str:
            from app.core.supabase_client import extract_numeric_id
            num_id = extract_numeric_id(target_team_id_str)
            canonical_team_id = f"TEAM-{num_id}" if num_id else target_team_id_str
            
            submissions = await supabase_client._request(f"presentation_submissions?team_id=eq.{canonical_team_id}")
            evaluations = await supabase_client.get_evaluations_by_team(target_team_id_str)
            
            cycles_to_return = []
            for cycle in (cycles or []):
                cycle["submission"] = next((s for s in (submissions or []) if s.get("cycle_id") == cycle.get("id")), None)
                cycle["evaluation"] = next((e for e in (evaluations or []) if e.get("cycle_id") == cycle.get("id")), None)
                if cycle.get("status") != "draft" or cycle["submission"] or cycle["evaluation"]:
                    cycles_to_return.append(cycle)
            return ok(data=cycles_to_return)
        
        non_draft_cycles = [c for c in (cycles or []) if c.get("status") != "draft"]
        return ok(data=non_draft_cycles)
    except Exception as e:
        print("ERROR IN GET CYCLES:", e)
        return ok(data=[])

class SubmitPresentationPayload(BaseModel):
    github_url: Optional[str] = None
    file_url: Optional[str] = None
    notes: Optional[str] = None

@router.post("/presentation-cycles/{cycle_id}/submit")
async def submit_presentation(
    cycle_id: str,
    payload: SubmitPresentationPayload,
    student: Student = Depends(get_current_student)
):
    if not student.team_membership or not student.team_membership.team:
        raise HTTPException(status_code=400, detail="Not assigned to a team")
        
    from app.core.supabase_client import supabase_client, extract_numeric_id
    
    # 1. Check Cycle status and deadline
    cycles = await supabase_client._request(f"presentation_cycles?id=eq.{cycle_id}&limit=1")
    if not cycles:
        raise HTTPException(status_code=404, detail="Cycle not found")
        
    cycle = cycles[0]
    if cycle.get("status") in ["closed", "frozen"]:
        raise HTTPException(status_code=400, detail="This presentation cycle is closed or frozen")
        
    deadline_str = cycle.get("deadline")
    if deadline_str:
        try:
            if deadline_str.endswith('Z'):
                deadline_str = deadline_str[:-1] + '+00:00'
            deadline_dt = datetime.fromisoformat(deadline_str)
            if datetime.now(timezone.utc) > deadline_dt:
                raise HTTPException(status_code=400, detail="Submission deadline has passed")
        except Exception as e:
            pass
            
    if cycle.get("requires_synopsis") and not payload.file_url:
        raise HTTPException(status_code=400, detail="A file upload is required for this presentation cycle")
        
    team_id_raw = str(student.team_membership.team_id)
    num_id = extract_numeric_id(team_id_raw)
    canonical_team_id = f"TEAM-{num_id}" if num_id else team_id_raw
    
    # 2. Check for duplicate
    existing = await supabase_client._request(f"presentation_submissions?cycle_id=eq.{cycle_id}&team_id=eq.{canonical_team_id}")
    if existing:
        raise HTTPException(status_code=409, detail="You have already submitted for this presentation cycle")
        
    # 3. Submit
    new_sub = {
        "cycle_id": cycle_id,
        "team_id": canonical_team_id,
        "student_id": str(student.id),
        "submission_type": "github" if payload.github_url else "file",
        "github_url": payload.github_url,
        "file_url": payload.file_url,
        "notes": payload.notes,
        "submitted_at": datetime.utcnow().isoformat() + "Z"
    }
    
    await supabase_client._request("presentation_submissions", method="POST", body=[new_sub])
    return ok(data=new_sub, message="Presentation submitted successfully")


class ProjectDetailsPayload(BaseModel):
    repository_url: str
    tech_stack: str
    project_title: Optional[str] = None
    description: Optional[str] = None
    domain: Optional[str] = None


@router.get("/team/project-details")
async def get_team_project_details(
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    try:
        if not student.team_membership or not student.team_membership.team:
            return ok(data=None)
        
        team = student.team_membership.team

        # Fetch repository_url from github_data. team.id (legacy teams.id) has no
        # relationship to teams_validation.uid (the canonical team_uid), so
        # resolve it via team_memberships/teams_validation instead.
        from sqlalchemy import text
        repository_url = ""
        try:
            canon_res = await db.execute(
                text("""
                    SELECT tv.uid AS team_uid
                    FROM team_memberships tm
                    JOIN teams_validation tv ON tv.uid = tm.team_uid
                    WHERE tm.student_roll = :roll AND tm.semester_id = :sem
                    LIMIT 1
                """),
                {"roll": str(student.id), "sem": str(student.semester_id)},
            )
            canon_row = canon_res.mappings().first()
            if canon_row:
                gh_res = await db.execute(text("SELECT repository_url FROM github_data WHERE team_uid = :team_uid"), {"team_uid": canon_row["team_uid"]})
                gh_row = gh_res.first()
                if gh_row:
                    repository_url = gh_row[0] or ""
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error querying github_data table: {e}")
            
        # Prefer the latest approved proposal when reconstructed team rows still
        # contain placeholder titles/descriptions.
        tech_stack = ""
        proposal_title = ""
        proposal_description = ""
        try:
            from app.core.supabase_client import supabase_client
            latest_proposal = await supabase_client.get_latest_approved_proposal_by_team_id(str(team.id))
            if latest_proposal:
                tech_stack = latest_proposal.get("technology_stack") or latest_proposal.get("technologyStack") or ""
                proposal_title = (latest_proposal.get("title") or "").strip()
                proposal_description = (
                    latest_proposal.get("description") or latest_proposal.get("aiRationale") or ""
                ).strip()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error querying latest proposal for tech_stack from Supabase: {e}")
            
        domain_str = ""
        if team.domain:
            if isinstance(team.domain, list):
                domain_str = ", ".join(team.domain)
            elif isinstance(team.domain, str):
                domain_str = team.domain

        team_title = (team.project_title or "").strip()
        placeholder_title = not team_title or re.match(
            r"^team\s*-?\s*\d+$", team_title, re.IGNORECASE
        ) is not None
        project_title = proposal_title if placeholder_title and proposal_title else team_title
        project_description = (team.description or "").strip() or proposal_description

        return ok(data={
            "repository_url": repository_url,
            "tech_stack": tech_stack,
            "project_title": project_title,
            "description": project_description,
            "domain": domain_str
        })
    except HTTPException:
        raise
    except Exception as e:
        import logging, traceback
        logging.getLogger(__name__).error(f"Error fetching team project details: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to load project details: {str(e)}")


class ReservePsPayload(BaseModel):
    ps_id: str

@router.post("/team/reserve-ps")
async def reserve_problem_statement(
    payload: ReservePsPayload,
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    if not student.team_membership or not student.team_membership.team:
        raise HTTPException(status_code=400, detail="Student is not assigned to a team")
        
    if student.team_membership.role != "LEADER":
        raise HTTPException(status_code=403, detail="Only the team leader can reserve problem statements")
        
    team = student.team_membership.team
    
    # Check if team already has an approved proposal
    from app.core.supabase_client import supabase_client
    try:
        latest_proposal = await supabase_client.get_proposal_by_team_id(str(team.id))
        if latest_proposal and latest_proposal.get("status", "").lower() == "approved" and not str(latest_proposal.get("id", "")).startswith("PROP-ADM-") and (latest_proposal.get("proposalFile") or latest_proposal.get("document_url")):
            raise HTTPException(status_code=400, detail="Team already has an approved custom proposal. Cannot reserve problem statements.")
    except Exception:
        pass
        
    # Get the problem statement details
    statements = await supabase_client.get_problem_statements()
    ps = next((s for s in (statements or []) if s.get("id") == payload.ps_id), None)
    if not ps:
        raise HTTPException(status_code=404, detail="Problem statement not found")
        
    # The database function locks the PS row, checks capacity, and updates the
    # allocation in one transaction, preventing two concurrent second holders.
    ps_title = ps.get("title", "")
    team_validation_id = str(team.id)
    try:
        await reserve_ps_atomically(supabase_client, team_validation_id, payload.ps_id)
    except Exception as exc:
        if "team not found" in str(exc).lower() and getattr(team, "semester_id", None):
            team_validation_id = f"{team.semester_id}-T{team.id}"
            try:
                await reserve_ps_atomically(supabase_client, team_validation_id, payload.ps_id)
            except Exception as fallback_exc:
                raise HTTPException(status_code=409, detail=str(fallback_exc)) from fallback_exc
        else:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
            
    # Reserve the topic for this team
    team.project_title = ps_title
    team.description = ps.get("description", "")
    
    # Parse domain
    ps_domain = ps.get("domain", "General")
    team.domain = [ps_domain]
    
    await db.commit()
    
    return ok(message="Problem statement reserved successfully", data={"title": ps_title})


@router.post("/team/project-details")
async def save_team_project_details(
    payload: ProjectDetailsPayload,
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    try:
        if not student.team_membership or not student.team_membership.team:
            raise HTTPException(status_code=400, detail="Student is not assigned to a team")
        
        # Team leader only check:
        if student.team_membership.role != "LEADER":
            raise HTTPException(status_code=403, detail="Only the team leader can submit project details")
            
        team = student.team_membership.team
        
        # Verify proposal is approved or project is assigned
        is_approved = False
        if team.status == "valid":
            is_approved = True
            
        tech_stack = ""
        from app.core.supabase_client import supabase_client
        try:
            latest_proposal = await supabase_client.get_proposal_by_team_id(str(team.id))
            if latest_proposal:
                tech_stack = latest_proposal.get("technology_stack") or latest_proposal.get("technologyStack") or ""
                if latest_proposal.get("status", "").lower() == "approved":
                    is_approved = True
        except Exception:
            pass
            
        if team.project_title and not is_placeholder_title(team.project_title, team.name):
            is_approved = True
        elif getattr(team, "description", None) and not is_placeholder_title(team.description, team.name):
            is_approved = True
            
        if not is_approved:
            raise HTTPException(status_code=403, detail="Project details can only be submitted after proposal approval or project assignment.")

        # Allow updating GitHub repository URL and project details
        from sqlalchemy import text

        # Resolve the canonical team_ref (teams_validation.id) via
        # team_memberships rather than the legacy teams.id: that id is a locally
        # autoincrementing integer with no relationship to teams_validation.id,
        # and using it as if it were the team's number let this endpoint's
        # github_data/github_agent_analysis writes below collide with an
        # unrelated team from a different semester that happened to share the
        # same number — the cause of one team's GitHub repo showing up for
        # another team.
        canon_res = await db.execute(
            text("""
                SELECT tv.id AS team_ref, tv.uid AS team_uid, tv.team_number
                FROM team_memberships tm
                JOIN teams_validation tv ON tv.uid = tm.team_uid
                WHERE tm.student_roll = :roll AND tm.semester_id = :sem
                LIMIT 1
            """),
            {"roll": str(student.id), "sem": str(student.semester_id)},
        )
        canon_row = canon_res.mappings().first()
        if not canon_row:
            raise HTTPException(status_code=400, detail="Could not resolve your team record. Please contact support.")

        team_ref = canon_row["team_ref"]
        team_uid = canon_row["team_uid"]
        numeric_team_id = canon_row["team_number"] or parse_numeric_team_id(team_ref)

        # Validate repository public visibility (GitHub returns 404 for private repos).
        #
        # The URL is parsed and its hostname matched exactly before any request is
        # made, and the request itself goes to a constant host (api.github.com) with
        # redirects disabled — so a crafted repository_url cannot steer the server at
        # internal addresses or cloud metadata.
        if payload.repository_url:
            from app.core.github_url import api_url, parse_repo

            parsed_repo = parse_repo(payload.repository_url)
            if parsed_repo is None:
                raise HTTPException(
                    status_code=400,
                    detail="Enter a valid public GitHub repository URL, e.g. https://github.com/owner/repository."
                )

            owner, repo = parsed_repo
            try:
                import httpx
                async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
                    gh_res = await client.get(
                        api_url(owner, repo),
                        headers={"User-Agent": "Procksi-Repo-Checker/1.0", "Accept": "application/vnd.github+json"},
                    )
                    if gh_res.status_code == 404:
                        raise HTTPException(
                            status_code=400,
                            detail="The provided GitHub repository is private or does not exist. Please make sure your repository is set to PUBLIC on GitHub before submitting."
                        )
            except HTTPException:
                raise
            except Exception:
                pass

        # 1. Save repository_url to github_data and github_agent_analysis tables
        job_id = None

        # Fetch active year from semester_config or student.year
        academic_year = getattr(student, "year", None) or 2026
        try:
            res_sem = await db.execute(text("SELECT year FROM semester_config WHERE id = :sem_id"), {"sem_id": student.semester_id})
            sem_row = res_sem.first()
            if sem_row and sem_row[0]:
                digits = "".join(filter(str.isdigit, str(sem_row[0])))
                if digits:
                    academic_year = int(digits)
        except Exception:
            pass

        import json
        raw_json_str = json.dumps({
            "analysis_job_id": job_id,
            "analysis_status": "queued" if job_id else "none"
        })

        # Save to github_data using a savepoint to prevent transaction rollback failure
        try:
            async with db.begin_nested():
                # team_uid is the canonical, globally-unique key. team_ref is kept as
                # a fallback match only for legacy rows created before team_uid was
                # backfilled everywhere; team_id (team_number) is never used as a
                # match key since it repeats across semesters.
                check_query = text(
                    "SELECT id FROM github_data WHERE team_uid = :team_uid "
                    "OR (team_uid IS NULL AND team_ref = :team_ref) LIMIT 1"
                )
                check_res = await db.execute(check_query, {"team_uid": team_uid, "team_ref": team_ref})
                row = check_res.first()
                if row:
                    update_query = text(
                        "UPDATE github_data SET repository_url = :repo_url, raw_json = :raw_json, "
                        "team_id = :team_id, team_uid = :team_uid, team_ref = :team_ref WHERE id = :row_id"
                    )
                    await db.execute(update_query, {
                        "repo_url": payload.repository_url,
                        "raw_json": raw_json_str,
                        "team_id": numeric_team_id,
                        "team_uid": team_uid,
                        "team_ref": team_ref,
                        "row_id": row[0]
                    })
                else:
                    insert_query = text(
                        "INSERT INTO github_data (team_id, team_ref, team_uid, repository_url, raw_json) "
                        "VALUES (:team_id, :team_ref, :team_uid, :repo_url, :raw_json)"
                    )
                    await db.execute(insert_query, {
                        "team_id": numeric_team_id,
                        "team_ref": team_ref,
                        "team_uid": team_uid,
                        "repo_url": payload.repository_url,
                        "raw_json": raw_json_str
                    })
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to update/insert repository url in github_data: {e}")

        # Save to github_agent_analysis using a savepoint
        try:
            async with db.begin_nested():
                check_query = text(
                    "SELECT id FROM github_agent_analysis WHERE team_uid = :team_uid "
                    "OR (team_uid IS NULL AND team_ref = :team_ref) LIMIT 1"
                )
                check_res = await db.execute(check_query, {"team_uid": team_uid, "team_ref": team_ref})
                row = check_res.first()
                if row:
                    update_query = text(
                        "UPDATE github_agent_analysis SET repository_url = :repo_url, "
                        "analysis_job_id = :job_id, analysis_status = :status, year = :year, "
                        "team_id = :team_id, team_uid = :team_uid, team_ref = :team_ref WHERE id = :row_id"
                    )
                    await db.execute(update_query, {
                        "repo_url": payload.repository_url,
                        "job_id": job_id,
                        "status": "queued" if job_id else "none",
                        "year": academic_year,
                        "team_id": numeric_team_id,
                        "team_uid": team_uid,
                        "team_ref": team_ref,
                        "row_id": row[0]
                    })
                else:
                    insert_query = text(
                        "INSERT INTO github_agent_analysis (team_id, team_ref, team_uid, repository_url, "
                        "analysis_job_id, analysis_status, year) "
                        "VALUES (:team_id, :team_ref, :team_uid, :repo_url, :job_id, :status, :year)"
                    )
                    await db.execute(insert_query, {
                        "team_id": numeric_team_id,
                        "team_ref": team_ref,
                        "team_uid": team_uid,
                        "repo_url": payload.repository_url,
                        "job_id": job_id,
                        "status": "queued" if job_id else "none",
                        "year": academic_year
                    })
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to update/insert repository url in github_agent_analysis: {e}")
            
        # 2. Save tech_stack to latest proposal in Supabase
        try:
            latest_proposal = await supabase_client.get_proposal_by_team_id(str(team.id))
            if latest_proposal:
                proposal_id = latest_proposal.get("id")
                await supabase_client._request(
                    f"proposals?id=eq.{proposal_id}",
                    method="PATCH",
                    body={"technology_stack": payload.tech_stack}
                )
            else:
                import uuid
                proposal_id = f"PROP-{uuid.uuid4().hex[:8].upper()}"
                await supabase_client._request(
                    "proposals",
                    method="POST",
                    body=[{
                        "id": proposal_id,
                        "teamId": str(team.id),
                        "title": payload.project_title or team.project_title or "Project Proposal",
                        "aiRationale": payload.description or team.description or "",
                        "technology_stack": payload.tech_stack,
                        "status": "Approved",
                        "submittedDate": datetime.utcnow().strftime("%Y-%m-%d"),
                        "semester_id": student.semester_id
                    }]
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save technology_stack to proposal in Supabase: {e}")
        
        # 3. Save title/description/domain to team model if provided, and set status to valid
        if payload.project_title:
            team.project_title = payload.project_title
        if payload.description:
            team.description = payload.description
        if payload.domain:
            # Parse comma-separated domains
            if isinstance(payload.domain, str):
                team.domain = [d.strip() for d in payload.domain.split(",") if d.strip()]
            elif isinstance(payload.domain, list):
                team.domain = payload.domain
        
        team.status = "valid"
            
        try:
            await db.commit()
        except Exception as commit_err:
            await db.rollback()
            err_msg_str = str(commit_err).lower()
            if "uq_team_project_semester" in err_msg_str or "unique" in err_msg_str:
                raise HTTPException(status_code=400, detail="A project with this title already exists in your semester. Please choose a unique title.")
            raise HTTPException(status_code=400, detail=f"Database error saving project details: {str(commit_err)}")
        
        # Also update teams_validation in Supabase so that other portals see updated title/description/domain
        try:
            val_patch = {
                "validationStatus": "Valid"
            }
            if payload.project_title:
                val_patch["title"] = payload.project_title
            if payload.description:
                val_patch["description"] = payload.description
            if payload.domain:
                val_patch["domain"] = payload.domain
                
            if val_patch:
                t_id_str = str(team.id)
                res = await supabase_client._request(f"teams_validation?id=eq.{t_id_str}", method="PATCH", body=val_patch)
                if not res and getattr(team, "semester_id", None):
                    fallback_id = f"{team.semester_id}-T{team.id}"
                    await supabase_client._request(f"teams_validation?id=eq.{fallback_id}", method="PATCH", body=val_patch)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to sync project details to Supabase teams_validation: {e}")
            
        try:
            from app.services.email_service import notify_student_workspace_updated
            recip_emails = [m.student.email for m in team.members if m.student and m.student.email] if team.members else []
            if student.email and student.email not in recip_emails:
                recip_emails.append(student.email)
            notify_student_workspace_updated(recip_emails, str(team.id), payload.repository_url, payload.tech_stack)
        except Exception:
            pass

        return ok(message="Project details saved successfully")
    except HTTPException:
        raise
    except Exception as e:
        import logging, traceback
        logging.getLogger(__name__).error(f"Failed to save team project details: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to save project details: {str(e)}")


# ---------------------------------------------------------------------------
# Task 4.2: Student Team Creation and Join Requests endpoints
# ---------------------------------------------------------------------------
class CreateTeamRequest(BaseModel):
    name: Optional[str] = None

@router.get("/teams")
async def get_teams_for_student(
    student: Student = Depends(get_current_student)
):
    from app.core.supabase_client import supabase_client
    import urllib.parse
    # Strip only email addresses from nested member objects — keep all other
    # fields (id, name, members, memberCount, etc.) so the join-request flow works.
    _MEMBER_STRIP_FIELDS = {"email"}
    try:
        endpoint = "teams_validation"
        sem_id = student.semester_id
        if not sem_id:
            try:
                active_sems = await supabase_client._request("semester_config?is_active=eq.true&limit=1")
                if active_sems:
                    sem_id = active_sems[0].get("id")
            except Exception:
                pass
        if sem_id:
            endpoint += f"?semester_id=eq.{urllib.parse.quote(str(sem_id))}"
        teams = await supabase_client._request(endpoint)
        safe_teams = []
        for team in (teams or []):
            safe_team = dict(team)  # keep all top-level team fields
            # Scrub only email from the members array if present
            if "members" in team and isinstance(team["members"], list):
                safe_members = [
                    {k: v for k, v in m.items() if k not in _MEMBER_STRIP_FIELDS}
                    if isinstance(m, dict) else m
                    for m in team["members"]
                ]
                safe_team["members"] = safe_members
            safe_teams.append(safe_team)
        return ok(data=safe_teams)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def _assert_student_is_free(db: AsyncSession, student_roll: str, semester_id: str) -> None:
    """Reject the request if this student already belongs to a team.

    The real guarantee is the unique (semester_id, student_roll) constraint on
    team_memberships: two concurrent joins cannot both succeed, whatever the
    application does. This check exists only to turn that integrity error into a
    clear 409 before any other work happens.

    It deliberately does NOT use student.team_membership / the team_members
    table: that legacy registry holds a fraction of live memberships, so a
    student who is already in a team passes those checks and ends up in two.
    """
    from sqlalchemy import text as _sql_text

    res = await db.execute(
        _sql_text(
            "SELECT tv.team_number FROM team_memberships tm "
            "JOIN teams_validation tv ON tv.uid = tm.team_uid "
            "WHERE tm.student_roll = :roll AND tm.semester_id = :sem LIMIT 1"
        ),
        {"roll": str(student_roll), "sem": str(semester_id)},
    )
    row = res.first()
    if row:
        raise HTTPException(
            status_code=409,
            detail=(
                f"You are already in Team {row[0]}. Leave your current team "
                "before creating or joining another one."
            ),
        )


async def _delete_legacy_team(db, team_id, student_id) -> None:
    """Remove the legacy teams / team_members rows for an abandoned team.

    student_create_team writes the team twice: once into the legacy Postgres
    tables via the ORM, then into teams_validation + team_memberships, which are
    the source of truth. When the second half fails we used to roll back the
    session and delete only the teams_validation row, leaving the flushed legacy
    rows behind. That orphan is what makes a student read as "already in a team"
    on their own portal (which resolves membership through team_members) while
    admin still lists them as unassigned (which reads team_memberships).

    Best-effort by design: the caller is already on an error path and raises its
    own HTTPException, so a failure here must not mask the original cause.
    """
    from sqlalchemy import delete as sa_delete
    from app.models.team import Team as TeamModel
    from app.models.team_member import TeamMember as TeamMemberModel

    try:
        await db.execute(
            sa_delete(TeamMemberModel).where(TeamMemberModel.student_id == student_id)
        )
        if team_id is not None:
            await db.execute(sa_delete(TeamModel).where(TeamModel.id == team_id))
        await db.commit()
    except Exception as exc:
        logging.getLogger(__name__).error(
            "Could not remove legacy rows for team %s / student %s: %s",
            team_id, student_id, exc,
        )


@router.post("/team/create")
async def student_create_team(
    payload: Optional[CreateTeamRequest] = Body(None),
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    import uuid
    import re
    import logging
    from datetime import datetime
    from sqlalchemy import select
    from app.models.team import Team as TeamModel
    from app.models.team_member import TeamMember as TeamMemberModel
    from app.core.supabase_client import extract_numeric_id, supabase_client
    from app.services.governance_service import GovernanceService

    logger = logging.getLogger(__name__)

    sem_id = student.semester_id
    if not sem_id:
        try:
            active_sem = await supabase_client._request("semester_config?is_active=eq.true&limit=1")
            if active_sem:
                sem_id = active_sem[0].get("id")
        except Exception:
            pass

    if not sem_id:
        raise HTTPException(status_code=400, detail="No active semester assigned to student")

    try:
        await GovernanceService.enforce_deadline(db, sem_id, "teamFormation")
    except HTTPException as h_err:
        raise h_err
    except Exception as d_err:
        logger.warning(f"enforce_deadline check non-fatal error: {d_err}")

    # Authoritative one-team-per-student check (see _assert_student_is_free).
    # The legacy team_members-backed checks that used to run here are removed:
    # that table only holds a fraction of live memberships, so a stale/orphaned
    # row there rejected students the canonical team_memberships table already
    # considers free — visible as "You are already in a team" on an Unassigned
    # Student page.
    await _assert_student_is_free(db, student.id, sem_id)

    year_str = str(datetime.utcnow().year)
    btech_year = None
    try:
        sem_info = await supabase_client._request(f"semester_config?id=eq.{sem_id}&limit=1")
        if sem_info and sem_info[0].get("academic_year"):
            year_str = str(sem_info[0].get("academic_year"))
        elif sem_info and sem_info[0].get("year"):
            year_str = str(sem_info[0].get("year"))
        if sem_info:
            from app.services.email_service import btech_year_label
            btech_year = btech_year_label(
                academic_level=sem_info[0].get("academic_level"),
                semester_number=sem_info[0].get("semester_number"),
            )
    except Exception:
        pass

    # Allocate the lowest FREE team number for this semester.
    #
    # This previously took max(number) + 1 across the legacy team names AND every
    # teams_validation id *and title*. Titles are free text, so a single title
    # containing a large number poisoned the sequence permanently: that is how
    # live teams ended up numbered 958-968 while 1-194 still had 12 unused gaps.
    # Only team_number — an integer column, uniquely constrained per semester —
    # may drive numbering.
    #
    # Reusing a freed number is safe now that identity is teams_validation.uid and
    # every foreign key references it; the number is a display label, not a key.
    try:
        number_rows = await supabase_client._request(
            f"teams_validation?semester_id=eq.{sem_id}&select=team_number"
        ) or []
    except Exception as num_err:
        # Guessing here would risk colliding with an existing team's number, which
        # the unique index would reject anyway — fail cleanly instead.
        logger.error(f"Could not read existing team numbers: {num_err}")
        raise HTTPException(status_code=503, detail="Could not allocate a team number. Please try again.")

    used_numbers = {
        r["team_number"] for r in number_rows if r.get("team_number") is not None
    }
    next_num = 1
    while next_num in used_numbers:
        next_num += 1

    # The legacy teams table keeps its own name sequence; it must stay unique
    # there but must NOT influence the team number above.
    legacy_suffix = next_num
    while True:
        candidate_name = f"{year_str}-{legacy_suffix}"
        existing_check = await db.execute(select(TeamModel).where(TeamModel.name == candidate_name, TeamModel.semester_id == sem_id))
        if not existing_check.scalars().first():
            break
        legacy_suffix += 1

    new_team_name = f"{year_str}-{legacy_suffix}"

    # Create Team in Postgres
    new_team = TeamModel(
        name=new_team_name,
        project_title=f"Pending ({new_team_name})",
        semester_id=sem_id,
        status="invalid",
        is_validated=False
    )
    db.add(new_team)
    await db.flush()

    # Add student as leader
    leader_member = TeamMemberModel(
        id=str(uuid.uuid4()),
        team_id=new_team.id,
        student_id=student.id,
        role="LEADER"
    )
    db.add(leader_member)

    # Sync to Supabase teams_validation (with resolution header & non-blocking fallback)
    team_id_str = f"{sem_id}-T{next_num}"
    val_row = {
        "id": team_id_str,
        "title": f"Team {next_num}",
        "description": "",
        "leader": student.name,
        # leader_roll is the identifier; `leader` above is display text only.
        "leader_roll": str(student.id),
        # The number is an ordinary attribute now — id stays immutable and uid
        # (defaulted by the database) is the canonical identity.
        "team_number": next_num,
        "domain": "",
        "mentor": None,
        "memberCount": 1,
        "validationStatus": "Pending",
        "members": [
            {
                "id": str(student.id),
                "name": student.name,
                "branch": student.branch,
                "roll": student.student_id or str(student.id),
                "role": "LEADER"
            }
        ],
        "semester_id": sem_id
    }
    
    created_team_id = None
    for _attempt in range(5):
        try:
            headers = {"Prefer": "resolution=merge-duplicates"}
            await supabase_client._request("teams_validation", method="POST", body=[val_row], headers=headers)
            created_team_id = val_row["id"]
            break
        except Exception as insert_err:
            msg = str(insert_err)
            # Another student claimed this number between our read and our write.
            # The unique index on (semester_id, team_number) is what turns that
            # race into a clean error instead of two teams sharing a number, so
            # take the next number and retry.
            if "teams_validation_semester_number_key" in msg or "23505" in msg:
                next_num += 1
                val_row["team_number"] = next_num
                val_row["id"] = f"{sem_id}-T{next_num}"
                val_row["title"] = f"Team {next_num}"
                logger.warning(f"Team number taken, retrying with {next_num}")
                continue
            logger.error(f"teams_validation insert failed: {insert_err}")
            break

    # Previously a failure here left created_team_id as None, the membership block
    # below was skipped, and the endpoint still returned success — the student was
    # told their team existed when it did not. Fail loudly instead.
    if not created_team_id:
        # rollback() alone is not enough to undo the legacy rows: new_team and
        # leader_member were flushed above, and on a REST-backed session that
        # flush has already been written. Delete them explicitly, or the student
        # is left in team_members with no teams_validation row — visible as "in a
        # team" on their portal and "unassigned" on admin.
        await _delete_legacy_team(db, new_team.id, student.id)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not create your team. Please try again."
        )

    # Record the creator's membership in team_memberships — the source of truth.
    #
    # Without this row the creator is not actually in any team as far as the
    # database is concerned: they would still appear in available_students and
    # _assert_student_is_free would let them create a second team. If it fails we
    # delete the team we just created rather than leave a team nobody belongs to.
    if created_team_id:
        try:
            created = await supabase_client._request(
                f"teams_validation?id=eq.{created_team_id}&select=uid&limit=1"
            )
            team_uid = created[0].get("uid") if created else None
            if not team_uid:
                raise Exception("created team has no uid")

            await supabase_client._request("team_memberships", method="POST", body=[{
                "team_uid": team_uid,
                "student_roll": str(student.id),
                "semester_id": sem_id,
                "role": "LEADER",
            }])
        except Exception as mem_err:
            logger.error(f"Failed to record creator membership, rolling back team: {mem_err}")
            try:
                await supabase_client._request(
                    f"teams_validation?id=eq.{created_team_id}", method="DELETE"
                )
            except Exception as cleanup_err:
                logger.error(f"Could not clean up team {created_team_id}: {cleanup_err}")
            await _delete_legacy_team(db, new_team.id, student.id)
            await db.rollback()
            if "team_memberships_one_team_per_student" in str(mem_err) or "23505" in str(mem_err):
                raise HTTPException(
                    status_code=409,
                    detail="You are already in a team, so a new one could not be created.",
                )
            raise HTTPException(status_code=500, detail="Could not create team; please try again.")

    # Remove student from unassigned_students
    try:
        await supabase_client._request(f"unassigned_students?id=eq.{student.id}", method="DELETE")
    except Exception as del_err:
        logger.warning(f"Error removing student from unassigned_students: {del_err}")

    await db.commit()
    
    supabase_client._cache.clear()
    try:
        from app.api.student_deps import PROFILE_CACHE
        PROFILE_CACHE.clear()
    except Exception:
        pass

    try:
        from app.services.email_service import notify_team_formed
        if student.email:
            notify_team_formed([student.email], new_team_name, student.name, btech_year=btech_year)
    except Exception as e_err:
        logger.warning(f"Failed to trigger team formation email: {e_err}")

    return ok(data={"team_id": new_team.id}, message=f"Team formed successfully! Designated as {new_team_name}.")


@router.post("/team/disband")
async def disband_own_team(
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    """Let a leader disband their own team while it still has no other members,
    so they can step down and join a different team instead."""
    from app.services.governance_service import GovernanceService
    await GovernanceService.enforce_deadline(db, student.semester_id, "teamFormation")

    if not student.team_membership or not student.team_membership.team_id:
        raise HTTPException(status_code=400, detail="You are not in a team")

    if student.team_membership.role != "LEADER":
        raise HTTPException(status_code=403, detail="Only the team leader can disband the team")

    # student.team_membership is synthesized from Supabase teams_validation, so
    # team_id is already the "TEAM-<n>" string id used by that table (not the
    # Postgres teams.id integer) - use it as-is for Supabase lookups.
    team_id_str = str(student.team_membership.team_id)
    await check_team_not_locked(team_id_str, student)

    from app.core.supabase_client import supabase_client
    team_res = await supabase_client._request(f"teams_validation?id=eq.{urllib.parse.quote(team_id_str)}&limit=1")
    if not team_res:
        raise HTTPException(status_code=404, detail="Team not found")

    members = team_res[0].get("members", []) or []
    if len(members) > 1:
        raise HTTPException(status_code=400, detail="Cannot disband a team that has other members. Remove them first.")

    team_uid = team_res[0].get("uid")
    if team_uid:
        try:
            await supabase_client._request(f"team_memberships?team_uid=eq.{urllib.parse.quote(str(team_uid))}", method="DELETE")
        except Exception as tm_e:
            print(f"Warning: failed to delete team_memberships for disbanded team {team_uid}: {tm_e}")

    try:
        await supabase_client._request(f"teams_validation?id=eq.{urllib.parse.quote(team_id_str)}", method="DELETE")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove team from Supabase: {str(e)}")

    try:
        await supabase_client._request(
            f"team_join_requests?team_id=eq.{urllib.parse.quote(team_id_str)}&status=eq.pending",
            method="PATCH",
            body={"status": "cancelled", "resolved_at": datetime.utcnow().isoformat()}
        )
    except Exception as e:
        print(f"Error cancelling pending join requests for disbanded team {team_id_str}: {e}")

    try:
        await supabase_client._request(f"unassigned_students?id=eq.{student.id}", method="DELETE")
    except Exception:
        pass
    try:
        await supabase_client._request("unassigned_students", method="POST", body=[{
            "id": str(student.id),
            "name": student.name,
            "roll": student.student_id or str(student.id),
            "branch": student.branch,
            "semester_id": student.semester_id
        }])
    except Exception as e:
        print(f"Error re-adding student to unassigned_students after disband: {e}")

    # Best-effort cleanup of the Postgres-side team rows created at team formation.
    # Match by student_id (not team_id) since the Postgres teams.id integer isn't
    # directly available from the Supabase-backed team_membership object above.
    try:
        result = await db.execute(select(TeamMember).where(TeamMember.student_id == student.id))
        member_row = result.scalar_one_or_none()
        if member_row:
            numeric_team_id = member_row.team_id
            await db.delete(member_row)
            other = await db.execute(select(TeamMember).where(TeamMember.team_id == numeric_team_id))
            if not other.scalars().first():
                team_obj = await db.get(Team, numeric_team_id)
                if team_obj:
                    await db.delete(team_obj)
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(f"Warning: failed to clean up Postgres team rows for student {student.id}: {e}")

    supabase_client._cache.clear()
    try:
        from app.api.student_deps import PROFILE_CACHE
        PROFILE_CACHE.clear()
    except Exception:
        pass

    return ok(message="Team disbanded successfully. You can now browse and join another team.")


@router.post("/team/request-join")
async def request_join_team(
    team_id: str,
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    from app.services.governance_service import GovernanceService
    await GovernanceService.enforce_deadline(db, student.semester_id, "teamFormation")

    from app.core.supabase_client import supabase_client

    # Authoritative check first — backed by the unique constraint on
    # team_memberships, so it cannot be raced past. The follow-up check that
    # used to run here (student.team_membership / get_team_by_student_id, which
    # falls back to scanning teams_validation.members JSONB) is removed: that
    # JSONB blob and the legacy team_members table both go stale independently
    # of team_memberships, so they could reject a student this authoritative
    # check had already cleared as free — visible as "You are already in a
    # team" on an Unassigned Student page.
    await _assert_student_is_free(db, student.id, student.semester_id)

    team_id_str = str(team_id)
    if team_id_str.isdigit():
        team_id_str = f"TEAM-{team_id}"

    from app.core.supabase_client import supabase_client
    import urllib.parse
    team_res = await supabase_client._request(f"teams_validation?id=eq.{urllib.parse.quote(team_id_str)}&limit=1")
    if not team_res:
        raise HTTPException(status_code=404, detail="Team not found")
    team_obj = team_res[0]

    members = team_obj.get("members", []) or []
    leader_id = None
    for m in members:
        if isinstance(m, dict) and (m.get("role") == "LEADER" or m.get("isLeader") is True):
            leader_id = m.get("id")
            break
    
    if not leader_id:
        # leader_roll is the leader's ROLL NUMBER. teams_validation.leader holds a
        # display name, which must never be used as an identifier — names are
        # neither unique nor stable.
        leader_id = team_obj.get("leader_roll")
        if not leader_id and members:
            leader_id = members[0].get("id") if isinstance(members[0], dict) else members[0]

    if not leader_id:
        raise HTTPException(status_code=400, detail="Team leader could not be resolved")

    existing_requests = await supabase_client._request(
        f"team_join_requests?student_id=eq.{urllib.parse.quote(str(student.id))}&team_id=eq.{urllib.parse.quote(team_id_str)}&status=eq.pending"
    )
    if existing_requests:
        raise HTTPException(status_code=400, detail="You have already requested to join this team")

    import uuid
    req_row = {
        "id": str(uuid.uuid4()),
        "team_id": team_id_str,
        "team_name": team_obj.get("title", ""),
        "student_id": str(student.id),
        "student_name": student.name,
        "student_branch": student.branch,
        "leader_id": str(leader_id),
        "status": "pending",
        "requested_at": datetime.utcnow().isoformat(),
        "initiated_by": "student"
    }

    await supabase_client._request("team_join_requests", method="POST", body=[req_row])
    return ok(message="Join request sent to the team leader.")


async def trigger_join_request_accepted_emails(invitee_id: str, leader_id: str, team_id: str):
    import smtplib
    import os
    import threading
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from sqlalchemy import select
    from app.models.student import Student
    from app.models.semester_config import SemesterConfig
    from app.core.config import settings
    from app.core.database import async_session_factory
    from app.services.email_service import btech_year_label, format_clean_team_name

    btech_year = None
    async with async_session_factory() as db:
        async def get_student_details(sid: str):
            try:
                res = await db.execute(select(Student).where((Student.id == sid) | (Student.student_id == sid)))
                return res.scalars().first()
            except Exception:
                return None

        invitee = await get_student_details(invitee_id)
        leader = await get_student_details(leader_id)

        # team_id is "<semester_uuid>-T<number>" — resolve the B.Tech year from
        # that semester so 2nd-year teams are not labelled "3rd Year".
        try:
            sem_id = re.sub(r"-[Tt]\d+$", "", str(team_id)).strip()
            if sem_id and sem_id != str(team_id):
                res = await db.execute(select(SemesterConfig).where(SemesterConfig.id == sem_id))
                sem = res.scalars().first()
                if sem is not None:
                    btech_year = btech_year_label(
                        academic_level=getattr(sem, "academic_level", None),
                        semester_number=getattr(sem, "semester_number", None),
                    )
        except Exception:
            pass

    recipients = []
    if invitee and invitee.email:
        recipients.append(invitee.email)
    if leader and leader.email:
        recipients.append(leader.email)

    if not recipients:
        return

    team_label = format_clean_team_name(team_id, btech_year=btech_year)
    subject = f"Teammate Joined {team_label}"
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 12px;">
        <h2 style="color: #10b981;">Teammate Join Request Accepted</h2>
        <p>Dear Students,</p>
        <p>A new teammate has officially joined your project team ({team_label}).</p>
        <p><b>Joined Student:</b> {invitee.name if invitee else invitee_id}</p>
        <p style="margin-top: 15px;">Please log in to the Student Portal to check your updated team members list and coordinate on project tasks.</p>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;"/>
        <p style="font-size: 12px; color: #888;">This is an automated notification from Procksi.</p>
    </div>
    """

    def task():
        try:
            mail_server = settings.MAIL_SERVER or "smtp.gmail.com"
            mail_port = settings.MAIL_PORT or 587
            mail_username = settings.MAIL_USERNAME or os.getenv("MASTER_ADMIN_EMAIL") or ""
            mail_password = (settings.MAIL_PASSWORD or os.getenv("MAIL_PASSWORD") or "").replace(" ", "").strip()
            mail_from = settings.MAIL_FROM or mail_username

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = mail_from
            msg["To"] = ", ".join(recipients)
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(mail_server, mail_port, timeout=20) as server:
                server.starttls()
                server.login(mail_username, mail_password)
                server.sendmail(mail_from, recipients, msg.as_string())
        except Exception as e:
            pass

    thread = threading.Thread(target=task)
    thread.daemon = True
    thread.start()


@router.get("/team/github")
async def get_student_team_github_data(
    student: Student = Depends(get_current_student),
    db: AsyncSession = Depends(get_db)
):
    # Resolve the student's current team from team_memberships/teams_validation —
    # the canonical source of truth — rather than the legacy team_members/teams
    # ORM tables. That legacy path is unreliable two ways: (1) teams.id is a
    # locally-autoincrementing integer with no relationship to teams_validation.id
    # (team_ref), so matching github_data/github_agent_analysis on it either found
    # nothing or, via a numeric fallback, could coincidentally match a different
    # team's row from another semester; and (2) a student who joined a team via a
    # join request (rather than creating it) never gets a legacy team_members row
    # at all, so this endpoint returned nothing for them.
    from sqlalchemy import text
    team_row_res = await db.execute(
        text("""
            SELECT tv.id AS team_ref, tv.uid AS team_uid, tv.team_number
            FROM team_memberships tm
            JOIN teams_validation tv ON tv.uid = tm.team_uid
            WHERE tm.student_roll = :roll AND tm.semester_id = :sem
            LIMIT 1
        """),
        {"roll": str(student.id), "sem": str(student.semester_id)},
    )
    team_row = team_row_res.mappings().first()
    if not team_row:
        return ok(data=None)

    team_ref = team_row["team_ref"]
    team_uid = team_row["team_uid"]
    num_id = team_row["team_number"] or parse_numeric_team_id(team_ref)

    if not num_id or num_id <= 0:
        raise HTTPException(status_code=404, detail="Invalid team number associated with your membership.")

    # Try querying the github_agent_analysis table first
    gh_res = await db.execute(
        text("""
            SELECT 
                repository_url, 
                commit_count_30d, 
                analysis_status, 
                quality_score, 
                security_score, 
                originality_score, 
                architecture_score, 
                documentation_score, 
                tech_stack,
                raw_report
            FROM github_agent_analysis
            WHERE team_uid = :team_uid
        """),
        {"team_uid": team_uid},
    )
    gh_row = gh_res.mappings().first()

    analysis_status = "pending"
    results_payload = {}
    repo_url = ""
    commit_count = 0
    raw_report_val = None
    progress = 0
    current_stage = None
    error_message = None

    # Always fetch the admin-authoritative repo URL from github_data
    gd_res = await db.execute(
        text("SELECT repository_url, commit_count_30d, raw_json FROM github_data WHERE team_uid = :team_uid"),
        {"team_uid": team_uid}
    )
    gd_row = gd_res.mappings().first()
    admin_repo_url = (gd_row["repository_url"] or "") if gd_row else ""
    
    if gh_row:
        # Prefer admin-saved URL from github_data over the potentially stale github_agent_analysis URL
        repo_url     = admin_repo_url or gh_row["repository_url"] or ""
        commit_count = gh_row["commit_count_30d"] or 0
        analysis_status = gh_row["analysis_status"] or "pending"
        if analysis_status == "dlq":
            analysis_status = "failed"
        raw_report_val = gh_row["raw_report"]
        
        # If admin changed the repo URL, reflect that as "pending" status for the NEW url
        gaa_url = gh_row["repository_url"] or ""
        def _norm(u):
            u = str(u or "").strip().lower()
            return u[:-4] if u.endswith(".git") else u
        if admin_repo_url and _norm(admin_repo_url) != _norm(gaa_url):
            # New URL hasn't been analyzed yet — treat as pending/queued
            if analysis_status not in ("queued", "running"):
                analysis_status = "pending"
            raw_report_val = None  # Don't show stale report for old repo

        # Check remote status in real-time if queued or running
        if analysis_status in ("queued", "running"):
            job_res = await db.execute(
                text("SELECT raw_json FROM github_data WHERE team_uid = :team_uid"),
                {"team_uid": team_uid}
            )
            job_row = job_res.mappings().first()
            if job_row and job_row.get("raw_json"):
                try:
                    raw_js = json.loads(job_row["raw_json"]) if isinstance(job_row["raw_json"], str) else job_row["raw_json"]
                    job_id = raw_js.get("analysis_job_id")
                    if job_id:
                        from app.core.github_analyzer import GitHubAnalyzerClient
                        status_data = await GitHubAnalyzerClient.check_status(job_id)
                        if status_data:
                            remote_status = status_data.get("status")
                            progress = status_data.get("progress") or 0
                            current_stage = status_data.get("currentStage") or status_data.get("current_stage")
                            error_message = status_data.get("errorMessage") or status_data.get("error_message")
                            
                            if remote_status in ("completed", "failed", "dlq"):
                                actual_status = "completed" if remote_status == "completed" else "failed"
                                analysis_status = actual_status
                                
                                rr_val = None
                                if actual_status == "completed":
                                    # Fetch results
                                    report_data = await GitHubAnalyzerClient.get_results(job_id)
                                    if not report_data:
                                        # Try getting it by reports endpoint too
                                        import httpx
                                        from app.core.config import settings
                                        api_url = settings.REPOSITORY_ANALYSIS_API_URL
                                        try:
                                            async with httpx.AsyncClient() as client:
                                                rep_res = await client.get(f"{api_url}/api/reports/team/{job_id}", timeout=15.0)
                                                if rep_res.status_code == 200:
                                                    report_data = rep_res.json()
                                        except Exception:
                                            pass
                                            
                                    if report_data:
                                        rr_val = json.dumps(report_data)
                                        raw_report_val = rr_val
                                        analysis = report_data.get("analysis", {})
                                        commits_block = report_data.get("commits", {})
                                        total_commits = commits_block.get("total", 0)
                                        tech_stack_raw = report_data.get("codeMetrics", {}).get("techStack", [])
                                        if not tech_stack_raw:
                                            tech_stack_raw = report_data.get("codeMetrics", {}).get("frameworks", [])
                                        
                                        await db.execute(
                                            text("""
                                                UPDATE github_agent_analysis 
                                                SET analysis_status = 'completed',
                                                    raw_report = CAST(:report AS JSONB),
                                                    quality_score     = :qs,
                                                    security_score    = :ss,
                                                    originality_score = :os,
                                                    architecture_score = :ars,
                                                    documentation_score = :ds,
                                                    commit_count_30d  = :cc,
                                                    tech_stack        = CAST(:ts AS JSONB)
                                                WHERE team_uid = :team_uid
                                            """),
                                            {
                                                "report": rr_val,
                                                "qs":   analysis.get("qualityScore", 0),
                                                "ss":   analysis.get("securityScore", 0),
                                                "os":   analysis.get("originalityScore", 0),
                                                "ars":  analysis.get("architectureScore", 0),
                                                "ds":   analysis.get("documentationScore", 0),
                                                "cc":   total_commits,
                                                "ts":   json.dumps(tech_stack_raw),
                                                "team_uid": team_uid
                                            }
                                        )

                                if not rr_val:
                                    if actual_status == "failed" and error_message:
                                        rr_val = json.dumps({"errorMessage": error_message})
                                    await db.execute(
                                        text("""
                                            UPDATE github_agent_analysis
                                            SET analysis_status = :status,
                                                raw_report = COALESCE(raw_report, :rr)
                                            WHERE team_uid = :team_uid
                                        """),
                                        {"status": actual_status, "team_uid": team_uid, "rr": rr_val}
                                    )
                                    
                                # Sync into github_data raw_json
                                rj_data = {"analysis_status": actual_status}
                                if rr_val:
                                    try:
                                        rj_data["results"] = json.loads(rr_val)
                                    except:
                                        pass
                                if error_message:
                                    rj_data["error_message"] = error_message
                                    
                                await db.execute(
                                    text("UPDATE github_data SET raw_json = :rj WHERE team_uid = :team_uid"),
                                    {"rj": json.dumps(rj_data), "team_uid": team_uid}
                                )
                                await db.commit()
                except Exception as check_e:
                    print("Error checking remote job status in student endpoint:", check_e)
    else:
        repo_url = admin_repo_url

    # Auto-trigger remote analysis if we have a repo URL and the status is not completed, queued, or running
    if repo_url and analysis_status not in ("completed", "queued", "running"):
        from app.core.config import settings
        import httpx
        api_url = settings.REPOSITORY_ANALYSIS_API_URL
        repo_name_suffix = ""
        parts = repo_url.rstrip("/").rstrip(".git").split("/")
        if parts:
            repo_name_suffix = f" - {parts[-1]}"
        team_name = f"Team {num_id}{repo_name_suffix}"
        
        async with httpx.AsyncClient() as client:
            try:
                trigger_res = await client.post(
                    f"{api_url}/api/analyze-repo",
                    json={
                        "repo_url": repo_url,
                        "team_name": team_name,
                        "force": False
                    },
                    timeout=10.0
                )
                if trigger_res.status_code in (200, 201, 202):
                    body = trigger_res.json()
                    job_id = body.get("job_id") or body.get("jobId")
                    if job_id:
                        analysis_status = "queued"
                        # Save state
                        await db.execute(
                            text("""
                                INSERT INTO github_agent_analysis
                                    (team_id, team_ref, team_uid, repository_url, analysis_status, year, analysis_job_id)
                                VALUES
                                    (:tid, :team_ref, :team_uid, :url, 'queued', 3, :rid)
                                ON CONFLICT (team_uid) DO UPDATE SET
                                    repository_url  = :url,
                                    analysis_status = 'queued',
                                    analysis_job_id = :rid
                                    , team_id = :tid
                                    , team_ref = :team_ref
                            """),
                            {"tid": num_id, "team_ref": team_ref, "team_uid": team_uid, "url": repo_url, "rid": job_id}
                        )
                        await db.execute(
                            text("""
                                INSERT INTO github_data
                                    (team_id, team_ref, team_uid, repository_url, raw_json)
                                VALUES
                                    (:tid, :team_ref, :team_uid, :url, :rj)
                                ON CONFLICT (team_uid) DO UPDATE SET
                                    repository_url  = :url,
                                    raw_json        = :rj
                                    , team_id       = :tid
                                    , team_ref      = :team_ref
                            """),
                            {"tid": num_id, "team_ref": team_ref, "team_uid": team_uid, "url": repo_url, "rj": json.dumps({"analysis_status": "queued", "analysis_job_id": job_id})}
                        )
                        await db.commit()
            except Exception as trigger_err:
                print("Auto-trigger failed in student GET endpoint:", trigger_err)

    # Parse raw_report JSON if it's a string
    if raw_report_val:
        try:
            if isinstance(raw_report_val, str):
                results_payload = json.loads(raw_report_val)
            else:
                results_payload = raw_report_val
        except Exception:
            results_payload = {}
            
    # Try parsing error message from raw_report metadata if present
    if not error_message and results_payload and isinstance(results_payload, dict):
        error_message = results_payload.get("error") or results_payload.get("errorMessage")

    return ok(data={
        "teamId": team_id_str,
        "repositoryUrl": repo_url,
        "commitCount": commit_count,
        "analysisStatus": analysis_status,
        "analysisResults": results_payload,
        "progress": progress,
        "currentStage": current_stage,
        "errorMessage": error_message
    })





@router.get("/procksi-chat-enabled")
async def get_procksi_chat_enabled():
    """Whether Procksi Chat is switched on for the student portal this semester.

    Deliberately unauthenticated and read-only: the portal shell needs this
    before it knows who the user is, and the answer is a single boolean that
    reveals nothing sensitive.

    Served here rather than read from the browser because RLS hides
    semester_config from the anon key -- a direct client read returns zero
    rows, which is indistinguishable from "no semester configured".

    Fails open (returns true) so a lookup problem leaves the feature as the
    build intended instead of hiding it.
    """
    try:
        from app.core.supabase_client import supabase_client
        rows = await supabase_client._request(
            "semester_config?is_active=eq.true&select=procksi_chat_student&limit=1"
        )
        if not rows:
            # See the mentor portal's copy: a silent fail-open makes a stale or
            # misconfigured backend look exactly like the feature being on.
            logging.getLogger(__name__).warning(
                "procksi-chat-enabled: no active semester_config row; defaulting to enabled"
            )
            return {"enabled": True, "reason": "no-active-semester"}
        value = rows[0].get("procksi_chat_student")
        if value is None:
            # The column has not been added yet.
            logging.getLogger(__name__).warning(
                "procksi-chat-enabled: procksi_chat_student column missing; defaulting to enabled"
            )
            return {"enabled": True, "reason": "column-missing"}
        return {"enabled": bool(value), "reason": "config"}
    except Exception as exc:
        logging.getLogger(__name__).warning("procksi-chat-enabled: lookup failed (%s); defaulting to enabled", exc)
        return {"enabled": True, "reason": "lookup-failed"}
