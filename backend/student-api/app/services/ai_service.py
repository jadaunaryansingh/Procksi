"""
ai_service.py — Domain-aware Hybrid Matching Engine for mentor auto-assignment.

Matching pipeline:
  1. HARD FILTER  — Drop mentors with zero domain relevance (no overlap at all)
  2. RULE SCORE   — Domain(40%) + Skills(30%) + Experience(10%) + Availability(20%)
  3. AI SCORE     — Cosine similarity of NVIDIA NIM embeddings
  4. HYBRID SCORE — (Rule × 0.70) + (AI × 0.30)
  5. RANK         — Return top-3 candidates per team

Domain matching:
  • Exact/synonym match  → 1.0
  • Same domain cluster  → 0.7  (e.g. "AI" team, mentor has "Data Science")
  • No overlap           → REJECT  (never assigned)
"""

import logging
import numpy as np
from typing import Optional, List, Dict, Any, Tuple, Literal

from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# NVIDIA NIM / OpenAI client — lazy initialisation
# Client is only created when an API key is actually present, so the backend
# starts cleanly even when no AI key is configured.
# ─────────────────────────────────────────────────────────────────────────────
_client: Optional[AsyncOpenAI] = None
_EMBEDDING_DIMS = 1024 if settings.NVIDIA_API_KEY else 1536


def _get_client() -> Optional[AsyncOpenAI]:
    """Return a cached AsyncOpenAI client, or None if no API key is set."""
    global _client
    if _client is not None:
        return _client
    api_key = settings.NVIDIA_API_KEY or settings.OPENAI_API_KEY
    if not api_key:
        return None
    _client = AsyncOpenAI(
        api_key=api_key,
        base_url=settings.AI_BASE_URL if settings.NVIDIA_API_KEY else None,
        timeout=30.0,
    )
    return _client


# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN TAXONOMY — clusters of semantically related domains
# Mentors and teams in the SAME cluster are "related" (score = 0.7).
# Exact/synonym match within a cluster → score = 1.0.
# No cluster overlap → REJECT (score = None → filtered out).
# ─────────────────────────────────────────────────────────────────────────────
_DOMAIN_CLUSTERS: List[set] = [
    # Artificial Intelligence / Machine Learning
    {
        "ai", "artificial intelligence", "machine learning", "ml", "deep learning",
        "neural networks", "nlp", "natural language processing", "computer vision",
        "data science", "data analysis", "data analytics", "generative ai",
        "llm", "large language models", "reinforcement learning",
    },
    # Web & Software Development
    {
        "web development", "web dev", "frontend", "front-end", "backend", "back-end",
        "full stack", "full-stack", "software development", "software engineering",
        "react", "angular", "vue", "node.js", "django", "flask", "fastapi",
    },
    # IoT / Embedded / Hardware / Robotics
    {
        "iot", "internet of things", "embedded systems", "embedded", "hardware",
        "robotics", "automation", "raspberry pi", "arduino", "real-time systems",
        "edge computing", "sensor networks",
    },
    # Cybersecurity / Networking
    {
        "cybersecurity", "cyber security", "network security", "security",
        "ethical hacking", "penetration testing", "cryptography", "privacy",
        "information security", "siem", "soc",
    },
    # Cloud / DevOps / Infrastructure
    {
        "cloud", "cloud computing", "devops", "aws", "gcp", "azure", "docker",
        "kubernetes", "ci/cd", "infrastructure", "site reliability engineering",
        "sre", "mlops",
    },
    # Blockchain / Web3
    {
        "blockchain", "web3", "cryptocurrency", "smart contracts", "defi",
        "distributed ledger", "nft",
    },
    # Mobile Development
    {
        "mobile", "android", "ios", "flutter", "react native", "mobile development",
        "swift", "kotlin",
    },
    # Database / Data Engineering
    {
        "database", "sql", "nosql", "data engineering", "etl", "data warehousing",
        "big data", "hadoop", "spark",
    },
    # AR / VR / Game Development
    {
        "ar", "vr", "augmented reality", "virtual reality", "game development",
        "unity", "unreal engine", "xr", "metaverse",
    },
    # Business / Management / Entrepreneurship
    {
        "business", "management", "entrepreneurship", "startup", "product management",
        "agile", "scrum", "project management",
    },
    # Healthcare / Bioinformatics
    {
        "healthcare", "health tech", "bioinformatics", "medical", "biomedical",
        "telemedicine", "digital health",
    },
]

# Flat synonym → canonical lookup: each token maps to its cluster index
_DOMAIN_TO_CLUSTER: Dict[str, int] = {}
for _idx, _cluster in enumerate(_DOMAIN_CLUSTERS):
    for _d in _cluster:
        _DOMAIN_TO_CLUSTER[_d] = _idx


def _normalise_domain(d: str) -> str:
    """Lowercase and strip a domain string for consistent comparison."""
    return d.strip().lower()


def _domain_to_cluster_id(domain: str) -> Optional[int]:
    """Return the cluster index for a domain, or None if unknown."""
    return _DOMAIN_TO_CLUSTER.get(_normalise_domain(domain))


def get_domain_overlap_score(
    team_domains: List[str],
    mentor_domains: List[str],
) -> Tuple[Optional[float], str]:
    """
    Compute the domain relevance score between a team and a mentor.

    Returns
    -------
    (score, reason)
      score = 1.0  → exact/synonym match
      score = 0.7  → same broad cluster (related domain)
      score = None → NO overlap → mentor should be REJECTED
    reason is a human-readable explanation string.
    """
    if not team_domains or not mentor_domains:
        # Missing domain data — treat as partial match, not reject
        return 0.5, "Domain data missing; assumed partial match"

    team_norm   = [_normalise_domain(d) for d in team_domains]
    mentor_norm = [_normalise_domain(d) for d in mentor_domains]

    # ── Exact / synonym match (within same cluster entry) ────────────────
    exact_matches = [d for d in team_norm if d in mentor_norm]
    if exact_matches:
        return 1.0, f"Exact domain match: {exact_matches}"

    # ── Cluster (related domain) match ───────────────────────────────────
    team_cluster_ids   = {_domain_to_cluster_id(d) for d in team_norm} - {None}
    mentor_cluster_ids = {_domain_to_cluster_id(d) for d in mentor_norm} - {None}
    shared_clusters = team_cluster_ids & mentor_cluster_ids

    if shared_clusters:
        # Find which domains triggered the cluster hit for the explanation
        team_hits   = [d for d in team_norm   if _domain_to_cluster_id(d) in shared_clusters]
        mentor_hits = [d for d in mentor_norm if _domain_to_cluster_id(d) in shared_clusters]
        reason = f"Related domain cluster match — team: {team_hits}, mentor: {mentor_hits}"
        return 0.7, reason

    # ── No overlap ───────────────────────────────────────────────────────
    return None, (
        f"No domain overlap — team needs {team_norm}, "
        f"mentor has {mentor_norm} → REJECTED"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEXT BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def _safe_join(items: Any, label: str = "") -> str:
    if items is None:
        return ""
    if isinstance(items, str):
        return items
    try:
        return ", ".join(str(i) for i in items if i is not None)
    except Exception as e:
        logger.warning(f"_safe_join failed for {label}: {e}")
        return str(items)


def create_team_text(team_data: dict) -> str:
    """
    Build a rich, embedding-friendly representation of a team project.
    Includes inferred project type tag for better semantic matching.
    """
    title   = team_data.get("project_title") or ""
    desc    = team_data.get("description")   or ""
    domains = team_data.get("domain")        or []
    skills  = team_data.get("required_skills") or []

    # Infer project type from domains for richer context
    domain_norm = [_normalise_domain(d) for d in domains]
    project_type = "General"
    if any(_domain_to_cluster_id(d) == 0 for d in domain_norm):   # AI cluster
        project_type = "AI / Research"
    elif any(_domain_to_cluster_id(d) == 2 for d in domain_norm): # IoT cluster
        project_type = "IoT / Hardware"
    elif any(_domain_to_cluster_id(d) == 3 for d in domain_norm): # Security cluster
        project_type = "Cybersecurity"
    elif any(_domain_to_cluster_id(d) == 4 for d in domain_norm): # Cloud cluster
        project_type = "Cloud / DevOps"
    elif any(_domain_to_cluster_id(d) == 1 for d in domain_norm): # Web cluster
        project_type = "Web / Software"

    parts = [
        f"Project Title: {title}",
        f"Project Type: {project_type}",
        f"Domain: {_safe_join(domains, 'domain')}",
        f"Required Skills: {_safe_join(skills, 'required_skills')}",
        f"Description: {desc}",
    ]
    return "\n".join(parts)


def create_mentor_text(mentor_data: dict) -> str:
    """
    Build a rich, embedding-friendly representation of a mentor.
    """
    parts = [
        f"Mentor Name: {mentor_data.get('name', '')}",
        f"Expertise: {mentor_data.get('expertise', '')}",
        f"Domains: {_safe_join(mentor_data.get('domains'), 'domains')}",
        f"Skills: {_safe_join(mentor_data.get('skills'), 'skills')}",
        f"Experience: {mentor_data.get('experience_years', 0)} years",
    ]
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# EMBEDDINGS
# ─────────────────────────────────────────────────────────────────────────────

async def get_embedding(text: str) -> List[float]:
    """
    Generate a vector embedding via NVIDIA NIM or OpenAI.
    Returns a zero-vector on failure — cosine_similarity handles this gracefully.
    """
    api_key = settings.NVIDIA_API_KEY or settings.OPENAI_API_KEY
    if not api_key:
        logger.warning("No AI API key configured — returning zero embedding.")
        return [0.0] * _EMBEDDING_DIMS

    try:
        c = _get_client()
        if c is None:
            return [0.0] * _EMBEDDING_DIMS
        model = (
            settings.EMBEDDING_MODEL if settings.NVIDIA_API_KEY
            else "text-embedding-3-small"
        )
        extra_body: Optional[dict] = None
        if settings.NVIDIA_API_KEY and "nv-embedqa" in model:
            extra_body = {"input_type": "query"}

        response = await c.embeddings.create(
            input=[text.replace("\n", " ")],
            model=model,
            extra_body=extra_body,
        )
        return response.data[0].embedding

    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return [0.0] * _EMBEDDING_DIMS


# ─────────────────────────────────────────────────────────────────────────────
# SIMILARITY
# ─────────────────────────────────────────────────────────────────────────────

def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Cosine similarity ∈ [-1, 1].  Returns 0.0 on zero-vector input.
    Dimension mismatch is handled by trimming to the shorter vector (logged).
    """
    a = np.asarray(vec_a, dtype=np.float64)
    b = np.asarray(vec_b, dtype=np.float64)

    # Hard constraint: skip if dimension mismatch
    if a.shape != b.shape:
        logger.warning(
            f"Embedding dimension mismatch ({len(vec_a)} vs {len(vec_b)}) — "
            "returning 0.0"
        )
        return 0.0

    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ─────────────────────────────────────────────────────────────────────────────
# RULE-BASED SCORING
# Domain(40%) + Skills(30%) + Experience(10%) + Availability(20%)
# ─────────────────────────────────────────────────────────────────────────────

def compute_rule_based_score(
    team_data: dict,
    mentor_data: dict,
    *,
    domain_score_override: Optional[float] = None,
) -> Tuple[float, dict]:
    """
    Compute the deterministic rule-based component of the hybrid score.

    Parameters
    ----------
    team_data            : dict with keys domain, required_skills
    mentor_data          : dict with keys domains, skills, experience_years,
                           current_teams, max_teams
    domain_score_override: Pre-computed domain score (from domain filter step).
                           If None, it is computed here.

    Returns
    -------
    (total_score ∈ [0,1], breakdown_dict)
    """
    breakdown: dict = {}

    # ── Domain score (40%) ────────────────────────────────────────────────
    if domain_score_override is not None:
        d_score = domain_score_override
        breakdown["domain"] = {"score": d_score, "reason": "pre-computed"}
    else:
        d_score, d_reason = get_domain_overlap_score(
            team_data.get("domain") or [],
            mentor_data.get("domains") or [],
        )
        if d_score is None:
            # No domain overlap — hard reject
            breakdown["domain"] = {"score": 0.0, "reason": "REJECTED — no overlap"}
            return 0.0, breakdown
        breakdown["domain"] = {"score": d_score, "reason": d_reason}

    # ── Skills score (30%) ────────────────────────────────────────────────
    team_skills   = {s.strip().lower() for s in (team_data.get("required_skills") or []) if s}
    mentor_skills = {s.strip().lower() for s in (mentor_data.get("skills") or []) if s}

    if team_skills and mentor_skills:
        matched = team_skills & mentor_skills
        s_score = len(matched) / len(team_skills)   # recall: how many required skills covered
        breakdown["skills"] = {
            "score": round(s_score, 4),
            "matched": sorted(matched),
            "required": sorted(team_skills),
            "mentor_has": sorted(mentor_skills),
        }
    elif not team_skills:
        s_score = 0.5   # no required skills → partial credit
        breakdown["skills"] = {"score": s_score, "reason": "no required skills specified"}
    else:
        s_score = 0.0
        breakdown["skills"] = {"score": 0.0, "reason": "mentor has no skills listed"}

    # ── Experience score (10%) ────────────────────────────────────────────
    exp = max(0, mentor_data.get("experience_years") or 0)
    e_score = min(exp / 15.0, 1.0)   # 15+ years = 1.0
    breakdown["experience"] = {"score": round(e_score, 4), "years": exp}

    # ── Availability score (20%) ──────────────────────────────────────────
    current = max(0, mentor_data.get("current_teams") or 0)
    max_t   = max(1, mentor_data.get("max_teams") or 3)
    a_score = max(0.0, 1.0 - (current / max_t))
    breakdown["availability"] = {
        "score": round(a_score, 4),
        "current_teams": current,
        "max_teams": max_t,
    }

    # ── Weighted sum ──────────────────────────────────────────────────────
    total = (
        0.40 * d_score +
        0.30 * s_score +
        0.10 * e_score +
        0.20 * a_score
    )
    breakdown["total"] = round(total, 4)
    return round(total, 4), breakdown


def compute_hybrid_score(
    rule_score: float,
    ai_score: float,
) -> float:
    """
    Final Score = (Rule × 70%) + (AI Similarity × 30%).

    Rule-based is primary because domain expertise is non-negotiable.
    AI similarity is secondary — adds semantic richness.
    """
    return round(0.70 * rule_score + 0.30 * max(ai_score, 0.0), 4)


# ─────────────────────────────────────────────────────────────────────────────
# CORE MATCHING — returns top-3 ranked mentors for a single team
# ─────────────────────────────────────────────────────────────────────────────

def rank_mentors_for_team(
    team_data: dict,
    team_embedding: List[float],
    mentors: List[dict],  # list of mentor_data dicts (must include 'id', 'embedding')
    *,
    top_k: int = 3,
    mode: Literal["rule_only", "hybrid"] = "hybrid",
) -> List[dict]:
    """
    Rank available mentors for a team using the domain-aware hybrid engine.

    Hard constraints applied before scoring:
      ✗ current_teams >= max_teams  (at capacity)
      ✗ No domain overlap           (domain filter)
      ✗ Embedding dimension mismatch

    Parameters
    ----------
    team_data      : team dict with domain, required_skills, etc.
    team_embedding : embedding vector for the team's text
    mentors        : list of mentor dicts; each MUST have 'id' and 'embedding' keys
    top_k          : number of top candidates to return

    Returns
    -------
    List of candidate dicts sorted by hybrid_score DESC (up to top_k).
    Each dict contains full score breakdown and rejection reasons.
    """
    team_domains = team_data.get("domain") or []
    candidates: List[dict] = []
    rejected_count = {"capacity": 0, "domain": 0, "total": 0}

    for mentor in mentors:
        mentor_id   = mentor.get("id", "?")
        mentor_name = mentor.get("name", "?")

        # ── Hard constraint 1: Capacity ───────────────────────────────────
        current = mentor.get("current_teams", 0) or 0
        max_t   = mentor.get("max_teams", 3) or 3
        if current >= max_t:
            logger.debug(
                f"  ✗ REJECTED '{mentor_name}' — at capacity "
                f"({current}/{max_t})"
            )
            rejected_count["capacity"] += 1
            rejected_count["total"] += 1
            continue

        # ── Hard constraint 2: Domain filter ─────────────────────────────
        domain_score, domain_reason = get_domain_overlap_score(
            team_domains,
            mentor.get("domains") or [],
        )
        if domain_score is None:
            logger.debug(f"  ✗ REJECTED '{mentor_name}' — {domain_reason}")
            rejected_count["domain"] += 1
            rejected_count["total"] += 1
            continue

        # ── Rule-based score ──────────────────────────────────────────────
        rule_score, breakdown = compute_rule_based_score(
            team_data, mentor, domain_score_override=domain_score
        )

        # ── AI similarity score (optional) ────────────────────────────────
        ai_score = 0.0
        if mode == "hybrid":
            mentor_emb = mentor.get("embedding") or []
            if mentor_emb and len(mentor_emb) == len(team_embedding):
                ai_score = cosine_similarity(team_embedding, mentor_emb)
            else:
                if mentor_emb:
                    logger.warning(
                        f"  ⚠ '{mentor_name}' embedding dim mismatch "
                        f"({len(mentor_emb)} vs {len(team_embedding)}) — AI score = 0"
                    )

        # ── Final score ────────────────────────────────────────────────────
        hybrid = compute_hybrid_score(rule_score, ai_score) if mode == "hybrid" else rule_score

        logger.debug(
            f"  ✓ '{mentor_name}' | "
            f"domain={domain_score:.2f} skill={breakdown.get('skills',{}).get('score',0):.2f} "
            f"exp={breakdown.get('experience',{}).get('score',0):.2f} "
            f"avail={breakdown.get('availability',{}).get('score',0):.2f} "
            f"rule={rule_score:.3f} ai={ai_score:.3f} → hybrid={hybrid:.3f}"
        )

        candidates.append({
            "mentor_id":   str(mentor_id),
            "mentor_name": mentor_name,
            "scores": {
                "hybrid_score":       hybrid,
                "rule_based_score":   rule_score,
                "ai_similarity_score": round(ai_score, 4),
                "breakdown": {
                    "domain":       breakdown.get("domain", {}),
                    "skills":       breakdown.get("skills", {}),
                    "experience":   breakdown.get("experience", {}),
                    "availability": breakdown.get("availability", {}),
                },
            },
            "_mentor_obj": mentor,  # keep reference for workload update
        })

    # Sort by hybrid score descending
    candidates.sort(key=lambda x: x["scores"]["hybrid_score"], reverse=True)

    logger.info(
        f"  Ranking complete — {len(candidates)} eligible, "
        f"{rejected_count['domain']} domain-rejected, "
        f"{rejected_count['capacity']} at-capacity"
    )

    return candidates[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# EXPLANATION GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def _build_rule_explanation(breakdown: dict, mentor_name: str) -> str:
    """
    Build a concise rule-based fallback explanation from the score breakdown.
    Used when LLM call is disabled or fails.
    """
    parts = []

    dom = breakdown.get("domain", {})
    dom_reason = dom.get("reason", "")
    if "exact" in dom_reason.lower():
        parts.append("exact domain match")
    elif "related" in dom_reason.lower() or "cluster" in dom_reason.lower():
        parts.append("related domain expertise")

    skills = breakdown.get("skills", {})
    matched = skills.get("matched", [])
    if matched:
        parts.append(f"matching skills in {', '.join(matched[:4])}")

    exp = breakdown.get("experience", {})
    years = exp.get("years", 0)
    if years >= 10:
        parts.append(f"extensive {years}-year experience")
    elif years >= 5:
        parts.append(f"{years} years of experience")

    avail = breakdown.get("availability", {})
    curr = avail.get("current_teams", 0)
    mx = avail.get("max_teams", 3)
    if curr < mx:
        parts.append(f"available capacity ({curr}/{mx} teams)")

    if not parts:
        return (
            f"{mentor_name} was selected based on overall compatibility "
            "with the project requirements."
        )
    return (
        f"{mentor_name} was selected due to: "
        + "; ".join(parts) + "."
    )


async def generate_assignment_explanation(
    team_text: str,
    mentor_text: str,
    similarity_score: float = 0.0,
    rule_score: float = 0.0,
    breakdown: Optional[dict] = None,
) -> str:
    """
    Generate a human-readable assignment explanation via LLM (NVIDIA NIM / OpenAI).
    Falls back to a rule-based explanation if LLM call fails or no key is set.
    """
    # Build the rule-based fallback first (always available)
    mentor_name = ""
    for line in mentor_text.splitlines():
        if line.startswith("Mentor Name:"):
            mentor_name = line.split(":", 1)[1].strip()
            break
    fallback = _build_rule_explanation(breakdown or {}, mentor_name)

    api_key = settings.NVIDIA_API_KEY or settings.OPENAI_API_KEY
    if not api_key:
        return fallback

    try:
        c = _get_client()
        if c is None:
            return fallback
        model = settings.AI_MODEL if settings.NVIDIA_API_KEY else "gpt-3.5-turbo"

        # Include score breakdown for richer LLM context
        breakdown_txt = ""
        if breakdown:
            dom   = breakdown.get("domain",       {}).get("score", "?")
            skl   = breakdown.get("skills",       {}).get("score", "?")
            exp   = breakdown.get("experience",   {}).get("score", "?")
            avail = breakdown.get("availability", {}).get("score", "?")
            breakdown_txt = (
                f"\nScore breakdown — "
                f"domain={dom}, skills={skl}, experience={exp}, "
                f"availability={avail}, ai_similarity={similarity_score:.2f}"
            )

        prompt = (
            "You are an academic project-management assistant. "
            "In 2–3 concise sentences, explain why this mentor is a strong match "
            "for this project team. Be specific about domain, skills, and experience.\n\n"
            f"Project:\n{team_text}\n\n"
            f"Mentor:\n{mentor_text}"
            f"{breakdown_txt}"
        )
        response = await c.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=160,
            temperature=0.6,
        )
        content = ((response.choices or [None])[0] and response.choices[0].message.content) or ""
        content = content.strip() if isinstance(content, str) else ""
        return content or fallback
    except Exception as e:
        logger.error(f"LLM explanation failed: {e}")
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# STUBS — kept for backward compatibility
# ─────────────────────────────────────────────────────────────────────────────

async def score_proposal(
    title: str,
    description: str,
    document_url: Optional[str],
) -> float:
    """Stub — replace with real AI agent when ready."""
    return 75.0


async def recommend_mentors(
    project_title: str,
    project_description: str,
    available_mentors: list[dict],
) -> list[dict]:
    """Stub — replace with real AI agent when ready."""
    return available_mentors
