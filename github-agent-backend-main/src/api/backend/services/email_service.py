"""
Email Service for sending duplicate commit alerts and quality alerts
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from ..utils.email import send_alert_email
from ..database import get_supabase_admin_client
from ..models.quality_models import ForensicsData, AlertResult
from ..templates.email_templates import EmailTemplates
from .leaderboard_service import LeaderboardService
from ..utils.leaderboard_pdf_generator import generate_leaderboard_pdf

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email alerts"""
    
    def __init__(self):
        self.leaderboard_service = LeaderboardService()
    
    async def send_weekly_report(
        self,
        team_id: str,
        team_name: str,
        batch_id: str,
        recipient_email: str,
        analysis_summary: Dict[str, Any]
    ) -> bool:
        """
        Send weekly report with leaderboard to a team member
        
        Args:
            team_id: UUID of the team
            team_name: Name of the team
            batch_id: UUID of the batch
            recipient_email: Email address of recipient
            analysis_summary: Summary of analysis results
        
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Generate main report content
            subject = EmailTemplates.weekly_report_subject(team_name)
            
            # Legacy low-detail attachment flow removed.
            # Celery/manual report endpoints send the full detailed PDF + leaderboard attachments.
            # This service now sends only the HTML weekly notification body.
            leaderboard_included = False

            # Build report body
            body = EmailTemplates.weekly_report_body(team_name, leaderboard_included)
            body_text = body.get("text", "") if isinstance(body, dict) else body
            html_body = body.get("html") if isinstance(body, dict) else None

            send_alert_email(
                subject=subject,
                body_text=body_text,
                to_email=recipient_email,
                html_body=html_body
            )

            logger.info(f"Weekly report notification sent to {recipient_email} for team {team_name} (legacy attachment flow removed)")
            return True
            
        except Exception as e:
            logger.error(f"Error sending weekly report to team {team_name}: {e}")
            return False
    
    async def send_duplicate_commit_alert(
        self,
        team_name: str,
        repo_url: str,
        incidents: List[Dict[str, Any]],
        recipient_emails: List[str]
    ) -> None:
        """
        Send duplicate commit alert email to team members
        
        Args:
            team_name: Name of the team
            repo_url: Repository URL
            incidents: List of duplicate commit incidents affecting this team
            recipient_emails: List of student email addresses
        """
        if not recipient_emails:
            logger.warning(f"No recipient emails for team {team_name}")
            return
        
        # Generate email content using centralized templates
        subject = EmailTemplates.duplicate_commit_alert_subject(team_name)
        body = EmailTemplates.duplicate_commit_alert_body(team_name, repo_url, incidents)
        body_text = body.get("text", "") if isinstance(body, dict) else body
        html_body = body.get("html") if isinstance(body, dict) else None
        
        # Send email to each recipient
        for email in recipient_emails:
            try:
                send_alert_email(
                    subject=subject,
                    body_text=body_text,
                    to_email=email,
                    html_body=html_body
                )
                logger.info(f"Sent duplicate commit alert to {email} for team {team_name}")
            except Exception as e:
                logger.error(f"Failed to send alert to {email}: {e}")
                # Continue sending to other recipients

    
    async def send_quality_alert(
        self,
        team_id: str,
        team_name: str,
        forensics: ForensicsData,
        threshold: float,
        force: bool = False
    ) -> AlertResult:
        """
        Send commit quality alert email to team members
        
        Args:
            team_id: Team UUID
            team_name: Name of the team
            forensics: Quality metrics to include
            threshold: Threshold used for evaluation
            force: Skip duplicate check if True
        
        Returns:
            AlertResult with success status and details
        """
        supabase = get_supabase_admin_client()
        
        try:
            # Check alert history unless forced
            if not force:
                recent_alert = self.check_alert_history(team_id, days=7)
                if recent_alert:
                    logger.info(f"Skipping alert for team {team_name} - alert sent {recent_alert['sent_at']}")
                    return AlertResult(
                        team_id=team_id,
                        team_name=team_name,
                        status="skipped",
                        reason="Alert sent within last 7 days",
                        fake_commit_ratio=forensics.fake_commit_ratio
                    )
            
            # Get student emails
            students_response = supabase.table("students").select(
                "name, email"
            ).eq("team_id", team_id).execute()
            
            student_emails = [
                s["email"] for s in students_response.data 
                if s.get("email")
            ]
            
            if not student_emails:
                logger.warning(f"No student emails found for team {team_name}")
                return AlertResult(
                    team_id=team_id,
                    team_name=team_name,
                    status="skipped",
                    reason="No email addresses found",
                    fake_commit_ratio=forensics.fake_commit_ratio
                )
            
            # Generate email content using centralized templates
            subject = EmailTemplates.quality_alert_subject(team_name)
            
            # Convert forensics data to dict format for template
            fake_commits_list = [
                {
                    "hash": fc.hash,
                    "reasons": fc.reasons,
                    "fake_additions": fc.fake_additions
                }
                for fc in forensics.fake_commits
            ] if forensics.fake_commits else []
            
            body = EmailTemplates.quality_alert_body(
                team_name=team_name,
                fake_commit_count=forensics.fake_commit_count,
                fake_commit_ratio=forensics.fake_commit_ratio,
                commit_health=forensics.commit_health,
                total_commits=forensics.total_commits,
                threshold=threshold,
                fake_commits=fake_commits_list,
                suspicious_authors=forensics.suspicious_authors
            )
            body_text = body.get("text", "") if isinstance(body, dict) else body
            html_body = body.get("html") if isinstance(body, dict) else None
            
            # Send email to each recipient
            sent_count = 0
            for email in student_emails:
                try:
                    send_alert_email(
                        subject=subject,
                        body_text=body_text,
                        to_email=email,
                        html_body=html_body
                    )
                    sent_count += 1
                    logger.info(f"Sent quality alert to {email} for team {team_name}")
                except Exception as e:
                    logger.error(f"Failed to send alert to {email}: {e}")
                    # Continue sending to other recipients
            
            if sent_count == 0:
                return AlertResult(
                    team_id=team_id,
                    team_name=team_name,
                    status="failed",
                    reason="Failed to send to any recipients",
                    fake_commit_ratio=forensics.fake_commit_ratio
                )
            
            # Record alert in database
            self.record_alert_sent(team_id, forensics, threshold, student_emails)
            
            return AlertResult(
                team_id=team_id,
                team_name=team_name,
                status="sent",
                fake_commit_ratio=forensics.fake_commit_ratio,
                email_count=sent_count
            )
            
        except Exception as e:
            logger.error(f"Error sending quality alert to team {team_name}: {e}")
            return AlertResult(
                team_id=team_id,
                team_name=team_name,
                status="failed",
                reason=str(e),
                fake_commit_ratio=forensics.fake_commit_ratio
            )
    
    def check_alert_history(self, team_id: str, days: int = 7) -> Optional[Dict[str, Any]]:
        """
        Check if alert was recently sent to team
        
        Args:
            team_id: Team UUID
            days: Number of days to look back
        
        Returns:
            Most recent alert record if found within days window
        """
        supabase = get_supabase_admin_client()
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            response = supabase.table("quality_alerts").select(
                "id, sent_at, fake_commit_ratio, commit_health"
            ).eq("team_id", team_id).gte(
                "sent_at", cutoff_date.isoformat()
            ).order("sent_at", desc=True).limit(1).execute()
            
            if response.data:
                return response.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error checking alert history for team {team_id}: {e}")
            return None
    
    def record_alert_sent(
        self,
        team_id: str,
        forensics: ForensicsData,
        threshold: float,
        email_recipients: List[str]
    ) -> None:
        """
        Record alert in database for history tracking
        
        Args:
            team_id: Team UUID
            forensics: Quality metrics
            threshold: Threshold used
            email_recipients: List of emails that received the alert
        """
        supabase = get_supabase_admin_client()
        
        try:
            supabase.table("quality_alerts").insert({
                "team_id": team_id,
                "fake_commit_ratio": forensics.fake_commit_ratio,
                "fake_commit_count": forensics.fake_commit_count,
                "commit_health": forensics.commit_health,
                "total_commits": forensics.total_commits,
                "threshold_used": threshold,
                "email_recipients": email_recipients
            }).execute()
            
            logger.info(f"Recorded quality alert for team {team_id}")
            
        except Exception as e:
            logger.error(f"Error recording alert for team {team_id}: {e}")
            # Don't raise - alert was sent successfully
