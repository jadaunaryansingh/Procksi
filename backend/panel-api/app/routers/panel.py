import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.config import settings
from app.db_helpers import get_project_title, get_batch_project_titles, from_numeric_id, to_numeric_id, get_meet_link_map, get_active_team_ids, resolve_team_string_id
from app.deps import get_current_user, require_panel_access
from app.supabase_client import get_supabase_service
from app.schemas import AlertRow, GitHubDataRow, MissedRow, PanelDashboardResponse, TeamCatalogRow, TeamSlotRow
from app.slot_service import refresh_slot_statuses

router = APIRouter(prefix="/panel", tags=["panel"])


@router.get("/{panel_id}/dashboard", response_model=PanelDashboardResponse)
def panel_dashboard(
    panel_id: str,
    response: Response,
    user: Annotated[dict, Depends(get_current_user)],
    force_sync: bool = False,
):
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
        
    if force_sync:
        from app.cache import invalidate
        invalidate(f"panel_dashboard_response:{panel_id}")
        invalidate(f"panel_teams_response:{panel_id}")
        invalidate(f"panel_status_data:{panel_id}")
        invalidate(f"meet_link_map:{panel_id}")
        invalidate(f"mentor_teams_response:{panel_id}")


    def _fetch_dashboard():
        refresh_slot_statuses(client, panel_id, full_sync=force_sync, force_sync=force_sync)

        # Use the panel's assigned round_name if available, fall back to config default
        res_panel = client.table("panels").select("description").eq("id", panel_id).execute()
        round_name = None
        if res_panel.data:
            round_name = res_panel.data[0]["description"]
        if not round_name:
            round_name = settings.assigned_round

        res_slots = client.table("slots").select("*").eq("panel_id", panel_id).order("window_start").execute()
        active_team_ids = get_active_team_ids(client)
        slots = [s for s in res_slots.data if s["team_id"] in active_team_ids]

        team_ids = [s["team_id"] for s in slots]
        teams = {}
        if team_ids:
            res_teams = client.table("teams").select("*").in_("id", team_ids).execute()
            teams = {t["id"]: t for t in (res_teams.data or [])}

        total = len(slots)
        completed = sum(1 for s in slots if s["status"].lower() == "submitted")
        missed = sum(1 for s in slots if s["status"].lower() == "missed")
        pending = sum(
            1
            for s in slots
            if s["status"].lower() not in ("submitted", "missed")
        )

        active = next((s for s in slots if s["status"].lower() == "active"), None)
        active_name = teams[active["team_id"]]["name"] if active and active["team_id"] in teams else None

        meet_link_map = get_meet_link_map(client, panel_id)

        upcoming = [s for s in slots if s["status"].lower() == "upcoming"]
        next_slot = min(upcoming, key=lambda s: s["window_start"]) if upcoming else None
        next_up = None
        if next_slot and next_slot["team_id"] in teams:
            next_up = {
                "team_id": next_slot["team_id"],
                "team_name": teams[next_slot["team_id"]]["name"],
                "slot": next_slot["slot_label"],
                "meet_link": meet_link_map.get(f"{next_slot['team_id']}_{next_slot.get('cycle_id')}") or meet_link_map.get(next_slot["team_id"]),
            }

        # Batch fetch project titles in ONE query instead of one per team
        all_team_ids = [s["team_id"] for s in slots]
        project_titles_map = get_batch_project_titles(client, all_team_ids)

        active_detail = None
        if active and active["team_id"] in teams:
            t = teams[active["team_id"]]
            active_detail = {
                "team_id": active["team_id"],
                "team_name": t["name"],
                "project_title": project_titles_map.get(active["team_id"]),
                "time_range": active["slot_label"],
                "venue": active["venue"],
                "meet_link": meet_link_map.get(f"{active['team_id']}_{active.get('cycle_id')}") or meet_link_map.get(active["team_id"]),
            }

        now = datetime.now(timezone.utc)
        return {
            "assigned_round": round_name,
            "total_teams": total,
            "active_slot": active_name,
            "system_time": now.strftime("%I:%M:%S %p").lstrip("0"),
            "evaluated_count": completed,
            "pending_count": pending,
            "completed_count": completed,
            "progress_fraction": (completed / total) if total else 0.0,
            "active_slot_detail": active_detail,
            "next_up": next_up,
        }

    from app.cache import get_cached
    cached_data = get_cached(f"panel_dashboard_response:{panel_id}", 10.0, _fetch_dashboard)
    response.headers["Cache-Control"] = "private, max-age=10, stale-while-revalidate=30"
    return PanelDashboardResponse(**cached_data)


@router.get("/{panel_id}/teams", response_model=list[TeamSlotRow])
def panel_teams(
    panel_id: str,
    response: Response,
    user: Annotated[dict, Depends(get_current_user)],
    force_sync: bool = False,
):
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
        
    if force_sync:
        from app.cache import invalidate
        invalidate(f"panel_teams_response:{panel_id}")
        invalidate(f"panel_dashboard_response:{panel_id}")
        invalidate(f"panel_status_data:{panel_id}")
        invalidate(f"meet_link_map:{panel_id}")
        invalidate(f"mentor_teams_response:{panel_id}")


    def _fetch_teams():
        refresh_slot_statuses(client, panel_id, force_sync=force_sync)
        
        res_slots = client.table("slots").select("*").eq("panel_id", panel_id).order("window_start").execute()
        active_team_ids = get_active_team_ids(client)
        # Show all slots (including Missed) so panel can still evaluate — filter only by active semester
        slots = [s for s in res_slots.data if s["team_id"] in active_team_ids]

        team_ids = [s["team_id"] for s in slots]
        teams = {}
        projects = {}
        if team_ids:
            res_teams = client.table("teams").select("*").in_("id", team_ids).execute()
            teams = {t["id"]: t for t in (res_teams.data or [])}
            res_proj = client.table("projects").select("team_id, title").in_("team_id", team_ids).execute()
            projects = {p["team_id"]: p["title"] for p in (res_proj.data or [])}

        meet_link_map = get_meet_link_map(client, panel_id)
        
        out = []
        import re
        for s in slots:
            t_name = teams[s["team_id"]]["name"] if s["team_id"] in teams else None
            sem_id = None
            if t_name:
                m = re.match(r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", t_name)
                if m:
                    sem_id = m.group(1)
            out.append({
                "team_id": s["team_id"],
                "slot": s["slot_label"],
                "status": s["status"],
                "team_name": t_name,
                "project_title": projects.get(s["team_id"]),
                "venue": s["venue"],
                "meet_link": meet_link_map.get(f"{s['team_id']}_{s.get('cycle_id')}") or meet_link_map.get(s["team_id"]),
                "semester_id": sem_id,
            })
        return out

    from app.cache import get_cached
    cached_data = get_cached(f"panel_teams_response:{panel_id}", 10.0, _fetch_teams)
    response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=60"
    return [TeamSlotRow(**r) for r in cached_data]


@router.get("/{panel_id}/teams/{team_id}/github", response_model=GitHubDataRow)
def team_github_data(
    panel_id: str,
    team_id: int,
    user: Annotated[dict, Depends(get_current_user)],
):
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
        
    res_slot = client.table("slots").select("id").eq("panel_id", panel_id).eq("team_id", team_id).execute()
    if not res_slot.data:
        raise HTTPException(status_code=404, detail="Team not in this panel schedule")

    # team_id here is panel-api's own local surrogate key (public.teams.id), not
    # the shared teams_validation.team_number — and github_data/github_agent_analysis
    # are the SAME tables the admin/mentor/student portals write to, keyed there by
    # team_number, which is only unique per semester (two different semesters can
    # both have a "Team 5"). Resolve the canonical team_uid (teams_validation.uid —
    # the designated canonical key for all team-scoped data) via public.teams.name,
    # which panel-api's own sync keeps equal to teams_validation.id, so this lookup
    # can't return a different semester's team's repo/report.
    team_ref = None
    team_uid = None
    try:
        team_row = client.table("teams").select("name").eq("id", team_id).execute()
        candidate = team_row.data[0].get("name") if team_row.data else None
        if candidate:
            tv_check = client.table("teams_validation").select("id,uid").eq("id", candidate).execute()
            if tv_check.data:
                team_ref = candidate
                team_uid = tv_check.data[0].get("uid")
    except Exception:
        pass
    if team_uid:
        gh_field, gh_val = "team_uid", team_uid
    elif team_ref:
        gh_field, gh_val = "team_ref", team_ref
    else:
        gh_field, gh_val = "team_id", team_id

    # Try querying the new github_agent_analysis table first
    res_gh = client.table("github_agent_analysis").select("*").eq(gh_field, gh_val).execute()
    row = res_gh.data[0] if res_gh.data else None

    # Always fetch authoritative repository URL from github_data
    auth_repo = None
    res_auth = client.table("github_data").select("repository_url").eq(gh_field, gh_val).execute()
    if res_auth.data and res_auth.data[0].get("repository_url"):
        auth_repo = res_auth.data[0]["repository_url"].strip()
    
    if row:
        last_commit = None
        if row.get("last_commit_at"):
            last_commit = datetime.fromisoformat(row["last_commit_at"].replace("Z", "+00:00"))
        
        # Reconstruct raw_json format
        import json
        raw_json_payload = {
            "analysis_job_id": row.get("analysis_job_id"),
            "analysis_status": row.get("analysis_status"),
            "results": row.get("raw_report") or {
                "scores": {
                    "quality": row.get("quality_score") or 0,
                    "security": row.get("security_score") or 0,
                    "originality": row.get("originality_score") or 0,
                    "architecture": row.get("architecture_score") or 0,
                    "documentation": row.get("documentation_score") or 0
                },
                "tech_stack": row.get("tech_stack")
            }
        }
        
        return GitHubDataRow(
            team_id=team_id,
            repository_url=auth_repo or row.get("repository_url"),
            default_branch="main",
            open_pull_requests=0,
            commit_count_30d=row.get("commit_count_30d") or 0,
            last_commit_at=last_commit,
            raw_json=json.dumps(raw_json_payload),
        )

    # Fallback to the old github_data table
    res_gh = client.table("github_data").select("*").eq(gh_field, gh_val).execute()
    row = res_gh.data[0] if res_gh.data else None
    
    if not row:
        return GitHubDataRow(team_id=team_id)
        
    last_commit = None
    if row["last_commit_at"]:
        last_commit = datetime.fromisoformat(row["last_commit_at"].replace("Z", "+00:00"))
        
    return GitHubDataRow(
        team_id=team_id,
        repository_url=row["repository_url"],
        default_branch=row["default_branch"],
        open_pull_requests=row["open_pull_requests"],
        commit_count_30d=row["commit_count_30d"],
        last_commit_at=last_commit,
        raw_json=row.get("raw_json"),
    )


@router.get("/{panel_id}/alerts", response_model=list[AlertRow])
def panel_alerts(
    panel_id: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Active notifications for this panel."""
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
        
    res = client.table("alerts").select("*")\
        .eq("panel_id", panel_id)\
        .is_("acknowledged_at", "null")\
        .order("created_at", desc=True)\
        .execute()
        
    return [
        AlertRow(
            id=r["id"],
            alert_type=r["alert_type"],
            title=r["title"],
            body=r["body"],
            team_id=r["team_id"],
            created_at=datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")),
            acknowledged_at=None,
        )
        for r in res.data
    ]


@router.get("/{panel_id}/missed", response_model=list[MissedRow])
def panel_missed(
    panel_id: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
        
    refresh_slot_statuses(client, panel_id)
    
    res_slots = client.table("slots").select("*")\
        .eq("panel_id", panel_id)\
        .in_("status", ["Missed", "missed"])\
        .order("window_start")\
        .execute()

    active_team_ids = get_active_team_ids(client)
    missed_slots = [s for s in (res_slots.data or []) if s["team_id"] in active_team_ids]
    missed_team_ids = [s["team_id"] for s in missed_slots]

    # Scoped fetch: only get teams involved in missed slots (not ALL teams)
    teams: dict[int, dict] = {}
    if missed_team_ids:
        res_teams = client.table("teams").select("id, name").in_("id", missed_team_ids).execute()
        teams = {t["id"]: t for t in (res_teams.data or [])}
    
    import re
    out = []
    for s in missed_slots:
        t_name = teams[s["team_id"]]["name"] if s["team_id"] in teams else "?"
        sem_id = None
        if t_name and t_name != "?":
            m = re.match(r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", t_name)
            if m:
                sem_id = m.group(1)
        out.append(
            MissedRow(
                team_id=s["team_id"],
                team_name=t_name,
                slot=s["slot_label"],
                status=s["status"],
                semester_id=sem_id,
            )
        )
    return out


@router.post("/{panel_id}/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    panel_id: str,
    alert_id: int,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Mark an alert as acknowledged/read"""
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    res = client.table("alerts").update({
        "acknowledged_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", alert_id).eq("panel_id", panel_id).execute()

    if res.data:
        return {"status": "acknowledged"}
    else:
        raise HTTPException(status_code=404, detail="Alert not found")


@router.post("/{panel_id}/missed/{team_id}/request-reschedule")
def request_reschedule(
    panel_id: str,
    team_id: int,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Request admin to reschedule a missed evaluation slot"""
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    res_team = client.table("teams").select("*").eq("id", team_id).execute()
    if not res_team.data:
        raise HTTPException(status_code=404, detail="Team not found")
    team = res_team.data[0]

    res_slot = client.table("slots").select("*")\
        .eq("panel_id", panel_id)\
        .eq("team_id", team_id)\
        .in_("status", ["Missed", "missed"])\
        .execute()
    slot = res_slot.data[0] if res_slot.data else None

    if not slot:
        raise HTTPException(status_code=404, detail="No missed slot found for this team")

    now = datetime.now(timezone.utc).isoformat()
    
    # ── Insert into absent_students to notify the Administrator in the absent list ──
    import time
    import json
    
    team_name_str = team.get("name") or resolve_team_string_id(client, team_id)
    
    possible_ids = [team_name_str, resolve_team_string_id(client, team_id), str(team_id)]
    possible_ids = list(set([pid for pid in possible_ids if pid]))
    
    # Select only id and members — absent_students has no semester_id column
    res_val = client.table("teams_validation").select("id, members").in_("id", possible_ids).execute()
    
    absent_rows = []
    
    from app.db_helpers import resolve_team_semester_id
    team_sem_id = resolve_team_semester_id(client, team_id)
    
    if res_val.data:
        row_data = res_val.data[0]
        team_key = row_data.get("id") or team_name_str
        
        members = row_data.get("members") or []
        if isinstance(members, str):
            try:
                members = json.loads(members)
            except Exception:
                members = []
                
        now_ms = int(time.time() * 1000)
        try:
            for idx, member in enumerate(members):
                # members can be dicts {name, roll} or plain strings
                if isinstance(member, dict):
                    roll = member.get("roll") or member.get("id") or f"{team_key}-student-{idx}"
                    name = member.get("name") or "Unknown Student"
                else:
                    name = str(member).strip() or "Unknown Student"
                    roll = f"{team_key}-student-{idx}"
                absent_rows.append({
                    "id": f"ABS-{now_ms}-{idx}",
                    "name": name,
                    "roll": str(roll),
                    "team": team_key,
                    "reason": f"Reschedule requested by Panel {panel_id}",
                    "status": "Pending",
                    "semester_id": team_sem_id,
                })
        except Exception as member_err:
            print(f"Error building absent rows from members: {member_err}")
            absent_rows = []  # fall through to the single-row fallback
    else:
        team_key = team_name_str
            
    if not absent_rows:
        now_ms = int(time.time() * 1000)
        absent_rows.append({
            "id": f"ABS-{now_ms}-0",
            "name": f"Entire Team {team_name_str}",
            "roll": f"{team_key}-ALL",
            "team": team_key,
            "reason": f"Reschedule requested by Panel {panel_id}",
            "status": "Pending",
            "semester_id": team_sem_id,
        })
        
    try:
        client.table("absent_students").insert(absent_rows).execute()
    except Exception as e:
        print(f"Error marking team/students as absent: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to record absent team/students: {str(e)}"
        )

    # Also log to alerts
    client.table("alerts").insert({
        "panel_id": panel_id,
        "team_id": team_id,
        "user_id": user["id"],
        "alert_type": "reschedule_request",
        "title": f"Reschedule Request - Team {team_name_str}",
        "body": f"Panel {panel_id} has requested to reschedule the missed evaluation slot for Team {team_name_str} (Team ID: {team_id}). Original slot: {slot['slot_label']}. Please review and assign a new slot.",
        "created_at": now
    }).execute()

    return {
        "status": "success",
        "message": "Reschedule request sent to administrator successfully"
    }


# ---------------------------------------------------------------------------
# Slot Management — panel-facing endpoints for SlotManagement.jsx
# ---------------------------------------------------------------------------


@router.get("/{panel_id}/teams/catalog", response_model=list[TeamCatalogRow])
def team_catalog(
    panel_id: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    """
    Returns ALL teams in the DB with their current slot assignment for this panel
    (or null if unassigned).
    """
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
        
    refresh_slot_statuses(client, panel_id)

    res_teams = client.table("teams").select("*").order("id").execute()
    active_team_ids = get_active_team_ids(client)
    all_teams = [t for t in res_teams.data if t["id"] in active_team_ids]
    
    res_slots = client.table("slots").select("*").eq("panel_id", panel_id).execute()
    slot_map = {s["team_id"]: s for s in res_slots.data}

    res_proj = client.table("projects").select("team_id, title").execute()
    projects = {p["team_id"]: p["title"] for p in res_proj.data or []}

    out: list[TeamCatalogRow] = []
    for team in all_teams:
        s = slot_map.get(team["id"])
        
        ws_val = None
        we_val = None
        if s:
            ws_val = datetime.fromisoformat(s["window_start"].replace("Z", "+00:00"))
            we_val = datetime.fromisoformat(s["window_end"].replace("Z", "+00:00"))
            
        sem_id = None
        t_name = team.get("name")
        if t_name:
            m = re.match(r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", t_name)
            if m:
                sem_id = m.group(1)
        out.append(
            TeamCatalogRow(
                team_id=team["id"],
                team_name=team["name"],
                project_title=projects.get(team["id"]),
                current_slot=s["slot_label"] if s else None,
                current_status=s["status"] if s else None,
                venue=s["venue"] if s else None,
                window_start=ws_val,
                window_end=we_val,
                semester_id=sem_id,
            )
        )
    return out


@router.get("/{panel_id}/teams/unassigned", response_model=list[TeamCatalogRow])
def unassigned_teams(
    panel_id: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Teams that do NOT yet have a slot assigned to this panel."""
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    res_slots = client.table("slots").select("team_id").eq("panel_id", panel_id).execute()
    assigned_team_ids = {s["team_id"] for s in res_slots.data}
    
    res_teams = client.table("teams").select("*").order("id").execute()
    active_team_ids = get_active_team_ids(client)
    teams = [t for t in res_teams.data if t["id"] in active_team_ids]
    
    res_proj = client.table("projects").select("team_id, title").execute()
    projects = {p["team_id"]: p["title"] for p in res_proj.data or []}
    
    import re
    out = []
    for t in teams:
        if t["id"] in assigned_team_ids:
            continue
        t_name = t.get("name")
        sem_id = None
        if t_name:
            m = re.match(r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", t_name)
            if m:
                sem_id = m.group(1)
        out.append(
            TeamCatalogRow(
                team_id=t["id"],
                team_name=t_name,
                project_title=projects.get(t["id"]),
                semester_id=sem_id,
            )
        )
    return out


from pydantic import BaseModel as _PanelBM
from datetime import datetime as _dt


class _SlotUpsertBody(_PanelBM):
    window_start: _dt
    window_end: _dt
    venue: str | None = "Main Hall"
    slot_label: str


@router.put("/{panel_id}/slots/{team_id}")
def upsert_slot(
    panel_id: str,
    team_id: int,
    body: _SlotUpsertBody,
    user: Annotated[dict, Depends(get_current_user)],
):
    """
    Create or update the slot for a team within this panel's schedule.
    """
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    res_team = client.table("teams").select("id").eq("id", team_id).execute()
    if not res_team.data:
        raise HTTPException(status_code=404, detail="Team not found")

    now = datetime.now(timezone.utc)

    res_slot = client.table("slots").select("*")\
        .eq("panel_id", panel_id)\
        .eq("team_id", team_id)\
        .execute()
    existing = res_slot.data[0] if res_slot.data else None

    from datetime import timezone as dt_timezone, timedelta as dt_timedelta
    ist_tz = dt_timezone(dt_timedelta(hours=5, minutes=30))
    ws = body.window_start if body.window_start.tzinfo else body.window_start.replace(tzinfo=ist_tz).astimezone(timezone.utc)
    we = body.window_end if body.window_end.tzinfo else body.window_end.replace(tzinfo=ist_tz).astimezone(timezone.utc)

    if now > we:
        new_status = "Missed"
    elif ws <= now <= we:
        new_status = "Active"
    else:
        new_status = "Upcoming"

    if existing:
        if existing["status"].lower() == "submitted":
            raise HTTPException(status_code=409, detail="Cannot modify a submitted slot")
        client.table("slots").update({
            "slot_label": body.slot_label,
            "window_start": body.window_start.isoformat(),
            "window_end": body.window_end.isoformat(),
            "venue": body.venue,
            "status": new_status,
        }).eq("id", existing["id"]).execute()
    else:
        client.table("slots").insert({
            "panel_id": panel_id,
            "team_id": team_id,
            "slot_label": body.slot_label,
            "window_start": body.window_start.isoformat(),
            "window_end": body.window_end.isoformat(),
            "venue": body.venue,
            "status": new_status,
        }).execute()

    from app.cache import invalidate
    invalidate(f"panel_teams_response:{panel_id}")
    invalidate(f"panel_dashboard_response:{panel_id}")
    invalidate(f"panel_status_data:{panel_id}")
    invalidate(f"meet_link_map:{panel_id}")
    invalidate(f"mentor_teams_response:{panel_id}")

    return {"saved": True, "team_id": team_id, "status": new_status}



@router.post("/{panel_id}/slots/{team_id}/activate")
def activate_slot(
    panel_id: str,
    team_id: int,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Force-activate an upcoming slot (admin override)."""
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    res_slot = client.table("slots").select("*")\
        .eq("panel_id", panel_id)\
        .eq("team_id", team_id)\
        .execute()
    slot = res_slot.data[0] if res_slot.data else None
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot["status"].lower() == "submitted":
        raise HTTPException(status_code=409, detail="Slot already submitted")

    client.table("slots").update({"status": "Active"}).eq("id", slot["id"]).execute()

    from app.cache import invalidate
    invalidate(f"panel_teams_response:{panel_id}")
    invalidate(f"panel_dashboard_response:{panel_id}")
    invalidate(f"panel_status_data:{panel_id}")
    invalidate(f"meet_link_map:{panel_id}")
    invalidate(f"mentor_teams_response:{panel_id}")

    return {"activated": True, "team_id": team_id}



@router.get("/semesters")
def get_semesters(user: Annotated[dict, Depends(get_current_user)]):
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
    res = client.table("semester_config").select("*").execute()
    return res.data or []


# ---------------------------------------------------------------------------
# Procksi Chat
#
# A panel member sees their own direct thread with the coordinator, plus
# broadcasts. Panel-to-team threads are created only when a panel writes to a
# team it is scheduled to evaluate; that lookup is not wired yet because
# schedule_slots is empty, so those threads are not offered here.
#
# The panel identity comes from the authenticated user's panel_id claim, never
# from the request body.
# ---------------------------------------------------------------------------

class PanelChatMessagePayload(BaseModel):
    conversation_id: int
    body: str


def _panel_identity(user: dict) -> tuple[str, str]:
    return str(user.get("panel_id") or ""), str(user.get("email") or "")


# The standing groups a panel belongs to. Membership is derived from role
# rather than stored, so a panel created next week is in "All Panels" without
# anyone editing a list. Someone who is also a mentor reaches "All Mentors"
# through their mentor login, not through this one, so neither group ever
# lists them twice.
PANEL_GROUP_KEYS = ("panels", "everyone")


def _panel_visible_conversations(user: dict) -> list[dict]:
    client = get_supabase_service()
    if client is None:
        return []
    panel_id, email = _panel_identity(user)
    rows = (client.table("conversations").select("*").execute().data) or []

    visible = []
    for c in rows:
        rtype = c.get("recipient_type")
        if rtype is None and c.get("kind") is None:
            visible.append({**c, "group": "broadcast"})
        elif c.get("kind") == "group":
            if c.get("group_key") in PANEL_GROUP_KEYS:
                visible.append({**c, "group": "group"})
        elif rtype == "panel" and str(c.get("recipient_id")) in (panel_id, email):
            visible.append({**c, "group": "coordinator"})
    return visible


@router.get("/chat/conversations")
def get_panel_chat_conversations(user: Annotated[dict, Depends(get_current_user)]):
    rows = _panel_visible_conversations(user)
    return {"status": "success", "data": [{
        "id": c.get("id"),
        "subject": c.get("subject"),
        "group": c.get("group"),
        "recipient_label": c.get("recipient_label"),
        "group_key": c.get("group_key"),
        "updated_at": c.get("updated_at"),
    } for c in rows]}


def _is_unread_for(message: dict, viewer_needle: str) -> bool:
    """Unread means somebody else wrote it and the viewer is not yet in read_by.
    Case-insensitive: the portals sign with whatever casing the login gave."""
    if not viewer_needle:
        return False
    if str(message.get("sender_id") or "").strip().lower() == viewer_needle:
        return False
    readers = message.get("read_by") if isinstance(message.get("read_by"), list) else []
    return not any(str(r or "").strip().lower() == viewer_needle for r in readers)


@router.get("/chat/unread")
def get_panel_chat_unread(user: Annotated[dict, Depends(get_current_user)]):
    """Unread totals for the sidebar badge, kept apart from /chat/conversations
    because the badge is polled from every page in the portal."""
    empty = {"status": "success", "data": {"unread": 0, "by_conversation": {}}}

    convs = _panel_visible_conversations(user)
    ids = [int(c["id"]) for c in convs if c.get("id") is not None]
    if not ids:
        return empty

    client = get_supabase_service()
    if client is None:
        return empty
    try:
        rows = (client.table("conversation_messages")
                .select("conversation_id,sender_id,read_by")
                .in_("conversation_id", ids).execute().data) or []
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Procksi Chat unread query failed: {exc}")
        return empty

    panel_id, email = _panel_identity(user)
    needle = (email or panel_id).strip().lower()
    by_conversation: dict = {}
    for m in rows:
        if not _is_unread_for(m, needle):
            continue
        key = str(m.get("conversation_id"))
        by_conversation[key] = by_conversation.get(key, 0) + 1

    return {"status": "success", "data": {
        "unread": sum(by_conversation.values()), "by_conversation": by_conversation,
    }}


@router.get("/chat/messages")
def get_panel_chat_messages(
    conversation_id: int,
    user: Annotated[dict, Depends(get_current_user)],
):
    allowed = {int(c["id"]) for c in _panel_visible_conversations(user) if c.get("id") is not None}
    if int(conversation_id) not in allowed:
        raise HTTPException(status_code=403, detail="This conversation is not available to you.")

    client = get_supabase_service()
    rows = (client.table("conversation_messages")
            .select("*").eq("conversation_id", int(conversation_id))
            .order("created_at").execute().data) or []

    # Opening a thread is what "read" means, so mark it here rather than
    # requiring a separate call. Messages this panel wrote, or has already read,
    # are skipped, so the poll stops writing once it has caught up.
    panel_id, email = _panel_identity(user)
    viewer = email or panel_id
    needle = viewer.strip().lower()
    for m in rows if viewer else []:
        if str(m.get("sender_id") or "").strip().lower() == needle:
            continue
        readers = m.get("read_by") if isinstance(m.get("read_by"), list) else []
        if any(str(r or "").strip().lower() == needle for r in readers):
            continue
        updated = list(readers) + [viewer]
        try:
            (client.table("conversation_messages")
             .update({"read_by": updated}).eq("id", int(m["id"])).execute())
            m["read_by"] = updated
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Procksi Chat could not mark message read: {exc}")

    return {"status": "success", "data": [{
        "id": m.get("id"),
        "conversation_id": m.get("conversation_id"),
        "sender_role": m.get("sender_role"),
        "sender_id": m.get("sender_id"),
        # Drives the delivery ticks: a reader other than the sender means read.
        "read_by": m.get("read_by") or [],
        "body": m.get("body"),
        # ProcksiBot's reports carry their structured payload here. Nothing else
        # writes it, so it is null for every message a person typed.
        "metadata": m.get("metadata"),
        "created_at": m.get("created_at"),
    } for m in rows]}


@router.post("/chat/messages")
def post_panel_chat_message(
    payload: PanelChatMessagePayload,
    user: Annotated[dict, Depends(get_current_user)],
):
    body = (payload.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message body is required.")

    allowed = {int(c["id"]) for c in _panel_visible_conversations(user) if c.get("id") is not None}
    if int(payload.conversation_id) not in allowed:
        raise HTTPException(status_code=403, detail="This conversation is not available to you.")

    client = get_supabase_service()
    _, email = _panel_identity(user)
    sender_id = email or str(user.get("panel_id") or "")

    client.table("conversation_messages").insert({
        "conversation_id": int(payload.conversation_id),
        "sender_role": "panel",
        "sender_id": sender_id,
        "body": body,
        "read_by": [sender_id],
    }).execute()
    client.table("conversations").update(
        {"updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", int(payload.conversation_id)).execute()

    return {"status": "success", "data": {"sent": True, "conversation_id": int(payload.conversation_id)}}


class PanelChatCommandPayload(BaseModel):
    command: str
    option: str | None = None
    conversation_id: int | None = None


def _post_report_as_bot(conversation_id: int, report: dict, requested_by: str) -> dict:
    """
    Write a finished report into the thread as a message from ProcksiBot.

    A report is a message, not a private lookup: it is stored, everyone in the
    thread sees it, and it stays there. The person who ran the command is seeded
    into read_by so they are not badged for output they just watched appear.
    """
    from app.services import chat_report

    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=503, detail="The chat store is not reachable.")

    row = chat_report.build_bot_message(conversation_id, report, requested_by)
    client.table("conversation_messages").insert(row).execute()
    try:
        client.table("conversations").update(
            {"updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", int(conversation_id)).execute()
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Could not bump conversation timestamp: {exc}")

    return {"status": "success", "data": {
        "command": "report",
        "step": "posted",
        "conversation_id": int(conversation_id),
    }}


@router.post("/chat/command")
def run_panel_chat_command(
    payload: PanelChatCommandPayload,
    user: Annotated[dict, Depends(get_current_user)],
):
    """
    Execute a slash command. The result is posted into the open conversation as
    a message from ProcksiBot, so it is stored and everyone in that thread sees it.

    Scope rule, shared by all four portals: a report reads only conversations
    the caller could already open. For a panel that means its own coordinator
    threads and announcements — NOT the private chats of the teams it
    evaluates. A panel is not a participant in those, and an evaluator being
    handed a team's internal conversation is not something this command should
    quietly enable.
    """
    import asyncio
    from app.services import chat_report

    command = (payload.command or "").strip().lower().lstrip("/")
    if command != "report":
        raise HTTPException(status_code=400, detail=f"Unknown command: /{command}")

    option = (payload.option or "").strip().lower()
    if option not in ("thread-analysis", "weekly-github"):
        return {"status": "success", "data": {
            "command": "report", "step": "choose",
            "options": [
                {"id": "weekly-github", "label": "Weekly GitHub",
                 "description": "Repository reports for the teams you evaluate."},
                {"id": "thread-analysis", "label": "Thread Analysis",
                 "description": "Tasks and communication across your own conversations."},
            ],
        }}

    convs = _panel_visible_conversations(user)
    ids = [int(c["id"]) for c in convs if c.get("id") is not None]

    # The report is posted into a thread, so the client has to say which one.
    #
    # Broadcasts are excluded even though the panel can read them: a broadcast
    # is the coordinator addressing everyone, and a panel's report does not
    # belong in it. Only the panel's own coordinator threads qualify.
    if not payload.conversation_id:
        raise HTTPException(status_code=400,
                            detail="Open a conversation before running /report.")
    conversation_id = int(payload.conversation_id)
    postable = {int(c["id"]) for c in convs
                if c.get("id") is not None and c.get("group") == "coordinator"}
    if conversation_id not in postable:
        raise HTTPException(status_code=403,
                            detail="A report can only be posted into your own conversations.")

    if option == "weekly-github":
        # A panel's conversations are with the coordinator and carry no team, so
        # unlike the other portals this report cannot scope to "the team in this
        # thread". It covers every team the panel is scheduled to evaluate, and
        # each row is labelled with the team it belongs to.
        import re

        panel_id, panel_email = _panel_identity(user)
        client = get_supabase_service()
        analysis: list[dict] = []
        labels: dict[str, str] = {}
        team_ids: list = []

        if client is not None and panel_id:
            try:
                slots = (client.table("slots").select("team_id")
                         .eq("panel_id", panel_id).execute().data) or []
                team_ids = sorted({s["team_id"] for s in slots if s.get("team_id") is not None})
            except Exception as exc:
                logging.getLogger(__name__).warning(f"/report slot lookup failed: {exc}")

        if client is not None and team_ids:
            # team_ids are panel-api's local surrogate keys (public.teams.id), not
            # the shared teams_validation.team_number that github_agent_analysis.team_id
            # actually stores — team_number repeats across semesters, so matching on
            # it here could pull another team's report into this list. Resolve each
            # team's canonical team_uid (teams_validation.uid — the designated
            # canonical key for all team-scoped data) via public.teams.name (kept
            # equal to teams_validation.id by panel-api's own sync) and match on that.
            team_uid_by_local_id: dict = {}
            try:
                teams_for_ref = (client.table("teams").select("id,name")
                                  .in_("id", team_ids).execute().data) or []
                candidate_names = [t["name"] for t in teams_for_ref if t.get("name")]
                uid_by_name = {}
                if candidate_names:
                    tv_rows = (client.table("teams_validation").select("id,uid")
                               .in_("id", candidate_names).execute().data) or []
                    uid_by_name = {r["id"]: r["uid"] for r in tv_rows if r.get("uid")}
                for t in teams_for_ref:
                    uid = uid_by_name.get(t.get("name"))
                    if uid:
                        team_uid_by_local_id[t["id"]] = uid
            except Exception as exc:
                logging.getLogger(__name__).warning(f"/report team_uid resolution failed: {exc}")

            team_uids = list(team_uid_by_local_id.values())
            unresolved_ids = [tid for tid in team_ids if tid not in team_uid_by_local_id]

            try:
                if team_uids:
                    analysis += (client.table("github_agent_analysis")
                                 .select("*").in_("team_uid", team_uids)
                                 .not_.is_("raw_report", "null")
                                 .order("created_at", desc=True).limit(20).execute().data) or []
                if unresolved_ids:
                    analysis += (client.table("github_agent_analysis")
                                 .select("*").in_("team_id", unresolved_ids)
                                 .not_.is_("raw_report", "null")
                                 .order("created_at", desc=True).limit(20).execute().data) or []
            except Exception as exc:
                logging.getLogger(__name__).warning(f"/report weekly lookup failed: {exc}")

            try:
                teams = (client.table("teams").select("id,name")
                         .in_("id", team_ids).execute().data) or []
                # Some team names are stored prefixed with the semester uuid
                # ("<uuid>-T3"); show the readable tail rather than the key.
                names = {t["id"]: re.sub(
                    r"^[0-9a-fA-F-]{36}-", "", str(t.get("name") or "")
                ) or f"Team {t['id']}" for t in teams}
                for r in analysis:
                    key = str(r.get("team_ref") or r.get("team_id") or "")
                    label = names.get(r.get("team_id"))
                    if key and label:
                        labels[key] = label
            except Exception as exc:
                logging.getLogger(__name__).warning(f"/report team name lookup failed: {exc}")

        return _post_report_as_bot(
            conversation_id,
            chat_report.build_weekly_github(
                analysis, requested_by=panel_email or "", team_labels=labels,
                unavailable_reason=None if team_ids else
                "You have no teams allocated yet, so there are no repositories "
                "to report on.",
            ),
            panel_email or "",
        )

    messages: list[dict] = []
    if ids:
        client = get_supabase_service()
        if client is not None:
            try:
                messages = (client.table("conversation_messages")
                            .select("*").in_("conversation_id", ids)
                            .order("created_at").execute().data) or []
            except Exception as exc:
                logging.getLogger(__name__).warning(f"/report message fetch failed: {exc}")

    _, email = _panel_identity(user)
    members = [{"id": email or "panel", "name": "You", "email": email or "", "roll": ""}]

    extraction = asyncio.run(chat_report.extract_tasks(messages, members))
    task_summary = chat_report.summarise_tasks(extraction["tasks"], members)
    communication = chat_report.compute_communication(messages, members)

    return _post_report_as_bot(conversation_id, {
        "command": "report", "option": "thread-analysis", "step": "result",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": email or "",
        "team": {"id": None, "members": members},
        "health": {
            "milestones_total": 0, "milestones_completed": 0, "milestones_overdue": 0,
            "tasks_total": task_summary["total"],
            "tasks_completed": task_summary["completed"],
            "tasks_overdue": task_summary["overdue"],
            "unanswered_messages": communication["unanswered_messages"],
        },
        "tasks": extraction["tasks"],
        "task_summary": task_summary,
        "workload": task_summary["workload"],
        "communication": communication,
        "github": {"available": False,
                   "reason": "Repository analysis belongs to a team, not to this thread."},
        "extraction": {
            "available": extraction["available"], "reason": extraction["reason"],
            "messages_scanned": len(chat_report.human_messages(messages)),
        },
    }, email or "")


@router.get("/procksi-chat-enabled")
def get_procksi_chat_enabled():
    """Whether Procksi Chat is switched on for the panel portal this semester.

    Unauthenticated and read-only: the portal shell needs this before it knows
    who the user is, and the answer is a single boolean.

    Served here rather than read from the browser because RLS hides
    semester_config from the anon key -- a direct client read returns zero
    rows, which is indistinguishable from "no semester configured".

    Fails open so a lookup problem leaves the feature as the build intended.
    """
    try:
        client = get_supabase_service()
        if client is None:
            logging.getLogger(__name__).warning("procksi-chat-enabled: no service client; defaulting to enabled")
            return {"enabled": True, "reason": "no-service-client"}
        res = (
            client.table("semester_config")
            .select("procksi_chat_panel")
            .eq("is_active", True)
            .execute()
        )
        rows = res.data or []
        if not rows:
            # See the mentor portal's copy: a silent fail-open makes a stale or
            # misconfigured backend look exactly like the feature being on.
            logging.getLogger(__name__).warning(
                "procksi-chat-enabled: no active semester_config row; defaulting to enabled"
            )
            return {"enabled": True, "reason": "no-active-semester"}
        # Multiple batches (B.Tech years) can be active at once; enable if any
        # active batch has it on. A missing column (None everywhere) counts as
        # on, matching the fail-open default.
        if all(r.get("procksi_chat_panel") is None for r in rows):
            logging.getLogger(__name__).warning(
                "procksi-chat-enabled: procksi_chat_panel column missing; defaulting to enabled"
            )
            return {"enabled": True, "reason": "column-missing"}
        enabled = any(r.get("procksi_chat_panel") in (None, True) for r in rows)
        return {"enabled": enabled, "reason": "config"}
    except Exception as exc:
        logging.getLogger(__name__).warning("procksi-chat-enabled: lookup failed (%s); defaulting to enabled", exc)
        return {"enabled": True, "reason": "lookup-failed"}
