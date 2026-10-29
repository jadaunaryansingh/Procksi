"""
Inactivity Alert System API
Detects and alerts teams that haven't been committing code
"""

from fastapi import APIRouter, Depends, HTTPException, Path
from typing import Dict, Any, Optional
from datetime import datetime

from ..middleware.auth import get_current_user
from ..database import get_supabase, get_supabase_admin_client
from ..utils.email import send_alert_email
from ..services.inactivity_detector import InactivityDetector
from ..templates.email_templates import EmailTemplates

router = APIRouter(prefix="/api/inactivity", tags=["inactivity"])


@router.post("/check-batch/{batchId}")
async def check_batch_inactivity(
    batchId: str = Path(..., description="Batch ID"),
    warning_threshold: Optional[int] = 7,
    critical_threshold: Optional[int] = 14,
    current_user: dict = Depends(get_current_user)
):
    """
    Check all teams in a batch for inactivity.
    
    Returns summary of inactive teams with severity levels.
    Admin only.
    
    Query Parameters:
    - warning_threshold: Days before warning alert (default: 7)
    - critical_threshold: Days before critical alert (default: 14)
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Get all teams in batch with relevant data
    teams_response = supabase.table("teams").select(
        "id, team_name, last_commit_date, is_private, status, last_inactivity_alert, inactivity_alert_count, repo_url"
    ).eq("batch_id", batchId).execute()
    
    teams = teams_response.data or []
    
    if not teams:
        return {
            "success": True,
            "message": "No teams found in this batch",
            "totalTeams": 0,
            "inactiveTeams": 0,
            "warningCount": 0,
            "criticalCount": 0,
            "excludedCount": 0,
            "details": []
        }
    
    # Detect inactivity
    detection_result = InactivityDetector.detect_batch_inactivity(
        teams,
        warning_threshold,
        critical_threshold
    )
    
    # Format results for API response
    details = []
    for result in detection_result["results"]:
        details.append({
            "teamId": result.team_id,
            "teamName": result.team_name,
            "daysInactive": result.days_inactive,
            "lastCommitDate": result.last_commit_date,
            "severity": result.severity,
            "reason": result.reason
        })
    
    return {
        "success": True,
        "message": f"Found {detection_result['inactive_teams']} inactive teams",
        "totalTeams": detection_result["total_teams"],
        "inactiveTeams": detection_result["inactive_teams"],
        "warningCount": detection_result["warning_count"],
        "criticalCount": detection_result["critical_count"],
        "excludedCount": detection_result["excluded_count"],
        "details": details
    }


@router.get("/list-inactive/{batchId}")
async def list_inactive_teams(
    batchId: str = Path(..., description="Batch ID"),
    warning_threshold: Optional[int] = 7,
    critical_threshold: Optional[int] = 14,
    current_user: dict = Depends(get_current_user)
):
    """
    Get detailed list of inactive teams with student emails.
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Get all teams with student data
    teams_response = supabase.table("teams").select(
        "id, team_name, last_commit_date, is_private, status, last_inactivity_alert, "
        "inactivity_alert_count, repo_url, students(name, email)"
    ).eq("batch_id", batchId).execute()
    
    teams = teams_response.data or []
    
    # Detect inactivity
    detection_result = InactivityDetector.detect_batch_inactivity(
        teams,
        warning_threshold,
        critical_threshold
    )
    
    # Separate by severity
    warning_teams = []
    critical_teams = []
    
    for result in detection_result["results"]:
        # Find team data to get students
        team_data = next((t for t in teams if t["id"] == result.team_id), None)
        if not team_data:
            continue
        
        students = team_data.get("students", [])
        student_emails = [s.get("email") for s in students if s.get("email")]
        
        # Check if alert should be sent (cooldown check)
        should_send = InactivityDetector.should_send_alert(team_data)
        
        team_info = {
            "teamId": result.team_id,
            "teamName": result.team_name,
            "daysInactive": result.days_inactive,
            "lastCommitDate": result.last_commit_date,
            "severity": result.severity,
            "reason": result.reason,
            "studentCount": len(students),
            "studentEmails": student_emails,
            "lastAlertSent": team_data.get("last_inactivity_alert"),
            "alertCount": team_data.get("inactivity_alert_count", 0),
            "shouldSendAlert": should_send,
            "repoUrl": team_data.get("repo_url")
        }
        
        if result.severity == "critical":
            critical_teams.append(team_info)
        else:
            warning_teams.append(team_info)
    
    return {
        "success": True,
        "totalInactiveTeams": len(warning_teams) + len(critical_teams),
        "warningTeams": warning_teams,
        "criticalTeams": critical_teams,
        "warningCount": len(warning_teams),
        "criticalCount": len(critical_teams)
    }


@router.post("/send-alerts/{batchId}")
async def send_inactivity_alerts(
    batchId: str = Path(..., description="Batch ID"),
    warning_threshold: Optional[int] = 7,
    critical_threshold: Optional[int] = 14,
    force: Optional[bool] = False,
    current_user: dict = Depends(get_current_user)
):
    """
    Send inactivity alerts to all inactive teams in a batch.
    
    Respects cooldown period unless force=true.
    Admin only.
    
    Query Parameters:
    - warning_threshold: Days before warning alert (default: 7)
    - critical_threshold: Days before critical alert (default: 14)
    - force: Send alerts even if in cooldown period (default: false)
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Get all teams with student data
    teams_response = supabase.table("teams").select(
        "id, team_name, last_commit_date, is_private, status, last_inactivity_alert, "
        "inactivity_alert_count, students(name, email)"
    ).eq("batch_id", batchId).execute()
    
    teams = teams_response.data or []
    
    # Detect inactivity
    detection_result = InactivityDetector.detect_batch_inactivity(
        teams,
        warning_threshold,
        critical_threshold
    )
    
    emails_sent = 0
    emails_failed = 0
    emails_skipped = 0
    details = []
    
    for result in detection_result["results"]:
        # Find team data
        team_data = next((t for t in teams if t["id"] == result.team_id), None)
        if not team_data:
            continue
        
        team_id = result.team_id
        team_name = result.team_name
        students = team_data.get("students", [])
        student_emails = [s.get("email") for s in students if s.get("email")]
        
        # Check cooldown unless force=true
        if not force and not InactivityDetector.should_send_alert(team_data):
            emails_skipped += 1
            details.append({
                "teamId": team_id,
                "teamName": team_name,
                "severity": result.severity,
                "status": "skipped",
                "reason": "Alert sent recently (cooldown period)"
            })
            continue
        
        # Check if team has student emails
        if not student_emails:
            emails_failed += 1
            details.append({
                "teamId": team_id,
                "teamName": team_name,
                "severity": result.severity,
                "status": "failed",
                "error": "No student emails found"
            })
            continue
        
        # Format last commit date for email
        last_commit_display = result.last_commit_date if result.last_commit_date else "Never"
        if result.last_commit_date:
            try:
                commit_dt = datetime.fromisoformat(result.last_commit_date.replace('Z', '+00:00'))
                last_commit_display = commit_dt.strftime("%B %d, %Y")
            except:
                pass
        
        # Generate email content
        alert_count = team_data.get("inactivity_alert_count", 0) or 0
        subject = EmailTemplates.inactive_team_alert_subject(team_name, result.severity)
        email_result = EmailTemplates.inactive_team_alert_body(
            team_name,
            result.days_inactive,
            last_commit_display,
            result.severity,
            alert_count
        )
        email_body = email_result.get("text", "") if isinstance(email_result, dict) else email_result
        email_html = email_result.get("html") if isinstance(email_result, dict) else None
        
        # Send email to each student
        team_sent = 0
        team_failed = []
        
        for email in student_emails:
            try:
                send_alert_email(
                    subject=subject,
                    body_text=email_body,
                    to_email=email,
                    html_body=email_html
                )
                team_sent += 1
            except Exception as e:
                print(f"Failed to send email to {email}: {e}")
                team_failed.append(email)
        
        if team_sent > 0:
            # Update team record
            current_alert_count = team_data.get("inactivity_alert_count", 0)
            supabase.table("teams").update({
                "last_inactivity_alert": datetime.utcnow().isoformat(),
                "inactivity_alert_count": current_alert_count + 1
            }).eq("id", team_id).execute()
            
            # Log to alert_history
            try:
                supabase.table("alert_history").insert({
                    "team_id": team_id,
                    "alert_type": "inactivity",
                    "severity": result.severity,
                    "recipient_count": team_sent,
                    "delivery_status": "sent" if not team_failed else "partial",
                    "metadata": {
                        "days_inactive": result.days_inactive,
                        "last_commit_date": result.last_commit_date,
                        "failed_emails": team_failed if team_failed else None
                    }
                }).execute()
            except Exception as e:
                print(f"Failed to log alert history: {e}")
            
            emails_sent += team_sent
            details.append({
                "teamId": team_id,
                "teamName": team_name,
                "severity": result.severity,
                "status": "success",
                "sentTo": team_sent,
                "failedEmails": team_failed if team_failed else None
            })
        else:
            emails_failed += 1
            details.append({
                "teamId": team_id,
                "teamName": team_name,
                "severity": result.severity,
                "status": "failed",
                "error": f"Failed to send to all recipients: {', '.join(team_failed)}"
            })
    
    return {
        "success": True,
        "message": f"Sent {emails_sent} inactivity alerts",
        "totalInactiveTeams": len(detection_result["results"]),
        "emailsSent": emails_sent,
        "emailsFailed": emails_failed,
        "emailsSkipped": emails_skipped,
        "details": details
    }


@router.post("/send-individual-alert")
async def send_individual_inactivity_alert(
    request_body: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Send inactivity alert to a specific team.
    
    Request body:
    {
        "teamId": "team-uuid",
        "force": false  // Optional: bypass cooldown check
    }
    
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    team_id = request_body.get("teamId")
    force = request_body.get("force", False)
    
    if not team_id:
        raise HTTPException(status_code=400, detail="teamId is required")
    
    supabase = get_supabase()
    
    # Get team data
    team_response = supabase.table("teams").select(
        "id, team_name, last_commit_date, is_private, status, last_inactivity_alert, "
        "inactivity_alert_count, students(name, email)"
    ).eq("id", team_id).execute()
    
    teams = team_response.data or []
    
    if not teams:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = teams[0]
    
    # Detect inactivity for this team
    result = InactivityDetector.detect_team_inactivity(team)
    
    # Check if team is actually inactive
    if not result.is_inactive:
        return {
            "success": False,
            "message": f"Team is not inactive ({result.reason})",
            "emailsSent": 0
        }
    
    # Check if team has repo issues
    if result.has_repo_issues:
        return {
            "success": False,
            "message": "Team has repository issues (use repo privacy alerts instead)",
            "emailsSent": 0
        }
    
    # Check cooldown unless force=true
    if not force and not InactivityDetector.should_send_alert(team):
        return {
            "success": False,
            "message": "Alert sent recently (cooldown period). Use force=true to override.",
            "emailsSent": 0
        }
    
    # Get student emails
    students = team.get("students", [])
    student_emails = [s.get("email") for s in students if s.get("email")]
    
    if not student_emails:
        return {
            "success": False,
            "message": "No student emails found for this team",
            "emailsSent": 0
        }
    
    # Format last commit date
    last_commit_display = result.last_commit_date if result.last_commit_date else "Never"
    if result.last_commit_date:
        try:
            commit_dt = datetime.fromisoformat(result.last_commit_date.replace('Z', '+00:00'))
            last_commit_display = commit_dt.strftime("%B %d, %Y")
        except:
            pass
    
    # Generate email content
    alert_count = team.get("inactivity_alert_count", 0) or 0
    subject = EmailTemplates.inactive_team_alert_subject(result.team_name, result.severity)
    email_result = EmailTemplates.inactive_team_alert_body(
        result.team_name,
        result.days_inactive,
        last_commit_display,
        result.severity,
        alert_count
    )
    email_body = email_result.get("text", "") if isinstance(email_result, dict) else email_result
    email_html = email_result.get("html") if isinstance(email_result, dict) else None
    
    # Send emails
    emails_sent = 0
    failed_emails = []
    
    for email in student_emails:
        try:
            send_alert_email(
                subject=subject,
                body_text=email_body,
                to_email=email,
                html_body=email_html
            )
            emails_sent += 1
        except Exception as e:
            print(f"Failed to send email to {email}: {e}")
            failed_emails.append(email)
    
    if emails_sent > 0:
        # Update team record
        current_alert_count = team.get("inactivity_alert_count", 0)
        supabase.table("teams").update({
            "last_inactivity_alert": datetime.utcnow().isoformat(),
            "inactivity_alert_count": current_alert_count + 1
        }).eq("id", team_id).execute()
        
        # Log to alert_history
        try:
            supabase.table("alert_history").insert({
                "team_id": team_id,
                "alert_type": "inactivity",
                "severity": result.severity,
                "recipient_count": emails_sent,
                "delivery_status": "sent" if not failed_emails else "partial",
                "metadata": {
                    "days_inactive": result.days_inactive,
                    "last_commit_date": result.last_commit_date,
                    "failed_emails": failed_emails if failed_emails else None
                }
            }).execute()
        except Exception as e:
            print(f"Failed to log alert history: {e}")
        
        return {
            "success": True,
            "message": f"Sent inactivity alert to {result.team_name}",
            "emailsSent": emails_sent,
            "failedEmails": failed_emails if failed_emails else None
        }
    else:
        return {
            "success": False,
            "message": "Failed to send emails to all recipients",
            "emailsSent": 0,
            "failedEmails": failed_emails
        }


@router.get("/alert-history/{batchId}")
async def get_alert_history(
    batchId: str = Path(..., description="Batch ID"),
    alert_type: Optional[str] = "inactivity",
    current_user: dict = Depends(get_current_user)
):
    """
    Get alert history for all teams in a batch.
    
    Query Parameters:
    - alert_type: Filter by alert type (default: "inactivity")
    
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Get all teams in batch
    teams_response = supabase.table("teams").select("id, team_name").eq("batch_id", batchId).execute()
    teams = teams_response.data or []
    team_ids = [t["id"] for t in teams]
    
    if not team_ids:
        return {
            "success": True,
            "totalAlerts": 0,
            "alerts": []
        }
    
    # Get alert history
    query = supabase.table("alert_history").select(
        "id, team_id, alert_type, severity, sent_at, recipient_count, delivery_status, metadata"
    ).in_("team_id", team_ids).order("sent_at", desc=True)
    
    if alert_type:
        query = query.eq("alert_type", alert_type)
    
    alerts_response = query.execute()
    alerts = alerts_response.data or []
    
    # Enrich with team names
    team_map = {t["id"]: t["team_name"] for t in teams}
    for alert in alerts:
        alert["teamName"] = team_map.get(alert["team_id"], "Unknown")
    
    return {
        "success": True,
        "totalAlerts": len(alerts),
        "alerts": alerts
    }


@router.get("/mentor-activity/{batchId}")
async def get_mentor_activity(
    batchId: str = Path(..., description="Batch ID"),
    warning_threshold: Optional[int] = 7,
    critical_threshold: Optional[int] = 14,
    current_user: dict = Depends(get_current_user)
):
    """
    Get team activity grouped by mentor for a batch.
    
    Returns each mentor with their total, active, and inactive team counts
    plus per-team inactivity details.
    Admin only.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    admin_supabase = get_supabase_admin_client()
    
    # Get all teams in batch with mentor_id and commit data
    teams_response = supabase.table("teams").select(
        "id, team_name, mentor_id, last_commit_date, is_private, status, "
        "last_inactivity_alert, inactivity_alert_count, repo_url, health_status"
    ).eq("batch_id", batchId).execute()
    
    teams = teams_response.data or []
    
    if not teams:
        return {
            "success": True,
            "mentors": [],
            "summary": {
                "totalMentors": 0,
                "mentorsWithInactiveTeams": 0,
                "mentorsAllActive": 0,
                "totalInactiveTeams": 0
            }
        }
    
    # Detect inactivity for all teams
    detection_result = InactivityDetector.detect_batch_inactivity(
        teams,
        warning_threshold,
        critical_threshold
    )
    
    # Build a set of inactive team ids for quick lookup
    inactive_map = {}
    for result in detection_result["results"]:
        inactive_map[result.team_id] = {
            "daysInactive": result.days_inactive,
            "lastCommitDate": result.last_commit_date,
            "severity": result.severity,
            "reason": result.reason
        }
    
    # Collect unique mentor IDs
    mentor_ids = list(set(
        t["mentor_id"] for t in teams if t.get("mentor_id")
    ))
    
    # Fetch mentor user details
    mentor_details = {}
    if mentor_ids:
        mentors_response = admin_supabase.table("users").select(
            "id, email, full_name, last_login, last_logout, is_online, total_time_spent"
        ).in_("id", mentor_ids).execute()
        
        from datetime import datetime, timedelta, timezone
        current_time = datetime.now(timezone.utc)
        SESSION_TIMEOUT_MINUTES = 30
        
        for m in (mentors_response.data or []):
            # Determine actual online status considering session timeout
            is_actually_online = m.get("is_online", False)
            last_login = m.get("last_login")
            last_logout = m.get("last_logout")
            
            if is_actually_online and last_login:
                try:
                    # Parse last_login and last_logout as datetime objects
                    if isinstance(last_login, str):
                        from dateutil import parser
                        last_login_dt = parser.parse(last_login)
                    else:
                        last_login_dt = last_login
                    
                    # Use last_logout if available, otherwise use last_login
                    last_activity = last_logout
                    if isinstance(last_activity, str):
                        from dateutil import parser
                        last_activity_dt = parser.parse(last_activity)
                    else:
                        last_activity_dt = last_activity if last_activity else last_login_dt
                    
                    # Check if session timed out
                    time_since_activity = current_time - last_activity_dt
                    if time_since_activity > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                        is_actually_online = False
                except Exception:
                    # If parsing fails, keep the database value
                    pass
            
            mentor_details[m["id"]] = {
                "email": m.get("email", ""),
                "fullName": m.get("full_name", m.get("email", "Unknown")),
                "last_login": m.get("last_login"),
                "last_logout": m.get("last_logout"),
                "is_online": is_actually_online,
                "total_time_spent": m.get("total_time_spent")
            }
    
    # Group teams by mentor
    mentor_groups = {}  # mentor_id -> list of team dicts
    unassigned_teams = []
    
    for team in teams:
        mid = team.get("mentor_id")
        if not mid:
            unassigned_teams.append(team)
            continue
        if mid not in mentor_groups:
            mentor_groups[mid] = []
        mentor_groups[mid].append(team)
    
    # Build response
    mentors_result = []
    mentors_with_inactive = 0
    total_inactive = 0
    
    for mid, group_teams in mentor_groups.items():
        details = mentor_details.get(mid, {"email": "unknown", "fullName": "Unknown"})
        
        team_entries = []
        inactive_count = 0
        
        for team in group_teams:
            tid = team["id"]
            is_inactive = tid in inactive_map
            entry = {
                "teamId": tid,
                "teamName": team.get("team_name", "Unknown"),
                "isInactive": is_inactive,
                "healthStatus": team.get("health_status", "unknown"),
                "repoUrl": team.get("repo_url"),
                "lastCommitDate": team.get("last_commit_date"),
                "lastAlertSent": team.get("last_inactivity_alert"),
                "alertCount": team.get("inactivity_alert_count", 0)
            }
            if is_inactive:
                entry.update(inactive_map[tid])
                inactive_count += 1
            team_entries.append(entry)
        
        if inactive_count > 0:
            mentors_with_inactive += 1
        total_inactive += inactive_count
        
        mentors_result.append({
            "mentorId": mid,
            "mentorName": details["fullName"],
            "mentorEmail": details["email"],
            "last_login": details.get("last_login"),
            "last_logout": details.get("last_logout"),
            "is_online": details.get("is_online"),
            "total_time_spent": details.get("total_time_spent"),
            "totalTeams": len(group_teams),
            "activeTeams": len(group_teams) - inactive_count,
            "inactiveTeams": inactive_count,
            "teams": team_entries
        })
    
    # Sort: mentors with most inactive teams first
    mentors_result.sort(key=lambda m: m["inactiveTeams"], reverse=True)
    
    return {
        "success": True,
        "mentors": mentors_result,
        "summary": {
            "totalMentors": len(mentors_result),
            "mentorsWithInactiveTeams": mentors_with_inactive,
            "mentorsAllActive": len(mentors_result) - mentors_with_inactive,
            "totalInactiveTeams": total_inactive
        }
    }


@router.post("/notify-mentor")
async def notify_mentor_inactive_teams(
    request_body: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Send an email to a mentor listing their inactive teams.
    
    Request body:
    {
        "mentorId": "mentor-uuid",
        "batchId": "batch-uuid",
        "force": false  // Optional: bypass cooldown
    }
    
    Admin only.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    mentor_id = request_body.get("mentorId")
    batch_id = request_body.get("batchId")
    force = request_body.get("force", False)
    
    if not mentor_id or not batch_id:
        raise HTTPException(status_code=400, detail="mentorId and batchId are required")
    
    supabase = get_supabase()
    admin_supabase = get_supabase_admin_client()
    
    # Get mentor info
    mentor_response = admin_supabase.table("users").select(
        "id, email, full_name"
    ).eq("id", mentor_id).execute()
    
    if not mentor_response.data:
        raise HTTPException(status_code=404, detail="Mentor not found")
    
    mentor = mentor_response.data[0]
    mentor_email = mentor.get("email")
    mentor_name = mentor.get("full_name") or mentor_email.split("@")[0]
    
    if not mentor_email:
        raise HTTPException(status_code=400, detail="Mentor has no email address")
    
    # Get mentor's teams in this batch
    teams_response = supabase.table("teams").select(
        "id, team_name, last_commit_date, is_private, status, "
        "last_inactivity_alert, inactivity_alert_count, repo_url"
    ).eq("batch_id", batch_id).eq("mentor_id", mentor_id).execute()
    
    teams = teams_response.data or []
    
    if not teams:
        return {
            "success": False,
            "message": "No teams found for this mentor in this batch",
            "emailsSent": 0
        }
    
    # Detect inactivity
    detection_result = InactivityDetector.detect_batch_inactivity(teams)
    
    if not detection_result["results"]:
        return {
            "success": False,
            "message": "All teams under this mentor are active",
            "emailsSent": 0
        }
    
    # Build inactive teams list for the email
    inactive_teams_for_email = []
    for result in detection_result["results"]:
        last_commit_display = result.last_commit_date or "Never"
        if result.last_commit_date:
            try:
                commit_dt = datetime.fromisoformat(
                    result.last_commit_date.replace('Z', '+00:00')
                )
                last_commit_display = commit_dt.strftime("%B %d, %Y")
            except Exception:
                pass
        
        inactive_teams_for_email.append({
            "teamName": result.team_name,
            "daysInactive": result.days_inactive,
            "lastCommitDate": last_commit_display,
            "severity": result.severity
        })
    
    # Generate email
    subject = EmailTemplates.mentor_inactive_teams_subject(mentor_name)
    email_result = EmailTemplates.mentor_inactive_teams_body(
        mentor_name, inactive_teams_for_email
    )
    email_body = email_result.get("text", "") if isinstance(email_result, dict) else email_result
    email_html = email_result.get("html") if isinstance(email_result, dict) else None
    
    # Send the email
    try:
        send_alert_email(
            subject=subject,
            body_text=email_body,
            to_email=mentor_email,
            html_body=email_html,
            use_mentor_sender=True,
        )
    except Exception as e:
        print(f"Failed to send mentor notification to {mentor_email}: {e}")
        return {
            "success": False,
            "message": f"Failed to send email: {str(e)}",
            "emailsSent": 0
        }
    
    # Log to alert_history
    try:
        supabase.table("alert_history").insert({
            "team_id": teams[0]["id"],  # reference first team
            "alert_type": "mentor_inactivity_notification",
            "severity": "warning",
            "recipient_count": 1,
            "delivery_status": "sent",
            "metadata": {
                "mentor_id": mentor_id,
                "mentor_email": mentor_email,
                "inactive_team_count": len(inactive_teams_for_email),
                "team_names": [t["teamName"] for t in inactive_teams_for_email]
            }
        }).execute()
    except Exception as e:
        print(f"Failed to log mentor alert history: {e}")
    
    return {
        "success": True,
        "message": f"Notification sent to {mentor_name} ({mentor_email}) about {len(inactive_teams_for_email)} inactive teams",
        "emailsSent": 1,
        "inactiveTeams": len(inactive_teams_for_email)
    }
