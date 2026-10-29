"""
Celery Task Definitions
Background workers for repository analysis
"""
from celery import Task
from celery.utils.log import get_task_logger
from celery_app import celery_app
from uuid import UUID, uuid4
import traceback
import time
import os
import html
from typing import Any, List, Dict, Optional
from datetime import datetime, timedelta
import json

from src.api.backend.services.analyzer_service import AnalyzerService
from src.api.backend.crud import AnalysisJobCRUD, BatchCRUD
from src.api.backend.database import get_supabase_admin_client
from src.api.backend.templates.email_templates import EmailTemplates
from src.api.backend.utils.report_storage import ReportStorageManager

import subprocess
from functools import wraps

logger = get_task_logger(__name__)


# ============================================================
# Scheduled Task Tracking System
# ============================================================

def track_scheduled_task(task_name: str, task_display_name: str = None):
    """
    Decorator to automatically track scheduled task executions.
    Logs to scheduled_task_executions table and sends alerts on failures.
    
    Usage:
        @celery_app.task
        @track_scheduled_task('weekly-batch-analysis', 'Weekly Batch Analysis')
        def auto_trigger_batch_analysis():
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            execution_id = None
            started_at = datetime.now()
            scheduled_time = started_at  # Could be made more accurate by parsing schedule
            
            try:
                supabase = get_supabase_admin_client()
                
                # Create execution record
                execution_record = supabase.table('scheduled_task_executions').insert({
                    'task_name': task_name,
                    'task_display_name': task_display_name or task_name,
                    'scheduled_time': scheduled_time.isoformat(),
                    'started_at': started_at.isoformat(),
                    'status': 'running',
                    'metadata': {
                        'args': str(args)[:500],  # Truncate to avoid huge payloads
                        'kwargs': str(kwargs)[:500]
                    }
                }).execute()
                
                execution_id = execution_record.data[0]['id'] if execution_record.data else None
                
                logger.info(f"📊 [{task_name}] Execution tracked: {execution_id}")
                
            except Exception as e:
                logger.error(f"Failed to create execution tracking record: {e}")
            
            # Execute the actual task
            result = None
            error_occurred = False
            error_message = None
            error_traceback = None
            
            try:
                result = func(*args, **kwargs)
                status = 'completed'
                
            except Exception as exc:
                error_occurred = True
                error_message = str(exc)
                error_traceback = traceback.format_exc()
                status = 'failed'
                logger.error(f"❌ [{task_name}] Task failed: {error_message}")
                result = {'error': error_message}
            
            finally:
                # Update execution record
                if execution_id:
                    try:
                        completed_at = datetime.now()
                        duration = (completed_at - started_at).total_seconds()
                        
                        supabase.table('scheduled_task_executions').update({
                            'completed_at': completed_at.isoformat(),
                            'duration_seconds': duration,
                            'status': status,
                            'result_summary': result if isinstance(result, dict) else {'result': str(result)[:1000]},
                            'error_message': error_message,
                            'error_traceback': error_traceback
                        }).eq('id', execution_id).execute()
                        
                        logger.info(f"📊 [{task_name}] Execution completed in {duration:.2f}s - Status: {status}")
                        
                        # Send alert on failure
                        if error_occurred:
                            send_task_failure_alert(task_name, task_display_name, error_message, error_traceback)
                        
                    except Exception as e:
                        logger.error(f"Failed to update execution record: {e}")
            
            if error_occurred:
                raise Exception(error_message)
            
            return result
        return wrapper
    return decorator


def send_task_failure_alert(task_name: str, task_display_name: str, error: str, traceback_str: str):
    """Send automated alert when a scheduled task fails."""
    try:
        supabase = get_supabase_admin_client()
        
        # Get health status to determine severity
        health_result = supabase.table('scheduled_task_health').select('consecutive_failures, health_status').eq('task_name', task_name).execute()
        
        consecutive_failures = 1
        health_status = 'degraded'
        
        if health_result.data and len(health_result.data) > 0:
            consecutive_failures = health_result.data[0].get('consecutive_failures', 1)
            health_status = health_result.data[0].get('health_status', 'degraded')
        
        # Determine notification type based on severity
        if consecutive_failures >= 3 or health_status == 'critical':
            notification_type = 'error'
            emoji = '🚨'
        elif consecutive_failures >= 2:
            notification_type = 'warning'
            emoji = '⚠️'
        else:
            notification_type = 'warning'
            emoji = '⚠️'
        
        # Create in-app notification
        create_notification(
            notification_type=notification_type,
            title=f'{emoji} Scheduled Task Failed: {task_display_name or task_name}',
            message=f'Task failed with error: {error[:200]}{"..." if len(error) > 200 else ""}',
            metadata={
                'task_name': task_name,
                'error': error,
                'consecutive_failures': consecutive_failures,
                'health_status': health_status
            }
        )
        
        # Send email for critical failures — throttle to avoid spam
        # Send on 3rd failure, then every 10th failure after that
        if consecutive_failures >= 3 and (consecutive_failures == 3 or consecutive_failures % 10 == 0):
            email_parts = EmailTemplates.scheduled_task_failure_body(
                task_name=task_display_name or task_name,
                health_status=health_status,
                consecutive_failures=consecutive_failures,
                error=error,
                traceback_excerpt=traceback_str[:1000],
            )
            send_notification_email(
                subject=f"🚨 CRITICAL: {task_display_name or task_name} Failed ({consecutive_failures}x)",
                body=email_parts["text"],
                html_body=email_parts["html"],
            )
            
            logger.error(f"🚨 CRITICAL ALERT: {task_name} has failed {consecutive_failures} times consecutively")
        
    except Exception as e:
        logger.error(f"Failed to send task failure alert: {e}")


def create_notification(notification_type: str, title: str, message: str, metadata: dict = None):
    """Create an in-app notification in the database."""
    try:
        supabase = get_supabase_admin_client()
        result = supabase.table('notifications').insert({
            'type': notification_type,
            'title': title,
            'message': message,
            'metadata': metadata or {},
            'is_read': False
        }).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
    except Exception as e:
        logger.warning(f"Failed to create notification: {e}")
        return None


def update_notification(notification_id: str, update_payload: dict):
    """Update an in-app notification by ID."""
    try:
        if not notification_id:
            return None
        supabase = get_supabase_admin_client()
        result = supabase.table('notifications').update(update_payload).eq('id', notification_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.warning(f"Failed to update notification {notification_id}: {e}")
        return None


def send_notification_email(subject: str, body: str, html_body: str = None):
    """Send email notification to admin emails. Silently skips if SMTP not configured."""
    try:
        from src.api.backend.utils.email import send_alert_email, EmailConfigError

        if not html_body:
            escaped_body = html.escape(body or "").replace("\n", "<br>")
            html_content = f"""
            <p style=\"color:#334155;\">Automated alert from GitHub Agent Monitoring System.</p>
            <div style=\"background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:14px;white-space:normal;font-family:monospace;line-height:1.5;\">{escaped_body}</div>
            """
            html_body = EmailTemplates.get_html_wrapper(subject, html_content)

        admin_emails = os.getenv('ADMIN_EMAILS', '')
        if not admin_emails:
            return
        recipients = [e.strip() for e in admin_emails.split(',') if e.strip()]
        for email in recipients:
            try:
                send_alert_email(subject=subject, body_text=body, to_email=email, html_body=html_body, use_mentor_sender=True)
                logger.info(f"📧 Notification email sent to {email}")
            except EmailConfigError:
                logger.debug("SMTP not configured, skipping email notification")
                return
            except Exception as e:
                logger.warning(f"Failed to send email to {email}: {e}")
    except ImportError:
        logger.debug("Email module not available, skipping email notification")


# ============================================================
# CONSOLIDATED MENTOR ALERTS FOR FAKE COMMITS
# ============================================================

def send_consolidated_mentor_alert(mentor_id: str, mentor_name: str, fake_commit_teams: List[Dict[str, Any]]):
    """
    Send a single consolidated email to a mentor listing all their teams with fake commits.
    
    Args:
        mentor_id: UUID of the mentor
        mentor_name: Name of the mentor
        fake_commit_teams: List of teams with fake commits, each containing:
                          - team_id, team_name, project_name, repo_url, 
                            fake_commit_count, fake_commit_ratio, commit_health, total_commits
    """
    if not fake_commit_teams:
        return
    
    try:
        from src.api.backend.utils.email import send_alert_email, EmailConfigError
        
        # Get frontend URL for team dashboard links
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:8080')
        dashboard_url = f"{frontend_url}/admin/mentor-portal"
        
        # Use the consolidated email template
        subject, text_body, html_body = EmailTemplates.fake_commits_mentor_weekly_summary(
            mentor_name=mentor_name,
            fc_teams=fake_commit_teams,
            dashboard_url=dashboard_url
        )
        
        # Get mentor email from database
        supabase = get_supabase_admin_client()
        mentor_response = supabase.table('users').select('email').eq('id', mentor_id).single().execute()
        
        if not mentor_response.data:
            logger.warning(f"Mentor {mentor_name} (ID: {mentor_id}) not found in database")
            return
        
        mentor_email = mentor_response.data.get('email')
        if not mentor_email:
            logger.warning(f"No email found for mentor {mentor_name}")
            return
        
        # Send email
        send_alert_email(
            subject=subject,
            body_text=text_body,
            to_email=mentor_email,
            html_body=html_body,
            use_mentor_sender=True
        )
        
        logger.info(f"📧 Consolidated fake commit alert sent to mentor {mentor_name} ({mentor_email}) for {len(fake_commit_teams)} team(s)")
        
    except EmailConfigError:
        logger.debug("SMTP not configured, skipping consolidated mentor alert")
    except ImportError:
        logger.debug("Email module not available, skipping consolidated mentor alert")
    except Exception as e:
        logger.error(f"Error sending consolidated mentor alert to {mentor_name}: {e}")
        logger.error(traceback.format_exc())


def collect_and_batch_mentor_alerts(batch_id: str):
    """
    Collect all teams in a batch with critical fake commits and send consolidated alerts to mentors.
    This should be called after batch analysis completes.
    
    Args:
        batch_id: UUID of the batch that was analyzed
    """
    try:
        supabase = get_supabase_admin_client()
        
        logger.info(f"🔍 Collecting fake commit alerts for batch {batch_id}")
        
        # Get all teams in batch with their analysis reports
        teams_response = supabase.table('teams').select(
            'id, team_name, mentor_id, repo_url, report_json, report_path, metadata'
        ).eq('batch_id', batch_id).execute()
        
        teams_data = teams_response.data or []
        logger.info(f"Found {len(teams_data)} teams in batch")
        
        # Group teams by mentor
        mentor_teams = {}  # mentor_id -> {mentor_name, teams_list}
        
        for team in teams_data:
            # Get report
            report = ReportStorageManager.get_report_for_team(team)
            commit_details = report.get('commit_details', {})
            
            fake_commit_count = commit_details.get('fake_commit_count', 0)
            fake_commit_ratio = commit_details.get('fake_commit_ratio', 0.0)
            commit_health = commit_details.get('commit_health', 'Healthy')
            
            # Skip if no fake commits or not critical
            if fake_commit_count == 0 or (commit_health != 'Critical' and fake_commit_ratio < 50):
                continue
            
            mentor_id = team.get('mentor_id')
            if not mentor_id:
                logger.warning(f"Team {team.get('team_name')} has no mentor assigned, skipping")
                continue
            
            # Get mentor name from metadata or database
            metadata = team.get('metadata', {}) or {}
            mentor_name = metadata.get('ingestion', {}).get('mentor', '')
            
            if not mentor_name:
                # Try to fetch from database
                try:
                    mentor_data = supabase.table('users').select('full_name').eq('id', mentor_id).single().execute()
                    if mentor_data.data:
                        mentor_name = mentor_data.data.get('full_name', 'Unknown Mentor')
                except:
                    mentor_name = 'Unknown Mentor'
            
            # Extract project name
            ingestion = metadata.get('ingestion', {}) or {}
            project_name = ingestion.get('project_statement', '')
            if not project_name and team.get('repo_url'):
                repo_url = team.get('repo_url', '')
                project_name = repo_url.rstrip('/').rstrip('.git').split('/')[-1]
            if not project_name:
                project_name = team.get('team_name', 'N/A')
            
            # Add to mentor's team list
            if mentor_id not in mentor_teams:
                mentor_teams[mentor_id] = {
                    'mentor_name': mentor_name,
                    'teams': []
                }
            
            mentor_teams[mentor_id]['teams'].append({
                'team_id': team.get('id'),
                'team_name': team.get('team_name'),
                'project_name': project_name,
                'repo_url': team.get('repo_url', 'N/A'),
                'fake_commit_count': fake_commit_count,
                'fake_commit_ratio': round(fake_commit_ratio, 1),
                'commit_health': commit_health,
                'total_commits': commit_details.get('total_commits', 0)
            })
        
        # Send consolidated alerts to each mentor
        for mentor_id, mentor_data in mentor_teams.items():
            try:
                send_consolidated_mentor_alert(
                    mentor_id=mentor_id,
                    mentor_name=mentor_data['mentor_name'],
                    fake_commit_teams=mentor_data['teams']
                )
            except Exception as e:
                logger.error(f"Error sending consolidated alert to mentor {mentor_id}: {e}")
                continue
        
        logger.info(f"✅ Batch alert collection complete: {len(mentor_teams)} mentor(s) notified")
        
    except Exception as e:
        logger.error(f"Error collecting batch mentor alerts: {e}")
        logger.error(traceback.format_exc())


def check_and_notify_fake_commits(team_id: str, team_name: str, report: dict):
    """
    Check if SEVERE fake commits were detected and send email alerts to admins and mentor.
    Only notifies for Critical health status (truly problematic fake commits).
    
    Args:
        team_id: UUID of the team
        team_name: Name of the team
        report: Analysis report dictionary containing commit_details
    """
    try:
        # Extract fake commit information from report
        commit_details = report.get('commit_details', {})
        fake_commit_count = commit_details.get('fake_commit_count', 0)
        fake_commits = commit_details.get('fake_commits', [])
        fake_commit_ratio = commit_details.get('fake_commit_ratio', 0.0)
        commit_health = commit_details.get('commit_health', 'Healthy')

        # Extract automation contributor signal (e.g., github-actions) and check majority threshold
        ai_bot_detection = commit_details.get('ai_bot_detection', {}) or {}
        ai_bot_contributors = ai_bot_detection.get('ai_bot_contributors', []) if isinstance(ai_bot_detection, dict) else []
        ai_bot_contributors = [b for b in ai_bot_contributors if isinstance(b, dict)]
        total_commits = max(1, int(commit_details.get('total_commits', 0) or 0))
        ai_bot_commit_count = sum(int(b.get('commits', 0) or 0) for b in ai_bot_contributors)
        ai_bot_share = (ai_bot_commit_count / total_commits) * 100.0
        ai_bot_majority = ai_bot_share > 50.0

        # Notify for either:
        # 1) severe fake commits (existing behavior), or
        # 2) automation/bot majority commits >50% (new policy)
        if not ai_bot_majority and (commit_health != 'Critical' or fake_commit_count == 0):
            return
        
        # Filter out commits that are ONLY flagged for generic messages (not truly malicious)
        # Only alert for commits with serious reasons: empty, repeated, timestamp manipulation, etc.
        serious_fake_commits = [
            fc for fc in fake_commits
            if not all('Generic Message' in r for r in fc.get('reasons', []))
        ]
        
        # If all "fake" commits are just generic messages, don't send CRITICAL fake-commit alert
        # unless automation-author majority condition is met.
        if len(serious_fake_commits) == 0 and not ai_bot_majority:
            return
        
        # Use only serious fake commits for the alert
        fake_commits = serious_fake_commits
        fake_commit_count = len(serious_fake_commits)
        
        if ai_bot_majority:
            logger.warning(
                f"🤖 CRITICAL: automation-authored commits exceed 50% for team {team_name} "
                f"({ai_bot_commit_count}/{total_commits}, {ai_bot_share:.1f}%)"
            )
        elif fake_commit_count > 0:
            logger.warning(f"🚨 CRITICAL: {fake_commit_count} fake commits detected for team {team_name} ({fake_commit_ratio}%)")
        
        # Get team details from database
        supabase = get_supabase_admin_client()
        team_data = supabase.table('teams').select('*').eq('id', team_id).single().execute()
        
        if not team_data.data:
            logger.error(f"Team {team_id} not found in database")
            return
            
        team = team_data.data
        repo_url = team.get('repo_url', 'N/A')
        metadata = team.get('metadata', {}) or {}
        mentor_name = metadata.get('ingestion', {}).get('mentor', 'Unknown')
        mentor_id = team.get('mentor_id')
        
        # Extract team_number from team_name (e.g. "Team 175" -> "175")
        import re as _re
        _tn_match = _re.search(r'\d+', team_name or '')
        team_number = _tn_match.group() if _tn_match else team_name or 'N/A'
        
        # Derive project_name: prefer problem statement, then repo URL, then team name
        ingestion = metadata.get('ingestion', {}) or {}
        project_name = ingestion.get('project_statement', '') or ''
        if not project_name and repo_url and repo_url != 'N/A':
            _repo_name = repo_url.rstrip("/").rstrip(".git").split("/")[-1]
            if _repo_name:
                project_name = _repo_name
        if not project_name:
            project_name = team_name or 'N/A'
        
        import html as _html

        # Frontend URL for team dashboard
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:8080')
        team_dashboard_url = f"{frontend_url}/admin/teams/{team_id}"
        
        # Use centralized HTML email templates
        if ai_bot_majority:
            _bot_rows = ""
            for i, bot in enumerate(ai_bot_contributors[:10]):
                _bg = '#f8fafc' if i % 2 == 0 else '#ffffff'
                _bot_rows += (
                    f'<tr style="background:{_bg};">'
                    f'<td style="padding:8px 10px;border:1px solid #e2e8f0;font-weight:700;color:#b91c1c;">'
                    f'{_html.escape(str(bot.get("name", "Unknown")))} - AUTOMATION COMMIT (NOT ACCEPTED)</td>'
                    f'<td style="padding:8px 10px;border:1px solid #e2e8f0;text-align:center;">{int(bot.get("commits", 0) or 0)}</td>'
                    f'<td style="padding:8px 10px;border:1px solid #e2e8f0;text-align:center;">{float(bot.get("share", 0) or 0):.1f}%</td>'
                    f'<td style="padding:8px 10px;border:1px solid #e2e8f0;">{_html.escape(str(bot.get("tool", "BOT")))}</td>'
                    f'</tr>'
                )
            ai_bot_details_html = (
                '<table style="width:100%;border-collapse:collapse;font-size:13px;margin:12px 0;">'
                '<thead><tr style="background:#0f172a;color:#ffffff;">'
                '<th style="padding:8px 10px;border:1px solid #334155;text-align:left;">Automation Author</th>'
                '<th style="padding:8px 10px;border:1px solid #334155;text-align:center;">Commits</th>'
                '<th style="padding:8px 10px;border:1px solid #334155;text-align:center;">Share</th>'
                '<th style="padding:8px 10px;border:1px solid #334155;text-align:left;">Detected Tool</th>'
                '</tr></thead><tbody>'
                f'{_bot_rows}'
                '</tbody></table>'
            )
            subject = EmailTemplates.ai_bot_majority_critical_subject(team_number, project_name)
            email_parts = EmailTemplates.ai_bot_majority_critical_body(
                team_number=team_number,
                team_name=team_name,
                project_name=project_name,
                repo_url=repo_url,
                mentor_name=mentor_name,
                total_commits=total_commits,
                ai_bot_commits=ai_bot_commit_count,
                ai_bot_share=ai_bot_share,
                ai_bot_details_html=ai_bot_details_html,
                dashboard_url=team_dashboard_url,
            )
        else:
            fake_commit_list = "\n".join([
                f"  \u2022 {fc.get('hash', 'N/A')[:7]} by {fc.get('author', 'Unknown')} on {fc.get('date', 'N/A')}\n"
                f"    Message: {fc.get('msg', 'No message')[:60]}\n"
                f"    Reasons: {', '.join(fc.get('reasons', []))}\n"
                f"    Fake Lines: {fc.get('fake_additions', 0)}"
                for fc in fake_commits[:10]
            ])
            if len(fake_commits) > 10:
                fake_commit_list += f"\n  ... and {len(fake_commits) - 10} more"

            _rows = ""
            for i, fc in enumerate(fake_commits[:10]):
                bg = '#f8fafc' if i % 2 == 0 else '#ffffff'
                reasons = ', '.join(fc.get('reasons', [])) or 'N/A'
                _rows += (
                    f'<tr style="background:{bg};">'
                    f'<td style="padding:6px 10px;border:1px solid #e2e8f0;font-family:monospace;font-size:13px;">{_html.escape(fc.get("hash", "N/A")[:7])}</td>'
                    f'<td style="padding:6px 10px;border:1px solid #e2e8f0;">{_html.escape(fc.get("author", "Unknown"))}</td>'
                    f'<td style="padding:6px 10px;border:1px solid #e2e8f0;">{_html.escape(fc.get("date", "N/A"))}</td>'
                    f'<td style="padding:6px 10px;border:1px solid #e2e8f0;">{_html.escape(fc.get("msg", "No message")[:60])}</td>'
                    f'<td style="padding:6px 10px;border:1px solid #e2e8f0;">{_html.escape(reasons)}</td>'
                    f'<td style="padding:6px 10px;border:1px solid #e2e8f0;text-align:center;">{fc.get("fake_additions", 0)}</td>'
                    f'</tr>'
                )
            _extra = f'<tr><td colspan="6" style="padding:8px;text-align:center;color:#64748b;">... and {len(fake_commits) - 10} more</td></tr>' if len(fake_commits) > 10 else ''
            fake_commits_html = (
                '<table style="width:100%;border-collapse:collapse;font-size:13px;margin:12px 0;">'
                '<thead><tr style="background:#0f172a;color:#ffffff;">'
                '<th style="padding:8px 10px;border:1px solid #334155;text-align:left;">Hash</th>'
                '<th style="padding:8px 10px;border:1px solid #334155;text-align:left;">Author</th>'
                '<th style="padding:8px 10px;border:1px solid #334155;text-align:left;">Date</th>'
                '<th style="padding:8px 10px;border:1px solid #334155;text-align:left;">Message</th>'
                '<th style="padding:8px 10px;border:1px solid #334155;text-align:left;">Reasons</th>'
                '<th style="padding:8px 10px;border:1px solid #334155;text-align:center;">Fake Lines</th>'
                '</tr></thead><tbody>'
                f'{_rows}{_extra}'
                '</tbody></table>'
            )
            subject = EmailTemplates.fake_commits_critical_subject(team_number, project_name)
            email_parts = EmailTemplates.fake_commits_critical_body(
                team_number=team_number,
                team_name=team_name,
                project_name=project_name,
                repo_url=repo_url,
                mentor_name=mentor_name,
                fake_commit_count=fake_commit_count,
                fake_commit_ratio=fake_commit_ratio,
                total_commits=commit_details.get('total_commits', 0),
                commit_health=commit_details.get('commit_health', 'Unknown'),
                fake_commits_list=fake_commit_list,
                dashboard_url=team_dashboard_url,
                fake_commits_html=fake_commits_html,
            )
        body = email_parts['text']
        html_body = email_parts['html']
        
        # Send to all admins from Supabase users table
        try:
            from src.api.backend.utils.email import send_alert_email, EmailConfigError
            
            # Get all admin users from Supabase
            admins_response = supabase.table('users').select('email, full_name').eq('role', 'admin').execute()
            
            if admins_response.data:
                logger.info(f"Found {len(admins_response.data)} admin(s) to notify")
                for admin in admins_response.data:
                    admin_email = admin.get('email')
                    if admin_email:
                        try:
                            send_alert_email(subject=subject, body_text=body, to_email=admin_email, html_body=html_body, use_mentor_sender=True)
                            logger.info(f"📧 Critical fake commit alert sent to admin: {admin_email}")
                        except EmailConfigError:
                            logger.debug("SMTP not configured, skipping admin emails")
                            break
                        except Exception as e:
                            logger.warning(f"Failed to send email to admin {admin_email}: {e}")
            else:
                logger.warning("No admin users found in database")
        except ImportError:
            logger.debug("Email module not available")
        except Exception as e:
            logger.error(f"Error fetching admin users: {e}")
        
        # Send to mentor if we have mentor_id
        if mentor_id:
            try:
                mentor_data = supabase.table('users').select('email').eq('id', mentor_id).single().execute()
                if mentor_data.data:
                    mentor_email = mentor_data.data.get('email')
                    if mentor_email:
                        try:
                            from src.api.backend.utils.email import send_alert_email, EmailConfigError
                            send_alert_email(subject=subject, body_text=body, to_email=mentor_email, html_body=html_body, use_mentor_sender=True)
                            logger.info(f"📧 Critical fake commit alert sent to mentor: {mentor_email}")
                        except EmailConfigError:
                            pass
                        except Exception as e:
                            logger.warning(f"Failed to send email to mentor {mentor_email}: {e}")
            except Exception as e:
                logger.warning(f"Failed to fetch mentor email: {e}")
        else:
            # Try to find mentor by name in metadata
            if mentor_name and mentor_name != 'Unknown':
                try:
                    # Try to find mentor by matching full_name (case-insensitive)
                    users = supabase.table('users').select('email, full_name').eq('role', 'mentor').execute()
                    for user in users.data:
                        if (user.get('full_name') or '').lower() == mentor_name.lower():
                            mentor_email = user.get('email')
                            if mentor_email:
                                try:
                                    from src.api.backend.utils.email import send_alert_email, EmailConfigError
                                    send_alert_email(subject=subject, body_text=body, to_email=mentor_email, html_body=html_body, use_mentor_sender=True)
                                    logger.info(f"📧 Critical fake commit alert sent to mentor: {mentor_email} (matched by name)")
                                    break
                                except EmailConfigError:
                                    break
                                except Exception as e:
                                    logger.warning(f"Failed to send email to mentor {mentor_email}: {e}")
                except Exception as e:
                    logger.warning(f"Failed to find mentor by name: {e}")
        
        # Create in-app notification
        create_notification(
            notification_type='fake_commits_detected' if not ai_bot_majority else 'automation_commits_detected',
            title=(
                f'🤖 CRITICAL: Automation Commits >50% - Team {team_number} ({project_name})'
                if ai_bot_majority
                else f'🚨 CRITICAL: Fake Commits - Team {team_number} ({project_name})'
            ),
            message=(
                f'{ai_bot_commit_count}/{total_commits} commits ({ai_bot_share:.1f}%) are automation-authored - URGENT ACTION REQUIRED'
                if ai_bot_majority
                else f'{fake_commit_count} fake commits detected ({fake_commit_ratio:.1f}%) - URGENT ACTION REQUIRED'
            ),
            metadata={
                'team_id': team_id,
                'team_number': team_number,
                'team_name': team_name,
                'project_name': project_name,
                'fake_commit_count': fake_commit_count,
                'fake_commit_ratio': fake_commit_ratio,
                'ai_bot_commit_count': ai_bot_commit_count,
                'ai_bot_share': round(ai_bot_share, 1),
                'commit_health': commit_health,
                'repo_url': repo_url,
                'mentor_name': mentor_name
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to send fake commit notifications: {e}")
        logger.error(traceback.format_exc())


def create_snapshot_from_team(team_id: str, run_number: int, batch_run_id: str):
    """
    Create analysis snapshot from team for historical tracking
    Called after each successful analysis to preserve state for 7-day comparisons
    
    Args:
        team_id: UUID of team
        run_number: Analysis run number (1, 2, 3, etc.)
        batch_run_id: UUID of batch_analysis_run
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Get current team state (include report_path for storage lookup)
        team = supabase.table('teams').select(
            'report_json, report_path, repo_url, batch_id'
        ).eq('id', team_id).execute()
        
        if not team.data:
            logger.warning(f"Team {team_id} not found for snapshot")
            return
        
        team_data = team.data[0]
        
        # Get report from storage if migrated
        report_path = team_data.get('report_path')
        if report_path:
            try:
                report_json = ReportStorageManager.get_report_from_storage(report_path)
            except Exception:
                report_json = team_data.get('report_json')
        else:
            report_json = team_data.get('report_json')
        
        # Parse report if string
        if isinstance(report_json, str):
            try:
                report_json = json.loads(report_json)
            except:
                logger.warning(f"Failed to parse report_json for snapshot")
                report_json = {}
        
        # Extract scores from report
        scores = {
            'quality_score': report_json.get('quality', {}).get('score', 0),
            'security_score': report_json.get('security', {}).get('score', 0),
            'architecture_score': report_json.get('architecture', {}).get('score', 0),
            'documentation_score': report_json.get('documentation', {}).get('score', 0),
            'originality_score': report_json.get('originality', {}).get('score', 0),
            'total_score': report_json.get('final_scores', {}).get('total_score', 0)
        }
        
        # Create snapshot
        # Extract additional metrics from report
        commit_count = report_json.get('commit_count', 0)
        file_count = report_json.get('file_count', 0)
        lines_of_code = report_json.get('lines_of_code', 0)
        tech_stack_count = len(report_json.get('tech_stack', [])) if report_json.get('tech_stack') else 0
        issue_count = len(report_json.get('issues', [])) if report_json.get('issues') else 0
        
        snapshot_data = {
            'team_id': team_id,
            'batch_run_id': batch_run_id,
            'run_number': run_number,
            'analyzed_at': datetime.utcnow().isoformat(),
            'quality_score': scores['quality_score'],
            'security_score': scores['security_score'],
            'engineering_score': scores['architecture_score'],  # Map architecture to engineering
            'documentation_score': scores['documentation_score'],
            'originality_score': scores['originality_score'],
            'total_score': scores['total_score'],
            'commit_count': commit_count,
            'file_count': file_count,
            'lines_of_code': lines_of_code,
            'tech_stack_count': tech_stack_count,
            'issue_count': issue_count
        }
        
        supabase.table('analysis_snapshots').insert(snapshot_data).execute()
        logger.info(f"✅ Snapshot created: team={team_id}, run={run_number}")
        
    except Exception as e:
        logger.error(f"Failed to create snapshot: {e}")
        logger.error(traceback.format_exc())


class CallbackTask(Task):
    """Base task with failure callback for DLQ"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails after max retries"""
        logger.error(f"Task {task_id} failed permanently: {exc}")
        logger.error(f"Args: {args}, Kwargs: {kwargs}")
        
        # Move to DLQ
        job_id = kwargs.get('job_id') or (args[1] if len(args) > 1 else None)
        if job_id:
            move_to_dlq.delay(
                job_id=job_id,
                error=str(exc),
                traceback_str=str(einfo)
            )


@celery_app.task(
    bind=True,
    base=CallbackTask,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    retry_backoff=True,  # Exponential backoff
    retry_backoff_max=1800,  # Max 30 minutes
    retry_jitter=True
)
def analyze_repository_task(
    self,
    team_id: str,  # Changed from project_id to team_id
    job_id: str,
    repo_url: str,
    team_name: str = None
):
    """
    Main repository analysis task
    
    Args:
        team_id: Team UUID as string (parameter name kept as team_id for clarity)
        job_id: Job UUID as string
        repo_url: GitHub repository URL
        team_name: Optional team name
    
    Returns:
        dict: Analysis results summary
    """
    try:
        logger.info(f"Starting analysis for {team_name or repo_url}")
        logger.info(f"Job ID: {job_id}, Team ID: {team_id}")
        
        # VALIDATE URL BEFORE PROCESSING
        # Import URL validation service
        from src.api.backend.services.url_validation import validate_repo_url
        
        # Validate the repository URL
        url_validation = validate_repo_url(repo_url)
        
        if not url_validation.is_valid:
            # URL is invalid - fail the job immediately
            error_message = f"Invalid repository URL: {url_validation.reason}"
            logger.error(f"🛑 {error_message}")
            
            supabase = get_supabase_admin_client()
            supabase.table('analysis_jobs').update({
                'status': 'failed',
                'error_message': error_message,
                'completed_at': datetime.now().isoformat()
            }).eq('id', job_id).execute()
            
            # Update team status
            supabase.table('teams').update({
                'status': 'failed'
            }).eq('id', team_id).execute()
            
            # Check if part of batch
            job_metadata = supabase.table('analysis_jobs').select('batch_id').eq('id', job_id).execute()
            batch_id = job_metadata.data[0].get('batch_id') if job_metadata.data else None
            
            # Only create individual notification if NOT part of a batch
            if not batch_id or batch_id == "00000000-0000-0000-0000-000000000000":
                create_notification(
                    'error',
                    f'Analysis Failed: {team_name or repo_url}',
                    error_message,
                    {'team_id': team_id, 'job_id': job_id}
                )
            
            return {
                'job_id': job_id,
                'status': 'failed',
                'error': error_message
            }
        
        # Convert string UUIDs to UUID objects
        team_uuid = UUID(team_id)
        job_uuid = UUID(job_id)
        
        # Check if batch analysis has been paused before starting
        supabase = get_supabase_admin_client()
        
        # Get the batch_id from the job metadata
        job_data = supabase.table('analysis_jobs').select('metadata').eq('id', job_id).execute()
        if job_data.data:
            batch_id = job_data.data[0].get('metadata', {}).get('batch_id')
            if batch_id:
                # Check if this batch's analysis run is paused
                runs_response = supabase.table("batch_analysis_runs")\
                    .select("status")\
                    .eq("batch_id", batch_id)\
                    .order("run_number", desc=True)\
                    .limit(1)\
                    .execute()
                
                if runs_response.data and runs_response.data[0].get("status") == "paused":
                    logger.info(f"⏸️  Batch analysis is paused. Skipping analysis for {team_name or repo_url}")
                    # Update job status to cancelled
                    supabase.table('analysis_jobs').update({
                        'status': 'cancelled',
                        'error_message': 'Batch analysis was paused',
                        'completed_at': datetime.now().isoformat()
                    }).eq('id', job_id).execute()
                    
                    return {
                        'job_id': job_id,
                        'status': 'cancelled',
                        'reason': 'batch_paused'
                    }
        
        # Update job with Celery task ID
        supabase = get_supabase_admin_client()
        supabase.table('analysis_jobs').update({
            'metadata': {
                'celery_task_id': self.request.id,
                'retry_count': self.request.retries,
                'started_at': datetime.now().isoformat()
            }
        }).eq('id', job_id).execute()
        
        # Run analysis and capture the report (existing logic) - now uses team_id
        report = AnalyzerService.analyze_repository(
            team_id=team_uuid,  # Changed from project_id to team_id
            job_id=job_uuid,
            repo_url=repo_url,
            team_name=team_name
        )
        
        # Check for fake commits and notify if detected
        if report:
            check_and_notify_fake_commits(team_id, team_name or repo_url, report)
        
        # CREATE SNAPSHOT after successful analysis (for 7-day tracking)
        try:
            # Get job metadata for run tracking
            job_metadata = supabase.table('analysis_jobs').select('run_number, batch_id, metadata').eq('id', job_id).execute()
            run_number = job_metadata.data[0].get('run_number') if job_metadata.data else None
            batch_run_id = job_metadata.data[0].get('metadata', {}).get('batch_run_id') if job_metadata.data else None
            batch_id = job_metadata.data[0].get('batch_id') if job_metadata.data else None
            
            # Create snapshot if we have run tracking info
            if run_number and batch_run_id:
                create_snapshot_from_team(
                    team_id=team_id,
                    run_number=run_number,
                    batch_run_id=batch_run_id
                )
                logger.info(f"📸 Snapshot created for team {team_id}, run {run_number}")
        except Exception as e:
            # Don't fail the job if snapshot creation fails
            logger.warning(f"⚠️ Failed to create snapshot: {e}")
            batch_id = None
        
        logger.info(f"✅ Analysis completed for {team_name or repo_url}")
        
        # Only create individual notification if NOT part of a batch
        # Batch completion notification will be sent separately
        if not batch_id or batch_id == "00000000-0000-0000-0000-000000000000":
            # Single repository analysis (not part of batch)
            # Fetch batch details if available
            batch_info = ""
            try:
                team_data = supabase.table('teams').select('batch_id').eq('id', team_id).single().execute()
                if team_data.data and team_data.data.get('batch_id'):
                    team_batch_id = team_data.data['batch_id']
                    batch_data = supabase.table('batches').select('name, semester, year').eq('id', team_batch_id).single().execute()
                    if batch_data.data:
                        batch_name = batch_data.data.get('name', '')
                        semester = batch_data.data.get('semester', '')
                        year = batch_data.data.get('year', '')
                        batch_info = f" ({batch_name} - {semester} {year})"
            except Exception as e:
                logger.warning(f"Could not fetch batch details: {e}")
            
            create_notification(
                'success',
                f'Analysis Completed: {team_name or repo_url}',
                f'Repository analysis for {team_name or repo_url}{batch_info} completed successfully.',
                {'team_id': team_id, 'job_id': job_id}
            )
        else:
            # Part of batch - skip individual notification
            logger.info(f"   (Part of batch {batch_id} - skipping individual notification)")
        
        return {
            'job_id': job_id,
            'status': 'completed',
            'team_name': team_name
        }
        
    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"❌ Analysis failed for {team_name or repo_url}: {error_msg}")
        
        # Check for Git Authentication/Access errors (don't retry these)
        # 1. Check for subprocess.CalledProcessError with return code 128 (Git error)
        is_git_error_128 = isinstance(exc, subprocess.CalledProcessError) and exc.returncode == 128
        
        # 2. Check for textual indicators in error message
        is_auth_error_text = any(s in error_msg for s in [
            "return code 128", 
            "status 128", 
            "exit status 128",
            "CalledProcessError(128",
            "Authentication failed", 
            "could not read Username",
            "could not read Password"
        ])
        
        is_auth_error = is_git_error_128 or is_auth_error_text
        
        if is_auth_error:
            logger.error(f"🛑 Permanent failure detected (Access Denied/Private Repo). Aborting retries for {repo_url}")
            try:
                AnalysisJobCRUD.fail_job(
                    job_id=UUID(job_id),
                    error_message=f"Access Denied: Private Repository or Invalid Credentials. {error_msg}"
                )
                
                # Check if part of batch
                job_metadata = supabase.table('analysis_jobs').select('batch_id').eq('id', job_id).execute()
                batch_id = job_metadata.data[0].get('batch_id') if job_metadata.data else None
            except Exception as e:
                logger.error(f"Failed to update job status: {e}")
                batch_id = None
            
            # Only create individual notification if NOT part of a batch
            if not batch_id or batch_id == "00000000-0000-0000-0000-000000000000":
                # Single repository analysis (not part of batch)
                create_notification(
                    'error',
                    f'Analysis Failed: {team_name or repo_url}',
                    f'Access Denied: Private Repository or Invalid Credentials.',
                    {'team_id': team_id, 'job_id': job_id}
                )
            else:
                # Part of batch - skip individual notification
                logger.info(f"   (Part of batch {batch_id} - skipping individual failure notification)")
            
            # Don't retry, just return
            return {
                'job_id': job_id,
                'status': 'failed',
                'error': f"Access Denied: {error_msg}"
            }

        # Update job status if max retries exceeded
        if self.request.retries >= self.max_retries:
            try:
                AnalysisJobCRUD.fail_job(
                    job_id=UUID(job_id),
                    error_message=f"Max retries exceeded: {error_msg}"
                )
            except Exception as e:
                logger.error(f"Failed to update job status: {e}")
        
        # Retry with exponential backoff
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    base=CallbackTask,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    retry_backoff=True,  # Exponential backoff
    retry_backoff_max=1800,  # Max 30 minutes
    retry_jitter=True
)
def analyze_single_repository_task(
    self,
    team_id: str,
    job_id: str,
    repo_url: str,
    team_name: str = None
):
    """
    Single repository analysis task (dedicated worker, not part of batch)
    
    This task is identical to analyze_repository_task but routes to a separate
    queue (single_analysis) with its own dedicated worker. This prevents single
    repository analyses from getting stuck behind batch jobs.
    
    Args:
        team_id: Team UUID as string
        job_id: Job UUID as string
        repo_url: GitHub repository URL
        team_name: Optional team name
    
    Returns:
        dict: Analysis results summary
    """
    try:
        logger.info(f"🔍 [SINGLE] Starting analysis for {team_name or repo_url}")
        logger.info(f"Job ID: {job_id}, Team ID: {team_id}")
        
        # Convert string UUIDs to UUID objects
        team_uuid = UUID(team_id)
        job_uuid = UUID(job_id)
        
        # Update job with Celery task ID
        supabase = get_supabase_admin_client()
        supabase.table('analysis_jobs').update({
            'metadata': {
                'celery_task_id': self.request.id,
                'retry_count': self.request.retries,
                'started_at': datetime.now().isoformat(),
                'worker_type': 'single'
            }
        }).eq('id', job_id).execute()
        
        # Run analysis and capture the report
        report = AnalyzerService.analyze_repository(
            team_id=team_uuid,
            job_id=job_uuid,
            repo_url=repo_url,
            team_name=team_name
        )
        
        # Check for fake commits and notify if detected
        if report:
            check_and_notify_fake_commits(team_id, team_name or repo_url, report)
        
        # CREATE SNAPSHOT after successful analysis (for 7-day tracking)
        try:
            # Get job metadata for run tracking
            job_metadata = supabase.table('analysis_jobs').select('run_number, batch_id, metadata').eq('id', job_id).execute()
            run_number = job_metadata.data[0].get('run_number') if job_metadata.data else None
            batch_run_id = job_metadata.data[0].get('metadata', {}).get('batch_run_id') if job_metadata.data else None
            
            # Create snapshot if we have run tracking info
            if run_number and batch_run_id:
                create_snapshot_from_team(
                    team_id=team_id,
                    run_number=run_number,
                    batch_run_id=batch_run_id
                )
                logger.info(f"📸 Snapshot created for team {team_id}, run {run_number}")
        except Exception as e:
            # Don't fail the job if snapshot creation fails
            logger.warning(f"⚠️ Failed to create snapshot: {e}")
        
        logger.info(f"✅ [SINGLE] Analysis completed for {team_name or repo_url}")
        
        # Fetch batch details if available
        batch_info = ""
        try:
            team_data = supabase.table('teams').select('batch_id').eq('id', team_id).single().execute()
            if team_data.data and team_data.data.get('batch_id'):
                team_batch_id = team_data.data['batch_id']
                batch_data = supabase.table('batches').select('name, semester, year').eq('id', team_batch_id).single().execute()
                if batch_data.data:
                    batch_name = batch_data.data.get('name', '')
                    semester = batch_data.data.get('semester', '')
                    year = batch_data.data.get('year', '')
                    batch_info = f" ({batch_name} - {semester} {year})"
        except Exception as e:
            logger.warning(f"Could not fetch batch details: {e}")
        
        # Create in-app notification
        create_notification(
            'success',
            f'Analysis Completed: {team_name or repo_url}',
            f'Single repository analysis for {team_name or repo_url}{batch_info} completed successfully.',
            {'team_id': team_id, 'job_id': job_id, 'worker_type': 'single'}
        )
        
        return {
            'job_id': job_id,
            'status': 'completed',
            'team_name': team_name
        }
        
    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"❌ [SINGLE] Analysis failed for {team_name or repo_url}: {error_msg}")
        
        # Check for Git Authentication/Access errors (don't retry these)
        is_git_error_128 = isinstance(exc, subprocess.CalledProcessError) and exc.returncode == 128
        is_auth_error_text = any(s in error_msg for s in [
            "return code 128", 
            "status 128", 
            "exit status 128",
            "CalledProcessError(128",
            "Authentication failed", 
            "could not read Username",
            "could not read Password"
        ])
        is_auth_error = is_git_error_128 or is_auth_error_text
        
        if is_auth_error:
            logger.error(f"🛑 Permanent failure detected (Access Denied/Private Repo). Aborting retries for {repo_url}")
            try:
                AnalysisJobCRUD.fail_job(
                    job_id=UUID(job_id),
                    error_message=f"Access Denied: Private Repository or Invalid Credentials. {error_msg}"
                )
            except Exception as e:
                logger.error(f"Failed to update job status: {e}")
            
            
            # Create failure notification
            create_notification(
                'error',
                f'Analysis Failed: {team_name or repo_url}',
                f'Access Denied: Private Repository or Invalid Credentials.',
                {'team_id': team_id, 'job_id': job_id, 'worker_type': 'single'}
            )
            
            return {
                'job_id': job_id,
                'status': 'failed',
                'error': f"Access Denied: {error_msg}"
            }

        # Update job status if max retries exceeded
        if self.request.retries >= self.max_retries:
            try:
                AnalysisJobCRUD.fail_job(
                    job_id=UUID(job_id),
                    error_message=f"Max retries exceeded: {error_msg}"
                )
            except Exception as e:
                logger.error(f"Failed to update job status: {e}")
        
        # Retry with exponential backoff
        raise self.retry(exc=exc)


@celery_app.task(bind=True)
def process_batch_sequential(self, batch_id: str, repos: List[Dict[str, str]]):
    """
    Process batch of repositories sequentially
    Maintains sequential processing for GitHub API rate limiting
    
    Args:
        batch_id: Batch UUID as string
        repos: List of dicts with keys: team_id, job_id, repo_url, team_name
    
    Returns:
        dict: Batch processing summary
    """
    logger.info(f"{'='*60}")
    logger.info(f"🚀 Starting Sequential Batch Processing: {len(repos)} repos")
    logger.info(f"   Batch ID: {batch_id}")
    logger.info(f"{'='*60}")
    
    results = {
        'batch_id': batch_id,
        'total': len(repos),
        'queued': 0,
        'failed': 0,
        'paused': False
    }
    
    try:
        supabase = get_supabase_admin_client()
        
        for i, repo in enumerate(repos):
            # Check if batch analysis has been paused
            runs_response = supabase.table("batch_analysis_runs")\
                .select("status")\
                .eq("batch_id", batch_id)\
                .order("run_number", desc=True)\
                .limit(1)\
                .execute()
            
            if runs_response.data and runs_response.data[0].get("status") == "paused":
                logger.info(f"⏸️  Batch analysis paused. Stopping after {i} repos.")
                results['paused'] = True
                break
            
            current_index = i + 1
            team_name = repo.get("team_name", f"Repo {current_index}")
            repo_url = repo.get("repo_url", "")
            team_id = repo.get("team_id")  # Changed from project_id
            job_id = repo.get("job_id")
            
            logger.info(f"[{current_index}/{len(repos)}] 📦 {team_name} | {repo_url}")
            
            # Queue individual analysis task (non-blocking)
            try:
                task_result = analyze_repository_task.delay(
                    team_id, job_id, repo_url, team_name  # Changed from project_id to team_id
                )
                
                results['queued'] += 1
                logger.info(f"    ✅ Queued: {team_name} (task_id: {task_result.id})")
                
            except Exception as e:
                results['failed'] += 1
                logger.error(f"    ❌ Failed to queue: {team_name} - {str(e)}")
            
            # No delay needed - Celery handles task queueing efficiently
            # Rate limiting is handled by the worker processing tasks sequentially
        if results['paused']:
            logger.info(f"⏸️  Batch paused: {results['queued']} queued before pause, {results['failed']} failed to queue")
            create_notification(
                'warning',
                'Batch Analysis Paused',
                f"Batch {batch_id} was paused after queuing {results['queued']} repos.",
                {'batch_id': batch_id, 'queued': results['queued']}
            )
        else:
            logger.info(f"✅ Batch queuing completed: {results['queued']} queued, {results['failed']} failed to queue")
            create_notification(
                'info',
                'Batch Queuing Complete',
                f"All {results['total']} repos queued for analysis. {results['queued']} queued, {results['failed']} failed.",
                {'batch_id': batch_id, 'total': results['total'], 'queued': results['queued'], 'failed': results['failed']}
            )
        
        return results
        
    except Exception as exc:
        logger.error(f"Batch processing failed: {exc}")
        logger.error(traceback.format_exc())
        
        # Notify on batch failure
        create_notification(
            'error',
            'Batch Processing Failed',
            f'Batch {batch_id} failed with error: {str(exc)[:200]}',
            {'batch_id': batch_id}
        )
        
        raise


@celery_app.task(bind=True)
def resume_batch_analysis_task(self, batch_id: str, run_id: str, repos: List[Dict[str, str]]):
    """
    Resume a paused batch analysis
    
    Args:
        batch_id: Batch UUID as string
        run_id: Batch analysis run ID
        repos: List of remaining repos to process
    
    Returns:
        dict: Batch processing summary
    """
    logger.info(f"{'='*60}")
    logger.info(f"▶️  Resuming Batch Analysis: {len(repos)} remaining repos")
    logger.info(f"   Batch ID: {batch_id}")
    logger.info(f"   Run ID: {run_id}")
    logger.info(f"{'='*60}")
    
    # Use the same sequential processing logic
    return process_batch_sequential(batch_id, repos)


@celery_app.task
def move_to_dlq(job_id: str, error: str, traceback_str: str):
    """
    Move failed job to Dead Letter Queue for manual review
    
    Args:
        job_id: Job UUID as string
        error: Error message
        traceback_str: Full traceback
    """
    logger.warning(f"📬 Moving job {job_id} to DLQ")
    
    try:
        supabase = get_supabase_admin_client()
        
        # Update job with DLQ flag
        supabase.table('analysis_jobs').update({
            'status': 'dlq',
            'error_message': f"DLQ: {error}",
            'metadata': {
                'dlq': True,
                'dlq_timestamp': datetime.now().isoformat(),
                'error_traceback': traceback_str,
                'requires_manual_review': True
            }
        }).eq('id', job_id).execute()
        
        logger.info(f"✅ Job {job_id} moved to DLQ")
        
    except Exception as e:
        logger.error(f"Failed to move job to DLQ: {e}")


@celery_app.task
@track_scheduled_task('retry-dlq-nightly', 'Retry DLQ Jobs')
def retry_dlq_jobs():
    """
    Retry jobs in DLQ (manual trigger only)
    """
    logger.info("🔄 Checking DLQ for retry candidates...")
    
    try:
        supabase = get_supabase_admin_client()
        
        # Get all DLQ jobs
        dlq_jobs = supabase.table('analysis_jobs')\
            .select('id, team_id, metadata')\
            .eq('status', 'dlq')\
            .execute()
        
        if not dlq_jobs.data:
            logger.info("No jobs in DLQ")
            return
        
        logger.info(f"Found {len(dlq_jobs.data)} jobs in DLQ")
        
        for job in dlq_jobs.data:
            job_id = job['id']
            team_id = job['team_id']  # Changed from project_id
            
            # Get team details (teams table now has repo_url)
            team = supabase.table('teams')\
                .select('repo_url, team_name')\
                .eq('id', team_id)\
                .single()\
                .execute()
            
            if team.data:
                repo_url = team.data['repo_url']
                team_name = team.data.get('team_name')
                
                # Reset job status
                supabase.table('analysis_jobs').update({
                    'status': 'queued',
                    'error_message': None,
                    'metadata': {'dlq_retry': True}
                }).eq('id', job_id).execute()
                
                # Queue analysis task
                analyze_repository_task.delay(
                    team_id=team_id,  # Changed from project_id
                    job_id=job_id,
                    repo_url=repo_url,
                    team_name=team_name
                )
                
                logger.info(f"✅ Retrying job {job_id} from DLQ")
        
    except Exception as e:
        logger.error(f"Failed to process DLQ: {e}")


@celery_app.task
@track_scheduled_task('weekly-batch-analysis', 'Weekly Batch Analysis')
def auto_trigger_batch_analysis(force: bool = False):
    """
    Automatically trigger batch analysis for all active batches
    Scheduled to run every Monday at 9 AM IST via Celery Beat
    
    Args:
        force: If True, ignore 7-day interval and analyze all teams
    
    Returns:
        dict: Summary of batches processed
    """
    start_time = datetime.now()
    logger.info("="*60)
    logger.info("🔄 Auto-triggering weekly batch analysis")
    logger.info(f"⏰ Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info(f"📍 Force mode: {force}")
    logger.info("="*60)
    
    # Create start notification
    create_notification(
        notification_type='info',
        title='🔄 Weekly Batch Analysis Started',
        message=f'Automated weekly batch analysis started at {start_time.strftime("%H:%M:%S")}',
        metadata={'started_at': start_time.isoformat(), 'force': force}
    )
    
    try:
        supabase = get_supabase_admin_client()
        
        # Get all active batches
        batches = supabase.table('batches')\
            .select('id, name, semester, year')\
            .eq('status', 'active')\
            .execute()
        
        if not batches.data:
            logger.info("No active batches found")
            return {'total_batches': 0, 'triggered': 0}
        
        results = {
            'total_batches': len(batches.data),
            'triggered': 0,
            'skipped': 0,
            'failed': 0,
            'batch_details': []
        }
        
        for batch in batches.data:
            batch_id = batch['id']
            batch_name = f"{batch['semester']} {batch['year']}"
            
            logger.info(f"📦 Processing: {batch_name}")
            
            try:
                # Get teams in batch (teams table now has all analysis data)
                teams = supabase.table('teams')\
                    .select('id, team_name, repo_url, status, last_analyzed_at')\
                    .eq('batch_id', batch_id)\
                    .execute()
                
                if not teams.data or len(teams.data) == 0:
                    logger.info(f"  ⚠️  No teams found in {batch_name}")
                    results['skipped'] += 1
                    continue
                
                # Filter teams that need analysis
                from src.api.backend.routers.analysis import should_allow_reanalysis
                
                repos = []
                for team in teams.data:
                    # Check if team needs analysis
                    allowed, reason = should_allow_reanalysis(team, force=force)
                    
                    if allowed and team.get('repo_url'):
                        # Create analysis job
                        job = supabase.table('analysis_jobs').insert({
                            'team_id': team['id'],
                            'batch_id': batch_id,
                            'status': 'queued',
                            'metadata': {'auto_scheduled': True, 'batch_id': batch_id}
                        }).execute()
                        
                        repos.append({
                            'team_id': team['id'],  # Changed from project_id
                            'job_id': job.data[0]['id'],
                            'repo_url': team.get('repo_url'),
                            'team_name': team['team_name']
                        })
                
                if repos:
                    # Queue batch processing
                    process_batch_sequential.delay(batch_id, repos)
                    logger.info(f"  ✅ Queued {len(repos)} teams for analysis")
                    results['triggered'] += 1
                    results['batch_details'].append({
                        'batch': batch_name,
                        'teams_queued': len(repos)
                    })
                else:
                    logger.info(f"  ⏭️  All teams recently analyzed (within 7-day interval)")
                    results['skipped'] += 1
                    
            except Exception as e:
                logger.error(f"  ❌ Failed to process {batch_name}: {e}")
                results['failed'] += 1
        
        # Send completion notification (includes mentor emails)
        notification_result = send_completion_notification.delay(results)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("="*60)
        logger.info(f"✅ Auto-trigger complete: {results['triggered']} batches triggered")
        logger.info(f"⏱️  Duration: {duration:.2f} seconds")
        logger.info(f"⏰ Completed at: {end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info("="*60)
        
        # Create completion notification
        total_teams = sum(b["teams_queued"] for b in results["batch_details"]) if results["batch_details"] else 0
        create_notification(
            notification_type='success',
            title='✅ Weekly Batch Analysis Completed',
            message=f'Successfully triggered {results["triggered"]} batch(es) with {total_teams} teams queued. Email notifications sent to admins.',
            metadata={
                'started_at': start_time.isoformat(),
                'completed_at': end_time.isoformat(),
                'duration_seconds': duration,
                'results': results,
                'notification_task_id': notification_result.id
            }
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Auto-trigger failed: {e}")
        logger.error(traceback.format_exc())
        return {'error': str(e)}


@celery_app.task
def send_completion_notification(results: dict):
    """
    Send email notification when batch analysis completes.
    Sends personalized emails to:
    - Admins: Full summary of all batches
    
    Args:
        results: Summary dict from auto_trigger_batch_analysis
    
    Returns:
        dict: Notification status (emails_sent, admins_notified)
    """
    logger.info("="*60)
    logger.info("📧 Sending Weekly Analysis Notifications")
    logger.info("📧 Personalizing emails for admins")
    logger.info("="*60)
    logger.info(f"Total Batches: {results.get('total_batches', 0)}")
    logger.info(f"Triggered: {results.get('triggered', 0)}")
    logger.info(f"Skipped: {results.get('skipped', 0)}")
    logger.info(f"Failed: {results.get('failed', 0)}")
    logger.info("")
    
    for detail in results.get('batch_details', []):
        logger.info(f"  ✓ {detail['batch']}: {detail['teams_queued']} teams queued")
    
    logger.info("="*60)
    
    # Send email notifications to admins only
    try:
        from src.api.backend.utils.email import send_alert_email
        
        supabase = get_supabase_admin_client()
        
        # Get all admins
        users_response = supabase.table("users").select("id, email, role, full_name").eq("role", "admin").execute()
        
        if not users_response.data:
            logger.warning("No admins found to send notifications")
            return {"status": "skipped", "reason": "no_recipients"}
        
        # Send to each user
        sent_count = 0
        failed_count = 0
        admin_count = 0
        
        for user in users_response.data:
            try:
                user_role = user.get('role', 'user')
                user_email = user['email']
                user_name = user.get('full_name') or user.get('name') or 'there'
                
                # Build admin email
                frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')

                dashboard_url = f"{frontend_url}/admin/dashboard"
                email_parts = EmailTemplates.weekly_analysis_complete_admin(
                    user_name=user_name,
                    results=results,
                    dashboard_url=dashboard_url,
                )
                email_body = email_parts["text"]
                html_body = email_parts["html"]
                subject = "Weekly Analysis Complete - New Scores Available"
                admin_count += 1
                
                # Send email
                send_alert_email(
                    subject=subject,
                    body_text=email_body,
                    to_email=user_email,
                    html_body=html_body,
                    use_mentor_sender=True,
                )
                sent_count += 1
                logger.info(f"✓ Email sent to {user_email} ({user_role})")
                
            except Exception as e:
                failed_count += 1
                logger.error(f"✗ Failed to send email to {user.get('email', 'unknown')}: {e}")
        
        logger.info(f"📧 Email notifications: {sent_count} sent ({admin_count} admins), {failed_count} failed")
        
        # Collect and send consolidated mentor alerts for each triggered batch
        logger.info("📦 Collecting fake commits alerts for batch mentors...")
        for batch_detail in results.get('batch_details', []):
            # Get batch by name to find ID
            batch_query = supabase.table('batches').select('id').ilike('name', f"%{batch_detail['batch']}%").execute()
            if batch_query.data:
                batch_id = batch_query.data[0]['id']
                try:
                    collect_and_batch_mentor_alerts(batch_id)
                except Exception as e:
                    logger.error(f"Error collecting mentor alerts for batch: {e}")
        
        return {
            "status": "completed",
            "emails_sent": sent_count,
            "emails_failed": failed_count,
            "admins_notified": admin_count,
            "mentors_notified": 0,
            "total_recipients": len(users_response.data)
        }
        
    except Exception as e:
        logger.error(f"Failed to send email notifications: {e}")
        logger.error(traceback.format_exc())
        return {"status": "failed", "error": str(e)}


@celery_app.task
@track_scheduled_task('auto-resume-paused-batches', 'Auto-Resume Paused Batches')
def auto_resume_paused_batches():
    """
    Automatically resume paused batch analyses
    Scheduled to run every Monday at 9:05 AM IST via Celery Beat
    
    This ensures that if an admin paused a batch and forgot to resume it,
    it will automatically resume during the next weekly analysis cycle.
    
    Returns:
        dict: Summary of batches resumed
    """
    start_time = datetime.now()
    logger.info("="*60)
    logger.info("▶️  Auto-resuming paused batch analyses")
    logger.info(f"⏰ Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info("="*60)
    
    # Create start notification
    create_notification(
        notification_type='info',
        title='▶️  Auto-Resume Started',
        message=f'Automatically resuming paused batches at {start_time.strftime("%H:%M:%S")}',
        metadata={'started_at': start_time.isoformat()}
    )
    
    try:
        supabase = get_supabase_admin_client()
        
        # Get all paused batch analysis runs
        paused_runs = supabase.table('batch_analysis_runs')\
            .select('id, batch_id, run_number, batches(name, semester, year)')\
            .eq('status', 'paused')\
            .execute()
        
        if not paused_runs.data:
            logger.info("No paused batch analyses found")
            return {'total_paused': 0, 'resumed': 0}
        
        results = {
            'total_paused': len(paused_runs.data),
            'resumed': 0,
            'failed': 0,
            'batch_details': []
        }
        
        for run in paused_runs.data:
            run_id = run['id']
            batch_id = run['batch_id']
            run_number = run['run_number']
            batch_info = run.get('batches', {})
            batch_name = f"{batch_info.get('semester', 'Unknown')} {batch_info.get('year', '')}"
            
            logger.info(f"📦 Resuming: {batch_name} (Run #{run_number})")
            
            try:
                # Get all teams that haven't been analyzed yet in this run
                teams_result = supabase.table("teams")\
                    .select("id, team_name, repo_url")\
                    .eq("batch_id", batch_id)\
                    .execute()
                
                teams = teams_result.data or []
                
                # Get jobs that are already completed/failed in this run
                jobs_result = supabase.table("analysis_jobs")\
                    .select("team_id, status")\
                    .eq("metadata->>batch_run_id", run_id)\
                    .execute()
                
                completed_team_ids = set(
                    job["team_id"] for job in (jobs_result.data or [])
                    if job["status"] in ["completed", "failed", "cancelled"]
                )
                
                # Build list of remaining repos to process
                repos = []
                for team in teams:
                    if team["id"] not in completed_team_ids and team.get("repo_url"):
                        # Create new analysis job for this team
                        job_insert = {
                            "team_id": team["id"],
                            "status": "queued",
                            "started_at": datetime.now().isoformat(),
                            "metadata": {
                                "batch_run_id": run_id,
                                "run_number": run_number,
                                "auto_resumed": True
                            }
                        }
                        
                        job_result = supabase.table("analysis_jobs").insert(job_insert).execute()
                        job_id = job_result.data[0]["id"]
                        
                        repos.append({
                            "team_id": team["id"],
                            "job_id": job_id,
                            "repo_url": team["repo_url"],
                            "team_name": team["team_name"]
                        })
                
                if not repos:
                    # No remaining repos to process - mark as completed
                    supabase.table("batch_analysis_runs").update({
                        "status": "completed",
                        "completed_at": datetime.now().isoformat()
                    }).eq("id", run_id).execute()
                    
                    logger.info(f"  ✅ No remaining repos - marked as completed")
                    results['resumed'] += 1
                    results['batch_details'].append({
                        'batch': batch_name,
                        'run_number': run_number,
                        'remaining_repos': 0,
                        'status': 'completed'
                    })
                else:
                    # Update run status to running
                    supabase.table("batch_analysis_runs").update({
                        "status": "running",
                        "metadata": {
                            "auto_resumed_at": datetime.now().isoformat(),
                            "auto_resumed": True
                        }
                    }).eq("id", run_id).execute()
                    
                    # Queue Celery task to process remaining repos
                    task = resume_batch_analysis_task.delay(batch_id, run_id, repos)
                    
                    # Store Celery task ID
                    supabase.table("batch_analysis_runs").update({
                        "metadata": {
                            "celery_task_id": task.id,
                            "auto_resumed_at": datetime.now().isoformat(),
                            "auto_resumed": True
                        }
                    }).eq("id", run_id).execute()
                    
                    logger.info(f"  ✅ Resumed with {len(repos)} remaining repos")
                    results['resumed'] += 1
                    results['batch_details'].append({
                        'batch': batch_name,
                        'run_number': run_number,
                        'remaining_repos': len(repos),
                        'status': 'resumed'
                    })
                    
            except Exception as e:
                logger.error(f"  ❌ Failed to resume {batch_name}: {e}")
                results['failed'] += 1
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("="*60)
        logger.info(f"✅ Auto-resume complete: {results['resumed']} batches resumed")
        logger.info(f"⏱️  Duration: {duration:.2f} seconds")
        logger.info(f"⏰ Completed at: {end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info("="*60)
        
        # Create completion notification
        if results['resumed'] > 0:
            create_notification(
                notification_type='success',
                title='✅ Auto-Resume Completed',
                message=f'Successfully resumed {results["resumed"]} batch(es)',
                metadata={
                    'started_at': start_time.isoformat(),
                    'completed_at': end_time.isoformat(),
                    'duration_seconds': duration,
                    'results': results
                }
            )
        
        return results
        
    except Exception as e:
        logger.error(f"Auto-resume failed: {e}")
        logger.error(traceback.format_exc())
        create_notification(
            notification_type='error',
            title='❌ Auto-Resume Failed',
            message=f'Failed to resume paused batches: {str(e)}',
            metadata={'error': str(e)}
        )
        return {'error': str(e)}


@celery_app.task
@track_scheduled_task('update-health-status', 'Update Team Health')
def update_team_health_status():
    """
    Periodic task to update health status for all teams.
    Runs every 2 hours via Celery Beat.
    
    Calculates health status and risk flags based on:
    - Days since last commit
    - Contribution balance
    - Team participation rate
    - Commit velocity trends
    
    Returns:
        dict: Summary of teams updated
    """
    logger.info("="*60)
    logger.info("🏥 Starting Team Health Status Update")
    logger.info("="*60)
    
    try:
        from src.api.backend.utils.health import calculate_team_health
        import json
        
        supabase = get_supabase_admin_client()
        
        # Get all teams with basic info (include report_path for storage lookup)
        teams_response = supabase.table("teams").select(
            "id, team_name, last_activity, created_at, report_json, report_path"
        ).execute()
        
        teams = teams_response.data or []
        logger.info(f"📊 Processing {len(teams)} teams")
        
        updated = 0
        errors = 0
        health_counts = {"on_track": 0, "at_risk": 0, "critical": 0}
        
        for team in teams:
            try:
                # Get report from storage if migrated, otherwise from database
                report_path = team.get("report_path")
                if report_path:
                    try:
                        report_json = ReportStorageManager.get_report_from_storage(report_path)
                    except Exception:
                        report_json = team.get("report_json")
                else:
                    report_json = team.get("report_json")
                    
                if isinstance(report_json, str):
                    try:
                        report_json = json.loads(report_json)
                    except:
                        report_json = None
                
                # Get member count (assume 4 if not known)
                team_members_count = 4
                if report_json and report_json.get("author_stats"):
                    team_members_count = max(4, len(report_json.get("author_stats", [])))
                
                # Calculate health
                health_status, risk_flags = calculate_team_health(
                    report_json=report_json,
                    team_members_count=team_members_count,
                    last_activity=team.get("last_activity"),
                    created_at=team.get("created_at")
                )
                
                # Update team in database
                supabase.table("teams").update({
                    "health_status": health_status,
                    "risk_flags": risk_flags,
                    "last_health_check": datetime.utcnow().isoformat()
                }).eq("id", team["id"]).execute()
                
                updated += 1
                health_counts[health_status] = health_counts.get(health_status, 0) + 1
                
                if risk_flags:
                    logger.debug(f"  {team['team_name']}: {health_status} - {risk_flags}")
                    
            except Exception as e:
                logger.error(f"Error updating team {team.get('team_name')}: {e}")
                errors += 1
        
        results = {
            "total_teams": len(teams),
            "updated": updated,
            "errors": errors,
            "health_distribution": health_counts
        }
        
        logger.info("="*60)
        logger.info(f"✅ Health update complete:")
        logger.info(f"   On Track: {health_counts.get('on_track', 0)}")
        logger.info(f"   At Risk: {health_counts.get('at_risk', 0)}")
        logger.info(f"   Critical: {health_counts.get('critical', 0)}")
        logger.info(f"   Errors: {errors}")
        logger.info("="*60)
        
        return results
        
    except Exception as e:
        logger.error(f"Health update task failed: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}


def is_weekly_reports_already_running(supabase_client=None, exclude_notification_id: str = None) -> dict:
    """
    Check if a weekly student reports task is already actively running.
    Returns {'running': True/False, 'notification_id': str or None, 'started_at': str or None}
    
    A run is considered "active" if:
    - It has state='running'
    - Its last checkpoint is within the last 30 minutes (not stale)
    """
    try:
        supabase = supabase_client or get_supabase_admin_client()
        stale_cutoff = (datetime.utcnow() - timedelta(minutes=30)).isoformat()

        recent = supabase.table('notifications')\
            .select('id, metadata, created_at')\
            .eq('title', '📧 Weekly Reports Started')\
            .order('created_at', desc=True)\
            .limit(10)\
            .execute()

        for row in (recent.data or []):
            metadata = row.get('metadata') or {}
            if metadata.get('task') != 'weekly_student_reports':
                continue
            if metadata.get('test_mode'):
                continue
            if metadata.get('state') != 'running':
                continue
            # Allow the same run to proceed (for resume)
            if exclude_notification_id and row['id'] == exclude_notification_id:
                continue

            last_checkpoint_at = metadata.get('last_checkpoint_at') or metadata.get('started_at') or row.get('created_at')
            # Only consider it "active" if it checkpointed within the last 30 minutes
            if last_checkpoint_at and last_checkpoint_at >= stale_cutoff:
                return {
                    'running': True,
                    'notification_id': row['id'],
                    'started_at': metadata.get('started_at'),
                    'last_checkpoint_at': last_checkpoint_at,
                }

        return {'running': False, 'notification_id': None, 'started_at': None}
    except Exception as e:
        logger.warning(f"Failed to check weekly-reports lock: {e}")
        return {'running': False, 'notification_id': None, 'started_at': None}


@celery_app.task
@track_scheduled_task('weekly-student-reports', 'Weekly Student Reports')
def send_weekly_student_reports(
    test_email: Optional[str] = None,
    max_emails: Optional[int] = None,
    resume_notification_id: Optional[str] = None,
):
    """
    Send weekly PDF analysis reports to students via email.
    For each team with a completed analysis, generates a PDF report
    and emails it to every student on that team.
    
    Scheduled: Monday 12 PM IST via celery beat.
    Can also be triggered manually via the admin API.
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("📧 Starting Weekly Student Report Emails")
    logger.info(f"⏰ Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info("=" * 60)

    is_test_mode = bool(test_email)
    email_limit = max_emails if (isinstance(max_emails, int) and max_emails > 0) else None
    if is_test_mode and email_limit is None:
        email_limit = 1

    # ── Duplicate-run guard ──────────────────────────────────────────
    # Skip this check for test-mode (single test email) and for resumed runs
    if not is_test_mode and not resume_notification_id:
        lock_check = is_weekly_reports_already_running()
        if lock_check['running']:
            logger.warning(
                f"⛔ Another weekly reports run is already active "
                f"(notification={lock_check['notification_id']}, "
                f"last_checkpoint={lock_check['last_checkpoint_at']}). "
                f"Aborting this duplicate run."
            )
            create_notification(
                'warning',
                '⛔ Duplicate Report Run Blocked',
                f"A weekly reports run is already in progress (started {lock_check.get('started_at', 'unknown')}). "
                f"This duplicate trigger was blocked to prevent sending duplicate emails.",
                {'blocked_at': datetime.utcnow().isoformat(), 'active_notification_id': lock_check['notification_id']}
            )
            return {
                'status': 'blocked',
                'reason': 'another_run_already_active',
                'active_notification_id': lock_check['notification_id'],
            }

    task_run_id = str(uuid4())
    checkpoint_notification_id = resume_notification_id
    processed_team_ids = set()
    is_resumed_run = False
    
    stats = {
        'teams_processed': 0,
        'emails_attempted': 0,
        'emails_sent': 0,
        'emails_failed': 0,
        'teams_skipped': 0,
        'sent_recipients_sample': [],
        'failed_recipients_sample': [],
        'sent_tracking_overflow': 0,
        'failed_tracking_overflow': 0,
    }

    max_tracking_sample = 50

    def build_checkpoint_metadata(state: str, error: Optional[str] = None):
        payload = {
            'task': 'weekly_student_reports',
            'task_run_id': task_run_id,
            'state': state,
            'started_at': start_time.isoformat(),
            'last_checkpoint_at': datetime.utcnow().isoformat(),
            'test_mode': is_test_mode,
            'test_email': test_email,
            'max_emails': email_limit,
            'resumed': is_resumed_run,
            'resume_notification_id': checkpoint_notification_id,
            'recovery_in_progress': False,
            'processed_team_ids': list(processed_team_ids),
            'stats': {
                'teams_processed': stats['teams_processed'],
                'teams_skipped': stats['teams_skipped'],
                'emails_attempted': stats['emails_attempted'],
                'emails_sent': stats['emails_sent'],
                'emails_failed': stats['emails_failed'],
            },
            'mail_tracking': {
                'sent_recipients_sample': stats['sent_recipients_sample'],
                'failed_recipients_sample': stats['failed_recipients_sample'],
                'sent_tracking_overflow': stats['sent_tracking_overflow'],
                'failed_tracking_overflow': stats['failed_tracking_overflow'],
            }
        }
        if error:
            payload['error'] = str(error)[:500]
        return payload

    def persist_checkpoint(state: str, message: Optional[str] = None, error: Optional[str] = None):
        if is_test_mode or not checkpoint_notification_id:
            return
        update_payload = {
            'metadata': build_checkpoint_metadata(state=state, error=error)
        }
        if message:
            update_payload['message'] = message
        update_notification(checkpoint_notification_id, update_payload)

    def track_email_event(status: str, team_id: str, team_name: str, student_name: str, student_email: str, error: str = None):
        event = {
            'status': status,
            'team_id': team_id,
            'team_name': team_name,
            'student_name': student_name,
            'email': student_email,
            'timestamp': datetime.utcnow().isoformat()
        }
        if error:
            event['error'] = str(error)[:300]

        if status == 'sent':
            if len(stats['sent_recipients_sample']) < max_tracking_sample:
                stats['sent_recipients_sample'].append(event)
            else:
                stats['sent_tracking_overflow'] += 1
        else:
            if len(stats['failed_recipients_sample']) < max_tracking_sample:
                stats['failed_recipients_sample'].append(event)
            else:
                stats['failed_tracking_overflow'] += 1

    def log_email_to_db(
        supabase_client,
        *,
        status: str,
        team_id,
        team_name: str,
        student_name: str,
        student_email: str,
        batch_id=None,
        subject: str = None,
        has_report_pdf: bool = False,
        has_leaderboard_pdf: bool = False,
        error_message: str = None,
        email_type: str = 'weekly_report',
    ):
        """Persist a row in email_send_log for every email attempt."""
        try:
            row = {
                'notification_id': checkpoint_notification_id,
                'task_run_id': task_run_id,
                'team_id': str(team_id) if team_id else None,
                'team_name': team_name,
                'student_name': student_name,
                'student_email': student_email,
                'batch_id': str(batch_id) if batch_id else None,
                'status': status,
                'email_type': 'test' if is_test_mode else email_type,
                'subject': (subject or '')[:500],
                'has_report_pdf': has_report_pdf,
                'has_leaderboard_pdf': has_leaderboard_pdf,
            }
            if error_message:
                row['error_message'] = str(error_message)[:1000]
            if status == 'sent':
                row['sent_at'] = datetime.utcnow().isoformat()
            supabase_client.table('email_send_log').insert(row).execute()
        except Exception as log_err:
            logger.warning(f"Failed to log email to DB: {log_err}")

    def compute_weekly_individual_marks(
        students_list,
        team_members_list,
        contributors,
        total_commits_value,
        team_total_score_value,
    ):
        """
        Build per-student weekly marks using contribution share.
        Mark formula: team_total_score * contribution_pct - inactivity_penalty.
        """
        try:
            from src.api.backend.utils.contributor_identity import TeamMemberIdentityResolver
        except Exception as identity_err:
            logger.warning(f"Could not load contributor identity resolver: {identity_err}")
            TeamMemberIdentityResolver = None

        resolver = TeamMemberIdentityResolver(team_members_list) if TeamMemberIdentityResolver else None
        marks_by_student: Dict[str, Dict[str, Any]] = {}

        for student in (students_list or []):
            sid = str(student.get("id") or "")
            if not sid:
                continue

            marks_by_student[sid] = {
                "studentId": sid,
                "name": student.get("name", "Unknown"),
                "email": student.get("email"),
                "github": student.get("github_username"),
                "commits": 0,
                "additions": 0,
                "deletions": 0,
                "contributionPct": 0.0,
                "weeklyBaseMark": 0.0,
                "inactivityPenalty": float(student.get("inactivity_penalty") or 0),
                "weeklyIndividualMark": 0.0,
            }

        if not marks_by_student:
            return []

        for contributor in (contributors or []):
            if not isinstance(contributor, dict):
                continue

            matched_member = resolver.resolve_member(contributor.get("name")) if resolver else None
            matched_sid = str(matched_member.get("id") or "") if matched_member else ""
            if not matched_sid or matched_sid not in marks_by_student:
                continue

            marks_by_student[matched_sid]["commits"] += int(contributor.get("commits") or 0)
            marks_by_student[matched_sid]["additions"] += int(contributor.get("additions") or 0)
            marks_by_student[matched_sid]["deletions"] += int(contributor.get("deletions") or 0)

        for sid, entry in marks_by_student.items():
            commits = int(entry.get("commits") or 0)
            if total_commits_value > 0:
                contribution_pct = round((commits / total_commits_value) * 100, 1)
            else:
                contribution_pct = 0.0

            weekly_base_mark = round((team_total_score_value * contribution_pct) / 100.0, 2)
            inactivity_penalty = float(entry.get("inactivityPenalty") or 0)
            final_mark = round(max(0.0, weekly_base_mark - inactivity_penalty), 2)

            entry["contributionPct"] = contribution_pct
            entry["weeklyBaseMark"] = weekly_base_mark
            entry["weeklyIndividualMark"] = final_mark

        marks = list(marks_by_student.values())
        marks.sort(key=lambda item: (item.get("weeklyIndividualMark") or 0, item.get("commits") or 0), reverse=True)
        return marks

    def persist_weekly_individual_marks(supabase_client, marks_payload, week_date_iso: str):
        """Persist latest weekly individual contribution marks for students."""
        for mark in (marks_payload or []):
            student_id = mark.get("studentId")
            if not student_id:
                continue

            try:
                existing_result = supabase_client.table("students").select("grading_details").eq("id", student_id).limit(1).execute()
                existing_student = (existing_result.data or [{}])[0]
                grading_details = existing_student.get("grading_details") or {}
                if not isinstance(grading_details, dict):
                    grading_details = {}

                grading_details["lastWeeklyContributionMark"] = {
                    "week_date": week_date_iso,
                    "weekly_individual_mark": mark.get("weeklyIndividualMark", 0),
                    "weekly_base_mark": mark.get("weeklyBaseMark", 0),
                    "contribution_pct": mark.get("contributionPct", 0),
                    "commits": mark.get("commits", 0),
                    "inactivity_penalty": mark.get("inactivityPenalty", 0),
                }

                supabase_client.table("students").update({
                    "contribution_score": mark.get("weeklyIndividualMark", 0),
                    "commit_count": mark.get("commits", 0),
                    "lines_added": mark.get("additions", 0),
                    "lines_deleted": mark.get("deletions", 0),
                    "grading_details": grading_details,
                }).eq("id", student_id).execute()
            except Exception as persist_err:
                logger.warning(f"Could not persist weekly mark for student {student_id}: {persist_err}")
    
    try:
        from src.api.backend.utils.email import send_email_with_attachment, EmailConfigError
        from src.api.backend.utils.pdf_generator import generate_team_report_pdf
        from src.api.backend.utils.student_report_fields import build_student_report_fields
    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        return {"error": str(e)}
    
    try:
        supabase = get_supabase_admin_client()

        if not is_test_mode and checkpoint_notification_id:
            try:
                checkpoint_result = supabase.table('notifications').select('id, metadata').eq('id', checkpoint_notification_id).single().execute()
                checkpoint_data = checkpoint_result.data or {}
                checkpoint_metadata = checkpoint_data.get('metadata') or {}

                if checkpoint_metadata.get('task') == 'weekly_student_reports':
                    processed_team_ids = set(checkpoint_metadata.get('processed_team_ids', []) or [])
                    checkpoint_stats = checkpoint_metadata.get('stats') or {}
                    stats['teams_processed'] = checkpoint_stats.get('teams_processed', 0)
                    stats['teams_skipped'] = checkpoint_stats.get('teams_skipped', 0)
                    stats['emails_attempted'] = checkpoint_stats.get('emails_attempted', 0)
                    stats['emails_sent'] = checkpoint_stats.get('emails_sent', 0)
                    stats['emails_failed'] = checkpoint_stats.get('emails_failed', 0)

                    checkpoint_tracking = checkpoint_metadata.get('mail_tracking') or {}
                    stats['sent_recipients_sample'] = checkpoint_tracking.get('sent_recipients_sample', []) or []
                    stats['failed_recipients_sample'] = checkpoint_tracking.get('failed_recipients_sample', []) or []
                    stats['sent_tracking_overflow'] = checkpoint_tracking.get('sent_tracking_overflow', 0)
                    stats['failed_tracking_overflow'] = checkpoint_tracking.get('failed_tracking_overflow', 0)
                    is_resumed_run = True

                    logger.info(
                        f"♻️ Resuming weekly reports from checkpoint {checkpoint_notification_id} "
                        f"({len(processed_team_ids)} team(s) already processed)"
                    )
                else:
                    checkpoint_notification_id = None
            except Exception as checkpoint_error:
                logger.warning(f"Failed to load checkpoint {checkpoint_notification_id}: {checkpoint_error}")
                checkpoint_notification_id = None

        if not is_test_mode and not checkpoint_notification_id:
            start_notification = create_notification(
                notification_type='info',
                title='📧 Weekly Reports Started',
                message=f'Sending weekly student reports at {start_time.strftime("%H:%M:%S")}',
                metadata=build_checkpoint_metadata(state='running')
            )
            checkpoint_notification_id = (start_notification or {}).get('id')

        if is_test_mode:
            create_notification(
                notification_type='info',
                title='📧 Weekly Reports Started',
                message=f'Sending test weekly report email to {test_email} at {start_time.strftime("%H:%M:%S")}',
                metadata={
                    'task': 'weekly_student_reports',
                    'task_run_id': task_run_id,
                    'state': 'running',
                    'started_at': start_time.isoformat(),
                    'test_mode': is_test_mode,
                    'test_email': test_email,
                    'max_emails': email_limit
                }
            )
        
        # Get all teams with completed analyses
        teams_response = supabase.table("teams").select(
            "*, students(*)"
        ).not_.is_("last_analyzed_at", "null").execute()
        
        if not teams_response.data:
            logger.info("No analyzed teams found. Skipping.")
            return {"status": "skipped", "reason": "no_analyzed_teams"}
        
        logger.info(f"Found {len(teams_response.data)} analyzed teams")

        if not is_test_mode and is_resumed_run:
            persist_checkpoint(
                state='running',
                message=(
                    f"Resumed weekly reports run. {len(processed_team_ids)} team(s) already processed, "
                    f"continuing remaining teams."
                )
            )
        
        stop_sending = False
        # Collect critical-fake-commit teams per mentor for a post-run summary email
        mentor_fake_teams: dict = {}  # mentor_id -> list of team info dicts
        # Cache leaderboard data per batch (fetched at most once per batch)
        batch_leaderboard_data: dict = {}
        for team in teams_response.data:
            team_name = team.get("team_name", "Unknown Team")
            team_id = team.get("id")
            team_id_str = str(team_id) if team_id else None
            students = team.get("students", [])

            if not is_test_mode and team_id_str and team_id_str in processed_team_ids:
                logger.info(f"  ⏭️  {team_name}: Already processed in checkpoint, skipping")
                continue
            
            # Filter students with valid emails
            students_with_email = [
                s for s in (students or [])
                if s.get("email") and s["email"].strip()
            ]
            
            if not students_with_email:
                logger.info(f"  ⏭️  {team_name}: No students with emails, skipping")
                stats['teams_skipped'] += 1
                if not is_test_mode and team_id_str:
                    processed_team_ids.add(team_id_str)
                    persist_checkpoint(
                        state='running',
                        message=(
                            f"Weekly reports in progress: {stats['teams_processed']} team(s) processed, "
                            f"{stats['teams_skipped']} skipped, {stats['emails_sent']} sent, {stats['emails_failed']} failed."
                        )
                    )
                continue
            
            try:
                # Build report data - fetch from storage if migrated
                report_path = team.get("report_path")
                if report_path:
                    try:
                        report_json = ReportStorageManager.get_report_from_storage(report_path)
                        logger.debug(f"Loaded report from storage for {team_name}: {report_path}")
                    except Exception as storage_err:
                        logger.warning(f"Failed to load report from storage for {team_name}: {storage_err}")
                        report_json = team.get("report_json", {})
                else:
                    report_json = team.get("report_json", {})
                
                if isinstance(report_json, str):
                    try:
                        report_json = json.loads(report_json)
                    except Exception:
                        report_json = {}
                
                forensics = report_json.get("forensics", {})
                author_stats_raw = forensics.get("author_stats", {})
                
                if isinstance(author_stats_raw, dict):
                    author_stats = [
                        {"author": name, **data} if isinstance(data, dict) else {"author": name}
                        for name, data in author_stats_raw.items()
                    ]
                elif isinstance(author_stats_raw, list):
                    author_stats = author_stats_raw
                else:
                    author_stats = []
                
                languages = report_json.get("languages", [])
                structure = report_json.get("structure", {})
                maturity = report_json.get("maturity", {})
                
                files_data = report_json.get("files", [])
                total_files = len(files_data) if isinstance(files_data, list) and len(files_data) > 0 else 0
                if total_files == 0:
                    total_files = maturity.get("test_files", 0)
                
                total_loc = 0
                for author_data in author_stats:
                    if isinstance(author_data, dict):
                        total_loc += author_data.get("lines_changed", 0) or 0
                if total_loc <= 0:
                    total_loc = (
                        team.get("total_loc")
                        or report_json.get("code_metrics", {}).get("total_lines_of_code", 0)
                        or report_json.get("summary", {}).get("total_lines", 0)
                        or 0
                    )
                
                repo_url = team.get("repo_url", "")
                project_name = ""
                if repo_url:
                    repo_name = repo_url.rstrip("/").rstrip(".git").split("/")[-1]
                    if repo_name:
                        project_name = repo_name
                if not project_name:
                    project_name = report_json.get("team", {}).get("project_name") or team_name
                
                metadata = team.get("metadata", {}) or {}
                ingestion = metadata.get("ingestion", {}) or {}
                problem_statement = ingestion.get("project_statement", "") or report_json.get("judge", {}).get("description", "")
                
                team_members = [
                    {
                        "id": s.get("id"),
                        "name": s.get("name", "Unknown"),
                        "email": s.get("email"),
                        "github": s.get("github_username")
                    }
                    for s in students
                ] if isinstance(students, list) else []
                
                # Extract enriched fields (matching manual send_team_report_email)
                scores = report_json.get("scores", {})
                judge = report_json.get("judge", {})
                features = judge.get("features", [])
                tech_stack_observed = judge.get("tech_stack_observed", [])
                positive_feedback = judge.get("positive_feedback", "")
                constructive_feedback = judge.get("constructive_feedback", "")
                ai_verdict = judge.get("verdict", team.get("verdict", "Unknown"))
                
                feature_analysis = judge.get("feature_analysis", [])
                product_analysis = judge.get("product_analysis", {})
                suggested_features = judge.get("suggested_features", [])
                overall_recommendation = judge.get("overall_recommendation", "")
                
                functionality_check = judge.get("functionality_check", {})
                completeness_analysis = judge.get("completeness_analysis", {})
                quality_indicators = judge.get("quality_indicators", {})
                verdict_reasoning = judge.get("verdict_reasoning", "")
                
                commit_details = report_json.get("commit_details", {})
                recent_commits = commit_details.get("recent_commits", [])[:10]

                # --- collect critical fake commits for mentor notification ---
                _mentor_id = team.get("mentor_id")
                if _mentor_id and not is_test_mode:
                    _fc_count = commit_details.get("fake_commit_count", 0)
                    _commit_health = commit_details.get("commit_health", "Healthy")
                    _ai_bot_detection = commit_details.get("ai_bot_detection", {}) or {}
                    _ai_bot_contributors = _ai_bot_detection.get("ai_bot_contributors", []) if isinstance(_ai_bot_detection, dict) else []
                    _ai_bot_contributors = [b for b in _ai_bot_contributors if isinstance(b, dict)]
                    _total_commits = max(1, int(commit_details.get("total_commits", 0) or 0))
                    _ai_bot_commits = sum(int(b.get("commits", 0) or 0) for b in _ai_bot_contributors)
                    _ai_bot_share = (_ai_bot_commits / _total_commits) * 100.0
                    _has_ai_bot_majority = _ai_bot_share > 50.0

                    if (_commit_health == "Critical" and _fc_count > 0) or _has_ai_bot_majority:
                        if _mentor_id not in mentor_fake_teams:
                            mentor_fake_teams[_mentor_id] = []
                        mentor_fake_teams[_mentor_id].append({
                            "team_id": str(team_id) if team_id else "N/A",
                            "team_name": team_name,
                            "project_name": project_name,
                            "repo_url": repo_url,
                            "fake_commit_count": _fc_count,
                            "fake_commit_ratio": commit_details.get("fake_commit_ratio", 0.0),
                            "commit_health": _commit_health,
                            "total_commits": commit_details.get("total_commits", 0),
                            "ai_bot_commit_count": _ai_bot_commits,
                            "ai_bot_share": round(_ai_bot_share, 1),
                            "has_ai_bot_majority": _has_ai_bot_majority,
                        })
                
                security = report_json.get("security", {})
                security_issues = security.get("issues", [])
                secrets_count = security.get("secrets_found", 0) or security.get("leak_count", 0)
                hardcoded_values = security.get("hardcoded_values", [])
                security_leaks = security.get("leaks", security.get("details", []))
                best_practices = security.get("best_practices", [])
                security_recommendations = security.get("recommendations", [])
                secrets_score = security.get("secrets_score")
                practices_score = security.get("practices_score")
                
                maturity_data = report_json.get("maturity", {})
                risky_files = report_json.get("files", [])[:10]
                llm_detection = report_json.get("llm_detection", {})
                overall_ai_percentage = llm_detection.get("overall_percentage", 0)
                
                total_commits_count = team.get("total_commits") or forensics.get("total_commits", 0) or 1
                contributors_with_pct = []
                for c in author_stats:
                    if isinstance(c, dict):
                        commit_count = c.get("commits", c.get("commit_count", 0)) or 0
                        contribution_pct = round((commit_count / total_commits_count) * 100, 1) if total_commits_count > 0 else 0
                        additions = c.get("additions", c.get("lines_added", c.get("lines_changed", 0))) or 0
                        deletions = c.get("deletions", c.get("lines_deleted", 0)) or 0
                        estimated_lines = False
                        if additions == 0 and deletions == 0 and total_loc > 0 and contribution_pct > 0:
                            additions = int(round((contribution_pct / 100.0) * total_loc * 0.8))
                            deletions = int(round((contribution_pct / 100.0) * total_loc * 0.2))
                            estimated_lines = True

                        contributors_with_pct.append({
                            "name": c.get("author", c.get("name", "Unknown")),
                            "commits": commit_count,
                            "additions": additions,
                            "deletions": deletions,
                            "contributionPct": contribution_pct,
                            "isEstimatedLines": estimated_lines
                        })

                team_total_score = float(team.get("total_score") or 0)
                weekly_individual_marks = compute_weekly_individual_marks(
                    students,
                    team_members,
                    contributors_with_pct,
                    total_commits_count,
                    team_total_score,
                )

                if not is_test_mode:
                    persist_weekly_individual_marks(
                        supabase,
                        weekly_individual_marks,
                        datetime.utcnow().date().isoformat(),
                    )
                
                # Extract individual student contribution-based scores
                individual_student_scores = []

                # Build a flexible map for enrichment (score rows are still emitted even if no exact match is found).
                student_map = {}
                for s in students:
                    if isinstance(s, dict):
                        name = (s.get("name") or "").lower().strip()
                        github = (s.get("github_username") or "").lower().strip()
                        if name:
                            student_map[f"name:{name}"] = s
                        if github:
                            student_map[f"github:{github}"] = s

                # Use normalized contributor rows so every contributor gets a score row.
                max_contributor_lines = max(
                    1,
                    max(
                        (
                            int((row.get("additions", 0) or 0) + (row.get("deletions", 0) or 0))
                            for row in contributors_with_pct
                            if isinstance(row, dict)
                        ),
                        default=1,
                    ),
                )

                for c in contributors_with_pct:
                    if not isinstance(c, dict):
                        continue

                    contributor_name = str(c.get("name", "Unknown") or "Unknown").strip()
                    author_key = contributor_name.lower()

                    student = (
                        student_map.get(f"name:{author_key}")
                        or student_map.get(f"github:{author_key}")
                    )

                    commit_count = c.get("commits", 0) or 0
                    additions = c.get("additions", 0) or 0
                    deletions = c.get("deletions", 0) or 0
                    contribution_pct = c.get("contributionPct", 0) or 0

                    # Calculate contribution-based scoring components.
                    contribution_score = round(float(contribution_pct), 2)
                    effort_score = min(100, round((commit_count / max(1, total_commits_count)) * 100, 2))
                    total_lines_changed = additions + deletions
                    is_estimated_lines = bool(c.get("isEstimatedLines", False))
                    lines_per_commit = total_lines_changed / max(1, commit_count)
                    impact_score = min(100, round((total_lines_changed / max_contributor_lines) * 100, 2))
                    depth_score = min(100, round((lines_per_commit / 120.0) * 100, 2))
                    bigger = max(additions, deletions)
                    balance_ratio = (min(additions, deletions) / max(1, bigger)) if bigger > 0 else 0
                    balance_score = round(20 + (80 * balance_ratio), 2)
                    quality_score = round((impact_score * 0.45 + depth_score * 0.4 + balance_score * 0.15), 2)
                    if is_estimated_lines:
                        quality_score = round(min(quality_score, float(contribution_pct) + 10), 2)

                    combined_score = round((contribution_score * 0.4 + effort_score * 0.35 + quality_score * 0.25), 2)

                    deductions = 0
                    commit_quality_data = report_json.get("commit_details", {})
                    if isinstance(commit_quality_data, dict):
                        fake_commits = commit_quality_data.get("fake_commits", [])
                        if isinstance(fake_commits, list) and commit_count > 0:
                            author_fake_commits = sum(
                                1
                                for fc in fake_commits
                                if isinstance(fc, dict)
                                and str(fc.get("author", "")).lower().strip() == author_key
                            )
                            if author_fake_commits > 0:
                                deductions = round(min(10, (author_fake_commits / commit_count) * 10), 2)

                    final_score = max(0, round(combined_score - deductions, 2))

                    student_score_entry = {
                        "id": student.get("id") if student else None,
                        "name": student.get("name", contributor_name) if student else contributor_name,
                        "email": student.get("email") if student else None,
                        "github": student.get("github_username") if student else None,
                        "commits": commit_count,
                        "contributionPercentage": contribution_pct,
                        "contributionScore": contribution_score,
                        "effortScore": effort_score,
                        "qualityScore": quality_score,
                        "deductions": deductions,
                        "finalScore": final_score,
                        "linesAdded": additions,
                        "linesDeleted": deletions,
                    }

                    individual_student_scores.append(student_score_entry)
                
                report_data = {
                    "teamId": team_id,
                    "teamName": team_name,
                    "projectName": project_name,
                    "problemStatement": problem_statement,
                    "repoUrl": repo_url,
                    "teamMembers": team_members,
                    "individualStudentScores": individual_student_scores,
                    "batchId": team.get("batch_id"),
                    "generatedAt": datetime.utcnow().isoformat(),
                    "analysis": {
                        "totalScore": team.get("total_score") or 0,
                        "qualityScore": team.get("quality_score") or scores.get("quality", 0),
                        "securityScore": team.get("security_score") or scores.get("security", 0),
                        "originalityScore": team.get("originality_score") or scores.get("originality", 0),
                        "architectureScore": team.get("architecture_score") or scores.get("organization", 0),
                        "documentationScore": team.get("documentation_score") or scores.get("documentation", 0),
                        "effortScore": scores.get("effort", 0),
                        "implementationScore": scores.get("implementation", 0),
                        "engineeringScore": scores.get("engineering", 0)
                    },
                    "commits": {
                        "total": total_commits_count,
                        "contributors": contributors_with_pct,
                        "recentCommits": recent_commits
                    },
                    "weeklyIndividualMarks": weekly_individual_marks,
                    "codeMetrics": {
                        "totalFiles": total_files,
                        "totalLinesOfCode": total_loc,
                        "languages": languages if isinstance(languages, list) else list(languages.keys()) if isinstance(languages, dict) else [],
                        "languagesWithPct": languages if isinstance(languages, dict) else {},
                        "architecturePattern": structure.get("architecture", "Unknown") if isinstance(structure, dict) else "Unknown",
                        "techStack": tech_stack_observed,
                        "frameworks": report_json.get("stack", [])
                    },
                    "security": {
                        "score": team.get("security_score") or scores.get("security", 0),
                        "secretsScore": secrets_score,
                        "practicesScore": practices_score,
                        "issues": security_issues,
                        "secretsDetected": secrets_count,
                        "hardcodedValues": hardcoded_values,
                        "leaks": security_leaks,
                        "bestPractices": best_practices,
                        "recommendations": security_recommendations
                    },
                    "aiAnalysis": {
                        "aiGeneratedPercentage": overall_ai_percentage,
                        "verdict": ai_verdict,
                        "verdictReasoning": verdict_reasoning,
                        "strengths": team.get("ai_pros") or (positive_feedback.split(". ") if positive_feedback else []),
                        "improvements": team.get("ai_cons") or (constructive_feedback.split(". ") if constructive_feedback else []),
                        "features": features,
                        "positiveFeedback": positive_feedback,
                        "constructiveFeedback": constructive_feedback,
                        "featureAnalysis": feature_analysis,
                        "suggestedFeatures": suggested_features,
                        "overallRecommendation": overall_recommendation,
                        "functionalityCheck": functionality_check,
                        "completenessAnalysis": completeness_analysis,
                        "qualityIndicators": quality_indicators
                    },
                    "productAnalysis": product_analysis,
                    "riskyFiles": risky_files,
                    "maturity": {
                        "hasTests": maturity_data.get("test_files", 0) > 0,
                        "testFiles": maturity_data.get("test_files", 0),
                        "hasCI": maturity_data.get("has_ci", False),
                        "hasDocker": maturity_data.get("has_docker", False),
                        "hasReadme": maturity_data.get("has_readme", False)
                    },
                    "healthStatus": team.get("health_status", "on_track"),
                    "riskFlags": team.get("risk_flags", []),
                    "lastAnalyzedAt": team.get("last_analyzed_at") or team.get("analyzed_at")
                }
                
                student_report_fields = build_student_report_fields(report_json, total_commits_count)
                report_data["commitQuality"] = student_report_fields["commitQuality"]
                report_data["marksDeduction"] = student_report_fields["marksDeduction"]

                # Generate PDF
                pdf_bytes = generate_team_report_pdf(report_data)
                safe_name = team_name.replace(' ', '_').replace('/', '_')[:30]
                filename = f"{safe_name}_report_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
                
                # Fetch and cache Leaderboard Data per batch
                batch_id = team.get("batch_id")
                if batch_id and batch_id not in batch_leaderboard_data:
                    try:
                        import asyncio
                        from src.api.backend.services.leaderboard_service import LeaderboardService
                        ls = LeaderboardService()
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        
                        data = loop.run_until_complete(ls.get_full_batch_leaderboard(batch_id))
                        batch_leaderboard_data[batch_id] = data
                    except Exception as e:
                        logger.error(f"Failed to get leaderboard data for batch {batch_id}: {e}")
                        batch_leaderboard_data[batch_id] = None
                        
                # Generate Leaderboard PDF for this team
                leaderboard_pdf_bytes = None
                lb_data = batch_leaderboard_data.get(batch_id) if batch_id else None
                if lb_data:
                    from src.api.backend.utils.leaderboard_pdf_generator import generate_leaderboard_pdf
                    pdf_data = {
                        "entries": [
                            {
                                "rank": entry.rank,
                                "team_id": entry.team_id,
                                "team_name": entry.team_name,
                                "overall_score": entry.overall_score,
                                "project_name": entry.project_name
                            }
                            for entry in lb_data.entries
                        ],
                        "batch_name": lb_data.batch_name,
                        "generated_at": lb_data.generated_at.isoformat(),
                        "total_teams": lb_data.total_teams
                    }
                    leaderboard_pdf_bytes = generate_leaderboard_pdf(pdf_data, team_id)
                
                stats['teams_processed'] += 1
                
                # Determine if repo is empty (matching manual send)
                is_empty_repo = total_files == 0 and total_loc == 0
                
                # Email to each student (or a single test recipient)
                recipients = students_with_email
                if is_test_mode and test_email:
                    recipients = [{"name": "Test Recipient", "email": test_email}]

                for student in recipients:
                    student_name = student.get("name", "Student")
                    student_email = student["email"].strip()

                    # Deduplication guard: skip if already sent TODAY for this student+team
                    # (protects against duplicate sends across different task runs on the same day)
                    if not is_test_mode:
                        try:
                            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                            _dup = supabase.table('email_send_log')\
                                .select('id')\
                                .eq('student_email', student_email)\
                                .eq('team_id', str(team_id))\
                                .eq('status', 'sent')\
                                .eq('email_type', 'weekly_report')\
                                .gte('sent_at', today_start)\
                                .limit(1)\
                                .execute()
                            if _dup.data:
                                logger.info(f"  ⏭️  Skipping {student_email} ({team_name}): already sent today")
                                continue
                        except Exception as _dup_err:
                            logger.warning(f"Deduplication check failed for {student_email}: {_dup_err}")

                    # Use EmailTemplates (same as manual send from Teams page)
                    subject = EmailTemplates.weekly_report_subject(team_name, project_name=project_name)
                    email_body_dict = EmailTemplates.weekly_report_body(
                        team_name,
                        includes_leaderboard=(leaderboard_pdf_bytes is not None),
                        project_name=project_name,
                        is_empty_repo=is_empty_repo
                    )
                    
                    try:
                        additional_attachments = []
                        if leaderboard_pdf_bytes:
                            leaderboard_fn = f"{safe_name}_leaderboard_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
                            additional_attachments.append({
                                "bytes": leaderboard_pdf_bytes,
                                "filename": leaderboard_fn
                            })
                            
                        send_email_with_attachment(
                            subject=subject,
                            body_text=email_body_dict["text"],
                            html_body=email_body_dict["html"],
                            to_email=student_email,
                            attachment_bytes=pdf_bytes,
                            attachment_filename=filename,
                            additional_attachments=additional_attachments
                        )
                        stats['emails_attempted'] += 1
                        stats['emails_sent'] += 1
                        track_email_event('sent', team_id, team_name, student_name, student_email)
                        log_email_to_db(
                            supabase, status='sent',
                            team_id=team_id, team_name=team_name,
                            student_name=student_name, student_email=student_email,
                            batch_id=batch_id, subject=subject,
                            has_report_pdf=True,
                            has_leaderboard_pdf=(leaderboard_pdf_bytes is not None),
                        )
                        logger.info(f"  ✉️  Sent to {student_email} ({team_name})")
                    except EmailConfigError:
                        stats['emails_attempted'] += 1
                        stats['emails_failed'] += 1
                        track_email_event('failed', team_id, team_name, student_name, student_email, 'SMTP not configured')
                        log_email_to_db(
                            supabase, status='failed',
                            team_id=team_id, team_name=team_name,
                            student_name=student_name, student_email=student_email,
                            batch_id=batch_id, subject=subject,
                            has_report_pdf=True,
                            has_leaderboard_pdf=(leaderboard_pdf_bytes is not None),
                            error_message='SMTP not configured',
                        )
                        logger.warning("SMTP not configured, aborting email sends")
                        persist_checkpoint(
                            state='failed',
                            message='Weekly reports failed: SMTP is not configured.',
                            error='SMTP not configured'
                        )
                        create_notification(
                            'warning',
                            'Student Reports Failed',
                            'SMTP is not configured. Cannot send student report emails.',
                            {}
                        )
                        return {
                            "error": "SMTP not configured",
                            "emails_attempted": stats['emails_attempted'],
                            "emails_sent": stats['emails_sent'],
                            "emails_failed": stats['emails_failed'],
                            "failed_recipients_sample": stats['failed_recipients_sample'],
                            "failed_tracking_overflow": stats['failed_tracking_overflow']
                        }
                    except Exception as e:
                        stats['emails_attempted'] += 1
                        stats['emails_failed'] += 1
                        track_email_event('failed', team_id, team_name, student_name, student_email, str(e))
                        log_email_to_db(
                            supabase, status='failed',
                            team_id=team_id, team_name=team_name,
                            student_name=student_name, student_email=student_email,
                            batch_id=batch_id, subject=subject,
                            has_report_pdf=True,
                            has_leaderboard_pdf=(leaderboard_pdf_bytes is not None),
                            error_message=str(e),
                        )
                        logger.warning(f"  ❌ Failed to email {student_email}: {e}")

                    if email_limit and (stats['emails_sent'] + stats['emails_failed']) >= email_limit:
                        stop_sending = True
                        logger.info(f"Reached email limit ({email_limit}); stopping send loop")
                        break

                # ---- Inactive-member poor-performance alert ----
                # For any student in an active (committing) team who has made zero personal commits.
                # Tracks consecutive inactive weeks per student and escalates severity + penalty each week.
                #
                # Penalty schedule (applied to contribution_score):
                #   Week 1 : warning only  (0 marks deducted)
                #   Week 2 : -5 marks
                #   Week 3 : -10 marks
                #   Week 4+: -15 marks (capped)
                if (not is_test_mode and not stop_sending and not is_empty_repo
                        and total_commits_count > 0 and contributors_with_pct):
                    import re as _re
                    def _norm_name(s: str) -> str:
                        return _re.sub(r'[^a-z0-9]', '', (s or '').lower())

                    def _email_local_part(s: str) -> str:
                        if not s or "@" not in s:
                            return ""
                        return s.split("@", 1)[0]

                    def _build_aliases(value: str) -> set:
                        aliases = set()
                        if not value:
                            return aliases

                        normalized = _norm_name(value)
                        if normalized:
                            aliases.add(normalized)

                        local_part = _norm_name(_email_local_part(value))
                        if local_part:
                            aliases.add(local_part)

                        for token in _re.split(r'[^a-z0-9]+', (value or '').lower()):
                            token_norm = _norm_name(token)
                            if len(token_norm) >= 3:
                                aliases.add(token_norm)

                        return aliases

                    contributor_commit_map = {}
                    for c in contributors_with_pct:
                        commits = int(c.get("commits") or 0)
                        for alias in _build_aliases(c.get("name") or ""):
                            contributor_commit_map[alias] = max(commits, contributor_commit_map.get(alias, 0))

                    try:
                        from src.api.backend.utils.email import send_alert_email as _send_inactive_alert
                    except ImportError:
                        _send_inactive_alert = None

                    _PENALTY_SCHEDULE = {1: 0, 2: 5, 3: 10}   # week → marks deducted (week 4+ = 15)
                    _MAX_PENALTY = 15

                    team_has_confident_match = False
                    for s in students_with_email:
                        student_aliases_preview = set()
                        student_aliases_preview |= _build_aliases(s.get("github_username") or "")
                        student_aliases_preview |= _build_aliases(s.get("name") or "")
                        student_aliases_preview |= _build_aliases(s.get("email") or "")
                        if any(alias in contributor_commit_map for alias in student_aliases_preview):
                            team_has_confident_match = True
                            break

                    # Guardrail: if contributor names cannot be mapped to any team member,
                    # skip member-level inactivity penalties for this team to avoid false alerts.
                    if not team_has_confident_match:
                        logger.info(
                            f"  ⏭️  Skipping inactive-member alerts for {team_name}: "
                            "no confident student-to-contributor mapping found"
                        )
                        continue

                    for s in students_with_email:
                        student_aliases = set()
                        student_aliases |= _build_aliases(s.get("github_username") or "")
                        student_aliases |= _build_aliases(s.get("name") or "")
                        student_aliases |= _build_aliases(s.get("email") or "")

                        student_id = s.get("id")

                        matched_commits = [
                            contributor_commit_map.get(alias, 0)
                            for alias in student_aliases
                            if alias in contributor_commit_map
                        ]

                        if not matched_commits:
                            logger.info(
                                f"  ⏭️  Skipping low-commit alert for {s.get('email')} ({team_name}): "
                                "student identity did not match contributor list"
                            )
                            continue

                        found_commits = max(matched_commits)

                        if found_commits is not None and found_commits > 0:
                            # Student is active this week — reset streak if they had one
                            if student_id and (s.get("inactive_weeks") or 0) > 0:
                                try:
                                    supabase.table("students").update({
                                        "inactive_weeks": 0,
                                        "inactivity_penalty": 0,
                                    }).eq("id", student_id).execute()
                                    logger.info(f"  ✅ Reset inactivity streak for {s.get('name')} ({team_name})")
                                except Exception as _rst_e:
                                    logger.warning(f"  ❌ Could not reset inactivity streak for {s.get('name')}: {_rst_e}")
                            continue

                        # Student has 0 commits — escalate streak
                        prev_weeks = int(s.get("inactive_weeks") or 0)
                        new_weeks = prev_weeks + 1
                        week_penalty = _PENALTY_SCHEDULE.get(new_weeks, _MAX_PENALTY)
                        prev_penalty = int(s.get("inactivity_penalty") or 0)
                        new_penalty = min(prev_penalty + week_penalty, _MAX_PENALTY)

                        # Persist updated streak + penalty to DB
                        if student_id:
                            try:
                                supabase.table("students").update({
                                    "inactive_weeks": new_weeks,
                                    "inactivity_penalty": new_penalty,
                                    "last_inactivity_alert": "now()",
                                }).eq("id", student_id).execute()
                            except Exception as _upd_e:
                                logger.warning(f"  ❌ Could not update inactivity streak for {s.get('name')}: {_upd_e}")

                        if _send_inactive_alert:
                            _member_name = s.get("name", "Student")
                            _member_email = s["email"].strip()
                            try:
                                _subj = EmailTemplates.inactive_member_alert_subject(
                                    team_name, weeks_inactive=new_weeks
                                )
                                _body_d = EmailTemplates.inactive_member_alert_body(
                                    member_name=_member_name,
                                    team_name=team_name,
                                    project_name=project_name,
                                    total_commits=total_commits_count,
                                    weeks_inactive=new_weeks,
                                    mark_penalty=new_penalty,
                                )
                                _send_inactive_alert(
                                    subject=_subj,
                                    body_text=_body_d["text"],
                                    to_email=_member_email,
                                    html_body=_body_d.get("html"),
                                )
                                logger.info(
                                    f"  ⚠️  Inactive-member alert (week {new_weeks}, penalty -{new_penalty}) "
                                    f"→ {_member_email} ({team_name})"
                                )
                            except Exception as _ime:
                                logger.warning(f"  ❌ Failed inactive-member alert for {_member_email}: {_ime}")

                if stop_sending:
                    break
                        
            except Exception as e:
                logger.error(f"  ❌ Failed to process team {team_name}: {e}")
                logger.error(traceback.format_exc())
                stats['teams_skipped'] += 1

            if not is_test_mode and team_id_str:
                processed_team_ids.add(team_id_str)
                persist_checkpoint(
                    state='running',
                    message=(
                        f"Weekly reports in progress: {stats['teams_processed']} team(s) processed, "
                        f"{stats['teams_skipped']} skipped, {stats['emails_sent']} sent, {stats['emails_failed']} failed."
                    )
                )

            if stop_sending:
                break

        # --- send fake-commit summary emails to affected mentors ---
        if mentor_fake_teams:
            logger.info(f"📧 Sending fake commit weekly summary to {len(mentor_fake_teams)} mentor(s)")
            try:
                from src.api.backend.utils.email import send_alert_email, EmailConfigError
                _frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:8080')
                for _mid, _fc_team_list in mentor_fake_teams.items():
                    try:
                        _mentor_resp = supabase.table('users').select('email, full_name').eq('id', _mid).single().execute()
                        if not _mentor_resp.data:
                            continue
                        _mentor_email = _mentor_resp.data.get('email')
                        _mentor_name = _mentor_resp.data.get('full_name') or 'Mentor'
                        if not _mentor_email:
                            continue
                        _subj, _body, _html_body = EmailTemplates.fake_commits_mentor_weekly_summary(
                            mentor_name=_mentor_name,
                            fc_teams=_fc_team_list,
                            dashboard_url=f"{_frontend_url}/mentor/dashboard",
                        )
                        try:
                            send_alert_email(
                                subject=_subj,
                                body_text=_body,
                                to_email=_mentor_email,
                                html_body=_html_body,
                                use_mentor_sender=True,
                            )
                            logger.info(f"📧 Fake commit summary sent to mentor {_mentor_email} ({len(_fc_team_list)} team(s))")
                        except EmailConfigError:
                            logger.debug("SMTP not configured, skipping mentor fake commits emails")
                            break
                        except Exception as _e:
                            logger.warning(f"Failed to send fake commits summary to mentor {_mentor_email}: {_e}")
                    except Exception as _e:
                        logger.warning(f"Failed to process mentor {_mid} for fake commits email: {_e}")
            except ImportError:
                logger.debug("Email module not available for mentor fake commits notification")
            except Exception as _e:
                logger.warning(f"Error sending mentor fake commits weekly summary: {_e}")

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info("=" * 60)
        logger.info(f"✅ Weekly Student Reports Complete")
        logger.info(f"   Teams processed: {stats['teams_processed']}")
        logger.info(f"   Emails attempted: {stats['emails_attempted']}")
        logger.info(f"   Emails sent: {stats['emails_sent']}")
        logger.info(f"   Emails failed: {stats['emails_failed']}")
        logger.info(f"   Teams skipped: {stats['teams_skipped']}")
        logger.info(f"⏱️  Duration: {duration:.2f} seconds")
        logger.info(f"⏰ Completed at: {end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info("=" * 60)

        persist_checkpoint(
            state='completed',
            message=(
                f"Weekly reports completed: attempted {stats['emails_attempted']}, "
                f"sent {stats['emails_sent']}, failed {stats['emails_failed']}."
            )
        )
        
        # Create in-app notification for admins
        create_notification(
            'success',
            '✅ Weekly Student Reports Sent',
            (
                f"Attempted {stats['emails_attempted']} report emails across {stats['teams_processed']} teams. "
                f"{stats['emails_sent']} sent, {stats['emails_failed']} failed."
                if not is_test_mode else
                f"Test mode complete: attempted {stats['emails_attempted']} email(s), "
                f"{stats['emails_sent']} sent, {stats['emails_failed']} failed."
            ),
            {
                'started_at': start_time.isoformat(),
                'completed_at': end_time.isoformat(),
                'duration_seconds': duration,
                'test_mode': is_test_mode,
                'test_email': test_email,
                'max_emails': email_limit,
                'resumed_run': is_resumed_run,
                'resume_notification_id': checkpoint_notification_id,
                'mail_tracking': {
                    'attempted': stats['emails_attempted'],
                    'sent': stats['emails_sent'],
                    'failed': stats['emails_failed'],
                    'sent_recipients_sample': stats['sent_recipients_sample'],
                    'failed_recipients_sample': stats['failed_recipients_sample'],
                    'sent_tracking_overflow': stats['sent_tracking_overflow'],
                    'failed_tracking_overflow': stats['failed_tracking_overflow']
                },
                **stats
            }
        )

        return {
            **stats,
            'resumed_run': is_resumed_run,
            'resume_notification_id': checkpoint_notification_id,
        }
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.error(f"Weekly student reports task failed: {e}")
        logger.error(traceback.format_exc())
        logger.error(f"⏱️  Failed after: {duration:.2f} seconds")

        persist_checkpoint(
            state='failed',
            message=f"Weekly reports failed: {str(e)[:200]}",
            error=str(e)
        )
        
        create_notification(
            'error',
            '❌ Weekly Student Reports Failed',
            f'Error: {str(e)[:200]}',
            {
                'started_at': start_time.isoformat(),
                'failed_at': end_time.isoformat(),
                'duration_seconds': duration,
                'error': str(e)
            }
        )
        return {"error": str(e)}


@celery_app.task
@track_scheduled_task('recover-weekly-student-reports', 'Recover Weekly Student Reports')
def recover_interrupted_weekly_student_reports():
    """
    Recover interrupted weekly student report runs.

    If a weekly reports notification is still in "running" state and hasn't checkpointed
    for more than 10 minutes, queue a resume run using its notification ID.
    """
    logger.info("♻️ Checking for interrupted weekly student report runs")

    try:
        supabase = get_supabase_admin_client()
        stale_cutoff = (datetime.utcnow() - timedelta(minutes=30)).isoformat()

        recent = supabase.table('notifications')\
            .select('id, title, metadata, created_at')\
            .eq('title', '📧 Weekly Reports Started')\
            .order('created_at', desc=True)\
            .limit(20)\
            .execute()

        candidate = None
        for row in (recent.data or []):
            metadata = row.get('metadata') or {}
            if metadata.get('task') != 'weekly_student_reports':
                continue
            if metadata.get('test_mode'):
                continue
            if metadata.get('state') != 'running':
                continue
            if metadata.get('recovery_in_progress'):
                continue

            last_checkpoint_at = metadata.get('last_checkpoint_at') or metadata.get('started_at') or row.get('created_at')
            if last_checkpoint_at and last_checkpoint_at < stale_cutoff:
                candidate = row
                break

        if not candidate:
            return {'status': 'skipped', 'reason': 'no_stale_weekly_report_run'}

        # Double-check: make sure no OTHER active run is in progress
        active_check = is_weekly_reports_already_running(
            supabase_client=supabase,
            exclude_notification_id=candidate['id']  # exclude the stale one we're about to resume
        )
        if active_check['running']:
            logger.info(
                f"♻️ Skipping recovery: another active run exists "
                f"(notification={active_check['notification_id']})"
            )
            return {
                'status': 'skipped',
                'reason': 'another_active_run_exists',
                'active_notification_id': active_check['notification_id'],
            }

        metadata = candidate.get('metadata') or {}
        metadata['recovery_in_progress'] = True
        metadata['recovery_triggered_at'] = datetime.utcnow().isoformat()
        update_notification(candidate['id'], {'metadata': metadata})

        resumed_task = send_weekly_student_reports.delay(resume_notification_id=candidate['id'])

        logger.info(
            f"♻️ Resumed interrupted weekly reports run from checkpoint {candidate['id']} "
            f"(task_id={resumed_task.id})"
        )

        return {
            'status': 'resumed',
            'checkpoint_notification_id': candidate['id'],
            'resume_task_id': resumed_task.id,
        }

    except Exception as e:
        logger.error(f"Failed to recover interrupted weekly student reports: {e}")
        logger.error(traceback.format_exc())
        return {'status': 'error', 'error': str(e)}


@celery_app.task
@track_scheduled_task('monitor-task-health', 'Monitor Scheduled Task Health')
def monitor_scheduled_task_health():
    """
    Monitor health of all scheduled tasks and send alerts for degraded/critical status.
    
    Checks:
    1. If tasks are running on schedule
    2. If tasks have consecutive failures
    3. If tasks haven't run when expected
    4. Overall health status
    
    Scheduled: Every 30 minutes via Celery Beat
    
    Returns:
        dict: Health status summary
    """
    logger.info("=" * 60)
    logger.info("🏥 Monitoring Scheduled Task Health")
    logger.info("=" * 60)
    
    try:
        supabase = get_supabase_admin_client()
        
        # Get health status of all tasks
        health_result = supabase.table('scheduled_task_health').select('*').execute()
        
        if not health_result.data:
            logger.warning("No task health records found")
            return {"status": "no_data"}
        
        summary = {
            'healthy': 0,
            'degraded': 0,
            'critical': 0,
            'unknown': 0,
            'alerts_sent': 0,
            'tasks': []
        }
        
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        for task_health in health_result.data:
            task_name = task_health['task_name']
            task_display = task_health.get('task_display_name', task_name)
            health_status = task_health.get('health_status', 'unknown')
            consecutive_failures = task_health.get('consecutive_failures', 0)
            last_success = task_health.get('last_success_at')
            last_failure = task_health.get('last_failure_at')
            success_rate = task_health.get('success_rate', 0.0)
            total_executions = task_health.get('total_executions', 0)
            
            summary[health_status] = summary.get(health_status, 0) + 1
            
            task_info = {
                'name': task_display,
                'status': health_status,
                'consecutive_failures': consecutive_failures,
                'success_rate': float(success_rate or 0),
                'total_executions': total_executions
            }
            
            summary['tasks'].append(task_info)
            
            # Log health status
            if health_status == 'critical':
                logger.error(f"🚨 CRITICAL: {task_display} - {consecutive_failures} consecutive failures")
            elif health_status == 'degraded':
                logger.warning(f"⚠️  DEGRADED: {task_display} - {consecutive_failures} consecutive failures")
            else:
                logger.debug(f"✅ HEALTHY: {task_display} - Success rate: {success_rate}%")
            
            # Check for tasks that should have run but haven't
            # (This is a simplified check - could be enhanced with actual schedule parsing)
            if last_success:
                hours_since_success = (now - datetime.fromisoformat(last_success.replace('Z', '+00:00'))).total_seconds() / 3600
                
                # Alert if critical-frequency task hasn't succeeded in too long
                max_hours = {
                    'cleanup-stuck-jobs': 1,  # Should run every 15 min
                    'update-health-status': 3,  # Should run every 2 hours
                    'retry-dlq-nightly': 26,  # Should run daily
                    'weekly-batch-analysis': 168 + 2,  # Should run weekly (Mon 9am) + 2h buffer
                    'auto-resume-paused-batches': 168 + 2,  # Weekly
                    'weekly-student-reports': 168 + 2,  # Weekly
                }.get(task_name)
                
                if max_hours and hours_since_success > max_hours and health_status != 'critical':
                    logger.warning(f"⏰ LATE: {task_display} hasn't succeeded in {hours_since_success:.1f} hours (expected: every {max_hours}h)")
                    
                    # Create notification for late task
                    create_notification(
                        'warning',
                        f'⏰ Task Running Late: {task_display}',
                        f'Task hasn\'t succeeded in {hours_since_success:.1f} hours. Expected interval: {max_hours}h',
                        {'task_name': task_name, 'hours_late': hours_since_success}
                    )
                    summary['alerts_sent'] += 1
        
        # Create summary notification if there are critical or degraded tasks
        critical_count = summary.get('critical', 0)
        degraded_count = summary.get('degraded', 0)
        
        if critical_count > 0 or degraded_count > 0:
            notification_type = 'error' if critical_count > 0 else 'warning'
            emoji = '🚨' if critical_count > 0 else '⚠️'
            
            message_parts = []
            if critical_count > 0:
                message_parts.append(f"{critical_count} critical")
            if degraded_count > 0:
                message_parts.append(f"{degraded_count} degraded")
            
            create_notification(
                notification_type,
                f'{emoji} Scheduled Task Health Alert',
                f'Found {", ".join(message_parts)} scheduled task(s). Check the monitoring dashboard.',
                summary
            )
        
        logger.info("=" * 60)
        logger.info(f"📊 Health Summary:")
        logger.info(f"   ✅ Healthy: {summary['healthy']}")
        logger.info(f"   ⚠️  Degraded: {summary['degraded']}")
        logger.info(f"   🚨 Critical: {summary['critical']}")
        logger.info(f"   ❓ Unknown: {summary['unknown']}")
        logger.info(f"   📧 Alerts Sent: {summary['alerts_sent']}")
        logger.info("=" * 60)
        
        return summary
        
    except Exception as e:
        logger.error(f"Health monitoring failed: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}


@celery_app.task
@track_scheduled_task('check-batch-completion-for-consolidation', 'Check Batch Completion For Consolidation')
def check_and_consolidate_batch_alerts():
    """
    Periodic task to check for batch analysis completions and send consolidated mentor alerts.

    This task runs every 5 minutes to:
    1. Find batches where all teams have completed analysis
    2. Send consolidated fake commit alerts to mentors
    3. Track which batches have been processed for consolidation

    Scheduled: Every 5 minutes via Celery Beat

    Returns:
        dict: Summary of batches processed for consolidation
    """
    try:
        supabase = get_supabase_admin_client()

        # Find all active batch analysis runs
        runs = supabase.table('batch_analysis_runs').select(
            'id, batch_id, run_number, status, created_at'
        ).eq('status', 'in_progress').order('created_at', desc=True).execute()

        if not runs.data:
            logger.debug("No active batch analysis runs to check")
            return {'status': 'ok', 'batches_processed': 0}

        logger.info(f"Checking {len(runs.data)} active batch analysis runs for completion")

        processed_count = 0
        consolidation_triggered_count = 0

        for run in runs.data:
            batch_id = run['batch_id']
            run_id = run['id']

            try:
                # Get all teams in this batch
                batch_teams = supabase.table('teams').select(
                    'id, team_name, mentor_id'
                ).eq('batch_id', batch_id).execute()

                if not batch_teams.data:
                    logger.warning(f"Batch {batch_id} has no teams")
                    continue

                total_teams = len(batch_teams.data)

                # Get count of teams with completed analysis
                completed_jobs = supabase.table('analysis_jobs').select(
                    'id'
                ).eq('batch_id', batch_id).eq('status', 'completed').execute()

                completed_count = len(completed_jobs.data) if completed_jobs.data else 0

                logger.debug(f"Batch {batch_id}: {completed_count}/{total_teams} teams analyzed")

                # If all teams completed, trigger consolidation
                if completed_count >= total_teams and total_teams > 0:
                    logger.info(f"✅ Batch {batch_id} analysis complete! Triggering consolidation...")

                    # Check if consolidation already triggered (prevent duplicates)
                    run_metadata = supabase.table('batch_analysis_runs').select(
                        'metadata'
                    ).eq('id', run_id).single().execute()

                    metadata = run_metadata.data.get('metadata', {}) if run_metadata.data else {}

                    if not metadata.get('consolidation_triggered'):
                        # Trigger consolidation
                        collect_and_batch_mentor_alerts(batch_id)
                        consolidation_triggered_count += 1

                        # Mark consolidation as triggered
                        new_metadata = metadata.copy()
                        new_metadata['consolidation_triggered'] = True
                        new_metadata['consolidation_triggered_at'] = datetime.utcnow().isoformat()

                        supabase.table('batch_analysis_runs').update({
                            'metadata': new_metadata
                        }).eq('id', run_id).execute()

                        logger.info(f"   📧 Consolidation triggered for batch {batch_id}")
                    else:
                        logger.debug(f"   ✓ Consolidation already triggered for batch {batch_id}")

                    processed_count += 1

            except Exception as e:
                logger.warning(f"Failed to process batch {batch_id}: {e}")
                continue

        return {
            'status': 'ok',
            'batches_checked': len(runs.data),
            'batches_processed': processed_count,
            'consolidations_triggered': consolidation_triggered_count
        }

    except Exception as e:
        logger.error(f"Batch consolidation check failed: {e}")
        logger.error(traceback.format_exc())
        return {'status': 'error', 'error': str(e)}


# Helper function for creating snapshots
def create_snapshot_from_team(team_id: str, run_number: int, batch_run_id: str):
    """
    Create analysis snapshot from team data for 7-day tracking.
    This function is implemented elsewhere in the codebase.
    """
    pass  # Implementation in analysis services


@celery_app.task
@track_scheduled_task('cleanup-stuck-jobs', 'Cleanup Stuck Jobs')
def cleanup_stuck_analysis_jobs():
    """
    Automated cleanup of stuck analysis jobs.
    
    Finds jobs that are stuck in 'queued' or 'running' status and:
    1. Checks if a corresponding Celery task exists
    2. Marks job as 'failed' if task doesn't exist or is too old
    3. Updates team status accordingly
    
    This prevents jobs from sitting indefinitely when task submission fails,
    workers crash, or status updates are missed.
    
    Scheduled: Every 15 minutes via Celery Beat
    Can also be triggered manually via admin API
    
    Returns:
        dict: Cleanup statistics
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("🧹 Starting Stuck Job Cleanup")
    logger.info(f"⏰ Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info("=" * 60)
    
    stats = {
        'total_queued_checked': 0,
        'total_running_checked': 0,
        'cleaned_up': 0,
        'still_valid': 0,
        'errors': 0,
        'jobs_cleaned': []
    }
    
    try:
        from celery.result import AsyncResult
        
        supabase = get_supabase_admin_client()
        
        # Thresholds:
        # - queued jobs should move quickly (30 minutes is generous)
        # - running jobs are allowed longer because task retries/backoff can extend runtime
        import datetime as dt_module
        thirty_min_ago = (dt_module.datetime.utcnow() - dt_module.timedelta(minutes=30)).isoformat()
        three_hours_ago = (dt_module.datetime.utcnow() - dt_module.timedelta(hours=3)).isoformat()

        stuck_queued_jobs = supabase.table('analysis_jobs')\
            .select('id, team_id, status, started_at, metadata, teams(team_name, repo_url, status)')\
            .eq('status', 'queued')\
            .lt('started_at', thirty_min_ago)\
            .execute()

        stuck_running_jobs = supabase.table('analysis_jobs')\
            .select('id, team_id, status, started_at, metadata, teams(team_name, repo_url, status)')\
            .eq('status', 'running')\
            .lt('started_at', three_hours_ago)\
            .execute()

        queued_jobs = stuck_queued_jobs.data or []
        running_jobs = stuck_running_jobs.data or []

        if not queued_jobs and not running_jobs:
            logger.info("✅ No stuck jobs found")
            return stats

        stats['total_queued_checked'] = len(queued_jobs)
        stats['total_running_checked'] = len(running_jobs)
        logger.info(
            f"Found {stats['total_queued_checked']} queued jobs (>30m) and "
            f"{stats['total_running_checked']} running jobs (>3h) to verify"
        )

        for job in queued_jobs + running_jobs:
            job_id = job['id']
            team_id = job['team_id']
            job_status = job.get('status')
            metadata = job.get('metadata') or {}
            celery_task_id = job.get('celery_task_id') or metadata.get('celery_task_id')
            team_data = job.get('teams', {})
            team_name = team_data.get('team_name', 'Unknown')
            team_status = team_data.get('status', 'unknown')
            started_at = job.get('started_at')
            
            logger.info(f"\n🔍 Checking job {job_id} (Team: {team_name})")
            logger.info(f"   Job Status: {job_status}")
            logger.info(f"   Started: {started_at}")
            logger.info(f"   Celery Task ID: {celery_task_id or 'MISSING'}")
            
            should_cleanup = False
            cleanup_reason = ""
            
            # Case 1: No Celery task ID - task was never submitted
            if not celery_task_id:
                should_cleanup = True
                cleanup_reason = "No Celery task ID - submission failed"
                logger.warning(f"   ⚠️  {cleanup_reason}")
            
            # Case 2: Has Celery task ID - verify task status in Celery
            else:
                try:
                    task_result = AsyncResult(celery_task_id, app=celery_app)
                    celery_state = task_result.state  # PENDING, STARTED, SUCCESS, FAILURE, etc.
                    
                    logger.info(f"   Celery State: {celery_state}")
                    
                    # If task is PENDING (not found in broker), it was never picked up
                    if celery_state == 'PENDING':
                        should_cleanup = True
                        cleanup_reason = "Task in PENDING state - never picked up by worker"
                        logger.warning(f"   ⚠️  {cleanup_reason}")
                    
                    # If task is terminal but DB still shows active, it's stale
                    elif celery_state in ['SUCCESS', 'FAILURE', 'REVOKED']:
                        should_cleanup = True
                        cleanup_reason = f"Task {celery_state} but DB still shows '{job_status}' - sync issue"
                        logger.warning(f"   ⚠️  {cleanup_reason}")
                    
                    # If task is STARTED or RETRY, it's legitimately running
                    elif celery_state in ['STARTED', 'RETRY']:
                        stats['still_valid'] += 1
                        logger.info(f"   ✅ Task is active - not cleaning up")
                        continue
                    
                except Exception as e:
                    should_cleanup = True
                    cleanup_reason = f"Error checking Celery state: {str(e)}"
                    logger.warning(f"   ⚠️  {cleanup_reason}")
            
            # Perform cleanup
            if should_cleanup:
                try:
                    # Mark job as failed
                    supabase.table('analysis_jobs').update({
                        'status': 'failed',
                        'error_message': f"Stuck job auto-cleanup: {cleanup_reason}",
                        'completed_at': datetime.now().isoformat()
                    }).eq('id', job_id).execute()
                    
                    # Update team status if it's stuck in 'analyzing' or 'queued'
                    if team_status in ['analyzing', 'queued']:
                        # Check if there are other active jobs for this team
                        other_active_jobs = supabase.table('analysis_jobs')\
                            .select('id')\
                            .eq('team_id', team_id)\
                            .in_('status', ['running', 'queued'])\
                            .neq('id', job_id)\
                            .execute()
                        
                        # Only update team status if no other active jobs
                        if not other_active_jobs.data:
                            # Check if team has ever been analyzed successfully
                            completed_jobs = supabase.table('analysis_jobs')\
                                .select('id')\
                                .eq('team_id', team_id)\
                                .eq('status', 'completed')\
                                .limit(1)\
                                .execute()
                            
                            new_team_status = 'active' if completed_jobs.data else 'pending'
                            
                            supabase.table('teams').update({
                                'status': new_team_status
                            }).eq('id', team_id).execute()
                            
                            logger.info(f"   📝 Updated team status: {team_status} → {new_team_status}")
                    
                    stats['cleaned_up'] += 1
                    stats['jobs_cleaned'].append({
                        'job_id': job_id,
                        'team_name': team_name,
                        'reason': cleanup_reason,
                        'started_at': started_at
                    })
                    
                    logger.info(f"   🧹 Cleaned up job {job_id}")
                    
                except Exception as e:
                    stats['errors'] += 1
                    logger.error(f"   ❌ Failed to cleanup job {job_id}: {e}")
        
        logger.info("=" * 60)
        logger.info(f"✅ Stuck Job Cleanup Complete")
        logger.info(f"   Total queued jobs checked: {stats['total_queued_checked']}")
        logger.info(f"   Total running jobs checked: {stats['total_running_checked']}")
        logger.info(f"   Cleaned up: {stats['cleaned_up']}")
        logger.info(f"   Still valid: {stats['still_valid']}")
        logger.info(f"   Errors: {stats['errors']}")
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"⏱️  Duration: {duration:.2f} seconds")
        logger.info(f"⏰ Completed at: {end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info("=" * 60)
        
        # Create in-app notification if jobs were cleaned up
        if stats['cleaned_up'] > 0:
            create_notification(
                'warning',
                'Stuck Jobs Cleaned Up',
                f"Found and cleaned {stats['cleaned_up']} stuck analysis jobs. "
                f"Check logs for details.",
                stats
            )
            
            # Send email alert to admins if significant number of jobs stuck
            if stats['cleaned_up'] >= 5:
                email_parts = EmailTemplates.stuck_jobs_cleanup_body(
                    cleaned_count=stats['cleaned_up'],
                    jobs_cleaned=stats['jobs_cleaned'],
                )

                send_notification_email(
                    subject=f"⚠️ HackEval Alert: {stats['cleaned_up']} Stuck Jobs Cleaned",
                    body=email_parts["text"],
                    html_body=email_parts["html"],
                )
        
        return stats
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.error(f"Stuck job cleanup task failed: {e}")
        logger.error(traceback.format_exc())
        logger.error(f"⏱️  Failed after: {duration:.2f} seconds")
        
        create_notification(
            'error',
            '❌ Stuck Job Cleanup Failed',
            f'Error: {str(e)[:200]}',
            {
                'started_at': start_time.isoformat(),
                'failed_at': end_time.isoformat(),
                'duration_seconds': duration,
                'error': str(e)
            }
        )
        
        return {"error": str(e)}

