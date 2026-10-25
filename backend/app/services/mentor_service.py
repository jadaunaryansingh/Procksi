"""
mentor_service.py — Mentor management and domain-aware AI auto-assignment.

Auto-assignment pipeline (7 steps):
  1. Fetch unassigned teams (mentor_id IS NULL)
  2. Fetch available mentors (current_teams < max_teams)
  3. Build / cache mentor embeddings + data dicts
  4. For each team:
     a. Build rich team text → generate embedding
     b. rank_mentors_for_team() → strict domain filter → hybrid score → top-3
     c. Assign top-1 mentor (best hybrid score)
  5. Update team.mentor_id + mentor.current_teams in-memory
  6. Generate LLM explanation (optional)
  7. Single commit — rollback on any failure

Manual assign/reassign also adjusts current_teams on both mentors.
"""

import uuid
import logging
from typing import List, Optional, Dict, Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.mentor import Mentor
from app.models.team import Team
from app.models.panel_mentor import PanelMentor
from app.models.schedule import Schedule
from app.repositories.mentor_repo import mentor_repo
from app.repositories.team_repo import team_repo
from app.services.ai_service import (
    get_embedding,
    cosine_similarity,
    create_team_text,
    create_mentor_text,
    rank_mentors_for_team,
    generate_assignment_explanation,
    compute_rule_based_score,
    compute_hybrid_score,
    get_domain_overlap_score,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPER — build a serialisable mentor data dict from a Mentor ORM object
# ═══════════════════════════════════════════════════════════════════════════════

def _mentor_to_dict(mentor: Mentor, embedding: Optional[List[float]] = None) -> dict:
    """Convert a Mentor ORM row to a plain dict for use in scoring functions."""
    return {
        "id":               mentor.id,
        "name":             mentor.name,
        "expertise":        mentor.expertise,
        "domains":          mentor.domains or [],
        "skills":           mentor.skills or [],
        "experience_years": mentor.experience_years or 0,
        "current_teams":    mentor.current_teams or 0,
        "max_teams":        mentor.max_teams or 3,
        "embedding":        embedding or mentor.embedding or [],
    }


def _build_team_data(team: Team) -> dict:
    """Build the same rich team payload for recommendations and auto-assign."""
    team_data = {
        "project_title": team.project_title,
        "description": team.description,
        "domain": team.domain,
        "required_skills": team.required_skills,
    }

    if getattr(team, "proposals", None):
        latest = sorted(team.proposals, key=lambda p: p.id, reverse=True)[0]
        team_data["description"] = (
            f"{team.description or ''} "
            f"{latest.description or ''} "
            f"{getattr(latest, 'technology_stack', '') or ''}"
        ).strip()

    return team_data


# ═══════════════════════════════════════════════════════════════════════════════
class MentorService:
# ═══════════════════════════════════════════════════════════════════════════════

    @staticmethod
    async def recompute_mentor_loads(db: AsyncSession) -> dict:
        """
        Recompute Mentor.current_teams from the teams table.

        This fixes counter drift when teams are reassigned/unassigned outside the
        expected code paths.
        """
        # Count assigned teams grouped by mentor_id
        res = await db.execute(
            select(Team.mentor_id, func.count())
            .where(Team.mentor_id.is_not(None))
            .group_by(Team.mentor_id)
        )
        counts = {row[0]: int(row[1]) for row in res.all()}  # mentor_id -> count

        mentors_res = await db.execute(select(Mentor))
        mentors = list(mentors_res.scalars().all())

        updated = 0
        for m in mentors:
            new_val = counts.get(m.id, 0)
            if (m.current_teams or 0) != new_val:
                m.current_teams = new_val
                db.add(m)
                updated += 1

        await db.commit()
        return {"mentors": len(mentors), "updated": updated}

    # ─────────────────────────────────────────────────────────────────────────
    #  AUTO-ASSIGN  —  Domain-aware Hybrid Matching
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    async def auto_assign_mentors(
        cls,
        db: AsyncSession,
        *,
        generate_explanations: bool = True,
        mode: Literal["rule_only", "hybrid"] = "rule_only",
    ) -> dict:
        """
        AI-powered mentor auto-assignment using the domain-aware hybrid engine.

        Scoring:
          Rule-Based (70%): Domain(40%) + Skills(30%) + Experience(10%) + Availability(20%)
          AI Semantic (30%): Cosine similarity of NVIDIA NIM embeddings

        Hard constraints (before scoring):
          • Skip mentors at capacity (current_teams >= max_teams)
          • Skip mentors with NO domain overlap with the team

        Returns
        -------
        dict with keys: success, message, assignments, stats
        Each assignment includes scores.top_3_candidates for transparency.
        """
        try:
            logger.info("═══ Auto-assignment pipeline started ═══")

            # Pre-step: fix counter drift so capacity checks are accurate
            try:
                stats = await cls.recompute_mentor_loads(db)
                logger.info(
                    f"Recomputed mentor loads (updated {stats['updated']}/{stats['mentors']})"
                )
            except Exception as e:
                # Don't hard-fail auto-assign if recompute fails; proceed with stored counters.
                logger.warning(f"Mentor load recompute failed; continuing: {e}")

            # ── Step 1: Fetch unassigned teams ───────────────────────────
            logger.info("[1/7] Fetching unassigned teams …")
            teams_result = await db.execute(
                select(Team)
                .where(Team.mentor_id.is_(None))
                .options(selectinload(Team.proposals))
            )
            unassigned_teams = teams_result.scalars().all()
            logger.info(f"  → {len(unassigned_teams)} unassigned team(s)")

            if not unassigned_teams:
                return {
                    "success": True,
                    "message": "All teams already have mentors assigned.",
                    "assignments": [],
                    "stats": {"total_unassigned": 0, "assigned": 0, "skipped": 0},
                }

            # ── Step 2: Fetch all mentors (filter happens per-team in ranker) ──
            logger.info("[2/7] Fetching all mentors …")
            mentors_result = await db.execute(select(Mentor))
            all_mentors: List[Mentor] = list(mentors_result.scalars().all())
            logger.info(f"  → {len(all_mentors)} mentor(s) in total")

            available_mentors = [
                m for m in all_mentors if m.current_teams < m.max_teams
            ]
            logger.info(f"  → {len(available_mentors)} with remaining capacity")

            if not available_mentors:
                return {
                    "success": False,
                    "message": "No mentors available with remaining capacity.",
                    "assignments": [],
                    "stats": {
                        "total_unassigned": len(unassigned_teams),
                        "assigned": 0,
                        "skipped": len(unassigned_teams),
                    },
                }

            # ── Step 3: Build mentor data cache (+ embeddings only for hybrid) ──
            logger.info(f"[3/7] Preparing mentor data cache (mode={mode}) …")
            mentor_data_cache: Dict[uuid.UUID, dict] = {}
            mentor_orm_cache:  Dict[uuid.UUID, Mentor] = {}

            for mentor in available_mentors:
                mentor_orm_cache[mentor.id] = mentor
                # Generate/reuse embedding only in hybrid mode
                embedding = []
                if mode == "hybrid":
                    if mentor.embedding:
                        embedding = mentor.embedding
                        logger.debug(f"  ✓ Reused stored embedding for '{mentor.name}'")
                    else:
                        mentor_text = create_mentor_text(_mentor_to_dict(mentor))
                        embedding = await get_embedding(mentor_text)
                        logger.debug(f"  ✓ Generated embedding for '{mentor.name}'")

                mentor_data_cache[mentor.id] = _mentor_to_dict(mentor, embedding)

            mentor_data_list = list(mentor_data_cache.values())

            # ── Steps 4–6: Matching loop ─────────────────────────────────
            logger.info(f"[4-6/7] Running matching engine in {mode} mode …")
            assignments: List[dict] = []
            skipped_teams: List[str] = []
            explanation_jobs: List[dict] = []

            for idx, team in enumerate(unassigned_teams, 1):
                log_pfx = f"  [{idx}/{len(unassigned_teams)}] '{team.name}'"

                # Abort if no mentors remain with capacity
                active_mentors = [
                    m for m in mentor_data_list
                    if m["current_teams"] < m["max_teams"]
                ]
                if not active_mentors:
                    logger.warning(f"{log_pfx} — no more available mentors, stopping")
                    skipped_teams.append(str(team.id))
                    continue

                # Build team representation
                team_data = _build_team_data(team)
                team_text = create_team_text(team_data)

                # Generate team embedding only in hybrid mode
                team_embedding = []
                if mode == "hybrid":
                    try:
                        team_embedding = await get_embedding(team_text)
                    except Exception as e:
                        logger.error(f"{log_pfx} — embedding failed: {e}, skipping")
                        skipped_teams.append(str(team.id))
                        continue

                logger.info(
                    f"{log_pfx} | domains={team.domain} | "
                    f"skills={team.required_skills}"
                )

                # Rank mentors (domain filter + hybrid scoring → top-3)
                top_candidates = rank_mentors_for_team(
                    team_data,
                    team_embedding,
                    active_mentors,
                    top_k=3,
                    mode=mode,
                )

                if not top_candidates:
                    logger.warning(
                        f"{log_pfx} — NO eligible mentor after domain filter + scoring"
                    )
                    skipped_teams.append(str(team.id))
                    continue

                # Best candidate is top_candidates[0]
                best = top_candidates[0]
                best_mentor_id   = uuid.UUID(best["mentor_id"])
                best_mentor_orm  = mentor_orm_cache[best_mentor_id]
                best_hybrid      = best["scores"]["hybrid_score"]
                best_rule        = best["scores"]["rule_based_score"]
                best_ai          = best["scores"]["ai_similarity_score"]
                best_breakdown   = best["scores"]["breakdown"]

                logger.info(
                    f"{log_pfx} → assigned '{best['mentor_name']}' "
                    f"(hybrid={best_hybrid:.3f}, "
                    f"rule={best_rule:.3f}, ai={best_ai:.3f})"
                )

                # ── Step 5: DB mutations (batched, committed once at end)
                team.mentor_id = best_mentor_id
                best_mentor_orm.current_teams += 1
                db.add(team)
                db.add(best_mentor_orm)

                # Update in-memory cache so subsequent teams see accurate workload
                mentor_data_cache[best_mentor_id]["current_teams"] = (
                    best_mentor_orm.current_teams
                )

                # Top-3 for transparency (strip internal _mentor_obj reference)
                top3_summary = [
                    {
                        "rank":        rank + 1,
                        "mentor_id":   c["mentor_id"],
                        "mentor_name": c["mentor_name"],
                        "scores":      c["scores"],
                    }
                    for rank, c in enumerate(top_candidates)
                ]

                assignments.append({
                    "team_id":       str(team.id),
                    "team_name":     team.name,
                    "project_title": team.project_title,
                    "mentor_id":     str(best_mentor_id),
                    "mentor_name":   best["mentor_name"],
                    "scores": {
                        "hybrid_score":        best_hybrid,
                        "rule_based_score":    best_rule,
                        "ai_similarity_score": best_ai,
                        "breakdown":           best_breakdown,
                    },
                    "top_3_candidates": top3_summary,
                    "explanation":     "",
                })

                if generate_explanations:
                    explanation_jobs.append({
                        "assignment_index": len(assignments) - 1,
                        "log_prefix": log_pfx,
                        "team_text": team_text,
                        "mentor_text": create_mentor_text(mentor_data_cache[best_mentor_id]),
                        "hybrid_score": best_hybrid,
                        "rule_score": best_rule,
                        "ai_score": best_ai,
                        "breakdown": best_breakdown,
                    })

                # Log if mentor reached capacity
                if best_mentor_orm.current_teams >= best_mentor_orm.max_teams:
                    logger.info(
                        f"  ⚑ '{best['mentor_name']}' reached max capacity "
                        f"— will be excluded from future iterations"
                    )

            # ── Step 7: Commit ────────────────────────────────────────────
            logger.info(f"[7/7] Committing {len(assignments)} assignment(s) …")
            await db.commit()

            if generate_explanations and explanation_jobs:
                logger.info("Generating assignment explanations after commit …")
                for job in explanation_jobs:
                    try:
                        explanation = await generate_assignment_explanation(
                            job["team_text"],
                            job["mentor_text"],
                            similarity_score=job["ai_score"],
                            rule_score=job["rule_score"],
                            breakdown=job["breakdown"],
                        )
                    except Exception as e:
                        logger.warning(f"{job['log_prefix']} — explanation error: {e}")
                        explanation = (
                            f"Matched with hybrid score {job['hybrid_score']:.2f} "
                            f"(rule={job['rule_score']:.2f}, ai={job['ai_score']:.2f})."
                        )

                    assignments[job["assignment_index"]]["explanation"] = explanation

            logger.info("═══ Auto-assignment pipeline completed successfully ═══")

            return {
                "success": True,
                "message": f"Successfully assigned {len(assignments)} mentor(s) to teams.",
                "assignments": assignments,
                "stats": {
                    "total_unassigned": len(unassigned_teams),
                    "assigned":         len(assignments),
                    "skipped":          len(skipped_teams),
                    "skipped_teams":    skipped_teams,
                },
            }

        except Exception as e:
            logger.error(
                f"Auto-assignment pipeline failed: {type(e).__name__}: {e}",
                exc_info=True,
            )
            await db.rollback()
            return {
                "success": False,
                "message": f"Auto-assignment failed: {str(e)}",
                "assignments": [],
                "stats": {"total_unassigned": 0, "assigned": 0, "skipped": 0},
            }

    # ─────────────────────────────────────────────────────────────────────────
    #  MANUAL ASSIGN / REASSIGN
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def check_mentor_conflict(
        db: AsyncSession, mentor_id: uuid.UUID, team_id: uuid.UUID
    ) -> Team:
        """
        Verify the mentor is not a panel evaluator for this team.
        Pre-loads team.semester to avoid an extra round-trip.
        """
        query = (
            select(Team)
            .where(Team.id == team_id)
            .options(selectinload(Team.semester))
        )
        result = await db.execute(query)
        team = result.scalar_one_or_none()

        if not team:
            raise ValueError("Team not found")

        schedules_result = await db.execute(
            select(Schedule.panel_id).where(Schedule.team_id == team_id)
        )
        panel_ids = schedules_result.scalars().all()

        if panel_ids:
            conflict_result = await db.execute(
                select(PanelMentor.id)
                .where(
                    PanelMentor.mentor_id == mentor_id,
                    PanelMentor.panel_id.in_(panel_ids),
                )
                .limit(1)
            )
            if conflict_result.scalar_one_or_none():
                raise ValueError(
                    "Mentor is already a panel evaluator for this team "
                    "and cannot also be the guiding mentor"
                )

        return team

    @classmethod
    async def assign_mentor(
        cls, db: AsyncSession, mentor_id: uuid.UUID, team_id: uuid.UUID
    ) -> Team:
        """
        Manually assign (or reassign) a mentor to a team.

        On reassignment:
          • Decrements previous mentor's current_teams (clamped to 0).
          • Increments new mentor's current_teams.
          • All mutations committed in one transaction.
        """
        # Fetch new mentor (verify existence + load for mutation)
        new_mentor_result = await db.execute(
            select(Mentor).where(Mentor.id == mentor_id)
        )
        new_mentor = new_mentor_result.scalar_one_or_none()
        if not new_mentor:
            raise ValueError("Mentor not found")

        # Capacity check for new mentor
        if new_mentor.current_teams >= new_mentor.max_teams:
            raise ValueError(
                f"Mentor '{new_mentor.name}' has reached maximum team capacity "
                f"({new_mentor.current_teams}/{new_mentor.max_teams})"
            )

        # Check team, semester, and panel conflict
        team = await cls.check_mentor_conflict(db, mentor_id, team_id)

        if team.mentor_id == mentor_id:
            raise ValueError(
                "This mentor is already assigned as the guiding mentor for this team"
            )
        if team.semester and team.semester.is_locked:
            raise ValueError("Semester is locked; mentor assignment not permitted")

        # Decrement previous mentor's workload
        previous_mentor_id = team.mentor_id
        if previous_mentor_id and previous_mentor_id != mentor_id:
            prev_result = await db.execute(
                select(Mentor).where(Mentor.id == previous_mentor_id)
            )
            prev_mentor = prev_result.scalar_one_or_none()
            if prev_mentor:
                prev_mentor.current_teams = max(0, prev_mentor.current_teams - 1)
                db.add(prev_mentor)
                logger.info(
                    f"Decremented current_teams for previous mentor "
                    f"'{prev_mentor.name}' → {prev_mentor.current_teams}"
                )

        # Increment new mentor's workload
        new_mentor.current_teams += 1
        db.add(new_mentor)
        logger.info(
            f"Incremented current_teams for new mentor "
            f"'{new_mentor.name}' → {new_mentor.current_teams}"
        )

        return await team_repo.update(db, db_obj=team, obj_in={"mentor_id": mentor_id})

    # ─────────────────────────────────────────────────────────────────────────
    #  CRUD HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_mentors(
        db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> List[Mentor]:
        return await mentor_repo.get_multi(db, skip=skip, limit=limit)

    @staticmethod
    async def count_mentors(db: AsyncSession) -> int:
        return await mentor_repo.count(db)

    # ─────────────────────────────────────────────────────────────────────────
    #  RECOMMENDATIONS  (domain-aware, top-5)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_recommendations(
        db: AsyncSession, team_id: uuid.UUID
    ) -> List[dict]:
        """
        Recommend up to 5 mentors for a specific team using the domain-aware
        hybrid engine.  Teams with no proposal yet fall back to rule-only scoring.
        """
        # Load team + its proposals in one query
        query = (
            select(Team)
            .where(Team.id == team_id)
            .options(selectinload(Team.proposals))
        )
        result = await db.execute(query)
        team = result.scalar_one_or_none()
        if not team:
            raise ValueError("Team not found")

        team_data = _build_team_data(team)

        # Generate team embedding
        team_text = create_team_text(team_data)
        team_embedding = await get_embedding(team_text)

        # Fetch all mentors
        mentors_result = await db.execute(select(Mentor))
        all_mentors = mentors_result.scalars().all()

        # Build mentor data dicts (with embeddings from DB if available)
        mentor_dicts = [_mentor_to_dict(m) for m in all_mentors]

        # Use domain-aware ranker (top-5 for recommendations)
        top_candidates = rank_mentors_for_team(
            team_data, team_embedding, mentor_dicts, top_k=5
        )

        return [
            {
                "id":           c["mentor_id"],
                "name":         c["mentor_name"],
                "hybrid_score": c["scores"]["hybrid_score"],
                "rule_score":   c["scores"]["rule_based_score"],
                "ai_score":     c["scores"]["ai_similarity_score"],
                "breakdown":    c["scores"]["breakdown"],
            }
            for c in top_candidates
        ]
