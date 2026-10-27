import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, get_current_mentor
from app.models.team import Team
from app.models.proposal import Proposal
from app.models.evaluation import Evaluation
from app.models.schedule import Schedule
from app.schemas.common import ok

router = APIRouter(prefix="/api/mentor", tags=["Mentor Portal"])


@router.get("/me")
async def get_current_mentor_profile(mentor=Depends(get_current_mentor)):
    """Return the authenticated mentor's profile."""
    return ok(data={
        "id": str(mentor.id),
        "name": mentor.name,
        "email": mentor.email,
        "expertise": mentor.expertise,
        "max_teams": mentor.max_teams,
    })


@router.get("/dashboard")
async def mentor_dashboard(
    db: AsyncSession = Depends(get_db),
    mentor=Depends(get_current_mentor),
):
    """
    Aggregated dashboard data for the logged-in mentor:
    - assigned teams count + list
    - pending proposals
    - pending evaluations (schedules without evaluations)
    """
    mentor_id = mentor.id

    # --- Assigned Teams ---
    teams_query = (
        select(Team)
        .where(Team.mentor_id == mentor_id)
        .options(
            selectinload(Team.proposals),
            selectinload(Team.members),
        )
    )
    teams_result = await db.execute(teams_query)
    teams = teams_result.scalars().all()

    teams_data = []
    for t in teams:
        latest_proposal = None
        if t.proposals:
            sorted_proposals = sorted(t.proposals, key=lambda p: p.submitted_at, reverse=True)
            lp = sorted_proposals[0]
            latest_proposal = {
                "id": str(lp.id),
                "title": lp.title,
                "status": lp.status,
                "submitted_at": lp.submitted_at.isoformat(),
            }

        teams_data.append({
            "id": str(t.id),
            "name": t.name,
            "project_title": t.project_title,
            "status": t.status,
            "member_count": len(t.members),
            "latest_proposal": latest_proposal,
        })

    # --- Pending proposals (status == 'pending') for mentor's teams ---
    team_ids = [t.id for t in teams]
    pending_proposals_count = 0
    pending_proposals = []
    if team_ids:
        pp_result = await db.execute(
            select(Proposal)
            .where(Proposal.team_id.in_(team_ids), Proposal.status == "pending")
            .order_by(Proposal.submitted_at.desc())
        )
        pending_props = pp_result.scalars().all()
        pending_proposals_count = len(pending_props)
        # Return up to 5 for the dashboard quick-actions
        for p in pending_props[:5]:
            # Find team name
            team_name = next((t.name for t in teams if t.id == p.team_id), "Unknown")
            pending_proposals.append({
                "id": str(p.id),
                "title": p.title,
                "team_name": team_name,
                "team_id": str(p.team_id),
                "submitted_at": p.submitted_at.isoformat(),
            })

    # --- Pending evaluations (schedules for mentor's teams that have no evaluation yet) ---
    pending_evaluations_count = 0
    if team_ids:
        # Count schedules that don't have a corresponding evaluation
        eval_subq = select(Evaluation.schedule_id)
        sched_result = await db.execute(
            select(func.count())
            .select_from(Schedule)
            .where(
                Schedule.team_id.in_(team_ids),
                ~Schedule.id.in_(eval_subq),
            )
        )
        pending_evaluations_count = sched_result.scalar_one()

    return ok(data={
        "mentor": {
            "name": mentor.name,
            "expertise": mentor.expertise,
        },
        "stats": {
            "assigned_teams": len(teams),
            "pending_proposals": pending_proposals_count,
            "pending_evaluations": pending_evaluations_count,
        },
        "teams": teams_data,
        "recent_proposals": pending_proposals,
    })


@router.get("/teams")
async def list_assigned_teams(
    db: AsyncSession = Depends(get_db),
    mentor=Depends(get_current_mentor),
):
    """List detailed teams assigned to the mentor."""
    mentor_id = mentor.id

    query = (
        select(Team)
        .where(Team.mentor_id == mentor_id)
        .options(
            selectinload(Team.proposals),
            selectinload(Team.members),
        )
    )
    result = await db.execute(query)
    teams = result.scalars().all()

    data = []
    for t in teams:
        latest = None
        if t.proposals:
            latest = sorted(t.proposals, key=lambda p: p.submitted_at, reverse=True)[0]

        data.append({
            "id": str(t.id),
            "name": t.name,
            "project_title": t.project_title,
            "member_count": len(t.members),
            "status": t.status,
            "github_url": f"https://github.com/Procksi-2026/team-{str(t.id)[:8]}",
            "latest_proposal": {
                "title": latest.title,
                "status": latest.status,
                "submitted_at": latest.submitted_at.isoformat(),
                "tech_stack": latest.technology_stack
            } if latest else None
        })

    return ok(data=data)


@router.get("/teams/{team_id}")
async def get_team_details(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    mentor=Depends(get_current_mentor),
):
    """Fetch all details for a specific team assigned to this mentor."""
    from fastapi import HTTPException
    
    query = (
        select(Team)
        .where(Team.id == team_id, Team.mentor_id == mentor.id)
        .options(
            selectinload(Team.members),
            selectinload(Team.proposals),
            selectinload(Team.schedules).selectinload(Schedule.evaluations),
            selectinload(Team.evaluations),
        )
    )
    result = await db.execute(query)
    team = result.scalar_one_or_none()

    if not team:
        raise HTTPException(status_code=404, detail="Team not found or not assigned to you.")

    # Sort proposals by date
    sorted_proposals = sorted(team.proposals, key=lambda p: p.submitted_at, reverse=True)
    latest_proposal = sorted_proposals[0] if sorted_proposals else None

    # Members list with names (Student model needs to be joined if needed, but for now just count/id)
    # Actually simpler to just return IDs/roles for now unless we do a join
    
    return ok(data={
        "id": str(team.id),
        "name": team.name,
        "project_title": team.project_title,
        "status": team.status,
        "github_url": f"https://github.com/Procksi-2026/team-{str(team.id)[:8]}",
        "members": [str(m.student_id) for m in team.members], # Minimal for now
        "proposal": {
            "title": latest_proposal.title if latest_proposal else team.project_title,
            "description": latest_proposal.description if latest_proposal else "",
            "tech_stack": latest_proposal.technology_stack if latest_proposal else "",
            "status": latest_proposal.status if latest_proposal else "pending",
            "submitted_at": latest_proposal.submitted_at.isoformat() if latest_proposal else None,
        },
        "schedules": [
            {
                "id": str(s.id),
                "type": s.type,
                "date": s.date.isoformat(),
                "mode": s.mode,
                "is_evaluated": len(s.evaluations) > 0
            } for s in team.schedules
        ],
        "evaluations": [
            {
                "id": str(e.id),
                "type": e.type,
                "marks": e.marks,
                "date": e.created_at.isoformat()
            } for e in team.evaluations
        ]
    })



