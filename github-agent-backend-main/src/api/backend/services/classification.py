"""
Classification Service for Repository Privacy Detection

This module provides multi-signal classification of repository issues with
confidence scoring and fix suggestions.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import re
import requests

from .url_validation import validate_repo_url, URLValidationResult
from .github_id_matcher import match_github_ids, GitHubIDMatchResult


@dataclass
class ClassificationResult:
    """Result of repository issue classification.
    
    Attributes:
        error_type: Type of error ("private", "not_found", "invalid_url", "missing_url", "other")
        is_private: True if likely private, False if likely not found, None if other error
        confidence: Confidence score for the classification (0.0-1.0)
        reason: Human-readable explanation of the classification
        signals_used: List of signals used in classification (e.g., ["error_message", "url_pattern", "github_id_mismatch"])
        suggested_fixes: List of suggested fix URLs or instructions
    """
    error_type: str
    is_private: Optional[bool]
    confidence: float
    reason: str
    signals_used: List[str]
    suggested_fixes: List[str]


def check_repo_public(repo_url: Optional[str]) -> Optional[bool]:
    """
    Quick check if a GitHub repo is publicly accessible.
    Makes a lightweight HEAD request to the GitHub API.
    
    Returns:
        True if repo is confirmed public (HTTP 200)
        False if repo is confirmed private/not-found (HTTP 404/403)
        None if check failed (timeout, rate limit, etc.)
    """
    if not repo_url:
        return None
    try:
        # Extract owner/repo from URL
        match = re.search(r'github\.com[/:]([^/]+)/([^/.\s]+)', repo_url)
        if not match:
            return None
        owner, repo = match.group(1), match.group(2).rstrip('.git')
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        resp = requests.head(api_url, timeout=5, allow_redirects=True)
        if resp.status_code == 200:
            return True  # Confirmed public
        elif resp.status_code in (404, 403, 401):
            return False  # Confirmed inaccessible
        return None  # Unclear (rate limited, etc.)
    except Exception:
        return None  # Network error, can't determine


def calculate_confidence(
    error_message: Optional[str],
    url_validation: Optional[URLValidationResult],
    github_match: Optional[GitHubIDMatchResult]
) -> float:
    """
    Calculate confidence score based on signal strength.
    
    Confidence factors:
    - Error message specificity (0.0-0.4)
      - Explicit errors (403, auth failed): 0.4
      - Specific errors (404, not found): 0.3
      - Ambiguous errors (generic): 0.1
      - No error: 0.0
    - URL validation result (0.0-0.3)
      - Valid URL: 0.3
      - Invalid URL: 0.2 (invalid is also informative)
      - No URL: 0.0
    - GitHub ID matching (0.0-0.3)
      - Match: 0.3
      - Mismatch: 0.1 (mismatch suggests "not found" over "private")
      - No GitHub IDs: 0.0
    
    Total confidence: 0.0-1.0
    
    Args:
        error_message: The error message from analysis failure
        url_validation: Result of URL validation
        github_match: Result of GitHub ID matching
        
    Returns:
        Confidence score in range [0.0, 1.0]
    """
    confidence = 0.0
    
    # Factor 1: Error message specificity
    if error_message:
        error_lower = error_message.lower()
        
        # Explicit errors (authentication, permission)
        explicit_indicators = [
            "authentication failed",
            "permission denied",
            "403 forbidden",
            "access denied",
            "requires authentication"
        ]
        
        # Specific errors (404, not found)
        specific_indicators = [
            "404",
            "repository not found",
            "does not exist",
            "could not read from remote repository"
        ]
        
        if any(indicator in error_lower for indicator in explicit_indicators):
            confidence += 0.4
        elif any(indicator in error_lower for indicator in specific_indicators):
            confidence += 0.3
        else:
            # Generic or ambiguous error
            confidence += 0.1
    
    # Factor 2: URL validation
    if url_validation:
        if url_validation.is_valid:
            confidence += 0.3
        elif url_validation.error_type in ("missing_protocol", "wrong_platform", "invalid_format", "profile_url", "homepage_url"):
            # Invalid URL is informative - we know it's a URL problem
            confidence += 0.2
    
    # Factor 3: GitHub ID matching
    if github_match:
        if github_match.matches:
            # Owner matches a student - suggests private repo
            confidence += 0.3
        elif github_match.student_github_ids and not github_match.matches:
            # Owner doesn't match any student - suggests not found or wrong URL
            confidence += 0.1
    
    # Ensure confidence is in valid range
    return min(confidence, 1.0)


def classify_repo_issue(
    error_message: Optional[str],
    repo_url: Optional[str],
    team_id: str,
    student_github_ids: Optional[List[str]] = None
) -> ClassificationResult:
    """
    Classify repository issue using multiple signals.
    
    This function integrates three sources of information:
    1. Error message patterns (existing logic)
    2. URL validation result
    3. GitHub ID matching result
    
    Classification logic:
    - Missing URL: Confidence 1.0
    - Invalid URL format: Confidence 0.9-1.0
    - Private repository: Confidence 0.5-1.0 (based on signals)
    - Repository not found: Confidence 0.5-0.9 (based on signals)
    - Other errors: Confidence 0.0-0.5
    
    Args:
        error_message: The error message from analysis failure (optional)
        repo_url: The repository URL (optional)
        team_id: The team ID for GitHub ID matching
        
    Returns:
        ClassificationResult with confidence score and suggested fixes
        
    Examples:
        >>> classify_repo_issue("Authentication failed", "https://github.com/owner/repo", "team-123")
        ClassificationResult(error_type="private", is_private=True, confidence=1.0, ...)
        
        >>> classify_repo_issue("Repository not found", "https://github.com/wronguser/repo", "team-123")
        ClassificationResult(error_type="not_found", is_private=False, confidence=0.7, ...)
    """
    signals_used = []
    suggested_fixes = []
    
    # Signal 1: Check for missing URL
    if not repo_url or not repo_url.strip():
        return ClassificationResult(
            error_type="missing_url",
            is_private=None,
            confidence=1.0,
            reason="No repository URL provided",
            signals_used=["missing_url"],
            suggested_fixes=["Provide a valid GitHub repository URL"]
        )
    
    # Signal 2: URL validation
    url_validation = validate_repo_url(repo_url)
    signals_used.append("url_validation")
    
    # If URL is invalid, return immediately with high confidence
    if not url_validation.is_valid:
        # Generate fix suggestions based on error type
        if url_validation.error_type == "missing_protocol":
            suggested_fixes.append(f"https://{repo_url}")
        elif url_validation.error_type == "profile_url":
            # Extract username and suggest common repo names
            try:
                username = repo_url.strip("/").split("/")[-1]
                suggested_fixes.extend([
                    f"{repo_url}/project",
                    f"{repo_url}/assignment",
                    f"{repo_url}/team-project"
                ])
            except:
                suggested_fixes.append("Add repository name to the URL (e.g., /project)")
        elif url_validation.error_type == "homepage_url":
            suggested_fixes.append("Provide complete repository URL (e.g., https://github.com/username/repo)")
        elif url_validation.error_type == "wrong_platform":
            suggested_fixes.append("Use a GitHub repository URL (github.com)")
        
        # Determine confidence based on error type
        confidence = 1.0 if url_validation.error_type == "missing_protocol" else 0.9
        
        return ClassificationResult(
            error_type="invalid_url",
            is_private=None,
            confidence=confidence,
            reason=url_validation.reason,
            signals_used=signals_used,
            suggested_fixes=suggested_fixes
        )
    
    # Signal 3: GitHub ID matching (only if URL is valid)
    github_match = None
    try:
        github_match = match_github_ids(repo_url, team_id, student_github_ids=student_github_ids)
        signals_used.append("github_id_match")
    except Exception as e:
        # GitHub ID matching failed - continue without it
        print(f"GitHub ID matching failed: {e}")
    
    # Signal 4: Error message analysis
    if error_message:
        signals_used.append("error_message")
    
    # Calculate confidence score
    confidence = calculate_confidence(error_message, url_validation, github_match)
    
    # Now classify based on all signals
    if not error_message:
        # No error message - can't determine issue type
        return ClassificationResult(
            error_type="other",
            is_private=None,
            confidence=0.5,
            reason="No error message available",
            signals_used=signals_used,
            suggested_fixes=[]
        )
    
    error_lower = error_message.lower()
    
    # Check for explicit authentication/permission errors (definitely private)
    explicit_private_indicators = [
        "authentication failed",
        "permission denied",
        "403 forbidden",
        "access denied",
        "requires authentication"
    ]
    
    if any(indicator in error_lower for indicator in explicit_private_indicators):
        return ClassificationResult(
            error_type="private",
            is_private=True,
            confidence=min(confidence, 1.0),
            reason="Repository is private and requires authentication",
            signals_used=signals_used,
            suggested_fixes=["Make repository public in GitHub settings"]
        )
    
    # Check for ambiguous "repository not found" errors
    ambiguous_indicators = [
        "repository not found",
        "could not read from remote repository",
        "remote: repository not found"
    ]
    
    if any(indicator in error_lower for indicator in ambiguous_indicators):
        # Use GitHub ID matching to improve classification
        if github_match and github_match.matches:
            # Owner matches a student - likely private
            return ClassificationResult(
                error_type="private",
                is_private=True,
                confidence=min(confidence, 0.8),
                reason="Repository not accessible (likely private). Owner matches student GitHub ID.",
                signals_used=signals_used,
                suggested_fixes=["Make repository public in GitHub settings"]
            )
        elif github_match and github_match.student_github_ids and not github_match.matches:
            # Owner doesn't match any student - likely not found or wrong URL
            suggested_fixes = github_match.suggested_urls if github_match.suggested_urls else []
            return ClassificationResult(
                error_type="not_found",
                is_private=False,
                confidence=min(confidence, 0.7),
                reason=f"Repository not found. Owner '{github_match.owner}' doesn't match any student GitHub ID.",
                signals_used=signals_used,
                suggested_fixes=suggested_fixes
            )
        else:
            # No GitHub IDs or matching failed — check if repo is actually public
            is_public = check_repo_public(repo_url)
            if is_public is True:
                # Repo IS public — analysis failed for another reason (timeout, etc.)
                return ClassificationResult(
                    error_type="other",
                    is_private=False,
                    confidence=min(confidence, 0.8),
                    reason="Repository is public but analysis failed (possibly due to timeout or transient error)",
                    signals_used=signals_used + ["github_api_check"],
                    suggested_fixes=["Re-run analysis for this team"]
                )
            # Repo is not accessible — default to private
            return ClassificationResult(
                error_type="private",
                is_private=True,
                confidence=min(confidence, 0.6),
                reason="Repository not accessible (likely private or requires authentication)",
                signals_used=signals_used,
                suggested_fixes=["Make repository public in GitHub settings"]
            )
    
    # Check for explicit "404" or "does not exist" messages
    not_found_indicators = [
        "404",
        "does not exist",
        "not found"
    ]
    
    if any(indicator in error_lower for indicator in not_found_indicators):
        # Generate suggested fixes based on GitHub ID matching
        if github_match and github_match.suggested_urls:
            suggested_fixes = github_match.suggested_urls
        
        return ClassificationResult(
            error_type="not_found",
            is_private=False,
            confidence=min(confidence, 0.9),
            reason="Repository not found or does not exist",
            signals_used=signals_used,
            suggested_fixes=suggested_fixes
        )
    
    # Unknown error type
    return ClassificationResult(
        error_type="other",
        is_private=None,
        confidence=min(confidence, 0.5),
        reason=error_message[:200],  # Truncate long errors
        signals_used=signals_used,
        suggested_fixes=[]
    )
