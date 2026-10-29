"""
Commit forensics module - Detects fake commits, AI tool usage, and suspicious patterns.
"""

from .ai_detection import detect_ai_bots_in_contributors, detect_ai_tool_mentions
from .suspicious_patterns import (
    is_suspicious_author_name,
    is_generic_commit_message,
    detect_superhuman_speed,
)
from .contribution_analysis import (
    analyze_contribution_balance,
    calculate_consistency_metrics,
)

__all__ = [
    "detect_ai_bots_in_contributors",
    "detect_ai_tool_mentions",
    "is_suspicious_author_name",
    "is_generic_commit_message",
    "detect_superhuman_speed",
    "analyze_contribution_balance",
    "calculate_consistency_metrics",
]
