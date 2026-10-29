"""
Pydantic Models for Database Tables
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


# Project models removed - data now stored in Team model


class AnalysisJobBase(BaseModel):
    """Base analysis job model"""
    team_id: UUID  # Changed from project_id
    status: str = "queued"  # queued, running, completed, failed
    progress: int = 0
    current_stage: Optional[str] = None


class AnalysisJobCreate(AnalysisJobBase):
    """Model for creating a new analysis job"""
    pass


class AnalysisJob(AnalysisJobBase):
    """Full analysis job model"""
    id: UUID
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class TechStack(BaseModel):
    """Tech stack model"""
    id: UUID
    team_id: UUID  # Changed from project_id
    technology: str
    category: Optional[str] = None  # language, framework, database, tool
    
    class Config:
        from_attributes = True


class Issue(BaseModel):
    """Issue/warning model"""
    id: UUID
    team_id: UUID  # Changed from project_id
    type: str  # security, quality, plagiarism
    severity: str  # high, medium, low
    file_path: Optional[str] = None
    description: str
    ai_probability: Optional[float] = None
    plagiarism_score: Optional[float] = None
    
    class Config:
        from_attributes = True


class TeamMember(BaseModel):
    """Team member model"""
    id: UUID
    team_id: UUID  # Changed from project_id
    name: str
    commits: int
    contribution_pct: Optional[float] = None
    
    class Config:
        from_attributes = True


# ProjectWithDetails removed - use TeamWithDetails instead


# ==================== NEW MODELS FOR BATCH SYSTEM ====================

class BatchBase(BaseModel):
    """Base batch model"""
    name: str = Field(..., description="Batch name (e.g., '4th Sem 2024')")
    program: Optional[str] = Field(None, description="Program/department (e.g., 'AI/ML')")
    semester: str = Field(..., description="Semester (e.g., '4th Sem', '6th Sem')")
    year: int = Field(..., description="Year (e.g., 2024)")
    start_date: datetime
    end_date: datetime
    status: str = Field("active", description="active, archived, upcoming")


class BatchCreate(BatchBase):
    """Model for creating a new batch"""
    pass


class BatchUpdate(BaseModel):
    """Model for updating a batch"""
    name: Optional[str] = None
    program: Optional[str] = None
    semester: Optional[str] = None
    year: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None


class Batch(BatchBase):
    """Full batch model"""
    id: UUID
    team_count: int = 0
    student_count: int = 0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TeamBase(BaseModel):
    """Base team model"""
    batch_id: UUID
    team_name: str
    repo_url: Optional[str] = None  # GitHub repository URL
    mentor_id: Optional[UUID] = None
    description: Optional[str] = None


class TeamCreate(TeamBase):
    """Model for creating a new team"""
    pass


class TeamUpdate(BaseModel):
    """Model for updating a team"""
    team_name: Optional[str] = None
    repo_url: Optional[str] = None
    mentor_id: Optional[UUID] = None
    health_status: Optional[str] = None
    risk_flags: Optional[List[str]] = None
    status: Optional[str] = None  # Analysis status


class Team(TeamBase):
    """Full team model with analysis fields"""
    id: UUID
    student_count: int = 0
    
    # Analysis Status
    status: str = "pending"  # pending, analyzing, completed, failed
    
    # Analysis Scores (0-100)
    total_score: Optional[float] = None
    quality_score: Optional[float] = None
    security_score: Optional[float] = None
    originality_score: Optional[float] = None
    architecture_score: Optional[float] = None
    documentation_score: Optional[float] = None
    effort_score: Optional[float] = None
    implementation_score: Optional[float] = None
    engineering_score: Optional[float] = None
    organization_score: Optional[float] = None
    
    # Analysis Metadata
    total_commits: Optional[int] = None
    verdict: Optional[str] = None
    ai_pros: Optional[List[str]] = None
    ai_cons: Optional[List[str]] = None
    report_json: Optional[Dict[str, Any]] = None
    report_path: Optional[str] = None
    viz_path: Optional[str] = None
    
    # Health Tracking
    health_status: str = "on_track"  # on_track, at_risk, critical
    risk_flags: Optional[List[str]] = []
    last_activity: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    analyzed_at: Optional[datetime] = None
    last_analyzed_at: Optional[datetime] = None
    
    # Flexible Metadata
    metadata: Optional[Dict[str, Any]] = {}
    
    class Config:
        from_attributes = True


class StudentBase(BaseModel):
    """Base student model"""
    team_id: UUID
    name: str
    email: Optional[str] = None
    github_username: Optional[str] = None


class StudentCreate(StudentBase):
    """Model for creating a new student"""
    pass


class StudentUpdate(BaseModel):
    """Model for updating a student"""
    name: Optional[str] = None
    email: Optional[str] = None
    github_username: Optional[str] = None
    contribution_score: Optional[float] = None
    commit_count: Optional[int] = None
    lines_added: Optional[int] = None
    lines_deleted: Optional[int] = None
    last_commit_date: Optional[datetime] = None
    grading_details: Optional[Dict[str, Any]] = None


class Student(StudentBase):
    """Full student model"""
    id: UUID
    contribution_score: float = 0
    commit_count: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    last_commit_date: Optional[datetime] = None
    grading_details: Optional[Dict[str, Any]] = {}
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class MentorTeamAssignmentBase(BaseModel):
    """Base mentor assignment model"""
    mentor_id: UUID
    team_id: UUID
    batch_id: UUID


class MentorTeamAssignmentCreate(MentorTeamAssignmentBase):
    """Model for creating a mentor assignment"""
    assigned_by: Optional[UUID] = None


class MentorTeamAssignment(MentorTeamAssignmentBase):
    """Full mentor assignment model"""
    id: UUID
    assigned_at: datetime
    assigned_by: Optional[UUID] = None
    
    class Config:
        from_attributes = True


class UserProfile(BaseModel):
    """User profile model from Supabase Auth"""
    id: UUID
    email: str
    role: str  # admin, mentor
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    # Mentor activity tracking fields
    last_login: Optional[datetime] = None
    last_logout: Optional[datetime] = None
    is_online: Optional[bool] = None
    total_time_spent: Optional[str] = None  # ISO 8601 duration string (maps to INTERVAL)

    class Config:
        from_attributes = True


# ==================== EXTENDED MODELS WITH RELATIONS ====================

class TeamWithDetails(Team):
    """Team with students and analysis data"""
    students: List[Student] = []
    mentor: Optional[UserProfile] = None
    tech_stack: List[TechStack] = []
    issues: List[Issue] = []
    team_members: List[TeamMember] = []


class BatchWithTeams(Batch):
    """Batch with teams"""
    teams: List[Team] = []


class BatchWithStats(Batch):
    """Batch with statistics"""
    avg_score: Optional[float] = None
    completed_projects: int = 0
    pending_projects: int = 0
    at_risk_teams: int = 0


class PaginatedResponse(BaseModel):
    """Generic paginated response"""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


class TeamList(BaseModel):
    """List of teams with pagination"""
    teams: List[Team]
    total: int
    page: int
    page_size: int
    total_pages: int

