import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin
from app.services.student_service import StudentService
from app.repositories.student_repo import student_repo
from app.schemas.common import ok, paginated, err
from app.schemas.student import (
    StudentResponse,
    StudentListResponse,
    StudentStatusUpdate,
    StudentPreviewResponse,
    SaveSelectedRequest,
)

router = APIRouter(prefix="/api/admin/students", tags=["Students"])

VALID_STATUSES = {"active", "inactive", "graduated"}


@router.post("/upload")
async def upload_students(
    file: UploadFile = File(...),
    admin=Depends(get_current_admin),
):
    """
    Deprecated: Use /preview and /save instead for better control.
    """
    content = await file.read()
    try:
        rows = StudentService._parse_upload(content, file.filename or "")
    except Exception as e:
        return err("VALIDATION_ERROR", f"Could not parse file: {str(e)}")

    return ok(data={"rows": rows, "count": len(rows)}, message="File parsed successfully")


@router.post("/preview", response_model=Dict[str, Any])
async def preview_students(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    content = await file.read()
    try:
        result = await StudentService.preview_upload(db, content, file.filename or "")
    except Exception as e:
        return err("VALIDATION_ERROR", f"Could not parse file: {str(e)}")

    return ok(data=result)


@router.post("/save")
async def save_students(
    file: UploadFile = File(...),
    semester_id: uuid.UUID = Form(...),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    content = await file.read()
    try:
        created_count = await StudentService.save_upload(
            db, content, file.filename or "",
            semester_id=semester_id
        )
    except Exception as e:
        return err("ACTION_FAILED", f"Could not save students: {str(e)}")

    return ok(data={"created": created_count}, message=f"{created_count} students saved")


@router.post("/save-selected")
async def save_selected_students(
    payload: SaveSelectedRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Persist the admin-approved rows from a /preview run (clean + accepted review)."""
    try:
        created_count = await StudentService.save_selected(
            db, payload.rows, semester_id=payload.semester_id
        )
    except ValueError as e:
        return err("VALIDATION_ERROR", str(e))
    except Exception as e:
        return err("ACTION_FAILED", f"Could not save students: {str(e)}")

    return ok(data={"created": created_count}, message=f"{created_count} students saved")


@router.get("", response_model=Dict[str, Any])
async def list_students(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    year: Optional[int] = None,
    branch: Optional[str] = None,
    section: Optional[str] = None,
    status: Optional[str] = None,
    semester_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    skip = (page - 1) * limit
    students, total = await StudentService.get_students_with_count(
        db, skip=skip, limit=limit,
        year=year, branch=branch, section=section,
        status=status, semester_id=semester_id, search=search
    )

    return paginated(
        data=[StudentResponse.model_validate(s).model_dump() for s in students],
        page=page,
        limit=limit,
        total=total,
    )


@router.patch("/{student_id}/status")
async def update_student_status(
    student_id: uuid.UUID,
    payload: StudentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    if payload.status not in VALID_STATUSES:
        return err("VALIDATION_ERROR", f"Invalid status. Must be one of: {VALID_STATUSES}")

    student = await student_repo.get(db, student_id)
    if not student:
        return err("NOT_FOUND", "Student not found", 404)

    updated_student = await student_repo.update(db, db_obj=student, obj_in={"status": payload.status})

    return ok(
        data={"id": updated_student.id, "status": updated_student.status},
        message="Student status updated",
    )
