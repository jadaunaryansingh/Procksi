"""Validation Agent endpoints for admin-api.

Reuses the framework-agnostic record-linkage cascade (app/validators) and wires it
to admin-api's Supabase-backed `students` table. In this schema the roll number is
the `students.id` column (text), so we map id <-> the validator's `student_id`.
"""
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.validators.roster_validator import RosterConfig, RosterValidator


class ValidateRequest(BaseModel):
    rows: list[dict[str, Any]]


class SaveSelectedRequest(BaseModel):
    rows: list[dict[str, Any]]
    semester_id: Optional[str] = None


def _roll(row: dict) -> str:
    for key in ("student_id", "id", "roll", "roll_number", "rollno", "university_roll_no"):
        val = row.get(key)
        if val not in (None, ""):
            return str(val).strip()
    return ""


def _to_int(value: Any, default: int) -> int:
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return default


def build_validation_router(service_client) -> APIRouter:
    router = APIRouter(prefix="/api/admin/students", tags=["Validation Agent"])
    # Roll-number formats vary in the live data (e.g. "STU-TESTING"), so we don't
    # enforce a strict pattern here — email + dedup + fuzzy matching do the work.
    validator = RosterValidator(config=RosterConfig(require_roll_pattern=False))

    @router.post("/validate")
    def validate(payload: ValidateRequest) -> dict:
        """Run the record-linkage cascade over uploaded rows vs the live roster."""
        resp = service_client.table("students").select("id,name,email").execute()
        existing = [
            {"student_id": r.get("id"), "name": r.get("name"), "email": r.get("email")}
            for r in (resp.data or [])
        ]
        rows = [
            {
                "student_id": _roll(raw),
                "name": str(raw.get("name", "")).strip(),
                "email": str(raw.get("email", "")).strip(),
                "branch": raw.get("branch"),
                "year": raw.get("year"),
                "section": raw.get("section"),
            }
            for raw in payload.rows
        ]
        return {"data": validator.validate_batch(rows, existing)}

    @router.post("/save-selected")
    def save_selected(payload: SaveSelectedRequest) -> dict:
        """Upsert the admin-approved rows into the live students table."""
        out = []
        for raw in payload.rows:
            roll = _roll(raw)
            name = str(raw.get("name", "")).strip()
            email = str(raw.get("email", "")).strip()
            if not roll or not name or not email:
                continue
            row = {
                "id": roll,
                "name": name,
                "email": email,
                "year": _to_int(raw.get("year"), 4),
                "branch": raw.get("branch") or "B.Tech CS",
                # None => no section allocated yet. Defaulting to "A" put every
                # student without a Section column into a real section.
                "section": (str(raw.get("section") or "").strip() or None),
                "status": "Active",
            }
            if payload.semester_id:
                row["semester_id"] = payload.semester_id
            out.append(row)

        if not out:
            return {"data": {"created": 0}}
        resp = service_client.table("students").upsert(out, on_conflict="id").execute()
        return {"data": {"created": len(resp.data or [])}}

    return router
