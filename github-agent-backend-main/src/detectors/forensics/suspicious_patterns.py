"""
Suspicious pattern detection for commits.
Detects generic messages, suspicious author names, and other red flags.
"""

import re
from typing import List


# Generic/default author names
SUSPICIOUS_AUTHOR_NAMES = {
    "user", "admin", "administrator", "root", "test", "owner",
    "default", "unknown", "none", "system", "pc", "desktop",
    "laptop", "computer", "home", "guest", "student",
    "ubuntu", "linux", "windows", "macos", "runner",
    "github", "actions", "bot", "ci", "server"
}


# Generic/lazy commit messages
GENERIC_COMMIT_MESSAGES = {
    ".", "..", "...", "a", "aa", "aaa", "aaaa",
    "test", "testing", "tests", "update", "updates", "updated",
    "fix", "fixes", "fixed", "bug", "bugs", "change", "changes",
    "commit", "save", "saved", "work", "wip", "todo",
    "asdf", "qwerty", "temp", "tmp", "empty", "blank",
    "1", "2", "3", "123", "abc", "xyz", "lol", "ok", "done",
    "initial commit", "first commit", "final commit", "last commit"
}


# Machine-generated name patterns
SUSPICIOUS_NAME_PATTERNS = [
    r'^DESKTOP-[A-Z0-9]+$',
    r'^LAPTOP-[A-Z0-9]+$',
    r'^PC-[A-Z0-9]+$',
    r'^[A-Z]{2,5}-[A-Z0-9]{5,}$',
    r'^user\d+$',
    r'^test\d*$',
    r'^\d+$',
]


def is_suspicious_author_name(author: str) -> tuple[bool, str]:
    """
    Check if author name is suspicious or machine-generated.
    
    Args:
        author: Author name to check
        
    Returns:
        (is_suspicious, reason)
    """
    name_lower = author.strip().lower()
    
    # Check against known suspicious names
    if name_lower in SUSPICIOUS_AUTHOR_NAMES:
        return True, f"Generic name: '{author}'"
    
    # Check against regex patterns
    for pattern in SUSPICIOUS_NAME_PATTERNS:
        if re.match(pattern, author, re.IGNORECASE):
            return True, f"Machine-generated name: '{author}'"
    
    return False, ""


def is_generic_commit_message(message: str) -> tuple[bool, str]:
    """
    Check if commit message is generic/lazy.
    
    Args:
        message: Commit message to check
        
    Returns:
        (is_generic, reason)
    """
    msg_stripped = message.strip().lower()
    
    if msg_stripped in GENERIC_COMMIT_MESSAGES:
        return True, f"Generic Message: '{message}'"
    
    if len(msg_stripped) < 3:
        return True, f"Too Short: '{message}'"
    
    return False, ""


def detect_superhuman_speed(commits: List[dict], threshold_seconds: int = 10) -> List[dict]:
    """
    Detect commits made suspiciously fast (< 10 seconds apart).
    Excludes merge commits (2+ parents).
    
    Args:
        commits: List of commits sorted by date
        threshold_seconds: Maximum time between commits
        
    Returns:
        List of superhuman speed commits
    """
    superhuman_commits = []
    
    for i in range(1, len(commits)):
        current = commits[i]
        previous = commits[i - 1]
        
        # Skip merge commits
        if current.get("parent_count", 1) > 1:
            continue
        
        # Check same author
        if current.get("author") != previous.get("author"):
            continue
        
        # Calculate time difference
        current_time = current.get("timestamp", 0)
        prev_time = previous.get("timestamp", 0)
        time_diff = abs(current_time - prev_time)
        
        if time_diff < threshold_seconds:
            superhuman_commits.append({
                "hash": current.get("hash", "")[:7],
                "author": current.get("author", "Unknown"),
                "time_diff": time_diff,
                "message": current.get("message", "")[:50]
            })
    
    return superhuman_commits
