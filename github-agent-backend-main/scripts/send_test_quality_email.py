"""
One-time script to send a test quality alert email with suspicious author data.
Uses real Team 4 data from the database.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from src.api.backend.utils.email import send_alert_email
from src.api.backend.templates.email_templates import EmailTemplates

# ---------- Real data from Team 4 ----------
team_name = "Team 4"
total_commits = 65
fake_commit_count = 4
fake_commit_ratio = 6.2
commit_health = "At Risk"
threshold = 30.0

# Suspicious author data (the "User" problem)
suspicious_authors = {
    "has_suspicious": True,
    "suspicious_authors": [
        {
            "name": "User",
            "commits": 51,
            "share": 78.5,
            "reason": "Generic default name 'User'"
        }
    ]
}

# Generate email body using the updated template
subject = EmailTemplates.quality_alert_subject(team_name)
body = EmailTemplates.quality_alert_body(
    team_name=team_name,
    fake_commit_count=fake_commit_count,
    fake_commit_ratio=fake_commit_ratio,
    commit_health=commit_health,
    total_commits=total_commits,
    threshold=threshold,
    fake_commits=[],
    suspicious_authors=suspicious_authors,
)

# Send to user
recipient = "parv.agarwal_cs.aiml23@gla.ac.in"

print(f"Subject: {subject}")
print(f"To: {recipient}")
print(f"---")
print(body)
print(f"---")
print(f"Sending...")

try:
    send_alert_email(
        subject=subject,
        body_text=body,
        to_email=recipient,
    )
    print("✅ Email sent successfully!")
except Exception as e:
    print(f"❌ Failed to send: {e}")
