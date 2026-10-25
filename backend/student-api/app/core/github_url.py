"""Strict validation for user-supplied GitHub repository URLs.

The repository-visibility check used to gate on `"github.com" in url.lower()`.
That substring can sit anywhere — in the query string, the path, or the userinfo
segment — so both the scheme and the host were attacker-controlled, and the URL
was then fetched with redirects followed. `http://169.254.169.254/latest/meta-data/?ref=github.com`
passes that check, which turned the endpoint into a probe for cloud metadata and
internal services.

Validation here parses the URL and matches the *parsed hostname* exactly, so no
amount of decoration in other parts of the URL can influence which host is
contacted.
"""

from __future__ import annotations

import urllib.parse

ALLOWED_HOSTS = frozenset({"github.com", "www.github.com"})
GITHUB_API = "https://api.github.com"


def parse_repo(url: str | None) -> tuple[str, str] | None:
    """Return (owner, repo) for a valid public GitHub repo URL, else None.

    Rejects anything that is not https, not exactly github.com, or carries
    userinfo (`user@host`, which can disguise the real host to a careless reader).
    """
    if not url:
        return None

    candidate = str(url).strip()
    if not candidate:
        return None

    # A bare "github.com/owner/repo" is a common paste; assume https rather than
    # allowing a scheme-less value through to the fetcher.
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    try:
        parsed = urllib.parse.urlsplit(candidate)
    except ValueError:
        return None

    if parsed.scheme != "https":
        return None
    if parsed.username or parsed.password or "@" in parsed.netloc:
        return None
    if (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        return None
    if parsed.port not in (None, 443):
        return None

    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        return None

    owner, repo = segments[0], segments[1]
    if not owner or not repo:
        return None
    return owner, repo


def api_url(owner: str, repo: str) -> str:
    """Repository metadata endpoint on a fixed host, with path components quoted."""
    return f"{GITHUB_API}/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}"
