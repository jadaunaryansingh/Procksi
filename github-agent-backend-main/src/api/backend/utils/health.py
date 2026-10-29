"""
Team Health Calculation Utility.
Calculates health status and risk flags for teams based on activity metrics.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
import json


def calculate_team_health(
    report_json: Optional[Dict[str, Any]],
    team_members_count: int = 4,
    last_activity: Optional[str] = None,
    created_at: Optional[str] = None
) -> Tuple[str, List[str]]:
    """
    Calculate team health status and risk flags based on activity metrics.
    
    Args:
        report_json: The team's report_json from the database
        team_members_count: Number of members in the team
        last_activity: ISO timestamp of last activity
        created_at: ISO timestamp of team creation
    
    Returns:
        Tuple of (health_status, risk_flags)
        - health_status: "on_track", "at_risk", or "critical"
        - risk_flags: List of flag identifiers
    """
    risk_flags = []
    now = datetime.now(timezone.utc)
    
    # Parse report_json if it's a string
    if isinstance(report_json, str):
        try:
            report_json = json.loads(report_json)
        except:
            report_json = None
    
    # Extract metrics from report
    commit_stats = report_json.get("commit_stats", {}) if isinstance(report_json, dict) else {}
    commit_details = report_json.get("commit_details", {}) if isinstance(report_json, dict) else {}
    all_commits = commit_details.get("all_commits", []) if isinstance(commit_details, dict) else []

    # Normalize contributors from multiple possible formats
    contributors_raw = None
    if isinstance(report_json, dict):
        contributors_raw = report_json.get("author_stats") or report_json.get("team")
    if not contributors_raw and isinstance(commit_details, dict):
        contributors_raw = commit_details.get("author_stats")

    contributors: List[Dict[str, Any]] = []
    if isinstance(contributors_raw, list):
        contributors = contributors_raw
    elif isinstance(contributors_raw, dict):
        for author, stats in contributors_raw.items():
            if isinstance(stats, dict):
                commit_count = stats.get("commit_count")
                if commit_count is None:
                    commit_count = stats.get("commits", 0)
            else:
                commit_count = stats
            contributors.append({"author": author, "commit_count": commit_count or 0})

    # Fallback commit stats if not present in report_json
    if not commit_stats and isinstance(report_json, dict):
        total_commits_fallback = commit_details.get("total_commits") or report_json.get("total_commits") or len(all_commits) or 0
        last_commit_str_fallback = None
        if all_commits:
            try:
                last_commit_str_fallback = max(
                    (c.get("date") for c in all_commits if c.get("date")),
                    default=None
                )
            except:
                last_commit_str_fallback = None

        commit_stats = {
            "total_commits": total_commits_fallback,
            "last_commit_date": last_commit_str_fallback,
            "commits_last_30_days": 0,
            "commits_last_7_days": 0
        }

        if all_commits:
            try:
                cutoff_30 = now - timedelta(days=30)
                cutoff_7 = now - timedelta(days=7)
                for commit in all_commits:
                    commit_date_str = commit.get("date")
                    if not commit_date_str:
                        continue
                    commit_date = datetime.fromisoformat(commit_date_str.replace("Z", "+00:00"))
                    if commit_date.tzinfo is None:
                        commit_date = commit_date.replace(tzinfo=timezone.utc)
                    if commit_date >= cutoff_30:
                        commit_stats["commits_last_30_days"] += 1
                    if commit_date >= cutoff_7:
                        commit_stats["commits_last_7_days"] += 1
            except:
                pass

    total_commits = commit_stats.get("total_commits", 0)
    last_commit_str = commit_stats.get("last_commit_date")
    
    # Calculate days since last commit
    days_since_commit = 999
    if last_commit_str:
        try:
            last_commit = datetime.fromisoformat(last_commit_str.replace("Z", "+00:00"))
            if last_commit.tzinfo is None:
                last_commit = last_commit.replace(tzinfo=timezone.utc)
            days_since_commit = (now - last_commit).days
        except:
            pass
    elif last_activity:
        try:
            last_act = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
            if last_act.tzinfo is None:
                last_act = last_act.replace(tzinfo=timezone.utc)
            days_since_commit = (now - last_act).days
        except:
            pass
    
    # === Risk Flag Detection ===
    
    # Ghost repo - no commits ever or repository unavailable
    if total_commits == 0 and not last_commit_str and not last_activity:
        risk_flags.append("ghost_repo")
    
    # Stale - no commits in >21 days
    if days_since_commit > 21:
        risk_flags.append("stale")
    elif days_since_commit > 7:
        risk_flags.append("inactive")
    
    # Contribution imbalance
    if contributors and len(contributors) > 0:
        total_contributor_commits = sum(c.get("commit_count", 0) for c in contributors)
        if total_contributor_commits > 0:
            top_contributor_commits = max(c.get("commit_count", 0) for c in contributors)
            top_contribution_pct = (top_contributor_commits / total_contributor_commits) * 100
            
            if top_contribution_pct > 70:
                risk_flags.append("imbalanced")
            
            # Solo project - only 1 contributor on team of 3+
            active_contributors = len([c for c in contributors if c.get("commit_count", 0) > 0])
            if active_contributors == 1 and team_members_count >= 3:
                risk_flags.append("solo_project")
            
            # Low participation - less than 50% of team contributed
            if team_members_count > 0:
                participation_rate = active_contributors / team_members_count
                if participation_rate < 0.5:
                    risk_flags.append("low_participation")
    
    # Check commit velocity (commits in last 30 days vs total)
    recent_commits = commit_stats.get("commits_last_30_days", 0)
    if total_commits > 20 and recent_commits < 5:
        risk_flags.append("declining_velocity")
    
    # No recent growth - very few commits in last 30 days
    if total_commits > 0 and recent_commits < 3:
        risk_flags.append("no_recent_growth")
    
    # Cramming - most commits very recent (deadline rush)
    commits_last_7_days = commit_stats.get("commits_last_7_days", 0)
    if total_commits >= 10 and commits_last_7_days > 0:
        if (commits_last_7_days / total_commits) > 0.7:
            risk_flags.append("cramming")
    
    # === Determine Health Status ===
    
    critical_flags = {"ghost_repo", "stale", "solo_project"}
    medium_flags = {"inactive", "imbalanced", "low_participation", "declining_velocity", "cramming"}
    
    critical_count = len([f for f in risk_flags if f in critical_flags])
    medium_count = len([f for f in risk_flags if f in medium_flags])
    
    if critical_count > 0:
        health_status = "critical"
    elif medium_count >= 2:
        health_status = "at_risk"
    elif medium_count == 1 or days_since_commit > 7:
        health_status = "at_risk"
    else:
        health_status = "on_track"
    
    return health_status, risk_flags


def get_risk_flag_display(flag: str) -> Dict[str, str]:
    """
    Get display information for a risk flag.
    
    Returns dict with keys: label, icon, severity, description
    """
    flags_info = {
        "inactive": {
            "label": "Inactive",
            "icon": "🟡",
            "severity": "medium",
            "description": "No commits in 8-14 days"
        },
        "stale": {
            "label": "Stale",
            "icon": "🔴",
            "severity": "high",
            "description": "No commits in over 21 days"
        },
        "ghost_repo": {
            "label": "Ghost Repository",
            "icon": "⚫",
            "severity": "critical",
            "description": "No commits ever or repository unavailable"
        },
        "imbalanced": {
            "label": "Imbalanced",
            "icon": "⚠️",
            "severity": "medium",
            "description": "Top contributor has >70% of commits"
        },
        "solo_project": {
            "label": "Solo Project",
            "icon": "🔴",
            "severity": "high",
            "description": "Only 1 contributor on a team of 3+"
        },
        "low_participation": {
            "label": "Low Participation",
            "icon": "🟡",
            "severity": "medium",
            "description": "Less than 50% of team has committed"
        },
        "no_recent_growth": {
            "label": "No Recent Growth",
            "icon": "🟡",
            "severity": "medium",
            "description": "Very few commits in last 30 days"
        },
        "cramming": {
            "label": "Cramming",
            "icon": "⚠️",
            "severity": "medium",
            "description": "70%+ of commits in last 7 days (deadline rush)"
        },
        "declining_velocity": {
            "label": "Declining Velocity",
            "icon": "🟡",
            "severity": "medium",
            "description": "Commit rate dropped significantly"
        },
    }
    
    return flags_info.get(flag, {
        "label": flag.replace("_", " ").title(),
        "icon": "🔵",
        "severity": "info",
        "description": "Unknown flag"
    })
