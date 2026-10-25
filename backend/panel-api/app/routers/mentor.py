"""
Mentor-specific routes.

Mentors share the same `panel` role and use their `panel_id` to scope data,
but these endpoints provide a mentor-facing view with richer personal info.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.db_helpers import get_project_title, get_meet_link_map, get_active_team_ids
from app.deps import get_current_user, require_panel_access
from app.supabase_client import get_supabase_service
from app.slot_service import refresh_slot_statuses

router = APIRouter(prefix="/mentor", tags=["mentor"])


class MentorProfileResponse(BaseModel):
    panel_id: str
    mentor_name: str | None = None
    email: str
    assigned_round: str | None = None
    total_teams: int = 0
    evaluated_count: int = 0
    pending_count: int = 0


class MentorTeamRow(BaseModel):
    team_id: int
    team_name: str | None = None
    project_title: str | None = None
    slot_label: str | None = None
    venue: str | None = None
    meet_link: str | None = None
    status: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    github_url: str | None = None
    commit_count_30d: int | None = None
    last_commit_at: datetime | None = None
    is_evaluated: bool = False
    receipt_id: str | None = None
    semester_id: str | None = None


@router.get("/{panel_id}/profile", response_model=MentorProfileResponse)
def mentor_profile(
    panel_id: str,
    response: Response,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Return the mentor's profile info including their name and summary stats."""
    require_panel_access(panel_id, user)

    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    def _fetch_profile():
        refresh_slot_statuses(client, panel_id, full_sync=False)

        # Mentor display name from panels table
        res_panel = client.table("panels").select("name, description").eq("id", panel_id).execute()
        mentor_name = None
        assigned_round = None
        if res_panel.data:
            mentor_name = res_panel.data[0].get("name")
            assigned_round = res_panel.data[0].get("description")

        # Stats from slots
        res_slots = client.table("slots").select("team_id, status").eq("panel_id", panel_id).execute()
        active_team_ids = get_active_team_ids(client)
        slots = [s for s in (res_slots.data or []) if s["team_id"] in active_team_ids]

        total = len(slots)
        evaluated = sum(1 for s in slots if s["status"].lower() == "submitted")
        pending = sum(1 for s in slots if s["status"].lower() not in ("submitted", "missed"))

        return {
            "panel_id": panel_id,
            "mentor_name": mentor_name,
            "email": user.get("email", ""),
            "assigned_round": assigned_round,
            "total_teams": total,
            "evaluated_count": evaluated,
            "pending_count": pending,
        }

    from app.cache import get_cached
    cached_data = get_cached(f"mentor_profile_response:{panel_id}", 10.0, _fetch_profile)
    # Update email dynamically from active user
    cached_data["email"] = user.get("email", "")
    response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=60"
    return MentorProfileResponse(**cached_data)


@router.get("/{panel_id}/teams", response_model=list[MentorTeamRow])
def mentor_teams(
    panel_id: str,
    response: Response,
    user: Annotated[dict, Depends(get_current_user)],
):
    """
    Return all teams assigned to this mentor's panel with full context:
    slot timing, evaluation status, GitHub metrics, and project info.
    """
    require_panel_access(panel_id, user)

    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    def _fetch_mentor_teams():
        refresh_slot_statuses(client, panel_id, full_sync=False)

        # Fetch slots for this panel
        res_slots = client.table("slots").select("*").eq("panel_id", panel_id).order("window_start").execute()
        active_team_ids = get_active_team_ids(client)
        slots = [s for s in (res_slots.data or []) if s["team_id"] in active_team_ids]

        if not slots:
            return []

        team_ids = [s["team_id"] for s in slots]

        # Bulk fetch teams, projects, evaluations, github — scoped to this panel's teams only
        teams_map = {}
        projects_map = {}
        if team_ids:
            res_teams = client.table("teams").select("*").in_("id", team_ids).execute()
            teams_map = {t["id"]: t for t in (res_teams.data or [])}
            res_projects = client.table("projects").select("team_id, title").in_("team_id", team_ids).execute()
            projects_map = {p["team_id"]: p["title"] for p in (res_projects.data or [])}

            # team_ids are panel-api's local surrogate keys (public.teams.id), not
            # the shared teams_validation.team_number that github_data.team_id
            # actually stores — team_number repeats across semesters, so matching on
            # it here could pull another team's repo into this map. Resolve each
            # team's canonical team_uid (teams_validation.uid — the designated
            # canonical key for all team-scoped data) via public.teams.name (kept
            # equal to teams_validation.id by panel-api's own sync) and match on
            # that instead.
            team_ref_by_local_id = {tid: t.get("name") for tid, t in teams_map.items() if t.get("name")}
            uid_by_ref = {}
            if team_ref_by_local_id:
                tv_rows = (client.table("teams_validation").select("id,uid")
                           .in_("id", list(team_ref_by_local_id.values())).execute().data) or []
                uid_by_ref = {r["id"]: r["uid"] for r in tv_rows if r.get("uid")}
            local_id_by_uid = {uid_by_ref[ref]: tid for tid, ref in team_ref_by_local_id.items() if ref in uid_by_ref}
            resolved_uids = list(local_id_by_uid.keys())
            unresolved_ids = [tid for tid in team_ids if uid_by_ref.get(team_ref_by_local_id.get(tid)) is None]

            gh_map = {}
            if resolved_uids:
                res_gh_uid = client.table("github_data").select("team_id, team_uid, repository_url, commit_count_30d, last_commit_at").in_("team_uid", resolved_uids).execute()
                for g in (res_gh_uid.data or []):
                    local_id = local_id_by_uid.get(g.get("team_uid"))
                    if local_id is not None:
                        gh_map[local_id] = g
            if unresolved_ids:
                res_gh_legacy = client.table("github_data").select("team_id, repository_url, commit_count_30d, last_commit_at").in_("team_id", unresolved_ids).execute()
                for g in (res_gh_legacy.data or []):
                    gh_map.setdefault(g["team_id"], g)
        else:
            gh_map = {}

        res_evals = client.table("evaluations").select("team_id, receipt_id").eq("panel_id", panel_id).execute()
        evals_map = {e["team_id"]: e["receipt_id"] for e in (res_evals.data or [])}

        # Query presentation evaluations for receipt mapping
        try:
            from app.db_helpers import to_numeric_id
            res_pevals = client.table("presentation_evaluations")\
                .select("id, team_id, cycle_id")\
                .eq("evaluator_id", panel_id)\
                .execute()
            for pe in (res_pevals.data or []):
                num_id = to_numeric_id(pe["team_id"])
                if num_id:
                    rec_id = f"REC-{pe['id'].split('-')[0].upper()}"
                    evals_map[(num_id, pe.get("cycle_id"))] = rec_id
                    if num_id not in evals_map:
                        evals_map[num_id] = rec_id
        except Exception:
            pass

        meet_link_map = get_meet_link_map(client, panel_id)

        now = datetime.now(timezone.utc)
        out = []

        for slot in slots:
            tid = slot["team_id"]
            team = teams_map.get(tid)
            gh = gh_map.get(tid)

            ws_val = None
            we_val = None
            if slot.get("window_start"):
                try:
                    ws_val = slot["window_start"]
                except Exception:
                    pass
            if slot.get("window_end"):
                try:
                    we_val = slot["window_end"]
                except Exception:
                    pass

            last_commit = None
            if gh and gh.get("last_commit_at"):
                try:
                    last_commit = gh["last_commit_at"]
                except Exception:
                    pass

            slot_cycle_id = slot.get("cycle_id")
            is_evaluated = slot.get("status", "").lower() == "submitted"
            receipt_id = None
            if is_evaluated:
                receipt_id = evals_map.get((tid, slot_cycle_id)) or evals_map.get(tid)

            out.append({
                "team_id": tid,
                "team_name": team["name"] if team else None,
                "project_title": projects_map.get(tid),
                "slot_label": slot.get("slot_label"),
                "venue": slot.get("venue"),
                "meet_link": meet_link_map.get(f"{tid}_{slot.get('cycle_id')}") or meet_link_map.get(tid),
                "status": slot.get("status"),
                "window_start": ws_val,
                "window_end": we_val,
                "github_url": gh["repository_url"] if gh else None,
                "commit_count_30d": gh["commit_count_30d"] if gh else None,
                "last_commit_at": last_commit,
                "is_evaluated": is_evaluated,
                "receipt_id": receipt_id,
                "semester_id": str(team.get("semester_id")) if team and team.get("semester_id") else None,
            })
        return out

    from app.cache import get_cached
    cached_data = get_cached(f"mentor_teams_response:{panel_id}", 10.0, _fetch_mentor_teams)
    response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=60"
    return [MentorTeamRow(**r) for r in cached_data]
