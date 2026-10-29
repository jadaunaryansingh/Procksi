"""
URL Validation Service for Repository Privacy Detection

This module provides URL validation, normalization, and classification
for GitHub repository URLs.
"""

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse


@dataclass
class URLValidationResult:
    """Result of URL validation operation.
    
    Attributes:
        is_valid: Whether the URL is valid
        error_type: Type of error if invalid (missing_protocol, wrong_platform, 
                   invalid_format, profile_url, homepage_url)
        normalized_url: Normalized version of the URL if valid
        reason: Human-readable explanation of the validation result
    """
    is_valid: bool
    error_type: Optional[str] = None
    normalized_url: Optional[str] = None
    reason: str = ""


def normalize_url(url: str) -> str:
    """
    Normalize a GitHub repository URL.
    
    Normalization steps:
    1. Remove .git suffix from path
    2. Remove trailing slashes
    3. Remove query parameters and fragments
    4. Convert to lowercase (scheme, domain, and path)
    
    This function is idempotent - normalizing twice produces the same result.
    
    Args:
        url: The URL to normalize
        
    Returns:
        Normalized URL string
        
    Examples:
        >>> normalize_url("https://github.com/owner/repo.git")
        'https://github.com/owner/repo'
        >>> normalize_url("HTTPS://GITHUB.COM/Owner/Repo/")
        'https://github.com/owner/repo'
        >>> normalize_url("https://github.com/owner/repo?tab=readme#section")
        'https://github.com/owner/repo'
    """
    if not url or not isinstance(url, str):
        return url
    
    try:
        # Parse the URL
        parsed = urlparse(url)
        
        # Lowercase the scheme and domain
        scheme = parsed.scheme.lower() if parsed.scheme else ""
        netloc = parsed.netloc.lower() if parsed.netloc else ""
        
        # Process the path - lowercase it as well
        path = parsed.path.lower() if parsed.path else ""
        
        # Remove trailing slashes first
        path = path.rstrip("/")
        
        # Then remove .git suffix
        if path.endswith(".git"):
            path = path[:-4]
        
        # Reconstruct URL without query params and fragments
        normalized = urlunparse((
            scheme,
            netloc,
            path,
            "",  # params (empty)
            "",  # query (empty)
            ""   # fragment (empty)
        ))
        
        return normalized
    except Exception:
        # If parsing fails, return original URL
        return url


def validate_repo_url(url: str) -> URLValidationResult:
    """
    Validate a GitHub repository URL.
    
    Validation checks:
    1. Protocol: Must be http:// or https://
    2. Platform: Must be github.com
    3. Path structure: Must have owner/repo format (at least 2 path segments)
    4. Profile detection: Single path segment = profile URL (invalid)
    5. Homepage detection: No path segments = homepage (invalid)
    
    Args:
        url: The repository URL to validate
        
    Returns:
        URLValidationResult with validation status and details
        
    Examples:
        >>> validate_repo_url("https://github.com/owner/repo")
        URLValidationResult(is_valid=True, normalized_url="https://github.com/owner/repo", ...)
        
        >>> validate_repo_url("github.com/owner/repo")
        URLValidationResult(is_valid=False, error_type="missing_protocol", ...)
        
        >>> validate_repo_url("https://github.com/username")
        URLValidationResult(is_valid=False, error_type="profile_url", ...)
    """
    # Handle empty or None URLs
    if not url or not isinstance(url, str) or not url.strip():
        return URLValidationResult(
            is_valid=False,
            error_type="missing_url",
            reason="URL is empty or missing"
        )
    
    url = url.strip()
    
    try:
        # Parse the URL
        parsed = urlparse(url)
        
        # Check 1: Protocol validation
        if not parsed.scheme:
            return URLValidationResult(
                is_valid=False,
                error_type="missing_protocol",
                reason="URL must start with http:// or https://"
            )
        
        if parsed.scheme.lower() not in ("http", "https"):
            return URLValidationResult(
                is_valid=False,
                error_type="invalid_protocol",
                reason=f"Protocol must be http:// or https://, got {parsed.scheme}://"
            )
        
        # Check 2: Platform validation
        domain = parsed.netloc.lower()
        if not domain:
            return URLValidationResult(
                is_valid=False,
                error_type="missing_domain",
                reason="URL must include a domain (github.com)"
            )
        
        if domain != "github.com":
            return URLValidationResult(
                is_valid=False,
                error_type="wrong_platform",
                reason=f"Only GitHub repositories are supported (must be github.com), got {domain}"
            )
        
        # Check 3: Path structure validation
        path = parsed.path.strip("/")
        
        if not path:
            return URLValidationResult(
                is_valid=False,
                error_type="homepage_url",
                reason="URL points to GitHub homepage, not a repository (must have owner/repo format)"
            )
        
        # Split path into segments
        path_segments = [seg for seg in path.split("/") if seg]
        
        if len(path_segments) < 2:
            return URLValidationResult(
                is_valid=False,
                error_type="profile_url",
                reason="URL points to a user profile, not a repository (must have owner/repo format)"
            )
        
        # Check 4: Validate repository name (second segment)
        repo_name = path_segments[1]
        
        # Check for .gitt extension (common typo - should be .git or nothing)
        if repo_name.endswith(".gitt"):
            return URLValidationResult(
                is_valid=False,
                error_type="invalid_format",
                reason="Invalid repository URL: '.gitt' extension is not valid (should be '.git' or no extension)"
            )
        
        # URL is valid - normalize it
        normalized = normalize_url(url)
        
        return URLValidationResult(
            is_valid=True,
            normalized_url=normalized,
            reason="Valid GitHub repository URL"
        )
        
    except Exception as e:
        return URLValidationResult(
            is_valid=False,
            error_type="invalid_format",
            reason=f"URL format is invalid: {str(e)}"
        )
