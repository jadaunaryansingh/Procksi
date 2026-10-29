"""
Helpers for student-facing report fields.
Ensures fake commit details, AI tool detection, and score-deduction reasons
are consistently available in reports and PDFs.
"""

from typing import Any, Dict, List


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def build_student_report_fields(report_json: Dict[str, Any], total_commits_count: int) -> Dict[str, Any]:
    """
    Build student-facing commit quality and deduction fields from report_json.

    Returns a dict with:
    - commitQuality
    - marksDeduction
    """
    commit_details = report_json.get("commit_details", {}) if isinstance(report_json, dict) else {}
    penalty_info = report_json.get("penalty_info", {}) if isinstance(report_json, dict) else {}

    fake_commits_list = commit_details.get("fake_commits", []) if isinstance(commit_details, dict) else []
    fake_commit_count = _to_int(commit_details.get("fake_commit_count", 0))
    fake_commit_ratio = _to_float(commit_details.get("fake_commit_ratio", 0.0))
    real_commit_count = _to_int(commit_details.get("real_commit_count", 0))
    total_real_additions = _to_int(commit_details.get("total_real_additions", 0))
    total_fake_additions = _to_int(commit_details.get("total_fake_additions", 0))
    commit_health = str(commit_details.get("commit_health", "Healthy"))
    inflation_ratio = _to_float(commit_details.get("inflation_ratio", 1.0), 1.0)
    quality_issue_ratio = _to_float(commit_details.get("quality_issue_ratio", 0.0))

    ai_tools_detected = set()

    ai_bot_detection = commit_details.get("ai_bot_detection", {}) if isinstance(commit_details, dict) else {}
    ai_bot_contributors = []
    if isinstance(ai_bot_detection, dict):
        ai_bot_contributors = ai_bot_detection.get("ai_bot_contributors", []) or []
        for bot in ai_bot_contributors:
            if not isinstance(bot, dict):
                continue
            tool_name = bot.get("tool")
            contributor_name = bot.get("name")
            if tool_name:
                ai_tools_detected.add(str(tool_name))
            elif contributor_name:
                ai_tools_detected.add(str(contributor_name))

    for mention in commit_details.get("ai_tool_mentions", []) or []:
        if not isinstance(mention, dict):
            continue
        tool_name = mention.get("tool")
        if tool_name:
            ai_tools_detected.add(str(tool_name))

    ai_tools_detected_list: List[str] = sorted(ai_tools_detected)
    has_ai_bots = False
    if isinstance(ai_bot_detection, dict):
        has_ai_bots = bool(
            ai_bot_detection.get("has_ai_bots")
            or (ai_bot_detection.get("ai_bot_contributors") or [])
        )

    # Prefer the full combined multiplier from penalty_info when available.
    total_penalty_multiplier = _to_float(penalty_info.get("penalty_multiplier", 1.0), 1.0)
    inactive_penalty = _to_float(penalty_info.get("inactive_penalty", 1.0), 1.0)
    outsourcing_penalty = _to_float(penalty_info.get("outsourcing_penalty", 1.0), 1.0)
    team_adjustment_multiplier = _to_float(penalty_info.get("team_adjustment_multiplier", 1.0), 1.0)
    days_inactive = _to_int(penalty_info.get("days_inactive", 0), 0)
    team_adjustment_reason = str(penalty_info.get("team_adjustment_reason", "N/A"))
    penalty_has_ai_bots = bool(penalty_info.get("has_ai_bots", False))
    penalty_ai_bot_share = _to_float(penalty_info.get("ai_bot_share", 0.0))
    heavy_ai_bot_penalty = bool(penalty_info.get("heavy_ai_bot_penalty", False))
    # Policy: Penalize only when automated/bot accounts are primary commit authors.
    # AI-assisted work with a student as primary author (e.g., co-authored-by trailer)
    # is informational and should not trigger this critical violation.
    ai_bot_violation = has_ai_bots or penalty_has_ai_bots
    ai_assistance_allowed = bool(ai_tools_detected_list) and not ai_bot_violation
    automation_commit_count = sum(
        _to_int(bot.get("commits", 0))
        for bot in ai_bot_contributors
        if isinstance(bot, dict)
    )
    computed_ai_bot_share = sum(
        _to_float(bot.get("share", 0.0))
        for bot in ai_bot_contributors
        if isinstance(bot, dict)
    )
    ai_bot_share = penalty_ai_bot_share if penalty_ai_bot_share > 0 else computed_ai_bot_share
    ai_bot_majority = heavy_ai_bot_penalty or ai_bot_share > 50.0

    reasons: List[str] = []

    if ai_bot_violation:
        reasons.append(
            "Critical violation: automated/bot accounts are primary commit authors (for example github-actions). Meet your mentor immediately for review."
        )
    if ai_bot_majority:
        reasons.append(
            f"Heavy penalty applied: automation-authored commits are {ai_bot_share:.1f}% (>50%)."
        )

    if fake_commit_ratio >= 30:
        reasons.append(
            f"High fake commit ratio ({fake_commit_ratio:.1f}%) triggered repository quality penalty."
        )
    elif fake_commit_ratio >= 10:
        reasons.append(
            f"Moderate fake commit ratio ({fake_commit_ratio:.1f}%) reduced affected score dimensions."
        )

    if quality_issue_ratio >= 70:
        reasons.append(
            f"High quality-issue ratio ({quality_issue_ratio:.1f}%) reduced repository quality multiplier."
        )
    elif quality_issue_ratio >= 40:
        reasons.append(
            f"Moderate quality-issue ratio ({quality_issue_ratio:.1f}%) reduced repository quality multiplier."
        )

    if inactive_penalty < 1.0:
        reasons.append(
            f"Inactivity penalty applied ({days_inactive} inactive days)."
        )

    if outsourcing_penalty < 1.0:
        reasons.append("Unverified contributor/outsourcing risk penalty applied.")

    if team_adjustment_multiplier < 1.0:
        reasons.append(f"Team-size adjustment penalty applied: {team_adjustment_reason}.")

    if total_penalty_multiplier < 1.0 and not reasons:
        reasons.append(
            "Score multiplier penalty applied based on repository quality checks."
        )

    detected_issues: List[Dict[str, Any]] = []
    if fake_commit_count > 0:
        detected_issues.append({
            "type": "Fake Commits Detected",
            "count": fake_commit_count,
            "percentage": round(fake_commit_ratio, 1),
            "severity": "Critical" if fake_commit_ratio > 50 else "High" if fake_commit_ratio > 30 else "Medium" if fake_commit_ratio > 10 else "Low",
            "description": f"Found {fake_commit_count} commits that are flagged as suspicious or low-quality.",
        })
    if ai_bot_violation:
        detected_issues.append({
            "type": "Automation Commit Authors Detected",
            "count": automation_commit_count,
            "percentage": round(ai_bot_share, 1),
            "severity": "Critical",
            "description": (
                "Automated accounts (for example github-actions) were used as primary commit authors."
                + (" Heavy penalty triggered because automation share is above 50%." if ai_bot_majority else "")
            ),
        })

    marks_deducted_percentage = round((1.0 - total_penalty_multiplier) * 100.0, 1) if total_penalty_multiplier < 1.0 else 0.0
    deduction_applied = total_penalty_multiplier < 1.0

    example_fake_commits = []
    for commit in fake_commits_list[:5]:
        if not isinstance(commit, dict):
            continue
        sha = (commit.get("hash") or commit.get("hexsha") or "")[:7]
        message = (commit.get("msg") or commit.get("message") or "No message")[:100]
        example_fake_commits.append({
            "sha": sha,
            "message": message,
            "reasons": commit.get("reasons", []),
            "additions": _to_int(commit.get("additions", 0)),
            "fakeAdditions": _to_int(commit.get("fake_additions", 0)),
            "files": (commit.get("files_changed", []) or [])[:5],
        })

    commit_quality = {
        "healthStatus": commit_health,
        "totalCommits": _to_int(total_commits_count, 0),
        "realCommits": real_commit_count,
        "fakeCommits": fake_commit_count,
        "fakeCommitPercentage": round(fake_commit_ratio, 1),
        "realAdditions": total_real_additions,
        "fakeAdditions": total_fake_additions,
        "inflationRatio": round(inflation_ratio, 2),
        "aiToolsDetected": ai_tools_detected_list,
        "aiToolsDetectedCount": len(ai_tools_detected_list),
        "aiBotContributors": ai_bot_contributors if ai_bot_violation else [],
        "detectedIssues": detected_issues,
        "exampleFakeCommits": example_fake_commits,
        "scorePenalty": {
            "applied": deduction_applied,
            "multiplier": round(total_penalty_multiplier, 3),
            "description": " | ".join(reasons) if reasons else "No score deduction applied.",
            "affectedDimensions": ["Implementation", "Quality", "Organization", "Effort"] if deduction_applied else [],
            "recommendation": (
                "Critical: meet your mentor immediately and stop automated commits before re-analysis."
                if ai_bot_violation
                else "Clean fake commits, improve commit quality, and maintain continuous activity to recover marks."
                if deduction_applied
                else "Keep maintaining good repository hygiene."
            ),
        },
        "criticalWarning": {
            "show": ai_bot_violation,
            "severity": "Critical" if ai_bot_violation else "None",
            "title": "Critical Repository Violation",
            "message": (
                (
                    f"Automated/bot commit authors detected ({ai_bot_share:.1f}% automation share). "
                    "Heavy penalty applied. Meet your mentor immediately."
                )
                if ai_bot_majority
                else "Automated/bot commit authors detected (for example github-actions). Meet your mentor immediately."
                if ai_bot_violation
                else ""
            ),
            "action": "Meet mentor immediately" if ai_bot_violation else "",
        },
        "automationPenalty": {
            "applied": ai_bot_majority,
            "automationShare": round(ai_bot_share, 1),
            "threshold": 50.0,
            "severity": "Critical" if ai_bot_majority else "High" if ai_bot_violation else "None",
            "description": (
                "Heavy penalty applied because automation-authored commits exceed 50%."
                if ai_bot_majority
                else "Automation-authored commits detected."
                if ai_bot_violation
                else "No automation penalty."
            ),
        },
        "aiAssistancePolicy": {
            "isAllowed": ai_assistance_allowed,
            "note": (
                "AI-assisted co-authored commits are allowed when a student remains the primary commit author."
                if ai_assistance_allowed
                else ""
            ),
        },
    }

    marks_deduction = {
        "applied": deduction_applied,
        "penaltyMultiplier": round(total_penalty_multiplier, 3),
        "marksDeductedPercentage": marks_deducted_percentage,
        "reason": " | ".join(reasons) if reasons else "No deduction.",
        "reasonDetails": reasons,
    }

    return {
        "commitQuality": commit_quality,
        "marksDeduction": marks_deduction,
    }
