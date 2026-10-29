"""
Duplicate Commits Detection Router
API endpoints for detecting and alerting on duplicate commits
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import Optional, List
from uuid import UUID
import logging
import json

from ..middleware import get_current_user, RoleChecker, AuthUser
from ..database import get_supabase_admin_client
from ..services.duplicate_commit_detector import DuplicateCommitDetector
from ..services.email_service import EmailService
from ..utils.report_storage import ReportStorageManager

router = APIRouter(prefix="/api/duplicate-commits", tags=["Duplicate Commits"])
logger = logging.getLogger(__name__)


@router.post("/detect/{batch_id}")
async def detect_duplicate_commits(
    batch_id: UUID,
    send_alerts: bool = Query(False, description="Send email alerts to affected teams"),
    background_tasks: BackgroundTasks = None,
    current_user: AuthUser = Depends(RoleChecker(["admin"]))
):
    """
    Detect duplicate commits across teams in a batch
    
    Admin only endpoint that:
    1. Analyzes all teams in the batch
    2. Finds commits that appear in multiple teams
    3. Optionally sends email alerts to affected teams
    """
    supabase = get_supabase_admin_client()
    
    try:
        # Check if batch exists
        logger.info(f"Checking if batch {batch_id} exists")
        batch_check = supabase.table("batches").select("id").eq("id", str(batch_id)).execute()
        logger.info(f"Batch check result: {batch_check.data}")
        if not batch_check.data:
            logger.warning(f"Batch {batch_id} not found in database")
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # Get all teams in the batch with their analysis results
        teams_response = supabase.table("teams").select(
            "id, team_name, report_json, report_path, repo_url"
        ).eq("batch_id", str(batch_id)).execute()
        
        teams_data = teams_response.data or []
        logger.info(f"Analyzing {len(teams_data)} teams for duplicate commits")
        
        # Enrich teams_data with report from storage if migrated
        for team in teams_data:
            team["report_json"] = ReportStorageManager.get_report_for_team(team)
        
        # If no teams in batch, return success with no duplicates
        if not teams_data:
            return {
                "success": True,
                "message": "No teams found in batch",
                "summary": {
                    "total_incidents": 0,
                    "total_commits": 0,
                    "total_teams_affected": 0,
                    "by_severity": {}
                },
                "incidents": []
            }
        
        # Find duplicate commits
        duplicate_commits = DuplicateCommitDetector.find_duplicate_commits(teams_data)
        
        if not duplicate_commits:
            return {
                "success": True,
                "message": "No duplicate commits found",
                "summary": {
                    "total_incidents": 0,
                    "total_commits": 0,
                    "total_teams_affected": 0,
                    "by_severity": {}
                },
                "incidents": []
            }
        
        # Analyze severity
        incidents = DuplicateCommitDetector.analyze_duplicate_severity(duplicate_commits)
        summary = DuplicateCommitDetector.generate_alert_summary(incidents)
        
        logger.info(f"Found {len(incidents)} duplicate commit incidents affecting {summary['total_teams_affected']} teams")
        
        # Send alerts if requested
        if send_alerts and background_tasks:
            background_tasks.add_task(
                send_duplicate_commit_alerts,
                batch_id=str(batch_id),
                incidents=incidents
            )
            message = f"Found {len(incidents)} duplicate commit incidents. Email alerts are being sent."
        else:
            message = f"Found {len(incidents)} duplicate commit incidents."
        
        return {
            "success": True,
            "message": message,
            "summary": summary,
            "incidents": incidents[:50]  # Limit to first 50 for response size
        }
    
    except Exception as e:
        logger.error(f"Error detecting duplicate commits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def send_duplicate_commit_alerts(batch_id: str, incidents: List[dict]):
    """
    Background task to send email alerts to teams with duplicate commits
    """
    supabase = get_supabase_admin_client()
    email_service = EmailService()
    
    try:
        # Group incidents by team
        team_incidents = {}
        for incident in incidents:
            for team in incident["teams"]:
                team_id = team["team_id"]
                if team_id not in team_incidents:
                    team_incidents[team_id] = []
                team_incidents[team_id].append(incident)
        
        logger.info(f"Sending duplicate commit alerts to {len(team_incidents)} teams")
        
        # Send email to each affected team
        for team_id, team_incidents_list in team_incidents.items():
            try:
                # Get team details and student emails
                team_response = supabase.table("teams").select(
                    "id, team_name, repo_url"
                ).eq("id", team_id).single().execute()
                
                if not team_response.data:
                    continue
                
                team = team_response.data
                
                # Get student emails
                students_response = supabase.table("students").select(
                    "name, email"
                ).eq("team_id", team_id).execute()
                
                student_emails = [
                    s["email"] for s in students_response.data 
                    if s.get("email")
                ]
                
                if not student_emails:
                    logger.warning(f"No student emails found for team {team['team_name']}")
                    continue
                
                # Send alert email
                await email_service.send_duplicate_commit_alert(
                    team_name=team["team_name"],
                    repo_url=team.get("repo_url", ""),
                    incidents=team_incidents_list,
                    recipient_emails=student_emails
                )
                
                logger.info(f"Sent duplicate commit alert to team {team['team_name']}")
            
            except Exception as e:
                logger.error(f"Error sending alert to team {team_id}: {e}")
                continue
        
        logger.info("Finished sending duplicate commit alerts")
    
    except Exception as e:
        logger.error(f"Error in send_duplicate_commit_alerts: {e}")


@router.get("/summary/{batch_id}")
async def get_duplicate_commits_summary(
    batch_id: UUID,
    current_user: AuthUser = Depends(RoleChecker(["admin", "mentor"]))
):
    """
    Get summary of duplicate commits for a batch
    Quick endpoint that just returns counts without full details
    """
    supabase = get_supabase_admin_client()
    
    try:
        # Get all teams in the batch
        teams_response = supabase.table("teams").select(
            "id, team_name, report_json"
        ).eq("batch_id", str(batch_id)).execute()
        
        if not teams_response.data:
            return {
                "batch_id": str(batch_id),
                "total_teams": 0,
                "duplicate_incidents": 0,
                "teams_affected": 0
            }
        
        teams_data = teams_response.data
        
        # Find duplicates
        duplicate_commits = DuplicateCommitDetector.find_duplicate_commits(teams_data)
        incidents = DuplicateCommitDetector.analyze_duplicate_severity(duplicate_commits)
        summary = DuplicateCommitDetector.generate_alert_summary(incidents)
        
        return {
            "batch_id": str(batch_id),
            "total_teams": len(teams_data),
            "duplicate_incidents": summary["total_incidents"],
            "teams_affected": summary["total_teams_affected"],
            "by_severity": summary["by_severity"]
        }
    
    except Exception as e:
        logger.error(f"Error getting duplicate commits summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
