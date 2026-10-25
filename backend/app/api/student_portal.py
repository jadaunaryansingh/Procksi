import asyncio
import json
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.api.deps import get_db
from app.api.student_deps import get_current_student
from app.models.student import Student
from app.models.team_member import TeamMember
from app.models.team import Team
from app.models.mentor import Mentor
from app.models.deadline import Deadline
from app.models.proposal import Proposal
from app.models.schedule import Schedule
from app.models.evaluation import Evaluation
from app.models.result import Result
from app.schemas.common import ok

router = APIRouter(prefix="/api/student", tags=["Student Portal"])

DATA_STORE_PATH = Path(__file__).resolve().parent.parent / "data_store.json"


def _read_store() -> dict:
    if not DATA_STORE_PATH.exists():
        return {
            "problem_statements": [],
            "announcements": [],
            "notifications": [],
            "extra_activities": {},
            "preferences": {}
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
            "preferences": {}
        }


def _write_store(data: dict):
    try:
        with open(DATA_STORE_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Failed to write to data store: {e}")


class ProposalPayload(BaseModel):
    title: str
    description: str
    domain: str
    techStack: str
    github: str
    proposalFile: str


class ExtraActivityPayload(BaseModel):
    title: str
    description: str
    date: str


@router.get("/me")
async def get_my_profile(
    student: Student = Depends(get_current_student)
):
    """
    Return the full profile of the currently authenticated student.
    Includes team name, team members, and assigned mentor details.
    """
    team_data = None
    mentor_data = None

    if student.team_membership:
        team_obj = student.team_membership.team
        if team_obj:
            members_list = []
            for member in team_obj.members:
                m_avatar = f"https://ui-avatars.com/api/?name={member.student.name.replace(' ', '+')}&background=random"
                members_list.append({
                    "id": str(member.student.id),
                    "name": member.student.name,
                    "email": member.student.email,
                    "roll_number": member.student.student_id,
                    "isLeader": member.role == "LEADER",
                    "avatar": m_avatar,
                    "role": "Student"
                })
            
            # Check proposal file using Supabase REST Client
            from app.core.supabase_client import supabase_client
            proposal = await supabase_client.get_proposal_by_team_id(team_obj.id)
            proposal_file = f"proposal_{str(team_obj.id)[:8]}.pdf" if proposal else None
            proposal_status = proposal["status"].capitalize() if (proposal and proposal.get("status")) else "Not Submitted"

            # Fallback techStack and domain
            tech_stack = ""
            domain_str = team_obj.domain[0] if team_obj.domain else ""

            team_data = {
                "id": str(team_obj.id),
                "name": team_obj.name,
                "title": team_obj.project_title or "",
                "description": team_obj.description or "",
                "domain": domain_str,
                "techStack": tech_stack,
                "github": f"https://github.com/PMS-2026/team-{str(team_obj.id)[:8]}",
                "proposalFile": proposal_file,
                "status": proposal_status,
                "members": members_list
            }
            
            # Format mentor details
            if team_obj.mentor:
                mentor_data = {
                    "name": team_obj.mentor.name,
                    "email": team_obj.mentor.email
                }

    avatar_url = f"https://ui-avatars.com/api/?name={student.name.replace(' ', '+')}&background=random"

    profile_data = {
        "id": str(student.id),
        "name": student.name,
        "email": student.email,
        "roll_number": student.student_id,
        "branch": student.branch,
        "section": student.section,
        "year": student.year,
        "avatar_url": avatar_url,
        "phone": None,
        "team": team_data,
        "mentor": mentor_data
    }

    return ok(data=profile_data)


@router.get("/team")
async def get_student_team(
    student: Student = Depends(get_current_student)
):
    """Return the team details of the currently authenticated student."""
    if not student.team_membership or not student.team_membership.team:
        return ok(data=None)
    
    team_obj = student.team_membership.team
    return ok(data={
        "id": str(team_obj.id),
        "name": team_obj.name,
        "project_title": team_obj.project_title,
        "semester_id": team_obj.semester_id,
        "created_at": getattr(team_obj, 'created_at', None)
    })


@router.get("/team/members")
async def get_student_team_members(
    student: Student = Depends(get_current_student)
):
    """Return the team members of the currently authenticated student's team."""
    if not student.team_membership or not student.team_membership.team:
        return ok(data=[])
    
    team_obj = student.team_membership.team
    members_list = []
    for member in team_obj.members:
        s = member.student
        avatar_url = f"https://ui-avatars.com/api/?name={s.name.replace(' ', '+')}&background=random"
        members_list.append({
            "id": str(s.id),
            "name": s.name,
            "email": s.email,
            "roll_number": s.student_id,
            "branch": s.branch,
            "section": s.section,
            "avatar_url": avatar_url,
            "isLeader": member.role == "LEADER"
        })
        
    return ok(data=members_list)


@router.get("/milestones")
async def get_student_milestones(
    student: Student = Depends(get_current_student)
):
    """Return milestones calculated dynamically based on database state."""
    semester_id = student.semester_id
    team_id = student.team_membership.team_id if student.team_membership else None

    # Fallback deadlines
    proposal_deadline = "2026-03-15T23:59:59"
    evaluation_deadline = "2026-04-15T23:59:59"

    # Milestone 1: Proposal status
    proposal_status = "pending"
    github_url = ""
    proposal_file = None
    if team_id:
        github_url = f"https://github.com/PMS-2026/team-{str(team_id)[:8]}"
        from app.core.supabase_client import supabase_client
        proposal = await supabase_client.get_proposal_by_team_id(team_id)
        if proposal:
            proposal_status = "completed" if proposal.get("status", "").lower() in ["approved", "submitted"] else "pending"
            proposal_file = f"proposal_{str(team_id)[:8]}.pdf"

    # Milestone 2 & 3: schedules / evaluations
    mid_status = "pending"
    final_status = "pending"
    
    if team_id:
        from app.core.supabase_client import supabase_client
        slots, evaluations, results = await asyncio.gather(
            supabase_client.get_schedule_slots_by_team(team_id),
            supabase_client.get_evaluations_by_team(team_id),
            supabase_client.get_results_by_team(team_id)
        )
        
        has_mid_eval = any(e.get("type", "").lower() == "mid" for e in evaluations) or (results and results.get("midMarks") is not None)
        has_final_eval = any(e.get("type", "").lower() == "final" for e in evaluations) or (results and results.get("finalMarks") is not None)
        
        if slots:
            mid_status = "completed" if has_mid_eval else "scheduled"
            final_status = "completed" if has_final_eval else "scheduled"

    milestones = [
        {
            "id": 1,
            "title": "Project Scope & Requirements",
            "deadline": proposal_deadline,
            "status": proposal_status,
            "github": github_url,
            "file": proposal_file,
            "commits": 12 if proposal_status == "completed" else 0,
            "lastCommit": "2 hours ago" if proposal_status == "completed" else None
        },
        {
            "id": 2,
            "title": "Mid-Term Presentation",
            "deadline": evaluation_deadline,
            "status": mid_status,
            "github": github_url if mid_status != "pending" else "",
            "file": None,
            "commits": 0,
            "lastCommit": None
        },
        {
            "id": 3,
            "title": "Final Code Submission",
            "deadline": "2026-05-10T23:59:59",
            "status": final_status,
            "github": github_url if final_status != "pending" else "",
            "file": None,
            "commits": 0,
            "lastCommit": None
        }
    ]
    return ok(data=milestones)


@router.get("/mentor")
async def get_student_mentor(
    student: Student = Depends(get_current_student)
):
    """Return the assigned mentor's details."""
    if student.team_membership and student.team_membership.team and student.team_membership.team.mentor:
        mentor = student.team_membership.team.mentor
        return ok(data={
            "id": str(mentor.id),
            "name": mentor.name,
            "department": "Computer Science and Engineering",
            "expertise": [mentor.expertise] if mentor.expertise else ["Artificial Intelligence", "Machine Learning"],
            "email": mentor.email,
            "phone": "+91-9876543210",
            "office": "Room 304, Academic Block 1",
            "availability": "Mon, Wed, Fri: 2:00 PM - 4:00 PM",
            "avatar": f"https://ui-avatars.com/api/?name={mentor.name.replace(' ', '+')}&background=random"
        })
    return ok(data=None)


@router.get("/presentations")
async def get_student_presentations(
    student: Student = Depends(get_current_student)
):
    """Return scheduled presentations and evaluation scores."""
    team_id = student.team_membership.team_id if student.team_membership else None
    if not team_id:
        return ok(data=[])

    from app.core.supabase_client import supabase_client
    slots, results = await asyncio.gather(
        supabase_client.get_schedule_slots_by_team(team_id),
        supabase_client.get_results_by_team(team_id)
    )

    presentations = []
    for idx, s in enumerate(slots):
        slot_type = "mid" if idx == 0 else "final"
        status_str = "Scheduled"
        score = None
        max_score = 30
        weightage = "30%"

        if slot_type == "mid":
            if results and results.get("midMarks") is not None:
                score = results["midMarks"]
                status_str = "Completed"
            max_score = 30
            weightage = "30%"
        elif slot_type == "final":
            if results and results.get("finalMarks") is not None:
                score = results["finalMarks"]
                status_str = "Completed"
            max_score = 50
            weightage = "50%"

        presentations.append({
            "id": str(s.get("id")),
            "title": f"{slot_type.capitalize()} Presentation",
            "status": status_str,
            "weightage": weightage,
            "date": s.get("date") or "TBD",
            "time": s.get("time") or "TBD",
            "location": s.get("room") or "TBD",
            "isOnline": s.get("room", "").lower() == "online",
            "meetingLink": s.get("meetLink") or ("https://meet.google.com/abc-defg-hij" if s.get("room", "").lower() == "online" else None),
            "panel": [s.get("panel") or "Prof. Panel Member"],
            "score": score,
            "maxScore": max_score
        })

    if results and results.get("proposalMarks") is not None:
        presentations.append({
            "id": "prop-slot",
            "title": "Proposal Presentation",
            "status": "Completed",
            "weightage": "20%",
            "date": "2026-03-15",
            "time": "10:00 AM",
            "location": "Online",
            "isOnline": True,
            "meetingLink": "https://meet.google.com/abc-defg-hij",
            "panel": ["Prof. Panel Member"],
            "score": results["proposalMarks"],
            "maxScore": 20
        })

    presentations.sort(key=lambda x: x["title"])
    return ok(data=presentations)


@router.get("/evaluations")
async def get_student_evaluations(
    student: Student = Depends(get_current_student)
):
    """Return detailed evaluation progress and metrics."""
    team_id = student.team_membership.team_id if student.team_membership else None
    if not team_id:
        return ok(data={"currentScore": 0, "maxPossibleSoFar": 0, "status": "Released", "parameters": []})

    from app.core.supabase_client import supabase_client
    results = await supabase_client.get_results_by_team(team_id)

    current_score = 0
    max_possible = 0
    parameters = []
    
    if results:
        if results.get("proposalMarks") is not None:
            parameters.append({
                "title": "Proposal Evaluation",
                "maxMarks": 20,
                "obtained": results["proposalMarks"]
            })
            current_score += results["proposalMarks"]
            max_possible += 20
        if results.get("midMarks") is not None:
            parameters.append({
                "title": "Mid-Term Evaluation",
                "maxMarks": 30,
                "obtained": results["midMarks"]
            })
            current_score += results["midMarks"]
            max_possible += 30
        if results.get("finalMarks") is not None:
            parameters.append({
                "title": "Final Evaluation",
                "maxMarks": 50,
                "obtained": results["finalMarks"]
            })
            current_score += results["finalMarks"]
            max_possible += 50

    return ok(data={
        "currentScore": current_score,
        "maxPossibleSoFar": max_possible,
        "status": "Released" if parameters else "Pending",
        "parameters": parameters
    })


@router.get("/results")
async def get_student_results(
    student: Student = Depends(get_current_student)
):
    """Return overall results and grading breakdown."""
    team_id = student.team_membership.team_id if student.team_membership else None
    if not team_id:
        return ok(data=None)

    from app.core.supabase_client import supabase_client
    results = await supabase_client.get_results_by_team(team_id)

    if not results:
        return ok(data=None)

    total_score = results.get("totalScore") or 0
    grade = "F"
    if total_score >= 90:
        grade = "A+"
    elif total_score >= 80:
        grade = "A"
    elif total_score >= 70:
        grade = "B"
    elif total_score >= 60:
        grade = "C"

    breakdown = [
        { "presentation": "Proposal Marks", "weightage": "20%", "rawScore": f"{results.get('proposalMarks') or 0}/20", "weightedScore": results.get('proposalMarks') or 0 },
        { "presentation": "Mid-Term Marks", "weightage": "30%", "rawScore": f"{results.get('midMarks') or 0}/30", "weightedScore": results.get('midMarks') or 0 },
        { "presentation": "Final Marks", "weightage": "50%", "rawScore": f"{results.get('finalMarks') or 0}/50", "weightedScore": results.get('finalMarks') or 0 }
    ]

    return ok(data={
        "overallScore": total_score,
        "maxTotalScore": 100,
        "grade": grade,
        "status": "Finalized",
        "breakdown": breakdown
    })


@router.get("/problem-statements")
async def get_problem_statements(
    student: Student = Depends(get_current_student)
):
    """Return available project problem statements."""
    store = _read_store()
    return ok(data=store.get("problem_statements", []))


@router.get("/preferences")
async def get_preferences(
    student: Student = Depends(get_current_student)
):
    """Return saved topic preferences for this student."""
    store = _read_store()
    student_id_str = str(student.id)
    prefs = store.get("preferences", {}).get(student_id_str, [])
    return ok(data=prefs)


@router.post("/preferences")
async def save_preferences(
    payload: list,
    student: Student = Depends(get_current_student)
):
    """Save selected topic preferences."""
    store = _read_store()
    student_id_str = str(student.id)
    if "preferences" not in store:
        store["preferences"] = {}
    store["preferences"][student_id_str] = payload
    _write_store(store)
    return ok(message="Preferences saved successfully")


@router.get("/extra-activities")
async def get_extra_activities(
    student: Student = Depends(get_current_student)
):
    """Return submitted extra-curricular activities."""
    store = _read_store()
    student_id_str = str(student.id)
    activities = store.get("extra_activities", {}).get(student_id_str, [])
    return ok(data=activities)


@router.post("/extra-activities")
async def add_extra_activity(
    payload: ExtraActivityPayload,
    student: Student = Depends(get_current_student)
):
    """Submit a new extra-curricular activity for review."""
    store = _read_store()
    student_id_str = str(student.id)
    if "extra_activities" not in store:
        store["extra_activities"] = {}
    if student_id_str not in store["extra_activities"]:
        store["extra_activities"][student_id_str] = []
      
    new_act = {
        "id": int(uuid.uuid4().int >> 64) & 0xFFFFFFFF,
        "title": payload.title,
        "description": payload.description,
        "date": payload.date,
        "status": "Pending Review",
        "points": 0
    }
    store["extra_activities"][student_id_str].insert(0, new_act)
    _write_store(store)
    return ok(data=new_act, message="Activity added for review")


@router.get("/announcements")
async def get_announcements(
    student: Student = Depends(get_current_student)
):
    """Return academic announcements."""
    store = _read_store()
    return ok(data=store.get("announcements", []))


@router.get("/notifications")
async def get_notifications(
    student: Student = Depends(get_current_student)
):
    """Return student notifications."""
    store = _read_store()
    return ok(data=store.get("notifications", []))


@router.post("/proposal")
async def submit_team_proposal(
    payload: ProposalPayload,
    student: Student = Depends(get_current_student)
):
    """Submit or update team project proposal."""
    team_id = student.team_membership.team_id if student.team_membership else None
    if not team_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student is not assigned to any team."
        )

    from app.core.supabase_client import supabase_client
    try:
        # Update proposal table
        await supabase_client.save_proposal(
            team_id=team_id,
            semester_id=student.semester_id or "3rd-year-config",
            title=payload.title,
            description=payload.description
        )

        # Update teams_validation details
        await supabase_client.update_team_proposal_details(
            team_id=team_id,
            title=payload.title,
            description=payload.description,
            domain=payload.domain
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit proposal: {str(e)}"
        )

    return ok(message="Proposal submitted successfully")
