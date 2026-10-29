from src.core.agent import calculate_penalty_multiplier
from src.api.backend.utils.student_report_fields import build_student_report_fields


def test_ai_bot_detection_forces_fake_penalty():
    fake_multiplier, quality_multiplier = calculate_penalty_multiplier(
        fake_commit_ratio=0.0,
        quality_issue_ratio=0.0,
        has_ai_bots=True,
    )
    assert fake_multiplier == 0.4
    assert quality_multiplier == 1.0


def test_ai_bot_majority_applies_heavy_penalty():
    fake_multiplier, quality_multiplier = calculate_penalty_multiplier(
        fake_commit_ratio=0.0,
        quality_issue_ratio=0.0,
        has_ai_bots=True,
        ai_bot_share=81.6,
    )
    assert fake_multiplier == 0.2
    assert quality_multiplier == 1.0


def test_student_report_contains_critical_meet_mentor_warning_for_ai_bots():
    report_json = {
        "commit_details": {
            "fake_commit_count": 0,
            "fake_commit_ratio": 0.0,
            "commit_health": "Critical",
            "ai_bot_detection": {
                "has_ai_bots": True,
                "ai_bot_contributors": [{"name": "github-actions", "tool": "GITHUB-ACTIONS"}],
            },
        },
        "penalty_info": {
            "penalty_multiplier": 0.2,
            "has_ai_bots": True,
            "ai_bot_share": 81.6,
            "heavy_ai_bot_penalty": True,
        },
    }

    fields = build_student_report_fields(report_json, total_commits_count=38)
    warning = fields["commitQuality"]["criticalWarning"]
    score_penalty = fields["commitQuality"]["scorePenalty"]
    detected_issues = fields["commitQuality"]["detectedIssues"]
    ai_bots = fields["commitQuality"]["aiBotContributors"]
    automation_penalty = fields["commitQuality"]["automationPenalty"]

    assert warning["show"] is True
    assert "heavy penalty" in warning["message"].lower()
    assert "meet your mentor" in warning["message"].lower()
    assert "meet your mentor" in score_penalty["recommendation"].lower()
    assert any(i.get("type") == "Automation Commit Authors Detected" for i in detected_issues)
    assert len(ai_bots) == 1
    assert automation_penalty["applied"] is True
    assert automation_penalty["automationShare"] == 81.6


def test_ai_assisted_coauthored_style_is_allowed_when_primary_author_is_student():
    report_json = {
        "commit_details": {
            "fake_commit_count": 0,
            "fake_commit_ratio": 0.0,
            "commit_health": "Healthy",
            "ai_bot_detection": {
                "has_ai_bots": False,
                "ai_bot_contributors": [],
            },
            "ai_tool_mentions": [
                {"tool": "github copilot", "author": "student-name", "message": "feat: update\n\nCo-authored-by: github-copilot"}
            ],
        },
        "penalty_info": {
            "penalty_multiplier": 1.0,
            "has_ai_bots": False,
        },
    }

    fields = build_student_report_fields(report_json, total_commits_count=12)
    warning = fields["commitQuality"]["criticalWarning"]
    policy = fields["commitQuality"]["aiAssistancePolicy"]
    marks = fields["marksDeduction"]

    assert warning["show"] is False
    assert policy["isAllowed"] is True
    assert "allowed" in policy["note"].lower()
    assert marks["applied"] is False
