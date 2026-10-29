"""
Debug and Diagnostic Router
Admin-only endpoints for system diagnostics and troubleshooting
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
import traceback
import logging

from ..middleware import get_current_user, RoleChecker, AuthUser
from ..database import get_supabase_admin_client

router = APIRouter(prefix="/api/debug", tags=["Debug"])
logger = logging.getLogger(__name__)


def test_celery_import() -> Dict[str, Any]:
    """Test if celery_worker can be imported"""
    try:
        from celery_worker import analyze_repository_task
        return {
            "success": True,
            "task_name": analyze_repository_task.name,
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "task_name": None,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


def test_redis_connection() -> Dict[str, Any]:
    """Test Redis connection through Celery"""
    try:
        from celery_app import celery_app
        import os
        
        redis_url = os.getenv('REDIS_URL', 'not_set')
        # Mask password in URL for security
        masked_url = redis_url.split('@')[1] if '@' in redis_url else redis_url
        
        # Try to ping Redis through Celery
        result = celery_app.control.inspect().stats()
        
        return {
            "success": True,
            "url": f"***@{masked_url}" if '@' in redis_url else masked_url,
            "connected": True,
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "url": "unknown",
            "connected": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


def test_worker_status() -> Dict[str, Any]:
    """Test if Celery workers are active"""
    try:
        from celery_app import celery_app
        
        # Get worker stats
        stats = celery_app.control.inspect().stats()
        active_queues = celery_app.control.inspect().active_queues()
        
        if stats:
            workers = list(stats.keys())
            queues = []
            if active_queues:
                for worker, worker_queues in active_queues.items():
                    queues.extend([q['name'] for q in worker_queues])
            
            return {
                "active": True,
                "workers": workers,
                "worker_count": len(workers),
                "queues": list(set(queues)),
                "error": None
            }
        else:
            return {
                "active": False,
                "workers": [],
                "worker_count": 0,
                "queues": [],
                "error": "No workers found"
            }
    except Exception as e:
        return {
            "active": False,
            "workers": [],
            "worker_count": 0,
            "queues": [],
            "error": str(e),
            "traceback": traceback.format_exc()
        }


def test_task_queuing() -> Dict[str, Any]:
    """Test if a task can be queued"""
    try:
        from celery_worker import analyze_repository_task
        
        # Queue a test task (will fail in worker but that's OK)
        task = analyze_repository_task.delay(
            team_id="test-diagnostic-team",
            job_id="test-diagnostic-job",
            repo_url="https://github.com/test/diagnostic",
            team_name="Diagnostic Test"
        )
        
        if task and task.id:
            return {
                "queued": True,
                "task_id": task.id,
                "task_state": task.state,
                "error": None
            }
        else:
            return {
                "queued": False,
                "task_id": None,
                "task_state": None,
                "error": "Task queued but no ID returned"
            }
    except Exception as e:
        return {
            "queued": False,
            "task_id": None,
            "task_state": None,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.get("/celery-status", dependencies=[Depends(RoleChecker(["admin"]))])
async def celery_status(current_user: AuthUser = Depends(get_current_user)):
    """
    Test all Celery components and return detailed status.
    
    Admin-only endpoint for diagnosing Celery/Redis issues.
    
    Returns:
        - celery_import: Can celery_worker be imported?
        - redis_connection: Can we connect to Redis?
        - worker_status: Are workers active?
        - test_task: Can we queue a test task?
    """
    logger.info(f"Running Celery diagnostics (requested by {current_user.email})")
    
    result = {
        "celery_import": test_celery_import(),
        "redis_connection": test_redis_connection(),
        "worker_status": test_worker_status(),
        "test_task": test_task_queuing()
    }
    
    # Determine overall status
    all_success = all([
        result["celery_import"]["success"],
        result["redis_connection"]["success"],
        result["worker_status"]["active"],
        result["test_task"]["queued"]
    ])
    
    result["overall_status"] = "healthy" if all_success else "unhealthy"
    result["summary"] = {
        "celery_import": "✅" if result["celery_import"]["success"] else "❌",
        "redis_connection": "✅" if result["redis_connection"]["success"] else "❌",
        "worker_active": "✅" if result["worker_status"]["active"] else "❌",
        "task_queuing": "✅" if result["test_task"]["queued"] else "❌"
    }
    
    logger.info(f"Celery diagnostics complete: {result['overall_status']}")
    
    return result


@router.get("/stuck-jobs", dependencies=[Depends(RoleChecker(["admin"]))])
async def get_stuck_jobs(current_user: AuthUser = Depends(get_current_user)):
    """
    Find analysis jobs stuck in 'queued' status.
    
    A job is considered stuck if:
    - Status is 'queued'
    - Started more than 5 minutes ago
    - No celery_task_id in metadata
    """
    from datetime import datetime, timedelta
    
    supabase = get_supabase_admin_client()
    
    # Find jobs queued > 5 minutes ago
    five_min_ago = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    
    stuck_jobs = supabase.table('analysis_jobs')\
        .select('id, team_id, status, started_at, metadata')\
        .eq('status', 'queued')\
        .lt('started_at', five_min_ago)\
        .execute()
    
    # Filter by missing celery_task_id
    truly_stuck = []
    for job in (stuck_jobs.data or []):
        metadata = job.get('metadata', {})
        if not metadata.get('celery_task_id'):
            truly_stuck.append({
                'job_id': job['id'],
                'team_id': job['team_id'],
                'started_at': job['started_at'],
                'metadata': metadata
            })
    
    return {
        "total_queued": len(stuck_jobs.data or []),
        "stuck_count": len(truly_stuck),
        "stuck_jobs": truly_stuck
    }


@router.post("/retry-stuck-jobs", dependencies=[Depends(RoleChecker(["admin"]))])
async def retry_stuck_jobs(current_user: AuthUser = Depends(get_current_user)):
    """
    Retry all jobs stuck in 'queued' status.
    
    This will:
    1. Find all stuck jobs (queued > 5 min, no celery_task_id)
    2. Re-queue each job with Celery
    3. Update metadata with celery_task_id and retry flag
    """
    from datetime import datetime, timedelta
    
    supabase = get_supabase_admin_client()
    
    # Import Celery task
    try:
        from celery_worker import analyze_repository_task
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Celery not available: {str(e)}"
        )
    
    # Find stuck jobs
    five_min_ago = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    
    stuck_jobs = supabase.table('analysis_jobs')\
        .select('id, team_id, metadata')\
        .eq('status', 'queued')\
        .lt('started_at', five_min_ago)\
        .execute()
    
    retried = []
    failed = []
    skipped = []
    
    for job in (stuck_jobs.data or []):
        job_id = job['id']
        team_id = job['team_id']
        metadata = job.get('metadata', {})
        
        # Skip if already has celery_task_id
        if metadata.get('celery_task_id'):
            skipped.append({
                'job_id': job_id,
                'reason': 'already_has_task_id'
            })
            continue
        
        # Get team details
        try:
            team = supabase.table('teams')\
                .select('repo_url, team_name')\
                .eq('id', team_id)\
                .single()\
                .execute()
            
            if not team.data:
                failed.append({
                    'job_id': job_id,
                    'error': 'Team not found'
                })
                continue
            
            # Retry queuing
            task = analyze_repository_task.delay(
                team_id=team_id,
                job_id=job_id,
                repo_url=team.data['repo_url'],
                team_name=team.data.get('team_name')
            )
            
            # Update metadata
            updated_metadata = {**metadata, 'celery_task_id': task.id, 'retried': True}
            supabase.table('analysis_jobs').update({
                'metadata': updated_metadata
            }).eq('id', job_id).execute()
            
            retried.append({
                'job_id': job_id,
                'task_id': task.id
            })
            
            logger.info(f"Retried stuck job {job_id}, task_id: {task.id}")
            
        except Exception as e:
            failed.append({
                'job_id': job_id,
                'error': str(e)
            })
            logger.error(f"Failed to retry job {job_id}: {e}")
    
    return {
        'total_stuck': len(stuck_jobs.data or []),
        'retried': len(retried),
        'failed': len(failed),
        'skipped': len(skipped),
        'details': {
            'retried': retried,
            'failed': failed,
            'skipped': skipped
        }
    }


@router.post("/cleanup-stuck-jobs", dependencies=[Depends(RoleChecker(["admin"]))])
async def manual_cleanup_stuck_jobs(current_user: AuthUser = Depends(get_current_user)):
    """
    Manually trigger the automated cleanup task for stuck analysis jobs.
    
    This endpoint runs the same logic as the automated Celery Beat task
    `cleanup_stuck_analysis_jobs`, but can be triggered on-demand by admins.
    
    Use cases:
    - Immediately fix stuck jobs without waiting for the 15-minute schedule
    - Test the cleanup logic after debugging
    - Run cleanup after recovering from Celery/Redis outages
    
    Returns:
        dict: Cleanup statistics including jobs cleaned, still valid, and errors
    """
    try:
        from celery_worker import cleanup_stuck_analysis_jobs
        
        # Trigger the cleanup task synchronously (not async)
        # This returns the result immediately rather than a task ID
        result = cleanup_stuck_analysis_jobs.apply().get(timeout=60)
        
        return {
            "status": "success",
            "message": f"Cleanup completed: {result.get('cleaned_up', 0)} jobs cleaned",
            "details": result
        }
        
    except Exception as e:
        logger.error(f"Manual cleanup failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup task failed: {str(e)}"
        )
