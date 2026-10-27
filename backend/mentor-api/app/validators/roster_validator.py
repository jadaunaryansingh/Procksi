"""Roster record-linkage cascade (the "Validation Agent").

Deterministic, auditable, *not* an autonomous LLM agent. A submitted roster row
flows through cheap-to-expensive stages:

    0. format gate      -> malformed rows become ``invalid`` with a specific reason
    1. normalize        -> name / email / id canonical forms
    2. exact dedup      -> DB + within-file id/email collisions become ``duplicates``
    3. fuzzy scoring    -> Jaro-Winkler + token-sort (+ Double Metaphone confirmer)
    4. route            -> near-duplicates become ``review`` (never auto-rejected)

The matcher is **pure and synchronous**: ``validate_batch`` takes the parsed rows
and a snapshot of existing roster records and returns the bucketed result. The
service layer owns the async DB fetch. Thresholds live in :class:`RosterThresholds`
and the format rules in :class:`RosterConfig`, so both are easy to tune without
touching logic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.validators.roster_matching import (
    NameComparator,
    RapidFuzzNameComparator,
    canonical_email,
    canonical_student_id,
    damerau_distance,
    normalize_name,
    surnames_sound_alike,
)

# email-validator ships with pydantic[email]; degrade to a regex if absent.
try:  # pragma: no cover - import guard
    from email_validator import EmailNotValidError, validate_email

    _HAS_EMAIL_VALIDATOR = True
except ImportError:  # pragma: no cover
    _HAS_EMAIL_VALIDATOR = False

_EMAIL_FALLBACK_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --------------------------------------------------------------------------- #
# Tunable configuration
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RosterThresholds:
    """Routing cutoffs in [0, 1]. Tune against the evaluation harness."""

    # Minimum name similarity for a row to be flagged as a possible duplicate.
    review_min: float = 0.84
    # At/above this, the reason states the match is *strong* (still routed to a
    # human — we never auto-accept or auto-reject).
    strong_min: float = 0.93
    # Max canonical-ID edit distance to *annotate* a name match as also having a
    # near-identical roll number. A confirmer only — never a standalone trigger.
    id_confirm_distance: int = 1


@dataclass(frozen=True)
class RosterConfig:
    """Format-gate rules. Defaults are deliberately permissive so legitimate
    uploads are never hard-rejected on a guessed institutional pattern — tighten
    ``roll_pattern`` / ``allowed_years`` once the real Procksi format is confirmed."""

    # Permissive default: >=5 alphanumerics after canonicalization.
    roll_pattern: str = r"^[A-Z0-9]{5,20}$"
    allowed_years: frozenset[int] = frozenset({1, 2, 3, 4})
    # Branch/section are overwritten from the active semester at save time, so they
    # are validated leniently here (only when a value is present and clearly wrong).
    allowed_sections: Optional[frozenset[str]] = None  # None => accept any
    require_roll_pattern: bool = True


@dataclass
class _Record:
    """A normalized roster row used as a match candidate."""

    student_id: str
    name: str
    email: str
    canon_id: str
    canon_email: str
    norm_name: str

    @classmethod
    def build(cls, student_id: str, name: str, email: str) -> "_Record":
        return cls(
            student_id=student_id,
            name=name,
            email=email,
            canon_id=canonical_student_id(student_id),
            canon_email=canonical_email(email),
            norm_name=normalize_name(name),
        )


@dataclass
class _Candidate:
    record: _Record
    score: float
    phonetic: bool
    id_near: bool  # roll numbers are also within id_confirm_distance (confirmer)


class RosterValidator:
    """Orchestrates the cascade. Stateless; safe to reuse across requests."""

    def __init__(
        self,
        comparator: Optional[NameComparator] = None,
        thresholds: Optional[RosterThresholds] = None,
        config: Optional[RosterConfig] = None,
    ) -> None:
        self.comparator: NameComparator = comparator or RapidFuzzNameComparator()
        self.thresholds = thresholds or RosterThresholds()
        self.config = config or RosterConfig()
        self._roll_re = re.compile(self.config.roll_pattern)

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #
    def validate_batch(
        self,
        rows: list[dict[str, Any]],
        existing: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Bucket ``rows`` against the ``existing`` roster snapshot.

        ``existing`` items need ``student_id``, ``name``, ``email`` keys.
        Returns ``{valid, duplicates, invalid, review, summary}`` where ``valid``
        and ``duplicates`` are the raw row dicts (unchanged contract) and ``review``
        carries score / reason / candidate for the admin queue.
        """
        roster = [
            _Record.build(
                str(e.get("student_id", "")),
                str(e.get("name", "")),
                str(e.get("email", "")),
            )
            for e in existing
        ]
        existing_by_id = {r.canon_id: r for r in roster if r.canon_id}
        existing_by_email = {r.canon_email: r for r in roster if r.canon_email}

        # Candidate pool grows with accepted rows so within-file near-duplicates
        # (same person typed twice with a different id) are caught too.
        pool: list[_Record] = list(roster)
        seen_ids: dict[str, int] = {}
        seen_emails: dict[str, int] = {}

        valid: list[dict] = []
        duplicates: list[dict] = []
        invalid: list[dict] = []
        review: list[dict] = []

        for idx, raw in enumerate(rows):
            sid = str(raw.get("student_id", "")).strip()
            email = str(raw.get("email", "")).strip()
            name = str(raw.get("name", "")).strip()

            # ---- stage 0: format gate -------------------------------------
            reason = self._format_problem(raw, sid, name, email)
            if reason:
                invalid.append({"row": raw, "reason": reason})
                continue

            canon_id = canonical_student_id(sid)
            canon_em = canonical_email(email)

            # ---- stage 2: exact dedup (DB then within-file) ---------------
            db_hit = existing_by_id.get(canon_id) or existing_by_email.get(canon_em)
            if db_hit is not None:
                which = "roll number" if canon_id in existing_by_id else "email"
                duplicates.append(raw)
                seen_ids.setdefault(canon_id, idx)
                seen_emails.setdefault(canon_em, idx)
                continue

            if canon_id in seen_ids or canon_em in seen_emails:
                first = seen_ids.get(canon_id, seen_emails.get(canon_em))
                duplicates.append(raw)
                continue

            # ---- stage 3/4: fuzzy score + route ---------------------------
            cand = self._best_candidate(canon_id, canon_em, name, pool)
            if cand is not None:
                review.append(self._review_payload(raw, cand))
                # Register keys so an identical later row is caught as a dup, but
                # do NOT add to the pool — it isn't an accepted record yet.
                seen_ids.setdefault(canon_id, idx)
                seen_emails.setdefault(canon_em, idx)
                continue

            # ---- clean new row -------------------------------------------
            valid.append(raw)
            rec = _Record.build(sid, name, email)
            pool.append(rec)
            seen_ids[canon_id] = idx
            seen_emails[canon_em] = idx

        summary = {
            "total": len(rows),
            "valid": len(valid),
            "duplicates": len(duplicates),
            "invalid": len(invalid),
            "review": len(review),
        }
        return {
            "valid": valid,
            "duplicates": duplicates,
            "invalid": invalid,
            "review": review,
            "summary": summary,
        }

    # ------------------------------------------------------------------ #
    # Stage 0 — format gate
    # ------------------------------------------------------------------ #
    def _format_problem(self, raw: dict, sid: str, name: str, email: str) -> Optional[str]:
        missing = [
            label
            for label, value in (("student_id", sid), ("name", name), ("email", email))
            if not value
        ]
        if missing:
            return f"Missing required field(s): {', '.join(missing)}"

        if not self._is_valid_email(email):
            return f"Invalid email format: '{email}'"

        if self.config.require_roll_pattern:
            if not self._roll_re.match(canonical_student_id(sid)):
                return f"Roll number '{sid}' does not match the expected format"

        year_raw = raw.get("year", None)
        if year_raw not in (None, "", "nan"):
            try:
                year = int(float(str(year_raw)))
            except (ValueError, TypeError):
                return f"Year '{year_raw}' is not a number"
            if year not in self.config.allowed_years:
                allowed = ", ".join(map(str, sorted(self.config.allowed_years)))
                return f"Year {year} is out of range (allowed: {allowed})"

        if self.config.allowed_sections is not None:
            section = str(raw.get("section", "")).strip().upper()
            if section and section not in self.config.allowed_sections:
                return f"Section '{section}' is not an allowed section"

        return None

    def _is_valid_email(self, email: str) -> bool:
        if _HAS_EMAIL_VALIDATOR:
            try:
                validate_email(email, check_deliverability=False)
                return True
            except EmailNotValidError:
                return False
        return bool(_EMAIL_FALLBACK_RE.match(email))

    # ------------------------------------------------------------------ #
    # Stage 3/4 — candidate scoring + routing
    # ------------------------------------------------------------------ #
    def _best_candidate(
        self, canon_id: str, canon_em: str, name: str, pool: list[_Record]
    ) -> Optional[_Candidate]:
        """Route on **name** similarity (the reliable signal). Roll-number proximity
        is only attached as a confirmer — never used to flag on its own, because
        sequential institutional roll numbers are legitimately one edit apart."""
        norm_name = normalize_name(name)
        if not norm_name:
            return None

        best: Optional[_Candidate] = None
        for rec in pool:
            if not rec.norm_name:
                continue
            ns = self.comparator.score(norm_name, rec.norm_name)
            if ns >= self.thresholds.review_min and (best is None or ns > best.score):
                id_near = bool(
                    canon_id
                    and rec.canon_id
                    and canon_id != rec.canon_id
                    and damerau_distance(canon_id, rec.canon_id)
                    <= self.thresholds.id_confirm_distance
                )
                best = _Candidate(
                    rec, ns, surnames_sound_alike(name, rec.name), id_near
                )
        return best

    def _review_payload(self, raw: dict, cand: _Candidate) -> dict:
        strong = cand.score >= self.thresholds.strong_min
        rec = cand.record
        phon = " (same phonetic code)" if cand.phonetic else ""
        id_note = " Roll numbers are also nearly identical." if cand.id_near else ""
        strength = "Strong match" if strong else "Possible match"
        reason = (
            f"{strength}: name resembles roster '{rec.name}' "
            f"[{rec.student_id}]{phon} — similarity {cand.score:.2f}. "
            f"Possible same person / typo.{id_note}"
        )
        return {
            "row": raw,
            "score": round(float(cand.score), 4),
            "reason": reason,
            "match_type": "id_near" if cand.id_near else "name",
            "phonetic_match": cand.phonetic,
            "strong": strong,
            "candidate": {
                "student_id": rec.student_id,
                "name": rec.name,
                "email": rec.email,
            },
        }
