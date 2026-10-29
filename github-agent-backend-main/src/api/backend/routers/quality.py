"""
Commit Quality API Router
Endpoints for checking commit quality and sending alerts
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field
import logging

from ..middleware import get_current_user, RoleChecker, AuthUser
from ..database import get_supabase_admin_client
from ..services.commit_quality_service import CommitQualityService
from ..services.email_service import EmailService
from ..models.quality_models import AlertSummary, AlertResult

router = APIRouter(prefix="/api/quality", tags=["Commit Quality"])
logger = logging.getLogger(__name__)


# Request/Response Models
class SendAlertsRequest(BaseModel):
    team_ids: List[str] = Field(..., description="List of team UUIDs")
    threshold: Optional[float] = Field(30.0, description="Quality threshold (0-100)")
    force: bool = Field(False, description="Force send even if recently sent")


@router.get("/batch/{batch_id}")
async def get_batch_quality(
    batch_id: UUID,
    threshold: float = Query(30.0, ge=0, le=100, description="Quality threshold percentage"),
    current_user: AuthUser = Depends(RoleChecker(["admin", "mentor"]))
):
    """
    Get commit quality metrics for all teams in a batch
    
    Returns quality metrics for each team including:
    - fake_commit_ratio
    - commit_health
    - requires_alert (based on threshold)
    - fake_commit_count
    - total_commits
    """
    supabase = get_supabase_admin_client()
    
    try:
        # Verify batch exists
        batch_response = supabase.table("batches").select("id, name").eq("id", str(batch_id)).single().execute()
        if not batch_response.data:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # Get all teams in batch
        teams_response = supabase.table("teams").select(
            "id, team_name, report_json"
        ).eq("batch_id", str(batch_id)).execute()
        
        if not teams_response.data:
            return {
                "batch_id": str(batch_id),
                "threshold": threshold,
                "teams": [],
                "summary": {
                    "total_teams": 0,
                    "teams_requiring_alerts": 0,
                    "critical_teams": 0,
                    "at_risk_teams": 0,
                    "healthy_teams": 0
                }
            }
        
        teams_data = []
        teams_requiring_alerts = 0
        critical_teams = 0
        at_risk_teams = 0
        healthy_teams = 0
        
        for team in teams_response.data:
            team_id = team["id"]
            team_name = team["team_name"]
            
            try:
                # Extract forensics
                forensics = CommitQualityService.extract_forensics_data(team_id)
                
                if not forensics:
                    teams_data.append({
                        "team_id": team_id,
                        "team_name": team_name,
                        "status": "No Data",
                        "fake_commit_ratio": 0,
                        "commit_health": "Unknown",
                        "requires_alert": False,
                        "fake_commit_count": 0,
                        "total_commits": 0
                    })
                    continue
                
                # Evaluate quality
                evaluation = CommitQualityService.evaluate_quality_threshold(forensics, threshold)
                
                teams_data.append({
                    "team_id": team_id,
                    "team_name": team_name,
                    "fake_commit_ratio": round(forensics.fake_commit_ratio, 1),
                    "commit_health": forensics.commit_health,
                    "requires_alert": evaluation.requires_alert,
                    "alert_priority": evaluation.alert_priority,
                    "fake_commit_count": forensics.fake_commit_count,
                    "total_commits": forensics.total_commits,
                    "dummy_commits": forensics.dummy_commits
                })
                
                # Update summary counts
                if evaluation.requires_alert:
                    teams_requiring_alerts += 1
                
                if forensics.commit_health == "Critical":
                    critical_teams += 1
                elif forensics.commit_health == "At Risk":
                    at_risk_teams += 1
                elif forensics.commit_health == "Healthy":
                    healthy_teams += 1
                    
            except Exception as e:
                logger.error(f"Error processing team {team_id}: {e}")
                teams_data.append({
                    "team_id": team_id,
                    "team_name": team_name,
                    "status": "Error",
                    "error": str(e),
                    "fake_commit_ratio": 0,
                    "commit_health": "Unknown",
                    "requires_alert": False
                })
        
        # Sort by fake_commit_ratio descending
        teams_data.sort(key=lambda x: x.get("fake_commit_ratio", 0), reverse=True)
        
        return {
            "batch_id": str(batch_id),
            "batch_name": batch_response.data["name"],
            "threshold": threshold,
            "teams": teams_data,
            "summary": {
                "total_teams": len(teams_response.data),
                "teams_requiring_alerts": teams_requiring_alerts,
                "critical_teams": critical_teams,
                "at_risk_teams": at_risk_teams,
                "healthy_teams": healthy_teams
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting batch quality for {batch_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/send")
async def send_quality_alerts(
    request: SendAlertsRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(RoleChecker(["admin"]))
):
    """
    Manually trigger quality alerts for specific teams
    
    Evaluates each team's quality and sends alerts to those exceeding threshold.
    Returns summary of sent/skipped/failed alerts.
    """
    email_service = EmailService()
    
    try:
        results = []
        sent_count = 0
        skipped_count = 0
        failed_count = 0

        # Pre-fetch all team names in one query
        supabase = get_supabase_admin_client()
        team_name_rows = supabase.table("teams").select("id, team_name")\
            .in_("id", request.team_ids).execute().data or []
        team_name_map = {r["id"]: r["team_name"] for r in team_name_rows}
        
        for team_id in request.team_ids:
            try:
                # Extract forensics
                forensics = CommitQualityService.extract_forensics_data(team_id)
                
                if not forensics:
                    results.append(AlertResult(
                        team_id=team_id,
                        team_name="Unknown",
                        status="failed",
                        reason="No forensics data available"
                    ))
                    failed_count += 1
                    continue
                
                # Get team name from pre-fetched map
                team_name = team_name_map.get(team_id, "Unknown")
                
                # Evaluate quality
                evaluation = CommitQualityService.evaluate_quality_threshold(forensics, request.threshold)
                
                if not evaluation.requires_alert and not request.force:
                    results.append(AlertResult(
                        team_id=team_id,
                        team_name=team_name,
                        status="skipped",
                        reason="Quality threshold not exceeded",
                        fake_commit_ratio=forensics.fake_commit_ratio
                    ))
                    skipped_count += 1
                    continue
                
                # Send alert
                result = await email_service.send_quality_alert(
                    team_id=team_id,
                    team_name=team_name,
                    forensics=forensics,
                    threshold=request.threshold,
                    force=request.force
                )
                
                results.append(result)
                
                if result.status == "sent":
                    sent_count += 1
                elif result.status == "skipped":
                    skipped_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing team {team_id}: {e}")
                results.append(AlertResult(
                    team_id=team_id,
                    team_name="Unknown",
                    status="failed",
                    reason=str(e)
                ))
                failed_count += 1
        
        return {
            "requested": len(request.team_ids),
            "sent": sent_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "threshold_used": request.threshold,
            "results": [
                {
                    "team_id": r.team_id,
                    "team_name": r.team_name,
                    "status": r.status,
                    "reason": r.reason,
                    "fake_commit_ratio": r.fake_commit_ratio,
                    "email_count": r.email_count
                }
                for r in results
            ]
        }
        
    except Exception as e:
        logger.error(f"Error sending quality alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rankings/{batch_id}")
async def get_quality_rankings(
    batch_id: UUID,
    current_user: AuthUser = Depends(RoleChecker(["admin", "mentor"]))
):
    """
    Get teams ranked by commit quality (worst first)
    
    Returns teams sorted by fake_commit_ratio in descending order
    """
    try:
        # Verify batch exists
        supabase = get_supabase_admin_client()
        batch_response = supabase.table("batches").select("id, name").eq("id", str(batch_id)).single().execute()
        if not batch_response.data:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # Get rankings
        rankings = CommitQualityService.rank_teams_by_quality(str(batch_id))
        
        return {
            "batch_id": str(batch_id),
            "batch_name": batch_response.data["name"],
            "rankings": [
                {
                    "rank": r.rank,
                    "team_id": r.team_id,
                    "team_name": r.team_name,
                    "fake_commit_ratio": round(r.fake_commit_ratio, 1),
                    "commit_health": r.commit_health,
                    "fake_commit_count": r.fake_commit_count,
                    "total_commits": r.total_commits
                }
                for r in rankings
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting quality rankings for {batch_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{team_id}")
async def get_alert_history(
    team_id: UUID,
    current_user: AuthUser = Depends(RoleChecker(["admin", "mentor"]))
):
    """
    Get alert history for a specific team
    
    Returns list of alerts sent to the team with timestamps and metrics
    """
    supabase = get_supabase_admin_client()
    
    try:
        # Verify team exists
        team_response = supabase.table("teams").select("id, team_name").eq("id", str(team_id)).single().execute()
        if not team_response.data:
            raise HTTPException(status_code=404, detail="Team not found")
        
        # Get alert history
        alerts_response = supabase.table("quality_alerts").select(
            "id, sent_at, fake_commit_ratio, fake_commit_count, commit_health, total_commits, threshold_used, email_recipients"
        ).eq("team_id", str(team_id)).order("sent_at", desc=True).execute()
        
        return {
            "team_id": str(team_id),
            "team_name": team_response.data["team_name"],
            "alerts": [
                {
                    "id": alert["id"],
                    "sent_at": alert["sent_at"],
                    "fake_commit_ratio": round(alert["fake_commit_ratio"], 1),
                    "fake_commit_count": alert["fake_commit_count"],
                    "commit_health": alert["commit_health"],
                    "total_commits": alert["total_commits"],
                    "threshold_used": alert["threshold_used"],
                    "recipient_count": len(alert.get("email_recipients", []))
                }
                for alert in alerts_response.data
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alert history for {team_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
