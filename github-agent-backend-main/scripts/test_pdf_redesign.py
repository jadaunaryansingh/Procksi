"""
Test script: Generate sample PDFs to verify the redesigned layouts.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.api.backend.utils.leaderboard_pdf_generator import generate_leaderboard_pdf
from src.api.backend.utils.pdf_generator import generate_team_report_pdf
from datetime import datetime

# ============ Test Leaderboard PDF ============
leaderboard_data = {
    "batch_name": "CEA - AIML & Hons Project 2025",
    "generated_at": datetime.utcnow().isoformat(),
    "total_teams": 5,
    "entries": [
        {"rank": 1, "team_id": "t1", "team_name": "Team Alpha", "project_name": "SmartCampus AI", "overall_score": 82.3, "report_json": {}},
        {"rank": 2, "team_id": "t2", "team_name": "Team Beta", "project_name": "EduTrack", "overall_score": 75.1, "report_json": {}},
        {"rank": 3, "team_id": "t3", "team_name": "Team Gamma", "project_name": "HealthSync", "overall_score": 68.9, "report_json": {}},
        {"rank": 4, "team_id": "t4", "team_name": "Team Delta", "project_name": "CodeReview Bot", "overall_score": 45.2, "report_json": {}},
        {"rank": 5, "team_id": "t5", "team_name": "Team Epsilon", "project_name": "ChatHelper", "overall_score": 22.7, "report_json": {}},
    ]
}

pdf_bytes = generate_leaderboard_pdf(leaderboard_data, recipient_team_id="t3")
out_path = os.path.join(os.path.dirname(__file__), "test_leaderboard.pdf")
with open(out_path, "wb") as f:
    f.write(pdf_bytes)
print(f"✅ Leaderboard PDF: {out_path} ({len(pdf_bytes)} bytes)")

# ============ Test Report PDF ============
report_data = {
    "teamName": "Team Alpha",
    "projectName": "SmartCampus AI",
    "repoUrl": "https://github.com/team-alpha/smart-campus",
    "generatedAt": datetime.utcnow().isoformat(),
    "healthStatus": "on_track",
    "teamMembers": [
        {"name": "Alice"}, {"name": "Bob"}, {"name": "Charlie"}
    ],
    "problemStatement": "Build an AI-powered campus management system with attendance tracking, resource allocation, and smart scheduling.",
    "analysis": {
        "totalScore": 82.3,
        "qualityScore": 78.5,
        "securityScore": 85.0,
        "originalityScore": 72.1,
        "architectureScore": 80.0,
        "documentationScore": 65.0,
        "effortScore": 90.2,
        "implementationScore": 0,
        "engineeringScore": 75.0,
    },
    "codeMetrics": {
        "totalFiles": 142,
        "totalLinesOfCode": 18450,
        "languagesWithPct": {"Python": 62.5, "TypeScript": 28.3, "CSS": 9.2},
        "techStack": ["FastAPI", "React"],
        "frameworks": ["Next.js", "Supabase"],
        "architecturePattern": "Microservices",
    },
    "maturity": {"hasTests": True, "testFiles": 12, "hasCI": True, "hasDocker": True, "hasReadme": True},
    "commits": {
        "total": 156,
        "contributors": [
            {"name": "Alice", "commits": 85, "additions": 12400, "deletions": 3200, "contributionPct": 54.5},
            {"name": "Bob", "commits": 45, "additions": 5600, "deletions": 1800, "contributionPct": 28.8},
            {"name": "Charlie", "commits": 26, "additions": 3100, "deletions": 900, "contributionPct": 16.7},
        ],
        "recentCommits": [
            {"message": "feat: add attendance tracking module", "author": "Alice", "date": "2025-02-20", "sha": "abc1234"},
            {"message": "fix: resolve login redirect loop", "author": "Bob", "date": "2025-02-19", "sha": "def5678"},
            {"message": "docs: update README with setup guide", "author": "Charlie", "date": "2025-02-18", "sha": "ghi9012"},
        ]
    },
    "aiAnalysis": {
        "aiGeneratedPercentage": 15.3,
        "verdict": "Genuine",
        "features": ["Attendance Tracking", "Smart Scheduling", "Resource Allocation", "Dashboard"],
        "positiveFeedback": "Well-structured codebase with good separation of concerns and consistent coding patterns.",
        "constructiveFeedback": "Could benefit from more comprehensive error handling and better input validation.",
        "suggestedFeatures": [
            {"feature_name": "Push Notifications", "priority": "High", "reason": "Important for real-time alerts", "implementation_hint": "Use Firebase Cloud Messaging"},
        ],
        "overallRecommendation": "Strong project with good fundamentals. Focus on testing coverage and error handling to reach production readiness.",
    },
    "security": {
        "score": 85.0,
        "secretsScore": 90.0,
        "practicesScore": 80.0,
        "secretsDetected": 1,
        "leaks": [
            {"type": "API Key", "path": "src/config.py", "line_number": 12, "severity": "high", "confidence": 0.95},
        ],
        "bestPractices": [
            {"practice_name": ".gitignore configured", "status": "implemented", "severity": "high"},
            {"practice_name": "Environment variables", "status": "implemented", "severity": "high"},
            {"practice_name": "Input validation", "status": "not_implemented", "severity": "medium"},
        ],
        "recommendations": [
            {"title": "Rotate exposed API key", "description": "The API key in config.py should be rotated immediately.", "priority": 9},
        ],
    },
    "riskyFiles": [
        {"file_path": "src/utils/helpers.py", "ai_percentage": 72, "risk_level": "High"},
    ],
    "riskFlags": ["Single API key detected in source code"],
}

pdf_bytes = generate_team_report_pdf(report_data)
out_path = os.path.join(os.path.dirname(__file__), "test_report.pdf")
with open(out_path, "wb") as f:
    f.write(pdf_bytes)
print(f"✅ Report PDF: {out_path} ({len(pdf_bytes)} bytes)")
