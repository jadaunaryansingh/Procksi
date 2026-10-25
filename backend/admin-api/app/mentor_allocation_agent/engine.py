"""
allocation_engine.py — pure, dependency-light matching logic for the Mentor
Allocation Agent (admin-api / Supabase world).

This mirrors the proven scoring in ``mentor-api/app/services/ai_service.py`` but
operates on plain dicts sourced from the Supabase ``teams_validation`` + ``mentors``
tables (the live source of truth) instead of the SQLAlchemy ``teams`` stub.

Rule score (deterministic, no API key required):
    domain 40% + keywords 30% + experience 10% + availability 20%

Embeddings/AI similarity are intentionally omitted here: the deployment has no
NVIDIA/OpenAI key, so the existing engine already collapses to rule-only. Rule
mode is fully functional and the agent stays self-contained.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN TAXONOMY — kept in sync with ai_service._DOMAIN_CLUSTERS
# ─────────────────────────────────────────────────────────────────────────────
_DOMAIN_CLUSTERS: List[set] = [
    {"ai", "artificial intelligence", "machine learning", "ml", "deep learning",
     "neural networks", "nlp", "natural language processing", "computer vision",
     "data science", "data analysis", "data analytics", "generative ai", "llm",
     "large language models", "reinforcement learning"},
    {"web development", "web dev", "frontend", "front-end", "backend", "back-end",
     "full stack", "full-stack", "software development", "software engineering",
     "react", "angular", "vue", "node.js", "django", "flask", "fastapi"},
    {"iot", "internet of things", "embedded systems", "embedded", "hardware",
     "robotics", "automation", "raspberry pi", "arduino", "real-time systems",
     "edge computing", "sensor networks"},
    {"cybersecurity", "cyber security", "network security", "security",
     "ethical hacking", "penetration testing", "cryptography", "privacy",
     "information security", "siem", "soc"},
    {"cloud", "cloud computing", "devops", "aws", "gcp", "azure", "docker",
     "kubernetes", "ci/cd", "infrastructure", "site reliability engineering",
     "sre", "mlops"},
    {"blockchain", "web3", "cryptocurrency", "smart contracts", "defi",
     "distributed ledger", "nft"},
    {"mobile", "android", "ios", "flutter", "react native", "mobile development",
     "swift", "kotlin"},
    {"database", "sql", "nosql", "data engineering", "etl", "data warehousing",
     "big data", "hadoop", "spark"},
    {"ar", "vr", "augmented reality", "virtual reality", "game development",
     "unity", "unreal engine", "xr", "metaverse"},
    {"business", "management", "entrepreneurship", "startup", "product management",
     "agile", "scrum", "project management"},
    {"healthcare", "health tech", "bioinformatics", "medical", "biomedical",
     "telemedicine", "digital health"},
]
_DOMAIN_TO_CLUSTER: Dict[str, int] = {}
for _i, _c in enumerate(_DOMAIN_CLUSTERS):
    for _d in _c:
        _DOMAIN_TO_CLUSTER[_d] = _i

# Flatten the taxonomy into a single skill/keyword vocabulary for extraction.
_DOMAIN_VOCAB = set(_DOMAIN_TO_CLUSTER.keys())

_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "using",
    "use", "based", "system", "systems", "project", "application", "app", "platform",
    "this", "that", "will", "are", "is", "be", "we", "our", "their", "it", "as", "by",
    "from", "at", "into", "via", "able", "user", "users", "data", "develop", "design",
    "implement", "build", "creating", "create", "management", "model", "models",
    "study", "analysis", "based", "etc", "also", "which", "can", "new", "more",
}


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def normalise_domains(value: Any) -> List[str]:
    """Accept a string / comma-or-pipe list / actual list → list of domain strings."""
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[;,|/]", str(value))
    return [d.strip() for d in (str(x) for x in items) if d and str(d).strip()]


def get_domain_overlap_score(
    team_domains: List[str], mentor_domains: List[str]
) -> Tuple[Optional[float], str]:
    """1.0 exact · 0.7 same cluster · None no overlap (reject) · 0.5 missing data."""
    if not team_domains or not mentor_domains:
        return 0.5, "Domain data missing; assumed partial match"
    tnorm = [_norm(d) for d in team_domains]
    mnorm = [_norm(d) for d in mentor_domains]
    exact = [d for d in tnorm if d in mnorm]
    if exact:
        return 1.0, f"Exact domain match: {exact}"
    t_ids = {_DOMAIN_TO_CLUSTER.get(d) for d in tnorm} - {None}
    m_ids = {_DOMAIN_TO_CLUSTER.get(d) for d in mnorm} - {None}
    if t_ids & m_ids:
        return 0.7, "Related domain cluster match"
    return None, "No domain overlap — REJECTED"


def extract_keywords(text: str, max_keywords: int = 12) -> List[str]:
    """No-API keyword extraction (RAKE-lite + domain-vocab boost).

    Pulls domain-vocabulary hits first, then the most frequent salient unigrams.
    Deterministic; safe with no AI key. This is M2's keyword step.
    """
    raw = _norm(text)
    if not raw:
        return []
    # 1) multi-word domain terms present verbatim
    found: List[str] = [term for term in _DOMAIN_VOCAB if " " in term and term in raw]
    # 2) frequent salient unigrams
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9+.#-]{2,}", raw)
    freq: Dict[str, int] = {}
    for tok in tokens:
        if tok in _STOPWORDS or len(tok) < 3:
            continue
        freq[tok] = freq.get(tok, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    for tok, _ in ranked:
        if tok not in found:
            found.append(tok)
        if len(found) >= max_keywords:
            break
    return found[:max_keywords]


def infer_domains(value: Any) -> List[str]:
    """Return taxonomy-recognised domain terms found in a string or list of terms.

    Used when a team's declared ``domain`` is generic ("General"/blank): we recover
    the real domain from the project title + extracted keywords so the domain filter
    stays meaningful instead of rejecting everyone.
    """
    if isinstance(value, list):
        terms = [_norm(t) for t in value]
        text = " ".join(terms)
    else:
        text, terms = _norm(value), []
    found = set(t for t in terms if t in _DOMAIN_VOCAB)
    for term in _DOMAIN_VOCAB:
        if " " in term and term in text:
            found.add(term)
    for tok in re.findall(r"[a-zA-Z][a-zA-Z0-9+./#-]{1,}", text):
        if tok in _DOMAIN_VOCAB:
            found.add(tok)
    return sorted(found)


def _tokenise(text: str) -> set:
    return {t for t in re.findall(r"[a-zA-Z][a-zA-Z0-9+.#-]{2,}", _norm(text)) if t not in _STOPWORDS}


def compute_rule_score(team: dict, mentor: dict, domain_score: float) -> Tuple[float, dict]:
    """domain 40% + keywords 30% + experience 10% + availability 20% → [0,1]."""
    breakdown: dict = {"domain": {"score": domain_score}}

    keywords = {_norm(k) for k in (team.get("required_skills") or []) if k}
    mentor_terms = {_norm(s) for s in (mentor.get("skills") or []) if s}
    mentor_terms |= _tokenise(mentor.get("expertise") or "")
    mentor_terms |= {_norm(d) for d in (mentor.get("domains") or [])}
    if keywords:
        matched = keywords & mentor_terms
        k_score = len(matched) / len(keywords)
        breakdown["keywords"] = {"score": round(k_score, 4),
                                 "matched": sorted(matched), "required": sorted(keywords)}
    else:
        k_score = 0.5
        breakdown["keywords"] = {"score": 0.5, "reason": "no keywords extracted"}

    exp = max(0, int(mentor.get("experience_years") or 0))
    e_score = min(exp / 15.0, 1.0)
    breakdown["experience"] = {"score": round(e_score, 4), "years": exp}

    current = max(0, int(mentor.get("current_teams") or 0))
    max_t = max(1, int(mentor.get("max_teams") or 2))
    a_score = max(0.0, 1.0 - current / max_t)
    breakdown["availability"] = {"score": round(a_score, 4),
                                 "current_teams": current, "max_teams": max_t}

    total = 0.40 * domain_score + 0.30 * k_score + 0.10 * e_score + 0.20 * a_score
    breakdown["total"] = round(total, 4)
    return round(total, 4), breakdown


def _reason(breakdown: dict, mentor_name: str) -> str:
    bits = []
    dom = breakdown.get("domain", {}).get("score")
    if dom == 1.0:
        bits.append("exact domain match")
    elif dom == 0.7:
        bits.append("related domain expertise")
    matched = breakdown.get("keywords", {}).get("matched", [])
    if matched:
        bits.append("skills in " + ", ".join(matched[:4]))
    yrs = breakdown.get("experience", {}).get("years", 0)
    if yrs >= 5:
        bits.append(f"{yrs} yrs experience")
    av = breakdown.get("availability", {})
    bits.append(f"{av.get('current_teams', 0)}/{av.get('max_teams', 2)} teams loaded")
    return f"{mentor_name}: " + "; ".join(bits) if bits else mentor_name


def rank_mentors_for_team(team: dict, mentors: List[dict], top_k: int = 5) -> List[dict]:
    """Hard-filter (capacity, domain) then rule-score; return ranked top-k with reasons."""
    team_domains = team.get("domain") or []
    out: List[dict] = []
    for m in mentors:
        current = int(m.get("current_teams") or 0)
        max_t = int(m.get("max_teams") or 2)
        if current >= max_t:
            continue  # capacity hard filter
        d_score, d_reason = get_domain_overlap_score(team_domains, m.get("domains") or [])
        if d_score is None:
            continue  # domain hard filter
        score, breakdown = compute_rule_score(team, m, d_score)
        out.append({
            "mentor_id": str(m.get("id")),
            "mentor_name": m.get("name"),
            "score": score,
            "breakdown": breakdown,
            "reason": _reason(breakdown, m.get("name") or "Mentor"),
        })
    out.sort(key=lambda c: c["score"], reverse=True)
    return out[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# RANK-AWARE DOMAIN MATCHING (current model)
# ─────────────────────────────────────────────────────────────────────────────
# Mentors no longer declare years of experience or a primary/secondary split.
# At signup they pick the live project domains and order them by preference, so
# ``mentor["domains"]`` is a RANK-ORDERED list (index 0 = strongest choice). We
# match a team to the mentor by the best (lowest-index) rank at which the
# mentor's domain overlaps the team's domain, then break ties on availability.
def _label_terms_and_clusters(label: Any) -> Tuple[set, set]:
    """Resolve a (possibly combined) domain label into the taxonomy vocab terms it
    contains and the cluster ids those map to.

    Handles the verbatim signup labels that aren't single taxonomy keys, e.g.
    ``"Machine Learning / AI"`` → {machine learning, ai} → {AI cluster};
    ``"IoT (Internet of Things)"`` → {iot, internet of things} → {IoT cluster};
    ``"Data Science / Analytics"`` → {data science} → {AI cluster}.
    """
    s = _norm(label)
    if not s:
        return set(), set()
    terms: set = set()
    # multi-word vocab phrases present verbatim anywhere in the label
    for term in _DOMAIN_VOCAB:
        if " " in term and term in s:
            terms.add(term)
    # single tokens (split on whitespace and the separators used in signup labels)
    for tok in re.split(r"[\s/,\|()\-]+", s):
        tok = tok.strip()
        if tok and tok in _DOMAIN_VOCAB:
            terms.add(tok)
    if s in _DOMAIN_VOCAB:
        terms.add(s)
    clusters = {_DOMAIN_TO_CLUSTER[t] for t in terms if t in _DOMAIN_TO_CLUSTER}
    return terms, clusters


def get_domain_rank_score(
    team_domains: List[str], mentor_domains_ranked: List[str]
) -> Tuple[Optional[float], str]:
    """Score a team↔mentor domain fit from the mentor's ranked domain list.

    Returns ``(score, reason)`` in [0,1], or ``(None, reason)`` when there is no
    overlap at all (the mentor is rejected for this team). An exact hit always
    beats a same-cluster hit at the same rank, and rank #1 always beats rank #2.

    Both sides are resolved through ``_label_terms_and_clusters`` first, so combined
    signup labels ("Machine Learning / AI", "IoT (Internet of Things)") match the
    right cluster instead of being silently rejected.
    """
    if not mentor_domains_ranked:
        return None, "Mentor declared no domains"
    if not team_domains:
        return 0.5, "Team domain missing; assumed partial match"
    # Team side → vocab terms + clusters (plus the raw normalized labels for exact compare)
    team_terms: set = set()
    team_clusters: set = set()
    for d in team_domains:
        t, c = _label_terms_and_clusters(d)
        team_terms |= t
        team_clusters |= c
        nd = _norm(d)
        if nd:
            team_terms.add(nd)
    for idx, md in enumerate(mentor_domains_ranked):
        m_terms, m_clusters = _label_terms_and_clusters(md)
        mn = _norm(md)
        if mn:
            m_terms.add(mn)
        if m_terms & team_terms:
            return round(max(0.6, 1.0 - 0.1 * idx), 4), f"Rank #{idx + 1} exact domain match: '{md}'"
        if m_clusters & team_clusters:
            return round(max(0.3, 0.6 - 0.1 * idx), 4), f"Rank #{idx + 1} related-domain match: '{md}'"
    return None, "No domain overlap — REJECTED"


def rank_mentors_by_domain(team: dict, mentors: List[dict], top_k: int = 5) -> List[dict]:
    """Rank mentors for a team by ranked-domain fit (0.8) + availability (0.2).

    Capacity-full and no-overlap mentors are hard-filtered out. No experience or
    keyword signal is used — the mentor's domain ranking is the match.
    """
    team_domains = team.get("domain") or []
    out: List[dict] = []
    for m in mentors:
        current = int(m.get("current_teams") or 0)
        max_t = int(m.get("max_teams") or 2)
        if current >= max_t:
            continue  # capacity hard filter
        d_score, d_reason = get_domain_rank_score(team_domains, m.get("domains") or [])
        if d_score is None:
            continue  # domain hard filter
        a_score = max(0.0, 1.0 - current / max_t)
        score = round(0.8 * d_score + 0.2 * a_score, 4)
        out.append({
            "mentor_id": str(m.get("id")),
            "mentor_name": m.get("name"),
            "score": score,
            "domain_score": d_score,
            "availability": round(a_score, 4),
            "reason": f"{m.get('name') or 'Mentor'}: {d_reason}; {current}/{max_t} teams loaded",
        })
    out.sort(key=lambda c: c["score"], reverse=True)
    return out[:top_k]
