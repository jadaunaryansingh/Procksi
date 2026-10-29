"""
Contributor Verification Module

Validates commit authors against repository collaborators using GitHub API or database team members.
Detects outsourced work (commits from non-team members).
"""

import os
import re
from typing import Dict, List, Set, Optional, Tuple


def fetch_team_members_from_database(team_id: str) -> Dict:
    """
    Fetch team members from database instead of GitHub API.
    
    This is the preferred method for student teams as it verifies against
    the registered team members in the database rather than GitHub collaborators.
    
    Args:
        team_id: UUID of the team
        
    Returns:
        Dictionary with:
        - success: bool
        - team_members: List[str] - List of team member identifiers (names, emails, github usernames)
        - count: int - Number of team members
        - error: str (optional)
    """
    if not team_id:
        return {
            "success": False,
            "team_members": [],
            "count": 0,
            "error": "No team_id provided"
        }
    
    try:
        from src.api.backend.database import get_supabase_admin_client
        
        supabase = get_supabase_admin_client()
        
        # Fetch all students for this team
        students_response = supabase.table("students").select(
            "name, email, github_username"
        ).eq("team_id", str(team_id)).execute()
        
        if not students_response.data:
            return {
                "success": True,
                "team_members": [],
                "count": 0,
                "error": "No students found for this team"
            }
        
        # Collect all identifiers (names, emails, github usernames)
        team_members = []
        for student in students_response.data:
            # Add name if present
            if student.get("name"):
                team_members.append(student["name"].lower())
            
            # Add email if present
            if student.get("email"):
                team_members.append(student["email"].lower())
            
            # Add github username if present
            if student.get("github_username"):
                team_members.append(student["github_username"].lower())
        
        return {
            "success": True,
            "team_members": team_members,
            "count": len(students_response.data),
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "team_members": [],
            "count": 0,
            "error": f"Database query failed: {str(e)}"
        }


def parse_repo_url(repo_url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract owner and repo name from GitHub URL.
    
    Args:
        repo_url: GitHub repository URL
        
    Returns:
        Tuple of (owner, repo_name) or (None, None) if invalid
        
    Examples:
        >>> parse_repo_url("https://github.com/owner/repo")
        ('owner', 'repo')
        >>> parse_repo_url("https://github.com/owner/repo.git")
        ('owner', 'repo')
    """
    if not repo_url:
        return None, None
    
    # Remove .git suffix and trailing slashes
    cleaned = repo_url.rstrip("/").replace(".git", "")
    
    # Extract from various GitHub URL formats
    patterns = [
        r'github\.com[:/]([^/]+)/([^/]+)$',  # HTTPS or SSH
        r'github\.com/([^/]+)/([^/]+)/?',     # HTTPS with/without trailing slash
    ]
    
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            return match.group(1), match.group(2)
    
    return None, None


def fetch_repository_collaborators(owner: str, repo: str, token: str) -> Dict:
    """
    Fetch repository collaborators from GitHub API.
    
    Args:
        owner: Repository owner (username or organization)
        repo: Repository name
        token: GitHub API token
        
    Returns:
        Dictionary with:
        - success: bool
        - collaborators: List[str] - List of collaborator usernames/emails
        - api_reachable: bool
        - error: str (optional)
        
    API Endpoint: GET /repos/{owner}/{repo}/collaborators
    """
    import requests
    
    if not token:
        return {
            "success": False,
            "collaborators": [],
            "api_reachable": False,
            "error": "No GitHub API token configured"
        }
    
    api_url = f"https://api.github.com/repos/{owner}/{repo}/collaborators"
    
    try:
        response = requests.get(
            api_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json"
            },
            timeout=10.0
        )
        
        if response.status_code == 200:
            collaborators_data = response.json()
            
            # Extract usernames and emails if available
            collaborators = []
            for collab in collaborators_data:
                username = collab.get("login", "").lower()
                if username:
                    collaborators.append(username)
            
            return {
                "success": True,
                "collaborators": collaborators,
                "api_reachable": True,
                "count": len(collaborators)
            }
        
        elif response.status_code == 404:
            return {
                "success": False,
                "collaborators": [],
                "api_reachable": True,
                "error": "Repository not found or not accessible (404)"
            }
        
        elif response.status_code == 403:
            # Rate limited or forbidden
            return {
                "success": False,
                "collaborators": [],
                "api_reachable": True,
                "error": f"GitHub API forbidden (403) - Rate limited or insufficient permissions"
            }
        
        else:
            return {
                "success": False,
                "collaborators": [],
                "api_reachable": True,
                "error": f"GitHub API returned {response.status_code}"
            }
    
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "collaborators": [],
            "api_reachable": False,
            "error": "GitHub API timeout"
        }
    
    except Exception as e:
        return {
            "success": False,
            "collaborators": [],
            "api_reachable": False,
            "error": f"GitHub API error: {str(e)}"
        }


def normalize_author_name(author: str) -> str:
    """
    Normalize author name for comparison.
    
    - Converts to lowercase
    - Removes common email domains
    - Extracts username from email
    
    Args:
        author: Commit author name or email
        
    Returns:
        Normalized author string
        
    Examples:
        >>> normalize_author_name("John Doe")
        'john doe'
        >>> normalize_author_name("johndoe@gmail.com")
        'johndoe'
        >>> normalize_author_name("john.doe@students.university.edu")
        'john.doe'
    """
    author_lower = author.lower().strip()
    
    # If it looks like an email, extract the username part
    if "@" in author_lower:
        username_part = author_lower.split("@")[0]
        return username_part.replace("+", "").strip()
    
    return author_lower


def verify_contributors(author_stats: Dict, collaborators: List[str]) -> Dict:
    """
    Verify commit authors against repository collaborators.
    
    Args:
        author_stats: Author statistics from commit_forensics (dict of author -> stats)
        collaborators: List of authorized collaborator usernames from GitHub API
        
    Returns:
        Dictionary with verification results:
        - total_authors: int
        - verified_authors: int
        - unauthorized_authors: List[Dict]
        - unauthorized_commits: int
        - unauthorized_commit_ratio: float (0-100)
        - has_outsourced_work: bool
        - severity: str ('none', 'minor', 'major', 'critical')
    """
    if not collaborators:
        # Cannot verify without collaborator list
        return {
            "total_authors": len(author_stats),
            "verified_authors": 0,
            "unauthorized_authors": [],
            "unauthorized_commits": 0,
            "unauthorized_commit_ratio": 0.0,
            "has_outsourced_work": False,
            "severity": "none",
            "verification_skipped": True,
            "reason": "No collaborator data available"
        }
    
    # Normalize collaborator names for comparison
    normalized_collaborators = set()
    for collab in collaborators:
        normalized_collaborators.add(normalize_author_name(collab))
    
    # Analyze each author
    total_authors = len(author_stats)
    total_commits = sum(stats.get("commits", 0) for stats in author_stats.values())
    
    verified_authors = 0
    unauthorized_authors = []
    unauthorized_commits = 0
    
    for author, stats in author_stats.items():
        normalized_author = normalize_author_name(author)
        commits = stats.get("commits", 0)
        
        # Check if author matches any collaborator (fuzzy match)
        is_verified = False
        
        # Exact match
        if normalized_author in normalized_collaborators:
            is_verified = True
        else:
            # Fuzzy match: Check if author name contains collaborator username or vice versa
            for collab in normalized_collaborators:
                # Check substring match (min 4 characters to avoid false positives)
                if len(collab) >= 4 and len(normalized_author) >= 4:
                    if collab in normalized_author or normalized_author in collab:
                        is_verified = True
                        break
        
        if is_verified:
            verified_authors += 1
        else:
            unauthorized_authors.append({
                "name": author,
                "commits": commits,
                "share": round((commits / max(1, total_commits)) * 100, 1)
            })
            unauthorized_commits += commits
    
    # Calculate metrics
    unauthorized_ratio = (unauthorized_commits / max(1, total_commits)) * 100
    has_outsourced_work = len(unauthorized_authors) > 0
    
    # Determine severity
    if not has_outsourced_work:
        severity = "none"
    elif unauthorized_ratio < 10:
        severity = "minor"  # <10% unauthorized commits
    elif unauthorized_ratio < 30:
        severity = "major"  # 10-30% unauthorized commits
    else:
        severity = "critical"  # >30% unauthorized commits (likely outsourced)
    
    return {
        "total_authors": total_authors,
        "verified_authors": verified_authors,
        "unauthorized_authors": unauthorized_authors,
        "unauthorized_commits": unauthorized_commits,
        "unauthorized_commit_ratio": round(unauthorized_ratio, 1),
        "has_outsourced_work": has_outsourced_work,
        "severity": severity,
        "verification_skipped": False
    }


def analyze_contributor_verification(author_stats: Dict, repo_url: str, team_id: Optional[str] = None) -> Dict:
    """
    Main entry point: Verify contributors against database team members or GitHub collaborators.
    
    Priority:
    1. If team_id is provided, use database team members (preferred for student teams)
    2. Otherwise, fallback to GitHub API collaborators
    
    Args:
        author_stats: Author statistics from commit_forensics analysis
        repo_url: GitHub repository URL
        team_id: Optional UUID of the team (enables database verification)
        
    Returns:
        Dictionary with:
        - api_status: Dict (success, reachable, error)
        - team_members/collaborators: List[str]
        - verification: Dict (results from verify_contributors)
        - penalty_recommended: float (0.0 to 1.0 multiplier)
    """
    # Try database verification first if team_id is provided
    if team_id:
        db_result = fetch_team_members_from_database(team_id)
        
        if db_result.get("success") and db_result.get("team_members"):
            # Database fetch successful - use team members for verification
            verification_result = verify_contributors(
                author_stats,
                db_result.get("team_members", [])
            )
            
            # Calculate penalty multiplier based on severity
            penalty_multiplier = 1.0
            
            if verification_result.get("severity") == "minor":
                penalty_multiplier = 0.95  # 5% penalty
            elif verification_result.get("severity") == "major":
                penalty_multiplier = 0.85  # 15% penalty
            elif verification_result.get("severity") == "critical":
                penalty_multiplier = 0.7   # 30% penalty (likely outsourced)
            
            return {
                "api_status": {
                    "success": True,
                    "reachable": True,
                    "error": None,
                    "source": "database"
                },
                "team_members": db_result.get("team_members", []),
                "team_member_count": db_result.get("count", 0),
                "verification": verification_result,
                "penalty_recommended": penalty_multiplier
            }
        else:
            # Database fetch failed - log warning and fall through to GitHub API
            print(f"⚠️  Database verification failed: {db_result.get('error')} - Falling back to GitHub API")
    
    # Parse repository URL for GitHub API fallback
    owner, repo = parse_repo_url(repo_url)
    
    if not owner or not repo:
        return {
            "api_status": {
                "success": False,
                "reachable": False,
                "error": "Invalid GitHub repository URL",
                "source": "none"
            },
            "collaborators": [],
            "verification": {
                "total_authors": len(author_stats),
                "verified_authors": 0,
                "unauthorized_authors": [],
                "unauthorized_commits": 0,
                "unauthorized_commit_ratio": 0.0,
                "has_outsourced_work": False,
                "severity": "none",
                "verification_skipped": True,
                "reason": "Invalid repository URL"
            },
            "penalty_recommended": 1.0  # No penalty
        }
    
    # Get GitHub API token
    token = os.getenv("GH_API_KEY") or os.getenv("GITHUB_TOKEN")
    
    # Fetch collaborators from GitHub API
    api_result = fetch_repository_collaborators(owner, repo, token)
    
    # Skip verification if too few collaborators (student repos often have 1-2 owners)
    # In student teams, most members commit without being added as GitHub collaborators
    collaborator_count = api_result.get("count", 0)
    if collaborator_count <= 2:
        return {
            "api_status": {
                "success": api_result.get("success", False),
                "reachable": api_result.get("api_reachable", False),
                "error": None,
                "source": "github-api-skipped"
            },
            "collaborators": api_result.get("collaborators", []),
            "collaborator_count": collaborator_count,
            "verification": {
                "total_authors": len(author_stats),
                "verified_authors": len(author_stats),  # Assume all verified
                "unauthorized_authors": [],
                "unauthorized_commits": 0,
                "unauthorized_commit_ratio": 0.0,
                "has_outsourced_work": False,
                "severity": "none",
                "verification_skipped": True,
                "reason": f"Too few GitHub collaborators ({collaborator_count}) - Cannot verify team composition"
            },
            "penalty_recommended": 1.0  # No penalty
        }
    
    # Perform verification
    verification_result = verify_contributors(
        author_stats, 
        api_result.get("collaborators", [])
    )
    
    # Calculate penalty multiplier based on severity
    penalty_multiplier = 1.0
    
    if verification_result.get("severity") == "minor":
        penalty_multiplier = 0.95  # 5% penalty
    elif verification_result.get("severity") == "major":
        penalty_multiplier = 0.85  # 15% penalty
    elif verification_result.get("severity") == "critical":
        penalty_multiplier = 0.7   # 30% penalty (likely outsourced)
    
    return {
        "api_status": {
            "success": api_result.get("success", False),
            "reachable": api_result.get("api_reachable", False),
            "error": api_result.get("error"),
            "source": "github-api"
        },
        "collaborators": api_result.get("collaborators", []),
        "collaborator_count": api_result.get("count", 0),
        "verification": verification_result,
        "penalty_recommended": penalty_multiplier
    }

