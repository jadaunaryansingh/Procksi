import json
from datetime import datetime

from src.api.backend.database import get_supabase
from src.api.backend.utils.pdf_generator import generate_team_report_pdf
from src.api.backend.utils.student_report_fields import build_student_report_fields

team_id = "929a0c7c-a637-4c9f-8d6a-b574310e3bc4"

supabase = get_supabase()
team = supabase.table("teams").select("*").eq("id", team_id).single().execute().data

report_json = team.get("report_json") or {}
if isinstance(report_json, str):
    report_json = json.loads(report_json)

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

total_commits_count = team.get("total_commits") or forensics.get("total_commits", 0) or 1
contributors_with_pct = []
for c in author_stats:
    if isinstance(c, dict):
        commit_count = c.get("commits", c.get("commit_count", 0)) or 0
        contribution_pct = round((commit_count / total_commits_count) * 100, 1) if total_commits_count > 0 else 0
        contributors_with_pct.append(
            {
                "name": c.get("author", c.get("name", "Unknown")),
                "commits": commit_count,
                "additions": c.get("additions", c.get("lines_added", c.get("lines_changed", 0))),
                "deletions": c.get("deletions", c.get("lines_deleted", 0)),
                "contributionPct": contribution_pct,
            }
        )

student_fields = build_student_report_fields(report_json, total_commits_count)

report = {
    "teamName": team.get("team_name", "Unknown Team"),
    "projectName": (team.get("repo_url") or "").rstrip("/").rstrip(".git").split("/")[-1],
    "repoUrl": team.get("repo_url", ""),
    "generatedAt": datetime.utcnow().isoformat(),
    "analysis": {
        "totalScore": team.get("total_score") or 0,
        "qualityScore": team.get("quality_score") or 0,
        "securityScore": team.get("security_score") or 0,
        "originalityScore": team.get("originality_score") or 0,
        "architectureScore": team.get("architecture_score") or 0,
        "documentationScore": team.get("documentation_score") or 0,
        "effortScore": (report_json.get("scores") or {}).get("effort", 0),
        "implementationScore": (report_json.get("scores") or {}).get("implementation", 0),
        "engineeringScore": (report_json.get("scores") or {}).get("engineering", 0),
    },
    "commits": {
        "total": total_commits_count,
        "contributors": contributors_with_pct,
        "recentCommits": ((report_json.get("commit_details") or {}).get("recent_commits") or [])[:10],
    },
    "codeMetrics": {
        "totalFiles": len(report_json.get("files", []) or []),
        "totalLinesOfCode": 0,
        "languages": list((report_json.get("languages", {}) or {}).keys()) if isinstance(report_json.get("languages", {}), dict) else (report_json.get("languages", []) or []),
        "languagesWithPct": report_json.get("languages", {}) if isinstance(report_json.get("languages", {}), dict) else {},
        "architecturePattern": ((report_json.get("structure") or {}).get("architecture") or "Unknown"),
        "techStack": ((report_json.get("judge") or {}).get("tech_stack_observed") or []),
        "frameworks": report_json.get("stack", []) or [],
    },
    "security": report_json.get("security", {}) or {},
    "aiAnalysis": {
        "aiGeneratedPercentage": ((report_json.get("llm_detection") or {}).get("overall_percentage", 0)),
        "verdict": ((report_json.get("judge") or {}).get("verdict", "Unknown")),
        "verdictReasoning": ((report_json.get("judge") or {}).get("verdict_reasoning", "")),
        "features": ((report_json.get("judge") or {}).get("features", [])),
        "positiveFeedback": ((report_json.get("judge") or {}).get("positive_feedback", "")),
        "constructiveFeedback": ((report_json.get("judge") or {}).get("constructive_feedback", "")),
        "featureAnalysis": ((report_json.get("judge") or {}).get("feature_analysis", [])),
        "suggestedFeatures": ((report_json.get("judge") or {}).get("suggested_features", [])),
        "overallRecommendation": ((report_json.get("judge") or {}).get("overall_recommendation", "")),
    },
    "productAnalysis": ((report_json.get("judge") or {}).get("product_analysis", {})),
    "riskyFiles": (report_json.get("files", []) or [])[:10],
    "maturity": report_json.get("maturity", {}) or {},
    "healthStatus": team.get("health_status", "on_track"),
    "riskFlags": team.get("risk_flags", []) or [],
    "lastAnalyzedAt": team.get("last_analyzed_at") or team.get("analyzed_at"),
    "commitQuality": student_fields["commitQuality"],
    "marksDeduction": student_fields["marksDeduction"],
}

pdf = generate_team_report_pdf(report)
print("OK PDF_BYTES", len(pdf))
