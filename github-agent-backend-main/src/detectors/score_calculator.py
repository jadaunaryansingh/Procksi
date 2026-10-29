"""
Security Score Calculator

This module calculates overall security scores based on detected
secret leaks and missing best practices.
"""

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class SecurityScore:
    """Security score with component breakdown."""
    overall_score: int  # 0-100
    secrets_score: int  # 0-100
    practices_score: int  # 0-100
    penalty_breakdown: Dict[str, int]


# Penalty weights by severity
SEVERITY_PENALTIES = {
    "critical": 10,
    "high": 5,
    "medium": 2,
    "low": 1
}


def calculate_secrets_score(secrets: List[Dict]) -> int:
    """
    Calculate score based on secret leaks.
    
    Args:
        secrets: List of detected secret leaks
        
    Returns:
        Score from 0-100 (100 = no secrets)
    """
    if not secrets:
        return 100
    
    total_penalty = 0
    
    for secret in secrets:
        severity = secret.get("severity", "medium")
        penalty = SEVERITY_PENALTIES.get(severity, 2)
        
        # Adjust penalty based on confidence
        confidence = secret.get("confidence", 1.0)
        adjusted_penalty = int(penalty * confidence)
        
        total_penalty += adjusted_penalty
    
    # Calculate score (start at 100, subtract penalties)
    score = max(0, 100 - total_penalty)
    
    return score


def calculate_practices_score(practices: List) -> int:
    """
    Calculate score based on security best practices.
    
    Args:
        practices: List of BestPracticeResult objects
        
    Returns:
        Score from 0-100 (100 = all practices implemented)
    """
    if not practices:
        return 100
    
    total_penalty = 0
    
    for practice in practices:
        # Only penalize missing or partial implementations
        if practice.status == "implemented":
            continue
        
        severity = practice.severity
        base_penalty = SEVERITY_PENALTIES.get(severity, 2)
        
        # Partial implementations get half penalty
        if practice.status == "partial":
            penalty = base_penalty // 2
        else:  # missing
            penalty = base_penalty
        
        total_penalty += penalty
    
    # Calculate score
    score = max(0, 100 - total_penalty)
    
    return score


def calculate_security_score(secrets: List[Dict], practices: List) -> SecurityScore:
    """
    Calculate overall security score with breakdown.
    
    Args:
        secrets: List of detected secret leaks
        practices: List of BestPracticeResult objects
        
    Returns:
        SecurityScore with component breakdown
    """
    # Calculate component scores
    secrets_score = calculate_secrets_score(secrets)
    practices_score = calculate_practices_score(practices)
    
    # Calculate overall score (weighted average)
    # Secrets are weighted more heavily (60%) than practices (40%)
    overall_score = int(secrets_score * 0.6 + practices_score * 0.4)
    
    # Ensure minimum score of 20
    overall_score = max(20, overall_score)
    
    # Build penalty breakdown
    penalty_breakdown = {
        "secrets_penalty": 100 - secrets_score,
        "practices_penalty": 100 - practices_score,
        "total_penalty": 100 - overall_score
    }
    
    # Add severity breakdown for secrets
    if secrets:
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for secret in secrets:
            severity = secret.get("severity", "medium")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        penalty_breakdown["secrets_by_severity"] = severity_counts
    
    # Add status breakdown for practices
    if practices:
        status_counts = {"missing": 0, "partial": 0, "implemented": 0}
        for practice in practices:
            status_counts[practice.status] = status_counts.get(practice.status, 0) + 1
        
        penalty_breakdown["practices_by_status"] = status_counts
    
    return SecurityScore(
        overall_score=overall_score,
        secrets_score=secrets_score,
        practices_score=practices_score,
        penalty_breakdown=penalty_breakdown
    )
