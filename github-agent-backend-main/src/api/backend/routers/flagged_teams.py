"""
Flagged Teams API
Provides endpoints to view teams flagged for fake commits, suspicious activity, and other integrity issues.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Optional
import json

from src.api.backend.database import get_supabase_admin_client
from src.api.backend.middleware.auth import RoleChecker
from src.api.backend.utils.report_storage import ReportStorageManager

router = APIRouter(prefix="/api/flagged-teams", tags=["Flagged Teams"])


def _to_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_list(value: Any) -> list:
    return value if isinstance(value, list) else []


@router.get("/")
async def get_flagged_teams(
    batch_id: Optional[str] = Query(None, description="Filter by batch ID"),
    severity: Optional[str] = Query(None, description="Filter by severity: critical, warning, all"),
    _=Depends(RoleChecker(["admin"]))
):
    """
    Get all teams flagged for fake commits, outsourcing, or suspicious activity.
    Returns forensic details extracted from analysis report_json.
    
    Admin only.
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Query teams with report_json containing commit forensics
        query = supabase.table("teams").select(
            "id, team_name, batch_id, repo_url, health_status, risk_flags, "
            "total_commits, total_score, verdict, status, last_analyzed_at, report_json, report_path"
        )
        
        if batch_id:
            query = query.eq("batch_id", batch_id)
        
        # Only get teams that have been analyzed (either have report_path or report_json)
        # Note: After migration, report_json is NULL but report_path exists
        query = query.or_("report_json.not.is.null,report_path.not.is.null")
        
        result = query.execute()
        teams = result.data or []
        
        flagged_teams = []
        summary = {
            "total_flagged": 0,
            "critical": 0,
            "warning": 0,
            "fake_commit_teams": 0,
            "outsourcing_teams": 0,
            "suspicious_author_teams": 0,
        }
        
        for team in teams:
            # Fetch report from storage if migrated
            report = ReportStorageManager.get_report_for_team(team)
            commit_details = _to_dict(report.get("commit_details"))
            
            fake_count = _to_int(commit_details.get("fake_commit_count", 0), 0)
            fake_ratio = _to_float(commit_details.get("fake_commit_ratio", 0), 0.0)
            commit_health = commit_details.get("commit_health", "Unknown")
            inflation_ratio = _to_float(commit_details.get("inflation_ratio", 0), 0.0)
            total_commits = _to_int(team.get("total_commits", 0), 0)
            ai_bot_detection = _to_dict(commit_details.get("ai_bot_detection"))
            ai_bot_contributors = _to_list(ai_bot_detection.get("ai_bot_contributors", []))
            has_ai_bots = bool(ai_bot_detection.get("has_ai_bots")) or len(ai_bot_contributors) > 0
            
            # Determine flags
            flags = []
            flag_severity = "none"
            
            # Fake commits
            if fake_count > 0:
                if fake_ratio >= 50:
                    flags.append("high_fake_commits")
                    flag_severity = "critical"
                elif fake_ratio >= 20:
                    flags.append("moderate_fake_commits")
                    if flag_severity != "critical":
                        flag_severity = "warning"
            
            # Suspicious authors
            suspicious = _to_dict(commit_details.get("suspicious_authors"))
            has_suspicious = suspicious.get("has_suspicious", False)
            if has_suspicious:
                flags.append("suspicious_authors")
                flag_severity = "critical"

            # Automated/bot commit authors (e.g., github-actions) - always critical
            if has_ai_bots:
                flags.append("automated_commit_authors")
                flag_severity = "critical"
            
            # Contribution imbalance
            imbalance = _to_dict(commit_details.get("contribution_imbalance"))
            imbalance_severity = imbalance.get("severity", "none")
            if imbalance_severity in ("high", "critical"):
                flags.append("contribution_imbalance")
                if flag_severity != "critical":
                    flag_severity = "warning"
            
            # Generic commit messages
            generic_ratio = _to_float(commit_details.get("generic_message_ratio", 0), 0.0)
            if generic_ratio >= 80 and total_commits > 3:
                flags.append("generic_messages")
                if flag_severity != "critical":
                    flag_severity = "warning"
            
            # Whitespace-only commits
            whitespace = _to_int(commit_details.get("whitespace_only_count", 0), 0)
            if whitespace > 0:
                flags.append("whitespace_commits")
                if flag_severity != "critical":
                    flag_severity = "warning"
            
            # Commit flooding
            has_flooding = commit_details.get("has_commit_flooding", False)
            if has_flooding:
                flags.append("commit_flooding")
                if flag_severity != "critical":
                    flag_severity = "warning"
            
            # Critical commit health
            if commit_health == "Critical":
                if "high_fake_commits" not in flags:
                    flags.append("critical_commit_health")
                flag_severity = "critical"
            
            # Skip teams with no flags
            if not flags:
                continue
            
            # Apply severity filter
            if severity == "critical" and flag_severity != "critical":
                continue
            if severity == "warning" and flag_severity != "warning":
                continue
            
            # Build team member info from report
            team_info = _to_dict(report.get("team"))
            members = []
            if isinstance(team_info, dict):
                for author, stats in team_info.items():
                    if isinstance(stats, dict):
                        commits = _to_int(stats.get("commits", 0), 0)
                        lines = _to_int(stats.get("lines_changed", 0), 0)
                    else:
                        commits = _to_int(stats, 0)
                        lines = 0
                    members.append({
                        "name": author,
                        "commits": commits,
                        "lines_changed": lines,
                    })
            
            # Extract dummy/fake commit list (first 10)
            dummy_commits = _to_list(commit_details.get("dummy_commits", []))[:10]
            fake_commits_list = _to_list(commit_details.get("fake_commits", []))[:10]
            
            flagged_team = {
                "id": team.get("id"),
                "team_name": team.get("team_name"),
                "batch_id": team.get("batch_id"),
                "repo_url": team.get("repo_url"),
                "health_status": team.get("health_status"),
                "risk_flags": _to_list(team.get("risk_flags") or []),
                "total_commits": total_commits,
                "total_score": team.get("total_score"),
                "verdict": team.get("verdict"),
                "last_analyzed_at": team.get("last_analyzed_at"),
                "flag_severity": flag_severity,
                "flags": flags,
                "forensics": {
                    "fake_commit_count": fake_count,
                    "fake_commit_ratio": round(fake_ratio, 1),
                    "commit_health": commit_health,
                    "inflation_ratio": round(inflation_ratio, 4),
                    "generic_message_ratio": round(generic_ratio, 1),
                    "whitespace_only_count": whitespace,
                    "has_commit_flooding": has_flooding,
                    "suspicious_authors": _to_list(suspicious.get("suspicious_authors", [])),
                    "contribution_imbalance": imbalance,
                    "has_ai_bots": has_ai_bots,
                    "ai_bot_contributors": ai_bot_contributors,
                },
                "members": members,
                "sample_fake_commits": fake_commits_list or dummy_commits,
            }
            
            flagged_teams.append(flagged_team)
            
            # Update summary
            summary["total_flagged"] += 1
            if flag_severity == "critical":
                summary["critical"] += 1
            else:
                summary["warning"] += 1
            if fake_count > 0:
                summary["fake_commit_teams"] += 1
            if has_ai_bots:
                summary["outsourcing_teams"] += 1
            if has_suspicious:
                summary["suspicious_author_teams"] += 1
        
        # Sort: critical first, then by fake ratio descending
        flagged_teams.sort(
            key=lambda t: (
                0 if t["flag_severity"] == "critical" else 1,
                -(t["forensics"]["fake_commit_ratio"]),
            )
        )
        
        return {
            "summary": summary,
            "teams": flagged_teams,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch flagged teams: {str(e)}")
