import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd
import io

from app.api.deps import get_db, get_super_admin, get_current_admin
from app.schemas.result import ResultResponse, ResultOverrideRequest
from app.schemas.common import ok, err
from app.services.result_service import ResultService

router = APIRouter(prefix="/api/admin/results", tags=["Results"])


@router.post("/calculate")
async def calculate_results(
    semester_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_super_admin),
):
    if not semester_id:
        from app.repositories.semester_repo import semester_repo
        active_sem = await semester_repo.get_active(db)
        if not active_sem:
            return err("NOT_FOUND", "No active semester found", 404)
        semester_id = active_sem.id
    try:
        processed = await ResultService.calculate_results(db, semester_id)
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    return ok(
        data={"teams_processed": processed},
        message=f"Results calculated for {processed} teams",
    )


@router.get("")
async def list_results(
    semester_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    if not semester_id:
        from app.repositories.semester_repo import semester_repo
        active_sem = await semester_repo.get_active(db)
        if not active_sem:
            return ok(data=[])
        semester_id = active_sem.id
    results = await ResultService.get_all_results(db, semester_id)
    return ok(data=results)


@router.get("/export")
async def export_results(
    semester_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    if not semester_id:
        from app.repositories.semester_repo import semester_repo
        active_sem = await semester_repo.get_active(db)
        if not active_sem:
            return err("NOT_FOUND", "No active semester found", 404)
        semester_id = active_sem.id
    data = await ResultService.get_results_for_export(db, semester_id)
    if not data:
        return err("NOT_FOUND", "No result records found for this semester", 404)

    # Convert to DataFrame
    df = pd.DataFrame(data)
    
    # Drop internal IDs
    if 'team_id' in df.columns:
        df.drop(columns=['team_id'], inplace=True)

    # Renaming for export
    df.rename(columns={
        "team_name": "Team Name",
        "project_title": "Project Title",
        "proposal_score": "Proposal (20%)",
        "mid_score": "Mid-Term (30%)",
        "final_score": "Final Protocol (50%)",
        "total_score": "Aggregate Score",
        "override_reason": "Audit/Override Rationale"
    }, inplace=True)

    # Output to buffer
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Cohorts Results')
    
    output.seek(0)
    
    headers = {
        'Content-Disposition': f'attachment; filename="pms_results_{semester_id}.xlsx"'
    }
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers=headers
    )


@router.patch("/override")
async def override_result(
    payload: ResultOverrideRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_super_admin),
):
    try:
        result_row = await ResultService.override_result(
            db,
            team_id=payload.team_id,
            proposal_score=payload.proposal_score,
            mid_score=payload.mid_score,
            final_score=payload.final_score,
            total_score=payload.total_score,
            admin_id=str(admin.id),
            reason=payload.reason
        )
    except ValueError as e:
        return err("ACTION_FAILED", str(e), 400)

    return ok(data=result_row, message="Result overridden and audit logged")
