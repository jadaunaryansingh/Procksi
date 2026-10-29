"""
API Request and Response Schemas
"""
from pydantic import BaseModel, Field, HttpUrl, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


# ==================== Request Schemas ====================

class AnalyzeRepoRequest(BaseModel):
    """Request to analyze a repository"""
    repo_url: str = Field(..., description="GitHub repository URL")
    team_name: Optional[str] = Field(None, description="Team or project name")
    
    @validator('repo_url')
    def validate_repo_url(cls, v):
        """Validate that URL is a proper GitHub URL"""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('repo_url must start with http:// or https://')
        if 'github.com' not in v.lower():
            raise ValueError('Only GitHub repositories are supported')
        return v


class BatchUploadRequest(BaseModel):
    """Request to analyze multiple repositories"""
    repos: List[AnalyzeRepoRequest] = Field(..., min_items=1, max_items=50)


# Project filter params removed - use team filtering instead


class LeaderboardParams(BaseModel):
    """Query parameters for leaderboard"""
    sort_by: str = Field("total_score", description="Field to sort by")
    order: str = Field("desc", description="asc or desc")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    status: Optional[str] = Field("completed", description="Filter by status")


# ==================== Response Schemas ====================

class AnalyzeRepoResponse(BaseModel):
    """Response from analyze-repo endpoint"""
    job_id: UUID
    team_id: UUID  # Changed from project_id
    status: str
    message: str = "Analysis queued successfully"


class BatchUploadResponse(BaseModel):
    """Response from batch-upload endpoint"""
    jobs: List[AnalyzeRepoResponse]
    total: int
    message: str


class AnalysisStatusResponse(BaseModel):
    """Response for analysis status"""
    job_id: UUID
    team_id: UUID  # Changed from project_id
    status: str  # queued, running, completed, failed
    progress: int  # 0-100
    current_stage: Optional[str] = None
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        # Allow response to use camelCase for frontend
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "job_id": "123e4567-e89b-12d3-a456-426614174000",
                "team_id": "987fcdeb-51a2-43f1-b9e5-ac4c5d6e7890",
                "status": "running",
                "progress": 45,
                "current_stage": "security_scan",
                "error_message": None,
                "started_at": "2024-01-09T10:30:00",
                "completed_at": None
            }
        }


class AnalysisJobListItem(BaseModel):
    """Analysis job list item"""
    job_id: Optional[UUID] = None
    team_id: UUID  # Changed from project_id
    repo_url: str
    team_name: Optional[str] = None
    status: str
    progress: int
    current_stage: Optional[str] = None
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    last_analyzed_at: Optional[datetime] = None


class AnalysisJobListResponse(BaseModel):
    """Response for analysis job list"""
    jobs: List[AnalysisJobListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class LanguageBreakdown(BaseModel):
    """Language usage breakdown"""
    name: str
    percentage: float


class ContributorDetail(BaseModel):
    """Detailed contributor information"""
    name: str
    commits: int
    additions: int = 0
    deletions: int = 0
    percentage: float


class CommitPattern(BaseModel):
    """Commit pattern over time"""
    date: str
    commits: int
    additions: int = 0
    deletions: int = 0


class SecurityIssue(BaseModel):
    """Security issue with enhanced details"""
    type: str
    severity: str
    file: str
    line: Optional[int] = None
    description: str


class AIAnalysis(BaseModel):
    """AI analysis results"""
    aiGeneratedPercentage: float
    aiVerdict: Optional[str] = None
    strengths: List[str] = []
    improvements: List[str] = []
    deletions: int = 0


class ScoreBreakdown(BaseModel):
    """Score breakdown"""
    total_score: Optional[float] = None
    originality_score: Optional[float] = None
    quality_score: Optional[float] = None
    security_score: Optional[float] = None
    effort_score: Optional[float] = None
    implementation_score: Optional[float] = None
    engineering_score: Optional[float] = None
    organization_score: Optional[float] = None
    documentation_score: Optional[float] = None
    architecture_score: Optional[float] = None
    llm_score: Optional[float] = None  # Maps to originality


class TechStackItem(BaseModel):
    """Tech stack item"""
    technology: str
    category: Optional[str] = None


class IssueItem(BaseModel):
    """Issue item"""
    type: str
    severity: str
    file_path: Optional[str] = None
    description: str
    ai_probability: Optional[float] = None
    plagiarism_score: Optional[float] = None


class TeamMemberItem(BaseModel):
    """Team member item"""
    name: str
    commits: int
    contribution_pct: Optional[float] = None


class AnalysisResultResponse(BaseModel):
    """Full analysis result"""
    team_id: UUID  # Changed from project_id
    repo_url: str
    team_name: Optional[str] = None
    status: str
    analyzed_at: Optional[datetime] = None
    
    # Scores
    scores: ScoreBreakdown
    
    # Details
    total_commits: Optional[int] = None
    verdict: Optional[str] = None
    ai_pros: Optional[str] = None
    ai_cons: Optional[str] = None
    
    # Related data
    tech_stack: List[TechStackItem] = []
    issues: List[IssueItem] = []
    team_members: List[TeamMemberItem] = []
    
    # Visualization
    viz_url: Optional[str] = None
    
    # Full report
    report_json: Optional[Dict[str, Any]] = None


# Project list/detail schemas removed - use Team schemas instead


class LeaderboardItem(BaseModel):
    """Leaderboard item"""
    rank: int
    id: UUID
    repo_url: str
    team_name: Optional[str] = None
    total_score: float
    originality_score: Optional[float] = None
    quality_score: Optional[float] = None
    security_score: Optional[float] = None
    implementation_score: Optional[float] = None
    verdict: Optional[str] = None
    analyzed_at: Optional[datetime] = None


class LeaderboardResponse(BaseModel):
    """Response for leaderboard"""
    leaderboard: List[LeaderboardItem]
    total: int
    page: int
    page_size: int


# ProjectDetailResponse removed - use TeamDetailResponse instead


class StatsResponse(BaseModel):
    """Dashboard statistics response"""
    totalProjects: int
    completedProjects: int
    pendingProjects: int
    averageScore: float  # Note: 'average' not 'avg'
    totalSecurityIssues: int


class BatchUploadItemRequest(BaseModel):
    """Single item in batch upload CSV"""
    teamName: str
    repoUrl: str
    description: Optional[str] = None


# ================ Auth & Collaboration ================


class AuthUserResponse(BaseModel):
    """Authenticated user context"""
    user_id: UUID
    email: Optional[str] = None
    role: str
    full_name: Optional[str] = None


class CreateTeamRequest(BaseModel):
    """Create a new team"""
    name: str
    mentor_id: Optional[UUID] = None
    description: Optional[str] = None
    is_active: bool = True


class TeamMemberRequest(BaseModel):
    """Add a member to a team"""
    user_id: UUID
    role: str = Field("member", pattern="^(leader|member)$")


class ProjectCommentRequest(BaseModel):
    """Create a comment for a team"""
    team_id: UUID  # Changed from project_id
    comment: str
    is_private: bool = False


class ProjectCommentResponse(BaseModel):
    """Returned project comment"""
    id: UUID
    team_id: UUID  # Changed from project_id
    user_id: UUID
    comment: str
    is_private: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None


class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


# ==================== NEW SCHEMAS FOR BATCH SYSTEM ====================

# ---------- Authentication Schemas ----------

class LoginRequest(BaseModel):
    """Login request with Google ID token"""
    id_token: str = Field(..., description="Google OAuth ID token")


class LoginResponse(BaseModel):
    """Login response"""
    access_token: str
    refresh_token: str
    user: "UserProfileResponse"
    expires_in: int
    requires_onboarding: bool = False  # True when mentor has no name set yet


class UserProfileResponse(BaseModel):
    """User profile response"""
    id: UUID
    email: str
    role: str  # admin, mentor
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    is_mentor: Optional[bool] = None


class UserUpdateRequest(BaseModel):
    """Update user profile"""
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


# ---------- Batch Management Schemas ----------

class MentorRoundConfig(BaseModel):
    """Configured mentor grading round for a batch"""
    id: str
    name: str = Field(..., min_length=1, max_length=100)
    marks_out_of: int = Field(..., ge=1, le=1000)
    created_at: Optional[datetime] = None


class MentorRoundCreateRequest(BaseModel):
    """Create a single mentor grading round"""
    name: str = Field(..., min_length=1, max_length=100)
    marks_out_of: int = Field(..., ge=1, le=1000)


class MentorRoundUpdateRequest(BaseModel):
    """Update a single mentor grading round"""
    name: str = Field(..., min_length=1, max_length=100)
    marks_out_of: int = Field(..., ge=1, le=1000)


class MentorRoundListResponse(BaseModel):
    """List mentor rounds for a batch"""
    batch_id: UUID
    rounds: List[MentorRoundConfig]


class BatchCreateRequest(BaseModel):
    """Create new batch"""
    name: str = Field(..., description="Batch name (e.g., '4th Sem 2024')")
    program: Optional[str] = Field(None, description="Program/department (e.g., 'AI/ML')")
    semester: str = Field(..., description="Semester (e.g., '4th Sem')")
    year: int = Field(..., ge=2020, le=2100, description="Year")
    start_date: datetime
    end_date: datetime
    mentor_rounds: List[MentorRoundConfig] = Field(default_factory=list, description="Configured mentor grading rounds")
    
    @validator('end_date')
    def validate_dates(cls, v, values):
        if 'start_date' in values and v <= values['start_date']:
            raise ValueError('end_date must be after start_date')
        return v


class BatchUpdateRequest(BaseModel):
    """Update batch"""
    name: Optional[str] = None
    program: Optional[str] = None
    semester: Optional[str] = None
    year: Optional[int] = Field(None, ge=2020, le=2100)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = Field(None, pattern="^(active|archived|upcoming)$")
    mentor_max_marks: Optional[int] = Field(None, ge=1, le=1000, description="Maximum marks a mentor can assign per student")
    mentor_rounds: Optional[List[MentorRoundConfig]] = None


class BatchResponse(BaseModel):
    """Batch response"""
    id: UUID
    name: str
    program: Optional[str] = None
    semester: str
    year: int
    start_date: datetime
    end_date: datetime
    status: str
    team_count: int
    student_count: int
    mentor_max_marks: int = 100
    mentor_rounds: List[MentorRoundConfig] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class BatchStatsResponse(BaseModel):
    """Batch with statistics"""
    id: UUID
    name: str
    program: Optional[str] = None
    semester: str
    year: int
    start_date: datetime
    end_date: datetime
    status: str
    team_count: int
    student_count: int
    mentor_max_marks: int = 100
    mentor_rounds: List[MentorRoundConfig] = Field(default_factory=list)
    avg_score: Optional[float] = None
    completed_projects: int = 0
    pending_projects: int = 0
    at_risk_teams: int = 0
    created_at: datetime
    updated_at: datetime


class BatchListResponse(BaseModel):
    """List of batches"""
    batches: List[BatchResponse]
    total: int


# ---------- Team Management Schemas ----------

class TeamCreateRequest(BaseModel):
    """Create new team"""
    batch_id: UUID
    team_name: str = Field(..., min_length=1, max_length=255)
    project_id: Optional[UUID] = None
    mentor_id: Optional[UUID] = None


class TeamUpdateRequest(BaseModel):
    """Update team"""
    team_name: Optional[str] = Field(None, min_length=1, max_length=255)
    project_id: Optional[UUID] = None
    mentor_id: Optional[UUID] = None
    health_status: Optional[str] = Field(None, pattern="^(on_track|at_risk|critical)$")
    risk_flags: Optional[List[str]] = None


class TeamResponse(BaseModel):
    """Team response with analysis fields"""
    id: UUID
    batch_id: UUID
    team_name: str
    repo_url: Optional[str] = None
    mentor_id: Optional[UUID] = None
    student_count: int
    
    # Analysis Status
    status: str = "pending"
    
    # Analysis Scores
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
    health_status: str
    risk_flags: List[str]
    last_activity: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    analyzed_at: Optional[datetime] = None
    last_analyzed_at: Optional[datetime] = None


class TeamWithDetailsResponse(BaseModel):
    """Team with students and analysis data"""
    id: UUID
    batch_id: UUID
    team_name: str
    repo_url: Optional[str] = None
    mentor_id: Optional[UUID] = None
    student_count: int
    
    # Analysis fields
    status: str = "pending"
    total_score: Optional[float] = None
    quality_score: Optional[float] = None
    security_score: Optional[float] = None
    analyzed_at: Optional[datetime] = None
    
    # Health
    health_status: str
    risk_flags: List[str]
    last_activity: Optional[datetime] = None
    
    # Related data
    students: List["StudentResponse"] = []
    mentor: Optional[UserProfileResponse] = None
    
    created_at: datetime
    updated_at: datetime


class SimpleTeamListResponse(BaseModel):
    """Simple list of teams (non-paginated) - used for dropdowns etc."""
    teams: List[TeamResponse]
    total: int


# ---------- Student Schemas ----------

class StudentCreateRequest(BaseModel):
    """Create new student"""
    team_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(None, pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    github_username: Optional[str] = None


class StudentUpdateRequest(BaseModel):
    """Update student"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    github_username: Optional[str] = None


class StudentResponse(BaseModel):
    """Student response"""
    id: UUID
    team_id: UUID
    name: str
    email: Optional[str] = None
    github_username: Optional[str] = None
    contribution_score: float
    commit_count: int
    lines_added: int
    lines_deleted: int
    last_commit_date: Optional[datetime] = None
    grading_details: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class StudentListResponse(BaseModel):
    """List of students"""
    students: List[StudentResponse]
    total: int


# ---------- Mentor Assignment Schemas ----------


class StudentGradeRequest(BaseModel):
    """Request to grade a student"""
    student_id: UUID
    admin_grade: Optional[float] = Field(None, ge=0, le=100)
    admin_feedback: Optional[str] = None
    grading_details: Optional[Dict[str, Any]] = None


class MentorAssignmentCreateRequest(BaseModel):
    """Assign mentor to team"""
    mentor_id: UUID
    team_id: UUID
    batch_id: UUID


class MentorAssignmentResponse(BaseModel):
    """Mentor assignment response"""
    id: UUID
    mentor_id: UUID
    team_id: UUID
    batch_id: UUID
    assigned_at: datetime
    assigned_by: Optional[UUID] = None


class MentorAssignmentListResponse(BaseModel):
    """List of mentor assignments"""
    assignments: List[MentorAssignmentResponse]
    total: int


# ---------- Admin Dashboard Schemas ----------

class AdminDashboardStatsResponse(BaseModel):
    """Admin dashboard statistics"""
    total_teams: int
    total_students: int
    total_projects: int
    avg_score: Optional[float] = None
    completed_projects: int
    pending_projects: int
    at_risk_teams: int
    critical_teams: int


class AdminTeamListItem(BaseModel):
    """Team item for admin dashboard"""
    id: UUID
    team_name: str
    project_id: Optional[UUID] = None
    student_count: int
    health_status: str
    risk_flags: List[str]
    total_score: Optional[float] = None
    mentor_name: Optional[str] = None


class AdminBatchOverviewResponse(BaseModel):
    """Batch overview for admin"""
    batch: BatchStatsResponse
    teams: List[AdminTeamListItem]
    recent_activity: List["ActivityLogResponse"] = []


# ---------- Mentor Dashboard Schemas ----------

class MentorDashboardStatsResponse(BaseModel):
    """Mentor dashboard statistics"""
    assigned_teams: int
    total_students: int
    avg_team_score: Optional[float] = None
    at_risk_teams: int
    pending_reviews: int


class MentorTeamListItem(BaseModel):
    """Team item for mentor dashboard"""
    id: UUID
    team_name: str
    batch_name: str
    student_count: int
    health_status: str
    total_score: Optional[float] = None
    last_activity: Optional[datetime] = None


class MentorDashboardResponse(BaseModel):
    """Mentor dashboard data"""
    stats: MentorDashboardStatsResponse
    teams: List[MentorTeamListItem]


# ---------- Analytics Schemas ----------

class HealthStatusDistribution(BaseModel):
    """Health status distribution"""
    on_track: int
    at_risk: int
    critical: int


class RiskFlagAnalysis(BaseModel):
    """Risk flag analysis"""
    flag: str
    count: int
    percentage: float


class BatchAnalyticsResponse(BaseModel):
    """Batch analytics"""
    batch_id: UUID
    batch_name: str
    health_distribution: HealthStatusDistribution
    risk_flags: List[RiskFlagAnalysis]
    avg_score: Optional[float] = None
    score_distribution: Dict[str, int]  # score ranges
    top_teams: List[AdminTeamListItem]
    bottom_teams: List[AdminTeamListItem]


class TeamAnalyticsResponse(BaseModel):
    """Team analytics"""
    team_id: UUID
    team_name: str
    health_status: str
    risk_flags: List[str]
    contributors: List["StudentContribution"]
    commit_timeline: List["CommitDataPoint"]
    score_breakdown: ScoreBreakdown


class FileTypeStat(BaseModel):
    """File type usage statistic"""
    name: str
    count: int


class StudentContribution(BaseModel):
    """Student contribution data"""
    student_id: Optional[UUID] = None
    name: str
    email: Optional[str] = None
    commits: int = Field(alias="commit_count")
    additions: int = Field(alias="lines_added")
    deletions: int = Field(alias="lines_deleted")
    percentage: float = Field(alias="contribution_percentage")
    active_days: Optional[int] = Field(None, alias="activeDays")
    avg_commits_per_day: Optional[float] = Field(None, alias="avgCommitsPerDay")
    top_file_types: List[FileTypeStat] = Field(default_factory=list, alias="topFileTypes")
    last_active: Optional[str] = Field(None, alias="lastActive")
    streak: Optional[int] = 0
    contribution_data: List[Dict[str, Any]] = Field(default_factory=list, alias="contributionData")

    class Config:
        allow_population_by_field_name = True


class CommitDataPoint(BaseModel):
    """Commit data point for timeline"""
    date: str
    commits: int
    contributors: int


class ActivityLogResponse(BaseModel):
    """Activity log entry"""
    id: UUID
    batch_id: Optional[UUID] = None
    team_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    action: str
    description: str
    timestamp: datetime


# ---------- Report Generation Schemas ----------

class GenerateReportRequest(BaseModel):
    """Generate report request"""
    batch_id: Optional[UUID] = None
    team_id: Optional[UUID] = None
    format: str = Field("pdf", pattern="^(pdf|csv|json)$")
    include_details: bool = True


class ReportResponse(BaseModel):
    """Report response"""
    report_id: UUID
    format: str
    download_url: str
    generated_at: datetime
    expires_at: Optional[datetime] = None


# ==================== Team Management Schemas ====================

class StudentCreateRequest(BaseModel):
    """Student data for team creation"""
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    github_username: Optional[str] = Field(None, max_length=255)


class TeamCreateRequest(BaseModel):
    """Create team request"""
    batch_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    repo_url: Optional[str] = None
    description: Optional[str] = None
    students: Optional[List[StudentCreateRequest]] = None
    
    @validator('repo_url')
    def validate_repo_url(cls, v):
        if v and 'github.com' not in v.lower():
            raise ValueError('Only GitHub repositories are supported')
        return v


class StudentUpdateItem(BaseModel):
    """Update a single student within a team"""
    id: UUID
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    github_username: Optional[str] = Field(None, max_length=255)


class NewStudentItem(BaseModel):
    """Add a new student to a team"""
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(None, pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    github_username: Optional[str] = Field(None, max_length=255)


class TeamUpdateRequest(BaseModel):
    """Update team request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    repo_url: Optional[str] = None
    repo_urls: Optional[List[str]] = None
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|inactive|archived)$")
    health_status: Optional[str] = Field(None, pattern="^(on_track|at_risk|critical)$")
    risk_flags: Optional[List[str]] = None
    students: Optional[List[StudentUpdateItem]] = None
    new_students: Optional[List[NewStudentItem]] = None
    delete_student_ids: Optional[List[UUID]] = None

    @validator('repo_url')
    def validate_repo_url(cls, v):
        if v and 'github.com' not in v.lower():
            raise ValueError('Only GitHub repositories are supported')
        return v

    @validator('repo_urls')
    def validate_repo_urls(cls, v):
        if v is None:
            return v

        cleaned_urls = []
        for url in v:
            if url is None:
                continue
            normalized = str(url).strip()
            if not normalized:
                continue
            if 'github.com' not in normalized.lower():
                raise ValueError('Only GitHub repositories are supported')
            cleaned_urls.append(normalized)
        return cleaned_urls


class TeamResponse(BaseModel):
    """Team operation response"""
    team: Dict[str, Any]
    message: str


class TeamDetailResponse(BaseModel):
    """Detailed team information"""
    id: UUID
    batch_id: UUID
    batch_name: str
    name: str
    repo_url: Optional[str] = None
    repo_urls: Optional[List[str]] = None
    description: Optional[str] = None
    status: str
    assigned_mentor_id: Optional[UUID] = None
    assigned_mentor_name: Optional[str] = None
    students: List[Dict[str, Any]]
    project_analysis: Optional[Dict[str, Any]] = None
    health_status: str
    risk_flags: List[str]
    contribution_balance: Optional[float] = None
    last_activity: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TeamListResponse(BaseModel):
    """Paginated team list response"""
    teams: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int


class BulkUploadResponse(BaseModel):
    """Bulk team upload response"""
    successful: int
    failed: int
    total: int
    errors: List[Dict[str, Any]]
    teams: List[Dict[str, Any]]
    message: str


class AnalysisJobResponse(BaseModel):
    """Analysis job response"""
    job_id: Optional[UUID] = None
    team_id: UUID  # Changed from project_id
    status: str
    message: str


class MessageResponse(BaseModel):
    """Generic message response"""
    success: bool
    message: str


# ==================== Mentor Management Schemas ====================

class MentorCreateRequest(BaseModel):
    """Create mentor request"""
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    full_name: str = Field(..., min_length=1, max_length=255)
    status: Optional[str] = Field("active", pattern="^(active|inactive)$")


class MentorUpdateRequest(BaseModel):
    """Update mentor request"""
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[str] = Field(None, pattern="^(active|inactive)$")


class MentorResponse(BaseModel):
    """Mentor operation response"""
    mentor: Dict[str, Any]
    message: str


class MentorListResponse(BaseModel):
    """Mentor list response"""
    mentors: List[Dict[str, Any]]
    total: int


class MentorDetailResponse(BaseModel):
    """Detailed mentor information"""
    id: UUID
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    status: str
    assigned_teams: List[Dict[str, Any]]
    team_count: int
    batches: List[str]
    created_at: datetime


# ==================== Assignment Management Schemas ====================

class AssignmentCreateRequest(BaseModel):
    """Assign teams to mentor request"""
    mentor_id: UUID
    team_ids: List[UUID] = Field(..., min_items=1)


class AssignmentDeleteRequest(BaseModel):
    """Unassign teams from mentor request"""
    mentor_id: UUID
    team_ids: List[UUID] = Field(..., min_items=1)


class AssignmentResponse(BaseModel):
    """Assignment operation response"""
    success: bool
    message: str
    assignments: List[Dict[str, Any]]


class TeamAssignRequest(BaseModel):
    """Assign a single team to a mentor"""
    mentor_id: UUID


# ==================== Dashboard Schemas ====================

class DashboardOverview(BaseModel):
    """Dashboard overview statistics"""
    totalTeams: int
    activeTeams: int
    inactiveTeams: int
    totalMentors: int
    totalStudents: int
    unassignedTeams: int
    analysisQueue: int


class HealthDistribution(BaseModel):
    """Team health distribution"""
    onTrack: int
    atRisk: int
    critical: int


class RecentActivityItem(BaseModel):
    """Recent activity item"""
    id: str
    type: str
    message: str
    teamName: str
    timestamp: str


class MentorWorkloadItem(BaseModel):
    """Mentor workload statistics"""
    mentorId: str
    mentorName: str
    assignedTeams: int
    onTrack: int
    atRisk: int


class AdminDashboardResponse(BaseModel):
    """Admin dashboard response"""
    batchId: str
    batchName: str
    overview: DashboardOverview
    healthDistribution: HealthDistribution
    recentActivity: List[RecentActivityItem]
    mentorWorkload: List[MentorWorkloadItem]


class MentorOverview(BaseModel):
    """Mentor dashboard overview"""
    totalTeams: int
    onTrack: int
    atRisk: int
    critical: int


class MentorTeamItem(BaseModel):
    """Mentor team item in dashboard"""
    id: str
    name: str
    batchId: str
    batchName: str
    repoUrl: str
    healthStatus: str
    lastActivity: str
    contributionBalance: int
    riskFlags: List[str]
    totalScore: float


class MentorActivityItem(BaseModel):
    """Mentor recent activity item"""
    teamId: str
    teamName: str
    type: str
    message: str
    timestamp: str


class MentorDashboardResponse(BaseModel):
    """Mentor dashboard response"""
    mentorId: str
    mentorName: str
    overview: MentorOverview
    teams: List[MentorTeamItem]
    recentActivity: List[MentorActivityItem]


class UserInfo(BaseModel):
    """User information"""
    id: str
    email: str
    fullName: str
    role: Optional[str] = None
    status: str
    lastLogin: Optional[str] = None
    createdAt: str


class UserListResponse(BaseModel):
    """User list response"""
    users: List[UserInfo]
    total: int
    page: int
    pageSize: int


class UserRoleUpdateRequest(BaseModel):
    """User role update request"""
    role: Optional[str] = Field(None, pattern="^(admin|mentor)$")


class UserRoleUpdateResponse(BaseModel):
    """User role update response"""
    user: UserInfo
    message: str


# ==================== Analytics Schemas ====================

class AnalysisScores(BaseModel):
    """Analysis scores breakdown"""
    totalScore: float
    qualityScore: float
    securityScore: float
    originalityScore: float
    architectureScore: float
    documentationScore: float


class ContributorStats(BaseModel):
    """Contributor statistics"""
    contributorName: str
    commits: int
    percentage: float
    additions: int
    deletions: int


class CommitTimelineItem(BaseModel):
    """Commit timeline entry"""
    date: str
    commits: int
    additions: int
    deletions: int


class CommitMetrics(BaseModel):
    """Commit metrics"""
    total: int
    lastWeek: int
    contributionDistribution: List[ContributorStats]
    timeline: List[CommitTimelineItem]
    burstDetected: bool
    lastMinuteCommits: int


class LanguageStats(BaseModel):
    """Language statistics"""
    name: str
    percentage: float


class CodeMetrics(BaseModel):
    """Code metrics"""
    totalFiles: int
    totalLinesOfCode: int
    languages: List[LanguageStats]
    techStack: List[str]
    architecturePattern: str


class HeatmapPoint(BaseModel):
    """Heatmap data point"""
    date: str
    count: int


class HourlyActivityItem(BaseModel):
    """Hourly activity data"""
    hour: str
    commits: int


class WeeklyCommitActivityItem(BaseModel):
    """Weekly commit activity"""
    week: str
    commits: int
    additions: int
    deletions: int


class WarningItem(BaseModel):
    """Analytics warning"""
    type: str
    message: str
    severity: str


class ActivityMetadata(BaseModel):
    """Activity metadata"""
    additions: Optional[int] = None
    deletions: Optional[int] = None
    files: Optional[int] = None


class RecentActivityItem(BaseModel):
    """Recent activity item"""
    id: str
    type: str
    title: str
    description: Optional[str] = None
    author: str
    date: str
    metadata: Optional[ActivityMetadata] = None


class LanguageBreakdownItem(BaseModel):
    """Language breakdown item"""
    name: str
    value: float
    color: Optional[str] = None


class ContributorActivity(BaseModel):
    """Enhanced contributor activity"""
    name: str
    email: str
    commits: int
    additions: int
    deletions: int
    percentage: float
    activeDays: int
    avgCommitsPerDay: float
    topFileTypes: List[FileTypeStat]
    contributionData: List[HeatmapPoint]
    lastActive: str
    streak: int


class SecurityIssueDetail(BaseModel):
    """Security issue detail"""
    type: str
    severity: str
    file: str
    line: int
    description: str


class SecurityMetrics(BaseModel):
    """Security metrics"""
    score: float
    issues: List[SecurityIssueDetail]
    secretsDetected: int


class AIAnalysis(BaseModel):
    """AI analysis results"""
    aiGeneratedPercentage: float
    verdict: str
    strengths: List[str]
    improvements: List[str]

class RiskFlagItem(BaseModel):
    """Risk flag display info"""
    flag: str
    label: str
    icon: str
    severity: str
    description: str


class TeamAnalyticsResponse(BaseModel):
    """Team analytics response"""
    teamId: str
    teamName: str
    batchId: str
    analysis: AnalysisScores
    commits: CommitMetrics
    codeMetrics: CodeMetrics
    security: SecurityMetrics
    aiAnalysis: AIAnalysis
    healthStatus: str
    riskFlags: List[RiskFlagItem] = []
    lastAnalyzedAt: Optional[str] = None
    repoUrl: Optional[str] = None
    createdAt: Optional[str] = None
    totalCommits: Optional[int] = None
    totalAdditions: Optional[int] = None
    totalDeletions: Optional[int] = None
    activeDays: Optional[int] = None
    avgCommitsPerDay: Optional[float] = None
    contributors: Optional[List[ContributorActivity]] = None
    commitActivity: Optional[List[WeeklyCommitActivityItem]] = None
    hourlyActivity: Optional[List[HourlyActivityItem]] = None
    teamContributionData: Optional[List[HeatmapPoint]] = None
    recentActivities: Optional[List[RecentActivityItem]] = None
    warnings: Optional[List[WarningItem]] = None
    languageBreakdown: Optional[List[LanguageBreakdownItem]] = None


class CommitFile(BaseModel):
    """File changed in a commit"""
    file: str
    additions: int = 0
    deletions: int = 0
    patch: Optional[str] = None


class CommitDetail(BaseModel):
    """Individual commit detail"""
    sha: str
    author: str
    authorEmail: str
    message: str
    date: str
    additions: int
    deletions: int
    filesChanged: int
    files: List[CommitFile] = []


class TeamCommitsResponse(BaseModel):
    """Team commits response"""
    commits: List[CommitDetail]
    total: int
    page: int
    pageSize: int


class FileNode(BaseModel):
    """File tree node"""
    path: str
    type: str  # "file" or "directory"
    size: Optional[int] = None
    language: Optional[str] = None
    children: Optional[List['FileNode']] = None


# Enable forward references
FileNode.model_rebuild()


class TeamFileTreeResponse(BaseModel):
    """Team file tree response"""
    tree: List[FileNode]
    totalFiles: int
    totalSize: int


# ==================== Reports Schemas ====================

class BatchReportSummary(BaseModel):
    """Batch report summary"""
    totalTeams: int
    averageScore: float
    topTeam: str
    topScore: float


class BatchReportTeam(BaseModel):
    """Team data in batch report"""
    rank: int
    teamName: str
    totalScore: float
    qualityScore: float
    securityScore: float
    originalityScore: Optional[float] = None
    architectureScore: Optional[float] = None
    documentationScore: Optional[float] = None
    healthStatus: Optional[str] = None
    mentorId: Optional[str] = None
    frameworks: Optional[List[str]] = None


class BatchReportInsights(BaseModel):
    """Batch insights"""
    mostUsedTech: str
    averageAiUsage: float
    totalSecurityIssues: int


class BatchReportResponse(BaseModel):
    """Batch report response"""
    batchId: str
    batchName: str
    generatedAt: str
    summary: BatchReportSummary
    teams: List[BatchReportTeam]
    insights: BatchReportInsights


class MentorReportSummary(BaseModel):
    """Mentor report summary"""
    totalTeams: int
    averageScore: float
    teamsOnTrack: int
    teamsAtRisk: int
    teamsCritical: Optional[int] = None


class MentorReportTeam(BaseModel):
    """Team data in mentor report"""
    teamId: str
    teamName: str
    batchId: str
    totalScore: float
    qualityScore: float
    securityScore: float
    healthStatus: str
    lastAnalyzed: Optional[str] = None


class MentorReportResponse(BaseModel):
    """Mentor report response"""
    mentorId: str
    mentorName: str
    generatedAt: str
    teams: List[MentorReportTeam]
    summary: MentorReportSummary


class TeamReportContributor(BaseModel):
    """Contributor in team report"""
    name: str
    commits: int
    additions: int
    deletions: int


class TeamReportCommits(BaseModel):
    """Commits section in team report"""
    total: int
    contributors: List[TeamReportContributor]


class TeamReportCodeMetrics(BaseModel):
    """Code metrics in team report"""
    totalFiles: int
    totalLinesOfCode: int
    languages: List[Any]
    techStack: List[str]
    architecturePattern: str


class TeamReportSecurity(BaseModel):
    """Security section in team report"""
    score: float
    issues: List[Any]
    secretsDetected: int


class TeamReportResponse(BaseModel):
    """Team report response"""
    teamId: str
    teamName: str
    batchId: str
    generatedAt: str
    analysis: AnalysisScores
    commits: TeamReportCommits
    codeMetrics: TeamReportCodeMetrics
    security: TeamReportSecurity
    aiAnalysis: Optional[AIAnalysis] = None
    healthStatus: str
    riskFlags: Optional[List[str]] = None
    lastAnalyzedAt: Optional[str] = None


# ==================== Mentor Analytics Schemas ====================

class TeamPerformanceInfo(BaseModel):
    """Information about a team's performance"""
    team_id: UUID
    team_name: str
    score: float = Field(..., ge=0, le=100)


class MentorAnalyticsItem(BaseModel):
    """Single mentor item in analytics list"""
    mentor_id: UUID
    full_name: Optional[str] = None
    email: str
    role: str = "mentor"  # User role (mentor or admin)
    last_login: Optional[datetime] = None
    last_logout: Optional[datetime] = None
    is_online: bool
    total_time_spent_seconds: int = Field(..., ge=0)
    weekly_time_spent_seconds: int = Field(..., ge=0)
    number_of_teams: int = Field(..., ge=0)
    average_team_score: Optional[float] = Field(None, ge=0, le=100)
    best_performing_team: Optional[TeamPerformanceInfo] = None
    worst_performing_team: Optional[TeamPerformanceInfo] = None
    teams_in_top_10: int = Field(..., ge=0)


class MentorAnalyticsListResponse(BaseModel):
    """Response for mentor analytics list endpoint"""
    mentors: List[MentorAnalyticsItem]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=100)
    total_pages: int = Field(..., ge=0)


class TeamDetailInfo(BaseModel):
    """Detailed information about a team"""
    team_id: UUID
    team_name: str
    batch_id: UUID
    batch_name: str
    total_score: Optional[float] = Field(None, ge=0, le=100)
    rank_in_batch: Optional[int] = Field(None, ge=1)
    student_count: int = Field(..., ge=0)
    last_activity: Optional[datetime] = None


class MentorPerformanceSummary(BaseModel):
    """Summary of mentor performance metrics"""
    average_team_score: Optional[float] = Field(None, ge=0, le=100)
    best_performing_team: Optional[TeamPerformanceInfo] = None
    worst_performing_team: Optional[TeamPerformanceInfo] = None
    teams_in_top_10: int = Field(..., ge=0)


class MentorAnalyticsDetailResponse(BaseModel):
    """Response for mentor analytics detail endpoint"""
    mentor_id: UUID
    full_name: Optional[str] = None
    email: str
    last_login: Optional[datetime] = None
    last_logout: Optional[datetime] = None
    is_online: bool
    total_time_spent_seconds: int = Field(..., ge=0)
    weekly_time_spent_seconds: int = Field(..., ge=0)
    teams: List[TeamDetailInfo]
    performance_summary: MentorPerformanceSummary
