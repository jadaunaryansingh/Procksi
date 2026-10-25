"""Mentoring domains offered on the signup form, sourced from the database.

Replaces the published-Google-Form CSV this used to read. The domains a mentor
can claim are now derived from the work students are actually doing — the
``domain`` column on ``teams_validation`` — so the picker stays in step with the
projects without anyone maintaining a second list.

That column is free text and arrives in three shapes:

    "General"                                   a single label
    '["Software"]'                              a JSON-encoded array
    "Artificial Intelligence, Computer Vision"  a comma-separated list

so a value has to be split into atoms before it means anything. Parsing and
aggregation are pure functions here; the fetch is separate and cached.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Iterable

logger = logging.getLogger(__name__)

# Values that carry no information as a mentoring domain.
_PLACEHOLDERS = {"general", "n/a", "na", "none", "other", "-", "tbd"}

# A single atom longer than this is a project blurb, not a domain label.
_MAX_LABEL_LEN = 60

# Separators between domains in a free-text value. "&" belongs here because the
# data uses an Oxford-style "A, B, & C": splitting on the comma alone left a
# bare "& C", and ten such fragments were being offered as selectable domains
# ("& HR Operations", "& Bio-Tech", "& Mobility", ...). A stray "&" is never a
# domain, so the cost of also splitting a genuine "X & Y" label is worth it —
# both halves still read as domains, which "& Y" never does.
_SEPARATORS = re.compile(r"\s*(?:,|&)\s*")

# Misspellings observed in the stored data, mapped to the intended label.
# Applied per atom after splitting, so a typo inside a list is corrected too.
# Keys are casefolded; add entries as new misspellings turn up.
_CORRECTIONS: dict[str, str] = {
    "artifical intelligence": "Artificial Intelligence",
}


def _canonical(label: str) -> str:
    """Apply a known spelling correction to one already-split label."""
    return _CORRECTIONS.get(label.casefold(), label)


def _split(value: str) -> list[str]:
    """Split one plain string on the separators and canonicalise each atom."""
    return [_canonical(part.strip()) for part in _SEPARATORS.split(value) if part.strip()]


def parse_domain_field(raw) -> list[str]:
    """Split one stored ``domain`` value into individual domain labels."""
    if not raw:
        return []
    value = str(raw).strip()
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                # Elements are split too, not returned verbatim: the data holds
                # '["Agritech, Resource Management, & Environmental Sensing"]',
                # a single JSON element carrying three domains.
                labels: list[str] = []
                for element in parsed:
                    labels.extend(_split(str(element)))
                return labels
        except (TypeError, ValueError):
            # Not valid JSON after all — fall through to separator splitting.
            pass
    return _split(value)


def _count_capitals(s: str) -> int:
    return sum(1 for c in s if c.isupper())


def collect_domains(rows: Iterable[dict], column: str = "domain") -> list[str]:
    """Distinct domain labels across ``rows``, cleaned and sorted.

    Deduplicated case-insensitively — the data holds near-duplicates differing
    only by capitalisation or a stray space ("Artificial Intelligence " vs
    "Artificial Intelligence") — keeping the better-capitalised spelling, which
    is almost always the intended one.
    """
    seen: dict[str, str] = {}
    for row in rows or []:
        for label in parse_domain_field((row or {}).get(column)):
            key = label.casefold()
            if key in _PLACEHOLDERS or len(label) > _MAX_LABEL_LEN:
                continue
            if key not in seen or _count_capitals(label) > _count_capitals(seen[key]):
                seen[key] = label
    return sorted(seen.values(), key=str.lower)


# In-memory cache shared across requests in this process.
_cache: dict = {"domains": None, "ts": 0.0}
_CACHE_TTL = 300.0


def _reset_cache_for_tests() -> None:
    _cache["domains"] = None
    _cache["ts"] = 0.0


async def _fetch_catalogue_rows() -> list[dict]:
    """Active domains from the curated catalogue, in display order.

    This used to read teams_validation.domain — free text produced by two
    unconstrained writers (an uploaded document's `Domain:` line, and an OpenAI
    enrichment step that invents a label per project). That yielded 145 distinct
    "domains" from 154 problem statements, 75% of them appearing exactly once,
    so the picker offered project descriptions as selectable expertise and
    could not tell AgTech from Agritech.

    It also meant a domain only became selectable once some team had been
    allocated that work, so the list lagged the catalogue of available projects.
    Reading the vocabulary directly removes both problems.
    """
    from app.core import rest_db
    return await rest_db.select(
        "domains",
        columns="name,kind,sort_order",
        eq={"is_active": True},
        order="sort_order",
    )


async def get_domains(fresh: bool = False) -> list[str]:
    """Domain labels for the signup form, cached for ``_CACHE_TTL`` seconds.

    Never raises: on failure it serves the last good result, or [] if there has
    never been one. The caller supplies the fallback — an empty list here must
    not leave signup with nothing selectable.
    """
    now = time.monotonic()
    if not fresh and _cache["domains"] is not None and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["domains"]

    try:
        rows = await _fetch_catalogue_rows()
        # The catalogue is already curated, so the parsing/dedupe pipeline that
        # free text needed is not applied here; only the display label is taken.
        # Order is the catalogue's own sort_order rather than alphabetical.
        domains = [str(r["name"]).strip() for r in rows if (r or {}).get("name")]
    except Exception as exc:
        logger.warning("domain_catalog: lookup failed: %s", exc)
        return _cache["domains"] or []

    _cache["domains"] = domains
    _cache["ts"] = now
    return domains
