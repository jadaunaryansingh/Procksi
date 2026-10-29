"""
Email Templates
Centralized location for all email subjects and body templates
Edit this file to change email content across the application
"""
from typing import Dict, Any, List, Optional


class EmailTemplates:
    """Centralized email templates for all system emails"""

    # ==================== SYSTEM ALERTS (CELERY) ====================

    @staticmethod
    def scheduled_task_failure_body(
        task_name: str,
        health_status: str,
        consecutive_failures: int,
        error: str,
        traceback_excerpt: str
    ) -> Dict[str, str]:
        """Body template for scheduled task failure alerts."""
        text_body = f"""CRITICAL: Scheduled Task Failure Alert

Task: {task_name}
Status: {health_status.upper()}
Consecutive Failures: {consecutive_failures}

Error:
{error}

This task has failed {consecutive_failures} times consecutively. Immediate attention required.

Traceback:
{traceback_excerpt}

---
Automated alert from GitHub Agent Monitoring System
"""

        html_content = f"""
        <p>A scheduled task has entered a critical failure state.</p>

        <div style="background:#fef2f2;border-left:4px solid #ef4444;padding:15px;margin:18px 0;border-radius:0 4px 4px 0;">
            <p style="margin:0;color:#991b1b;"><strong>Immediate attention required</strong></p>
            <p style="margin:8px 0 0;color:#991b1b;">This task has failed <strong>{consecutive_failures}</strong> times consecutively.</p>
        </div>

        <table style="width:100%;border-collapse:collapse;margin:14px 0;">
            <tr><td style="padding:8px;border:1px solid #e2e8f0;background:#f8fafc;font-weight:600;">Task</td><td style="padding:8px;border:1px solid #e2e8f0;">{task_name}</td></tr>
            <tr><td style="padding:8px;border:1px solid #e2e8f0;background:#f8fafc;font-weight:600;">Status</td><td style="padding:8px;border:1px solid #e2e8f0;">{health_status.upper()}</td></tr>
            <tr><td style="padding:8px;border:1px solid #e2e8f0;background:#f8fafc;font-weight:600;">Consecutive Failures</td><td style="padding:8px;border:1px solid #e2e8f0;">{consecutive_failures}</td></tr>
        </table>

        <h3 style="margin:16px 0 8px;">Error</h3>
        <pre style="background:#0f172a;color:#e2e8f0;padding:12px;border-radius:6px;overflow:auto;white-space:pre-wrap;">{error}</pre>

        <h3 style="margin:16px 0 8px;">Traceback (excerpt)</h3>
        <pre style="background:#0f172a;color:#e2e8f0;padding:12px;border-radius:6px;overflow:auto;white-space:pre-wrap;">{traceback_excerpt}</pre>
        """

        html_wrapper = EmailTemplates.get_html_wrapper("Scheduled Task Failure Alert", html_content)
        return {"text": text_body, "html": html_wrapper}

    @staticmethod
    def stuck_jobs_cleanup_body(cleaned_count: int, jobs_cleaned: List[Dict[str, Any]]) -> Dict[str, str]:
        """Body template for stuck jobs cleanup alerts."""
        jobs_preview = jobs_cleaned[:10]
        jobs_text = "\n".join([f"  - {j.get('team_name', 'Unknown Team')}: {j.get('reason', 'Unknown reason')}" for j in jobs_preview])
        if len(jobs_cleaned) > 10:
            jobs_text += f"\n  ... and {len(jobs_cleaned) - 10} more"

        text_body = f"""ALERT: Stuck Analysis Jobs Cleanup

The automated cleanup task found {cleaned_count} jobs stuck in 'queued' status.

This indicates a problem with Celery task submission. Common causes:
1. Redis connection issues
2. Celery workers were offline when jobs were created
3. Network partition between API and Redis
4. Exception during task.delay() call

Cleaned Jobs:
{jobs_text}

Please investigate the root cause.
"""

        rows_html = "".join([
            f"<tr><td style='padding:8px;border:1px solid #e2e8f0;'>{j.get('team_name', 'Unknown Team')}</td>"
            f"<td style='padding:8px;border:1px solid #e2e8f0;'>{j.get('reason', 'Unknown reason')}</td></tr>"
            for j in jobs_preview
        ])
        extra_html = f"<p style='color:#64748b;'>... and {len(jobs_cleaned) - 10} more jobs</p>" if len(jobs_cleaned) > 10 else ""

        html_content = f"""
        <p>The automated cleanup task found <strong>{cleaned_count}</strong> jobs stuck in <code>queued</code> status.</p>

        <div style="background:#fffbeb;border-left:4px solid #f59e0b;padding:15px;margin:18px 0;border-radius:0 4px 4px 0;">
            <p style="margin:0;color:#92400e;"><strong>Potential Celery submission issue detected.</strong></p>
            <p style="margin:8px 0 0;color:#92400e;">Please investigate this incident.</p>
        </div>

        <h3 style="margin:16px 0 8px;">Common Causes</h3>
        <ol>
            <li>Redis connection issues</li>
            <li>Celery workers were offline when jobs were created</li>
            <li>Network partition between API and Redis</li>
            <li>Exception during <code>task.delay()</code> call</li>
        </ol>

        <h3 style="margin:16px 0 8px;">Cleaned Jobs (first 10)</h3>
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr>
                    <th style="padding:8px;border:1px solid #e2e8f0;background:#f8fafc;text-align:left;">Team</th>
                    <th style="padding:8px;border:1px solid #e2e8f0;background:#f8fafc;text-align:left;">Reason</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
        {extra_html}

        <p><strong>Please investigate the root cause.</strong></p>
        """

        html_wrapper = EmailTemplates.get_html_wrapper("Stuck Jobs Cleanup Alert", html_content)
        return {"text": text_body, "html": html_wrapper}
    
    # ==================== DUPLICATE COMMIT ALERTS ====================
    
    @staticmethod
    def duplicate_commit_alert_subject(team_name: str) -> str:
        """Subject line for duplicate commit alerts"""
        return "Duplicate Commits Detected on Semester GitHub Project Repository"
    
    @staticmethod
    def duplicate_commit_alert_body(
        team_name: str,
        repo_url: str,
        incidents: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Body template for duplicate commit alerts. Returns dict with 'text' and 'html' keys."""
        text_body = f"""Dear {team_name},

It has been observed that some duplicate commits have been identified in your GitHub repositories. Please note that duplicate or repetitive commits are being actively tracked and monitored.

Students are strictly advised not to make duplicate commits merely to increase activity. Such practices will be considered invalid and may negatively impact your evaluation and individual contribution score.

Ensure that all commits are meaningful, relevant, and reflect genuine progress on the semester project.

Best regards,
Preshit Desai
Technical Trainer - AIML
"""
        html_content = f"""
        <p>Dear <strong>{team_name}</strong>,</p>

        <p>It has been observed that some <strong>duplicate commits</strong> have been identified in your GitHub repositories.
        Please note that duplicate or repetitive commits are being actively tracked and monitored.</p>

        <div style="background-color:#fffbeb;border-left:4px solid #f59e0b;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
            <h3 style="margin-top:0;color:#92400e;">\u26A0\uFE0F Warning</h3>
            <p style="margin-bottom:0;color:#92400e;">Students are strictly advised not to make duplicate commits merely to increase activity.
            Such practices will be considered invalid and may negatively impact your evaluation and individual contribution score.</p>
        </div>

        <p>Ensure that all commits are <strong>meaningful, relevant, and reflect genuine progress</strong> on the semester project.</p>

        <br>
        <p>Best regards,<br>
        <strong>Preshit Desai</strong><br>
        <span style="color:#64748b;">Technical Trainer - AIML</span></p>
        """
        html_wrapper = EmailTemplates.get_html_wrapper("Duplicate Commits Detected", html_content)
        return {"text": text_body, "html": html_wrapper}
    
    # ==================== COMMIT QUALITY ALERTS ====================
    
    @staticmethod
    def quality_alert_subject(team_name: str) -> str:
        """Subject line for commit quality alerts"""
        return "Action Required: Low Quality Commits Detected"
    
    @staticmethod
    def quality_alert_body(
        team_name: str,
        fake_commit_count: int,
        fake_commit_ratio: float,
        commit_health: str,
        total_commits: int,
        threshold: float,
        fake_commits: List[Dict[str, Any]],
        suspicious_authors: Dict[str, Any] = None
    ) -> Dict[str, str]:
        """Body template for commit quality alerts. Returns dict with 'text' and 'html' keys."""
        body = f"Dear {team_name},\n\n"
        
        if fake_commit_count > 0:
            body += f"""It has been observed during regular monitoring that your GitHub repository contains a high number of low-quality or "fake" commits ({fake_commit_count} out of {total_commits} commits, {fake_commit_ratio:.1f}%). 

Please note that attempting to artificially inflate your commit count by committing auto-generated files, spamming empty changes, or repeatedly committing dependency folders is strictly prohibited. Such practices will be considered invalid and will negatively impact your evaluation and individual contribution score.
"""
        else:
            body += f"""It has been observed during regular monitoring that your GitHub repository requires attention regarding commit quality, version control practices, or contributor activity.

Please note that all team members must follow standard version control practices. This includes making meaningful commits that reflect genuine progress, and properly configuring your Git environment.
"""

        # Add suspicious author warning if detected
        if suspicious_authors and suspicious_authors.get("has_suspicious"):
            body += "\n⚠️ SUSPICIOUS AUTHOR NAMES DETECTED:\n"
            body += "The following commit authors are using generic or default names that do not identify a real team member. This has been flagged for review.\n\n"
            for sa in suspicious_authors.get("suspicious_authors", []):
                body += f"  - \"{sa.get('name', 'Unknown')}\" — {sa.get('commits', 0)} commits ({sa.get('share', 0)}%) — {sa.get('reason', 'Suspicious name')}\n"
            body += "\nAll team members must configure Git with their real name and university email. Using default or generic names is not acceptable.\n"

        body += """
You are required to adhere to standard version control practices immediately:
1. Ensure all commits are meaningful, relevant, and reflect genuine progress.
2. Use proper `.gitignore` files to exclude dependencies (e.g., node_modules, vendor) and generated files (.pyc, .min.js).
3. Provide clear and descriptive commit messages for all your changes.

Ensure your team maintains the required quality standards moving forward.

Best regards,
Preshit Desai
Technical Trainer - AIML
"""

        # --- HTML version ---
        if fake_commit_count > 0:
            issue_html = f"""
            <p>It has been observed during regular monitoring that your GitHub repository contains a high number of
            low-quality or &ldquo;fake&rdquo; commits (<strong>{fake_commit_count}</strong> out of <strong>{total_commits}</strong> commits, <strong>{fake_commit_ratio:.1f}%</strong>).</p>
            <div style="background-color:#fef2f2;border-left:4px solid #ef4444;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
                <p style="margin:0;color:#991b1b;">Attempting to artificially inflate your commit count by committing auto-generated files,
                spamming empty changes, or repeatedly committing dependency folders is <strong>strictly prohibited</strong>.
                Such practices will be considered invalid and will negatively impact your evaluation.</p>
            </div>"""
        else:
            issue_html = """
            <p>It has been observed during regular monitoring that your GitHub repository requires attention
            regarding commit quality, version control practices, or contributor activity.</p>
            <p>All team members must follow standard version control practices, making meaningful commits
            that reflect genuine progress.</p>"""

        suspicious_html = ""
        if suspicious_authors and suspicious_authors.get("has_suspicious"):
            rows = ""
            for sa in suspicious_authors.get("suspicious_authors", []):
                rows += f'<tr><td style="padding:6px 10px;border:1px solid #e2e8f0;">{sa.get("name", "Unknown")}</td>'
                rows += f'<td style="padding:6px 10px;border:1px solid #e2e8f0;text-align:center;">{sa.get("commits", 0)}</td>'
                rows += f'<td style="padding:6px 10px;border:1px solid #e2e8f0;">{sa.get("reason", "Suspicious name")}</td></tr>'
            suspicious_html = f"""
            <div style="background-color:#fffbeb;border-left:4px solid #f59e0b;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
                <h3 style="margin-top:0;color:#92400e;">⚠️ Suspicious Author Names Detected</h3>
                <p style="color:#92400e;">The following commit authors are using generic or default names:</p>
                <table style="width:100%;border-collapse:collapse;font-size:13px;">
                <thead><tr style="background:#92400e;color:#fff;"><th style="padding:6px 10px;text-align:left;">Author</th><th style="padding:6px 10px;text-align:center;">Commits</th><th style="padding:6px 10px;text-align:left;">Reason</th></tr></thead>
                <tbody>{rows}</tbody></table>
                <p style="margin-bottom:0;color:#92400e;">All team members must configure Git with their real name and university email.</p>
            </div>"""

        html_content = f"""
        <p>Dear <strong>{team_name}</strong>,</p>
        {issue_html}
        {suspicious_html}
        <h3 style="color:#1e293b;">Required Actions</h3>
        <ol>
            <li>Ensure all commits are meaningful, relevant, and reflect genuine progress.</li>
            <li>Use proper <code>.gitignore</code> files to exclude dependencies and generated files.</li>
            <li>Provide clear and descriptive commit messages for all your changes.</li>
        </ol>
        <p>Ensure your team maintains the required quality standards moving forward.</p>
        <br>
        <p>Best regards,<br>
        <strong>Preshit Desai</strong><br>
        <span style="color:#64748b;">Technical Trainer - AIML</span></p>
        """
        html_wrapper = EmailTemplates.get_html_wrapper("Low Quality Commits Detected", html_content)
        return {"text": body, "html": html_wrapper}
    
    # ==================== CRITICAL FAKE COMMIT ALERTS (Admin/Mentor) ====================
    
    @staticmethod
    def fake_commits_critical_subject(team_number: str, project_name: str) -> str:
        """Subject line for critical fake commit alerts to admins/mentors"""
        return f"\U0001F6A8 URGENT: Fake Commits Detected - Team {team_number} ({project_name})"
    
    @staticmethod
    def fake_commits_critical_body(
        team_number: str,
        team_name: str,
        project_name: str,
        repo_url: str,
        mentor_name: str,
        fake_commit_count: int,
        fake_commit_ratio: float,
        total_commits: int,
        commit_health: str,
        fake_commits_list: str,
        dashboard_url: str,
        fake_commits_html: str = "",
    ) -> Dict[str, str]:
        """Body template for critical fake commit alerts to admins/mentors.
        Returns dict with 'text' and 'html' keys."""

        # ---- plain-text version (kept for non-HTML clients) ----
        text_body = f"""Dear Admin/Mentor,

This is to inform you that CRITICAL commit quality issues have been detected during automated analysis of semester project repositories.

TEAM DETAILS:
- Team Number: {team_number}
- Team Name: {team_name}
- Project Name: {project_name}
- Repository: {repo_url}
- Assigned Mentor: {mentor_name}

CRITICAL ISSUES DETECTED:
- Fake Commits: {fake_commit_count} out of {total_commits} total commits
- Fake Commit Ratio: {fake_commit_ratio:.1f}%
- Commit Health Status: {commit_health}

TOP PROBLEMATIC COMMITS:
{fake_commits_list}

THESE COMMITS SHOW SEVERE ISSUES:
- Empty commits with no actual changes
- Repeated/duplicate commits within seconds
- Suspicious automated patterns
- Commit timestamp manipulation

This behavior is strictly prohibited and indicates attempts to artificially inflate commit counts without genuine contributions. Such practices will result in zero marks for individual contribution and may lead to project failure.

ACTION REQUIRED:
Please immediately review this team's repository and take appropriate disciplinary action. Contact the team and ensure they understand proper version control practices.

View Full Analysis:
{dashboard_url}

Best regards,
Preshit Desai
Technical Trainer - AIML

---
This is an automated alert from the HackEval Analysis System.
"""

        # ---- HTML version ----
        html_content = f"""
        <p>Dear <strong>Admin / Mentor</strong>,</p>

        <p>This is to inform you that <strong style="color:#dc2626;">CRITICAL</strong> commit quality issues
        have been detected during automated analysis of semester project repositories.</p>

        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <tr style="background:#f8fafc;">
                <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Team Number</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">{team_number}</td>
            </tr>
            <tr>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Team Name</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">{team_name}</td>
            </tr>
            <tr style="background:#f8fafc;">
                <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Project Name</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">{project_name}</td>
            </tr>
            <tr>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Repository</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">
                    <a href="{repo_url}" style="color:#3b82f6;">{repo_url}</a>
                </td>
            </tr>
            <tr style="background:#f8fafc;">
                <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Assigned Mentor</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">{mentor_name}</td>
            </tr>
        </table>

        <div style="background-color:#fef2f2;border-left:4px solid #ef4444;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
            <h3 style="margin-top:0;color:#991b1b;">\U0001F6A8 Critical Issues Detected</h3>
            <ul style="margin-bottom:0;color:#991b1b;">
                <li><strong>Fake Commits:</strong> {fake_commit_count} out of {total_commits} total commits</li>
                <li><strong>Fake Commit Ratio:</strong> {fake_commit_ratio:.1f}%</li>
                <li><strong>Commit Health Status:</strong> {commit_health}</li>
            </ul>
        </div>

        <h3 style="color:#1e293b;">Top Problematic Commits</h3>
        {fake_commits_html if fake_commits_html else f'<pre style="background:#f8fafc;padding:12px;border-radius:4px;font-size:13px;overflow-x:auto;">{fake_commits_list}</pre>'}

        <div style="background-color:#fffbeb;border-left:4px solid #f59e0b;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
            <h3 style="margin-top:0;color:#92400e;">\u26A0\uFE0F These Commits Show Severe Issues</h3>
            <ul style="margin-bottom:0;color:#92400e;">
                <li>Empty commits with no actual changes</li>
                <li>Repeated/duplicate commits within seconds</li>
                <li>Suspicious automated patterns</li>
                <li>Commit timestamp manipulation</li>
            </ul>
        </div>

        <p>This behavior is <strong>strictly prohibited</strong> and indicates attempts to artificially inflate
        commit counts without genuine contributions. Such practices will result in
        <strong>zero marks</strong> for individual contribution and may lead to project failure.</p>

        <div style="background-color:#f0fdf4;border-left:4px solid #22c55e;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
            <h3 style="margin-top:0;color:#166534;">\u2757 Action Required</h3>
            <p style="margin-bottom:0;color:#166534;">
                Please immediately review this team's repository and take appropriate disciplinary action.
                Contact the team and ensure they understand proper version control practices.
            </p>
        </div>

        <p style="text-align:center;">
            <a href="{dashboard_url}" class="button" style="display:inline-block;padding:12px 24px;background-color:#dc2626;color:#ffffff;text-decoration:none;border-radius:6px;font-weight:bold;">
                View Full Analysis
            </a>
        </p>

        <br>
        <p>Best regards,<br>
        <strong>Preshit Desai</strong><br>
        <span style="color:#64748b;">Technical Trainer - AIML</span></p>
        """

        html_wrapper = EmailTemplates.get_html_wrapper(
            f"\U0001F6A8 Fake Commits \u2013 Team {team_number}", html_content
        )

        return {
            "text": text_body,
            "html": html_wrapper,
        }

    @staticmethod
    def ai_bot_majority_critical_subject(team_number: str, project_name: str) -> str:
        """Subject line for critical automation-commit alerts to admins/mentors."""
        return f"\U0001F916 URGENT: Automation Commits >50% - Team {team_number} ({project_name})"

    @staticmethod
    def ai_bot_majority_critical_body(
        team_number: str,
        team_name: str,
        project_name: str,
        repo_url: str,
        mentor_name: str,
        total_commits: int,
        ai_bot_commits: int,
        ai_bot_share: float,
        ai_bot_details_html: str,
        dashboard_url: str,
    ) -> Dict[str, str]:
        """HTML-first body for alerts when automation-authored commits exceed 50%."""
        text_body = (
            f"CRITICAL: Automation commits exceed 50% for Team {team_number} ({project_name}). "
            f"Please check the HTML version of this email for full details."
        )

        html_content = f"""
        <p>Dear <strong>Admin / Mentor</strong>,</p>

        <p>A <strong style="color:#dc2626;">CRITICAL</strong> policy violation was detected:
        automation-authored commits exceed 50% for this team repository.</p>

        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <tr style="background:#f8fafc;">
                <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Team Number</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">{team_number}</td>
            </tr>
            <tr>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Team Name</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">{team_name}</td>
            </tr>
            <tr style="background:#f8fafc;">
                <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Project Name</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">{project_name}</td>
            </tr>
            <tr>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Repository</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">
                    <a href="{repo_url}" style="color:#3b82f6;">{repo_url}</a>
                </td>
            </tr>
            <tr style="background:#f8fafc;">
                <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Assigned Mentor</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">{mentor_name}</td>
            </tr>
        </table>

        <div style="background-color:#fef2f2;border-left:4px solid #ef4444;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
            <h3 style="margin-top:0;color:#991b1b;">\U0001F6A8 Automation Commits Not Accepted</h3>
            <ul style="margin-bottom:0;color:#991b1b;">
                <li><strong>Total Commits:</strong> {total_commits}</li>
                <li><strong>Automation-authored Commits:</strong> {ai_bot_commits}</li>
                <li><strong>Automation Share:</strong> {ai_bot_share:.1f}%</li>
            </ul>
        </div>

        <h3 style="color:#1e293b;">Detected Automation Contributors</h3>
        {ai_bot_details_html}

        <div style="background-color:#fffbeb;border-left:4px solid #f59e0b;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
            <p style="margin:0;color:#92400e;">
                <strong>Policy:</strong> Automation-authored commits (for example github-actions) are not accepted for grading.
                AI assistance is allowed only when a student remains the primary commit author.
            </p>
        </div>

        <div style="background-color:#f0fdf4;border-left:4px solid #22c55e;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
            <h3 style="margin-top:0;color:#166534;">\u2757 Action Required</h3>
            <p style="margin-bottom:0;color:#166534;">
                Please contact the mentor and team immediately, stop automation-authored commits, and request re-analysis.
            </p>
        </div>

        <p style="text-align:center;">
            <a href="{dashboard_url}" class="button" style="display:inline-block;padding:12px 24px;background-color:#dc2626;color:#ffffff;text-decoration:none;border-radius:6px;font-weight:bold;">
                View Full Analysis
            </a>
        </p>
        """

        html_wrapper = EmailTemplates.get_html_wrapper(
            f"\U0001F916 Automation Commits \u2013 Team {team_number}", html_content
        )

        return {
            "text": text_body,
            "html": html_wrapper,
        }
    
    # ==================== BATCH ANALYSIS COMPLETION ====================
    
    @staticmethod
    def fake_commits_mentor_weekly_summary(
        mentor_name: str,
        fc_teams: List[Dict[str, Any]],
        dashboard_url: str,
    ) -> tuple:
        """Weekly fake commits summary email for a mentor.
        Returns (subject, text_body, html_body) tuple.
        fc_teams: list of dicts with keys: team_name, project_name, repo_url,
                  fake_commit_count, fake_commit_ratio, commit_health, total_commits, team_id.
        """
        import html as _html

        subject = f"\U0001F6A8 Weekly Alert: Fake Commits Detected in Your Teams ({len(fc_teams)} team{'s' if len(fc_teams) != 1 else ''})"

        # ---- plain text ----
        teams_text = ""
        for i, t in enumerate(fc_teams, 1):
            teams_text += (
                f"\n{i}. {t['team_name']} ({t.get('project_name', 'N/A')})\n"
                f"   Repository : {t.get('repo_url', 'N/A')}\n"
                f"   Fake Commits: {t['fake_commit_count']} / {t.get('total_commits', '?')} "
                f"({t['fake_commit_ratio']:.1f}%)\n"
                f"   Health Status: {t['commit_health']}\n"
            )

        text_body = f"""Dear {mentor_name},

This is your weekly automated alert from the HackEval Analysis System.

Critical commit quality issues have been detected in {len(fc_teams)} of your assigned team(s).
These teams have earned a CRITICAL commit health rating due to fake or suspicious commits.

AFFECTED TEAMS:
{teams_text}

WHY THIS MATTERS:
- Empty commits with no actual changes
- Repeated/duplicate commits within seconds
- Suspicious automated patterns
- Commit timestamp manipulation

This behaviour is strictly prohibited and may result in zero marks for individual contribution.

ACTION REQUIRED:
Please review the repositories listed above and follow up with the concerned teams immediately.

View your mentor dashboard: {dashboard_url}

Best regards,
Preshit Desai
Technical Trainer - AIML

---
This is an automated alert from the HackEval Analysis System.
"""

        # ---- HTML rows ----
        rows_html = ""
        for i, t in enumerate(fc_teams):
            bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
            health_color = "#dc2626"
            team_dashboard_link = f"{dashboard_url.split('/admin/mentor-portal')[0]}/admin/teams/{t.get('team_id', '')}" if 'team_id' in t else "#"
            rows_html += (
                f'<tr style="background:{bg};">'
                f'<td style="padding:8px 12px;border:1px solid #e2e8f0;">'
                f'<strong>{_html.escape(t["team_name"])}</strong><br/>'
                f'<a href="{_html.escape(team_dashboard_link)}" style="color:#3b82f6;font-size:12px;text-decoration:none;">View Details →</a>'
                f'</td>'
                f'<td style="padding:8px 12px;border:1px solid #e2e8f0;">{_html.escape(t.get("project_name", "N/A"))}</td>'
                f'<td style="padding:8px 12px;border:1px solid #e2e8f0;">'
                f'<a href="{_html.escape(t.get("repo_url", "#"))}" style="color:#3b82f6;font-size:12px;">'
                f'{_html.escape(t.get("repo_url", "N/A")[:40])}</a></td>'
                f'<td style="padding:8px 12px;border:1px solid #e2e8f0;text-align:center;">'
                f'{t["fake_commit_count"]} / {t.get("total_commits", "?")} ({t["fake_commit_ratio"]:.1f}%)</td>'
                f'<td style="padding:8px 12px;border:1px solid #e2e8f0;text-align:center;'
                f'font-weight:600;color:{health_color};">{_html.escape(t["commit_health"])}</td>'
                f'</tr>'
            )

        html_content = f"""
        <p>Dear <strong>{_html.escape(mentor_name)}</strong>,</p>

        <p>This is your <strong>weekly automated alert</strong> from the HackEval Analysis System.</p>

        <div style="background-color:#fef2f2;border-left:4px solid #ef4444;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
            <h3 style="margin-top:0;color:#991b1b;">\U0001F6A8 Critical Fake Commits Detected</h3>
            <p style="color:#991b1b;margin-bottom:0;">
                <strong>{len(fc_teams)} of your assigned team(s)</strong> have earned a
                <strong>CRITICAL</strong> commit health rating due to fake or suspicious commits.
            </p>
        </div>

        <h3 style="color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:6px;">Affected Teams</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;margin:12px 0;">
            <thead>
                <tr style="background:#0f172a;color:#ffffff;">
                    <th style="padding:8px 12px;border:1px solid #334155;text-align:left;">Team Name</th>
                    <th style="padding:8px 12px;border:1px solid #334155;text-align:left;">Project</th>
                    <th style="padding:8px 12px;border:1px solid #334155;text-align:left;">Repository</th>
                    <th style="padding:8px 12px;border:1px solid #334155;text-align:center;">Fake Commits</th>
                    <th style="padding:8px 12px;border:1px solid #334155;text-align:center;">Health</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        <div style="background-color:#fffbeb;border-left:4px solid #f59e0b;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
            <h3 style="margin-top:0;color:#92400e;">\u26A0\uFE0F Why This Matters</h3>
            <ul style="margin-bottom:0;color:#92400e;">
                <li>Empty commits with no actual changes</li>
                <li>Repeated/duplicate commits within seconds</li>
                <li>Suspicious automated patterns</li>
                <li>Commit timestamp manipulation</li>
            </ul>
        </div>

        <div style="background-color:#f0fdf4;border-left:4px solid #22c55e;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
            <h3 style="margin-top:0;color:#166534;">\u2757 Action Required</h3>
            <p style="margin-bottom:0;color:#166534;">
                Please review the repositories listed above and follow up with the concerned teams immediately.
                Such practices will result in <strong>zero marks</strong> for individual contribution.
            </p>
        </div>

        <p style="text-align:center;">
            <a href="{_html.escape(dashboard_url)}" style="display:inline-block;padding:12px 24px;background-color:#dc2626;color:#ffffff;text-decoration:none;border-radius:6px;font-weight:bold;">
                View Mentor Dashboard
            </a>
        </p>

        <br>
        <p>Best regards,<br>
        <strong>Preshit Desai</strong><br>
        <span style="color:#64748b;">Technical Trainer - AIML</span></p>
        """

        html_wrapper = EmailTemplates.get_html_wrapper(
            f"\U0001F6A8 Fake Commits Alert \u2013 {len(fc_teams)} Team{'s' if len(fc_teams) != 1 else ''}",
            html_content
        )

        return subject, text_body, html_wrapper

    @staticmethod
    def batch_analysis_complete_subject(batch_name: str) -> str:
        """Subject line for batch analysis completion"""
        return f"Update: Batch Analysis Completed - {batch_name}"
    
    @staticmethod
    def batch_analysis_complete_body(
        batch_name: str,
        total_teams: int,
        completed: int,
        failed: int
    ) -> Dict[str, str]:
        """Body template for batch analysis completion notification. Returns dict with 'text' and 'html' keys."""
        text_body = f"""Dear Admin/Mentor,

This is to inform you that the automated analysis for batch "{batch_name}" has successfully concluded.

PROCESSING SUMMARY:
- Total Teams in Batch: {total_teams}
- Successfully Analyzed: {completed}
- Failed to Analyze: {failed}

Please log in to the admin dashboard to review the detailed performance metrics, identify inactive teams, and take any necessary actions.

Best regards,
Preshit Desai
Technical Trainer - AIML
"""
        html_content = f"""
        <p>Dear <strong>Admin / Mentor</strong>,</p>
        <p>The automated analysis for batch <strong>{batch_name}</strong> has successfully concluded.</p>

        <h3 style="color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:6px;">Processing Summary</h3>
        <div style="background:#f8fafc;border-radius:6px;padding:16px;margin:12px 0;">
            <table style="width:100%;font-size:14px;">
                <tr><td style="padding:4px 0;color:#64748b;">Total Teams in Batch</td><td style="padding:4px 0;font-weight:600;">{total_teams}</td></tr>
                <tr><td style="padding:4px 0;color:#64748b;">Successfully Analyzed</td><td style="padding:4px 0;font-weight:600;color:#16a34a;">{completed}</td></tr>
                <tr><td style="padding:4px 0;color:#64748b;">Failed to Analyze</td><td style="padding:4px 0;font-weight:600;color:#dc2626;">{failed}</td></tr>
            </table>
        </div>

        <p>Please log in to the admin dashboard to review the detailed performance metrics, identify inactive teams, and take any necessary actions.</p>

        <br>
        <p>Best regards,<br>
        <strong>Preshit Desai</strong><br>
        <span style="color:#64748b;">Technical Trainer - AIML</span></p>
        """
        html_wrapper = EmailTemplates.get_html_wrapper(f"Batch Analysis Complete \u2014 {batch_name}", html_content)
        return {"text": text_body, "html": html_wrapper}

    # ==================== WEEKLY ANALYSIS COMPLETE (Admin & Mentor) ====================

    @staticmethod
    def weekly_analysis_complete_mentor(
        user_name: str,
        analyzed_teams: List[Dict[str, Any]],
        results: Dict[str, Any],
        dashboard_url: str,
    ) -> Dict[str, str]:
        """Weekly analysis complete email for mentors. Returns dict with 'text' and 'html' keys."""

        # --- plain text ---
        text_body = f"Hello {user_name},\n\nThe weekly GitHub repository analysis has completed. Here's your summary:\n\n"
        text_body += "YOUR TEAMS ANALYZED:\n-------------------\n"
        if analyzed_teams:
            text_body += f"{len(analyzed_teams)} of your teams were analyzed:\n\n"
            for team in analyzed_teams[:10]:
                batch_info = team.get('batches', {}) or {}
                batch_name = f"{batch_info.get('semester', '')} {batch_info.get('year', '')}".strip()
                score = team.get('total_score', 0) or 0
                entry = f"  • {team['team_name']}"
                if batch_name:
                    entry += f" ({batch_name})"
                entry += f" - Score: {score}/100\n"
                text_body += entry
            if len(analyzed_teams) > 10:
                text_body += f"\n  ... and {len(analyzed_teams) - 10} more teams\n"
        else:
            text_body += "(None of your teams were analyzed in this cycle)\n"

        text_body += f"\nOVERALL SUMMARY:\n---------------\n"
        text_body += f"Total Batches Processed: {results.get('total_batches', 0)}\n"
        text_body += f"Batches Triggered: {results.get('triggered', 0)}\n"
        text_body += f"Batches Skipped: {results.get('skipped', 0)}\n\n"
        for detail in results.get('batch_details', []):
            text_body += f"✓ {detail['batch']}: {detail['teams_queued']} teams\n"
        text_body += f"\nView your teams: {dashboard_url}\n\nBest regards,\nGitHub Agent Analysis System\n"

        # --- html ---
        team_rows = ""
        if analyzed_teams:
            for i, team in enumerate(analyzed_teams[:10]):
                batch_info = team.get('batches', {}) or {}
                batch_name = f"{batch_info.get('semester', '')} {batch_info.get('year', '')}".strip()
                score = team.get('total_score', 0) or 0
                bg = '#f8fafc' if i % 2 == 0 else '#ffffff'
                score_color = '#16a34a' if score >= 70 else '#ea580c' if score >= 40 else '#dc2626'
                team_rows += (
                    f'<tr style="background:{bg};">'
                    f'<td style="padding:8px 12px;border:1px solid #e2e8f0;">{team["team_name"]}</td>'
                    f'<td style="padding:8px 12px;border:1px solid #e2e8f0;">{batch_name or "—"}</td>'
                    f'<td style="padding:8px 12px;border:1px solid #e2e8f0;text-align:center;font-weight:600;color:{score_color};">{score:.1f}</td>'
                    f'</tr>'
                )
            if len(analyzed_teams) > 10:
                team_rows += f'<tr><td colspan="3" style="padding:8px;text-align:center;color:#64748b;">... and {len(analyzed_teams) - 10} more teams</td></tr>'
            teams_html = (
                f'<p><strong>{len(analyzed_teams)}</strong> of your teams were analyzed:</p>'
                '<table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;">'
                '<thead><tr style="background:#0f172a;color:#ffffff;">'
                '<th style="padding:10px 12px;border:1px solid #334155;text-align:left;">Team</th>'
                '<th style="padding:10px 12px;border:1px solid #334155;text-align:left;">Batch</th>'
                '<th style="padding:10px 12px;border:1px solid #334155;text-align:center;">Score</th>'
                '</tr></thead><tbody>'
                f'{team_rows}'
                '</tbody></table>'
            )
        else:
            teams_html = '<p style="color:#64748b;font-style:italic;">None of your teams were analyzed in this cycle.</p>'

        batch_details_html = ""
        for detail in results.get('batch_details', []):
            batch_details_html += f'<li>✓ {detail["batch"]}: <strong>{detail["teams_queued"]}</strong> teams</li>'

        html_content = f"""
        <p>Hello <strong>{user_name}</strong>,</p>
        <p>The weekly GitHub repository analysis has completed. Here's your summary:</p>

        <h3 style="color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:6px;">Your Teams Analyzed</h3>
        {teams_html}

        <h3 style="color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:6px;">Overall Summary</h3>
        <div style="background:#f8fafc;border-radius:6px;padding:16px;margin:12px 0;">
            <table style="width:100%;font-size:14px;">
                <tr><td style="padding:4px 0;color:#64748b;">Total Batches Processed</td><td style="padding:4px 0;font-weight:600;">{results.get('total_batches', 0)}</td></tr>
                <tr><td style="padding:4px 0;color:#64748b;">Batches Triggered</td><td style="padding:4px 0;font-weight:600;">{results.get('triggered', 0)}</td></tr>
                <tr><td style="padding:4px 0;color:#64748b;">Batches Skipped</td><td style="padding:4px 0;font-weight:600;">{results.get('skipped', 0)}</td></tr>
            </table>
            <ul style="margin-top:12px;padding-left:20px;">{batch_details_html}</ul>
        </div>

        <p style="text-align:center;margin-top:24px;">
            <a href="{dashboard_url}" style="display:inline-block;padding:12px 28px;background-color:#3b82f6;color:#ffffff;text-decoration:none;border-radius:6px;font-weight:bold;">
                View Mentor Dashboard
            </a>
        </p>

        <br>
        <p>Best regards,<br>
        <strong>GitHub Agent Analysis System</strong></p>
        """
        html_wrapper = EmailTemplates.get_html_wrapper(
            f"Weekly Analysis Complete — {len(analyzed_teams)} Teams Analyzed", html_content
        )
        return {"text": text_body, "html": html_wrapper}

    @staticmethod
    def weekly_analysis_complete_admin(
        user_name: str,
        results: Dict[str, Any],
        dashboard_url: str,
    ) -> Dict[str, str]:
        """Weekly analysis complete email for admins. Returns dict with 'text' and 'html' keys."""

        # --- plain text ---
        text_body = f"Hello {user_name},\n\nThe weekly batch analysis has completed successfully.\n\n"
        text_body += "SUMMARY:\n--------\n"
        text_body += f"Total Batches: {results.get('total_batches', 0)}\n"
        text_body += f"Triggered: {results.get('triggered', 0)}\n"
        text_body += f"Skipped: {results.get('skipped', 0)}\n"
        text_body += f"Failed: {results.get('failed', 0)}\n\n"
        text_body += "BATCH DETAILS:\n--------------\n"
        for detail in results.get('batch_details', []):
            text_body += f"✓ {detail['batch']}: {detail['teams_queued']} teams analyzed\n"
        text_body += f"\nView all teams: {dashboard_url}\n\n---\nThis is an automated notification from GitHub Agent Analysis System.\n"

        # --- html ---
        batch_rows = ""
        for i, detail in enumerate(results.get('batch_details', [])):
            bg = '#f8fafc' if i % 2 == 0 else '#ffffff'
            batch_rows += (
                f'<tr style="background:{bg};">'
                f'<td style="padding:8px 12px;border:1px solid #e2e8f0;">{detail["batch"]}</td>'
                f'<td style="padding:8px 12px;border:1px solid #e2e8f0;text-align:center;font-weight:600;">{detail["teams_queued"]}</td>'
                f'</tr>'
            )

        html_content = f"""
        <p>Hello <strong>{user_name}</strong>,</p>
        <p>The weekly batch analysis has completed successfully.</p>

        <h3 style="color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:6px;">Summary</h3>
        <div style="background:#f8fafc;border-radius:6px;padding:16px;margin:12px 0;">
            <table style="width:100%;font-size:14px;">
                <tr><td style="padding:4px 0;color:#64748b;">Total Batches</td><td style="padding:4px 0;font-weight:600;">{results.get('total_batches', 0)}</td></tr>
                <tr><td style="padding:4px 0;color:#64748b;">Triggered</td><td style="padding:4px 0;font-weight:600;">{results.get('triggered', 0)}</td></tr>
                <tr><td style="padding:4px 0;color:#64748b;">Skipped</td><td style="padding:4px 0;font-weight:600;">{results.get('skipped', 0)}</td></tr>
                <tr><td style="padding:4px 0;color:#64748b;">Failed</td><td style="padding:4px 0;font-weight:600;">{results.get('failed', 0)}</td></tr>
            </table>
        </div>

        <h3 style="color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:6px;">Batch Details</h3>
        <table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;">
            <thead><tr style="background:#0f172a;color:#ffffff;">
                <th style="padding:10px 12px;border:1px solid #334155;text-align:left;">Batch</th>
                <th style="padding:10px 12px;border:1px solid #334155;text-align:center;">Teams Analyzed</th>
            </tr></thead>
            <tbody>{batch_rows}</tbody>
        </table>

        <p>New scores are now available in the admin dashboard.</p>

        <p style="text-align:center;margin-top:24px;">
            <a href="{dashboard_url}" style="display:inline-block;padding:12px 28px;background-color:#3b82f6;color:#ffffff;text-decoration:none;border-radius:6px;font-weight:bold;">
                View Admin Dashboard
            </a>
        </p>

        <br>
        <p style="color:#94a3b8;font-size:12px;">This is an automated notification from GitHub Agent Analysis System.</p>
        """
        html_wrapper = EmailTemplates.get_html_wrapper("Weekly Analysis Complete", html_content)
        return {"text": text_body, "html": html_wrapper}

    @staticmethod
    def private_repo_alert_subject(team_name: str, issue_type: str) -> str:
        """Subject line for private repository alerts"""
        if issue_type == "invalid" or issue_type == "not_found" or issue_type == "missing":
            return "Action Required: Invalid GitHub URL Detected"
        return "Action Required: Make GitHub Repository Public"
    
    @staticmethod
    def private_repo_alert_body(
        team_name: str,
        repo_url: str,
        issue_type: str
    ) -> Dict[str, str]:
        """Body template for private repository alerts. Returns dict with 'text' and 'html' keys."""
        if issue_type == "invalid" or issue_type == "not_found" or issue_type == "missing":
            text_body = f"""Hi {team_name},

You have been flagged during the recent data validation process as your submitted GitHub URL was found to be invalid or inaccessible. Please verify your repository link and resolve this issue at the earliest.

To proceed, kindly contact the concerned faculty based on your program:

* Mr. Preshit Desai (AIML)
* Ms. Anushka Shukla (Honors)

For this issue, please send the email to the same email ID (preshit.desai@gla.ac.in (For AIML), anushka.shukla@gla.ac.in (For Honors))through which you received this mail and share the following team details:

1. Team No.
2. Team Members Details (Name & Enrollment No.)
3. Branch and Year
4. Project Name
5. Correct GitHub Repository URL

Ensure that the shared GitHub URL is public, valid, and contains your latest project updates. Delays in resolving this issue may affect your evaluation and project tracking.

Kindly treat this as a priority and respond as soon as possible.

Best regards,
Preshit Desai
Technical Trainer - AIML
"""
            html_content = f"""
            <p>Hi <strong>{team_name}</strong>,</p>
            <p>You have been flagged during the recent data validation process as your submitted GitHub URL
            was found to be <strong>invalid or inaccessible</strong>. Please verify your repository link and resolve this issue at the earliest.</p>

            <div style="background-color:#fef2f2;border-left:4px solid #ef4444;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
                <h3 style="margin-top:0;color:#991b1b;">\u2757 Action Required</h3>
                <p style="color:#991b1b;">Contact the concerned faculty based on your program:</p>
                <ul style="color:#991b1b;">
                    <li><strong>Mr. Preshit Desai</strong> (AIML) &mdash; preshit.desai@gla.ac.in</li>
                    <li><strong>Ms. Anushka Shukla</strong> (Honors) &mdash; anushka.shukla@gla.ac.in</li>
                </ul>
            </div>

            <p>Please reply to the same email ID through which you received this mail and share the following team details:</p>
            <ol>
                <li>Team No.</li>
                <li>Team Members Details (Name &amp; Enrollment No.)</li>
                <li>Branch and Year</li>
                <li>Project Name</li>
                <li>Correct GitHub Repository URL</li>
            </ol>

            <p>Ensure that the shared GitHub URL is <strong>public, valid, and contains your latest project updates</strong>.
            Delays in resolving this issue may affect your evaluation and project tracking.</p>

            <p style="color:#dc2626;font-weight:600;">Kindly treat this as a priority and respond as soon as possible.</p>

            <br>
            <p>Best regards,<br>
            <strong>Preshit Desai</strong><br>
            <span style="color:#64748b;">Technical Trainer - AIML</span></p>
            """
            html_wrapper = EmailTemplates.get_html_wrapper("Action Required: Invalid GitHub URL", html_content)
            return {"text": text_body, "html": html_wrapper}

        # fallback for private repo
        text_body = f"""Hi {team_name},

Your submitted GitHub repository is currently private and cannot be accessed for evaluation. Please make your repository public at the earliest to ensure proper review and monitoring.

Best regards,
Preshit Desai
Technical Trainer - AIML
"""
        html_content = f"""
        <p>Hi <strong>{team_name}</strong>,</p>
        <p>Your submitted GitHub repository is currently <strong>private</strong> and cannot be accessed for evaluation.</p>

        <div style="background-color:#fffbeb;border-left:4px solid #f59e0b;padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
            <h3 style="margin-top:0;color:#92400e;">\u26A0\uFE0F Make Your Repository Public</h3>
            <p style="margin-bottom:0;color:#92400e;">Please make your repository public at the earliest to ensure proper review and monitoring.</p>
        </div>

        <br>
        <p>Best regards,<br>
        <strong>Preshit Desai</strong><br>
        <span style="color:#64748b;">Technical Trainer - AIML</span></p>
        """
        html_wrapper = EmailTemplates.get_html_wrapper("Make GitHub Repository Public", html_content)
        return {"text": text_body, "html": html_wrapper}
    
    # ==================== INACTIVE TEAM ALERTS ====================
    
    @staticmethod
    def inactive_team_alert_subject(team_name: str, severity: str) -> str:
        """Subject line for inactive team alerts"""
        return "Warning: Inactive for Semester Project on GitHub"
    
    @staticmethod
    def inactive_team_alert_body(
        team_name: str,
        days_inactive: int,
        last_commit_date: str,
        severity: str,
        alert_count: int = 0
    ) -> Dict[str, str]:
        """Body template for inactive team alerts. Returns dict with 'text' and 'html' keys."""
        text_body = f"""Dear {team_name},

This is to inform you that your team has been inactive on GitHub for the past few days. This is unacceptable for the mini project.

You are required to be active on GitHub immediately. Follow the CI/CD process and continuously push your code on time. Failure to maintain regular activity will result in a reduction of marks for this semester’s mini project.

Individual contribution will be strictly evaluated. Ensure that all team members are consistently active on GitHub.

Treat this on priority
Best regards,
Preshit Desai
Technical Trainer - AIML
"""
        severity_color = '#dc2626' if severity == 'critical' else '#f59e0b'
        severity_bg = '#fef2f2' if severity == 'critical' else '#fffbeb'
        severity_label = 'CRITICAL' if severity == 'critical' else 'WARNING'

        html_content = f"""
        <p>Dear <strong>{team_name}</strong>,</p>

        <div style="background-color:{severity_bg};border-left:4px solid {severity_color};padding:15px;margin:20px 0;border-radius:0 4px 4px 0;">
            <h3 style="margin-top:0;color:{severity_color};">{severity_label}: Team Inactive for {days_inactive} Days</h3>
            <p style="margin-bottom:0;color:{severity_color};">Last commit: <strong>{last_commit_date}</strong></p>
        </div>

        <p>This is to inform you that your team has been <strong>inactive on GitHub</strong> for the past few days.
        This is unacceptable for the mini project.</p>

        <p>You are required to be <strong>active on GitHub immediately</strong>. Follow the CI/CD process and continuously
        push your code on time. Failure to maintain regular activity will result in a <strong>reduction of marks</strong>
        for this semester's mini project.</p>

        <p>Individual contribution will be strictly evaluated. Ensure that <strong>all team members</strong> are consistently
        active on GitHub.</p>

        <p style="color:#dc2626;font-weight:600;">Treat this on priority.</p>

        <br>
        <p>Best regards,<br>
        <strong>Preshit Desai</strong><br>
        <span style="color:#64748b;">Technical Trainer - AIML</span></p>
        """
        html_wrapper = EmailTemplates.get_html_wrapper("Inactivity Alert", html_content)
        return {"text": text_body, "html": html_wrapper}
    
    # ==================== MENTOR INACTIVE TEAM ALERTS ====================
    
    @staticmethod
    def mentor_inactive_teams_subject(mentor_name: str) -> str:
        """Subject line for mentor notification about inactive teams"""
        return "Attention Required: Inactive Teams Under Your Mentorship"
    
    @staticmethod
    def mentor_inactive_teams_body(
        mentor_name: str,
        inactive_teams: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Body template for mentor notification about inactive teams. Returns dict with 'text' and 'html' keys."""
        team_lines = ""
        for i, team in enumerate(inactive_teams, 1):
            severity_label = "CRITICAL" if team.get("severity") == "critical" else "WARNING"
            last_commit = team.get("lastCommitDate", "Never")
            raw_days = team.get('daysInactive', '?')
            days_display = "Never committed" if raw_days == 999 else f"{raw_days} days"
            team_lines += (
                f"  {i}. {team.get('teamName', 'Unknown')} "
                f"- {days_display} "
                f"(Last commit: {last_commit}) [{severity_label}]\n"
            )

        text_body = f"""Dear {mentor_name},

This is to inform you that the following teams under your mentorship have been identified as inactive on GitHub:

{team_lines}
These teams are not following the CI/CD process and are not pushing their code regularly. As their mentor, you are requested to follow up with these teams and ensure they resume regular activity on GitHub immediately.

Individual contribution of each team member is being strictly evaluated. Please ensure all team members are consistently active.

Kindly treat this on priority.

Best regards,
Anushka Shukla
Technical Trainer - AIML
"""

        # HTML version
        team_rows = ""
        for i, team in enumerate(inactive_teams):
            sev = team.get("severity", "warning")
            sev_color = '#dc2626' if sev == 'critical' else '#f59e0b'
            sev_label = 'CRITICAL' if sev == 'critical' else 'WARNING'
            bg = '#f8fafc' if i % 2 == 0 else '#ffffff'
            raw_days = team.get("daysInactive", "?")
            days_cell = "Never" if raw_days == 999 else raw_days
            team_rows += (
                f'<tr style="background:{bg};">'
                f'<td style="padding:8px 12px;border:1px solid #e2e8f0;">{team.get("teamName", "Unknown")}</td>'
                f'<td style="padding:8px 12px;border:1px solid #e2e8f0;text-align:center;">{days_cell}</td>'
                f'<td style="padding:8px 12px;border:1px solid #e2e8f0;">{team.get("lastCommitDate", "Never")}</td>'
                f'<td style="padding:8px 12px;border:1px solid #e2e8f0;text-align:center;"><span style="color:{sev_color};font-weight:600;">{sev_label}</span></td>'
                f'</tr>'
            )

        html_content = f"""
        <p>Dear <strong>{mentor_name}</strong>,</p>
        <p>The following teams under your mentorship have been identified as <strong>inactive on GitHub</strong>:</p>

        <table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;">
            <thead><tr style="background:#0f172a;color:#ffffff;">
                <th style="padding:10px 12px;border:1px solid #334155;text-align:left;">Team</th>
                <th style="padding:10px 12px;border:1px solid #334155;text-align:center;">Days Inactive</th>
                <th style="padding:10px 12px;border:1px solid #334155;text-align:left;">Last Commit</th>
                <th style="padding:10px 12px;border:1px solid #334155;text-align:center;">Severity</th>
            </tr></thead>
            <tbody>{team_rows}</tbody>
        </table>

        <p>These teams are not following the CI/CD process. As their mentor, please follow up with these teams
        and ensure they resume regular activity on GitHub <strong>immediately</strong>.</p>

        <p>Individual contribution of each team member is being strictly evaluated.
        Please ensure all team members are consistently active.</p>

        <p style="color:#dc2626;font-weight:600;">Kindly treat this on priority.</p>

        <br>
        <p>Best regards,<br>
        <strong>Anushka Shukla</strong><br>
        <span style="color:#64748b;">Technical Trainer - AIML</span></p>
        """
        html_wrapper = EmailTemplates.get_html_wrapper("Inactive Teams Alert", html_content)
        return {"text": text_body, "html": html_wrapper}

    @staticmethod
    def mentor_marks_reminder_subject(team_name: str, round_name: str = "") -> str:
        """Subject line for mentor reminder about pending marks entry."""
        if round_name:
            return f"Weekly Reminder: Pending Mentor Marks - {team_name} ({round_name})"
        return f"Weekly Reminder: Pending Mentor Marks - {team_name}"

    @staticmethod
    def mentor_marks_reminder_body(
        mentor_name: str,
        team_name: str,
        batch_name: str,
        round_name: str = "",
        requested_by: str = "ProjectFlow Admin",
    ) -> Dict[str, str]:
        """Body template for mentor reminder when team marks are pending. Returns text and html."""
        round_display = round_name.strip() if round_name and round_name.strip() else "Current Round"

        text_body = f"""Dear {mentor_name},

The following team under your mentorship has pending marks entry:

  Team: {team_name}
  Batch: {batch_name}
  Round: {round_display}
  Status: PENDING MARKS

Please submit marks for this team at the earliest.

Individual contribution of each team member is being strictly evaluated. Please ensure all team members are assessed consistently.

Kindly treat this on priority.

Best regards,
{requested_by}
"""

        html_content = f"""
        <p>Dear <strong>{mentor_name}</strong>,</p>
        <p>The following team under your mentorship has pending mentor marks:</p>

        <table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;">
            <thead><tr style="background:#0f172a;color:#ffffff;">
                <th style="padding:10px 12px;border:1px solid #334155;text-align:left;">Team</th>
                <th style="padding:10px 12px;border:1px solid #334155;text-align:left;">Batch</th>
                <th style="padding:10px 12px;border:1px solid #334155;text-align:left;">Round</th>
                <th style="padding:10px 12px;border:1px solid #334155;text-align:center;">Status</th>
            </tr></thead>
            <tbody>
                <tr style="background:#f8fafc;">
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;">{team_name}</td>
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;">{batch_name}</td>
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;">{round_display}</td>
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;text-align:center;"><span style="color:#dc2626;font-weight:600;">PENDING MARKS</span></td>
                </tr>
            </tbody>
        </table>

        <p>Please submit marks for this team at the earliest.</p>

        <p>Individual contribution of each team member is being strictly evaluated.
        Please ensure all team members are assessed consistently.</p>

        <p style="color:#dc2626;font-weight:600;">Kindly treat this on priority.</p>

        <br>
        <p>Best regards,<br>
        <strong>{requested_by}</strong></p>
        """
        html_wrapper = EmailTemplates.get_html_wrapper("Mentor Marks Reminder", html_content)
        return {"text": text_body, "html": html_wrapper}

    @staticmethod
    def mentor_marks_bulk_reminder_subject(batch_name: str, round_name: str = "", team_count: int = 0) -> str:
        """Subject line for mentor reminder about multiple pending teams."""
        team_label = "Team" if int(team_count or 0) == 1 else "Teams"
        if round_name:
            return f"Weekly Reminder: Pending Mentor Marks - {team_count} {team_label} ({round_name})"
        return f"Weekly Reminder: Pending Mentor Marks - {team_count} {team_label}"

    @staticmethod
    def mentor_marks_bulk_reminder_body(
        mentor_name: str,
        team_names: List[str],
        batch_name: str,
        round_name: str = "",
        requested_by: str = "ProjectFlow Admin",
    ) -> Dict[str, str]:
        """Body template for mentor reminder when multiple teams have pending marks."""
        clean_team_names = [str(team_name or "").strip() for team_name in team_names if str(team_name or "").strip()]
        team_count = len(clean_team_names)
        team_label = "team" if team_count == 1 else "teams"
        round_display = round_name.strip() if round_name and round_name.strip() else "Current Round"

        team_lines = "\n".join(f"  - {team_name}" for team_name in clean_team_names)
        team_rows = "".join(
            f"""
                <tr style=\"background:{'#f8fafc' if index % 2 == 0 else '#ffffff'};\">
                    <td style=\"padding:8px 12px;border:1px solid #e2e8f0;\">{team_name}</td>
                </tr>
            """
            for index, team_name in enumerate(clean_team_names)
        )

        text_body = f"""Dear {mentor_name},

The following {team_label} under your mentorship have pending marks entry:

{team_lines}

  Batch: {batch_name}
  Round: {round_display}
  Status: PENDING MARKS

Please submit marks for these {team_label} at the earliest.

Individual contribution of each team member is being strictly evaluated. Please ensure all team members are assessed consistently.

Kindly treat this on priority.

Best regards,
{requested_by}
"""

        html_content = f"""
        <p>Dear <strong>{mentor_name}</strong>,</p>
        <p>The following {team_label} under your mentorship have pending mentor marks:</p>

        <table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;">
            <thead><tr style="background:#0f172a;color:#ffffff;">
                <th style="padding:10px 12px;border:1px solid #334155;text-align:left;">Team</th>
            </tr></thead>
            <tbody>
                {team_rows}
            </tbody>
        </table>

        <table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;">
            <tbody>
                <tr style="background:#f8fafc;">
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;width:180px;">Batch</td>
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;">{batch_name}</td>
                </tr>
                <tr>
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Round</td>
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;">{round_display}</td>
                </tr>
                <tr style="background:#f8fafc;">
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Pending Teams</td>
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;">{team_count} {team_label}</td>
                </tr>
            </tbody>
        </table>

        <p>Please submit marks for these {team_label} at the earliest.</p>

        <p>Individual contribution of each team member is being strictly evaluated.
        Please ensure all team members are assessed consistently.</p>

        <p style="color:#dc2626;font-weight:600;">Kindly treat this on priority.</p>

        <br>
        <p>Best regards,<br>
        <strong>{requested_by}</strong></p>
        """
        html_wrapper = EmailTemplates.get_html_wrapper("Mentor Marks Reminder", html_content)
        return {"text": text_body, "html": html_wrapper}

    @staticmethod
    def mentor_round_assignment_subject(batch_name: str, round_name: str) -> str:
        """Subject line for new mentor round notification."""
        return f"Action Required: Fill Marks for {round_name} - {batch_name}"

    @staticmethod
    def mentor_round_assignment_body(
        mentor_name: str,
        batch_name: str,
        round_name: str,
        team_count: int,
        dashboard_url: str,
        requested_by: str = "ProjectFlow Admin",
    ) -> Dict[str, str]:
        """Body template for notifying mentors when a new marks round is created."""
        team_label = "team" if int(team_count or 0) == 1 else "teams"

        text_body = f"""Dear {mentor_name},

A new mentor grading round has been created and marks submission is now open.

  Batch: {batch_name}
  Round: {round_name}
  Assigned Teams: {team_count} {team_label}

Please open your mentor dashboard and submit marks for your assigned teams:
{dashboard_url}

Best regards,
{requested_by}
"""

        html_content = f"""
        <p>Dear <strong>{mentor_name}</strong>,</p>

        <p>A new mentor grading round has been created and marks submission is now open.</p>

        <table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;">
            <tbody>
                <tr style="background:#f8fafc;">
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;width:180px;">Batch</td>
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;">{batch_name}</td>
                </tr>
                <tr>
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Round</td>
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;">{round_name}</td>
                </tr>
                <tr style="background:#f8fafc;">
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:600;">Assigned Teams</td>
                    <td style="padding:8px 12px;border:1px solid #e2e8f0;">{team_count} {team_label}</td>
                </tr>
            </tbody>
        </table>

        <p>
            <a href="{dashboard_url}" style="display:inline-block;background:#0f172a;color:#ffffff;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:600;">
                Open Mentor Dashboard
            </a>
        </p>

        <p>If the button does not work, copy this link into your browser:<br>
        <a href="{dashboard_url}">{dashboard_url}</a></p>

        <br>
        <p>Best regards,<br>
        <strong>{requested_by}</strong></p>
        """

        html_wrapper = EmailTemplates.get_html_wrapper("Mentor Marks Submission", html_content)
        return {"text": text_body, "html": html_wrapper}

    # ==================== INACTIVE MEMBER ALERTS ====================

    @staticmethod
    def inactive_member_alert_subject(team_name: str, weeks_inactive: int = 1) -> str:
        """Subject line for individual inactive member poor-performance alert.
        Escalates wording based on how many consecutive weeks the member has been inactive.
        """
        if weeks_inactive >= 4:
            return f"\U0001F6A8 FINAL WARNING: {weeks_inactive} Weeks No Contribution \u2013 {team_name}"
        elif weeks_inactive >= 2:
            return f"\U0001F6A8 Escalated Alert: {weeks_inactive} Weeks No Contribution \u2013 {team_name}"
        return f"\u26a0\ufe0f Warning: No GitHub Contribution Detected \u2013 {team_name}"

    @staticmethod
    def inactive_member_alert_body(
        member_name: str,
        team_name: str,
        project_name: str,
        total_commits: int,
        weeks_inactive: int = 1,
        mark_penalty: int = 0,
    ) -> Dict[str, str]:
        """Email body for a team member who has made zero commits while their team is active.

        weeks_inactive: consecutive weeks with zero personal commits (1 = first notice).
        mark_penalty:   cumulative marks already deducted (0 on first notice, grows each week).
        """
        # ---- severity tier ----
        if weeks_inactive >= 4:
            severity_label = "FINAL WARNING"
            severity_emoji = "\U0001F6A8"
        elif weeks_inactive >= 2:
            severity_label = "ESCALATED ALERT"
            severity_emoji = "\U0001F6A8"
        else:
            severity_label = "FIRST NOTICE"
            severity_emoji = "\u26a0\ufe0f"

        penalty_line = (
            f"\nMARK PENALTY APPLIED: -{mark_penalty} marks deducted from your contribution score.\n"
            if mark_penalty > 0 else ""
        )
        escalation_note = (
            f"\nThis is your {weeks_inactive}{'st' if weeks_inactive == 1 else 'nd' if weeks_inactive == 2 else 'rd' if weeks_inactive == 3 else 'th'} consecutive week with zero commits."
            f"{penalty_line}"
        )

        text_body = f"""Dear {member_name},

[{severity_emoji} {severity_label}]

This is a formal notice regarding your GitHub contribution in the mini-project "{project_name}" for team {team_name}.

Our system has detected that you have made NO commits to the team's GitHub repository, despite your team having {total_commits} total commit(s) recorded.
{escalation_note}
This is unacceptable. Individual contribution is strictly evaluated as part of your semester project assessment.

Action Required:
1. Push your code to the team repository immediately.
2. Ensure your commits are made under your registered GitHub username.
3. Follow the CI/CD process as instructed.

Failure to maintain personal GitHub activity WILL result in ZERO marks for individual contribution and may affect your overall project grade.

This is a serious matter. If you are facing any difficulties, contact your mentor immediately.

Best regards,
Preshit Desai
Technical Trainer - AIML
"""

        # ---- HTML severity colours ----
        if weeks_inactive >= 4:
            sev_bg, sev_border, sev_text, sev_dark = "#fef2f2", "#7f1d1d", "#991b1b", "#7f1d1d"
        elif weeks_inactive >= 2:
            sev_bg, sev_border, sev_text, sev_dark = "#fef2f2", "#dc2626", "#dc2626", "#991b1b"
        else:
            sev_bg, sev_border, sev_text, sev_dark = "#fffbeb", "#f59e0b", "#b45309", "#92400e"

        week_ord = (
            f"{weeks_inactive}st" if weeks_inactive == 1 else
            f"{weeks_inactive}nd" if weeks_inactive == 2 else
            f"{weeks_inactive}rd" if weeks_inactive == 3 else
            f"{weeks_inactive}th"
        )

        # Penalty block — only shown from week 2 onwards
        penalty_html = ""
        if mark_penalty > 0:
            penalty_html = f"""
        <div style="background:#fef2f2;border:2px solid #dc2626;border-radius:8px;padding:14px 16px;margin:16px 0;text-align:center;">
            <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#dc2626;margin-bottom:4px;">
                Marks Deducted This Week
            </div>
            <div style="font-size:36px;font-weight:800;color:#dc2626;line-height:1;">-{mark_penalty}</div>
            <div style="font-size:12px;color:#991b1b;margin-top:4px;">
                Cumulative inactivity penalty applied to your contribution score
            </div>
        </div>"""

        html_content = f"""
        <p>Dear <strong>{member_name}</strong>,</p>

        <div style="background-color:{sev_bg};border-left:4px solid {sev_border};padding:16px 18px;margin:20px 0;border-radius:0 6px 6px 0;">
            <h3 style="margin-top:0;color:{sev_text};">{severity_emoji} {severity_label} &mdash; {week_ord} Consecutive Week With No Commits</h3>
            <p style="margin-bottom:0;color:{sev_dark};">
                This is a formal notice regarding your GitHub contribution in the mini-project
                <strong>&ldquo;{project_name}&rdquo;</strong> for team <strong>{team_name}</strong>.
            </p>
        </div>

        <!-- Commit stats comparison -->
        <table style="width:100%;border-collapse:separate;border-spacing:10px;margin:18px 0;">
            <tr>
                <td style="width:50%;background:#fef2f2;border:2px solid #fca5a5;border-radius:8px;padding:16px;text-align:center;vertical-align:top;">
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#dc2626;margin-bottom:6px;">Your Commits</div>
                    <div style="font-size:42px;font-weight:800;color:#dc2626;line-height:1;">0</div>
                    <div style="font-size:12px;color:#991b1b;margin-top:6px;">{week_ord} week &mdash; no contribution</div>
                </td>
                <td style="width:50%;background:#f0fdf4;border:2px solid #86efac;border-radius:8px;padding:16px;text-align:center;vertical-align:top;">
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#16a34a;margin-bottom:6px;">Team Total Commits</div>
                    <div style="font-size:42px;font-weight:800;color:#16a34a;line-height:1;">{total_commits}</div>
                    <div style="font-size:12px;color:#15803d;margin-top:6px;">Commits by your teammates</div>
                </td>
            </tr>
        </table>

        {penalty_html}

        <div style="background:#fffbeb;border-left:4px solid #f59e0b;padding:14px 16px;margin:20px 0;border-radius:0 6px 6px 0;">
            <p style="margin:0 0 8px;font-weight:700;color:#92400e;">&#9889; Action Required &mdash; Push your code immediately:</p>
            <ol style="margin:0;padding-left:20px;color:#78350f;line-height:1.8;">
                <li>Push your code to the team repository <strong>immediately</strong>.</li>
                <li>Ensure commits are made under your <strong>registered GitHub username</strong>.</li>
                <li>Follow the CI/CD process as instructed.</li>
            </ol>
        </div>

        <div style="background:#fef2f2;border-radius:6px;padding:12px 16px;margin:16px 0;border:1px solid #fca5a5;">
            <p style="margin:0;color:#991b1b;font-weight:600;">
                &#10060; Continued inactivity <strong>WILL result in ZERO marks</strong> for individual
                contribution and may affect your overall project grade.
                Each additional inactive week adds a further penalty to your score.
            </p>
        </div>

        <p style="color:#64748b;font-size:13px;margin-top:20px;">
            If you are facing any difficulties, contact your mentor <strong>immediately</strong>.
        </p>

        <br>
        <p>Best regards,<br>
        <strong>Preshit Desai</strong><br>
        <span style="color:#64748b;">Technical Trainer - AIML</span></p>
        """
        html_wrapper = EmailTemplates.get_html_wrapper(
            f"{severity_emoji} Poor Performance Alert \u2013 Week {weeks_inactive}", html_content
        )
        return {"text": text_body, "html": html_wrapper}

    # ==================== ANALYSIS REPORT ====================
    
    @staticmethod
    def analysis_report_subject(team_name: str) -> str:
        """Subject line for analysis report"""
        return f"Update: Repository Analysis Complete - {team_name}"
    
    @staticmethod
    def analysis_report_body(
        team_name: str,
        repo_url: str,
        overall_score: float,
        tech_stack: str,
        highlights: List[str]
    ) -> Dict[str, str]:
        """Body template for analysis report. Returns dict with 'text' and 'html' keys."""
        highlights_text = "\n".join([f"- {h}" for h in highlights])
        
        text_body = f"""Dear {team_name},

Please be informed that the automated analysis of your GitHub repository has been completed successfully.

REPOSITORY: {repo_url}
OVERALL SCORE: {overall_score:.1f}/100
DETECTED TECH STACK: {tech_stack}

Key findings from the analysis:
{highlights_text}

We strongly recommend reviewing your detailed performance report and taking necessary actions to resolve any identified issues before your next evaluation.

Best regards,
Preshit Desai
Technical Trainer - AIML
"""
        highlights_html = "".join([f"<li>{h}</li>" for h in highlights])
        score_color = '#16a34a' if overall_score >= 70 else '#ea580c' if overall_score >= 40 else '#dc2626'

        html_content = f"""
        <p>Dear <strong>{team_name}</strong>,</p>
        <p>The automated analysis of your GitHub repository has been completed successfully.</p>

        <div style="background:#f8fafc;border-radius:6px;padding:16px;margin:12px 0;">
            <table style="width:100%;font-size:14px;">
                <tr><td style="padding:4px 0;color:#64748b;">Repository</td><td style="padding:4px 0;"><a href="{repo_url}" style="color:#3b82f6;">{repo_url}</a></td></tr>
                <tr><td style="padding:4px 0;color:#64748b;">Overall Score</td><td style="padding:4px 0;font-weight:700;font-size:18px;color:{score_color};">{overall_score:.1f}/100</td></tr>
                <tr><td style="padding:4px 0;color:#64748b;">Detected Tech Stack</td><td style="padding:4px 0;font-weight:600;">{tech_stack}</td></tr>
            </table>
        </div>

        <h3 style="color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:6px;">Key Findings</h3>
        <ul>{highlights_html}</ul>

        <p>We strongly recommend reviewing your detailed performance report and taking necessary actions to
        resolve any identified issues before your next evaluation.</p>

        <br>
        <p>Best regards,<br>
        <strong>Preshit Desai</strong><br>
        <span style="color:#64748b;">Technical Trainer - AIML</span></p>
        """
        html_wrapper = EmailTemplates.get_html_wrapper(f"Repository Analysis \u2014 {team_name}", html_content)
        return {"text": text_body, "html": html_wrapper}
    
    @staticmethod
    def weekly_report_subject(team_name: str, project_name: str = "") -> str:
        """Subject line for weekly report emails"""
        subject = f"Update: Weekly GitHub Analysis Report - {team_name}"
        if project_name:
            subject += f" | {project_name}"
        return subject
        
    @staticmethod
    def get_html_wrapper(title: str, content_html: str) -> str:
        """Standard HTML wrapper for all emails to ensure consistent styling"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333333;
                    background-color: #f4f7f6;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    max-width: 600px;
                    margin: 20px auto;
                    background-color: #ffffff;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                }}
                .header {{
                    background-color: #0f172a;
                    color: #ffffff;
                    padding: 20px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                    font-weight: 600;
                }}
                .content {{
                    padding: 30px;
                }}
                .footer {{
                    background-color: #f8fafc;
                    padding: 20px;
                    text-align: center;
                    font-size: 12px;
                    color: #64748b;
                    border-top: 1px solid #e2e8f0;
                }}
                .button {{
                    display: inline-block;
                    padding: 10px 20px;
                    background-color: #3b82f6;
                    color: #ffffff;
                    text-decoration: none;
                    border-radius: 4px;
                    font-weight: bold;
                    margin-top: 15px;
                }}
                .highlight-box {{
                    background-color: #f0fdf4;
                    border-left: 4px solid #22c55e;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 0 4px 4px 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{title}</h1>
                </div>
                <div class="content">
                    {content_html}
                </div>
                <div class="footer">
                    <p>This is an automated message from ProjectFlow.</p>
                </div>
            </div>
        </body>
        </html>
        """

    @staticmethod
    def weekly_report_body(team_name: str, includes_leaderboard: bool, project_name: str = "", is_empty_repo: bool = False) -> Dict[str, str]:
        """Body template for weekly reports. Returns both text and html formats."""
        greeting_name = team_name
        if project_name and project_name != team_name:
            greeting_name += f" ({project_name})"
            
        # Plain text generation
        text_body = f"""Dear {greeting_name},

This is to inform you that your weekly GitHub analysis report has been generated and is attached to this email.

This comprehensive report includes:
- Overall scores and performance metrics
- Code quality and security analysis
- Individual contributor statistics
- AI-generated content analysis
- Recommendations for improvement
"""

        if includes_leaderboard:
            text_body += "\nWe have also attached the batch leaderboard PDF, which indicates your team's current standing among all teams in your batch.\n"

        if is_empty_repo:
            text_body += """
⚠️ WARNING: EMPTY REPOSITORY DETECTED ⚠️
Our analysis indicates that your linked GitHub repository is completely empty. 
Because there is no code, you have received a score of 0 for this evaluation cycle.
You are strictly advised to push your code immediately to avoid failing the mini-project.

"""
        else:
            text_body += """
You are strictly advised to review the attached report(s) carefully and take necessary actions to resolve any identified issues before your next evaluation cycle.

"""

        text_body += """Best regards,
Preshit Desai
Technical Trainer - AIML
"""
        
        # HTML generation
        html_content = f"""
        <p>Dear <strong>{greeting_name}</strong>,</p>
        
        <p>This is to inform you that your weekly GitHub analysis report has been generated and is attached to this email.</p>
        
        <div class="highlight-box">
            <h3 style="margin-top: 0; color: #166534;">📝 Report Contents:</h3>
            <ul style="margin-bottom: 0;">
                <li>Overall scores and performance metrics</li>
                <li>Code quality and security analysis</li>
                <li>Individual contributor statistics</li>
                <li>AI-generated content analysis</li>
                <li>Recommendations for improvement</li>
            </ul>
        </div>
        """
        
        if includes_leaderboard:
            html_content += """
            <p><em>We have also attached the batch leaderboard PDF, which indicates your team's current standing among all teams in your batch.</em></p>
            """
            
        if is_empty_repo:
            html_content += """
            <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 15px; margin: 20px 0; border-radius: 0 4px 4px 0;">
                <h3 style="margin-top: 0; color: #991b1b;">⚠️ WARNING: EMPTY REPOSITORY DETECTED ⚠️</h3>
                <p style="color: #991b1b; margin-bottom: 0;">
                    Our analysis indicates that your linked GitHub repository is completely empty. Because there is no code, you have received a score of 0 for this evaluation cycle.<br><br>
                    <strong>You are strictly advised to push your code immediately to avoid failing the mini-project.</strong>
                </p>
            </div>
            """
        else:
            html_content += """
            <p style="color: #b91c1c; font-weight: 500;">
                ⚠️ You are strictly advised to review the attached report(s) carefully and take necessary actions to resolve any identified issues before your next evaluation cycle.
            </p>
            """
        
        html_content += """
        <br>
        <p>Best regards,<br>
        <strong>Preshit Desai</strong><br>
        <span style="color: #64748b;">Technical Trainer - AIML</span></p>
        """
        
        html_wrapper = EmailTemplates.get_html_wrapper("Weekly Analysis Report", html_content)
        
        return {
            "text": text_body,
            "html": html_wrapper
        }


        
    @staticmethod
    def leaderboard_only_subject(batch_name: str) -> str:
        """Subject line for batch leaderboard emails"""
        return f"Batch Leaderboard Update: {batch_name}"

    @staticmethod
    def leaderboard_only_body(batch_name: str, team_name: str) -> Dict[str, str]:
        """Body template for standalone leaderboard emails. Returns both text and html formats."""
        # Plain text generation
        text_body = f"""Dear {team_name},

This is to inform you that the updated batch leaderboard for {batch_name} has been generated and is attached to this email.

This leaderboard indicates your team's current standing among all teams in your batch based on the latest automated analysis of your GitHub repository.

You are encouraged to review the attached leaderboard to understand your current performance level.

Best regards,
Preshit Desai
Technical Trainer - AIML
"""
        
        # HTML generation
        html_content = f"""
        <p>Dear <strong>{team_name}</strong>,</p>
        
        <p>This is to inform you that the updated batch leaderboard for <strong>{batch_name}</strong> has been generated and is attached to this email.</p>
        
        <div class="highlight-box">
            <h3 style="margin-top: 0; color: #1e40af;">🏆 Batch Leaderboard</h3>
            <p style="margin-bottom: 0;">This leaderboard indicates your team's current standing among all teams in your batch based on the latest automated analysis of your GitHub repository.</p>
        </div>
        
        <p>You are encouraged to review the attached leaderboard to understand your current performance level.</p>
        
        <br>
        <p>Best regards,<br>
        <strong>Preshit Desai</strong><br>
        <span style="color: #64748b;">Technical Trainer - AIML</span></p>
        """
        
        html_wrapper = EmailTemplates.get_html_wrapper(f"Leaderboard: {batch_name}", html_content)
        
        return {
            "text": text_body,
            "html": html_wrapper
        }

    # ==================== HELPER METHODS ====================
    
    @staticmethod
    def get_ordinal_suffix(rank: int) -> str:
        """
        Get ordinal suffix for rank (1st, 2nd, 3rd, 4th, etc.)
        
        Args:
            rank: Integer rank
        
        Returns:
            Ordinal string (e.g., "1st", "2nd", "3rd")
        """
        if 11 <= rank <= 13:
            suffix = "th"
        else:
            last_digit = rank % 10
            if last_digit == 1:
                suffix = "st"
            elif last_digit == 2:
                suffix = "nd"
            elif last_digit == 3:
                suffix = "rd"
            else:
                suffix = "th"
        
        return f"{rank}{suffix}"
    
    @staticmethod
    def format_leaderboard_entry(
        rank: int,
        team_name: str,
        score: float,
        project_name: Optional[str] = None,
        is_recipient: bool = False
    ) -> str:
        """
        Format a single leaderboard entry
        
        Args:
            rank: Team rank
            team_name: Name of the team
            score: Overall score
            project_name: Optional project name
            is_recipient: Whether this is the recipient's team
        
        Returns:
            Formatted entry string
        """
        ordinal = EmailTemplates.get_ordinal_suffix(rank)
        # Pad ordinal to 5 characters for alignment
        ordinal_padded = f"{ordinal:>5}"
        # Pad team name to 30 characters
        team_padded = f"{team_name:<30}"
        # Pad project name to 35 characters or use "N/A"
        project_display = (project_name[:35] if project_name else "N/A")
        project_padded = f"{project_display:<35}"
        # Format score with one decimal place
        score_str = f"{score:.1f}"
        
        if is_recipient:
            return f">>> {ordinal_padded}  {team_padded}  {project_padded}  {score_str} <<<"
        else:
            return f" {ordinal_padded}  {team_padded}  {project_padded}  {score_str}"
    
    @staticmethod
    def get_footer() -> str:
        """Standard footer for all emails"""
        return "\n---\nThis is an automated message from the GitHub Analysis System."
    
    # ==================== MENTOR CUSTOM MAIL ====================
    
    @staticmethod
    def mentor_custom_mail_html(
        sender_name: str,
        team_name: str,
        subject: str,
        body: str,
    ) -> str:
        """HTML template for custom mentor-to-team emails."""
        # Escape HTML chars in user-supplied text
        import html as _html
        safe_body = _html.escape(body).replace("\n", "<br>")
        safe_subject = _html.escape(subject)
        safe_sender = _html.escape(sender_name)
        safe_team = _html.escape(team_name)

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_subject}</title>
<style>
body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; background: #f4f7f6; margin: 0; padding: 0; }}
.container {{ max-width: 600px; margin: 24px auto; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
.header {{ background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: #fff; padding: 24px 28px; }}
.header h1 {{ margin: 0 0 4px 0; font-size: 20px; font-weight: 600; }}
.header p {{ margin: 0; font-size: 13px; opacity: 0.85; }}
.body {{ padding: 28px; }}
.body .message {{ background: #f8fafc; border-left: 4px solid #6366f1; padding: 16px 20px; border-radius: 0 6px 6px 0; margin-bottom: 20px; font-size: 15px; color: #334155; }}
.meta {{ font-size: 13px; color: #64748b; margin-bottom: 16px; }}
.footer {{ background: #f8fafc; padding: 16px 28px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{safe_subject}</h1>
    <p>From {safe_sender} &middot; Team: {safe_team}</p>
  </div>
  <div class="body">
    <div class="meta">This email was sent by your mentor/admin via ProjectFlow.</div>
    <div class="message">{safe_body}</div>
    <p style="font-size:13px;color:#64748b;">You can reply directly to this email to respond to {safe_sender}.</p>
  </div>
  <div class="footer">
    Sent via ProjectFlow &mdash; GitHub Project Analysis &amp; Management
  </div>
</div>
</body>
</html>"""

    @staticmethod
    def format_commit_list(commits: List[Dict[str, Any]], limit: int = 10) -> str:
        """Format a list of commits for email display"""
        if not commits:
            return "No commits to display.\n"
        
        result = ""
        for i, commit in enumerate(commits[:limit], 1):
            commit_hash = commit.get("hash", "unknown")[:7]
            message = commit.get("message", "No message")[:50]
            result += f"{i}. {commit_hash} - {message}\n"
        
        if len(commits) > limit:
            result += f"\n... and {len(commits) - limit} more commits\n"
        
        return result


# ==================== USAGE EXAMPLES ====================
"""
Example usage in email service:

from ..templates.email_templates import EmailTemplates

# Duplicate commit alert
subject = EmailTemplates.duplicate_commit_alert_subject(team_name)
body = EmailTemplates.duplicate_commit_alert_body(team_name, repo_url, incidents)

# Quality alert
subject = EmailTemplates.quality_alert_subject(team_name)
body = EmailTemplates.quality_alert_body(
    team_name, 
    fake_commit_count, 
    fake_commit_ratio, 
    commit_health,
    total_commits,
    threshold,
    fake_commits
)
"""
