# GitHub ID Matcher Service Implementation

## Overview

Implemented Task 3 from the spec: **Implement GitHub ID Matcher Service**

This service provides GitHub ID matching functionality to cross-reference repository URLs with student GitHub usernames, helping identify teams using incorrect or unrelated repositories.

## Files Created

### 1. `src/api/backend/services/github_id_matcher.py`

Main service implementation with:

#### Data Class: `GitHubIDMatchResult`
```python
@dataclass
class GitHubIDMatchResult:
    owner: str                      # Repository owner extracted from URL
    student_github_ids: List[str]   # GitHub usernames of students in team
    matches: bool                   # Whether owner matches any student
    suggested_urls: List[str]       # Suggested URLs based on student GitHub IDs
    confidence: float               # Confidence score (0.0-1.0)
```

#### Functions:

**`extract_owner_from_url(repo_url: str) -> Optional[str]`**
- Extracts repository owner from GitHub URL (first path segment)
- Validates URL has proper protocol and domain (github.com)
- Returns lowercased owner for case-insensitive comparison
- Returns None for invalid URLs

**`match_github_ids(repo_url: str, team_id: str) -> GitHubIDMatchResult`**
- Extracts owner from repository URL
- Fetches student GitHub usernames from database (students.github_username column)
- Compares owner with GitHub usernames (case-insensitive)
- Generates suggested URLs based on GitHub usernames
- Handles edge cases:
  - Teams with no students
  - Teams with no GitHub usernames
  - Organization repositories
  - Invalid URLs
  - Database query failures

## Confidence Scoring

The service assigns confidence scores based on match results:

| Scenario | Confidence | Description |
|----------|-----------|-------------|
| Exact match | 0.9 | Owner exactly matches a student's GitHub username |
| Case-insensitive match | 0.7 | Owner matches ignoring case |
| No match (likely org) | 0.5 | Owner doesn't match but looks like organization |
| No match | 0.3 | Owner doesn't match any student |
| No GitHub usernames | 0.5 | No students have GitHub usernames |
| Cannot extract owner | 0.5 | Invalid URL or extraction failed |

## Organization Detection

The service detects likely organization repositories based on:
- Owner contains hyphens
- Owner is longer than 20 characters
- Owner contains keywords: "org", "team", "group", "company", "project"

## Suggested URL Generation

When owner doesn't match any student GitHub username:
1. Extracts repo name from original URL (second path segment)
2. Generates suggested URLs: `https://github.com/{github_username}/{repo_name}`
3. Removes .git suffix from repo name if present
4. Falls back to "repo" as default name if extraction fails

## Testing

### Test Files Created:

1. **`test_github_id_matcher.py`** - Unit tests for owner extraction
   - Tests various URL formats
   - Tests edge cases (empty, None, invalid URLs)
   - Tests case normalization
   - All tests pass ✓

2. **`test_github_id_matcher_db.py`** - Database integration tests
   - Tests with real team data
   - Tests edge cases (non-existent teams, invalid URLs)
   - Verifies database queries work correctly
   - All tests pass ✓

## Requirements Validated

This implementation satisfies the following requirements from the spec:

- **US-2.1**: System extracts owner from repository URL ✓
- **US-2.2**: System fetches GitHub IDs for all students in a team ✓
- **US-2.3**: System compares URL owner with student GitHub IDs ✓
- **US-2.4**: System flags mismatches as warnings (not errors) ✓
- **US-2.5**: System suggests correct URLs based on student GitHub IDs ✓
- **US-2.6**: System handles teams where no students have GitHub IDs ✓
- **US-2.7**: System handles organization repositories ✓

## Database Schema

The service uses the existing database schema:
- **students table**: Uses `github_username` column (not `github_id`)
- **teams table**: Uses `id` and `repo_url` columns

## Integration Points

This service is designed to integrate with:
1. **URL Validation Service** (`url_validation.py`) - Already exists
2. **Classification Service** - To be implemented in Task 4
3. **Proactive Validation API** - To be implemented in Task 7
4. **Real-Time Validation API** - To be implemented in Task 8

## Usage Example

```python
from src.api.backend.services.github_id_matcher import match_github_ids

# Match GitHub IDs for a team
result = match_github_ids(
    repo_url="https://github.com/someuser/myrepo",
    team_id="6da5baf7-a610-4de6-84f6-097e2467404d"
)

print(f"Owner: {result.owner}")
print(f"Matches: {result.matches}")
print(f"Confidence: {result.confidence}")
print(f"Suggested URLs: {result.suggested_urls}")
```

## Next Steps

As per the spec, the optional tasks (3.3 and 3.4 - property tests and unit tests) were skipped as requested. The implementation is ready for integration with:

- Task 4: Classification Service with Confidence Scoring
- Task 7: Proactive Validation API Endpoint
- Task 8: Real-Time Validation API Endpoint

## Notes

- The service uses case-insensitive comparison for GitHub usernames
- All database queries use the standard Supabase client
- Error handling is graceful - returns neutral confidence on failures
- The service is stateless and can be called multiple times safely
