"""
Frontend-compatible API endpoints
Matches the expected frontend specification
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, UploadFile, File, Form
from typing import Optional, List
from uuid import UUID
import csv
import io

from src.api.backend.crud import TeamCRUD, TechStackCRUD, IssueCRUD, TeamMemberCRUD, AnalysisJobCRUD
from src.api.backend.services.frontend_adapter import FrontendAdapter
from src.api.backend.background import run_analysis_job
from src.api.backend.utils.cache import cache, RedisCache

router = APIRouter(prefix="/api", tags=["frontend"])











@router.get("/leaderboard")
async def get_leaderboard(
    tech: Optional[str] = Query(None),
    sort: Optional[str] = Query(None, pattern="^(total|quality|security|originality|architecture|documentation)$"),
    search: Optional[str] = Query(None),
    # New parameters to support frontend format
    sort_by: Optional[str] = Query(None),
    order: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    cursor_score: Optional[float] = Query(None, description="Keyset cursor: last row total_score"),
    cursor_team_name: Optional[str] = Query(None, description="Keyset cursor: last row team_name"),
    batch_id: Optional[str] = Query(None),
    mentor_id: Optional[str] = Query(None)
):
    """
    Get leaderboard with filters (matches frontend LeaderboardEntry[])
    Note: Now queries teams table since projects table is dropped
    """ 
    try:
        from ..database import get_supabase_admin_client
        supabase = get_supabase_admin_client()
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size - 1

        # Handle both old and new parameter formats
        if sort_by:
            sort_field = sort_by
        elif sort:
            sort_field = f"{sort}_score" if sort != "total" else "total_score"
        else:
            sort_field = "total_score"
        
        sort_order = order or "desc"
        use_keyset = (
            cursor_score is not None
            and cursor_team_name is not None
            and sort_field == "total_score"
            and sort_order.lower() == "desc"
        )
        
        # Check cache first — skip cache for mentor-specific queries (always fresh)
        cache_key = (
            f"hackeval:leaderboard:{tech}:{sort_field}:{sort_order}:{search}:{batch_id}:{mentor_id}:"
            f"{page}:{page_size}:{cursor_score}:{cursor_team_name}"
        )
        if not mentor_id:
            cached_result = cache.get(cache_key)
            if cached_result:
                return cached_result

        # If mentor_id is provided, resolve the team IDs for that mentor first
        # Use admin client directly to bypass RLS. Retry up to 3 times on transient errors.
        mentor_team_ids: Optional[List[str]] = None
        if mentor_id:
            import time
            assigned_ids: set = set()
            max_retries = 3

            # A. teams.mentor_id direct column — also scope by batch_id if provided
            for attempt in range(max_retries):
                try:
                    q = supabase.table("teams").select("id").eq("mentor_id", mentor_id).limit(10000)
                    if batch_id:
                        q = q.eq("batch_id", batch_id)
                    direct = q.execute()
                    if direct.data:
                        assigned_ids.update(t["id"] for t in direct.data)
                        print(f"[leaderboard] Found {len(direct.data)} teams via teams.mentor_id for {mentor_id}")
                    break
                except Exception as e:
                    print(f"[leaderboard] Attempt {attempt+1}/{max_retries} failed (teams.mentor_id): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(0.5 * (attempt + 1))

            # B. mentor_team_assignments junction table — join teams to scope by batch_id
            for attempt in range(max_retries):
                try:
                    if batch_id:
                        # Join with teams table to filter by batch
                        a_q = supabase.table("mentor_team_assignments").select(
                            "team_id, teams!inner(batch_id)"
                        ).eq("mentor_id", mentor_id).eq("teams.batch_id", batch_id).limit(10000)
                    else:
                        a_q = supabase.table("mentor_team_assignments").select("team_id").eq("mentor_id", mentor_id).limit(10000)
                    assignments = a_q.execute()
                    if assignments.data:
                        assigned_ids.update(a["team_id"] for a in assignments.data)
                        print(f"[leaderboard] Found {len(assignments.data)} teams via mentor_team_assignments for {mentor_id}")
                    break
                except Exception as e:
                    print(f"[leaderboard] Attempt {attempt+1}/{max_retries} failed (mentor_team_assignments): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(0.5 * (attempt + 1))

            mentor_team_ids = list(assigned_ids)
            print(f"[leaderboard] Total unique team IDs for mentor {mentor_id} (batch={batch_id}): {len(mentor_team_ids)}")
            if not mentor_team_ids:
                return {"leaderboard": [], "total": 0, "total_assigned": 0, "page": page, "page_size": page_size}

        # Build leaderboard query — show all teams that have been scored
        # Use DB-level pagination to avoid loading large result sets into memory.
        query = supabase.table("teams").select(
            "id, team_name, repo_url, total_score, quality_score, security_score, "
            "originality_score, engineering_score, documentation_score, verdict, status, metadata",
            count="exact"
        ).not_.is_("total_score", "null")

        # Apply mentor filter — split into chunks of 200 to avoid URL length limits
        if mentor_team_ids is not None:
            if len(mentor_team_ids) <= 200:
                query = query.in_("id", mentor_team_ids)
            else:
                # Fetch in chunks and merge
                all_teams = []
                chunk_size = 200
                for i in range(0, len(mentor_team_ids), chunk_size):
                    chunk = mentor_team_ids[i:i + chunk_size]
                    chunk_q = supabase.table("teams").select(
                        "id, team_name, repo_url, total_score, quality_score, security_score, "
                        "originality_score, engineering_score, documentation_score, verdict, status, metadata"
                    ).not_.is_("total_score", "null").in_("id", chunk).limit(10000)
                    if batch_id:
                        chunk_q = chunk_q.eq("batch_id", batch_id)
                    chunk_result = chunk_q.execute()
                    if chunk_result.data:
                        all_teams.extend(chunk_result.data)

                print(f"[leaderboard] Chunked fetch returned {len(all_teams)} scored teams for mentor {mentor_id}")
                # Sort in Python since we merged chunks
                if sort_field == "total_score" and sort_order.lower() == "desc":
                    all_teams.sort(key=lambda t: (-(t.get("total_score") or 0), (t.get("team_name") or ""), (t.get("id") or "")))
                else:
                    reverse = (sort_order.lower() == "desc")
                    all_teams.sort(key=lambda t: ((t.get(sort_field) or 0), (t.get("team_name") or "")), reverse=reverse)

                # Apply search filter
                if search:
                    all_teams = [t for t in all_teams if search.lower() in (t.get("team_name") or "").lower()]

                # Apply keyset cursor for mentor-chunked flow when eligible.
                if use_keyset:
                    all_teams = [
                        t for t in all_teams
                        if (
                            (t.get("total_score") or 0) < cursor_score
                            or (
                                (t.get("total_score") or 0) == cursor_score
                                and (t.get("team_name") or "") > cursor_team_name
                            )
                        )
                    ]

                team_ids = [t["id"] for t in all_teams]
                tech_response = supabase.table("tech_stack").select("team_id, technology").in_("team_id", team_ids).limit(10000).execute()
                tech_map: dict = {}
                for tech_item in (tech_response.data or []):
                    tid = tech_item["team_id"]
                    if tid not in tech_map:
                        tech_map[tid] = []
                    tech_map[tid].append(tech_item)

                results = []
                for idx, team in enumerate(all_teams):
                    tid = team["id"]
                    tech_stack = tech_map.get(tid, [])
                    if tech:
                        if tech not in [t.get("technology") for t in tech_stack]:
                            continue
                    item = FrontendAdapter.transform_leaderboard_item(team, tech_stack)
                    item["rank"] = idx + 1
                    results.append(item)

                total_results = len(results)
                if use_keyset:
                    paged_results = results[:page_size]
                else:
                    start_idx = (page - 1) * page_size
                    end_idx = start_idx + page_size
                    paged_results = results[start_idx:end_idx]

                response = {
                    "leaderboard": paged_results,
                    "total": total_results,
                    "total_assigned": len(mentor_team_ids),
                    "page": page,
                    "page_size": page_size,
                }
                cache.set(cache_key, response, 60)
                return response

        # Apply batch filter if specified
        if batch_id:
            query = query.eq("batch_id", batch_id)

        # Apply technology filter at DB level to keep count/pagination accurate.
        if tech:
            tech_team_rows = supabase.table("tech_stack").select("team_id").eq("technology", tech).limit(10000).execute()
            tech_team_ids = list({row.get("team_id") for row in (tech_team_rows.data or []) if row.get("team_id")})
            if not tech_team_ids:
                return {"leaderboard": [], "total": 0, "page": page, "page_size": page_size}
            query = query.in_("id", tech_team_ids)
        
        # Apply search filter at database level
        if search:
            query = query.ilike("team_name", f"%{search}%")

        # Apply keyset cursor filter for total_score DESC, team_name ASC ordering.
        if use_keyset:
            escaped_team_name = cursor_team_name.replace('"', '\\"')
            query = query.or_(
                f"total_score.lt.{cursor_score},and(total_score.eq.{cursor_score},team_name.gt.\"{escaped_team_name}\")"
            )
        
        # Sort at database level
        query = query.order(sort_field, desc=(sort_order.lower() == "desc"))
        # Deterministic tie-breaker for stable pagination.
        query = query.order("team_name", desc=False)
        if use_keyset:
            query = query.range(0, page_size - 1)
        else:
            query = query.range(start_idx, end_idx)
        
        # Execute optimized query
        result = query.execute()
        teams = result.data or []
        total_results = result.count if result.count is not None else len(teams)
        
        # Early return if no teams
        if not teams:
            return {"leaderboard": [], "total": 0, "page": page, "page_size": page_size}
        
        # Get team IDs for tech stack fetch
        team_ids = [t["id"] for t in teams]
        
        # Single query for all tech stacks (using team_id)
        tech_response = supabase.table("tech_stack").select("team_id, technology").in_("team_id", team_ids).limit(10000).execute()
        tech_map = {}
        for tech_item in (tech_response.data or []):
            tid = tech_item["team_id"]
            if tid not in tech_map:
                tech_map[tid] = []
            tech_map[tid].append(tech_item)
        
        # Transform using pre-fetched data
        results = []
        for team in teams:
            tid = team["id"]
            tech_stack = tech_map.get(tid, [])
            
            item = FrontendAdapter.transform_leaderboard_item(team, tech_stack)
            results.append(item)

        # Results are already paged at DB level.
        for idx, item in enumerate(results):
            start_rank = start_idx
            item["rank"] = start_rank + idx + 1
        
        # Return proper schema format
        response = {
            "leaderboard": results,
            "total": total_results,
            "total_assigned": len(mentor_team_ids) if mentor_team_ids is not None else total_results,
            "page": page,
            "page_size": page_size,
            "next_cursor": (
                {
                    "cursor_score": results[-1].get("total_score"),
                    "cursor_team_name": results[-1].get("team_name"),
                }
                if use_keyset and results
                else None
            ),
        }
        
        # Cache non-mentor results for 60 seconds
        if not mentor_id:
            cache.set(cache_key, response, 60)
        
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaderboard/chart")
async def get_leaderboard_chart():
    """
    Get leaderboard data for chart visualization
    Note: Now queries teams table since projects table is dropped
    """
    try:
        # Check cache
        cache_key = "hackeval:leaderboard:chart"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        from ..database import get_supabase_admin_client
        supabase = get_supabase_admin_client()
        
        # Query teams table for completed teams
        result = supabase.table("teams").select(
            "team_name, total_score, quality_score, security_score, originality_score, "
            "engineering_score, documentation_score"
        ).eq("status", "completed").order("total_score", desc=True).limit(10).execute()
        
        teams = result.data or []
        
        chart_data = []
        for team in teams:
            chart_data.append({
                "teamName": team.get("team_name"),
                "totalScore": team.get("total_score") or 0,
                "qualityScore": team.get("quality_score") or 0,
                "securityScore": team.get("security_score") or 0,
                "originalityScore": team.get("originality_score") or 0,
                "architectureScore": team.get("engineering_score") or 0,
                "documentationScore": team.get("documentation_score") or 0
            })
        
        # Cache for 1 minute
        cache.set(cache_key, chart_data, 60)
        
        return chart_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_dashboard_stats():
    """
    Get aggregate statistics for dashboard
    Note: Now queries teams table since projects table is dropped
    """
    try:
        # Check cache
        cache_key = "hackeval:stats"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        from ..database import get_supabase_admin_client
        supabase = get_supabase_admin_client()
        
        # Query teams table
        result = supabase.table("teams").select("id, status, total_score").execute()
        teams = result.data or []
        
        completed = [t for t in teams if t.get("status") == "completed"]
        in_progress = [t for t in teams if t.get("status") in ["pending", "processing", "analyzing"]]
        
        avg_score = 0
        if completed:
            total_scores = sum(t.get("total_score") or 0 for t in completed)
            avg_score = round(total_scores / len(completed), 1)
        
        # Get all tech stacks
        all_tech = set()
        if completed:
            team_ids = [t["id"] for t in completed]
            tech_result = supabase.table("tech_stack").select("technology").in_("team_id", team_ids).execute()
            for tech in (tech_result.data or []):
                tech_name = tech.get("technology")
                if tech_name:
                    all_tech.add(tech_name)
        
        # Count security issues
        total_issues = 0
        if completed:
            team_ids = [t["id"] for t in completed]
            issues_result = supabase.table("issues").select("type").in_("team_id", team_ids).execute()
            total_issues = len([i for i in (issues_result.data or []) if i.get("type") == "security"])
        
        result = {
            "totalProjects": len(teams),
            "completedProjects": len(completed),
            "pendingProjects": len(in_progress),  # Changed from inProgressProjects
            "averageScore": avg_score,  # Changed from avgScore
            "totalSecurityIssues": total_issues
        }
        
        # Cache for 5 minutes
        cache.set(cache_key, result, RedisCache.TTL_MEDIUM)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.get("/tech-stacks")
async def get_available_technologies():
    """
    Get list of all technologies used across projects
    Note: Now queries teams table since projects table is dropped
    """
    try:
        # Check cache
        cache_key = "hackeval:tech-stacks"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
        
        from ..database import get_supabase_admin_client
        supabase = get_supabase_admin_client()
        
        # Get all teams
        teams_result = supabase.table("teams").select("id").execute()
        teams = teams_result.data or []
        
        tech_count = {}
        if teams:
            team_ids = [t["id"] for t in teams]
            tech_result = supabase.table("tech_stack").select("technology").in_("team_id", team_ids).execute()
            for tech in (tech_result.data or []):
                name = tech.get("technology")
                if name:
                    tech_count[name] = tech_count.get(name, 0) + 1
        
        # Convert to list and sort by usage
        tech_list = [{"name": name, "count": count} 
                     for name, count in tech_count.items()]
        tech_list = sorted(tech_list, key=lambda x: x["count"], reverse=True)
        
        # Cache for 5 minutes
        cache.set(cache_key, tech_list, RedisCache.TTL_MEDIUM)
        
        return tech_list
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/batch-upload")
async def batch_upload(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    Batch upload projects from CSV file - SEQUENTIAL PROCESSING
    Expected CSV columns: teamName, repoUrl, description (optional)
    
    Note: Now creates teams instead of projects since projects table is dropped
    
    Returns batchId for tracking progress via /api/batch/{batch_id}/status
    """
    from src.api.backend.crud import BatchCRUD, TeamCRUD
    from src.api.backend.background import run_batch_sequential
    
    try:
        # Validate file type
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV")
        
        # Read CSV content
        content = await file.read()
        # Handle BOM (Byte Order Mark) from Excel/Windows
        csv_text = content.decode('utf-8-sig')  # utf-8-sig handles BOM automatically
        csv_reader = csv.DictReader(io.StringIO(csv_text))
        
        # Validate headers - support both camelCase and snake_case
        headers = set(csv_reader.fieldnames or [])
        has_camel = {'teamName', 'repoUrl'}.issubset(headers)
        has_snake = {'team_name', 'repo_url'}.issubset(headers)
        
        if not has_camel and not has_snake:
            raise HTTPException(
                status_code=400, 
                detail="CSV missing required columns: teamName/team_name, repoUrl/repo_url"
            )
        
        # First pass: validate all rows and create teams/jobs
        repos_to_process = []
        failed_rows = []
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (header is row 1)
            # Support both camelCase and snake_case column names
            team_name = (row.get('teamName') or row.get('team_name') or '').strip()
            repo_url = (row.get('repoUrl') or row.get('repo_url') or '').strip()
            
            if not team_name or not repo_url:
                failed_rows.append({
                    "row": row_num,
                    "error": "Missing teamName or repoUrl"
                })
                continue
            
            # Validate GitHub URL
            if 'github.com' not in repo_url.lower():
                failed_rows.append({
                    "row": row_num,
                    "error": "Invalid GitHub URL"
                })
                continue
            
            try:
                # Check if team already exists with this repo URL
                existing = TeamCRUD.get_team_by_url(repo_url)
                if existing and existing.get("status") in ["analyzing", "completed"]:
                    failed_rows.append({
                        "row": row_num,
                        "teamName": team_name,
                        "repoUrl": repo_url,
                        "error": f"Already {existing.get('status')}"
                    })
                    continue
                
                # Create or update team
                if existing:
                    team_id = UUID(existing["id"])
                else:
                    # Create new team (simplified - no batch_id for now)
                    from ..database import get_supabase_admin_client
                    supabase = get_supabase_admin_client()
                    
                    team_data = {
                        "id": str(uuid4()),
                        "team_name": team_name,
                        "repo_url": repo_url,
                        "status": "pending"
                    }
                    
                    team_response = supabase.table("teams").insert(team_data).execute()
                    if not team_response.data:
                        raise Exception("Failed to create team")
                    
                    team_id = UUID(team_response.data[0]["id"])
                
                # Create job
                job = AnalysisJobCRUD.create_job(team_id)
                job_id = UUID(job["id"])
                
                # Add to processing queue
                repos_to_process.append({
                    "row": row_num,
                    "team_name": team_name,
                    "repo_url": repo_url,
                    "project_id": str(team_id),  # Keep as project_id for backward compatibility
                    "job_id": str(job_id)
                })
                
            except Exception as e:
                failed_rows.append({
                    "row": row_num,
                    "teamName": team_name,
                    "repoUrl": repo_url,
                    "error": str(e)
                })
        
        # Create batch record for tracking
        batch = None
        batch_id = None
        if repos_to_process:
            batch = BatchCRUD.create_batch(total_repos=len(repos_to_process))
            batch_id = batch["id"] if batch else None
            
            # Queue SINGLE background task for sequential processing
            if background_tasks and batch_id:
                background_tasks.add_task(
                    run_batch_sequential,
                    batch_id=batch_id,
                    repos=repos_to_process
                )
        
        # Build response for frontend
        queued_jobs = [
            {
                "row": r["row"],
                "teamName": r["team_name"],
                "repoUrl": r["repo_url"],
                "jobId": r["job_id"],
                "projectId": r["project_id"]  # Keep as projectId for backward compatibility
            }
            for r in repos_to_process
        ]
        
        return {
            "batchId": batch_id,  # NEW: for tracking
            "success": len(repos_to_process),
            "failed": len(failed_rows),
            "total": len(repos_to_process) + len(failed_rows),
            "queued": queued_jobs,
            "errors": failed_rows,
            "message": f"Successfully queued {len(repos_to_process)} teams for sequential processing, {len(failed_rows)} failed"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"\n❌ BATCH UPLOAD ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batch/{batch_id}/status")
async def get_batch_status(batch_id: str):
    """
    Get the current status of a batch upload - for live progress tracking
    
    Returns:
        - status: pending/processing/completed/failed
        - total: total number of repos in batch
        - completed: number of completed repos
        - failed: number of failed repos
        - currentIndex: which repo is currently being analyzed (1-indexed)
        - currentRepo: URL of the repo being analyzed
        - currentTeam: team name of the repo being analyzed
    """
    from src.api.backend.crud import BatchCRUD
    
    try:
        batch = BatchCRUD.get_batch(batch_id)
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        return {
            "batchId": batch_id,
            "status": batch.get("status", "pending"),
            "total": batch.get("total_repos", 0),
            "completed": batch.get("completed_repos", 0),
            "failed": batch.get("failed_repos", 0),
            "currentIndex": batch.get("current_index", 0),
            "currentRepo": batch.get("current_repo_url"),
            "currentTeam": batch.get("current_repo_team"),
            "createdAt": batch.get("created_at"),
            "completedAt": batch.get("completed_at"),
            "errorMessage": batch.get("error_message")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

