import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin
from app.repositories.panel_repo import panel_repo
from app.schemas.panel import PanelResponse, PanelCreate, PanelUpdate
from app.schemas.common import ok, err, StandardResponse

router = APIRouter(prefix="/api/admin/panels", tags=["Panel"])

@router.get("", response_model=StandardResponse[List[PanelResponse]])
async def list_panels(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=100),
    semester_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    # Base filter if semester provided
    filters = {}
    if semester_id:
        filters["semester_id"] = semester_id
        
    panels = await panel_repo.get_multi(db, skip=(page - 1) * limit, limit=limit)
    
    return ok(data=panels)

@router.post("", response_model=StandardResponse[PanelResponse])
async def create_panel(
    payload: PanelCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        panel = await panel_repo.create(db, obj_in=payload)
        return ok(data=panel)
    except Exception as e:
        return err("ACTION_FAILED", str(e), 400)

@router.patch("/{panel_id}", response_model=StandardResponse[PanelResponse])
async def update_panel(
    panel_id: uuid.UUID,
    payload: PanelUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    panel = await panel_repo.get(db, panel_id)
    if not panel:
        return err("NOT_FOUND", "Panel not found", 404)
    
    panel = await panel_repo.update(db, db_obj=panel, obj_in=payload)
    return ok(data=panel)
