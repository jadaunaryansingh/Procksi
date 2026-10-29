"""
Contributor identity resolution helpers.

Merges commit/contributor aliases into canonical team members using:
1) email (full and local-part),
2) github username,
3) unique full-name fallback.
"""

from collections import Counter
import re
from typing import Any, Dict, List, Optional


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    return " ".join(text.split())


def _normalize_email(value: Any) -> str:
    return _normalize_text(value)


def _email_local_part(value: Any) -> str:
    email = _normalize_email(value)
    if "@" not in email:
        return ""
    return email.split("@", 1)[0]


def _normalize_github(value: Any) -> str:
    gh = _normalize_text(value)
    if gh.startswith("@"):
        gh = gh[1:]
    return gh


def _compact_alnum(value: Any) -> str:
    """Normalize to lowercase alphanumeric only (remove spaces/symbols)."""
    return "".join(ch for ch in _normalize_text(value) if ch.isalnum())


def _strip_trailing_digits(value: str) -> str:
    return re.sub(r"\d+$", "", value or "")


def _first_name_token(value: Any) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return ""
    return normalized.split(" ", 1)[0]


class TeamMemberIdentityResolver:
    """Resolve raw contributor names/emails to canonical team member identity."""

    def __init__(self, team_members: Optional[List[Dict[str, Any]]] = None):
        self.team_members: List[Dict[str, Any]] = team_members or []
        self._by_email: Dict[str, Dict[str, Any]] = {}
        self._by_email_local: Dict[str, Dict[str, Any]] = {}
        self._by_github: Dict[str, Dict[str, Any]] = {}
        self._by_unique_name: Dict[str, Dict[str, Any]] = {}
        self._by_compact_github: Dict[str, Dict[str, Any]] = {}
        self._by_compact_unique_name: Dict[str, Dict[str, Any]] = {}
        self._by_unique_first_name: Dict[str, Dict[str, Any]] = {}

        self._build_indexes()

    def _build_indexes(self) -> None:
        name_counts = Counter()
        compact_name_counts = Counter()
        first_name_counts = Counter()

        for member in self.team_members:
            normalized_name = _normalize_text(member.get("name"))
            compact_name = _compact_alnum(member.get("name"))
            first_name = _first_name_token(member.get("name"))
            if normalized_name:
                name_counts[normalized_name] += 1
            if compact_name:
                compact_name_counts[compact_name] += 1
            if first_name:
                first_name_counts[first_name] += 1

        for member in self.team_members:
            email = _normalize_email(member.get("email"))
            email_local = _email_local_part(member.get("email"))
            github = _normalize_github(member.get("github") or member.get("github_username"))
            compact_github = _compact_alnum(github)
            normalized_name = _normalize_text(member.get("name"))
            compact_name = _compact_alnum(member.get("name"))
            first_name = _first_name_token(member.get("name"))

            if email:
                self._by_email[email] = member
            if email_local:
                self._by_email_local[email_local] = member
            if github:
                self._by_github[github] = member
            if compact_github:
                self._by_compact_github[compact_github] = member
            if normalized_name and name_counts[normalized_name] == 1:
                self._by_unique_name[normalized_name] = member
            if compact_name and compact_name_counts[compact_name] == 1:
                self._by_compact_unique_name[compact_name] = member
            if first_name and first_name_counts[first_name] == 1:
                self._by_unique_first_name[first_name] = member

    def resolve_member(self, raw_name: Any, raw_email: Any = None) -> Optional[Dict[str, Any]]:
        email = _normalize_email(raw_email)
        email_local = _email_local_part(raw_email)
        name = _normalize_text(raw_name)
        gh_candidate = _normalize_github(raw_name)
        compact_candidate = _compact_alnum(raw_name)
        compact_no_digits = _strip_trailing_digits(compact_candidate)

        if email and email in self._by_email:
            return self._by_email[email]
        if email_local and email_local in self._by_email_local:
            return self._by_email_local[email_local]
        if gh_candidate and gh_candidate in self._by_github:
            return self._by_github[gh_candidate]
        if compact_candidate and compact_candidate in self._by_compact_github:
            return self._by_compact_github[compact_candidate]
        if compact_candidate and compact_candidate in self._by_compact_unique_name:
            return self._by_compact_unique_name[compact_candidate]
        if compact_no_digits and compact_no_digits in self._by_compact_unique_name:
            return self._by_compact_unique_name[compact_no_digits]

        # Safe fuzzy match: single compact full-name candidate by prefix.
        if compact_no_digits:
            compact_name_matches = [
                member
                for compact_name, member in self._by_compact_unique_name.items()
                if compact_name.startswith(compact_no_digits) or compact_no_digits.startswith(compact_name)
            ]
            unique_compact_matches = list({id(member): member for member in compact_name_matches}.values())
            if len(unique_compact_matches) == 1:
                return unique_compact_matches[0]

            # Safe fuzzy match: username starts with a unique first name.
            first_name_matches = [
                member
                for first_name, member in self._by_unique_first_name.items()
                if len(first_name) >= 3 and compact_no_digits.startswith(first_name)
            ]
            unique_first_matches = list({id(member): member for member in first_name_matches}.values())
            if len(unique_first_matches) == 1:
                return unique_first_matches[0]

        if name and name in self._by_unique_name:
            return self._by_unique_name[name]

        return None

    def resolve_name(self, raw_name: Any, raw_email: Any = None) -> str:
        member = self.resolve_member(raw_name, raw_email)
        if member and member.get("name"):
            return str(member.get("name"))
        return str(raw_name or "Unknown")


def merge_contributors_by_team_members(
    contributors: List[Dict[str, Any]],
    team_members: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Merge contributor records into canonical student identities."""
    resolver = TeamMemberIdentityResolver(team_members or [])
    merged: Dict[str, Dict[str, Any]] = {}

    for entry in contributors or []:
        raw_name = entry.get("author") or entry.get("name") or entry.get("contributorName") or "Unknown"
        raw_email = entry.get("email")

        canonical_member = resolver.resolve_member(raw_name, raw_email)
        canonical_name = canonical_member.get("name") if canonical_member else str(raw_name)
        canonical_email = (
            canonical_member.get("email") if canonical_member and canonical_member.get("email") else raw_email
        )

        key = _normalize_text(canonical_name) or _normalize_text(raw_name) or "unknown"
        if key not in merged:
            merged[key] = {
                "author": canonical_name,
                "name": canonical_name,
                "email": canonical_email,
                "commits": 0,
                "commit_count": 0,
                "additions": 0,
                "deletions": 0,
                "lines_changed": 0,
                "lines_added": 0,
                "lines_deleted": 0,
            }

        current = merged[key]

        commits = entry.get("commits", entry.get("commit_count", 0)) or 0
        additions = entry.get("additions", entry.get("lines_added", 0)) or 0
        deletions = entry.get("deletions", entry.get("lines_deleted", 0)) or 0
        lines_changed = entry.get("lines_changed")
        if lines_changed is None:
            lines_changed = additions + deletions

        current["commits"] += int(commits)
        current["commit_count"] += int(commits)
        current["additions"] += int(additions)
        current["deletions"] += int(deletions)
        current["lines_added"] += int(additions)
        current["lines_deleted"] += int(deletions)
        current["lines_changed"] += int(lines_changed)

    results = list(merged.values())
    results.sort(key=lambda x: x.get("commits", 0), reverse=True)
    return results
