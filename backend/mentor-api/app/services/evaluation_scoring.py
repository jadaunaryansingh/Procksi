"""Server-side bounds for submitted evaluation scores.

Pure logic — no DB, no FastAPI — so it can be unit tested without credentials.

Why this exists: the mentor evaluation form computes a team's total in the
browser and POSTs it, and the endpoint used to store that number verbatim. Any
value was accepted, so a crafted request (or simply a bug in the client-side
averaging) could write an arbitrary grade. The client may still propose the
total, but the server now decides whether it is admissible.
"""
from __future__ import annotations

from typing import Iterable, Optional

# Cycles configured without a rubric are scored out of 100 in the UI.
DEFAULT_MAX_TOTAL = 100


class ScoreOutOfRange(ValueError):
    """Raised when a submitted total is outside what the rubric allows."""


def rubric_max_total(rubrics: Optional[Iterable[dict]]) -> int:
    """Highest total this cycle's rubric can award.

    Sums `max_marks` across the cycle's criteria. Rows with a missing or
    non-numeric value contribute nothing rather than breaking the whole check.
    A cycle with no rubric falls back to the conventional 100.
    """
    total = 0
    found = False
    for row in rubrics or []:
        try:
            total += int((row or {}).get("max_marks"))
            found = True
        except (TypeError, ValueError):
            continue
    return total if found else DEFAULT_MAX_TOTAL


def validate_total_score(value, max_total: int) -> int:
    """Return the score as an int, or raise ScoreOutOfRange.

    Accepts 0..max_total inclusive. Anything non-numeric, negative, or above the
    ceiling is rejected — the caller turns this into a 400.
    """
    try:
        score = int(value)
    except (TypeError, ValueError):
        raise ScoreOutOfRange(
            f"Score must be a whole number between 0 and {max_total}."
        ) from None

    if score < 0 or score > max_total:
        raise ScoreOutOfRange(
            f"Score {score} is outside the permitted range 0–{max_total} for this cycle."
        )
    return score
