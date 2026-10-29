"""
Reports API endpoints.
Generates comprehensive reports for batches, mentors, and teams.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from starlette.requests import Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
from typing import Optional
from datetime import datetime
import json
import io
import logging
import re

from ..middleware.auth import get_current_user
from ..database import get_supabase
from ..schemas import (
    BatchReportResponse,
    MentorReportResponse,
    TeamReportResponse
)
from ..utils.cache import cache, RedisCache
from ..utils.rate_limiter import limiter
from ..utils.contributor_identity import merge_contributors_by_team_members
from ..utils.student_report_fields import build_student_report_fields
from ..utils.report_storage import ReportStorageManager

logger = logging.getLogger("reports")
from ..utils.pdf_generator import generate_team_report_pdf
from ..utils.leaderboard_pdf_generator import generate_leaderboard_pdf
from ..utils.email import send_email_with_attachment
from ..services.leaderboard_service import LeaderboardService
from ..templates.email_templates import EmailTemplates
import asyncio

router = APIRouter(prefix="/api/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Score Insights helper – produces the same insights used in the PDF report
# so the JSON API response includes actionable improvement advice.
# ---------------------------------------------------------------------------
_LOW_SCORE_THRESHOLD = 50

def _safe_float(value, default: float = 0.0) -> float:
    """Convert *value* to float, returning *default* on failure."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def _generate_score_insights(report_data: dict) -> list:
    """Return **personalized** insight dicts for every scoring dimension below threshold.

    Reasons are derived from actual report data — not generic checklists.
    Dimensions with no supporting data are skipped entirely.
    """
    from ..utils.pdf_generator import TeamReportPDFGenerator

    insights_db = TeamReportPDFGenerator.SCORE_INSIGHTS_DB
    analysis = report_data.get("analysis", {})
    if not analysis:
        return []

    score_items = [
        ("Quality", analysis.get("qualityScore", 0)),
        ("Security", analysis.get("securityScore", 0)),
        ("Originality", analysis.get("originalityScore", 0)),
        ("Architecture", analysis.get("architectureScore", 0)),
        ("Documentation", analysis.get("documentationScore", 0)),
        ("Effort", analysis.get("effortScore", 0)),
        ("Implementation", analysis.get("implementationScore", 0)),
        ("Engineering", analysis.get("engineeringScore", 0)),
    ]

    insights = []
    for dimension, raw_score in score_items:
        score = _safe_float(raw_score, 0.0)
        if score >= _LOW_SCORE_THRESHOLD or score <= 0:
            continue

        db_entry = insights_db.get(dimension, {})
        if not db_entry:
            continue

        # Severity
        if score < 20:
            severity = "critical"
        elif score < 40:
            severity = "needs_work"
        else:
            severity = "fair"

        # ── Build PERSONALIZED reasons from actual report data ──
        reasons = []

        if dimension == "Security":
            sec = report_data.get("security", {})
            secrets = (sec.get("secretsDetected", 0)) or 0
            if secrets > 0:
                reasons.append(f"Your repository has {secrets} leaked secret(s)/credential(s)")
            leaks = sec.get("leaks") or sec.get("issues", [])
            if isinstance(leaks, list):
                for leak in leaks[:2]:
                    if isinstance(leak, dict):
                        desc = leak.get("description") or leak.get("type", "")
                        fpath = leak.get("file_path") or leak.get("file", "")
                        if desc and fpath:
                            reasons.append(f"Found: {desc} in {fpath}")
                        elif desc:
                            reasons.append(f"Issue: {desc}")
            recs = sec.get("recommendations", [])
            if isinstance(recs, list):
                for rec in recs[:2]:
                    if isinstance(rec, str) and rec.strip():
                        reasons.append(rec.strip())

        elif dimension == "Originality":
            ai = report_data.get("aiAnalysis", {})
            ai_pct = _safe_float(ai.get("aiGeneratedPercentage", 0), 0.0)
            if ai_pct > 30:
                reasons.append(f"{ai_pct:.0f}% of your code was flagged as AI-generated")
            verdict = ai.get("verdict", "")
            if verdict and "ai" in str(verdict).lower():
                reasons.append(f"AI verdict: {verdict}")
            risky = report_data.get("riskyFiles", [])
            high_ai = [f for f in risky if isinstance(f, dict) and _safe_float(f.get("ai_pct", 0), 0) > 60]
            for rf in high_ai[:2]:
                reasons.append(f'{rf.get("name", "?")} — {rf.get("ai_pct", 0):.0f}% AI-generated')

        elif dimension == "Effort":
            cq = report_data.get("commitQuality", {})
            total_c = cq.get("totalCommits", 0) or 0
            fake_c = cq.get("fakeCommits", 0) or 0
            fake_pct = _safe_float(cq.get("fakeCommitPercentage", 0), 0.0)
            health = cq.get("healthStatus", "")

            if total_c > 0 and total_c < 20:
                reasons.append(f"Only {total_c} total commits — very low development activity")
            if fake_pct > 10:
                reasons.append(f"{fake_pct:.0f}% of commits ({fake_c}/{total_c}) are fake/low-quality")
            if health and health != "Healthy":
                reasons.append(f"Commit health: {health}")

            contributors = report_data.get("commits", {}).get("contributors", [])
            if len(contributors) >= 2:
                pcts = sorted([_safe_float(c.get("contributionPct", 0), 0) for c in contributors], reverse=True)
                if pcts[0] > 70:
                    top = next((c.get("name", "?") for c in contributors
                                if _safe_float(c.get("contributionPct", 0), 0) == pcts[0]), "?")
                    reasons.append(f"Uneven contribution — {top} made {pcts[0]:.0f}% of all commits")

        elif dimension == "Implementation":
            ai = report_data.get("aiAnalysis", {})
            func_check = ai.get("functionalityCheck", {})
            completeness = ai.get("completenessAnalysis", {})
            constructive = ai.get("constructiveFeedback", "")

            if isinstance(func_check, dict):
                broken = func_check.get("brokenFeatures", []) or func_check.get("missingFeatures", [])
                working = func_check.get("workingFeatures", [])
                if isinstance(broken, list) and broken:
                    for feat in broken[:2]:
                        ft = feat if isinstance(feat, str) else feat.get("name", str(feat))
                        reasons.append(f"Missing/broken feature: {ft}")
                if isinstance(working, list):
                    reasons.append(f"{len(working)} feature(s) verified working, but gaps remain")

            if isinstance(completeness, dict):
                pct = completeness.get("completionPercentage", 0) or completeness.get("percentage", 0)
                if pct and pct < 60:
                    reasons.append(f"Only {pct}% of stated features appear complete")

            if constructive and not reasons:
                snippet = str(constructive)[:150].strip()
                if snippet:
                    reasons.append(f'AI feedback: "{snippet}…"')

        elif dimension == "Engineering":
            mat = report_data.get("maturity", {})
            if mat:
                if not mat.get("hasTests"):
                    reasons.append("No test files detected in your repository")
                elif mat.get("testFiles", 0) < 3:
                    reasons.append(f'Only {mat.get("testFiles", 0)} test file(s) found — very limited coverage')
                if not mat.get("hasCI"):
                    reasons.append("No CI/CD pipeline (GitHub Actions, etc.) configured")
                if not mat.get("hasDocker"):
                    reasons.append("No Docker/containerization setup found")

        elif dimension == "Documentation":
            mat = report_data.get("maturity", {})
            if mat and not mat.get("hasReadme"):
                reasons.append("No README file detected — this is critical")
            metrics = report_data.get("codeMetrics", {})
            if isinstance(metrics, dict):
                tf = metrics.get("totalFiles", 0) or 0
                if tf > 0 and tf < 5:
                    reasons.append(f"Very few files ({tf}) may indicate missing documentation files")

        elif dimension == "Architecture":
            metrics = report_data.get("codeMetrics", {})
            pattern = metrics.get("architecturePattern", "") if isinstance(metrics, dict) else ""
            if pattern and pattern.lower() in ("unknown", "none", ""):
                reasons.append("No recognizable architectural pattern detected")
            elif pattern:
                reasons.append(f"Detected pattern: {pattern} — but implementation is incomplete")

        elif dimension == "Quality":
            ai = report_data.get("aiAnalysis", {})
            qi = ai.get("qualityIndicators", {})
            if isinstance(qi, dict):
                for indicator, value in qi.items():
                    if isinstance(value, str) and len(value) < 120:
                        reasons.append(f"{indicator}: {value}")
                    if len(reasons) >= 3:
                        break
            metrics = report_data.get("codeMetrics", {})
            if isinstance(metrics, dict):
                loc = metrics.get("totalLinesOfCode", 0) or 0
                files = metrics.get("totalFiles", 0) or 0
                if files > 0 and loc / max(1, files) > 500:
                    reasons.append(f"Average {loc // max(1, files)} lines/file — files may be too large")

        # Fallback: only 1-2 generic tips if nothing personalized was found
        if not reasons:
            generic = db_entry.get("common_reasons", [])
            reasons = generic[:2]

        # Skip if we truly have nothing to say
        if not reasons:
            continue

        insights.append({
            "dimension": dimension,
            "score": round(score, 1),
            "severity": severity,
            "what_it_measures": db_entry.get("what_it_measures", ""),
            "likely_reasons": reasons[:4],
            "improvement_steps": db_entry.get("how_to_improve", [])[:4],
        })

    insights.sort(key=lambda x: x["score"])
    return insights

@router.get("/batch/{batchId}", response_model=BatchReportResponse)
async def get_batch_report(
    batchId: str = Path(..., description="Batch ID"),
    format: Optional[str] = Query("json", description="Format: json, pdf, or csv"),
    current_user: dict = Depends(get_current_user)
):
    """
    Generate batch-wide report.
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Check cache first (skip for CSV/PDF exports)
    if format == "json":
        cache_key = f"hackeval:report:batch:{batchId}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
    
    supabase = get_supabase()
    
    # Verify batch exists
    batch_response = supabase.table("batches").select("*").eq("id", batchId).execute()
    if not batch_response.data:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    batch = batch_response.data[0]
    
    # Get all teams in the batch - OPTIMIZED: No report_json, no students(*)
    # Fetch only required fields for leaderboard (90% IO reduction)
    teams_response = supabase.table("teams").select(
        "id, team_name, total_score, quality_score, security_score, originality_score, "
        "effort_score, implementation_score, engineering_score, organization_score, "
        "documentation_score, health_status, mentor_id, last_analyzed_at, students(name, email)"
    ).eq("batch_id", batchId).execute()
    
    teams = teams_response.data or []
    
    # Calculate summary statistics
    total_teams = len(teams)
    
    # Get scores from teams that have been analyzed
    scores = []
    teams_data = []
    
    for idx, team in enumerate(teams):
        # Use database columns directly instead of parsing JSON
        # This eliminates 300KB JSON.loads() per team (1000x speedup)
        total_score = team.get("total_score", 0) or 0
        
        if total_score > 0:
            scores.append(total_score)
        
        teams_data.append({
            "teamId": team["id"],
            "rank": idx + 1,  # Will be re-ranked after sorting
            "teamName": team["team_name"],
            "totalScore": total_score,
            "qualityScore": team.get("quality_score", 0) or 0,
            "securityScore": team.get("security_score", 0) or 0,
            "originalityScore": team.get("originality_score", 0) or 0,
            "architectureScore": team.get("implementation_score", 0) or 0,  # Map to frontend field
            "documentationScore": team.get("documentation_score", 0) or 0,
            "healthStatus": team.get("health_status", "on_track"),
            "mentorId": team.get("mentor_id"),
            "frameworks": [],  # Not needed for leaderboard summary
            "lastAnalyzed": team.get("last_analyzed_at")
        })
    
    # Sort teams by total score descending
    teams_data.sort(key=lambda x: x["totalScore"], reverse=True)
    
    # Update ranks
    for idx, team in enumerate(teams_data):
        team["rank"] = idx + 1
    
    # Calculate summary
    average_score = sum(scores) / len(scores) if scores else 0
    top_team = teams_data[0] if teams_data else None
    
    # Get most used technologies
    all_frameworks = []
    total_ai_usage = []
    
    for team_data in teams_data:
        frameworks = team_data.get("frameworks", [])
        if isinstance(frameworks, list):
            all_frameworks.extend(frameworks)
    
    # Count framework occurrences
    framework_counts = {}
    for fw in all_frameworks:
        framework_counts[fw] = framework_counts.get(fw, 0) + 1
    
    most_used_tech = max(framework_counts, key=framework_counts.get) if framework_counts else "Unknown"
    
    # AI usage and security issues - query from columns if available
    # TODO: Add ai_percentage and security_issues_count columns to teams table
    # For now, skip these expensive operations in leaderboard (not critical)
    average_ai_usage = 0
    total_security_issues = 0
    
    # NOTE: Previously parsed analysis_result JSON in loop (expensive!)
    # Now skipped for performance - add columns to teams table if needed:
    # ALTER TABLE teams ADD COLUMN ai_percentage FLOAT;
    # ALTER TABLE teams ADD COLUMN security_issues_count INT;
    
    # Build response
    report = {
        "batchId": batchId,
        "batchName": batch["name"],
        "generatedAt": datetime.utcnow().isoformat(),
        "summary": {
            "totalTeams": total_teams,
            "averageScore": round(average_score, 2),
            "topTeam": top_team["teamName"] if top_team else "N/A",
            "topScore": top_team["totalScore"] if top_team else 0
        },
        "teams": teams_data,
        "insights": {
            "mostUsedTech": most_used_tech,
            "averageAiUsage": round(average_ai_usage, 2),
            "totalSecurityIssues": total_security_issues
        }
    }
    
    # Handle different formats
    if format == "pdf":
        # In production, generate PDF using ReportLab or similar
        return JSONResponse(
            content={
                "message": "PDF generation not yet implemented",
                "data": report
            }
        )
    elif format == "csv":
        import csv
        import io
        from fastapi.responses import StreamingResponse

        output = io.StringIO()
        # Updated CSV format to include student details
        writer = csv.DictWriter(output, fieldnames=[
            "Rank", "Team Name", "Student Name", "Student Email", 
            "Admin Grade", "Admin Feedback", 
            "Mentor Grade", "Mentor Feedback",
            "Total Score", "Quality", "Security", "Originality", "Architecture", 
            "Documentation", "Health Status", "Verdict", "Mentor", "Frameworks"
        ])
        
        writer.writeheader()
        
        # Build a map of team_id -> students for O(1) lookup (already fetched in teams query)
        team_students_map = {}
        for team in teams:
            team_id = team.get("id")
            students = team.get("students", [])
            team_students_map[team_id] = students if isinstance(students, list) else []
        
        for team in teams_data:
            # Use pre-fetched students from the map (no additional queries!)
            team_id = team.get("teamId")
            students = team_students_map.get(team_id, [])
            
            base_row = {
                "Rank": team.get("rank"),
                "Team Name": team.get("teamName"),
                "Total Score": round(team.get("totalScore", 0), 2),
                "Quality": round(team.get("qualityScore", 0), 2),
                "Security": round(team.get("securityScore", 0), 2),
                "Originality": round(team.get("originalityScore", 0), 2),
                "Architecture": round(team.get("architectureScore", 0), 2),
                "Documentation": round(team.get("documentationScore", 0), 2),
                "Health Status": team.get("healthStatus"),
                "Verdict": "N/A",
                "Mentor": team.get("mentorId", "Unassigned"),
                "Frameworks": ", ".join(team.get("frameworks", []))
            }
            
            if not students:
                # Write one row for the team if no students
                row = base_row.copy()
                row.update({
                    "Student Name": "N/A",
                    "Student Email": "N/A",
                    "Admin Grade": "N/A",
                    "Admin Feedback": "N/A",
                    "Mentor Grade": "N/A",
                    "Mentor Feedback": "N/A"
                })
                writer.writerow(row)
            else:
                for student in students:
                    round_one = (student.get("grading_details") or {}).get("round_1") or {}
                    row = base_row.copy()
                    row.update({
                        "Student Name": student.get("name"),
                        "Student Email": student.get("email"),
                        "Admin Grade": student.get("admin_grade", ""),
                        "Admin Feedback": student.get("admin_feedback", ""),
                        "Mentor Grade": round_one.get("grade", ""),
                        "Mentor Feedback": round_one.get("feedback", "")
                    })
                    writer.writerow(row)
            
        output.seek(0)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"batch_report_{batchId}_{timestamp}.csv"
    # Cache the JSON response for 2 minutes
    if format == "json":
        cache.set(f"hackeval:report:batch:{batchId}", report, RedisCache.TTL_SHORT)
    
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    return report


@router.get("/mentor/{mentorId}", response_model=MentorReportResponse)
async def get_mentor_report(
    mentorId: str = Path(..., description="Mentor ID"),
    batchId: Optional[str] = Query(None, description="Filter by batch ID"),
    format: Optional[str] = Query("json", description="Format: json or pdf"),
    current_user: dict = Depends(get_current_user)
):
    """
    Generate report for mentor's assigned teams.
    Admin or the mentor themselves can access.
    """
    role = current_user.get("role")
    user_id = current_user.get("user_id")
    
    # Check authorization
    if role != "admin" and user_id != mentorId:
        raise HTTPException(
            status_code=403,
            detail="You can only access your own reports"
        )
    
    # Check cache first (skip for PDF exports)
    if format == "json":
        cache_key = f"hackeval:report:mentor:{mentorId}:{batchId or 'all'}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
    
    supabase = get_supabase()
    
    # Verify mentor exists
    mentor_response = supabase.table("users").select("*").eq("id", mentorId).execute()
    if not mentor_response.data:
        raise HTTPException(status_code=404, detail="Mentor not found")
    
    mentor = mentor_response.data[0]
    
    # Get mentor's assigned teams
    mentor_team_ids = []
    
    # 1. Get IDs using centralized logic
    try:
        from ..crud import TeamCRUD
        mentor_team_ids = TeamCRUD.get_mentor_team_ids(mentorId)
    except Exception as e:
        print(f"[Reports] Error getting mentor teams: {e}")
        
    if not mentor_team_ids:
        # If no teams assigned, return empty report
        return {
            "mentorId": mentorId,
            "mentorName": mentor.get("full_name", ""),
            "generatedAt": datetime.utcnow().isoformat(),
            "teams": [],
            "summary": {
                "totalTeams": 0,
                "averageScore": 0,
                "teamsOnTrack": 0,
                "teamsAtRisk": 0,
                "teamsCritical": 0
            }
        }

    # 2. Fetch full team data for these IDs (include students in single query)
    # Projects table has been dropped - all analysis data is now in teams table
    query = supabase.table("teams").select("*, students(*)").in_("id", mentor_team_ids)
    
    if batchId:
        query = query.eq("batch_id", batchId)
    
    teams_response = query.execute()
    teams = teams_response.data or []
    
    # Process teams data
    teams_data = []
    scores = []
    on_track_count = 0
    at_risk_count = 0
    critical_count = 0
    
    for team in teams:
        # Projects table has been dropped - analysis data is now in teams table
        analysis_result = team.get("analysis_result", {})
        if isinstance(analysis_result, str):
            try:
                analysis_result = json.loads(analysis_result)
            except:
                analysis_result = {}
        
        total_score = analysis_result.get("totalScore", 0)
        if total_score > 0:
            scores.append(total_score)
        
        health_status = team.get("health_status", "on_track")
        if health_status == "on_track":
            on_track_count += 1
        elif health_status == "at_risk":
            at_risk_count += 1
        elif health_status == "critical":
            critical_count += 1
        
        teams_data.append({
            "teamId": team["id"],
            "teamName": team["team_name"],
            "batchId": team["batch_id"],
            "totalScore": total_score,
            "qualityScore": analysis_result.get("qualityScore", 0),
            "securityScore": analysis_result.get("securityScore", 0),
            "healthStatus": health_status,
            "lastAnalyzed": team.get("last_analyzed_at")
        })
    
    # Calculate summary
    average_score = sum(scores) / len(scores) if scores else 0
    
    report = {
        "mentorId": mentorId,
        "mentorName": mentor.get("full_name", ""),
        "generatedAt": datetime.utcnow().isoformat(),
        "teams": teams_data,
        "summary": {
            "totalTeams": len(teams),
            "averageScore": round(average_score, 2),
            "teamsOnTrack": on_track_count,
            "teamsAtRisk": at_risk_count,
            "teamsCritical": critical_count
        }
    }
    
    # Handle PDF format
    if format == "pdf":
        return JSONResponse(
            content={
                "message": "PDF generation not yet implemented",
                "data": report
            }
        )
    
    # Cache the JSON response for 2 minutes
    if format == "json":
        cache.set(f"hackeval:report:mentor:{mentorId}:{batchId or 'all'}", report, RedisCache.TTL_SHORT)
    
    return report


@router.get("/team/{teamId}")
async def get_team_report(
    teamId: str = Path(..., description="Team ID"),
    format: Optional[str] = Query("json", description="Format: json or pdf"),
    current_user: dict = Depends(get_current_user)
):
    """
    Generate detailed team report.
    Admin or assigned mentor only.
    Returns JSON (TeamReportResponse) or PDF based on format parameter.
    """
    # Check cache first (skip for PDF exports)
    if format == "json":
        cache_key = f"hackeval:report:team:{teamId}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result
    
    supabase = get_supabase()
    
    # Get team data with students (projects table has been dropped - all analysis data is now in teams table)
    team_response = supabase.table("teams").select("*, students(*)").eq("id", teamId).execute()
    if not team_response.data:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = team_response.data[0]
    
    # Extract students/team members
    students = team.get("students", [])
    team_members = [
        {
            "name": s.get("name", "Unknown"),
            "email": s.get("email"),
            "github": s.get("github_username")
        }
        for s in students
    ] if isinstance(students, list) else []
    
    # Check authorization
    role = current_user.role
    user_id = str(current_user.user_id)
    
    if role != "admin" and team.get("mentor_id") != user_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied. You can only view reports for teams assigned to you."
        )
    
    # Check if team has been analyzed - use the actual database columns
    has_analysis = team.get("total_score") is not None or team.get("status") == "completed"
    
    # OPTIMIZED: Fetch full report from storage if migrated
    report_path = team.get("report_path")
    report_json = {}
    
    if report_path:
        # Team has been migrated to storage - fetch full report
        try:
            report_json = ReportStorageManager.get_report_from_storage(report_path)
            logger.debug(f"Loaded report from storage: {report_path}")
        except Exception as e:
            logger.warning(f"Failed to load report from storage ({report_path}): {e}")
            # Fallback to database report_json if storage fails
            report_json = team.get("report_json", {})
    else:
        # Team not yet migrated - use database report_json
        report_json = team.get("report_json", {})
    
    if isinstance(report_json, str):
        try:
            report_json = json.loads(report_json)
        except:
            report_json = {}
    
    # Extract contributors from report_json.forensics.author_stats
    forensics = report_json.get("forensics", {})
    author_stats_raw = forensics.get("author_stats", {})
    
    # Convert author_stats to list format (could be dict or list)
    if isinstance(author_stats_raw, dict):
        # Dict format: {"author_name": {"commits": 5, ...}}
        author_stats = [
            {"author": name, **data} if isinstance(data, dict) else {"author": name}
            for name, data in author_stats_raw.items()
        ]
    elif isinstance(author_stats_raw, list):
        author_stats = author_stats_raw
    else:
        author_stats = []

    # Merge contributor aliases (username/name variants) into registered students.
    author_stats = merge_contributors_by_team_members(author_stats, team_members)
    
    # Also get languages from report_json
    languages = report_json.get("languages", [])
    
    # Calculate total files and lines of code from available data
    structure = report_json.get("structure", {})
    maturity = report_json.get("maturity", {})
    
    # Total files: try files list, then maturity test_files, otherwise 0
    files_data = report_json.get("files", [])
    total_files = len(files_data) if isinstance(files_data, list) and len(files_data) > 0 else 0
    if total_files == 0:
        # Fallback: count from maturity or structure info
        total_files = maturity.get("test_files", 0)
    
    # Total lines of code: sum lines_changed from all authors
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
    
    # Get project name from GitHub repo URL
    repo_url = team.get("repo_url", "")
    project_name = ""
    if repo_url:
        # Extract repo name from URL like https://github.com/user/repo-name.git
        repo_name = repo_url.rstrip("/").rstrip(".git").split("/")[-1]
        if repo_name:
            project_name = repo_name
    
    # Fallback to report_json or team name
    if not project_name:
        project_name = report_json.get("team", {}).get("project_name") or report_json.get("projectName") or team.get("team_name", "Unknown Project")
    
    # Get problem statement from metadata.ingestion.project_statement
    metadata = team.get("metadata", {}) or {}
    ingestion = metadata.get("ingestion", {}) or {}
    problem_statement = ingestion.get("project_statement", "") or report_json.get("judge", {}).get("description", "")
    
    # Extract detailed scores from report_json
    scores = report_json.get("scores", {})
    
    # Extract judge data for detailed AI feedback
    judge = report_json.get("judge", {})
    features = judge.get("features", [])
    tech_stack_observed = judge.get("tech_stack_observed", [])
    positive_feedback = judge.get("positive_feedback", "")
    constructive_feedback = judge.get("constructive_feedback", "")
    ai_verdict = judge.get("verdict", team.get("verdict", "Unknown"))
    
    # Extract detailed product analysis (new enhanced fields)
    feature_analysis = judge.get("feature_analysis", [])
    product_analysis = judge.get("product_analysis", {})
    suggested_features = judge.get("suggested_features", [])
    overall_recommendation = judge.get("overall_recommendation", "")
    project_description = judge.get("description", "")
    
    # Extract NEW deep analysis fields from enhanced judge
    functionality_check = judge.get("functionality_check", {})
    completeness_analysis = judge.get("completeness_analysis", {})
    quality_indicators = judge.get("quality_indicators", {})
    verdict_reasoning = judge.get("verdict_reasoning", "")
    
    # Extract commit details for recent commits
    commit_details = report_json.get("commit_details", {})
    recent_commits = commit_details.get("recent_commits", [])[:10]  # Last 10 commits
    
    # Extract fake commit data for student report
    fake_commits_list = commit_details.get("fake_commits", [])
    fake_commit_count = commit_details.get("fake_commit_count", 0)
    fake_commit_ratio = commit_details.get("fake_commit_ratio", 0)
    real_commit_count = commit_details.get("real_commit_count", 0)
    total_real_additions = commit_details.get("total_real_additions", 0)
    total_fake_additions = commit_details.get("total_fake_additions", 0)
    commit_health = commit_details.get("commit_health", "Healthy")
    inflation_ratio = commit_details.get("inflation_ratio", 1.0)
    
    # Extract branch tracking data
    branch_details = commit_details.get("branch_details", {})
    main_branch = commit_details.get("main_branch", "main")
    branch_count = commit_details.get("branch_count", 0)
    branches_list = commit_details.get("branches", [])
    
    # Extract security details (enhanced)
    security = report_json.get("security", {})
    
    # Legacy format support
    security_issues = security.get("issues", [])
    secrets_count = security.get("secrets_found", 0) or security.get("leak_count", 0)
    hardcoded_values = security.get("hardcoded_values", [])
    
    # Enhanced security data (from new security scanner)
    security_leaks = security.get("leaks", security.get("details", []))
    best_practices = security.get("best_practices", [])
    recommendations = security.get("recommendations", [])
    secrets_score = security.get("secrets_score")
    practices_score = security.get("practices_score")
    
    # Extract maturity/engineering data
    maturity_data = report_json.get("maturity", {})
    
    # Extract file risk analysis
    risky_files = report_json.get("files", [])[:10]  # Top 10 risky files
    
    # AI detection summary
    llm_detection = report_json.get("llm_detection", {})
    overall_ai_percentage = llm_detection.get("overall_percentage", 0)
    
    # Calculate contribution percentages for team members
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
    
    # Project archetype and type mapping
    metadata = team.get("metadata", {}) or {}
    project_profile = metadata.get("project_profile") or report_json.get("project_profile") or report_json.get("judge", {}).get("project_profile") or {}
    if not isinstance(project_profile, dict):
        project_profile = {}
    archetype = project_profile.get("archetype", "unknown")
    manual_archetype = project_profile.get("manual_archetype")
    if manual_archetype:
        archetype = manual_archetype
    
    archetype_map = {
        "chrome_extension": "Browser Extension",
        "web_app": "Web Application",
        "mobile_app": "Mobile Application",
        "backend_api": "Backend API",
        "ml_ai_pipeline": "ML/AI Pipeline",
        "iot_embedded": "IoT/Embedded System",
        "cli_tool": "CLI Tool",
        "desktop_app": "Desktop Application",
        "game": "Game",
        "unknown": "General Project",
    }
    project_type = archetype_map.get(archetype, "General Project")

    # Build report using actual database columns
    report = {
        "teamId": teamId,
        "teamName": team.get("team_name", "Unknown Team"),
        "projectName": project_name,
        "problemStatement": problem_statement,
        "projectProfile": {
            "archetype": archetype,
            "confidence": project_profile.get("confidence", "low"),
            "source": project_profile.get("source", "none"),
            "manual_archetype": manual_archetype,
        },
        "projectType": project_type,
        "repoUrl": repo_url,
        "teamMembers": team_members,
        "batchId": team["batch_id"],
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
        "commitQuality": {
            "healthStatus": commit_health,
            "totalCommits": total_commits_count,
            "realCommits": real_commit_count,
            "fakeCommits": fake_commit_count,
            "fakeCommitPercentage": round(fake_commit_ratio, 1),
            "realAdditions": total_real_additions,
            "fakeAdditions": total_fake_additions,
            "inflationRatio": round(inflation_ratio, 2),
            "explanation": {
                "whatAreFakeCommits": "Fake commits are commits that inflate your repository with non-meaningful content. Common types include: 1) Committing dependency folders (node_modules, vendor), 2) Committing generated/minified files (.min.js, .pyc), 3) Large binary files or assets, 4) Empty commits with no actual changes.",
                "whyItMatters": "Fake commits negatively impact your evaluation because they: 1) Don't demonstrate your actual coding work, 2) Make it hard to review your real contributions, 3) Violate Git best practices, 4) Result in score penalties (30-60% reduction for affected dimensions).",
                "healthStatusMeaning": {
                    "Healthy": "Less than 30% fake commits - Great job! Your repository follows best practices.",
                    "At Risk": "30-50% fake commits - Your scores are reduced by 30%. Clean up your repository.",
                    "Critical": "Over 50% fake commits - Your scores are reduced by 60%. Immediate action needed!"
                },
                "currentStatus": commit_health,
                "yourScore": f"{fake_commit_ratio}% of your commits are identified as fake or low-quality"
            },
            "detectedIssues": [
                {
                    "type": "Fake Commits Detected",
                    "count": fake_commit_count,
                    "percentage": round(fake_commit_ratio, 1),
                    "severity": "Critical" if fake_commit_ratio > 50 else "High" if fake_commit_ratio > 30 else "Medium" if fake_commit_ratio > 10 else "Low",
                    "description": f"Found {fake_commit_count} commits that add dependencies, generated files, or no meaningful code changes."
                }
            ] if fake_commit_count > 0 else [],
            "exampleFakeCommits": [
                {
                    "sha": commit.get("hexsha", "")[:7],
                    "message": commit.get("message", "No message")[:100],
                    "reasons": commit.get("reasons", []),
                    "additions": commit.get("additions", 0),
                    "fakeAdditions": commit.get("fake_additions", 0),
                    "files": commit.get("files_changed", [])[:5]  # Show first 5 files as examples
                }
                for commit in fake_commits_list[:5]  # Show top 5 fake commits
            ] if fake_commits_list else [],
            "howToFix": {
                "immediate": [
                    "Create/update .gitignore file to exclude dependency folders and generated files",
                    "Remove committed dependencies using: git rm -r --cached node_modules (or vendor, etc.)",
                    "Delete generated files from repository: git rm --cached *.min.js *.pyc",
                    "Commit the changes: git commit -m 'Clean repository: remove dependencies and generated files'",
                    "Push the cleaned repository: git push origin main"
                ],
                "prevention": [
                    "Always use .gitignore BEFORE committing (copy from gitignore.io for your tech stack)",
                    "Review 'git status' before committing to ensure you're only adding source code",
                    "Use 'git add' with specific files instead of 'git add .' blindly",
                    "Keep commits small and focused (50-200 lines per commit is ideal)",
                    "Write meaningful commit messages that describe WHAT changed and WHY"
                ],
                "bestPractices": [
                    "Commit only source code files (.py, .js, .java, .cpp, etc.)",
                    "Always exclude: node_modules/, __pycache__/, .venv/, dist/, build/, vendor/",
                    "Never commit: API keys, passwords, .env files, database dumps, large binaries",
                    "Each commit should represent one logical change to the codebase",
                    "Test your code before committing to ensure it works"
                ]
            },
            "commonMistakes": [
                {
                    "mistake": "Running 'git add .' without .gitignore",
                    "consequence": "Commits entire node_modules or vendor folder (thousands of files)",
                    "fix": "Create .gitignore first, then use 'git rm -r --cached <folder>'"
                },
                {
                    "mistake": "Committing minified/compiled files (.min.js, .pyc, .class)",
                    "consequence": "These are generated files that bloat your repository",
                    "fix": "Add these extensions to .gitignore and remove from repository"
                },
                {
                    "mistake": "Empty commits or commits with only whitespace changes",
                    "consequence": "These don't demonstrate any actual work",
                    "fix": "Only commit when you've made meaningful code changes"
                },
                {
                    "mistake": "Committing large assets (images, videos, datasets)",
                    "consequence": "Git is for code, not large binary files",
                    "fix": "Use Git LFS or external storage for large files"
                }
            ],
            "scorePenalty": {
                "applied": fake_commit_ratio >= 30,
                "multiplier": 0.4 if fake_commit_ratio > 50 else 0.7 if fake_commit_ratio >= 30 else 1.0,
                "description": "Critical (>50% fake): 60% score penalty | At Risk (30-50% fake): 30% score penalty | Healthy (<30%): No penalty",
                "affectedDimensions": ["Implementation", "Quality", "Organization", "Effort"] if fake_commit_ratio >= 30 else [],
                "recommendation": "Clean your repository immediately to improve your scores!" if fake_commit_ratio >= 30 else "Keep maintaining good repository hygiene!"
            },
            "resources": [
                {
                    "title": "Create .gitignore for your tech stack",
                    "url": "https://www.toptal.com/developers/gitignore",
                    "description": "Generate a comprehensive .gitignore file for your project"
                },
                {
                    "title": "Git Best Practices Guide",
                    "url": "https://git-scm.com/book/en/v2/Distributed-Git-Contributing-to-a-Project",
                    "description": "Learn how to make effective commits and manage your repository"
                },
                {
                    "title": "How to Write Good Commit Messages",
                    "url": "https://chris.beams.io/posts/git-commit/",
                    "description": "Best practices for clear, meaningful commit messages"
                }
            ]
        },
        "branchTracking": {
            "totalBranches": branch_count,
            "mainBranch": main_branch,
            "branches": branches_list,
            "branchDetails": [
                {
                    "name": branch_info.get("name"),
                    "totalCommits": branch_info.get("totalCommits", 0),
                    "primaryAuthor": branch_info.get("primaryAuthor", "Unknown"),
                    "authors": branch_info.get("authors", {}),
                    "lastCommitDate": branch_info.get("lastCommitDate"),
                    "firstCommitDate": branch_info.get("firstCommitDate"),
                    "isActive": branch_info.get("isActive", False),
                    "daysSinceLastCommit": branch_info.get("daysSinceLastCommit"),
                    "mergeStatus": branch_info.get("mergeStatus", "Unknown"),
                    "isMerged": branch_info.get("isMerged", False),
                    "isMainBranch": branch_info.get("isMainBranch", False)
                }
                for branch_name, branch_info in branch_details.items()
            ] if branch_details else [],
            "teamBranchActivity": {
                "byMember": [
                    {
                        "memberName": author_name,
                        "branches": [
                            {
                                "branchName": branch_name,
                                "commits": commit_count
                            }
                            for branch_name, branch_info in branch_details.items()
                            if author_name in branch_info.get("authors", {})
                            for commit_count in [branch_info["authors"][author_name]]
                        ]
                    }
                    for author_name in set(
                        author_name
                        for branch_info in branch_details.values()
                        for author_name in branch_info.get("authors", {}).keys()
                    )
                ] if branch_details else [],
                "summary": {
                    "activeBranches": len([b for b in branch_details.values() if b.get("isActive", False)]),
                    "mergedBranches": len([b for b in branch_details.values() if b.get("isMerged", False)]),
                    "unmergedBranches": len([b for b in branch_details.values() if b.get("mergeStatus") == "Unmerged"]),
                    "staleBranches": len([b for b in branch_details.values() if not b.get("isActive", False) and not b.get("isMainBranch", False)])
                }
            },
            "insights": {
                "branchingStrategy": {
                    "assessment": "Good" if branch_count >= 2 and any(b.get("isMerged") for b in branch_details.values()) else "Basic" if branch_count >= 2 else "Poor",
                    "description": f"Team has {branch_count} branches. " + 
                                 ("Using feature branches effectively. " if branch_count >= 2 else "Consider using feature branches for parallel development. ") +
                                 (f"{len([b for b in branch_details.values() if b.get('isMerged')])} branches have been merged back to {main_branch}." if any(b.get("isMerged") for b in branch_details.values()) else f"No branches merged to {main_branch} yet."),
                    "recommendation": "Great branching workflow!" if branch_count >= 2 and any(b.get("isMerged") for b in branch_details.values()) 
                                    else "Create feature branches for new features and merge via Pull Requests" if branch_count < 2
                                    else "Remember to merge completed feature branches back to main"
                },
                "collaborationPattern": {
                    "sharedBranches": len([b for b in branch_details.values() if len(b.get("authors", {})) > 1]),
                    "dedicatedBranches": len([b for b in branch_details.values() if len(b.get("authors", {})) == 1]),
                    "description": f"{len([b for b in branch_details.values() if len(b.get('authors', {})) > 1])} branches have multiple contributors, showing good collaboration."
                },
                "warnings": [
                    {
                        "type": "Stale Branches",
                        "count": len([b for b in branch_details.values() if not b.get("isActive") and not b.get("isMainBranch")]),
                        "severity": "Medium",
                        "message": f"You have {len([b for b in branch_details.values() if not b.get('isActive') and not b.get('isMainBranch')])} stale branches (no commits in 14+ days). Consider cleaning them up or merging."
                    } if len([b for b in branch_details.values() if not b.get("isActive") and not b.get("isMainBranch")]) > 0 else None,
                    {
                        "type": "Unmerged Work",
                        "count": len([b for b in branch_details.values() if b.get("mergeStatus") == "Unmerged"]),
                        "severity": "High",
                        "message": f"You have {len([b for b in branch_details.values() if b.get('mergeStatus') == 'Unmerged'])} active branches that haven't been merged. Make sure to merge completed work!"
                    } if len([b for b in branch_details.values() if b.get("mergeStatus") == "Unmerged"]) > 0 else None,
                    {
                        "type": "No Branching",
                        "severity": "Medium",
                        "message": "Your team is working only on the main branch. Consider using feature branches for better collaboration and code review."
                    } if branch_count <= 1 else None
                ],
                "bestPractices": [
                    {
                        "practice": "Create Feature Branches",
                        "status": "Following" if branch_count >= 2 else "Not Following",
                        "explanation": "Use separate branches for each feature/task to enable parallel development and easier code review.",
                        "howTo": "1. Create branch: git checkout -b feature/your-feature-name\n2. Work on your feature\n3. Push branch: git push origin feature/your-feature-name\n4. Create Pull Request on GitHub\n5. Merge after review"
                    },
                    {
                        "practice": "Merge via Pull Requests",
                        "status": "Following" if any(b.get("isMerged") for b in branch_details.values()) else "Unknown",
                        "explanation": "Merge feature branches back to main using Pull Requests for code review and quality control.",
                        "howTo": "1. Go to your GitHub repository\n2. Click 'Pull Requests' → 'New Pull Request'\n3. Select your feature branch to merge into main\n4. Add description and request review\n5. Merge after approval"
                    },
                    {
                        "practice": "Keep Branches Up to Date",
                        "status": "Following" if len([b for b in branch_details.values() if not b.get("isActive") and not b.get("isMainBranch")]) == 0 else "Needs Improvement",
                        "explanation": "Regularly update your feature branches with changes from main to avoid merge conflicts.",
                        "howTo": "1. Switch to main: git checkout main\n2. Pull latest: git pull origin main\n3. Switch to feature: git checkout feature/your-feature\n4. Merge main: git merge main\n5. Resolve conflicts if any"
                    },
                    {
                        "practice": "Delete Merged Branches",
                        "status": "Following" if branch_count <= 3 else "Needs Improvement",
                        "explanation": "Clean up branches after merging to keep repository organized.",
                        "howTo": "1. After merging PR on GitHub, click 'Delete branch'\n2. Locally: git branch -d feature/branch-name\n3. Remove remote: git push origin --delete feature/branch-name"
                    }
                ]
            }
        },
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
            "recommendations": recommendations
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

    # ========== SCORE INSIGHTS (Why Low & How to Improve) ==========
    # Generate contextual insights for low-scoring dimensions (< 50/100).
    # This data appears in both the JSON API response and the PDF report.
    score_insights = _generate_score_insights(report)
    if score_insights:
        report["scoreInsights"] = score_insights

    # Build individual scores from contributor stats for report/PDF rendering.
    individual_student_scores = []
    student_map = {}
    for s in students:
        if isinstance(s, dict):
            name = (s.get("name") or "").lower().strip()
            github = (s.get("github_username") or "").lower().strip()
            if name:
                student_map[f"name:{name}"] = s
            if github:
                student_map[f"github:{github}"] = s

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

        individual_student_scores.append({
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
        })

    report["individualStudentScores"] = individual_student_scores
    
    student_report_fields = build_student_report_fields(report_json, total_commits_count)
    report["commitQuality"] = student_report_fields["commitQuality"]
    report["marksDeduction"] = student_report_fields["marksDeduction"]

    # Add leaderboard data if generating PDF
    if format == "pdf":
        try:
            leaderboard_service = LeaderboardService()
            leaderboard_data = await leaderboard_service.get_full_batch_leaderboard(
                batch_id=team["batch_id"],
                limit=None  # Get all teams for PDF
            )
            
            if leaderboard_data:
                # Convert leaderboard entries to dict format for PDF
                leaderboard_entries = [
                    {
                        "rank": entry.rank,
                        "team_id": entry.team_id,
                        "team_name": entry.team_name,
                        "overall_score": entry.overall_score
                    }
                    for entry in leaderboard_data.entries
                ]
                
                report["leaderboard"] = {
                    "entries": leaderboard_entries,
                    "batch_name": leaderboard_data.batch_name,
                    "generated_at": leaderboard_data.generated_at.isoformat(),
                    "total_teams": leaderboard_data.total_teams
                }
                print(f"[Reports] Leaderboard added to PDF report for team {teamId}")
        except Exception as e:
            print(f"[Reports] ⚠️ Failed to add leaderboard to PDF report: {e}")
            # Continue without leaderboard
    
    # Handle PDF format
    if format == "pdf":
        try:
            pdf_bytes = generate_team_report_pdf(report)
            
            # Create filename
            raw_team_name = str(report.get("teamName", "team"))
            safe_team_name = re.sub(r"[^A-Za-z0-9_-]", "_", raw_team_name).strip("_")[:30] or "team"
            filename = f"{safe_team_name}_report_{datetime.utcnow().strftime('%Y%m%d')}.pdf"

            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
        except Exception as e:
            logger.exception("PDF generation failed for team %s", teamId)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate PDF: {str(e)}"
            )
    
    # Cache the JSON response for 2 minutes
    if format == "json":
        cache.set(f"hackeval:report:team:{teamId}", report, RedisCache.TTL_SHORT)
    
    return report


@router.post("/team/{teamId}/send")
@limiter.limit("10/minute")
async def send_team_report_email(
    request: Request,
    teamId: str = Path(..., description="Team ID"),
    dry_run: bool = Query(False, description="If true, only verify emails without sending"),
    current_user: dict = Depends(get_current_user)
):
    """
    Send team report PDF via email to all team members.
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Get team data with students
    team_response = supabase.table("teams").select("*, students(*)").eq("id", teamId).execute()
    if not team_response.data:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = team_response.data[0]
    team_name = team.get("team_name", "Unknown Team")
    
    # Get students/team members
    students = team.get("students", [])
    if not students or not isinstance(students, list):
        raise HTTPException(status_code=400, detail="No students are linked to this team. Please add students first.")

    team_members = [
        {
            "name": s.get("name", "Unknown"),
            "email": s.get("email"),
            "github": s.get("github_username")
        }
        for s in students
    ]
    
    # Filter students with valid emails
    student_emails = [s.get("email") for s in students if s.get("email")]
    if not student_emails:
        raise HTTPException(status_code=400, detail="Students are linked, but none have a registered email address.")
    
    # Generate report data (reuse existing logic)
    # OPTIMIZED: Fetch from storage if migrated
    report_path = team.get("report_path")
    if report_path:
        try:
            report_json = ReportStorageManager.get_report_from_storage(report_path)
        except Exception as e:
            logger.warning(f"Failed to load report from storage ({report_path}): {e}")
            report_json = team.get("report_json") or {}
    else:
        report_json = team.get("report_json") or {}
    
    if isinstance(report_json, str):
        try:
            report_json = json.loads(report_json)
        except:
            report_json = {}
    
    # Extract data for report
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

    # Normalize aliases to canonical team member identity for report output.
    author_stats = merge_contributors_by_team_members(author_stats, team_members)
    
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
        project_name = report_json.get("team", {}).get("project_name") or report_json.get("projectName") or team_name
    
    metadata = team.get("metadata", {}) or {}
    ingestion = metadata.get("ingestion", {}) or {}
    problem_statement = ingestion.get("project_statement", "") or report_json.get("judge", {}).get("description", "")
    
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
    
    # Extract NEW deep analysis fields from enhanced judge  
    functionality_check = judge.get("functionality_check", {})
    completeness_analysis = judge.get("completeness_analysis", {})
    quality_indicators = judge.get("quality_indicators", {})
    verdict_reasoning = judge.get("verdict_reasoning", "")
    
    commit_details = report_json.get("commit_details", {})
    recent_commits = commit_details.get("recent_commits", [])[:10]
    
    security = report_json.get("security", {})
    security_issues = security.get("issues", [])
    secrets_count = security.get("secrets_found", 0) or security.get("leak_count", 0)
    hardcoded_values = security.get("hardcoded_values", [])
    
    # Enhanced security data (from new security scanner)
    security_leaks = security.get("leaks", security.get("details", []))
    best_practices = security.get("best_practices", [])
    recommendations = security.get("recommendations", [])
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
    
    team_members = [
        {
            "name": s.get("name", "Unknown"),
            "email": s.get("email"),
            "github": s.get("github_username")
        }
        for s in students
    ] if isinstance(students, list) else []
    
    # Project archetype and type mapping
    metadata = team.get("metadata", {}) or {}
    project_profile = metadata.get("project_profile") or report_json.get("project_profile") or report_json.get("judge", {}).get("project_profile") or {}
    if not isinstance(project_profile, dict):
        project_profile = {}
    archetype = project_profile.get("archetype", "unknown")
    manual_archetype = project_profile.get("manual_archetype")
    if manual_archetype:
        archetype = manual_archetype
    
    archetype_map = {
        "chrome_extension": "Browser Extension",
        "web_app": "Web Application",
        "mobile_app": "Mobile Application",
        "backend_api": "Backend API",
        "ml_ai_pipeline": "ML/AI Pipeline",
        "iot_embedded": "IoT/Embedded System",
        "cli_tool": "CLI Tool",
        "desktop_app": "Desktop Application",
        "game": "Game",
        "unknown": "General Project",
    }
    project_type = archetype_map.get(archetype, "General Project")

    # Build report data
    report_data = {
        "teamId": teamId,
        "teamName": team_name,
        "projectName": project_name,
        "problemStatement": problem_statement,
        "projectProfile": {
            "archetype": archetype,
            "confidence": project_profile.get("confidence", "low"),
            "source": project_profile.get("source", "none"),
            "manual_archetype": manual_archetype,
        },
        "projectType": project_type,
        "repoUrl": repo_url,
        "teamMembers": team_members,
        "individualStudentScores": individual_student_scores,
        "batchId": team["batch_id"],
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
            "recommendations": recommendations
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

    # Generate team report PDF
    try:
        pdf_bytes = generate_team_report_pdf(report_data)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate PDF: {str(e)}"
        )
    
    # Generate leaderboard PDF
    leaderboard_pdf_bytes = None
    try:
        leaderboard_service = LeaderboardService()
        leaderboard_data = await leaderboard_service.get_full_batch_leaderboard(
            batch_id=team["batch_id"],
            limit=None  # Get all teams
        )
        
        if leaderboard_data:
            # Convert to dict format for PDF generator
            leaderboard_dict = {
                "batch_name": leaderboard_data.batch_name,
                "generated_at": leaderboard_data.generated_at.isoformat(),
                "total_teams": leaderboard_data.total_teams,
                "entries": [
                    {
                        "rank": entry.rank,
                        "team_id": entry.team_id,
                        "team_name": entry.team_name,
                        "overall_score": entry.overall_score,
                        "project_name": entry.project_name
                    }
                    for entry in leaderboard_data.entries
                ]
            }
            
            leaderboard_pdf_bytes = generate_leaderboard_pdf(leaderboard_dict, teamId)
            logger.info(f"Leaderboard PDF generated for team {team_name}")
    except Exception as e:
        logger.warning(f"Failed to generate leaderboard PDF: {e}")
        # Continue without leaderboard PDF
    
    # Create filenames
    safe_team_name = team_name.replace(' ', '_').replace('/', '_')[:30]
    report_filename = f"{safe_team_name}_report_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    leaderboard_filename = f"{safe_team_name}_leaderboard_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    
    # Send email to the entire team at once
    sent_count = 0
    failed_emails = []
    
    # Determine if repo is empty
    is_empty_repo = total_files == 0 and total_loc == 0

    if student_emails:
        try:
            # Prepare email body
            subject = EmailTemplates.weekly_report_subject(team_name, project_name=project_name)
            email_body_dict = EmailTemplates.weekly_report_body(
                team_name, 
                includes_leaderboard=(leaderboard_pdf_bytes is not None), 
                project_name=project_name,
                is_empty_repo=is_empty_repo
            )
            
            # Send email with attachments
            if not dry_run:
                team_emails_str = ", ".join(student_emails)
                if leaderboard_pdf_bytes:
                    # Send with both PDFs
                    send_email_with_attachment(
                        subject=subject,
                        body_text=email_body_dict["text"],
                        html_body=email_body_dict["html"],
                        to_email=team_emails_str,
                        attachment_bytes=pdf_bytes,
                        attachment_filename=report_filename,
                        additional_attachments=[
                            {
                                "bytes": leaderboard_pdf_bytes,
                                "filename": leaderboard_filename
                            }
                        ]
                    )
                else:
                    # Send with only team report PDF
                    send_email_with_attachment(
                        subject=subject,
                        body_text=email_body_dict["text"],
                        html_body=email_body_dict["html"],
                        to_email=team_emails_str,
                        attachment_bytes=pdf_bytes,
                        attachment_filename=report_filename
                    )
            
            sent_count = len(student_emails)
        except Exception as e:
            print(f"Failed to send email to team {team_name}: {e}")
            failed_emails = student_emails
            
    if sent_count == 0 and student_emails:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send emails to any recipients. Errors: {', '.join(failed_emails)}"
        )
    
    return {
        "success": True,
        "message": f"Report {'verified' if dry_run else 'sent'} for {sent_count} student(s)" + (" with leaderboard" if leaderboard_pdf_bytes else ""),
        "sentTo": sent_count,
        "totalStudents": len(student_emails),
        "failedEmails": failed_emails if failed_emails else None,
        "leaderboardIncluded": leaderboard_pdf_bytes is not None,
        "dryRun": dry_run
    }


@router.post("/batch/{batchId}/send-all")
@limiter.limit("10/minute")
async def send_all_batch_reports(
    request: Request,
    batchId: str = Path(..., description="Batch ID"),
    dry_run: bool = Query(False, description="If true, only verify emails without sending"),
    current_user: dict = Depends(get_current_user)
):
    """
    Send reports to all analyzed teams in a batch.
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Verify batch exists
    batch_response = supabase.table("batches").select("*").eq("id", batchId).execute()
    if not batch_response.data:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    batch = batch_response.data[0]
    
    # Get all teams in batch that have been analyzed
    teams_response = supabase.table("teams").select(
        "id, team_name, last_analyzed_at"
    ).eq("batch_id", batchId).not_.is_("last_analyzed_at", "null").execute()
    
    teams = teams_response.data or []
    
    if not teams:
        return {
            "success": True,
            "message": "No analyzed teams found in this batch",
            "totalTeams": 0,
            "successfulSends": 0,
            "failedSends": 0,
            "details": []
        }
    
    # Generate leaderboard PDF once for the entire batch to reuse
    leaderboard_pdf_bytes = None
    try:
        leaderboard_service = LeaderboardService()
        leaderboard_data = await leaderboard_service.get_full_batch_leaderboard(
            batch_id=batchId,
            limit=None  # Get all teams
        )
        
        if leaderboard_data:
            # Convert to dict format for PDF generator
            leaderboard_dict = {
                "batch_name": leaderboard_data.batch_name,
                "generated_at": leaderboard_data.generated_at.isoformat(),
                "total_teams": leaderboard_data.total_teams,
                "entries": [
                    {
                        "rank": entry.rank,
                        "team_id": entry.team_id,
                        "team_name": entry.team_name,
                        "overall_score": entry.overall_score,
                        "project_name": entry.project_name
                    }
                    for entry in leaderboard_data.entries
                ]
            }
            # We will generate recipient-specific ones inside the loop later,
            # but generating the data structure here saves querying DB multiple times
            logger.info(f"Leaderboard data fetched for batch {batch['name']}")
    except Exception as e:
        logger.warning(f"Failed to fetch leaderboard data for batch: {e}")
        leaderboard_dict = None

    # Send reports for each team
    successful_sends = 0
    failed_sends = 0
    details = []
    
    for team in teams:
        team_id = team["id"]
        team_name = team["team_name"]
        
        try:
            # Get team data with students
            team_full_response = supabase.table("teams").select("*, students(*)").eq("id", team_id).execute()
            if not team_full_response.data:
                failed_sends += 1
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "status": "failed",
                    "error": "Team not found"
                })
                continue
            
            team_full = team_full_response.data[0]
            students = team_full.get("students", [])
            
            if not students or not isinstance(students, list):
                failed_sends += 1
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "status": "failed",
                    "error": "No students are linked to this team. Please add students first."
                })
                continue
            
            # Filter students with valid emails
            student_emails = [s.get("email") for s in students if s.get("email")]
            if not student_emails:
                failed_sends += 1
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "status": "failed",
                    "error": "Students are linked, but none have a registered email address."
                })
                continue

            team_members = [
                {
                    "name": s.get("name", "Unknown"),
                    "email": s.get("email"),
                    "github": s.get("github_username")
                }
                for s in students
            ]
            
            # Generate report data - fetch from storage if migrated
            report_json = ReportStorageManager.get_report_for_team(team_full)
            
            # Extract data for report
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

            # Merge contributor aliases so exported reports use canonical identities.
            author_stats = merge_contributors_by_team_members(author_stats, team_members)
            
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
                    team_full.get("total_loc")
                    or report_json.get("code_metrics", {}).get("total_lines_of_code", 0)
                    or report_json.get("summary", {}).get("total_lines", 0)
                    or 0
                )
            
            repo_url = team_full.get("repo_url", "")
            project_name = ""
            if repo_url:
                repo_name = repo_url.rstrip("/").rstrip(".git").split("/")[-1]
                if repo_name:
                    project_name = repo_name
            
            if not project_name:
                project_name = report_json.get("team", {}).get("project_name") or report_json.get("projectName") or team_name
            
            metadata = team_full.get("metadata", {}) or {}
            ingestion = metadata.get("ingestion", {}) or {}
            problem_statement = ingestion.get("project_statement", "") or report_json.get("judge", {}).get("description", "")
            
            scores = report_json.get("scores", {})
            judge = report_json.get("judge", {})
            features = judge.get("features", [])
            tech_stack_observed = judge.get("tech_stack_observed", [])
            positive_feedback = judge.get("positive_feedback", "")
            constructive_feedback = judge.get("constructive_feedback", "")
            ai_verdict = judge.get("verdict", team_full.get("verdict", "Unknown"))
            
            feature_analysis = judge.get("feature_analysis", [])
            product_analysis = judge.get("product_analysis", {})
            suggested_features = judge.get("suggested_features", [])
            overall_recommendation = judge.get("overall_recommendation", "")
            
            # Extract NEW deep analysis fields from enhanced judge
            functionality_check = judge.get("functionality_check", {})
            completeness_analysis = judge.get("completeness_analysis", {})
            quality_indicators = judge.get("quality_indicators", {})
            verdict_reasoning = judge.get("verdict_reasoning", "")
            
            commit_details = report_json.get("commit_details", {})
            recent_commits = commit_details.get("recent_commits", [])[:10]
            
            security = report_json.get("security", {})
            security_issues = security.get("issues", [])
            secrets_count = security.get("secrets_found", 0) or security.get("leak_count", 0)
            hardcoded_values = security.get("hardcoded_values", [])
            
            # Enhanced security data (from new security scanner)
            security_leaks = security.get("leaks", security.get("details", []))
            best_practices = security.get("best_practices", [])
            recommendations = security.get("recommendations", [])
            secrets_score = security.get("secrets_score")
            practices_score = security.get("practices_score")
            
            maturity_data = report_json.get("maturity", {})
            risky_files = report_json.get("files", [])[:10]
            llm_detection = report_json.get("llm_detection", {})
            overall_ai_percentage = llm_detection.get("overall_percentage", 0)
            
            total_commits_count = team_full.get("total_commits") or forensics.get("total_commits", 0) or 1
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
            
            team_members = [
                {
                    "name": s.get("name", "Unknown"),
                    "email": s.get("email"),
                    "github": s.get("github_username")
                }
                for s in students
            ] if isinstance(students, list) else []
            
            # Project archetype and type mapping
            metadata = team_full.get("metadata", {}) or {}
            project_profile = metadata.get("project_profile") or report_json.get("project_profile") or report_json.get("judge", {}).get("project_profile") or {}
            if not isinstance(project_profile, dict):
                project_profile = {}
            archetype = project_profile.get("archetype", "unknown")
            manual_archetype = project_profile.get("manual_archetype")
            if manual_archetype:
                archetype = manual_archetype
            
            archetype_map = {
                "chrome_extension": "Browser Extension",
                "web_app": "Web Application",
                "mobile_app": "Mobile Application",
                "backend_api": "Backend API",
                "ml_ai_pipeline": "ML/AI Pipeline",
                "iot_embedded": "IoT/Embedded System",
                "cli_tool": "CLI Tool",
                "desktop_app": "Desktop Application",
                "game": "Game",
                "unknown": "General Project",
            }
            project_type = archetype_map.get(archetype, "General Project")

            # Build report data
            report_data = {
                "teamId": team_id,
                "teamName": team_name,
                "projectName": project_name,
                "problemStatement": problem_statement,
                "projectProfile": {
                    "archetype": archetype,
                    "confidence": project_profile.get("confidence", "low"),
                    "source": project_profile.get("source", "none"),
                    "manual_archetype": manual_archetype,
                },
                "projectType": project_type,
                "repoUrl": repo_url,
                "teamMembers": team_members,
                "individualStudentScores": individual_student_scores,
                "batchId": team_full["batch_id"],
                "generatedAt": datetime.utcnow().isoformat(),
                "analysis": {
                    "totalScore": team_full.get("total_score") or 0,
                    "qualityScore": team_full.get("quality_score") or scores.get("quality", 0),
                    "securityScore": team_full.get("security_score") or scores.get("security", 0),
                    "originalityScore": team_full.get("originality_score") or scores.get("originality", 0),
                    "architectureScore": team_full.get("architecture_score") or scores.get("organization", 0),
                    "documentationScore": team_full.get("documentation_score") or scores.get("documentation", 0),
                    "effortScore": scores.get("effort", 0),
                    "implementationScore": scores.get("implementation", 0),
                    "engineeringScore": scores.get("engineering", 0)
                },
                "commits": {
                    "total": total_commits_count,
                    "contributors": contributors_with_pct,
                    "recentCommits": recent_commits
                },
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
                    "score": team_full.get("security_score") or scores.get("security", 0),
                    "secretsScore": secrets_score,
                    "practicesScore": practices_score,
                    "issues": security_issues,
                    "secretsDetected": secrets_count,
                    "hardcodedValues": hardcoded_values,
                    "leaks": security_leaks,
                    "bestPractices": best_practices,
                    "recommendations": recommendations
                },
                "aiAnalysis": {
                    "aiGeneratedPercentage": overall_ai_percentage,
                    "verdict": ai_verdict,
                    "verdictReasoning": verdict_reasoning,
                    "strengths": team_full.get("ai_pros") or (positive_feedback.split(". ") if positive_feedback else []),
                    "improvements": team_full.get("ai_cons") or (constructive_feedback.split(". ") if constructive_feedback else []),
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
                "healthStatus": team_full.get("health_status", "on_track"),
                "riskFlags": team_full.get("risk_flags", []),
                "lastAnalyzedAt": team_full.get("last_analyzed_at") or team_full.get("analyzed_at")
            }
            
            student_report_fields = build_student_report_fields(report_json, total_commits_count)
            report_data["commitQuality"] = student_report_fields["commitQuality"]
            report_data["marksDeduction"] = student_report_fields["marksDeduction"]

            # Generate PDF
            try:
                pdf_bytes = generate_team_report_pdf(report_data)
            except Exception as e:
                failed_sends += 1
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "status": "failed",
                    "error": f"PDF generation failed: {str(e)}"
                })
                continue
            
            # Generate specific leaderboard PDF for this team if data is available
            team_leaderboard_pdf_bytes = None
            if 'leaderboard_dict' in locals() and leaderboard_dict:
                try:
                    team_leaderboard_pdf_bytes = generate_leaderboard_pdf(leaderboard_dict, team_id)
                except Exception as e:
                    logger.warning(f"Failed to generate specific leaderboard PDF for team {team_name}: {e}")

            # Create filename
            safe_team_name = team_name.replace(' ', '_').replace('/', '_')[:30]
            filename = f"{safe_team_name}_report_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
            leaderboard_filename = f"{safe_team_name}_leaderboard_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
            
            # Send email to the entire team at once
            sent_count = 0
            failed_emails = []
            
            # Determine if repo is empty
            is_empty_repo = total_files == 0 and total_loc == 0
            
            if student_emails:
                try:
                    subject = EmailTemplates.weekly_report_subject(team_name, project_name=project_name)
                    email_body_dict = EmailTemplates.weekly_report_body(
                        team_name, 
                        includes_leaderboard=(team_leaderboard_pdf_bytes is not None), 
                        project_name=project_name,
                        is_empty_repo=is_empty_repo
                    )
                    
                    if not dry_run:
                        team_emails_str = ", ".join(student_emails)
                        if team_leaderboard_pdf_bytes:
                             send_email_with_attachment(
                                 subject=subject,
                                 body_text=email_body_dict["text"],
                                 html_body=email_body_dict["html"],
                                 to_email=team_emails_str,
                                 attachment_bytes=pdf_bytes,
                                 attachment_filename=filename,
                                 additional_attachments=[
                                     {
                                         "bytes": team_leaderboard_pdf_bytes,
                                         "filename": leaderboard_filename
                                     }
                                 ]
                             )
                        else:
                             send_email_with_attachment(
                                 subject=subject,
                                 body_text=email_body_dict["text"],
                                 html_body=email_body_dict["html"],
                                 to_email=team_emails_str,
                                 attachment_bytes=pdf_bytes,
                                 attachment_filename=filename
                             )
                        # Small delay after sending to a team
                        await asyncio.sleep(0.5)
                    
                    sent_count = len(student_emails)
                except Exception as e:
                    print(f"Failed to send email to team {team_name}: {e}")
                    failed_emails = student_emails
            
            # Larger delay between teams to prevent rate limiting
            if not dry_run:
                await asyncio.sleep(2.0)
            
            if sent_count > 0:
                successful_sends += 1
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "status": "success",
                    "sentTo": sent_count,
                    "failedEmails": failed_emails if failed_emails else None
                })
            else:
                failed_sends += 1
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "status": "failed",
                    "error": f"Failed to send to any recipients: {', '.join(failed_emails)}"
                })
        
        except Exception as e:
            failed_sends += 1
            details.append({
                "teamId": team_id,
                "teamName": team_name,
                "status": "failed",
                "error": str(e)
            })
    
    return {
        "success": True,
        "message": f"{'Verified' if dry_run else 'Sent'} reports for {successful_sends} out of {len(teams)} teams",
        "batchName": batch["name"],
        "totalTeams": len(teams),
        "successfulSends": successful_sends,
        "failedSends": failed_sends,
        "dryRun": dry_run,
        "details": details
    }


@router.post("/batch/{batchId}/send-leaderboard")
@limiter.limit("10/minute")
async def send_batch_leaderboard(
    request: Request,
    batchId: str = Path(..., description="Batch ID"),
    dry_run: bool = Query(False, description="If true, only verify emails without sending"),
    current_user: dict = Depends(get_current_user)
):
    """
    Send the batch leaderboard PDF to all students in the batch.
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Verify batch exists
    batch_response = supabase.table("batches").select("*").eq("id", batchId).execute()
    if not batch_response.data:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    batch = batch_response.data[0]
    
    # Get all teams in the batch
    teams_response = supabase.table("teams").select(
        "id, team_name"
    ).eq("batch_id", batchId).execute()
    
    teams = teams_response.data or []
    
    if not teams:
        return {
            "success": True,
            "message": "No teams found in this batch",
            "totalTeams": 0,
            "successfulSends": 0,
            "failedSends": 0,
            "details": []
        }
        
    # Generate leaderboard PDF once for the entire batch to reuse
    try:
        leaderboard_service = LeaderboardService()
        leaderboard_data = await leaderboard_service.get_full_batch_leaderboard(
            batch_id=batchId,
            limit=None  # Get all teams
        )
        
        if not leaderboard_data or not leaderboard_data.entries:
             return {
                "success": False,
                "message": "No leaderboard data available for this batch",
                "totalTeams": len(teams),
                "successfulSends": 0,
                "failedSends": 0,
                "details": []
            }
            
        # Convert to dict format for PDF generator
        leaderboard_dict = {
            "batch_name": leaderboard_data.batch_name,
            "generated_at": leaderboard_data.generated_at.isoformat(),
            "total_teams": leaderboard_data.total_teams,
            "entries": [
                {
                    "rank": entry.rank,
                    "team_id": entry.team_id,
                    "team_name": entry.team_name,
                    "overall_score": entry.overall_score,
                    "project_name": entry.project_name
                }
                for entry in leaderboard_data.entries
            ]
        }
        logger.info(f"Leaderboard data fetched for batch {batch['name']}")
    except Exception as e:
        logger.error(f"Failed to fetch leaderboard data for batch: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate leaderboard: {str(e)}")

    # Send leaderboard to each team
    successful_sends = 0
    failed_sends = 0
    details = []
    
    for team in teams:
        team_id = team["id"]
        team_name = team["team_name"]
        
        try:
            # Get students for this team
            students_response = supabase.table("students").select("email").eq("team_id", team_id).execute()
            students = students_response.data or []
            
            # Check why we have no emails
            if not students:
                failed_sends += 1
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "status": "failed",
                    "error": "No students are linked to this team. Please add students first."
                })
                continue
                
            # Filter valid emails
            student_emails = [s.get("email") for s in students if s.get("email")]
            if not student_emails:
                failed_sends += 1
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "status": "failed",
                    "error": "Students are linked, but none have a registered email address."
                })
                continue
                
            # Generate specific leaderboard PDF for this team
            team_leaderboard_pdf_bytes = generate_leaderboard_pdf(leaderboard_dict, team_id)

            # Create filename
            safe_team_name = team_name.replace(' ', '_').replace('/', '_')[:30]
            leaderboard_filename = f"{safe_team_name}_leaderboard_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
            
            # Send email to each student
            sent_count = 0
            failed_emails = []
            
            for email in student_emails:
                try:
                    subject = EmailTemplates.leaderboard_only_subject(batch["name"])
                    email_body_dict = EmailTemplates.leaderboard_only_body(batch["name"], team_name)
                    
                    if not dry_run:
                        send_email_with_attachment(
                            subject=subject,
                            body_text=email_body_dict["text"],
                            html_body=email_body_dict["html"],
                            to_email=email,
                            attachment_bytes=team_leaderboard_pdf_bytes,
                            attachment_filename=leaderboard_filename
                        )
                        # Small delay between individual emails only if actually sending
                        await asyncio.sleep(0.5)
                    
                    sent_count += 1
                except Exception as e:
                    print(f"Failed to {'send' if not dry_run else 'verify'} email to {email}: {e}")
                    failed_emails.append(email)
            
            # Larger delay between teams only if actually sending
            if not dry_run:
                await asyncio.sleep(2.0)
            
            if sent_count > 0:
                successful_sends += 1
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "status": "success",
                    "sentTo": sent_count,
                    "failedEmails": failed_emails if failed_emails else None
                })
            else:
                failed_sends += 1
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "status": "failed",
                    "error": f"Failed to send to any recipients: {', '.join(failed_emails)}"
                })
        
        except Exception as e:
            failed_sends += 1
            details.append({
                "teamId": team_id,
                "teamName": team_name,
                "status": "failed",
                "error": str(e)
            })
    
    return {
        "success": True,
        "message": f"{'Verified' if dry_run else 'Sent'} leaderboard for {successful_sends} out of {len(teams)} teams",
        "batchName": batch["name"],
        "totalTeams": len(teams),
        "successfulSends": successful_sends,
        "failedSends": failed_sends,
        "dryRun": dry_run,
        "details": details
    }


@router.get("/batch/{batchId}/leaderboard")
async def get_batch_leaderboard_pdf(
    batchId: str = Path(..., description="Batch ID"),
    format: Optional[str] = Query("pdf", description="Format: json or pdf"),
    current_user: dict = Depends(get_current_user)
):
    """
    Generate batch leaderboard report.
    Returns JSON data or PDF based on format parameter.
    Admin, mentor, or student can access.
    """
    supabase = get_supabase()
    
    # Verify batch exists
    batch_response = supabase.table("batches").select("*").eq("id", batchId).execute()
    if not batch_response.data:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    batch = batch_response.data[0]
    
    # Get leaderboard data
    leaderboard_service = LeaderboardService()
    
    try:
        leaderboard_data = await leaderboard_service.get_full_batch_leaderboard(
            batch_id=batchId,
            limit=None  # Get all teams
        )
        
        if not leaderboard_data:
            raise HTTPException(
                status_code=404,
                detail="No leaderboard data available for this batch"
            )
        
        # Convert to dict format
        leaderboard_dict = {
            "batch_name": leaderboard_data.batch_name,
            "generated_at": leaderboard_data.generated_at.isoformat(),
            "total_teams": leaderboard_data.total_teams,
            "entries": [
                {
                    "rank": entry.rank,
                    "team_id": entry.team_id,
                    "team_name": entry.team_name,
                    "overall_score": entry.overall_score
                }
                for entry in leaderboard_data.entries
            ]
        }
        
        # Handle PDF format
        if format == "pdf":
            try:
                # Determine recipient team ID if user is a student
                recipient_team_id = None
                if current_user.role == "student":
                    # Get user's team
                    user_id = str(current_user.user_id)
                    student_response = supabase.table("students").select(
                        "team_id"
                    ).eq("email", current_user.email).execute()
                    
                    if student_response.data:
                        recipient_team_id = student_response.data[0].get("team_id")
                
                pdf_bytes = generate_leaderboard_pdf(leaderboard_dict, recipient_team_id)
                
                # Create filename
                safe_batch_name = batch["name"].replace(' ', '_').replace('/', '_')[:30]
                filename = f"{safe_batch_name}_leaderboard_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
                
                return StreamingResponse(
                    io.BytesIO(pdf_bytes),
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f'attachment; filename="{filename}"'
                    }
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to generate PDF: {str(e)}"
                )
        
        # Return JSON
        return leaderboard_dict
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating leaderboard: {str(e)}"
        )
