"""
Admin-sync router — endpoints called by the admin portal to keep the
panel portal's shared Supabase database in sync.

All routes require the `X-Admin-Api-Key` header matching ADMIN_API_KEY in .env.
"""

import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.deps import require_admin_key
from app.supabase_client import get_supabase_service
from app.security import hash_password
from app.slot_service import normalized_score
from app.db_helpers import get_project_title, resolve_team_uid, semester_id_from_cycle

router = APIRouter(prefix="/admin/sync", tags=["admin-sync"])

# ---------------------------------------------------------------------------
# Request / Response schemas (admin-facing)
# ---------------------------------------------------------------------------


class PanelUpsertRequest(BaseModel):
    display_name: str | None = None
    round_name: str | None = None
    is_active: bool = True
    email: EmailStr | None = None
    password: str | None = None


class TeamUpsertItem(BaseModel):
    team_id: int
    team_name: str
    project_title: str | None = None
    project_description: str | None = None
    github_url: str | None = None
    github_branch: str | None = "main"
    open_pull_requests: int | None = None
    commit_count_30d: int | None = None
    last_commit_at: datetime | None = None


class SlotUpsertItem(BaseModel):
    team_id: int
    slot_label: str
    window_start: datetime
    window_end: datetime
    venue: str | None = None
    cycle_id: UUID | None = None
    meet_link: str | None = None


class EvaluationResult(BaseModel):
    panel_id: str
    team_id: int
    team_name: str | None
    project_title: str | None
    receipt_id: str
    submitted_at: datetime
    scores: dict
    total_raw: int
    final_score_normalized: int
    remarks: str
    locked: bool
    cycle_id: UUID | None = None


class RubricCriterionIn(BaseModel):
    name: str | None = None
    criterion_name: str | None = None
    max_marks: int


class RubricSectionIn(BaseModel):
    category: str
    criteria: list[RubricCriterionIn]


class EvalParamsSyncRequest(BaseModel):
    sections: list[RubricSectionIn]


class BroadcastRequest(BaseModel):
    type: str
    recipients: str
    subject: str
    body: str
    sent_at: str | None = None


# ---------------------------------------------------------------------------
# Panel upsert
# ---------------------------------------------------------------------------


@router.put(
    "/panels/{panel_id}",
    summary="Upsert a panel and optionally its login user",
    dependencies=[Depends(require_admin_key)],
)
def upsert_panel(
    panel_id: str,
    body: PanelUpsertRequest,
):
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    res = client.table("panels").select("*").eq("id", panel_id).execute()
    panel = res.data[0] if res.data else None

    if panel:
        client.table("panels").update({
            "name": body.display_name or panel["name"],
            "description": body.round_name or panel["description"],
        }).eq("id", panel_id).execute()
    else:
        client.table("panels").insert({
            "id": panel_id,
            "name": body.display_name or panel_id,
            "description": body.round_name,
        }).execute()

    result: dict = {"panel_id": panel_id, "user_created": False, "user_updated": False}

    if body.email:
        res_user = client.table("users").select("*").eq("email", body.email).execute()
        user = res_user.data[0] if res_user.data else None

        password_val = body.password.strip() if body.password else None
        password_hash_to_use = None
        if not password_val:
            # Look up password_hash in mentors table (registration)
            res_mentor = client.table("mentors").select("password_hash").eq("email", body.email).execute()
            if res_mentor.data and res_mentor.data[0].get("password_hash"):
                password_hash_to_use = res_mentor.data[0]["password_hash"]

        if user:
            update_data = {
                "panel_id": panel_id,
                "role": "panel",
            }
            if password_val:
                update_data["hashed_password"] = hash_password(password_val)
            elif password_hash_to_use:
                update_data["hashed_password"] = password_hash_to_use
            client.table("users").update(update_data).eq("email", body.email).execute()
            result["user_updated"] = True
        else:
            hashed_val = None
            if password_val:
                hashed_val = hash_password(password_val)
            elif password_hash_to_use:
                hashed_val = password_hash_to_use

            if not hashed_val:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="password is required when creating a new panel user (and no registration record found)",
                )
            client.table("users").insert({
                "email": body.email,
                "hashed_password": hashed_val,
                "role": "panel",
                "panel_id": panel_id,
            }).execute()
            result["user_created"] = True

    return result


# ---------------------------------------------------------------------------
# Evaluation parameters sync — admin pushes rubric from semester config
# ---------------------------------------------------------------------------


@router.get(
    "/evaluation-parameters",
    summary="Get current evaluation rubric parameters",
    dependencies=[Depends(require_admin_key)],
)
def get_evaluation_parameters():
    """
    Called by the admin portal to load the live rubric on the semester edit form.
    Returns sections with criterion_name + max_marks per row.
    """
    client = get_supabase_service()
    if client is None:
        return {"sections": []}

    res = client.table("evaluation_parameters").select("*").order("id").execute()
    rows = res.data or []
    if not rows:
        return {"sections": []}

    sections_map: dict[str, list[dict]] = {}
    for r in rows:
        sections_map.setdefault(r["category"], []).append({
            "criterion_name": r["criterion_name"],
            "max_marks": r["max_marks"],
        })

    return {
        "sections": [
            {"category": cat, "criteria": criteria}
            for cat, criteria in sections_map.items()
        ]
    }


@router.post(
    "/evaluation-parameters",
    summary="Sync evaluation rubric parameters from admin portal",
    dependencies=[Depends(require_admin_key)],
)
def sync_evaluation_parameters(body: EvalParamsSyncRequest):
    """
    Called by the admin portal when evaluation config is saved.
    Replaces all rows in evaluation_parameters with the new rubric.
    """
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    # Delete existing parameters
    client.table("evaluation_parameters").delete().neq("id", 0).execute()

    # Insert new parameters
    rows = []
    for section in body.sections:
        for criterion in section.criteria:
            # Use either name or criterion_name
            criterion_name_val = criterion.name or criterion.criterion_name
            if not criterion_name_val:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Each criterion must have either 'name' or 'criterion_name'",
                )
            rows.append({
                "category": section.category,
                "criterion_name": criterion_name_val,
                "max_marks": criterion.max_marks,
            })

    if rows:
        client.table("evaluation_parameters").insert(rows).execute()

    return {"synced": True, "total_criteria": len(rows)}


# ---------------------------------------------------------------------------
# Broadcast — admin sends a message to the panel portal
# ---------------------------------------------------------------------------


@router.post(
    "/broadcast",
    summary="Broadcast a message from admin to panel portal",
    dependencies=[Depends(require_admin_key)],
)
def broadcast_message(body: BroadcastRequest):
    """
    Stores a broadcast message in the panel portal's notifications table.
    Panel members will see it on their next login/page load.
    """
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    row = {
        "type": body.type,
        "target": body.recipients,
        "subject": body.subject,
        "body": body.body,
        "sent_at": body.sent_at or datetime.now(timezone.utc).isoformat(),
        "is_read": False,
    }

    # Try to insert into notifications table; create it if it doesn't exist
    try:
        client.table("notifications").insert(row).execute()
    except Exception as e:
        # Notifications table may not exist yet — log but don't fail
        print(f"Broadcast insert warning: {e}")
        return {"broadcast": False, "warning": str(e)}

    return {"broadcast": True}


# ---------------------------------------------------------------------------
# Teams bulk upsert
# ---------------------------------------------------------------------------


@router.post(
    "/teams",
    summary="Bulk upsert teams, projects, and GitHub data",
    dependencies=[Depends(require_admin_key)],
)
def upsert_teams(items: list[TeamUpsertItem]):
    if not items:
        raise HTTPException(status_code=400, detail="No teams provided")

    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    updated, created = 0, 0

    for item in items:
        res_team = client.table("teams").select("id").eq("id", item.team_id).execute()
        if res_team.data:
            client.table("teams").update({"name": item.team_name}).eq("id", item.team_id).execute()
            updated += 1
        else:
            client.table("teams").insert({"id": item.team_id, "name": item.team_name}).execute()
            created += 1

        if item.project_title is not None:
            res_proj = client.table("projects").select("id").eq("team_id", item.team_id).execute()
            if res_proj.data:
                proj_update = {"title": item.project_title}
                if item.project_description is not None:
                    proj_update["description"] = item.project_description
                client.table("projects").update(proj_update).eq("team_id", item.team_id).execute()
            else:
                client.table("projects").insert({
                    "team_id": item.team_id,
                    "title": item.project_title,
                    "description": item.project_description,
                }).execute()

        if item.github_url is not None:
            res_gh = client.table("github_data").select("id").eq("team_id", item.team_id).execute()
            if res_gh.data:
                gh_update = {
                    "repository_url": item.github_url,
                    "default_branch": item.github_branch or "main",
                }
                if item.open_pull_requests is not None:
                    gh_update["open_pull_requests"] = item.open_pull_requests
                if item.commit_count_30d is not None:
                    gh_update["commit_count_30d"] = item.commit_count_30d
                if item.last_commit_at is not None:
                    gh_update["last_commit_at"] = item.last_commit_at.isoformat()
                client.table("github_data").update(gh_update).eq("team_id", item.team_id).execute()
            else:
                client.table("github_data").insert({
                    "team_id": item.team_id,
                    "repository_url": item.github_url,
                    "default_branch": item.github_branch or "main",
                    "open_pull_requests": item.open_pull_requests,
                    "commit_count_30d": item.commit_count_30d,
                    "last_commit_at": item.last_commit_at.isoformat() if item.last_commit_at else None,
                }).execute()

    return {"created": created, "updated": updated, "total": len(items)}


# ---------------------------------------------------------------------------
# Slots bulk upsert
# ---------------------------------------------------------------------------


@router.post(
    "/slots/{panel_id}",
    summary="Bulk upsert evaluation slots for a panel",
    dependencies=[Depends(require_admin_key)],
)
def upsert_slots(panel_id: str, items: list[SlotUpsertItem]):
    if not items:
        raise HTTPException(status_code=400, detail="No slots provided")

    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    res_panel = client.table("panels").select("id").eq("id", panel_id).execute()
    if not res_panel.data:
        raise HTTPException(
            status_code=404,
            detail=f"Panel '{panel_id}' not found. Create it first via PUT /admin/sync/panels/{panel_id}",
        )

    team_ids = list({item.team_id for item in items})
    res_teams = client.table("teams").select("id").in_("id", team_ids).execute()
    existing_team_ids = {t["id"] for t in res_teams.data or []}

    for item in items:
        if item.team_id not in existing_team_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Team {item.team_id} not found. Sync teams first via POST /admin/sync/teams",
            )

    res_slot = client.table("slots").select("*").eq("panel_id", panel_id).in_("team_id", team_ids).execute()
    existing_slots_map = {}
    for s in (res_slot.data or []):
        key = (s["team_id"], s.get("cycle_id"))
        existing_slots_map[key] = s

    for item in items:
        try:
            q = client.table("slots").delete().eq("team_id", item.team_id).neq("panel_id", panel_id)
            if item.cycle_id:
                q = q.eq("cycle_id", str(item.cycle_id))
            else:
                q = q.is_("cycle_id", "null")
            q.not_.eq("status", "submitted").not_.eq("status", "Submitted").execute()
        except Exception as del_e:
            print(f"Error cleaning up duplicate slot for team {item.team_id}: {del_e}")

    upserted, skipped = 0, 0
    slots_to_insert = []
    slots_to_update = []

    now = datetime.now(timezone.utc)
    from datetime import timezone as dt_timezone, timedelta as dt_timedelta
    ist_tz = dt_timezone(dt_timedelta(hours=5, minutes=30))

    for item in items:
        existing = existing_slots_map.get((item.team_id, str(item.cycle_id) if item.cycle_id else None))
        ws = item.window_start if item.window_start.tzinfo else item.window_start.replace(tzinfo=ist_tz).astimezone(timezone.utc)
        we = item.window_end if item.window_end.tzinfo else item.window_end.replace(tzinfo=ist_tz).astimezone(timezone.utc)

        if now > we:
            derived_status = "Missed"
        elif ws <= now <= we:
            derived_status = "Active"
        else:
            derived_status = "Upcoming"

        # Canonical cohort-scoped team link (team numbers collide across the
        # concurrently-active B.Tech years — resolve within the cycle's semester).
        item_sem_id = semester_id_from_cycle(client, item.cycle_id) if item.cycle_id else None
        team_uid = resolve_team_uid(client, item.team_id, semester_id=item_sem_id) if item_sem_id else None

        if existing:
            if existing["status"].lower() == "submitted":
                skipped += 1
                continue
            row = {
                "id": existing["id"],
                "panel_id": panel_id,
                "team_id": item.team_id,
                "slot_label": item.slot_label,
                "window_start": item.window_start.isoformat(),
                "window_end": item.window_end.isoformat(),
                "venue": item.venue if item.venue is not None else existing["venue"],
                "status": derived_status,
                "cycle_id": str(item.cycle_id) if item.cycle_id else None,
                "meet_link": item.meet_link if item.meet_link is not None else existing.get("meet_link"),
            }
            if team_uid and existing.get("team_uid") != team_uid:
                row["team_uid"] = team_uid
            slots_to_update.append(row)
        else:
            slots_to_insert.append({
                "panel_id": panel_id,
                "team_id": item.team_id,
                "team_uid": team_uid,
                "slot_label": item.slot_label,
                "window_start": item.window_start.isoformat(),
                "window_end": item.window_end.isoformat(),
                "venue": item.venue,
                "status": derived_status,
                "cycle_id": str(item.cycle_id) if item.cycle_id else None,
                "meet_link": item.meet_link,
            })
        upserted += 1

    if slots_to_insert:
        try:
            client.table("slots").insert(slots_to_insert).execute()
        except Exception as ins_e:
            raise HTTPException(status_code=500, detail=f"Database insert error: {ins_e}")

    if slots_to_update:
        try:
            for s in slots_to_update:
                payload = {k: v for k, v in s.items() if k != "id"}
                client.table("slots").update(payload).eq("id", s["id"]).execute()
        except Exception as upd_e:
            raise HTTPException(status_code=500, detail=f"Database update error: {upd_e}")

    # Invalidate panel caches so fresh data is visible immediately
    from app.cache import invalidate
    invalidate(f"panel_teams_response:{panel_id}")
    invalidate(f"panel_dashboard_response:{panel_id}")
    invalidate(f"panel_status_data:{panel_id}")
    invalidate(f"meet_link_map:{panel_id}")
    invalidate(f"mentor_teams_response:{panel_id}")

    return {"upserted": upserted, "skipped_submitted": skipped, "total": len(items)}



# ---------------------------------------------------------------------------
# Delete a slot
# ---------------------------------------------------------------------------


@router.delete(
    "/slots/{panel_id}/{team_id}",
    summary="Remove a slot (only if not yet submitted)",
    dependencies=[Depends(require_admin_key)],
)
def delete_slot(panel_id: str, team_id: int):
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    res_slot = client.table("slots").select("*").eq("panel_id", panel_id).eq("team_id", team_id).execute()
    slot = res_slot.data[0] if res_slot.data else None
    if not slot:
        return {"deleted": True, "panel_id": panel_id, "team_id": team_id, "detail": "Slot not found"}
    if slot["status"].lower() == "submitted":
        raise HTTPException(status_code=409, detail="Cannot delete a submitted slot.")
    client.table("slots").delete().eq("id", slot["id"]).execute()

    # Invalidate panel caches so changes are visible immediately
    from app.cache import invalidate
    invalidate(f"panel_teams_response:{panel_id}")
    invalidate(f"panel_dashboard_response:{panel_id}")
    invalidate(f"panel_status_data:{panel_id}")
    invalidate(f"meet_link_map:{panel_id}")
    invalidate(f"mentor_teams_response:{panel_id}")

    return {"deleted": True, "panel_id": panel_id, "team_id": team_id}



# ---------------------------------------------------------------------------
# Read evaluations
# ---------------------------------------------------------------------------


@router.get(
    "/evaluations",
    response_model=list[EvaluationResult],
    summary="Get all submitted evaluations (all panels)",
    dependencies=[Depends(require_admin_key)],
)
def get_all_evaluations():
    client = get_supabase_service()
    if client is None:
        return []
    res_sems = client.table("semester_config").select("id").eq("is_active", True).execute()
    active_sem_ids = [s["id"] for s in res_sems.data or []]

    # Get active team IDs
    from app.db_helpers import get_active_team_ids, to_numeric_id
    active_team_ids = get_active_team_ids(client)

    # 1. Fetch legacy evaluations
    query = client.table("evaluations").select("*").eq("locked", True)
    if active_sem_ids:
        query = query.in_("semester_id", active_sem_ids)
    res = query.execute()
    legacy_rows = [row for row in (res.data or []) if row.get("team_id") in active_team_ids]

    # 2. Fetch presentation evaluations
    pe_rows = []
    if active_sem_ids:
        res_cycles = client.table("presentation_cycles").select("id").in_("semester_id", active_sem_ids).execute()
        active_cycle_ids = [c["id"] for c in res_cycles.data or []]
        if active_cycle_ids:
            res_pe = client.table("presentation_evaluations").select("*").in_("cycle_id", active_cycle_ids).execute()
            pe_rows = [row for row in (res_pe.data or []) if to_numeric_id(row.get("team_id")) in active_team_ids]

    # Build results
    return _merge_and_build_eval_results(client, legacy_rows, pe_rows)


@router.get(
    "/evaluations/{panel_id}",
    response_model=list[EvaluationResult],
    summary="Get submitted evaluations for a specific panel",
    dependencies=[Depends(require_admin_key)],
)
def get_panel_evaluations(panel_id: str):
    client = get_supabase_service()
    if client is None:
        return []
    res_sems = client.table("semester_config").select("id").eq("is_active", True).execute()
    active_sem_ids = [s["id"] for s in res_sems.data or []]

    from app.db_helpers import get_active_team_ids, to_numeric_id
    active_team_ids = get_active_team_ids(client)

    # 1. Fetch legacy evaluations
    query = client.table("evaluations").select("*").eq("panel_id", panel_id).eq("locked", True)
    if active_sem_ids:
        query = query.in_("semester_id", active_sem_ids)
    res = query.execute()
    legacy_rows = [row for row in (res.data or []) if row.get("team_id") in active_team_ids]

    # 2. Fetch presentation evaluations
    pe_rows = []
    if active_sem_ids:
        res_cycles = client.table("presentation_cycles").select("id").in_("semester_id", active_sem_ids).execute()
        active_cycle_ids = [c["id"] for c in res_cycles.data or []]
        if active_cycle_ids:
            res_pe = client.table("presentation_evaluations")\
                .select("*")\
                .eq("evaluator_id", panel_id)\
                .in_("cycle_id", active_cycle_ids)\
                .execute()
            pe_rows = [row for row in (res_pe.data or []) if to_numeric_id(row.get("team_id")) in active_team_ids]

    # Build results
    return _merge_and_build_eval_results(client, legacy_rows, pe_rows)


def _merge_and_build_eval_results(client, legacy_rows: list[dict], pe_rows: list[dict]) -> list[EvaluationResult]:
    # 1. Gather team names and project titles.
    #    presentation_evaluations.team_id is the cohort-correct teams_validation.id
    #    slug — resolve labels from it directly. Bare team numbers are NOT unique
    #    across the concurrently-active B.Tech years, so the legacy teams(int)
    #    lookup would mislabel every colliding number.
    from app.db_helpers import to_numeric_id, resolve_team_string_id

    all_team_ids = set()          # numeric ids (legacy fallback lookups)
    slugs = set()                 # teams_validation.id slugs (canonical)
    for r in legacy_rows:
        all_team_ids.add(r["team_id"])
        slug = resolve_team_string_id(client, r["team_id"], semester_id=r.get("semester_id"))
        if slug:
            slugs.add(slug)
    for pe in pe_rows:
        tid = to_numeric_id(pe["team_id"])
        if tid:
            all_team_ids.add(tid)
        if pe.get("team_id"):
            slugs.add(str(pe["team_id"]))

    # canonical: slug -> {title, name}
    tv_by_slug = {}
    if slugs:
        res_tv = client.table("teams_validation").select("id, title").in_("id", list(slugs)).execute()
        tv_by_slug = {row["id"]: row for row in (res_tv.data or [])}

    team_ids_list = list(all_team_ids)
    teams = {}
    projects = {}
    if team_ids_list:
        res_teams = client.table("teams").select("id, name").in_("id", team_ids_list).execute()
        teams = {t["id"]: t for t in res_teams.data or []}
        res_projects = client.table("projects").select("team_id, title").in_("team_id", team_ids_list).execute()
        projects = {p["team_id"]: p for p in res_projects.data or []}

    def _labels_for_slug(slug):
        tv = tv_by_slug.get(slug) if slug else None
        if not tv:
            return None, None
        return slug, tv.get("title")

    # 2. Build presentation evaluations first
    results = []
    matched_legacy_ids = set()
    
    # Pre-parse presentation evaluations for matching
    pe_info = []
    for pe in pe_rows:
        tid = to_numeric_id(pe["team_id"])
        if not tid:
            continue
        pe_time = datetime.fromisoformat(pe["evaluated_at"].replace("Z", "+00:00"))
        pe_info.append({
            "pe": pe,
            "tid": tid,
            "time": pe_time,
            "panel_id": pe["evaluator_id"]
        })
        
        canon_name, canon_title = _labels_for_slug(str(pe["team_id"]))
        team = teams.get(tid)
        proj = projects.get(tid)
        results.append(EvaluationResult(
            panel_id=pe["evaluator_id"],
            team_id=tid,
            team_name=canon_name or (team["name"] if team else None),
            project_title=canon_title or (proj["title"] if proj else None),
            receipt_id=f"REC-{pe['id'].split('-')[0].upper()}",
            submitted_at=pe_time,
            scores={},
            total_raw=0,
            final_score_normalized=int(pe["total_score"]),
            remarks=pe["remarks"],
            locked=True,
            cycle_id=UUID(pe["cycle_id"]) if pe["cycle_id"] else None
        ))

    # 3. For each legacy evaluation, check if it matches any presentation evaluation.
    # If it does, we mark it as matched and do not add it to results.
    for ev in legacy_rows:
        ev_time = datetime.fromisoformat(ev["submitted_at"].replace("Z", "+00:00"))
        # Check if matched with any pe within 5 minutes
        matched = False
        for info in pe_info:
            if info["panel_id"] == ev["panel_id"] and info["tid"] == ev["team_id"]:
                diff = abs((ev_time - info["time"]).total_seconds())
                if diff < 300: # 5 minutes
                    matched = True
                    break
        if not matched:
            scores = json.loads(ev["scores_json"])
            int_scores = {k: int(v) for k, v in scores.items()}
            canon_name, canon_title = _labels_for_slug(
                resolve_team_string_id(client, ev["team_id"], semester_id=ev.get("semester_id"))
            )
            team = teams.get(ev["team_id"])
            proj = projects.get(ev["team_id"])
            results.append(EvaluationResult(
                panel_id=ev["panel_id"],
                team_id=ev["team_id"],
                team_name=canon_name or (team["name"] if team else None),
                project_title=canon_title or (proj["title"] if proj else None),
                receipt_id=ev["receipt_id"],
                submitted_at=ev_time,
                scores=int_scores,
                total_raw=sum(int_scores.values()),
                final_score_normalized=normalized_score(int_scores),
                remarks=ev["remarks"],
                locked=ev["locked"],
                cycle_id=None
            ))
            
    return results


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class AlertCreateRequest(BaseModel):
    panel_id: str
    team_id: int | None = None
    alert_type: str
    title: str
    body: str | None = None


@router.post(
    "/alerts",
    summary="Create a panel-facing alert",
    dependencies=[Depends(require_admin_key)],
)
def create_panel_alert(body: AlertCreateRequest):
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
    row = {
        "panel_id": body.panel_id,
        "team_id": body.team_id,
        "alert_type": body.alert_type,
        "title": body.title,
        "body": body.body,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = client.table("alerts").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create alert")
    return {"created": True, "alert": res.data[0]}


@router.get(
    "/alerts",
    summary="Get all alerts",
    dependencies=[Depends(require_admin_key)],
)
def get_all_alerts(alert_type: str | None = None, unacknowledged_only: bool = False):
    client = get_supabase_service()
    if client is None:
        return []
    query = client.table("alerts").select("*")
    if alert_type:
        query = query.eq("alert_type", alert_type)
    if unacknowledged_only:
        query = query.is_("acknowledged_at", "null")
    res = query.order("created_at", desc=True).execute()
    rows = res.data

    from app.db_helpers import get_active_team_ids
    active_team_ids = get_active_team_ids(client)
    ALWAYS_SHOW_TYPES = {"reschedule_request", "reschedule", "admin_action"}

    def _keep(r: dict) -> bool:
        if r.get("alert_type") in ALWAYS_SHOW_TYPES:
            return True
        if not r.get("team_id"):
            return True
        return r.get("team_id") in active_team_ids

    rows = [r for r in rows if _keep(r)]

    team_ids_needed = [r["team_id"] for r in rows if r.get("team_id")]
    teams: dict[int, dict] = {}
    if team_ids_needed:
        res_teams = client.table("teams").select("id, name").in_("id", team_ids_needed).execute()
        teams = {t["id"]: t for t in res_teams.data}

    return [
        {
            "id": r["id"],
            "panel_id": r["panel_id"],
            "team_id": r["team_id"],
            "team_name": teams[r["team_id"]]["name"] if r["team_id"] and r["team_id"] in teams else None,
            "alert_type": r["alert_type"],
            "title": r["title"],
            "body": r["body"],
            "created_at": r["created_at"],
            "acknowledged_at": r["acknowledged_at"],
        }
        for r in rows
    ]


@router.post(
    "/alerts/{alert_id}/acknowledge",
    summary="Mark an alert as acknowledged",
    dependencies=[Depends(require_admin_key)],
)
def acknowledge_alert_admin(alert_id: int):
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
    res = client.table("alerts").update({
        "acknowledged_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", alert_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"acknowledged": True, "alert_id": alert_id}


# ---------------------------------------------------------------------------
# Read slots
# ---------------------------------------------------------------------------


@router.get(
    "/slots/{panel_id}",
    summary="Get current slot schedule for a panel",
    dependencies=[Depends(require_admin_key)],
)
def get_panel_slots(panel_id: str):
    client = get_supabase_service()
    if client is None:
        return []
    from app.slot_service import refresh_slot_statuses
    refresh_slot_statuses(client, panel_id)
    res_slots = client.table("slots").select("*").eq("panel_id", panel_id).order("window_start").execute()
    slots = res_slots.data
    res_teams = client.table("teams").select("*").execute()
    teams = {t["id"]: t for t in res_teams.data}
    res_projects = client.table("projects").select("*").execute()
    projects = {p["team_id"]: p for p in res_projects.data}
    return [
        {
            "team_id": s["team_id"],
            "team_name": teams[s["team_id"]]["name"] if s["team_id"] in teams else None,
            "project_title": projects[s["team_id"]]["title"] if s["team_id"] in projects else None,
            "slot_label": s["slot_label"],
            "window_start": s["window_start"],
            "window_end": s["window_end"],
            "venue": s["venue"],
            "status": s["status"],
            "cycle_id": s.get("cycle_id"),
        }
        for s in slots
    ]


@router.get(
    "/panels",
    summary="List all panels",
    dependencies=[Depends(require_admin_key)],
)
def list_panels():
    client = get_supabase_service()
    if client is None:
        return []
    res = client.table("panels").select("*").order("id").execute()
    return [
        {
            "panel_id": p["id"],
            "display_name": p["name"],
            "round_name": p["description"],
            "is_active": True,
            "created_at": None,
        }
        for p in res.data
    ]
