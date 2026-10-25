"""Normalization + pluggable comparison primitives for roster record-linkage.

This module is intentionally **pure and synchronous** — no DB, no async, no I/O.
That keeps the matching logic trivially unit-testable and lets the comparison
engine be swapped later (RapidFuzz -> Splink/Zingg/pg_trgm) without touching the
service layer that calls it. The cascade that orchestrates these primitives lives
in ``roster_validator.py``.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional, Protocol, runtime_checkable

from rapidfuzz import fuzz
from rapidfuzz.distance import DamerauLevenshtein, JaroWinkler

# Double Metaphone is an *optional* confirmer. If jellyfish isn't installed the
# cascade still works — it just loses the phonetic-agreement annotation.
try:  # pragma: no cover - import guard
    from jellyfish import metaphone

    _HAS_PHONETIC = True
except ImportError:  # pragma: no cover
    metaphone = None  # type: ignore
    _HAS_PHONETIC = False


# --------------------------------------------------------------------------- #
# Normalization (stage 1 of the cascade)
# --------------------------------------------------------------------------- #
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")
_ID_STRIP_RE = re.compile(r"[\s\-_/.]")

_GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}


def strip_accents(text: str) -> str:
    """Drop combining marks so 'José' and 'Jose' compare equal."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_name(name: Optional[str]) -> str:
    """Casefold, de-accent, strip punctuation, collapse whitespace."""
    if not name:
        return ""
    text = strip_accents(str(name)).casefold()
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def name_tokens(name: Optional[str]) -> list[str]:
    norm = normalize_name(name)
    return norm.split() if norm else []


def canonical_email(email: Optional[str]) -> str:
    """Lowercase + trim; for Gmail also strip dots and ``+tag`` from the local part."""
    if not email:
        return ""
    text = str(email).strip().casefold()
    if "@" not in text:
        return text
    local, _, domain = text.partition("@")
    local = local.split("+", 1)[0]
    if domain in _GMAIL_DOMAINS:
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def canonical_student_id(student_id: Optional[str]) -> str:
    """Uppercase and strip separators so 'gla-2021/001' == 'GLA2021001'."""
    if student_id is None:
        return ""
    return _ID_STRIP_RE.sub("", str(student_id).strip().upper())


def phonetic_code(token: Optional[str]) -> str:
    """Metaphone code for a single token; '' if phonetics unavailable/empty."""
    if not token or not _HAS_PHONETIC:
        return ""
    return metaphone(strip_accents(str(token)))  # type: ignore[misc]


def surnames_sound_alike(name_a: str, name_b: str) -> bool:
    """True if the last tokens of two names share a phonetic code (a *confirmer*).

    Never used to decide a match on its own — only to add evidence/confidence to a
    border-line name-similarity hit. Returns False when phonetics are unavailable.
    """
    if not _HAS_PHONETIC:
        return False
    ta, tb = name_tokens(name_a), name_tokens(name_b)
    if not ta or not tb:
        return False
    ca, cb = phonetic_code(ta[-1]), phonetic_code(tb[-1])
    return bool(ca) and ca == cb


# --------------------------------------------------------------------------- #
# Pluggable comparator interface (stage 4 of the cascade)
# --------------------------------------------------------------------------- #
@runtime_checkable
class NameComparator(Protocol):
    """Swap-in point for the scoring engine. Inputs are *normalized* names."""

    def score(self, a_norm: str, b_norm: str) -> float:  # pragma: no cover - protocol
        """Return a similarity in [0.0, 1.0]."""
        ...


class RapidFuzzNameComparator:
    """Default comparator: Jaro-Winkler (typo tolerance) combined with a
    token-sort ratio (absorbs given/surname order swaps).

    We take the **max** of the two so either failure mode — a transposed letter
    *or* a reordered name — still scores high, while token-*sort* (not token-set)
    avoids the over-matching that a bare common surname would cause.
    """

    def score(self, a_norm: str, b_norm: str) -> float:
        if not a_norm or not b_norm:
            return 0.0
        jw = JaroWinkler.normalized_similarity(a_norm, b_norm)
        token_sort = fuzz.token_sort_ratio(a_norm, b_norm) / 100.0
        return max(jw, token_sort)


def id_similarity(canon_a: str, canon_b: str) -> float:
    """Jaro-Winkler over canonical IDs. NOTE: institutional roll numbers share long
    common prefixes and run sequentially, so this is *not* safe as a standalone
    duplicate trigger (adjacent rolls look near-identical). Kept as a utility."""
    if not canon_a or not canon_b:
        return 0.0
    return JaroWinkler.normalized_similarity(canon_a, canon_b)


def damerau_distance(canon_a: str, canon_b: str) -> int:
    """Edit distance with transpositions. Used only as a *confirmer* alongside a
    name match (e.g. 'BCA1234' vs 'BCA1243' is distance 1) — never on its own,
    because two adjacent legitimate roll numbers are also distance 1."""
    if not canon_a or not canon_b:
        return max(len(canon_a), len(canon_b))
    return DamerauLevenshtein.distance(canon_a, canon_b)
