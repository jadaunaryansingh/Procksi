from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    panel_id: str | None = None
    role: str | None = None
    mentor_name: str | None = None


class UserPublic(BaseModel):
    email: EmailStr
    role: str
    panel_id: str | None = None
    mentor_name: str | None = None

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    password: str
    domains: list[str] = []



class PanelDashboardResponse(BaseModel):
    """GET /panel/{panel_id}/dashboard — PDF contract + UI helpers."""

    assigned_round: str
    total_teams: int
    active_slot: str | None
    system_time: str

    evaluated_count: int = 0
    pending_count: int = 0
    completed_count: int = 0
    progress_fraction: float = 0.0

    active_slot_detail: dict[str, Any] | None = None
    next_up: dict[str, Any] | None = None


class TeamSlotRow(BaseModel):
    """GET /panel/{panel_id}/teams — PDF-style + names for UI."""

    team_id: int
    slot: str
    status: str
    team_name: str | None = None
    project_title: str | None = None
    venue: str | None = None
    meet_link: str | None = None
    semester_id: str | None = None


class TeamCatalogRow(BaseModel):
    team_id: int
    team_name: str
    project_title: str | None = None
    current_slot: str | None = None
    current_status: str | None = None
    venue: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    semester_id: str | None = None


class MissedRow(BaseModel):
    team_id: int
    team_name: str
    slot: str
    status: str
    semester_id: str | None = None


class AlertRow(BaseModel):
    """PDF: alerts / reminders / admin notifications."""

    id: int
    alert_type: str
    title: str
    body: str | None
    team_id: int | None
    created_at: datetime
    acknowledged_at: datetime | None = None


class GitHubDataRow(BaseModel):
    """PDF: github_data — repo metrics for a team assigned to this panel."""

    team_id: int
    repository_url: str | None = None
    default_branch: str | None = None
    open_pull_requests: int | None = None
    commit_count_30d: int | None = None
    last_commit_at: datetime | None = None
    raw_json: str | None = None


class RubricCriterion(BaseModel):
    name: str
    max_marks: int


class RubricSection(BaseModel):
    category: str
    criteria: list[RubricCriterion]


class CycleRubrics(BaseModel):
    id: str
    title: str
    type: str
    weightage: int
    rubrics: list[RubricSection]
    total_maximum: int


class SemesterRubrics(BaseModel):
    id: str
    academic_year: str
    semester_type: str
    branch: str
    academic_level: str
    cycles: list[CycleRubrics]


class EvaluationParametersResponse(BaseModel):
    sections: list[RubricSection]
    total_maximum: int
    locked: bool = True
    semesters: list[SemesterRubrics] | None = None


class EvaluationSessionResponse(BaseModel):
    team_id: int
    team_name: str
    project_title: str | None
    allow_submission: bool
    slot_label: str
    window_start: datetime
    window_end: datetime
    server_now: datetime
    evaluation_timer_seconds: int
    remaining_seconds: int = 0
    already_submitted: bool
    receipt_id: str | None = None
    semester_id: str | None = None


class DraftPayload(BaseModel):
    scores: dict[str, int | str] = Field(default_factory=dict)
    remarks: str = ""


class SubmitEvaluationRequest(BaseModel):
    panel_id: str
    team_id: int
    scores: dict[str, int | str]
    remarks: str


class SubmitEvaluationResponse(BaseModel):
    receipt_id: str
    panel_id: str
    team_id: int
    submitted_at: datetime
    final_score_normalized: int
