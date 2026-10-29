"""
Analysis Router
Endpoints for triggering and monitoring repository analysis
"""
from fastapi import APIRouter, HTTPException, status, Query
from starlette.requests import Request
from uuid import UUID
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import os

from src.api.backend.schemas import (
    AnalyzeRepoRequest,
    AnalyzeRepoResponse,
    AnalysisStatusResponse,
    AnalysisResultResponse,
    ScoreBreakdown,
    TechStackItem,
    IssueItem,
    TeamMemberItem,
    ErrorResponse,
    AnalysisJobListResponse
)
from src.api.backend.crud import AnalysisJobCRUD, TechStackCRUD, IssueCRUD, TeamMemberCRUD
from src.api.backend.utils.cache import cache, RedisCache
from src.api.backend.utils.rate_limiter import limiter

# Re-analysis interval configuration (in days)
# Can be overridden via environment variable REANALYSIS_INTERVAL_DAYS
REANALYSIS_INTERVAL_DAYS = int(os.getenv("REANALYSIS_INTERVAL_DAYS", "7"))  # Default: 7 days


def should_allow_reanalysis(project: Dict[str, Any], force: bool = False) -> tuple[bool, Optional[str]]:
    """
    Check if a project should be allowed to be re-analyzed.
    
    Returns:
        tuple: (allowed: bool, reason: str or None)
    """
    if force:
        return True, None
    
    status = project.get("status")
    
    # Allow if failed or pending
    if status in ["failed", "pending", None]:
        return True, None
    
    # Block if currently analyzing
    if status in ["analyzing", "queued"]:
        return False, f"Repository is currently being analyzed (status: {status})"
    
    # For completed projects, check the re-analysis interval
    if status == "completed":
        last_analyzed = project.get("last_analyzed_at")
        
        if not last_analyzed:
            # Never analyzed (old data without timestamp), allow re-analysis
            return True, None
        
        # Parse the timestamp
        try:
            if isinstance(last_analyzed, str):
                # Handle ISO format with or without timezone
                last_analyzed_dt = datetime.fromisoformat(last_analyzed.replace("Z", "+00:00"))
                # Make naive for comparison if needed
                if last_analyzed_dt.tzinfo:
                    last_analyzed_dt = last_analyzed_dt.replace(tzinfo=None)
            else:
                last_analyzed_dt = last_analyzed
            
            days_since_analysis = (datetime.now() - last_analyzed_dt).days
            
            if days_since_analysis < REANALYSIS_INTERVAL_DAYS:
                next_allowed = last_analyzed_dt + timedelta(days=REANALYSIS_INTERVAL_DAYS)
                return False, (
                    f"Repository was analyzed {days_since_analysis} day(s) ago. "
                    f"Re-analysis allowed after {REANALYSIS_INTERVAL_DAYS} days "
                    f"(next: {next_allowed.strftime('%Y-%m-%d')}). Use force=true to override."
                )
            
            # Enough time has passed
            return True, None
            
        except (ValueError, TypeError) as e:
            # If we can't parse the date, allow re-analysis
            return True, None
    
    # Default: allow
    return True, None

# Import Celery tasks
try:
    from celery_worker import analyze_single_repository_task
    CELERY_ENABLED = True
except ImportError:
    CELERY_ENABLED = False
    # Fallback to old background tasks
    from src.api.backend.background import run_analysis_job

router = APIRouter(prefix="/api", tags=["Analysis"])


@router.post(
    "/analyze-repo",
    response_model=AnalyzeRepoResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse}
    }
)
@limiter.limit("10/minute")
async def analyze_repo(
    request: Request,
    body: AnalyzeRepoRequest,
    force: bool = Query(False, description="Force re-analysis even if recently analyzed")
):
    """
    Trigger repository analysis
    
    - **repo_url**: GitHub repository URL
    - **team_name**: Optional team or project name
    - **force**: Force re-analysis even if recently analyzed (default: false)
    
    Returns job_id to track analysis progress.
    
    Note: By default, repos that have been analyzed within the last {REANALYSIS_INTERVAL_DAYS} days
    will not be re-analyzed. Use force=true to override this behavior.
    """
    try:
        # Check if team already exists with this repo_url
        from src.api.backend.database import get_supabase_admin_client
        supabase = get_supabase_admin_client()
        
        existing_team = supabase.table("teams").select("*").eq("repo_url", body.repo_url).limit(1).execute()
        
        if existing_team.data:
            team = existing_team.data[0]
            # Check if re-analysis should be allowed
            allowed, reason = should_allow_reanalysis(team, force=force)
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=reason
                )
            team_id = UUID(team["id"])
        else:
            # Create new team record
            team_data = {
                "team_name": body.team_name or "Unknown Team",
                "repo_url": body.repo_url,
                "status": "pending",
                "batch_id": "00000000-0000-0000-0000-000000000000"  # Default batch for standalone analysis
            }
            team_response = supabase.table("teams").insert(team_data).execute()
            if not team_response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create team record"
                )
            team_id = UUID(team_response.data[0]["id"])
        
        # Create analysis job
        job = AnalysisJobCRUD.create_job(team_id)
        job_id = UUID(job["id"])
        
        # Queue Celery task (or fallback to BackgroundTasks)
        celery_queued = False
        if CELERY_ENABLED:
            try:
                task = analyze_single_repository_task.delay(
                    team_id=str(team_id),
                    job_id=str(job_id),
                    repo_url=body.repo_url,
                    team_name=body.team_name
                )
                # Store Celery task ID
                supabase.table('analysis_jobs').update({
                    'metadata': {'celery_task_id': task.id}
                }).eq('id', str(job_id)).execute()
                celery_queued = True
            except Exception as celery_error:
                print(f"⚠ Celery queueing failed: {celery_error}")
                print("  Falling back to in-process background tasks...")
        
        # Fallback to old method if Celery failed
        if not celery_queued:
            try:
                from src.api.backend.background import run_analysis_job
                import asyncio
                asyncio.create_task(run_analysis_job(
                    project_id=str(team_id),
                    job_id=str(job_id),
                    repo_url=body.repo_url,
                    team_name=body.team_name
                ))
            except ImportError:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Analysis service temporarily unavailable"
                )
        
        return AnalyzeRepoResponse(
            job_id=job_id,
            team_id=team_id,
            status="queued",
            message="Analysis queued successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue analysis: {str(e)}"
        )


@router.post(
    "/cancel-analysis/{job_id}",
    responses={404: {"model": ErrorResponse}}
)
async def cancel_analysis(job_id: UUID):
    """
    Cancel a running or queued analysis job
    
    This will:
    - Revoke the Celery task if it's running
    - Mark the job as cancelled in the database
    - Update the team status back to pending
    
    **Parameters:**
    - job_id: UUID of the analysis job to cancel
    
    **Returns:**
    - Success message with cancellation details
    """
    try:
        from celery_app import celery_app
        from src.api.backend.database import get_supabase_admin_client
        from src.api.backend.crud import TeamCRUD
        
        supabase = get_supabase_admin_client()
        
        # Get the job
        job = AnalysisJobCRUD.get_job(job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis job {job_id} not found"
            )
        
        job_status = job.get("status")
        
        # Check if job can be cancelled
        if job_status not in ["queued", "running"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel job with status: {job_status}. Only queued or running jobs can be cancelled."
            )
        
        # Get Celery task ID from metadata
        metadata = job.get("metadata", {})
        celery_task_id = metadata.get("celery_task_id")
        
        revoked = False
        if celery_task_id:
            try:
                # Revoke the Celery task (terminate=True kills the worker process)
                celery_app.control.revoke(celery_task_id, terminate=True, signal='SIGKILL')
                revoked = True
            except Exception as e:
                print(f"Failed to revoke Celery task {celery_task_id}: {e}")
        
        # Update job status to cancelled
        supabase.table("analysis_jobs").update({
            "status": "cancelled",
            "error_message": "Cancelled by user",
            "completed_at": datetime.now().isoformat()
        }).eq("id", str(job_id)).execute()
        
        # Update team status back to pending
        team_id = job.get("team_id")
        if team_id:
            try:
                TeamCRUD.update_team_status(UUID(team_id), "pending")
            except Exception as e:
                print(f"Failed to update team status: {e}")
        
        return {
            "message": "Analysis cancelled successfully",
            "job_id": str(job_id),
            "celery_task_revoked": revoked,
            "previous_status": job_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel analysis: {str(e)}"
        )


@router.get(
    "/analysis-status/{job_id}",
    response_model=AnalysisStatusResponse,
    responses={404: {"model": ErrorResponse}}
)
async def get_analysis_status(job_id: UUID):
    """
    Get analysis job status and progress
    
    - **job_id**: UUID of the analysis job
    
    Returns current status, progress (0-100), and current stage
    """
    try:
        # Check cache for completed jobs
        cache_key = f"hackeval:analysis:{job_id}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return AnalysisStatusResponse(**cached_result)
        
        job = AnalysisJobCRUD.get_job(job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis job not found"
            )
        
        result = AnalysisStatusResponse(
            job_id=UUID(job["id"]),
            team_id=UUID(job["team_id"]),  # Changed from project_id
            status=job["status"],
            progress=job["progress"],
            current_stage=job.get("current_stage"),
            error_message=job.get("error_message"),
            started_at=job["started_at"],
            completed_at=job.get("completed_at")
        )
        
        # Cache completed/failed jobs for longer
        if job["status"] in ["completed", "failed"]:
            cache.set(cache_key, result.model_dump(mode="json"), RedisCache.TTL_MEDIUM)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status: {str(e)}"
        )


@router.get(
    "/analysis/stats",
    response_model=Dict[str, int],
    responses={500: {"model": ErrorResponse}}
)
async def get_analysis_stats(
    latest: bool = Query(True, description="Count only the latest job per project"),
    batch_id: Optional[str] = Query(None, description="Filter stats by Batch ID")
):
    """
    Get global analysis statistics
    
    Returns counts of projects in each status (queued, running, completed, failed).
    If latest=true (default), only counts the most recent job for each project.
    If batch_id is provided, filters stats to only include teams/projects in that batch.
    """
    try:
        stats = AnalysisJobCRUD.get_global_stats(latest_only=latest, batch_id=batch_id)
        return stats
    except Exception as e:
        print(f"Error getting analysis stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )


@router.get(
    "/analysis/jobs",
    response_model=AnalysisJobListResponse,
    responses={500: {"model": ErrorResponse}}
)
async def list_analysis_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    job_status: Optional[str] = Query(None, alias="status", pattern="^(queued|running|completed|failed|pending|cancelled)$"),
    latest: bool = Query(True, description="Show only the latest job per project"),
    batch_id: Optional[str] = Query(None, description="Filter by batch ID")
):
    """
    List all analysis jobs
    
    Returns jobs with project details (repo_url, team_name)
    Optionally filter by batch_id to show jobs for a specific batch
    """
    try:
        from math import ceil
        from src.api.backend.schemas import AnalysisJobListItem, AnalysisJobListResponse
        
        skip = (page - 1) * page_size
        jobs_data, total_jobs = AnalysisJobCRUD.list_jobs(skip=skip, limit=page_size, status=job_status, latest_only=latest, batch_id=batch_id)
        
        jobs = []
        for job in jobs_data:
            # Join data is in 'projects' key
            project_data = job.get("projects", {}) or {}
            
            # Map job_id, handling pending state where it might be None
            job_id_val = job.get("job_id")
            job_id = UUID(job_id_val) if job_id_val else None
            
            jobs.append(AnalysisJobListItem(
                job_id=job_id,
                team_id=UUID(job["project_id"]),  # Using project_id field (which contains team_id after migration)
                repo_url=job.get("repo_url", "Unknown"),
                team_name=job.get("team_name"),
                status=job["status"],
                progress=job.get("progress") or 0,
                current_stage=job.get("current_stage"),
                error_message=job.get("error_message"),
                started_at=job.get("started_at") or datetime.now(),
                completed_at=job.get("completed_at"),
                last_analyzed_at=job.get("last_analyzed_at")
            ))
        
        total_pages = ceil(total_jobs / page_size) if page_size > 0 else 0
        
        return AnalysisJobListResponse(
            jobs=jobs,
            total=total_jobs,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
        
    except Exception as e:
        print(f"Error listing analysis jobs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list jobs: {str(e)}"
        )


# Alias endpoint for frontend compatibility
@router.get(
    "/analysis/{job_id}",
    response_model=AnalysisStatusResponse,
    responses={404: {"model": ErrorResponse}}
)
async def get_analysis_status_alias(job_id: UUID):
    """Alias endpoint for /analysis-status/{job_id} for frontend compatibility"""
    return await get_analysis_status(job_id)



@router.get(
    "/analysis-result/{job_id}",
    response_model=AnalysisResultResponse,
    responses={
        404: {"model": ErrorResponse},
        425: {"model": ErrorResponse}
    }
)
async def get_analysis_result(job_id: UUID):
    """
    Get full analysis results
    
    - **job_id**: UUID of the analysis job
    
    Returns complete analysis report with scores, issues, tech stack, etc.
    Only available when analysis is completed.
    """
    try:
        # Check cache first
        cache_key = f"hackeval:analysis-result:{job_id}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        # Get job
        job = AnalysisJobCRUD.get_job(job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis job not found"
            )
        
        # Check if completed
        if job["status"] != "completed":
            raise HTTPException(
                status_code=status.HTTP_425_TOO_EARLY,
                detail=f"Analysis not completed yet. Current status: {job['status']}"
            )
        
        # Get team
        team_id = UUID(job["team_id"])
        from src.api.backend.database import get_supabase_admin_client
        supabase = get_supabase_admin_client()
        team_response = supabase.table("teams").select("*").eq("id", str(team_id)).limit(1).execute()
        
        if not team_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        
        team = team_response.data[0]
        
        # Get related data
        tech_stack = TechStackCRUD.get_tech_stack(team_id)
        issues = IssueCRUD.get_issues(team_id)
        team_members = TeamMemberCRUD.get_team_members(team_id)
        
        # Build response
        result = AnalysisResultResponse(
            team_id=team_id,
            repo_url=team["repo_url"],
            team_name=team.get("team_name"),
            status=team["status"],
            analyzed_at=team.get("analyzed_at"),
            scores=ScoreBreakdown(
                total_score=team.get("total_score"),
                originality_score=team.get("originality_score"),
                quality_score=team.get("quality_score"),
                security_score=team.get("security_score"),
                effort_score=team.get("effort_score"),
                implementation_score=team.get("implementation_score"),
                engineering_score=team.get("engineering_score"),
                organization_score=team.get("organization_score"),
                documentation_score=team.get("documentation_score")
            ),
            total_commits=team.get("total_commits"),
            verdict=team.get("verdict"),
            ai_pros=team.get("ai_pros"),
            ai_cons=team.get("ai_cons"),
            tech_stack=[
                TechStackItem(
                    technology=t["technology"],
                    category=t.get("category")
                ) for t in tech_stack
            ],
            issues=[
                IssueItem(
                    type=i["type"],
                    severity=i["severity"],
                    file_path=i.get("file_path"),
                    description=i["description"],
                    ai_probability=i.get("ai_probability"),
                    plagiarism_score=i.get("plagiarism_score")
                ) for i in issues
            ],
            team_members=[
                TeamMemberItem(
                    name=tm["name"],
                    commits=tm["commits"],
                    contribution_pct=tm.get("contribution_pct")
                ) for tm in team_members
            ],
            viz_url=team.get("viz_path"),
            report_json=team.get("report_json")
        )
        
        # Cache the result for 5 minutes (completed results don't change)
        cache.set(cache_key, result.model_dump(mode="json"), RedisCache.TTL_MEDIUM)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analysis result: {str(e)}"
        )
