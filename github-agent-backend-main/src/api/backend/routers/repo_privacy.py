"""
Repository Privacy Detection and Alert System
Extracts privacy information from analysis failures instead of making separate GitHub API calls.
"""

from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import os
from urllib.parse import urlparse

import requests

from ..middleware.auth import get_current_user
from ..database import get_supabase
from ..utils.email import send_alert_email
from ..services.url_validation import validate_repo_url
from ..services.github_id_matcher import match_github_ids
from ..services.classification import classify_repo_issue
from ..services.fix_suggestions import generate_fix_suggestions
from ..templates.email_templates import EmailTemplates

router = APIRouter(prefix="/api/repo-privacy", tags=["repo-privacy"])


def _extract_owner_repo(repo_url: Optional[str]) -> Optional[tuple[str, str]]:
    if not repo_url or not isinstance(repo_url, str):
        return None

    try:
        parsed = urlparse(repo_url.strip())
        if parsed.netloc.lower() not in ("github.com", "www.github.com"):
            return None

        segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
        if len(segments) < 2:
            return None

        owner = segments[0]
        repo = segments[1]
        if repo.endswith(".git"):
            repo = repo[:-4]

        if not owner or not repo:
            return None

        return owner, repo
    except Exception:
        return None


def _is_public_github_repo(repo_url: Optional[str]) -> Optional[bool]:
    owner_repo = _extract_owner_repo(repo_url)
    if not owner_repo:
        return None

    owner, repo = owner_repo
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-agent-backend"
    }

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(api_url, headers=headers, timeout=8)

        if response.status_code == 200:
            payload = response.json() or {}
            return not bool(payload.get("private", False))

        # 404/403/401 cannot reliably distinguish private vs missing with unauthenticated access.
        if response.status_code in (401, 403, 404):
            pass
    except requests.RequestException:
        pass

    # Fallback: check the GitHub repository page directly.
    # Public repos return 200; missing/private commonly return 404.
    try:
        page_response = requests.get(repo_url, headers={"User-Agent": "github-agent-backend"}, timeout=8, allow_redirects=True)
        if page_response.status_code == 200:
            return True
        if page_response.status_code == 404:
            return False
    except requests.RequestException:
        return None

    return None


def check_batch_repo_privacy_internal(batch_id: str) -> Dict[str, Any]:
    """
    Internal function to check repository privacy for a batch.
    This is called automatically after batch analysis completes.
    Does not require authentication since it's called from backend code.
    
    Args:
        batch_id: The batch ID to check
        
    Returns:
        Dict with privacy check results
    """
    from ..database import get_supabase_admin_client
    supabase = get_supabase_admin_client()  # Use admin client to bypass RLS
    
    # Get ALL teams in batch (including those without repo_url)
    all_teams_response = supabase.table("teams").select(
        "id, team_name, repo_url, status, is_private, last_privacy_check, validation_status, validation_confidence, validation_reason, suggested_fixes"
    ).eq("batch_id", batch_id).execute()
    
    all_teams = all_teams_response.data or []
    
    if not all_teams:
        return {
            "success": True,
            "message": "No teams found in this batch",
            "totalTeams": 0,
            "checkedTeams": 0,
            "privateRepos": 0,
            "notFoundRepos": 0,
            "invalidRepos": 0,
            "missingRepos": 0,
            "details": []
        }
    
    checked_count = 0
    private_count = 0
    not_found_count = 0
    invalid_count = 0
    missing_count = 0
    details = []
    
    # OPTIMIZATION: Fetch ALL analysis jobs for the batch in ONE query
    team_ids = [team["id"] for team in all_teams]
    all_jobs_response = supabase.table("analysis_jobs").select(
        "team_id, error_message, status, started_at"
    ).in_("team_id", team_ids).order("started_at", desc=True).execute()
    
    # Build a map of team_id -> latest job
    jobs_map = {}
    for job in (all_jobs_response.data or []):
        team_id = job["team_id"]
        if team_id not in jobs_map:  # Keep only the latest (already sorted by started_at desc)
            jobs_map[team_id] = job

    # OPTIMIZATION: Fetch ALL student github usernames for the batch in ONE query
    students_response = supabase.table("students").select("team_id, github_username").in_("team_id", team_ids).execute()
    team_student_ids_map = {team_id: [] for team_id in team_ids}
    for student in (students_response.data or []):
        current_team_id = student.get("team_id")
        github_username = student.get("github_username")
        if current_team_id and isinstance(github_username, str) and github_username.strip():
            team_student_ids_map.setdefault(current_team_id, []).append(github_username.strip())
    
    # Collect batch updates to minimize DB calls
    teams_to_update = []

    def _normalize_fixes(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        return []

    def _append_team_update_if_changed(team: Dict[str, Any], update_data: Dict[str, Any]):
        existing_fixes = _normalize_fixes(team.get("suggested_fixes"))
        new_fixes = _normalize_fixes(update_data.get("suggested_fixes"))

        changed = (
            team.get("is_private") != update_data.get("is_private")
            or team.get("validation_status") != update_data.get("validation_status")
            or (team.get("validation_confidence") or 0) != (update_data.get("validation_confidence") or 0)
            or (team.get("validation_reason") or "") != (update_data.get("validation_reason") or "")
            or existing_fixes != new_fixes
        )

        if changed:
            teams_to_update.append({"id": team["id"], **update_data})
    
    for team in all_teams:
        team_id = team["id"]
        team_name = team["team_name"]
        repo_url = team.get("repo_url")
        status = team.get("status", "pending")
        
        # Check if repo URL is missing
        if not repo_url or repo_url.strip() == "":
            _append_team_update_if_changed(team, {
                "is_private": None,
                "validation_status": "missing_url",
                "validation_confidence": 1.0,
                "validation_reason": "No repository URL provided",
                "suggested_fixes": ["Provide a valid GitHub repository URL"],
                "last_privacy_check": datetime.utcnow().isoformat()
            })
            
            missing_count += 1
            checked_count += 1
            
            details.append({
                "teamId": team_id,
                "teamName": team_name,
                "repoUrl": None,
                "error": "No repository URL provided",
                "errorType": "missing_url",
                "isPrivate": None
            })
            continue
        
        # Get the latest analysis job for this team from the map
        latest_job = jobs_map.get(team_id)
        jobs = [latest_job] if latest_job else []
        
        # Check if team status is "failed" (from teams table)
        team_status_failed = status == "failed"
        
        # Check if there's a failed analysis job
        has_failed_job = jobs and jobs[0].get("status") == "failed"
        
        # If team is marked as failed OR has a failed job, classify the error
        if team_status_failed or has_failed_job:
            error_message = jobs[0].get("error_message") if jobs else None
            
            # If no error message but team is failed, it might be a stuck job
            # Try to infer the issue from the URL
            if not error_message and team_status_failed:
                # Proactively validate URL to see if that's the issue
                url_validation = validate_repo_url(repo_url)
                if not url_validation.is_valid:
                    error_message = url_validation.reason or "Invalid repository URL format"
                else:
                    # URL looks valid but analysis failed - might be private
                    error_message = "Repository not found or inaccessible"
            
            # Classify the error (pass repo_url and team_id for enhanced classification)
            classification = classify_repo_error(
                error_message,
                repo_url,
                team_id,
                student_github_ids=team_student_ids_map.get(team_id, [])
            )

            current_url_validation = validate_repo_url(repo_url)
            stale_invalid_error_indicators = [
                "invalid url",
                "invalid github url",
                "invalid repository format",
                "url appears to point to a user profile",
                "url points to a user profile",
                "url points to github homepage",
                "personal page",
                "owner/repo format"
            ]
            error_lower = (error_message or "").lower()

            if (
                current_url_validation.is_valid
                and classification["error_type"] in ("invalid_url", "other")
                and any(indicator in error_lower for indicator in stale_invalid_error_indicators)
            ):
                classification = {
                    "is_private": None,
                    "error_type": "valid",
                    "reason": "Valid GitHub repository URL",
                    "confidence": 1.0,
                    "suggested_fixes": []
                }

            # Guard against false positives: if GitHub confirms the repository is public,
            # do not classify it as a private repository.
            if classification["error_type"] == "private":
                is_public = _is_public_github_repo(repo_url)
                if is_public is True:
                    classification = {
                        "is_private": None,
                        "error_type": "other",
                        "reason": "Repository is public on GitHub. Analysis failed for a non-privacy reason.",
                        "confidence": 0.9,
                        "suggested_fixes": []
                    }
            
            # Collect update for batch processing
            _append_team_update_if_changed(team, {
                "is_private": classification["is_private"],
                "last_privacy_check": datetime.utcnow().isoformat(),
                "validation_status": classification["error_type"],
                "validation_confidence": classification.get("confidence", 0.5),
                "validation_reason": classification["reason"],
                "suggested_fixes": classification.get("suggested_fixes", [])
            })
            
            checked_count += 1
            
            # Count by type
            if classification["error_type"] == "private":
                private_count += 1
            elif classification["error_type"] == "not_found":
                not_found_count += 1
            elif classification["error_type"] == "invalid_url":
                invalid_count += 1
            
            # Add to details list for reporting
            details.append({
                "teamId": team_id,
                "teamName": team_name,
                "repoUrl": repo_url,
                "error": classification["reason"],
                "errorType": classification["error_type"],
                "isPrivate": classification["is_private"]
            })
        else:
            # Team has not been analyzed yet or analysis succeeded
            # Proactively validate URL format to catch malformed URLs
            url_validation = validate_repo_url(repo_url)
            
            if not url_validation.is_valid:
                # URL is malformed - mark as invalid
                _append_team_update_if_changed(team, {
                    "is_private": None,
                    "last_privacy_check": datetime.utcnow().isoformat(),
                    "validation_status": "invalid_url",
                    "validation_confidence": 0.9,
                    "validation_reason": url_validation.reason or "Invalid repository URL format",
                    "suggested_fixes": []
                })
                
                checked_count += 1
                invalid_count += 1
                
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "repoUrl": repo_url,
                    "error": url_validation.reason or "Invalid repository URL format",
                    "errorType": "invalid_url",
                    "isPrivate": None
                })
            else:
                # URL is valid and analysis is not currently failed.
                # Clear stale repository issue flags from past runs.
                stale_issue_statuses = {
                    "private",
                    "not_found",
                    "invalid_url",
                    "missing_url",
                    "profile_url",
                    "other"
                }

                if team.get("is_private") is not None or team.get("validation_status") in stale_issue_statuses:
                    _append_team_update_if_changed(team, {
                        "is_private": None,
                        "validation_status": "valid",
                        "validation_confidence": 1.0,
                        "validation_reason": "Valid GitHub repository URL",
                        "suggested_fixes": [],
                        "last_privacy_check": None
                    })
    
    # OPTIMIZATION: Batch update all teams in one transaction
    if teams_to_update:
        # Supabase doesn't support batch updates directly, so we'll do them in chunks
        # to reduce the number of round trips (10 teams per update call)
        chunk_size = 10
        for i in range(0, len(teams_to_update), chunk_size):
            chunk = teams_to_update[i:i + chunk_size]
            for team_update in chunk:
                team_id = team_update.pop("id")
                supabase.table("teams").update(team_update).eq("id", team_id).execute()
    
    return {
        "success": True,
        "message": f"Analyzed {checked_count} repositories: {private_count} private, {not_found_count} not found, {invalid_count} invalid, {missing_count} missing",
        "totalTeams": len(all_teams),
        "checkedTeams": checked_count,
        "privateRepos": private_count,
        "notFoundRepos": not_found_count,
        "invalidRepos": invalid_count,
        "missingRepos": missing_count,
        "details": details
    }


def classify_repo_error(
    error_message: Optional[str],
    repo_url: Optional[str] = None,
    team_id: Optional[str] = None,
    student_github_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Classify repository error from analysis failure.
    
    This function now uses the enhanced classification service with multi-signal approach.
    It maintains backward compatibility with the old interface while leveraging new capabilities.
    
    Git clone gives the SAME error for both private repos and non-existent repos.
    We use additional heuristics (URL validation, GitHub ID matching) to distinguish between them.
    
    Args:
        error_message: The error message from analysis failure
        repo_url: The repository URL (optional, for better classification)
        team_id: The team ID (optional, for GitHub ID matching)
    
    Returns:
        Dict with keys:
        - is_private: True if likely private, False if likely not found, None if other error
        - error_type: "private", "not_found", "invalid_url", or "other"
        - reason: Human-readable reason
        - confidence: Confidence score (0.0-1.0)
        - suggested_fixes: List of suggested fixes
    """
    # Use new classification service if team_id is provided
    if team_id:
        try:
            classification = classify_repo_issue(
                error_message=error_message,
                repo_url=repo_url,
                team_id=team_id,
                student_github_ids=student_github_ids
            )
            
            return {
                "is_private": classification.is_private,
                "error_type": classification.error_type,
                "reason": classification.reason,
                "confidence": classification.confidence,
                "suggested_fixes": classification.suggested_fixes
            }
        except Exception as e:
            print(f"Enhanced classification failed, falling back to legacy: {e}")
            # Fall through to legacy classification
    
    # Legacy classification (backward compatibility)
    if not error_message:
        return {
            "is_private": None,
            "error_type": "other",
            "reason": "No error message available",
            "confidence": 0.0,
            "suggested_fixes": []
        }
    
    error_lower = error_message.lower()
    
    # Check for invalid URL indicators FIRST (highest priority)
    invalid_url_indicators = [
        "invalid url",
        "invalid github url",
        "malformed",
        "bad url",
        "could not extract owner/repo",
        "invalid repository format",
        "only github repositories are supported"
    ]
    
    if any(indicator in error_lower for indicator in invalid_url_indicators):
        return {
            "is_private": None,
            "error_type": "invalid_url",
            "reason": "Invalid repository URL format",
            "confidence": 0.9,
            "suggested_fixes": []
        }
    
    # Check for explicit authentication/permission errors (definitely private)
    explicit_private_indicators = [
        "authentication failed",
        "permission denied",
        "403 forbidden",
        "access denied",
        "requires authentication"
    ]
    
    if any(indicator in error_lower for indicator in explicit_private_indicators):
        return {
            "is_private": True,
            "error_type": "private",
            "reason": "Repository is private and requires authentication",
            "confidence": 1.0,
            "suggested_fixes": ["Make repository public in GitHub settings"]
        }
    
    # The tricky case: "repository not found" or "could not read from remote repository"
    # Git gives this for BOTH private repos AND non-existent repos
    ambiguous_indicators = [
        "repository not found",
        "could not read from remote repository",
        "remote: repository not found"
    ]
    
    if any(indicator in error_lower for indicator in ambiguous_indicators):
        # Use heuristics to distinguish:
        
        # 1. Check if URL looks like a user profile instead of a repo
        if repo_url:
            url_lower = repo_url.lower().strip()
            # Profile URLs: github.com/username (no second path segment)
            # Repo URLs: github.com/username/reponame
            if url_lower.startswith('http'):
                path_parts = url_lower.replace('https://', '').replace('http://', '').split('/')
                # Remove github.com and filter empty strings
                path_parts = [p for p in path_parts[1:] if p and p != '.git']
                
                if len(path_parts) == 0:
                    # Just github.com
                    return {
                        "is_private": None,
                        "error_type": "invalid_url",
                        "reason": "URL points to GitHub homepage, not a repository",
                        "confidence": 1.0,
                        "suggested_fixes": []
                    }
                elif len(path_parts) == 1:
                    # github.com/username - profile URL, not a repo
                    return {
                        "is_private": None,
                        "error_type": "invalid_url",
                        "reason": f"URL points to user profile ({path_parts[0]}), not a repository",
                        "confidence": 0.9,
                        "suggested_fixes": []
                    }
        
        # 2. If error mentions "404" explicitly, it's likely not found
        if "404" in error_lower:
            return {
                "is_private": False,
                "error_type": "not_found",
                "reason": "Repository does not exist (404)",
                "confidence": 0.9,
                "suggested_fixes": []
            }
        
        # 3. Check if repo is actually accessible before assuming private
        # This prevents false positives for public repos that failed for other reasons
        from ..services.classification import check_repo_public
        is_public = check_repo_public(repo_url)
        if is_public is True:
            # Repo IS public - analysis failed for another reason
            return {
                "is_private": False,
                "error_type": "other",
                "reason": "Repository is public but analysis failed (possibly due to timeout or transient error)",
                "confidence": 0.8,
                "suggested_fixes": ["Re-run analysis for this team"]
            }
        
        # 4. Default assumption: If we can't tell AND repo isn't accessible, assume PRIVATE
        # Reasoning: It's better to alert teams about potentially private repos
        # than to miss private repos and mark them as "not found"
        return {
            "is_private": True,
            "error_type": "private",
            "reason": "Repository not accessible (likely private or requires authentication)",
            "confidence": 0.6,
            "suggested_fixes": ["Make repository public in GitHub settings"]
        }
    
    # Check for explicit "does not exist" messages
    not_found_indicators = [
        "does not exist",
        "404",
        "not found",
        "could not resolve host"
    ]
    
    if any(indicator in error_lower for indicator in not_found_indicators):
        return {
            "is_private": False,
            "error_type": "not_found",
            "reason": "Repository not found or does not exist",
            "confidence": 0.8,
            "suggested_fixes": []
        }
    
    # Unknown error
    return {
        "is_private": None,
        "error_type": "other",
        "reason": error_message[:200],  # Truncate long errors
        "confidence": 0.3,
        "suggested_fixes": []
    }


@router.post("/check-batch/{batchId}")
async def check_batch_repo_privacy(
    batchId: str = Path(..., description="Batch ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    Extract privacy status from analysis failures for all repos in a batch.
    Also identifies teams with missing repo URLs.
    Uses existing analysis job error messages instead of making GitHub API calls.
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Use the internal function
    return check_batch_repo_privacy_internal(batchId)


@router.get("/list-private/{batchId}")
async def list_private_repos(
    batchId: str = Path(..., description="Batch ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of teams with private repositories, repos not found, invalid URLs, or missing repos.
    Uses data extracted from analysis failures.
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Get all teams with their privacy status
    teams_response = supabase.table("teams").select(
        "id, team_name, repo_url, is_private, last_privacy_check, status, validation_status, metadata, students(name, email)"
    ).eq("batch_id", batchId).execute()
    
    all_teams = teams_response.data or []
    
    # Separate teams by status
    private_teams = []
    not_found_teams = []
    invalid_teams = []
    missing_teams = []
    
    for team in all_teams:
        is_private = team.get("is_private")
        last_checked = team.get("last_privacy_check")
        status = team.get("status", "pending")
        repo_url = team.get("repo_url")
        
        # Extract project statement from metadata
        metadata = team.get("metadata", {}) or {}
        ingestion = metadata.get("ingestion", {}) or {}
        project_statement = ingestion.get("project_statement", "")
        
        students = team.get("students", [])
        student_emails = [s.get("email") for s in students if s.get("email")]
        
        team_info = {
            "teamId": team["id"],
            "teamName": team["team_name"],
            "repoUrl": repo_url,
            "projectStatement": project_statement,
            "lastChecked": last_checked,
            "status": status,
            "studentCount": len(students),
            "studentEmails": student_emails
        }
        
        # Check for missing repo URL first
        if not repo_url or repo_url.strip() == "":
            # Always include teams with missing URLs, regardless of check status
            missing_teams.append({**team_info, "issueType": "missing"})
            continue
        
        # Include teams that have been checked OR have is_private set
        # This ensures teams with privacy issues show up even if last_privacy_check is NULL
        if last_checked is None and is_private is None:
            # Skip teams that haven't been checked and don't have privacy status
            continue
        
        validation_status = team.get("validation_status", "")
        
        # Classify based on is_private value and validation_status
        if is_private is True:
            private_teams.append({**team_info, "issueType": "private"})
        elif is_private is False:
            not_found_teams.append({**team_info, "issueType": "not_found"})
        elif is_private is None and last_checked:
            # Only mark as invalid URL if validation_status explicitly says so
            if validation_status in ("invalid_url", "missing_url", "profile_url"):
                invalid_teams.append({**team_info, "issueType": "invalid"})
            # else: team was checked but URL is valid — skip (not an issue to report)
    
    return {
        "success": True,
        "totalPrivateRepos": len(private_teams),
        "totalNotFoundRepos": len(not_found_teams),
        "totalInvalidRepos": len(invalid_teams),
        "totalMissingRepos": len(missing_teams),
        "privateTeams": private_teams,
        "notFoundTeams": not_found_teams,
        "invalidTeams": invalid_teams,
        "missingTeams": missing_teams
    }


@router.post("/send-alerts/{batchId}")
async def send_private_repo_alerts(
    batchId: str = Path(..., description="Batch ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    Send email alerts to teams with repository issues (private, not found, invalid, or missing).
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Get all teams with repo issues (is_private = True, False, or NULL after check)
    teams_response = supabase.table("teams").select(
        "id, team_name, repo_url, is_private, last_privacy_check, students(name, email)"
    ).eq("batch_id", batchId).not_.is_("last_privacy_check", "null").execute()
    
    teams = teams_response.data or []
    
    # Filter for teams with issues only
    teams_with_issues = []
    for team in teams:
        is_private = team.get("is_private")
        repo_url = team.get("repo_url")
        # Include if: private (True), not found (False), invalid (None), or missing (no URL)
        if is_private is not None or team.get("last_privacy_check"):
            teams_with_issues.append(team)
    
    if not teams_with_issues:
        return {
            "success": True,
            "message": "No teams with repository issues found",
            "totalTeams": 0,
            "emailsSent": 0,
            "emailsFailed": 0
        }
    
    emails_sent = 0
    emails_failed = 0
    details = []
    
    for team in teams_with_issues:
        team_id = team["id"]
        team_name = team["team_name"]
        repo_url = team.get("repo_url")
        is_private = team.get("is_private")
        students = team.get("students", [])
        
        # Check for missing repo URL first
        if not repo_url or repo_url.strip() == "":
            issue_type_key = "missing"
        # Determine issue type based on is_private value
        elif is_private is True:
            issue_type_key = "private"
        elif is_private is False:
            issue_type_key = "not_found"
        else:  # None
            issue_type_key = "invalid"
        
        # Get student emails
        student_emails = [s.get("email") for s in students if s.get("email")]
        
        if not student_emails:
            emails_failed += 1
            details.append({
                "teamId": team_id,
                "teamName": team_name,
                "issueType": issue_type_key,
                "status": "failed",
                "error": "No student emails found"
            })
            continue
        
        # Generate email content using centralized templates
        subject = EmailTemplates.private_repo_alert_subject(team_name, issue_type_key)
        email_result = EmailTemplates.private_repo_alert_body(team_name, repo_url or "", issue_type_key)
        email_body = email_result.get("text", "") if isinstance(email_result, dict) else email_result
        email_html = email_result.get("html") if isinstance(email_result, dict) else None
        
        # Send email to each student
        team_sent = 0
        team_failed = []
        
        for email in student_emails:
            try:
                send_alert_email(
                    subject=subject,
                    body_text=email_body,
                    to_email=email,
                    html_body=email_html
                )
                team_sent += 1
            except Exception as e:
                print(f"Failed to send email to {email}: {e}")
                team_failed.append(email)
        
        if team_sent > 0:
            emails_sent += team_sent
            details.append({
                "teamId": team_id,
                "teamName": team_name,
                "issueType": issue_type_key,
                "status": "success",
                "sentTo": team_sent,
                "failedEmails": team_failed if team_failed else None
            })
        else:
            emails_failed += 1
            details.append({
                "teamId": team_id,
                "teamName": team_name,
                "issueType": issue_type_key,
                "status": "failed",
                "error": f"Failed to send to all recipients: {', '.join(team_failed)}"
            })
    
    return {
        "success": True,
        "message": f"Sent alerts to {len(teams_with_issues)} teams with repository issues",
        "totalTeams": len(teams_with_issues),
        "emailsSent": emails_sent,
        "emailsFailed": emails_failed,
        "details": details
    }



@router.post("/validate-batch/{batchId}")
async def validate_batch_repos(
    batchId: str = Path(..., description="Batch ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    Proactively validate all repository URLs in a batch.
    
    This endpoint runs validation BEFORE analysis, catching issues early:
    - URL format validation (protocol, platform, path structure)
    - GitHub ID matching (cross-reference with student GitHub IDs)
    - Classification with confidence scoring
    - Fix suggestion generation
    
    Unlike check-batch, this does NOT create analysis jobs - it only validates URLs.
    
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Get ALL teams in batch
    all_teams_response = supabase.table("teams").select(
        "id, team_name, repo_url, status"
    ).eq("batch_id", batchId).execute()
    
    all_teams = all_teams_response.data or []
    
    if not all_teams:
        return {
            "success": True,
            "message": "No teams found in this batch",
            "totalTeams": 0,
            "validatedTeams": 0,
            "issuesByType": {
                "valid": 0,
                "invalid_url": 0,
                "private": 0,
                "not_found": 0,
                "missing_url": 0
            },
            "details": []
        }
    
    validated_count = 0
    issues_by_type = {
        "valid": 0,
        "invalid_url": 0,
        "private": 0,
        "not_found": 0,
        "missing_url": 0
    }
    details = []
    
    for team in all_teams:
        team_id = team["id"]
        team_name = team["team_name"]
        repo_url = team.get("repo_url")
        
        # Step 1: Validate URL format
        url_validation = validate_repo_url(repo_url) if repo_url else None
        
        # Step 2: Match GitHub IDs (only if URL is valid)
        github_match = None
        if url_validation and url_validation.is_valid:
            try:
                github_match = match_github_ids(repo_url, team_id)
            except Exception as e:
                print(f"GitHub ID matching failed for team {team_id}: {e}")
        
        # Step 3: Classify the issue (no error message for proactive validation)
        classification = classify_repo_issue(
            error_message=None,  # No error message for proactive validation
            repo_url=repo_url,
            team_id=team_id
        )
        
        # Step 4: Generate fix suggestions
        suggested_fixes = []
        if url_validation and github_match:
            suggested_fixes = generate_fix_suggestions(
                classification=classification,
                url_validation=url_validation,
                github_match=github_match
            )
        elif classification.suggested_fixes:
            suggested_fixes = classification.suggested_fixes
        
        # Step 5: Update database with validation results
        update_data = {
            "validation_status": classification.error_type,
            "validation_confidence": classification.confidence,
            "validation_reason": classification.reason,
            "suggested_fixes": suggested_fixes,
            "last_validation_check": datetime.utcnow().isoformat()
        }
        
        # Also update is_private for backward compatibility
        if classification.error_type == "private":
            update_data["is_private"] = True
        elif classification.error_type == "not_found":
            update_data["is_private"] = False
        elif classification.error_type in ("invalid_url", "missing_url"):
            update_data["is_private"] = None
        
        supabase.table("teams").update(update_data).eq("id", team_id).execute()
        
        validated_count += 1
        
        # Count by type
        error_type = classification.error_type
        if error_type in issues_by_type:
            issues_by_type[error_type] += 1
        else:
            # If URL is valid and no issues, count as valid
            if url_validation and url_validation.is_valid and not classification.is_private:
                issues_by_type["valid"] += 1
        
        # Add to details
        details.append({
            "teamId": team_id,
            "teamName": team_name,
            "repoUrl": repo_url,
            "validationStatus": classification.error_type,
            "confidence": classification.confidence,
            "reason": classification.reason,
            "suggestedFixes": suggested_fixes
        })
    
    return {
        "success": True,
        "message": f"Validated {validated_count} teams",
        "totalTeams": len(all_teams),
        "validatedTeams": validated_count,
        "issuesByType": issues_by_type,
        "details": details
    }



@router.post("/validate-url")
async def validate_url_realtime(
    request_body: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Real-time validation of a single repository URL.
    
    This endpoint provides instant feedback for URL validation:
    - URL format validation
    - GitHub ID matching (if team_id provided)
    - Fix suggestions
    
    Used for real-time validation in the UI as users type.
    
    Request body:
    {
        "url": "https://github.com/owner/repo",
        "teamId": "optional-team-id"  // Optional, for GitHub ID matching
    }
    
    Response:
    {
        "isValid": true/false,
        "errorType": "missing_protocol" | "wrong_platform" | etc.,
        "normalizedUrl": "https://github.com/owner/repo",
        "reason": "Human-readable explanation",
        "confidence": 0.9,
        "suggestedFixes": ["https://github.com/student1/repo", ...],
        "githubIdMatch": {
            "owner": "owner",
            "studentGithubIds": ["student1", "student2"],
            "matches": true/false
        }
    }
    """
    url = request_body.get("url")
    team_id = request_body.get("teamId")
    
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    # Step 1: Validate URL format
    url_validation = validate_repo_url(url)
    
    # Step 2: Match GitHub IDs (if team_id provided and URL is valid)
    github_match = None
    if team_id and url_validation.is_valid:
        try:
            github_match = match_github_ids(url, team_id)
        except Exception as e:
            print(f"GitHub ID matching failed: {e}")
    
    # Step 3: Classify (no error message for real-time validation)
    classification = classify_repo_issue(
        error_message=None,
        repo_url=url,
        team_id=team_id or ""
    )
    
    # Step 4: Generate fix suggestions
    suggested_fixes = []
    if github_match:
        suggested_fixes = generate_fix_suggestions(
            classification=classification,
            url_validation=url_validation,
            github_match=github_match
        )
    elif classification.suggested_fixes:
        suggested_fixes = classification.suggested_fixes
    
    # Build response
    response = {
        "isValid": url_validation.is_valid,
        "errorType": url_validation.error_type,
        "normalizedUrl": url_validation.normalized_url,
        "reason": url_validation.reason if not url_validation.is_valid else "Valid GitHub repository URL",
        "confidence": classification.confidence,
        "suggestedFixes": suggested_fixes
    }
    
    # Add GitHub ID match info if available
    if github_match:
        response["githubIdMatch"] = {
            "owner": github_match.owner,
            "studentGithubIds": github_match.student_github_ids,
            "matches": github_match.matches
        }
    
    return response



@router.post("/apply-fixes")
async def apply_bulk_fixes(
    request_body: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Apply suggested fixes to multiple teams.
    
    This endpoint allows bulk application of suggested fixes:
    - Preview mode: Show what would be changed without applying
    - Apply mode: Apply fixes and log changes to audit trail
    
    Request body:
    {
        "teamIds": ["team-1", "team-2", ...],
        "preview": true/false  // If true, don't apply, just show what would change
    }
    
    Response:
    {
        "success": true,
        "totalFixes": 5,
        "successfulFixes": 4,
        "failedFixes": 1,
        "details": [
            {
                "teamId": "team-1",
                "teamName": "Team Alpha",
                "oldUrl": "github.com/owner/repo",
                "newUrl": "https://github.com/owner/repo",
                "status": "success" | "failed" | "preview",
                "error": "Optional error message"
            },
            ...
        ]
    }
    
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    team_ids = request_body.get("teamIds", [])
    preview = request_body.get("preview", False)
    
    if not team_ids:
        raise HTTPException(status_code=400, detail="teamIds is required")
    
    supabase = get_supabase()
    
    total_fixes = 0
    successful_fixes = 0
    failed_fixes = 0
    details = []
    
    for team_id in team_ids:
        try:
            # Fetch team data
            team_response = supabase.table("teams").select(
                "id, team_name, repo_url, suggested_fixes"
            ).eq("id", team_id).execute()
            
            teams = team_response.data or []
            
            if not teams:
                failed_fixes += 1
                details.append({
                    "teamId": team_id,
                    "teamName": "Unknown",
                    "oldUrl": None,
                    "newUrl": None,
                    "status": "failed",
                    "error": "Team not found"
                })
                continue
            
            team = teams[0]
            team_name = team.get("team_name")
            old_url = team.get("repo_url")
            suggested_fixes = team.get("suggested_fixes", [])
            
            # Check if there are suggested fixes
            if not suggested_fixes or len(suggested_fixes) == 0:
                failed_fixes += 1
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "oldUrl": old_url,
                    "newUrl": None,
                    "status": "failed",
                    "error": "No suggested fixes available"
                })
                continue
            
            # Use the first suggested fix (highest priority)
            new_url = suggested_fixes[0]
            
            # Skip if it's an informational message (not a URL)
            if not new_url.startswith("http"):
                failed_fixes += 1
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "oldUrl": old_url,
                    "newUrl": new_url,
                    "status": "failed",
                    "error": "Suggested fix is not a valid URL"
                })
                continue
            
            total_fixes += 1
            
            # Preview mode: Don't apply, just show what would change
            if preview:
                details.append({
                    "teamId": team_id,
                    "teamName": team_name,
                    "oldUrl": old_url,
                    "newUrl": new_url,
                    "status": "preview",
                    "error": None
                })
                continue
            
            # Apply mode: Update the URL and log to audit trail
            # Get current URL change history
            url_change_history = team.get("url_change_history", [])
            if not isinstance(url_change_history, list):
                url_change_history = []
            
            # Add new entry to audit trail
            url_change_history.append({
                "old_url": old_url,
                "new_url": new_url,
                "changed_by": current_user.get("id"),
                "changed_at": datetime.utcnow().isoformat(),
                "reason": "Bulk fix application"
            })
            
            # Update team record
            supabase.table("teams").update({
                "repo_url": new_url,
                "url_change_history": url_change_history,
                "validation_status": "valid",  # Reset validation status
                "suggested_fixes": []  # Clear suggested fixes
            }).eq("id", team_id).execute()
            
            successful_fixes += 1
            details.append({
                "teamId": team_id,
                "teamName": team_name,
                "oldUrl": old_url,
                "newUrl": new_url,
                "status": "success",
                "error": None
            })
            
        except Exception as e:
            failed_fixes += 1
            details.append({
                "teamId": team_id,
                "teamName": "Unknown",
                "oldUrl": None,
                "newUrl": None,
                "status": "failed",
                "error": str(e)
            })
    
    return {
        "success": True,
        "totalFixes": total_fixes,
        "successfulFixes": successful_fixes,
        "failedFixes": failed_fixes,
        "details": details
    }



@router.post("/send-individual-alert")
async def send_individual_repo_alert(
    request_body: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Send email alert to a single team about their repository issue.
    
    Admin selects the issue type and the system sends appropriate email.
    
    Request body:
    {
        "teamId": "team-123",
        "issueType": "private" | "not_found" | "invalid" | "missing"
    }
    
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    team_id = request_body.get("teamId")
    issue_type = request_body.get("issueType")
    
    if not team_id or not issue_type:
        raise HTTPException(status_code=400, detail="teamId and issueType are required")
    
    if issue_type not in ["private", "not_found", "invalid", "missing"]:
        raise HTTPException(status_code=400, detail="Invalid issue type")
    
    supabase = get_supabase()
    
    # Get team data
    team_response = supabase.table("teams").select(
        "id, team_name, repo_url, students(name, email)"
    ).eq("id", team_id).execute()
    
    teams = team_response.data or []
    
    if not teams:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = teams[0]
    team_name = team.get("team_name")
    repo_url = team.get("repo_url")
    students = team.get("students", [])
    
    # Get student emails
    student_emails = [s.get("email") for s in students if s.get("email")]
    
    if not student_emails:
        return {
            "success": False,
            "message": "No student emails found for this team",
            "emailsSent": 0
        }
    
    # Generate email content using centralized templates
    subject = EmailTemplates.private_repo_alert_subject(team_name, issue_type)
    email_result = EmailTemplates.private_repo_alert_body(team_name, repo_url or "", issue_type)
    email_body = email_result.get("text", "") if isinstance(email_result, dict) else email_result
    email_html = email_result.get("html") if isinstance(email_result, dict) else None
    
    # Send email to each student
    emails_sent = 0
    failed_emails = []
    
    for email in student_emails:
        try:
            send_alert_email(
                subject=subject,
                body_text=email_body,
                to_email=email,
                html_body=email_html
            )
            emails_sent += 1
        except Exception as e:
            print(f"Failed to send email to {email}: {e}")
            failed_emails.append(email)
    
    if emails_sent > 0:
        return {
            "success": True,
            "message": f"Email sent to {team_name}",
            "emailsSent": emails_sent,
            "failedEmails": failed_emails if failed_emails else None
        }
    else:
        return {
            "success": False,
            "message": f"Failed to send emails to all recipients",
            "emailsSent": 0,
            "failedEmails": failed_emails
        }
