"""
Mentor API routes — admin-scoped endpoints for mentor management.

Endpoints:
  GET   /api/admin/mentors                     — list mentors (paginated)
  POST  /api/admin/mentor/assign               — manually assign mentor
  PATCH /api/admin/mentor/change               — change assigned mentor
  GET   /api/admin/mentors/recommend/{team_id} — get AI recommendations
  POST  /api/admin/mentors/auto-assign         — AI-powered bulk auto-assignment
"""

import uuid
import logging
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin
from app.schemas.mentor import MentorAssignRequest, MentorChangeRequest, MentorResponse
from app.schemas.common import ok, err, paginated
from app.services.mentor_service import MentorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Mentors"])


# ═══════════════════════════════════════════════════════════════════════════
#  REQUEST / RESPONSE SCHEMAS (auto-assign specific)
# ═══════════════════════════════════════════════════════════════════════════

class AutoAssignRequest(BaseModel):
    """Optional body for the auto-assign endpoint."""
    generate_explanations: bool = False
    mode: Literal["rule_only", "hybrid"] = "rule_only"


# ═══════════════════════════════════════════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/mentors")
async def list_mentors(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    skip = (page - 1) * limit
    mentors = await MentorService.get_mentors(db, skip=skip, limit=limit)
    total = await MentorService.count_mentors(db)

    # Get loads in a single query
    from sqlalchemy import select, func
    from app.models.team import Team
    load_query = select(Team.mentor_id, func.count()).where(Team.mentor_id.is_not(None)).group_by(Team.mentor_id)
    load_result = await db.execute(load_query)
    load_map = {str(row[0]): row[1] for row in load_result.all()}

    return paginated(
        data=[
            {
                "id": str(m.id),
                "name": m.name,
                "email": m.email,
                "expertise": m.expertise,
                "skills": m.skills,
                "domains": m.domains,
                "experience_years": m.experience_years,
                "current_load": load_map.get(str(m.id), 0),
                "max_load": getattr(m, 'max_teams', 3),
            }
            for m in mentors
        ],
        page=page,
        limit=limit,
        total=total,
    )


@router.post("/mentor/assign")
async def assign_mentor(
    payload: MentorAssignRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        team = await MentorService.assign_mentor(db, payload.mentor_id, payload.team_id)
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    return ok(
        data={"team_id": team.id, "mentor_id": team.mentor_id},
        message="Mentor assigned successfully",
    )


@router.patch("/mentor/change")
async def change_mentor(
    payload: MentorChangeRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        team = await MentorService.assign_mentor(db, payload.new_mentor_id, payload.team_id)
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    return ok(
        data={"team_id": team.id, "mentor_id": team.mentor_id},
        message="Mentor changed successfully",
    )


@router.get("/mentors/recommend/{team_id}")
async def recommend_mentors(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        recommendations = await MentorService.get_recommendations(db, team_id)
        return ok(data=recommendations)
    except ValueError as e:
        return err("NOT_FOUND", str(e), 404)


@router.post("/mentors/auto-assign")
async def auto_assign_mentors(
    body: Optional[AutoAssignRequest] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    AI-powered auto-assignment of mentors to unassigned teams.

    Uses a **hybrid matching engine**:
      - Rule-Based Score  (60 %) — domain, skills, experience, availability
      - AI Similarity     (40 %) — cosine similarity via NVIDIA NIM embeddings

    Triggered from the Admin Portal's "Auto-Assign Pending" button.

    Example response:
    ```json
    {
      "success": true,
      "data": {
        "assignments": [
          {
            "team_id": "a1b2c3d4-...",
            "team_name": "Team Alpha",
            "project_title": "Smart Irrigation System",
            "mentor_id": "e5f6g7h8-...",
            "mentor_name": "Dr. Alice Smith",
            "scores": {
              "hybrid_score": 0.8234,
              "rule_based_score": 0.7500,
              "ai_similarity_score": 0.9351
            },
            "explanation": "Dr. Smith's expertise in IoT and embedded systems
                           directly aligns with the project's smart irrigation
                           focus. Her 10+ years of experience in sensor networks
                           makes her an ideal mentor."
          }
        ],
        "count": 1,
        "stats": {
          "total_unassigned": 5,
          "assigned": 4,
          "skipped": 1
        }
      },
      "message": "Successfully assigned 4 mentor(s) to teams."
    }
    ```
    """
    logger.info("Auto-assign endpoint triggered by admin")

    generate_explanations = body.generate_explanations if body else False
    mode = body.mode if body else "rule_only"

    result = await MentorService.auto_assign_mentors(
        db,
        generate_explanations=generate_explanations,
        mode=mode,
    )

    if not result["success"]:
        return err("AUTO_ASSIGN_FAILED", result["message"], 400)

    return ok(
        data={
            "assignments": result["assignments"],
            "count": len(result["assignments"]),
            "stats": result.get("stats", {}),
        },
        message=result["message"],
    )
