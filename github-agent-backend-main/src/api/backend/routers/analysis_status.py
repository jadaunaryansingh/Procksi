"""
Real-time Analysis Status Tracking
Syncs analytics UI with Celery background jobs
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from typing import Optional, Dict, Any
import json
import asyncio
from datetime import datetime

from ..middleware.auth import get_current_user, AuthUser
from ..database import get_supabase_admin_client
from celery.result import AsyncResult
from celery_app import celery_app

router = APIRouter(prefix="/api/analysis", tags=["analysis-status"])


@router.get("/job/{job_id}/status")
async def get_job_realtime_status(
    job_id: str,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get real-time status of analysis job including Celery task state.
    Combines database status with Celery worker status.
    """
    supabase = get_supabase_admin_client()
    
    # Get job from database (projects table has been dropped)
    # team_id is now directly in analysis_jobs table
    job_response = supabase.table("analysis_jobs").select(
        "*, teams!inner(id, batch_id)"
    ).eq("id", job_id).execute()
    
    if not job_response.data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_response.data[0]
    
    # Get Celery task status if task_id exists
    celery_task_id = job.get("metadata", {}).get("celery_task_id")
    celery_status = None
    celery_info = None
    
    if celery_task_id:
        try:
            task_result = AsyncResult(celery_task_id, app=celery_app)
            celery_status = task_result.state  # PENDING, STARTED, SUCCESS, FAILURE, RETRY
            
            # Get task info (progress, current stage)
            if task_result.info:
                if isinstance(task_result.info, dict):
                    celery_info = task_result.info
                elif task_result.state == "FAILURE":
                    celery_info = {"error": str(task_result.info)}
            
            # Check if task is stuck (db says "running" but celery says "pending")
            if job["status"] == "running" and celery_status == "PENDING":
                # Task lost - mark as failed
                supabase.table("analysis_jobs").update({
                    "status": "failed",
                    "error_message": "Worker lost connection",
                    "completed_at": datetime.now().isoformat()
                }).eq("id", job_id).execute()
                
                job["status"] = "failed"
                job["error_message"] = "Worker lost connection"
                
        except Exception as e:
            print(f"[WARNING] Failed to get Celery status for task {celery_task_id}: {e}")
    
    # Build response (projects table has been dropped)
    teams_data = job.get("teams", {})
    response = {
        "jobId": job_id,
        "projectId": str(job["team_id"]),  # For backward compatibility
        "teamId": str(job["team_id"]),
        "batchId": str(teams_data.get("batch_id")) if teams_data else None,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "currentStage": job.get("current_stage"),
        "errorMessage": job.get("error_message"),
        "startedAt": job.get("started_at"),
        "completedAt": job.get("completed_at"),
        "retryCount": job.get("metadata", {}).get("retry_count", 0),
        
        # Celery real-time status
        "celery": {
            "taskId": celery_task_id,
            "state": celery_status,
            "info": celery_info,
            "isActive": celery_status in ["PENDING", "STARTED", "RETRY"]
        } if celery_task_id else None
    }
    
    return response


@router.websocket("/ws/job/{job_id}")
async def websocket_job_status(
    websocket: WebSocket,
    job_id: str
):
    """
    WebSocket endpoint for real-time job status updates.
    Pushes updates every 2 seconds while job is running.
    """
    await websocket.accept()
    
    try:
        while True:
            # Get current status (projects table has been dropped)
            supabase = get_supabase_admin_client()
            job_response = supabase.table("analysis_jobs").select(
                "*, teams!inner(id)"
            ).eq("id", job_id).execute()
            
            if not job_response.data:
                await websocket.send_json({"error": "Job not found"})
                break
            
            job = job_response.data[0]
            
            # Get Celery status
            celery_task_id = job.get("metadata", {}).get("celery_task_id")
            celery_state = None
            
            if celery_task_id:
                try:
                    task_result = AsyncResult(celery_task_id, app=celery_app)
                    celery_state = task_result.state
                except Exception:
                    pass
            
            # Send update
            await websocket.send_json({
                "jobId": job_id,
                "status": job["status"],
                "progress": job.get("progress", 0),
                "currentStage": job.get("current_stage"),
                "celeryState": celery_state,
                "timestamp": datetime.now().isoformat()
            })
            
            # Stop if completed or failed
            if job["status"] in ["completed", "failed"]:
                break
            
            # Wait 2 seconds before next update
            await asyncio.sleep(2)
            
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for job {job_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.close()


@router.get("/batch/{batch_id}/progress")
async def get_batch_analysis_progress(
    batch_id: str,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get progress of batch analysis (for weekly automatic runs).
    Shows which teams are being analyzed and overall progress.
    """
    supabase = get_supabase_admin_client()
    
    # Get latest batch run
    batch_run = supabase.table("batch_analysis_runs").select(
        "*"
    ).eq("batch_id", batch_id).order("run_number", desc=True).limit(1).execute()
    
    if not batch_run.data:
        return {
            "batchId": batch_id,
            "status": "no_runs",
            "progress": 0,
            "currentRun": None
        }
    
    run = batch_run.data[0]
    
    # Get team-level job statuses (projects table has been dropped)
    jobs = supabase.table("analysis_jobs").select(
        "id, team_id, status, progress, current_stage, metadata, teams!inner(team_name)"
    ).eq("batch_id", batch_id).eq("run_number", run["run_number"]).execute()
    
    # Count statuses
    total = len(jobs.data) if jobs.data else run["total_teams"]
    completed = sum(1 for j in jobs.data if j["status"] == "completed") if jobs.data else run["completed_teams"]
    failed = sum(1 for j in jobs.data if j["status"] == "failed") if jobs.data else run["failed_teams"]
    running = sum(1 for j in jobs.data if j["status"] in ["pending", "running"]) if jobs.data else 0
    
    # Get currently running teams (projects table has been dropped)
    running_teams = []
    if jobs.data:
        for job in jobs.data:
            if job["status"] in ["pending", "running"]:
                teams_data = job.get("teams", {})
                running_teams.append({
                    "jobId": job["id"],
                    "teamId": str(job["team_id"]),
                    "teamName": teams_data.get("team_name", "Unknown") if teams_data else "Unknown",
                    "status": job["status"],
                    "progress": job.get("progress", 0),
                    "stage": job.get("current_stage"),
                    "celeryTaskId": job.get("metadata", {}).get("celery_task_id")
                })
    
    return {
        "batchId": batch_id,
        "runNumber": run["run_number"],
        "status": run["status"],
        "progress": round((completed / total * 100) if total > 0 else 0, 1),
        "stats": {
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": total - completed - failed - running
        },
        "runningTeams": running_teams,
        "startedAt": run.get("started_at"),
        "completedAt": run.get("completed_at"),
        "avgScore": run.get("avg_score")
    }
