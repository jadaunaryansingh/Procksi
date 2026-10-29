"""
GitHub ID Matcher Service for Repository Privacy Detection

This module provides GitHub ID matching functionality to cross-reference
repository URLs with student GitHub IDs.
"""

from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

from ..database import get_supabase_client


@dataclass
class GitHubIDMatchResult:
    """Result of GitHub ID matching operation.
    
    Attributes:
        owner: The repository owner extracted from the URL
        student_github_ids: List of GitHub IDs for students in the team
        matches: Whether the owner matches any student GitHub ID
        suggested_urls: List of suggested repository URLs based on student GitHub IDs
        confidence: Confidence score for the match result (0.0-1.0)
    """
    owner: str
    student_github_ids: List[str]
    matches: bool
    suggested_urls: List[str]
    confidence: float


def extract_owner_from_url(repo_url: str) -> Optional[str]:
    """
    Extract the repository owner from a GitHub URL.
    
    The owner is the first path segment after the domain.
    For example: https://github.com/owner/repo -> "owner"
    
    Args:
        repo_url: The GitHub repository URL
        
    Returns:
        The owner name, or None if extraction fails
        
    Examples:
        >>> extract_owner_from_url("https://github.com/owner/repo")
        'owner'
        >>> extract_owner_from_url("https://github.com/owner/repo.git")
        'owner'
    """
    if not repo_url or not isinstance(repo_url, str):
        return None
    
    try:
        parsed = urlparse(repo_url.strip())
        
        # Validate that we have a proper URL with a domain
        # If no scheme or netloc, it's not a valid URL
        if not parsed.scheme or not parsed.netloc:
            return None
        
        # Validate it's a GitHub URL
        if parsed.netloc.lower() != "github.com":
            return None
        
        path = parsed.path.strip("/")
        
        if not path:
            return None
        
        # Split path and get first segment (owner)
        path_segments = [seg for seg in path.split("/") if seg]
        
        if len(path_segments) < 1:
            return None
        
        # Return owner (first segment), lowercased for comparison
        return path_segments[0].lower()
        
    except Exception:
        return None


def match_github_ids(repo_url: str, team_id: str, student_github_ids: Optional[List[str]] = None) -> GitHubIDMatchResult:
    """
    Extract owner from URL and compare with student GitHub IDs.
    
    This function performs the following steps:
    1. Extract owner from repository URL (first path segment)
    2. Fetch all students in the team from database
    3. Get GitHub usernames for students (from students.github_username column)
    4. Compare owner with GitHub usernames (case-insensitive)
    5. Generate suggested URLs if mismatch
    
    Confidence scoring:
    - Exact match: 0.9
    - Case-insensitive match: 0.7
    - No match: 0.3
    - No GitHub IDs: 0.5
    - Organization repo (common pattern): 0.5
    
    Args:
        repo_url: The repository URL to check
        team_id: The team ID to fetch student GitHub IDs for
        
    Returns:
        GitHubIDMatchResult with match status and suggestions
        
    Examples:
        >>> match_github_ids("https://github.com/student1/repo", "team-123")
        GitHubIDMatchResult(owner="student1", matches=True, confidence=0.9, ...)
        
        >>> match_github_ids("https://github.com/wronguser/repo", "team-123")
        GitHubIDMatchResult(owner="wronguser", matches=False, confidence=0.3, 
                          suggested_urls=["https://github.com/student1/repo", ...])
    """
    # Extract owner from URL
    owner = extract_owner_from_url(repo_url)
    
    if not owner:
        # Cannot extract owner - return neutral result
        return GitHubIDMatchResult(
            owner="",
            student_github_ids=[],
            matches=False,
            suggested_urls=[],
            confidence=0.5
        )
    
    # Use prefetched student GitHub IDs when provided; fallback to database fetch
    if student_github_ids is not None:
        github_ids = [
            github_id.lower()
            for github_id in student_github_ids
            if isinstance(github_id, str) and github_id.strip()
        ]
    else:
        try:
            supabase = get_supabase_client()
            students_response = supabase.table("students").select("github_username").eq("team_id", team_id).execute()

            students = students_response.data or []

            # Extract GitHub usernames (filter out None/empty values)
            github_ids = [
                student.get("github_username").lower()
                for student in students
                if student.get("github_username") and isinstance(student.get("github_username"), str) and student.get("github_username").strip()
            ]

        except Exception as e:
            # Database query failed - return neutral result
            print(f"Error fetching student GitHub IDs: {e}")
            return GitHubIDMatchResult(
                owner=owner,
                student_github_ids=[],
                matches=False,
                suggested_urls=[],
                confidence=0.5
            )
    
    # Handle case: No GitHub IDs available
    if not github_ids:
        return GitHubIDMatchResult(
            owner=owner,
            student_github_ids=[],
            matches=False,
            suggested_urls=[],
            confidence=0.5  # Neutral - cannot determine match without GitHub IDs
        )
    
    # Compare owner with GitHub IDs (case-insensitive)
    owner_lower = owner.lower()
    matches = owner_lower in github_ids
    
    # Determine confidence based on match type
    if matches:
        # Check if it's an exact case match or case-insensitive match
        exact_match = any(owner == github_id for github_id in github_ids)
        confidence = 0.9 if exact_match else 0.7
    else:
        # Check if owner looks like an organization (common patterns)
        # Organizations often have hyphens, are longer, or contain keywords
        is_likely_org = (
            "-" in owner or 
            len(owner) > 20 or 
            any(keyword in owner for keyword in ["org", "team", "group", "company", "project"])
        )
        
        confidence = 0.5 if is_likely_org else 0.3
    
    # Generate suggested URLs based on student GitHub IDs
    suggested_urls = []
    if not matches and github_ids:
        # Extract repo name from original URL
        try:
            parsed = urlparse(repo_url.strip())
            path_segments = [seg for seg in parsed.path.strip("/").split("/") if seg]
            
            # Get repo name (second segment), or use "repo" as default
            repo_name = path_segments[1] if len(path_segments) >= 2 else "repo"
            
            # Remove .git suffix if present
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            
            # Generate suggested URLs for each student GitHub ID
            for github_id in github_ids:
                suggested_url = f"https://github.com/{github_id}/{repo_name}"
                suggested_urls.append(suggested_url)
                
        except Exception:
            # If we can't extract repo name, just suggest with generic name
            for github_id in github_ids:
                suggested_url = f"https://github.com/{github_id}/repo"
                suggested_urls.append(suggested_url)
    
    return GitHubIDMatchResult(
        owner=owner,
        student_github_ids=github_ids,
        matches=matches,
        suggested_urls=suggested_urls,
        confidence=confidence
    )
