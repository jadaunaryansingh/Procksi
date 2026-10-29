"""
Scheduled Task Monitoring API
Provides endpoints to view and monitor Celery Beat scheduled task executions
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from src.api.backend.database import get_supabase_admin_client
from src.api.backend.middleware.auth import RoleChecker
from src.api.backend.utils.cache import cache, RedisCache

router = APIRouter(prefix="/api/scheduled-tasks", tags=["Scheduled Tasks"])


# ============================================================
# Response Models
# ============================================================

class TaskExecutionModel(BaseModel):
    """Model for individual task execution"""
    id: str
    task_name: str
    task_display_name: Optional[str] = None
    celery_task_id: Optional[str] = None
    scheduled_time: datetime
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    status: str
    result_summary: Optional[dict] = None
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: datetime


class TaskHealthModel(BaseModel):
    """Model for task health status"""
    task_name: str
    task_display_name: Optional[str] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    last_status: Optional[str] = None
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    success_rate: float = 0.0
    expected_schedule: Optional[str] = None
    expected_next_run: Optional[datetime] = None
    consecutive_failures: int = 0
    alert_sent_at: Optional[datetime] = None
    health_status: str = "unknown"
    updated_at: datetime
    created_at: datetime


class TaskHealthSummary(BaseModel):
    """Summary of all task health statuses"""
    healthy: int
    degraded: int
    critical: int
    unknown: int
    total: int
    tasks: List[TaskHealthModel]


class TaskExecutionHistory(BaseModel):
    """Task execution history with pagination"""
    executions: List[TaskExecutionModel]
    total: int
    page: int
    page_size: int
    has_more: bool


# ============================================================
# API Endpoints
# ============================================================

@router.get("/health/summary", response_model=TaskHealthSummary)
async def get_task_health_summary(_=Depends(RoleChecker(["admin"]))):
    """
    Get health summary of all scheduled tasks.
    Shows which tasks are healthy, degraded, or critical.
    
    Admin only.
    """
    try:
        cache_key = "hackeval:scheduled_tasks:health_summary"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        supabase = get_supabase_admin_client()
        
        # Get all task health records
        result = supabase.table('scheduled_task_health')\
            .select('*')\
            .order('health_status.desc, task_name')\
            .execute()
        
        tasks = result.data or []
        
        # Count by status
        summary = {
            'healthy': 0,
            'degraded': 0,
            'critical': 0,
            'unknown': 0
        }
        
        for task in tasks:
            status = task.get('health_status', 'unknown')
            summary[status] = summary.get(status, 0) + 1
        
        response = {
            **summary,
            'total': len(tasks),
            'tasks': tasks
        }
        cache.set(cache_key, response, RedisCache.TTL_SHORT)
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch task health: {str(e)}")


@router.get("/health/{task_name}", response_model=TaskHealthModel)
async def get_task_health(task_name: str, _=Depends(RoleChecker(["admin"]))):
    """
    Get detailed health information for a specific scheduled task.
    
    Admin only.
    """
    try:
        cache_key = f"hackeval:scheduled_tasks:health:{task_name}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        supabase = get_supabase_admin_client()
        
        result = supabase.table('scheduled_task_health')\
            .select('*')\
            .eq('task_name', task_name)\
            .single()\
            .execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail=f"Task '{task_name}' not found")
        
        cache.set(cache_key, result.data, RedisCache.TTL_SHORT)
        return result.data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch task health: {str(e)}")


@router.get("/executions", response_model=TaskExecutionHistory)
async def get_task_executions(
    task_name: Optional[str] = Query(None, description="Filter by task name"),
    status: Optional[str] = Query(None, description="Filter by status (running, completed, failed, timeout, skipped)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    _=Depends(RoleChecker(["admin"]))
):
    """
    Get execution history for scheduled tasks with pagination.
    
    Admin only.
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Build query
        query = supabase.table('scheduled_task_executions').select('*', count='exact')
        
        # Apply filters
        if task_name:
            query = query.eq('task_name', task_name)
        if status:
            query = query.eq('status', status)
        
        # Apply pagination and ordering
        offset = (page - 1) * page_size
        query = query.order('started_at', desc=True).order('id', desc=True).range(offset, offset + page_size - 1)
        
        result = query.execute()
        executions = result.data or []
        total = result.count if hasattr(result, 'count') and result.count is not None else len(executions)
        
        has_more = total > (page * page_size)
        
        return {
            'executions': executions,
            'total': total,
            'page': page,
            'page_size': page_size,
            'has_more': has_more
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch executions: {str(e)}")


@router.get("/executions/{execution_id}", response_model=TaskExecutionModel)
async def get_task_execution_detail(execution_id: str, _=Depends(RoleChecker(["admin"]))):
    """
    Get detailed information for a specific task execution.
    Includes full error traceback if available.
    
    Admin only.
    """
    try:
        supabase = get_supabase_admin_client()
        
        result = supabase.table('scheduled_task_executions')\
            .select('*')\
            .eq('id', execution_id)\
            .single()\
            .execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
        
        return result.data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch execution detail: {str(e)}")


@router.get("/executions/{task_name}/recent")
async def get_recent_executions(
    task_name: str,
    limit: int = Query(10, ge=1, le=50, description="Number of recent executions to retrieve"),
    _=Depends(RoleChecker(["admin"]))
):
    """
    Get recent executions for a specific task.
    Useful for debugging and monitoring.
    
    Admin only.
    """
    try:
        cache_key = f"hackeval:scheduled_tasks:recent:{task_name}:{limit}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        supabase = get_supabase_admin_client()
        
        result = supabase.table('scheduled_task_executions')\
            .select('*')\
            .eq('task_name', task_name)\
            .order('started_at', desc=True)\
            .order('id', desc=True)\
            .limit(limit)\
            .execute()
        
        response = {
            'task_name': task_name,
            'count': len(result.data or []),
            'executions': result.data or []
        }
        cache.set(cache_key, response, RedisCache.TTL_SHORT)
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch recent executions: {str(e)}")


@router.get("/stats/overview")
async def get_task_stats_overview(_=Depends(RoleChecker(["admin"]))):
    """
    Get overview statistics for all scheduled tasks.
    Shows execution counts, success rates, and trends.
    
    Admin only.
    """
    try:
        cache_key = "hackeval:scheduled_tasks:stats_overview"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        supabase = get_supabase_admin_client()
        
        # Get executions from last 7 days
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        
        result = supabase.table('scheduled_task_executions')\
            .select('task_name, task_display_name, status, duration_seconds, started_at')\
            .gte('started_at', seven_days_ago)\
            .execute()
        
        executions = result.data or []
        
        # Aggregate statistics by task
        stats_by_task = {}
        
        for execution in executions:
            task_name = execution['task_name']
            status = execution['status']
            duration = execution.get('duration_seconds', 0) or 0
            
            if task_name not in stats_by_task:
                stats_by_task[task_name] = {
                    'task_name': task_name,
                    'task_display_name': execution.get('task_display_name', task_name),
                    'total': 0,
                    'completed': 0,
                    'failed': 0,
                    'running': 0,
                    'avg_duration': 0,
                    'total_duration': 0,
                    'min_duration': float('inf'),
                    'max_duration': 0
                }
            
            stats = stats_by_task[task_name]
            stats['total'] += 1
            
            if status == 'completed':
                stats['completed'] += 1
                if duration > 0:
                    stats['total_duration'] += duration
                    stats['min_duration'] = min(stats['min_duration'], duration)
                    stats['max_duration'] = max(stats['max_duration'], duration)
            elif status in ('failed', 'timeout'):
                stats['failed'] += 1
            elif status == 'running':
                stats['running'] += 1
        
        # Calculate averages
        for task_name, stats in stats_by_task.items():
            if stats['completed'] > 0:
                stats['avg_duration'] = round(stats['total_duration'] / stats['completed'], 2)
                if stats['min_duration'] == float('inf'):
                    stats['min_duration'] = 0
            else:
                stats['min_duration'] = 0
            
            stats['success_rate'] = round((stats['completed'] / stats['total'] * 100), 2) if stats['total'] > 0 else 0
            
            # Remove internal counters
            del stats['total_duration']
        
        response = {
            'period': '7_days',
            'tasks': list(stats_by_task.values())
        }
        cache.set(cache_key, response, RedisCache.TTL_SHORT)
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch task statistics: {str(e)}")


@router.post("/trigger-health-check")
async def trigger_health_check(_=Depends(RoleChecker(["admin"]))):
    """
    Manually trigger the scheduled task health check.
    Useful for debugging or immediate health assessment.
    
    Admin only.
    """
    try:
        from celery_worker import monitor_scheduled_task_health
        
        # Queue the task
        task = monitor_scheduled_task_health.delay()
        
        return {
            'status': 'queued',
            'task_id': task.id,
            'message': 'Health check task queued successfully'
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger health check: {str(e)}")


@router.get("/batch-analysis-overview")
async def get_batch_analysis_overview(_=Depends(RoleChecker(["admin"]))):
    """
    Get per-batch analysis overview showing how many teams were analyzed today,
    within 7 days, never analyzed, etc.
    
    Admin only.
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Get active batches
        batches_result = supabase.table('batches')\
            .select('id, name, semester, year, status')\
            .eq('status', 'active')\
            .execute()
        
        batches = batches_result.data or []
        overview = []
        
        today_start = (datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).isoformat()
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        
        for batch in batches:
            # Get team stats for this batch
            teams_result = supabase.table('teams')\
                .select('id, repo_url, last_analyzed_at')\
                .eq('batch_id', batch['id'])\
                .execute()
            
            teams = teams_result.data or []
            total = len(teams)
            
            no_repo = sum(1 for t in teams if not t.get('repo_url'))
            never_analyzed = sum(1 for t in teams if t.get('last_analyzed_at') is None)
            
            analyzed_today = 0
            analyzed_within_7d = 0
            latest_analysis = None
            earliest_today = None
            
            for t in teams:
                la = t.get('last_analyzed_at')
                if la:
                    if latest_analysis is None or la > latest_analysis:
                        latest_analysis = la
                    if la >= today_start:
                        analyzed_today += 1
                        if earliest_today is None or la < earliest_today:
                            earliest_today = la
                    if la >= seven_days_ago:
                        analyzed_within_7d += 1
            
            overview.append({
                'batch': {
                    'id': batch['id'],
                    'name': batch['name'],
                    'semester': batch['semester'],
                    'year': batch['year'],
                    'status': batch['status'],
                },
                'total_teams': total,
                'analyzed_today': analyzed_today,
                'analyzed_within_7d': analyzed_within_7d,
                'never_analyzed': never_analyzed,
                'no_repo': no_repo,
                'latest_analysis': latest_analysis,
                'earliest_today': earliest_today,
            })
        
        return overview
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch batch analysis overview: {str(e)}")


@router.get("/schedules")
async def get_task_schedules(_=Depends(RoleChecker(["admin"]))):
    """
    Get all Celery Beat scheduled tasks with their default and current schedules.
    Merges hardcoded defaults with DB overrides.
    
    Admin only.
    """
    try:
        from celery_app import celery_app
        supabase = get_supabase_admin_client()
        
        # 1. Get hardcoded defaults from celery_app
        defaults = celery_app.conf.beat_schedule or {}
        
        # 2. Get active overrides from DB
        result = supabase.table('celery_beat_overrides').select('*').execute()
        overrides = {row['schedule_key']: row for row in (result.data or [])}
        
        schedules = []
        
        # Merge them
        for key, task_def in defaults.items():
            schedule_obj = task_def.get('schedule')
            task_path = task_def.get('task')
            
            # Extract cron fields from Celery crontab object if possible
            # This is a bit hacky because crontab internals aren't meant for easy parsing,
            # but we can try to extract string representations
            default_day = "*"
            default_hour = "*"
            default_minute = "*"
            
            if hasattr(schedule_obj, 'day_of_week') and hasattr(schedule_obj, 'hour') and hasattr(schedule_obj, 'minute'):
                # Handle generic set/list structures celery uses
                def format_cron_field(field):
                    if hasattr(field, 'pop'):
                        return ','.join(map(str, sorted(list(field))))
                    return str(field)
                    
                try:
                    default_day = format_cron_field(schedule_obj.day_of_week)
                    default_hour = format_cron_field(schedule_obj.hour)
                    default_minute = format_cron_field(schedule_obj.minute)
                except Exception:
                    pass
            
            # Check if there's an override
            override = overrides.get(key)
            
            schedules.append({
                'schedule_key': key,
                'task_path': task_path,
                'is_overridden': bool(override),
                'enabled': override['enabled'] if override else True,
                
                # Active schedule
                'day_of_week': override['day_of_week'] if override and override.get('day_of_week') is not None else default_day,
                'hour': override['hour'] if override and override.get('hour') is not None else default_hour,
                'minute': override['minute'] if override and override.get('minute') is not None else default_minute,
                
                # Default schedule info
                'default_day_of_week': default_day,
                'default_hour': default_hour,
                'default_minute': default_minute,
                
                # Audit info
                'updated_by': override.get('updated_by') if override else None,
                'updated_at': override.get('updated_at') if override else None,
            })
            
        return schedules
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch task schedules: {str(e)}")


class ScheduleUpdateRequest(BaseModel):
    day_of_week: Optional[str] = None
    hour: Optional[str] = None
    minute: Optional[str] = None
    enabled: bool = True

@router.put("/schedules/{schedule_key}")
async def update_task_schedule(
    schedule_key: str, 
    request: ScheduleUpdateRequest,
    _=Depends(RoleChecker(["admin"]))
):
    """
    Update a task's schedule. This saves an override to the DB.
    Changes won't apply until the Celery Beat worker restarts.
    
    Admin only.
    """
    try:
        from celery_app import celery_app
        supabase = get_supabase_admin_client()
        
        # Verify the task exists in our defaults
        defaults = celery_app.conf.beat_schedule or {}
        if schedule_key not in defaults:
            raise HTTPException(status_code=404, detail=f"Task schedule '{schedule_key}' not found in Celery defaults.")
            
        task_path = defaults[schedule_key].get('task')
        
        # Check if override already exists
        existing = supabase.table('celery_beat_overrides').select('id').eq('schedule_key', schedule_key).execute()
        
        data = {
            'schedule_key': schedule_key,
            'task_path': task_path,
            'enabled': request.enabled,
            # For auditing, ideally we'd get the actual user email from token
            'updated_by': 'admin@system', 
            'updated_at': datetime.utcnow().isoformat()
        }
        
        if request.day_of_week is not None:
             data['day_of_week'] = request.day_of_week
        if request.hour is not None:
            data['hour'] = request.hour
        if request.minute is not None:
            data['minute'] = request.minute
            
        if existing.data and len(existing.data) > 0:
            # Update
            result = supabase.table('celery_beat_overrides').update(data).eq('schedule_key', schedule_key).execute()
        else:
            # Insert
            result = supabase.table('celery_beat_overrides').insert(data).execute()
            
        return {
            'status': 'success',
            'message': 'Schedule updated successfully. Note: Celery Beat must be restarted for changes to take effect.',
            'data': result.data[0] if result.data else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update task schedule: {str(e)}")


@router.post("/schedules/reset/{schedule_key}")
async def reset_task_schedule(
    schedule_key: str, 
    _=Depends(RoleChecker(["admin"]))
):
    """
    Reset a task's schedule to default by deleting the DB override.
    Changes won't apply until the Celery Beat worker restarts.
    
    Admin only.
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Delete the override
        supabase.table('celery_beat_overrides').delete().eq('schedule_key', schedule_key).execute()
            
        return {
            'status': 'success',
            'message': 'Schedule reset to default successfully. Note: Celery Beat must be restarted for changes to take effect.'
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset task schedule: {str(e)}")
