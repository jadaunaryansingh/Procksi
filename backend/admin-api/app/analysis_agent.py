"""Analysis dashboard data provider.

Serves the RAW (lean) rows the Analysis page needs. Filtering (semester / year /
branch) and aggregation happen client-side, reusing the admin app's shared
``filterRows`` logic, so the Analysis numbers always agree with the rest of the
app under the same global filter, and changing the filter re-aggregates instantly
without another round-trip.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException


def _project(rows: list[dict], fields: list[str]) -> list[dict]:
    return [{f: r.get(f) for f in fields} for r in rows]


def build_analysis_router(service_client) -> APIRouter:
    router = APIRouter(prefix="/api/admin/analysis", tags=["Analysis"])

    @router.get("/data")
    def data() -> dict[str, Any]:
        """Lean rows for every dataset the dashboard charts.

        Scoped to ACTIVE semesters, matching how the rest of the admin app fetches
        (``/api/data`` auto-scopes to active semesters unless a semester_id is given).
        This keeps the Analysis numbers consistent with every other page. The client
        then narrows further (year / branch / a specific active semester) via the
        shared filterRows. Mentors are global (not semester-scoped).
        """
        try:
            active_res = service_client.table("semester_config").select("id").eq("is_active", True).execute()
            active_ids = [s["id"] for s in active_res.data or []]

            def _scoped(table: str, fields: list[str]) -> list[dict]:
                q = service_client.table(table).select("*")
                if active_ids:
                    q = q.in_("semester_id", active_ids)
                rows = q.execute().data or [] if active_ids else []
                return _project(rows, fields)

            teams = _scoped("teams_validation",
                            ["id", "semester_id", "branch", "section", "memberCount", "validationStatus",
                             "mentor", "domain", "title", "leader", "year", "academic_level", "members"])
            results = _scoped("results",
                              ["team", "title", "domain", "branch", "mentor", "totalScore",
                               "proposalMarks", "midMarks", "finalMarks", "semester_id"])
            proposals = _scoped("proposals", ["status", "aiScore", "ai_score", "semester_id", "teamId"])
            absents = _scoped("absent_students", ["reason", "status", "semester_id", "team", "name", "roll"])
            students = _scoped("students", ["id", "name", "branch", "section", "semester_id", "year", "academic_level"])
            mentors = _project(service_client.table("mentors").select("*").execute().data or [],
                               ["name", "max_teams", "maxLoad"])
            semesters = service_client.table("semester_config").select("*").execute().data or []

            # Panel evaluations, panels and GitHub agent scores are not reliably
            # semester-scoped (evaluations may carry a null semester_id, panels /
            # github_agent_analysis have no semester_id column), so fetch them
            # whole and let the client join by team. Guarded individually so a
            # missing table never breaks the whole dashboard.
            def _all(table: str, fields: list[str]) -> list[dict]:
                try:
                    return _project(service_client.table(table).select("*").execute().data or [], fields)
                except Exception:
                    return []

            evaluations = _all("evaluations",
                               ["id", "panel_id", "team_id", "scores_json", "remarks", "semester_id"])
            panels = _all("panels", ["id", "name", "members", "teams"])
            github = _all("github_agent_analysis",
                          ["team_id", "quality_score", "security_score", "originality_score",
                           "architecture_score", "documentation_score", "commit_count_30d",
                           "repository_url", "last_commit_at"])
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return {"data": {
            "teams": teams,
            "results": results,
            "proposals": proposals,
            "absents": absents,
            "students": students,
            "mentors": mentors,
            "semesters": semesters,
            "evaluations": evaluations,
            "panels": panels,
            "github": github,
        }}

    return router
