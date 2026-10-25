"""
Seed helpers for the Panel Portal using Supabase instead of SQLAlchemy.
"""

import json
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.supabase_client import get_supabase_service
from app.security import hash_password


def _seed_rubric(client) -> None:
    """Always seed the evaluation rubric if it's missing."""
    res = client.table("evaluation_parameters").select("id").limit(1).execute()
    if res.data:
        return
    rows = [
        {"category": "Innovation & Core Idea (20 Marks)", "criterion_name": "Originality of the project concept", "max_marks": 10},
        {"category": "Innovation & Core Idea (20 Marks)", "criterion_name": "Relevance to current industry problems", "max_marks": 10},
        {"category": "Technical Implementation (40 Marks)", "criterion_name": "Architecture and Design patterns used", "max_marks": 15},
        {"category": "Technical Implementation (40 Marks)", "criterion_name": "Code quality and maintainability", "max_marks": 15},
        {"category": "Technical Implementation (40 Marks)", "criterion_name": "Integration of core technologies (e.g., ML, Blockchain)", "max_marks": 10},
        {"category": "Project Management & Collaboration (20 Marks)", "criterion_name": "Milestone tracking and adherence to timeline", "max_marks": 10},
        {"category": "Project Management & Collaboration (20 Marks)", "criterion_name": "Team contribution and GitHub activity", "max_marks": 10},
        {"category": "Presentation & Q&A (20 Marks)", "criterion_name": "Clarity of the presentation", "max_marks": 10},
        {"category": "Presentation & Q&A (20 Marks)", "criterion_name": "Ability to answer technical questions effectively", "max_marks": 10},
    ]
    client.table("evaluation_parameters").insert(rows).execute()


# ---------------------------------------------------------------------------
# Demo data — only used when SEED_DEMO_DATA=true
# ---------------------------------------------------------------------------

def _seed_teams_projects_github(client) -> None:
    teams_spec = [
        (1, "Apollo Web Services", "Cloud Operations Suite"),
        (2, "Gamma Rayburst", "Particle Visualization"),
        (3, "Beta Blockers", "Real-time Vital Monitoring System"),
        (4, "Delta Force", "Campus Logistics"),
        (5, "Echo Systems", "Peer Learning Network"),
        (6, "Falcon Stack", "Smart Attendance Analytics"),
        (7, "Gridline AI", "Adaptive Timetable Optimizer"),
        (8, "Helix Coders", "Lab Equipment Tracker"),
        (9, "Ion Innovators", "Digital Noticeboard Engine"),
        (10, "Jupiter Labs", "Automated Exam Invigilation"),
        (11, "Kernel Knights", "Student Mentoring CRM"),
        (12, "Lambda Crew", "Placement Readiness Platform"),
        (13, "Matrix Minds", "Transport Route Optimizer"),
        (14, "Nova Nerds", "Hostel Complaint Resolver"),
        (15, "Omega Builders", "Research Paper Recommender"),
        (16, "Pixel Forge", "Internship Workflow Portal"),
        (17, "Quantum Squad", "Campus Energy Dashboard"),
        (18, "Rocket Runtime", "Code Review Automation"),
        (19, "Sigma Systems", "Department Budget Monitor"),
        (20, "Titan Tech", "Faculty Workload Planner"),
    ]
    for tid, name, title in teams_spec:
        # Check if team exists
        res_team = client.table("teams").select("id").eq("id", tid).execute()
        if not res_team.data:
            client.table("teams").insert({"id": tid, "name": name}).execute()
            
        res_proj = client.table("projects").select("id").eq("team_id", tid).execute()
        if not res_proj.data:
            client.table("projects").insert({"team_id": tid, "title": title}).execute()
            
        res_gh = client.table("github_data").select("id").eq("team_id", tid).execute()
        if not res_gh.data:
            client.table("github_data").insert({
                "team_id": tid,
                "repository_url": f"https://github.com/gla-pms/team-{tid}-project",
                "default_branch": "main",
                "open_pull_requests": 0,
                "commit_count_30d": 12 + tid,
                "last_commit_at": (datetime.now(timezone.utc) - timedelta(days=tid)).isoformat(),
            }).execute()


def _seed_demo_alerts(client, panel_id: str) -> None:
    res = client.table("alerts").select("id").eq("panel_id", panel_id).limit(1).execute()
    if res.data:
        return
    now = datetime.now(timezone.utc).isoformat()
    client.table("alerts").insert([
        {
            "panel_id": panel_id,
            "team_id": 2,
            "alert_type": "missed_escalation",
            "title": "Missed submission — Gamma Rayburst",
            "body": "Slot closed without evaluation. Administration notified per dashboard policy.",
            "created_at": now,
        },
        {
            "panel_id": panel_id,
            "team_id": 3,
            "alert_type": "reminder",
            "title": "Submit evaluation during live slot",
            "body": "Reminder: complete scoring and remarks before the slot window ends.",
            "created_at": now,
        }
    ]).execute()


def _seed_demo_panel(client) -> None:
    """Create demo panel record + user + slots. Only called when SEED_DEMO_DATA=true."""
    panel_id = "P01"
    email = "panel01@gla.ac.in"

    # Remove stale user if email changed
    client.table("users").delete().eq("email", "panel@gla.ac.in").execute()

    # Ensure Panel metadata row in 'panels' table
    res_panel = client.table("panels").select("id").eq("id", panel_id).execute()
    if not res_panel.data:
        client.table("panels").insert({
            "id": panel_id,
            "name": "Demo Panel 01",
            "description": settings.assigned_round,
        }).execute()

    # Ensure User
    res_user = client.table("users").select("id").eq("email", email).execute()
    if not res_user.data:
        client.table("users").insert({
            "email": email,
            "hashed_password": hash_password("panel123"),
            "role": "panel",
            "panel_id": panel_id,
        }).execute()
    else:
        client.table("users").update({
            "hashed_password": hash_password("panel123"),
            "role": "panel",
            "panel_id": panel_id,
        }).eq("email", email).execute()


    res_slots = client.table("slots").select("id").eq("panel_id", panel_id).limit(1).execute()
    if res_slots.data:
        _seed_demo_alerts(client, panel_id)
        return

    _seed_teams_projects_github(client)

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def at(h: int, m: int) -> datetime:
        return day_start + timedelta(hours=h, minutes=m)

    windows = [
        (1, at(4, 0), at(4, 15), "Submitted"),
        (2, at(4, 20), at(4, 35), "Missed"),
        (3, max(at(4, 45), now - timedelta(minutes=5)), now + timedelta(hours=2), "Active"),
        (4, now + timedelta(hours=2, minutes=5), now + timedelta(hours=2, minutes=20), "Upcoming"),
        (5, now + timedelta(hours=2, minutes=25), now + timedelta(hours=2, minutes=40), "Upcoming"),
    ]

    venues = ["Table 1", "Table 2", "Table 4, Main Hall", "Table 3", "Lab A"]
    labels = ["10:00 AM - 10:15 AM", "10:20 AM - 10:35 AM", "11:00 AM - 11:15 AM", "11:20 AM - 11:35 AM", "11:40 AM - 11:55 AM"]

    for i, (team_id, start, end, initial_status) in enumerate(windows):
        client.table("slots").insert({
            "panel_id": panel_id,
            "team_id": team_id,
            "venue": venues[i],
            "slot_label": labels[i],
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "status": initial_status,
        }).execute()

    existing_eval = client.table("evaluations").select("id")\
        .eq("panel_id", panel_id)\
        .eq("team_id", 1)\
        .execute()

    if not existing_eval.data:
        client.table("evaluations").insert({
            "panel_id": panel_id,
            "team_id": 1,
            "scores_json": json.dumps({"q1": 8, "q2": 7, "q3": 8, "q4": 9}),
            "remarks": "Strong delivery; minor architecture gaps.",
            "submitted_at": (now - timedelta(days=1)).isoformat(),
            "receipt_id": "REC-DEMO-APOLLO01",
            "locked": True,
        }).execute()

    _seed_demo_alerts(client, panel_id)


def seed_if_empty(client) -> None:
    """Entry point called at startup."""
    _seed_rubric(client)
    if settings.seed_demo_data:
        _seed_demo_panel(client)
