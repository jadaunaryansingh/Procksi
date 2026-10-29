import os
import sys
import asyncio
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

from src.api.backend.utils.email import send_alert_email
from src.api.backend.templates.email_templates import EmailTemplates

# Recipient list for testing
RECIPIENTS = [
    "parv.agarwal_cs.aiml23@gla.ac.in",
    "yash.jain_cs.aiml23@gla.ac.in"
]

def format_terminal_output(title: str, content: str):
    """Log the email being sent to terminal"""
    print(f"\n{'='*50}")
    print(f"SENDING: {title}")
    print(f"{'='*50}")
    print(f"Subject: {content.get('subject')}")
    body_preview = content.get('body', '')
    if isinstance(body_preview, dict):
        body_preview = body_preview.get('text', '')
    print(f"Body Preview: {body_preview[:100]}...")


def _extract(body):
    """Extract text and html from template result (dict or str)."""
    if isinstance(body, dict):
        return body.get("text", ""), body.get("html")
    return body, None

def test_duplicate_commit_alert():
    subject = EmailTemplates.duplicate_commit_alert_subject("Test Team A")
    incidents = [
        {"hash": "a1b2c3d", "message": "Initial commit"},
        {"hash": "e4f5g6h", "message": "Initial commit"}
    ]
    body = EmailTemplates.duplicate_commit_alert_body("Test Team A", "https://github.com/test/repo", incidents)
    body_text, html_body = _extract(body)
    
    format_terminal_output("Duplicate Commit Alert", {"subject": subject, "body": body_text})
    for email in RECIPIENTS:
        send_alert_email(subject=subject, body_text=body_text, to_email=email, html_body=html_body)

def test_private_repo_alert():
    subject = EmailTemplates.private_repo_alert_subject("Test Team B", "private")
    body = EmailTemplates.private_repo_alert_body("Test Team B", "https://github.com/test/repo", "private")
    body_text, html_body = _extract(body)
    
    format_terminal_output("Private Repo Alert", {"subject": subject, "body": body_text})
    for email in RECIPIENTS:
        send_alert_email(subject=subject, body_text=body_text, to_email=email, html_body=html_body)

def test_invalid_url_alert():
    subject = EmailTemplates.private_repo_alert_subject("Test Team C", "invalid")
    body = EmailTemplates.private_repo_alert_body("Test Team C", "https://github.com/test/repo", "invalid")
    body_text, html_body = _extract(body)
    
    format_terminal_output("Invalid URL Alert", {"subject": subject, "body": body_text})
    for email in RECIPIENTS:
        send_alert_email(subject=subject, body_text=body_text, to_email=email, html_body=html_body)

def test_inactive_team_alert():
    subject = EmailTemplates.inactive_team_alert_subject("Test Team D", "High")
    body = EmailTemplates.inactive_team_alert_body("Test Team D", 10, "2026-02-12", "High", 2)
    body_text, html_body = _extract(body)
    
    format_terminal_output("Inactive Team Alert", {"subject": subject, "body": body_text})
    for email in RECIPIENTS:
        send_alert_email(subject=subject, body_text=body_text, to_email=email, html_body=html_body)

def test_quality_alert():
    subject = EmailTemplates.quality_alert_subject("Test Team E")
    fake_commits = [
        {"hash": "x1y2z3", "reasons": ["Auto-generated file", "node_modules dump"], "fake_additions": 15000}
    ]
    body = EmailTemplates.quality_alert_body("Test Team E", 45, 85.5, "Poor", 52, 20.0, fake_commits)
    body_text, html_body = _extract(body)
    
    format_terminal_output("Commit Quality Alert", {"subject": subject, "body": body_text})
    for email in RECIPIENTS:
        send_alert_email(subject=subject, body_text=body_text, to_email=email, html_body=html_body)

def test_batch_analysis_complete():
    subject = EmailTemplates.batch_analysis_complete_subject("Batch 2026-A")
    body = EmailTemplates.batch_analysis_complete_body("Batch 2026-A", 50, 48, 2)
    body_text, html_body = _extract(body)
    
    format_terminal_output("Batch Analysis Complete (Admin)", {"subject": subject, "body": body_text})
    for email in RECIPIENTS:
        send_alert_email(subject=subject, body_text=body_text, to_email=email, html_body=html_body)

def test_generic_analysis_report():
    subject = EmailTemplates.analysis_report_subject("Test Team F")
    body = EmailTemplates.analysis_report_body("Test Team F", "https://github.com/test/repo", 92.5, "React, Python", ["Excellent commit frequency", "Good code structure"])
    body_text, html_body = _extract(body)
    
    format_terminal_output("Generic Analysis Report", {"subject": subject, "body": body_text})
    for email in RECIPIENTS:
        send_alert_email(subject=subject, body_text=body_text, to_email=email, html_body=html_body)

def test_weekly_report():
    team_name = "Test Team G"
    
    subject = EmailTemplates.weekly_report_subject(team_name)
    body = EmailTemplates.weekly_report_body(
        team_name=team_name,
        includes_leaderboard=True,
        project_name="Health App",
        is_empty_repo=False
    )
    body_text, html_body = _extract(body)
    
    format_terminal_output("Weekly Report", {"subject": subject, "body": body_text})
    for email in RECIPIENTS:
        send_alert_email(subject=subject, body_text=body_text, to_email=email, html_body=html_body)

if __name__ == "__main__":
    print("Starting email template tests...")
    
    test_duplicate_commit_alert()
    test_private_repo_alert()
    test_invalid_url_alert()
    test_inactive_team_alert()
    test_quality_alert()
    test_batch_analysis_complete()
    test_generic_analysis_report()
    test_weekly_report()
    
    print("\n✅ All test emails dispatched to recipients.")
