from src.api.backend.services.analyzer_service import AnalyzerService


def test_merge_repository_reports_uses_weighted_scores_and_combines_metadata():
    reports = [
        {
            "repo_url": "https://github.com/org/frontend-a",
            "scores": {
                "originality": 80,
                "quality": 70,
                "security": 90,
                "effort": 60,
                "implementation": 40,
                "engineering": 50,
                "organization": 65,
                "documentation": 75,
            },
            "final_scores": {"total_score": 65.0},
            "commit_count": 10,
            "file_count": 20,
            "lines_of_code": 100,
            "team": {"alice": {"commits": 6}, "bob": {"commits": 4}},
            "forensics": {"author_stats": {"alice": {"commits": 6}, "bob": {"commits": 4}}},
            "issues": [{"type": "quality", "severity": "medium"}],
            "positive_feedback": "Frontend flow is clear and responsive.",
            "constructive_feedback": "Add stronger loading states.",
            "overall_recommendation": "Polish the UI before release.",
            "verdict": "MVP",
            "verdict_reasoning": "Good user-facing work with small gaps.",
            "suggested_features": [{"feature_name": "Loading states"}],
        },
        {
            "repo_url": "https://github.com/org/frontend-b",
            "scores": {
                "originality": 60,
                "quality": 50,
                "security": 95,
                "effort": 70,
                "implementation": 80,
                "engineering": 75,
                "organization": 55,
                "documentation": 85,
            },
            "final_scores": {"total_score": 72.5},
            "commit_count": 20,
            "file_count": 30,
            "lines_of_code": 300,
            "team": {"alice": {"commits": 8}, "carol": {"commits": 12}},
            "forensics": {"author_stats": {"alice": {"commits": 8}, "carol": {"commits": 12}}},
            "issues": [{"type": "security", "severity": "high"}],
            "positive_feedback": "Backend endpoints are structured well.",
            "constructive_feedback": "Add auth and validation coverage.",
            "overall_recommendation": "Harden API boundaries.",
            "verdict": "Ready",
            "verdict_reasoning": "Backend is more complete than the frontend half.",
            "suggested_features": [{"feature_name": "Auth middleware"}],
        },
    ]

    merged = AnalyzerService._merge_repository_reports(
        reports,
        [r["repo_url"] for r in reports],
    )

    assert merged["repo_url"] == "https://github.com/org/frontend-a"
    assert merged["related_repositories"] == [
        "https://github.com/org/frontend-a",
        "https://github.com/org/frontend-b",
    ]
    assert merged["commit_count"] == 30
    assert merged["file_count"] == 50
    assert merged["lines_of_code"] == 400
    assert merged["scores"]["implementation"] == 70.0
    assert merged["scores"]["quality"] == 55.0
    assert merged["final_scores"]["total_score"] > 0
    assert merged["team"]["alice"]["commits"] == 14
    assert merged["team"]["bob"]["commits"] == 4
    assert merged["team"]["carol"]["commits"] == 12
    assert len(merged["issues"]) == 2
    assert len(merged["repo_analysis_breakdown"]) == 2
    assert "Frontend flow is clear and responsive." in merged["positive_feedback"]
    assert "Backend endpoints are structured well." in merged["positive_feedback"]
    assert "Add stronger loading states." in merged["constructive_feedback"]
    assert "Add auth and validation coverage." in merged["constructive_feedback"]
    assert len(merged["suggested_features"]) == 2
    assert len(merged["repo_verdicts"]) == 2
    assert merged["repo_analysis_breakdown"][0]["positive_feedback"] == "Frontend flow is clear and responsive."
    assert merged["repo_analysis_breakdown"][1]["constructive_feedback"] == "Add auth and validation coverage."


def test_merge_repository_reports_single_repo_keeps_report_shape():
    report = {
        "repo_url": "https://github.com/org/frontend-a",
        "scores": {
            "originality": 80,
            "quality": 70,
            "security": 90,
            "effort": 60,
            "implementation": 40,
            "engineering": 50,
            "organization": 65,
            "documentation": 75,
        },
        "final_scores": {"total_score": 65.0},
        "commit_count": 10,
        "file_count": 20,
        "lines_of_code": 100,
    }

    merged = AnalyzerService._merge_repository_reports([report], [report["repo_url"]])

    assert merged["repo_url"] == report["repo_url"]
    assert merged["related_repositories"] == [report["repo_url"]]
    assert merged["repo_analysis_breakdown"][0]["repo_url"] == report["repo_url"]

def test_merge_repository_reports_missing_scores():
    reports = [
        {
            "repo_url": "repo1",
            "scores": {
                "implementation": 90,
                "engineering": 100,
            },
            "lines_of_code": 100,
        },
        {
            "repo_url": "repo2",
            "scores": {
                "engineering": 80,
            },
            "lines_of_code": 100, # Same weight as repo1
        },
    ]

    merged = AnalyzerService._merge_repository_reports(reports, [r["repo_url"] for r in reports])

    # With equal weight, repo1 engineering=100 and repo2 engineering=80 average to 90
    assert merged["scores"]["engineering"] == 90.0
    
    # repo1 implementation=90, repo2 has no implementation. 
    # Must be 90, not 45.
    assert merged["scores"]["implementation"] == 90.0