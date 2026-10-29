"""
Fix Suggestion Generator for Repository Privacy Detection

This module generates actionable fix suggestions based on classification results,
URL validation, and GitHub ID matching.
"""

from typing import List, Optional
import re
from .classification import ClassificationResult
from .url_validation import URLValidationResult
from .github_id_matcher import GitHubIDMatchResult


def _fix_common_domain_typos(url: str) -> Optional[str]:
    """
    Fix common domain typos in GitHub URLs.
    
    Common typos:
    - githib.com -> github.com
    - guthub.com -> github.com
    - githup.com -> github.com
    - gitub.com -> github.com
    - gihub.com -> github.com
    
    Args:
        url: The URL with potential typos
        
    Returns:
        Fixed URL if typo detected, None otherwise
    """
    if not url or not isinstance(url, str):
        return None
    
    # Common typo patterns
    typo_patterns = [
        (r'githib\.com', 'github.com'),
        (r'guthub\.com', 'github.com'),
        (r'githup\.com', 'github.com'),
        (r'gitub\.com', 'github.com'),
        (r'gihub\.com', 'github.com'),
        (r'githbu\.com', 'github.com'),
        (r'gtihub\.com', 'github.com'),
    ]
    
    for pattern, replacement in typo_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            fixed_url = re.sub(pattern, replacement, url, flags=re.IGNORECASE)
            return fixed_url
    
    return None


def generate_fix_suggestions(
    classification: ClassificationResult,
    url_validation: URLValidationResult,
    github_match: GitHubIDMatchResult
) -> List[str]:
    """
    Generate fix suggestions based on classification and context.
    
    This function generates actionable fix suggestions in priority order:
    1. Missing protocol fixes (highest priority - simple fix)
    2. Common typo fixes (fix domain typos like githib -> github)
    3. Profile URL fixes (append common repo names)
    4. GitHub ID-based fixes (use student GitHub IDs)
    5. Organization repo flags (informational)
    
    The function intelligently combines suggestions from multiple sources:
    - URL validation errors (missing protocol, wrong format)
    - GitHub ID matching (suggested URLs based on student IDs)
    - Classification results (existing suggestions)
    
    Args:
        classification: The classification result with error type and confidence
        url_validation: The URL validation result with error details
        github_match: The GitHub ID match result with suggested URLs
        
    Returns:
        List of suggested fixes in priority order (most likely fix first)
        
    Examples:
        >>> # Missing protocol
        >>> generate_fix_suggestions(
        ...     classification=ClassificationResult(error_type="invalid_url", ...),
        ...     url_validation=URLValidationResult(is_valid=False, error_type="missing_protocol", ...),
        ...     github_match=GitHubIDMatchResult(...)
        ... )
        ['https://github.com/owner/repo']
        
        >>> # Profile URL
        >>> generate_fix_suggestions(
        ...     classification=ClassificationResult(error_type="invalid_url", ...),
        ...     url_validation=URLValidationResult(is_valid=False, error_type="profile_url", ...),
        ...     github_match=GitHubIDMatchResult(...)
        ... )
        ['https://github.com/username/project', 'https://github.com/username/assignment', ...]
        
        >>> # GitHub ID mismatch
        >>> generate_fix_suggestions(
        ...     classification=ClassificationResult(error_type="not_found", ...),
        ...     url_validation=URLValidationResult(is_valid=True, ...),
        ...     github_match=GitHubIDMatchResult(matches=False, suggested_urls=[...], ...)
        ... )
        ['https://github.com/student1/repo', 'https://github.com/student2/repo']
    """
    suggestions = []
    
    # Priority 1: Missing protocol (simplest fix)
    # This is the highest priority because it's a simple, unambiguous fix
    if url_validation and url_validation.error_type == "missing_protocol":
        if classification.suggested_fixes:
            suggestions.extend(classification.suggested_fixes)
        # Return immediately - this is the most likely fix
        return _deduplicate_suggestions(suggestions)
    
    # Priority 2: Common typo fixes (fix domain typos)
    # Check if the URL has common domain typos
    if url_validation and url_validation.error_type == "wrong_platform":
        # Try to fix common typos
        # We need to get the original URL - it might be in the classification
        # For now, use classification's suggested fixes
        if classification.suggested_fixes:
            suggestions.extend(classification.suggested_fixes)
        # Return immediately if we have typo fixes
        if suggestions:
            return _deduplicate_suggestions(suggestions)
    
    # Priority 3: Profile URL (append common repo names)
    # This is a clear structural issue with the URL
    if url_validation and url_validation.error_type == "profile_url":
        if classification.suggested_fixes:
            suggestions.extend(classification.suggested_fixes)
        # Return immediately - profile URL fixes are high priority
        return _deduplicate_suggestions(suggestions)
    
    # Priority 4: Homepage URL
    if url_validation and url_validation.error_type == "homepage_url":
        if classification.suggested_fixes:
            suggestions.extend(classification.suggested_fixes)
        # Return immediately
        return _deduplicate_suggestions(suggestions)
    
    # Priority 5: GitHub ID-based fixes (use student GitHub IDs)
    # This applies when the URL is valid but points to wrong owner
    if github_match and github_match.suggested_urls:
        # Add GitHub ID-based suggestions
        suggestions.extend(github_match.suggested_urls)
    
    # Priority 6: Organization repos (informational, no fix needed)
    # Only add this if we don't have other suggestions
    if github_match and not github_match.matches and github_match.confidence >= 0.5:
        # This might be an organization repo
        if not suggestions:
            suggestions.append("This may be an organization repository (no fix needed)")
    
    # Fallback: Use classification's suggested fixes if we haven't added anything yet
    if not suggestions and classification.suggested_fixes:
        suggestions.extend(classification.suggested_fixes)
    
    return _deduplicate_suggestions(suggestions)


def _deduplicate_suggestions(suggestions: List[str]) -> List[str]:
    """
    Remove duplicate suggestions while preserving order.
    
    Args:
        suggestions: List of suggestions (may contain duplicates)
        
    Returns:
        List of unique suggestions in original order
    """
    seen = set()
    unique_suggestions = []
    
    for suggestion in suggestions:
        if suggestion and suggestion not in seen:
            seen.add(suggestion)
            unique_suggestions.append(suggestion)
    
    return unique_suggestions
