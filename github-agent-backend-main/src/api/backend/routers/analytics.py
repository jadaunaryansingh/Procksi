"""
Team Analytics API endpoints.
Provides detailed analytics, commit history, and file tree for teams.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
import json
import httpx
import os

from ..middleware.auth import get_current_user, AuthUser
from ..database import get_supabase_admin_client, get_supabase
from ..schemas import (
    TeamAnalyticsResponse,
    TeamCommitsResponse,
    TeamFileTreeResponse,
    CommitDetail
)
from ..services.frontend_adapter import FrontendAdapter
from ..utils.health import calculate_team_health, get_risk_flag_display
from ..utils.contributor_identity import TeamMemberIdentityResolver
from ..utils.report_storage import ReportStorageManager

router = APIRouter(prefix="/api/teams", tags=["analytics"])


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            dt = value
        elif value.endswith("Z"):
            value = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(value)
        else:
            dt = datetime.fromisoformat(value)
            
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _format_relative_time(dt: Optional[datetime], now: datetime) -> str:
    if not dt:
        return "Unknown"
    delta = now - dt
    if delta.total_seconds() < 0:
        return dt.strftime("%Y-%m-%d")
    if delta.days == 0:
        hours = max(1, int(delta.total_seconds() // 3600))
        return f"{hours} hours ago"
    if delta.days == 1:
        return "1 day ago"
    if delta.days < 7:
        return f"{delta.days} days ago"
    weeks = delta.days // 7
    if weeks < 5:
        return f"{weeks} weeks ago"
    return dt.strftime("%Y-%m-%d")


def _calculate_current_streak(active_days: List[str]) -> int:
    if not active_days:
        return 0
    days = sorted({datetime.fromisoformat(d).date() for d in active_days if d})
    if not days:
        return 0
    streak = 1
    for i in range(len(days) - 1, 0, -1):
        if (days[i] - days[i - 1]).days == 1:
            streak += 1
        else:
            break
    return streak


def _language_color(name: str) -> str:
    color_map = {
        "typescript": "#3178c6",
        "javascript": "#f7df1e",
        "python": "#3572A5",
        "css": "#264de4",
        "html": "#e34c26",
        "java": "#b07219",
        "go": "#00ADD8",
        "rust": "#dea584",
        "c#": "#178600",
        "c++": "#f34b7d",
        "c": "#555555",
        "php": "#4F5D95",
        "ruby": "#701516"
    }
    return color_map.get(name.lower(), "#6b7280")


def _extract_language_breakdown(report_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    lang_data = report_json.get("languages")
    breakdown: List[Dict[str, Any]] = []

    if isinstance(lang_data, dict):
        for name, pct in lang_data.items():
            breakdown.append({
                "name": name,
                "value": round(float(pct), 2),
                "color": _language_color(name)
            })
    elif isinstance(lang_data, list):
        for item in lang_data:
            if isinstance(item, dict):
                name = item.get("name") or item.get("language") or "Unknown"
                value = item.get("percentage") or item.get("value") or 0
                breakdown.append({
                    "name": name,
                    "value": round(float(value), 2),
                    "color": _language_color(name)
                })

    if not breakdown:
        stack = report_json.get("stack", [])
        if isinstance(stack, str):
            stack = [s.strip() for s in stack.split(",") if s.strip()]

        if isinstance(stack, list) and stack:
            language_keywords = [
                "python", "javascript", "typescript", "java", "go", "rust",
                "c++", "cpp", "c#", "php", "ruby", "swift", "kotlin"
            ]
            language_candidates = [
                item for item in stack
                if isinstance(item, str) and any(k in item.lower() for k in language_keywords)
            ]
            selected = language_candidates or [item for item in stack if isinstance(item, str)]

            if selected:
                pct = round(100 / len(selected), 2)
                for name in selected:
                    breakdown.append({
                        "name": name,
                        "value": pct,
                        "color": _language_color(name)
                    })

    return breakdown


def _split_feedback(text: str) -> List[str]:
    if not text:
        return []
    parts = text.replace("\n-", ".").replace("\n*", ".").replace("\n", ". ").split(".")
    items = [p.strip() for p in parts if p.strip() and len(p.strip()) > 10]
    return items[:5]


async def verify_team_access(team_id: str, current_user: AuthUser, supabase):
    """
    Verify user has access to the team.
    Admin has access to all teams, mentors only to assigned teams.
    """
    role = current_user.role
    user_id = str(current_user.user_id)
    
    # Get team details
    team_response = supabase.table("teams").select("*").eq("id", team_id).execute()
    if not team_response.data:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = team_response.data[0]
    
    # Admin has access to all teams
    if role == "admin":
        return team
    
    # Mentor can only access assigned teams
    if role == "mentor":
        if str(team.get("mentor_id")) != user_id:
            assignment = supabase.table("mentor_team_assignments").select("id").eq(
                "mentor_id", user_id
            ).eq("team_id", team_id).limit(1).execute()
            if not assignment.data:
                raise HTTPException(
                    status_code=403, 
                    detail="Access denied. You can only view teams assigned to you."
                )
        return team
    
    raise HTTPException(status_code=403, detail="Access denied")


@router.get("/{teamId}/analytics", response_model=TeamAnalyticsResponse)
async def get_team_analytics(
    teamId: str = Path(..., description="Team ID"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get comprehensive analytics for a team.
    Admin or assigned mentor only.
    OPTIMIZED: Added caching for 5-minute TTL.
    """
    from ..utils.cache import cache, RedisCache
    
    # Check cache first (analytics are expensive to compute)
    cache_key = f"hackeval:analytics:{teamId}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result
    
    supabase = get_supabase_admin_client()
    
    # Verify access
    team = await verify_team_access(teamId, current_user, supabase)

    # Load registered students for canonical contributor identity mapping.
    students_response = supabase.table("students").select(
        "id, name, email, github_username"
    ).eq("team_id", teamId).execute()
    students = students_response.data or []
    resolver = TeamMemberIdentityResolver(students)
    
    # Check if team has been analyzed (status should be 'completed')
    if not team.get("status") or team.get("status") == "pending":
        # Team hasn't been analyzed yet
        return {
            "teamId": teamId,
            "teamName": team["team_name"],
            "batchId": team["batch_id"],
            "analysis": {
                "totalScore": 0,
                "qualityScore": 0,
                "securityScore": 0,
                "originalityScore": 0,
                "architectureScore": 0,
                "documentationScore": 0
            },
            "commits": {
                "total": 0,
                "lastWeek": 0,
                "contributionDistribution": [],
                "timeline": [],
                "burstDetected": False,
                "lastMinuteCommits": 0
            },
            "codeMetrics": {
                "totalFiles": 0,
                "totalLinesOfCode": 0,
                "languages": [],
                "techStack": [],
                "architecturePattern": "Unknown"
            },
            "security": {
                "score": 0,
                "issues": [],
                "secretsDetected": 0
            },
            "aiAnalysis": {
                "aiGeneratedPercentage": 0,
                "verdict": "Not analyzed",
                "strengths": [],
                "improvements": []
            },
            "healthStatus": team.get("health_status", "on_track"),
            "riskFlags": team.get("risk_flags", []),
            "lastAnalyzedAt": None,
            "repoUrl": team.get("repo_url"),
            "createdAt": team.get("created_at"),
            "totalCommits": 0,
            "totalAdditions": 0,
            "totalDeletions": 0,
            "activeDays": 0,
            "avgCommitsPerDay": 0,
            "contributors": [],
            "commitActivity": [],
            "hourlyActivity": [],
            "teamContributionData": [],
            "recentActivities": [],
            "warnings": [],
            "languageBreakdown": []
        }
    
    # Use team data directly (analysis results are now in teams table)
    project = team
    
    # Fetch report from storage if migrated, otherwise from database
    report_json = ReportStorageManager.get_report_for_team(project)
    
    # Fallback to analysis_result if report_json is empty
    if not report_json:
        analysis_result = project.get("analysis_result") or {}
        if isinstance(analysis_result, str):
            try:
                report_json = json.loads(analysis_result)
            except Exception:
                report_json = {}
        elif isinstance(analysis_result, dict):
            report_json = analysis_result

    scores = FrontendAdapter._extract_scores(project, report_json)

    commit_details = report_json.get("commit_details", {}) or {}
    all_commits = commit_details.get("all_commits", []) or []

    now = datetime.now(timezone.utc)
    daily_counts: Dict[str, int] = {}
    hourly_counts: Dict[str, int] = {f"{h:02d}:00": 0 for h in range(24)}
    weekly_counts: Dict[str, Dict[str, int]] = {}
    author_totals: Dict[str, Dict[str, Any]] = {}
    author_daily_counts: Dict[str, Dict[str, int]] = {}

    total_additions = 0
    total_deletions = 0

    for commit in all_commits:
        commit_dt = _parse_datetime(commit.get("date"))
        if not commit_dt:
            continue
        if commit_dt.tzinfo is None:
            commit_dt = commit_dt.replace(tzinfo=timezone.utc)

        day_key = commit_dt.date().isoformat()
        hour_key = f"{commit_dt.hour:02d}:00"
        week_key = f"{commit_dt.isocalendar().year}-W{commit_dt.isocalendar().week:02d}"

        daily_counts[day_key] = daily_counts.get(day_key, 0) + 1
        hourly_counts[hour_key] = hourly_counts.get(hour_key, 0) + 1

        if week_key not in weekly_counts:
            weekly_counts[week_key] = {"commits": 0, "additions": 0, "deletions": 0}
        weekly_counts[week_key]["commits"] += 1

        additions = int(commit.get("additions", 0) or 0)
        deletions = int(commit.get("deletions", 0) or 0)
        total_additions += additions
        total_deletions += deletions
        weekly_counts[week_key]["additions"] += additions
        weekly_counts[week_key]["deletions"] += deletions

        raw_author = commit.get("author") or "Unknown"
        raw_email = commit.get("email") or ""
        member = resolver.resolve_member(raw_author, raw_email)
        author = resolver.resolve_name(raw_author, raw_email)
        email = (member.get("email") if member and member.get("email") else raw_email) or ""
        if author not in author_totals:
            author_totals[author] = {
                "name": author,
                "email": email,
                "commits": 0,
                "additions": 0,
                "deletions": 0,
                "active_days": set(),
                "last_active": commit_dt,
                "top_file_types": []
            }
        author_totals[author]["commits"] += 1
        author_totals[author]["additions"] += additions
        author_totals[author]["deletions"] += deletions
        author_totals[author]["active_days"].add(day_key)
        if commit_dt > author_totals[author]["last_active"]:
            author_totals[author]["last_active"] = commit_dt

        if author not in author_daily_counts:
            author_daily_counts[author] = {}
        author_daily_counts[author][day_key] = author_daily_counts[author].get(day_key, 0) + 1

    total_commits = len(all_commits) or commit_details.get("total_commits") or report_json.get("total_commits") or 0
    active_days = len(daily_counts)
    avg_commits_per_day = round((total_commits / active_days), 1) if active_days > 0 else 0


    week_cutoff = now - timedelta(days=7)
    last_week_commits = sum(
        count for day, count in daily_counts.items()
        if _parse_datetime(day) and _parse_datetime(day).replace(tzinfo=timezone.utc) >= week_cutoff
    )

    timeline = []
    for i in range(30):
        day = (now - timedelta(days=(29 - i))).date().isoformat()
        timeline.append({
            "date": day,
            "commits": daily_counts.get(day, 0),
            "additions": 0,
            "deletions": 0
        })

    contribution_distribution = []
    for author, stats in author_totals.items():
        commits_count = stats.get("commits", 0)
        percentage = round((commits_count / total_commits) * 100, 2) if total_commits > 0 else 0
        contribution_distribution.append({
            "contributorName": author,
            "commits": commits_count,
            "percentage": percentage,
            "additions": stats.get("additions", 0),
            "deletions": stats.get("deletions", 0)
        })

    contribution_distribution.sort(key=lambda x: x["commits"], reverse=True)

    commit_activity = [
        {
            "week": week,
            "commits": data["commits"],
            "additions": data["additions"],
            "deletions": data["deletions"]
        }
        for week, data in sorted(weekly_counts.items())
    ]

    hourly_activity = [{"hour": hour, "commits": hourly_counts[hour]} for hour in sorted(hourly_counts.keys())]

    team_contribution_data = [{"date": day, "count": count} for day, count in daily_counts.items()]

    commit_details_stats = commit_details.get("author_stats", {}) or {}
    contributors = []
    for author, stats in author_totals.items():
        active_day_list = sorted(stats["active_days"])
        last_active_dt = stats.get("last_active")
        top_file_types = []
        author_stat = commit_details_stats.get(author, {})
        if author_stat.get("top_file_types"):
            for item in author_stat["top_file_types"].split(","):
                try:
                    parts = item.strip().split('(')
                    name = parts[0].strip()
                    count = 0
                    if len(parts) > 1:
                        count_str = parts[1].replace(')', '').strip()
                        count = int(count_str) if count_str.isdigit() else 0
                    
                    if name and name != "no_ext":
                        # Clean name: remove leading dot and uppercase
                        name = name.lstrip('.').upper()
                        top_file_types.append({"name": name, "count": count})
                except Exception:
                    continue
                    
        if not top_file_types:
            top_file_types = [{"name": "UNKNOWN", "count": 0}]

        contributor_total = stats.get("commits", 0)
        active_days_count = len(stats["active_days"])
        avg_per_day = round((contributor_total / active_days_count), 1) if active_days_count > 0 else 0

        contributors.append({
            "name": author,
            "email": stats.get("email") or f"{author.replace(' ', '.').lower()}@unknown",
            "commits": contributor_total,
            "additions": stats.get("additions", 0),
            "deletions": stats.get("deletions", 0),
            "percentage": round((contributor_total / total_commits) * 100, 1) if total_commits > 0 else 0,
            "activeDays": active_days_count,
            "avgCommitsPerDay": avg_per_day,
            "topFileTypes": top_file_types,
            "contributionData": [
                {"date": day, "count": count}
                for day, count in author_daily_counts.get(author, {}).items()
            ],
            "lastActive": _format_relative_time(last_active_dt, now),
            "streak": _calculate_current_streak(active_day_list)
        })

    contributors.sort(key=lambda x: x["commits"], reverse=True)

    warnings = []
    if total_commits > 0 and daily_counts:
        sorted_days = sorted(daily_counts.items())
        last_days = sorted_days[int(len(sorted_days) * 0.8):]
        recent_commits = sum(count for _, count in last_days)
        if recent_commits / total_commits >= 0.5:
            warnings.append({
                "type": "burst",
                "message": f"{round(recent_commits / total_commits * 100)}% of commits were made recently",
                "severity": "medium"
            })

    for contributor in contributors:
        last_active_str = contributor.get("lastActive")
        if "days ago" in last_active_str:
            days = int(last_active_str.split(" ")[0])
            if days >= 7:
                warnings.append({
                    "type": "inactive",
                    "message": f"{contributor['name']} hasn't committed in {days} days",
                    "severity": "low" if days < 14 else "medium"
                })

    if commit_details.get("dummy_commits", 0) > 0:
        warnings.append({
            "type": "dummy",
            "message": f"{commit_details.get('dummy_commits')} empty commits detected",
            "severity": "low"
        })

    if commit_details.get("suspicious_list"):
        warnings.append({
            "type": "suspicious",
            "message": f"{len(commit_details.get('suspicious_list', []))} suspicious commits detected",
            "severity": "medium"
        })

    recent_activities = []
    for commit in sorted(all_commits, key=lambda x: x.get("date", ""), reverse=True)[:20]:
        commit_dt = _parse_datetime(commit.get("date"))
        recent_activities.append({
            "id": commit.get("hash") or commit.get("short_hash") or commit.get("date") or "",
            "type": "commit",
            "title": commit.get("message") or "Commit",
            "description": None,
            "author": commit.get("author") or "Unknown",
            "date": _format_relative_time(commit_dt, now) if commit_dt else "Unknown",
            "metadata": {
                "additions": commit.get("additions", 0),
                "deletions": commit.get("deletions", 0),
                "files": len(commit.get("files_changed", [])) if commit.get("files_changed") else None
            }
        })

    for branch_name in (commit_details.get("branches", []) or [])[:10]:
        recent_activities.append({
            "id": f"branch-{branch_name}",
            "type": "branch",
            "title": f"Branch: {branch_name}",
            "description": "Branch activity detected",
            "author": "System",
            "date": "Unknown",
            "metadata": None
        })

    judge_data = report_json.get("judge", {}) if isinstance(report_json, dict) else {}
    constructive = judge_data.get("constructive_feedback") if isinstance(judge_data, dict) else None
    if constructive:
        recent_activities.append({
            "id": "review-feedback",
            "type": "comment",
            "title": "Review feedback",
            "description": str(constructive)[:240],
            "author": "AI Reviewer",
            "date": _format_relative_time(_parse_datetime(project.get("created_at")), now),
            "metadata": None
        })

    language_breakdown = _extract_language_breakdown(report_json)

    languages = [
        {"name": item.get("name"), "percentage": item.get("value")}
        for item in language_breakdown
    ] if language_breakdown else []

    tech_stack = report_json.get("stack", []) if isinstance(report_json.get("stack", []), list) else []

    security_data = report_json.get("security", {}) if isinstance(report_json, dict) else {}
    security_issues = []
    if security_data.get("leaked_keys"):
        for leak in security_data.get("leaked_keys", []):
            security_issues.append({
                "type": leak.get("type", "Unknown"),
                "severity": "high",
                "file": leak.get("file", ""),
                "line": leak.get("line", 0),
                "description": "Secret detected"
            })
    
    # Build response
    judge_data = report_json.get("judge", {}) if isinstance(report_json, dict) else {}
    positive_feedback = judge_data.get("positive_feedback", "") if isinstance(judge_data, dict) else ""
    constructive_feedback = judge_data.get("constructive_feedback", "") if isinstance(judge_data, dict) else ""
    strengths = _split_feedback(positive_feedback)
    improvements = _split_feedback(constructive_feedback)
    
    # Calculate health status in real-time for accuracy
    health_status, risk_flags = calculate_team_health(
        report_json=report_json,
        team_members_count=len(contributors) if contributors else 4,
        last_activity=team.get("last_activity"),
        created_at=team.get("created_at")
    )
    
    # Format risk flags with display info
    risk_flags_display = [
        {
            "flag": flag,
            **get_risk_flag_display(flag)
        }
        for flag in risk_flags
    ]

    result = {
        "teamId": teamId,
        "teamName": team["team_name"],
        "batchId": team["batch_id"],
        "analysis": {
            "totalScore": scores.get("totalScore", 0),
            "qualityScore": scores.get("qualityScore", 0),
            "securityScore": scores.get("securityScore", 0),
            "originalityScore": scores.get("originalityScore", 0),
            "architectureScore": scores.get("architectureScore", 0),
            "documentationScore": scores.get("documentationScore", 0)
        },
        "commits": {
            "total": total_commits,
            "lastWeek": last_week_commits,
            "contributionDistribution": contribution_distribution,
            "timeline": timeline,
            "burstDetected": any(warning.get("type") == "burst" for warning in warnings),
            "lastMinuteCommits": 0
        },
        "codeMetrics": {
            "totalFiles": len(report_json.get("files", [])) if isinstance(report_json.get("files"), list) else 0,
            "totalLinesOfCode": sum(f.get("lines", 0) for f in report_json.get("files", [])) if isinstance(report_json.get("files"), list) else 0,
            "languages": languages,
            "techStack": tech_stack,
            "architecturePattern": report_json.get("structure", {}).get("architecture", "Unknown") if isinstance(report_json.get("structure"), dict) else "Unknown"
        },
        "security": {
            "score": scores.get("securityScore", 0),
            "issues": security_issues,
            "secretsDetected": len(security_data.get("leaked_keys", [])) if isinstance(security_data, dict) else 0
        },
        "aiAnalysis": {
            "aiGeneratedPercentage": report_json.get("llm_detection", {}).get("overall_percentage", 0) if isinstance(report_json.get("llm_detection"), dict) else 0,
            "verdict": judge_data.get("verdict", "Unknown") if isinstance(judge_data, dict) else "Unknown",
            "strengths": strengths,
            "improvements": improvements
        },
        "healthStatus": health_status,
        "riskFlags": risk_flags_display,
        "lastAnalyzedAt": project.get("created_at"),
        "repoUrl": project.get("repo_url") or team.get("repo_url"),
        "createdAt": team.get("created_at") or project.get("created_at"),
        "totalCommits": total_commits,
        "totalAdditions": total_additions,
        "totalDeletions": total_deletions,
        "activeDays": active_days,
        "avgCommitsPerDay": avg_commits_per_day,
        "contributors": contributors,
        "commitActivity": commit_activity,
        "hourlyActivity": hourly_activity,
        "teamContributionData": team_contribution_data,
        "recentActivities": recent_activities,
        "warnings": warnings,
        "languageBreakdown": language_breakdown
    }
    
    # Cache result for 5 minutes (balances freshness with performance)
    cache.set(cache_key, result, RedisCache.TTL_MEDIUM)
    
    return result


@router.get("/{teamId}/commits", response_model=TeamCommitsResponse)
async def get_team_commits(
    teamId: str = Path(..., description="Team ID"),
    author: Optional[str] = Query(None, description="Filter by contributor name"),
    startDate: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    endDate: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="Page number"),
    pageSize: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get commit history for a team with optional filters.
    Admin or assigned mentor only.
    """
    supabase = get_supabase_admin_client()
    
    # Verify access
    team = await verify_team_access(teamId, current_user, supabase)
    
    # Check if team has been analyzed
    if not team.get("status") or team.get("status") == "pending":
        return {
            "commits": [],
            "total": 0,
            "page": page,
            "pageSize": pageSize
        }
    
    # Use team data directly (analysis results are now in teams table)
    project = team
    
    # Fetch report from storage if migrated
    report = ReportStorageManager.get_report_for_team(project)
    
    # Fallback to analysis_result if empty
    if not report:
        analysis_result = project.get("analysis_result")
        if isinstance(analysis_result, str):
            try:
                report = json.loads(analysis_result)
            except:
                report = {}
        elif isinstance(analysis_result, dict):
            report = analysis_result
        else:
            report = {}
            
    if not report:
         return {
            "commits": [],
            "total": 0,
            "page": page,
            "pageSize": pageSize
        }

    # Extract commits from report
    commit_details = report.get("commit_details", {})
    all_commits_data = commit_details.get("all_commits", [])
    
    # Fallback to forensics if commit_details not found
    if not all_commits_data:
        # Try finding in forensics or other locations if needed
        pass

    # Filter by author if provided
    if author:
        all_commits_data = [c for c in all_commits_data if c.get("author") == author]

    # Filter by date if provided
    if startDate:
        all_commits_data = [c for c in all_commits_data if c.get("date") and c.get("date") >= startDate]
    if endDate:
        all_commits_data = [c for c in all_commits_data if c.get("date") and c.get("date") <= endDate]

    # Sort by date descending (assuming ISO format)
    # They usually come sorted from git, but good to ensure
    all_commits_data.sort(key=lambda x: x.get("date", ""), reverse=True)

    # Check total before pagination
    total_commits = len(all_commits_data)
    
    # Pagination
    start_idx = (page - 1) * pageSize
    end_idx = start_idx + pageSize
    paginated_commits = all_commits_data[start_idx:end_idx]
    
    # Map to response schema
    result_commits = []
    for c in paginated_commits:
        files_changed = c.get("files_changed", [])
        files_count = len(files_changed) if isinstance(files_changed, list) else 0
        
        result_commits.append({
            "sha": c.get("hash", ""),
            "author": c.get("author", "Unknown"),
            "authorEmail": c.get("email", ""),
            "message": c.get("message", ""),
            "date": c.get("date", ""),
            "additions": c.get("additions", 0),
            "deletions": c.get("deletions", 0),
            "filesChanged": files_count,
            "files": [
                {
                    "file": f.get("file") or f.get("path", ""),
                    "additions": f.get("additions", 0),
                    "deletions": f.get("deletions", 0)
                } for f in files_changed
            ] if isinstance(files_changed, list) else []
        })

    return {
        "commits": result_commits,
        "total": total_commits,
        "page": page,
        "pageSize": pageSize
    }
    



@router.get("/{teamId}/file-tree", response_model=TeamFileTreeResponse)
async def get_team_file_tree(
    teamId: str = Path(..., description="Team ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get repository file tree structure.
    Admin or assigned mentor only.
    """
    supabase = get_supabase_admin_client()
    
    # Verify access
    team = await verify_team_access(teamId, current_user, supabase)
    
    # Check if team has been analyzed
    if not team.get("status") or team.get("status") == "pending":
        return {
            "tree": [],
            "totalFiles": 0,
            "totalSize": 0
        }
    
    # Use team data directly (analysis results are now in teams table)
    project = team
    
    # Fetch report from storage if migrated
    report = ReportStorageManager.get_report_for_team(project)
    
    # Fallback to analysis_result
    if not report:
        analysis_result = project.get("analysis_result")
        if isinstance(analysis_result, str):
            try:
                report = json.loads(analysis_result)
            except:
                report = {}
        elif isinstance(analysis_result, dict):
            report = analysis_result
        else:
            report = {}

    structure = report.get("structure", {}) if isinstance(report.get("structure"), dict) else {}

    # In a real implementation, this would build from actual file data
    # For now, create a simplified tree structure from languages
    languages = (
        report.get("languages")
        or report.get("codeMetrics", {}).get("languages")
        or report.get("code_metrics", {}).get("languages")
        or []
    )
    if isinstance(languages, dict):
        languages = [
            {"language": name, "percentage": pct}
            for name, pct in languages.items()
        ]
    if not isinstance(languages, list):
        languages = []
    total_files = (
        structure.get("file_count")
        or report.get("totalFiles")
        or report.get("codeMetrics", {}).get("totalFiles")
        or report.get("code_metrics", {}).get("totalFiles")
        or 0
    )
    total_loc = (
        structure.get("loc")
        or report.get("totalLinesOfCode")
        or report.get("codeMetrics", {}).get("totalLinesOfCode")
        or report.get("code_metrics", {}).get("totalLinesOfCode")
        or 0
    )
    
    def _parse_repo_tree(tree_text: str):
        if not tree_text or not isinstance(tree_text, str):
            return [], 0
        if "Tree structure unavailable" in tree_text or "Tree generation failed" in tree_text or "Tree generation skipped" in tree_text:
            return [], 0

        lines = [line for line in tree_text.splitlines() if line.strip()]
        nodes = []
        stack = []
        file_count = 0

        for line in lines:
            if "... (" in line and "more files" in line:
                continue

            depth = line.count("│   ")
            cleaned = line.replace("│   ", "")
            cleaned = cleaned.replace("├── ", "")
            cleaned = re.sub(r"^[^A-Za-z0-9_\.\-]+", "", cleaned).strip()
            if not cleaned:
                continue

            is_dir = cleaned.endswith("/")
            name = cleaned[:-1] if is_dir else cleaned

            parent_path = ""
            if depth - 1 >= 0 and depth - 1 < len(stack):
                parent_path = stack[depth - 1]["path"]

            node_path = f"{parent_path}/{name}" if parent_path else name
            node = {
                "path": node_path,
                "type": "directory" if is_dir else "file"
            }
            if is_dir:
                node["children"] = []

            if depth - 1 >= 0 and depth - 1 < len(stack):
                stack[depth - 1].setdefault("children", []).append(node)
            else:
                nodes.append(node)

            if is_dir:
                stack = stack[:depth]
                stack.append(node)
            else:
                file_count += 1

        if nodes and len(nodes) == 1 and nodes[0].get("type") == "directory":
            return nodes[0].get("children", []), file_count

        return nodes, file_count

    # Build simplified tree
    tree = []
    
    # Create src directory with language-based files
    src_children = []
    for lang_data in languages:
        lang = lang_data.get("language", "Unknown")
        percentage = lang_data.get("percentage", 0)
        file_count = int(total_files * percentage / 100)
        
        # Determine file extension
        ext_map = {
            "Python": ".py",
            "JavaScript": ".js",
            "TypeScript": ".ts",
            "Java": ".java",
            "C++": ".cpp",
            "Go": ".go",
            "Rust": ".rs"
        }
        ext = ext_map.get(lang, ".txt")
        
        for i in range(min(file_count, 5)):  # Limit for demo
            src_children.append({
                "path": f"src/module{i}{ext}",
                "type": "file",
                "size": 1024 * (i + 1),
                "language": lang
            })
    
    if src_children:
        tree.append({
            "path": "src",
            "type": "directory",
            "children": src_children
        })
    
    # Add README
    tree.append({
        "path": "README.md",
        "type": "file",
        "size": 2048,
        "language": "Markdown"
    })

    repo_tree_text = report.get("repo_tree") if isinstance(report, dict) else None
    parsed_tree, parsed_file_count = _parse_repo_tree(repo_tree_text)
    if parsed_tree:
        tree = parsed_tree

    def _count_tree(nodes):
        file_count = 0
        total_size = 0
        for node in nodes:
            if node.get("type") == "file":
                file_count += 1
                total_size += node.get("size") or 0
            for child in node.get("children") or []:
                child_count, child_size = _count_tree([child])
                file_count += child_count
                total_size += child_size
        return file_count, total_size

    tree_file_count, tree_size = _count_tree(tree)
    if not total_files:
        total_files = parsed_file_count or tree_file_count

    # Calculate total size (estimate) if needed
    total_size = total_loc * 50 if total_loc else tree_size
    
    return {
        "tree": tree,
        "totalFiles": total_files,
        "totalSize": total_size
    }

@router.get("/{teamId}/commits/{sha}/diff", response_model=CommitDetail)
async def get_team_commit_diff(
    teamId: str = Path(..., description="Team ID"),
    sha: str = Path(..., description="Commit SHA"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get detailed commit information including patches/diffs from GitHub.
    """
    supabase = get_supabase_admin_client()
    
    # Verify access
    team = await verify_team_access(teamId, current_user, supabase)
    
    repo_url = team.get("repo_url")
    if not repo_url:
        raise HTTPException(status_code=400, detail="Team has no repository URL")
        
    try:
        # Extract owner/repo from URL
        cleaned = repo_url.rstrip("/").replace(".git", "")
        if "github.com/" in cleaned:
            parts = cleaned.split("github.com/")[1].split("/")
            if len(parts) >= 2:
                repo_path = f"{parts[0]}/{parts[1]}"
            else:
                raise ValueError("Invalid GitHub URL format")
        elif "github.com:" in cleaned:
            parts = cleaned.split("github.com:")[1].split("/")
            if len(parts) >= 2:
                repo_path = f"{parts[0]}/{parts[1]}"
            else:
                repo_path = cleaned.split("github.com:")[1] # Fallback for simple git@ formats
        else:
            raise ValueError("Only GitHub repositories are supported for diff view")
            
        # Get GitHub token (prefer GH_API_KEY, fallback to GITHUB_TOKEN)
        gh_token = os.getenv("GH_API_KEY") or os.getenv("GITHUB_TOKEN")
            
        api_url = f"https://api.github.com/repos/{repo_path}/commits/{sha}"
        
        headers = {"Accept": "application/vnd.github.v3+json"}
        if gh_token:
            headers["Authorization"] = f"Bearer {gh_token}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                api_url,
                headers=headers,
                timeout=10.0
            )

            if response.status_code == 401 and gh_token:
                # Retry once without token for public repos
                response = await client.get(
                    api_url,
                    headers={"Accept": "application/vnd.github.v3+json"},
                    timeout=10.0
                )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code, 
                    detail=f"GitHub API error: {response.text}"
                )
                
            data = response.json()
            
            # Map GitHub response to our CommitDetail schema
            commit_info = data.get("commit", {})
            files = data.get("files", [])
            stats = data.get("stats", {})
            
            result = {
                "sha": sha,
                "author": commit_info.get("author", {}).get("name", "Unknown"),
                "authorEmail": commit_info.get("author", {}).get("email", ""),
                "message": commit_info.get("message", ""),
                "date": commit_info.get("author", {}).get("date", ""),
                "additions": stats.get("additions", 0) if isinstance(stats, dict) else 0,
                "deletions": stats.get("deletions", 0) if isinstance(stats, dict) else 0,
                "filesChanged": len(files),
                "files": [
                    {
                        "file": f.get("filename", ""),
                        "additions": f.get("additions", 0),
                        "deletions": f.get("deletions", 0),
                        "patch": f.get("patch")
                    } for f in files
                ]
            }
            
            # Recalculate stats if they are missing from GitHub
            if not result["additions"] and not result["deletions"] and files:
                result["additions"] = sum(f.get("additions", 0) for f in files)
                result["deletions"] = sum(f.get("deletions", 0) for f in files)
            
            return result
            
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to fetch commit diff: {str(e)}")
