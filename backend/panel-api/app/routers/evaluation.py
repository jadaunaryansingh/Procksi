import json
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.db_helpers import get_project_title, sync_team_results_from_evaluations, resolve_team_string_id
from app.deps import get_current_user, require_panel_access
from app.supabase_client import get_supabase_service
from app.schemas import (
    DraftPayload,
    EvaluationParametersResponse,
    EvaluationSessionResponse,
    RubricCriterion,
    RubricSection,
    SubmitEvaluationRequest,
    SubmitEvaluationResponse,
    CycleRubrics,
    SemesterRubrics,
)
from app.slot_service import normalized_score, refresh_slot_statuses, slot_allows_submission

router = APIRouter(tags=["evaluation"])

def resolve_semester_id_from_cycle(client, cycle_id: str) -> str | None:
    if not cycle_id:
        return None
    try:
        from app.cache import get_cached
        def _fetch():
            res = client.table("presentation_cycles").select("semester_id").eq("id", cycle_id).execute()
            return res.data[0].get("semester_id") if res.data else None
        return get_cached(f"cycle_sem:{cycle_id}", 3600.0, _fetch)
    except Exception as e:
        print(f"Error fetching cycle semester ID: {e}")
        return None

def resolve_team_cycle_id(client, team_id: int) -> str | None:
    try:
        res = client.table("slots").select("*").eq("team_id", team_id).execute()
        slots = res.data or []
        if not slots:
            return None
        unsubmitted = [s for s in slots if s.get("status", "").lower() != "submitted"]
        if unsubmitted:
            for status_type in ["Active", "Upcoming", "Missed"]:
                matching = [s for s in unsubmitted if s.get("status") == status_type]
                if matching:
                    return matching[0].get("cycle_id")
            return unsubmitted[0].get("cycle_id")
        return slots[0].get("cycle_id")
    except Exception as e:
        print(f"Error resolving team cycle_id: {e}")
        return None


def resolve_slot_cycle_id(client, panel_id: str, team_id: int) -> tuple[str | None, str | None]:
    try:
        res = client.table("slots").select("*").eq("panel_id", panel_id).eq("team_id", team_id).execute()
        slots = res.data or []
        if not slots:
            return None, None
        
        unsubmitted = [s for s in slots if s.get("status", "").lower() != "submitted"]
        if unsubmitted:
            for status_type in ["Active", "Upcoming", "Missed"]:
                matching = [s for s in unsubmitted if s.get("status") == status_type]
                if matching:
                    return matching[0].get("cycle_id"), matching[0]["id"]
            return unsubmitted[0].get("cycle_id"), unsubmitted[0]["id"]
        
        return slots[0].get("cycle_id"), slots[0]["id"]
    except Exception as e:
        print(f"Error resolving slot cycle_id: {e}")
        return None, None

REQUIRED_SCORE_KEYS = ("q1", "q2", "q3", "q4")


def _get_required_score_keys(client, team_id: int | None = None, semester_id: str | None = None, cycle_id: str | None = None) -> tuple[str, ...]:
    """Derive score keys from the live evaluation_parameters table or active presentation cycle.
    Falls back to the legacy ('q1','q2','q3','q4') tuple if empty."""
    if team_id is not None or semester_id is not None or cycle_id is not None:
        try:
            team_sem_id = semester_id
            if not team_sem_id and team_id is not None:
                from app.db_helpers import resolve_team_semester_id
                team_sem_id = resolve_team_semester_id(client, team_id)
            
            if not cycle_id and team_id is not None:
                cycle_id = resolve_team_cycle_id(client, team_id)
            if not cycle_id and team_sem_id:
                res_cycle = client.table("presentation_cycles")\
                    .select("id")\
                    .eq("semester_id", team_sem_id)\
                    .eq("status", "active")\
                    .execute()
                if res_cycle.data:
                    cycle_id = res_cycle.data[0]["id"]
            if cycle_id:
                res_rubrics = client.table("presentation_rubrics")\
                    .select("id")\
                    .eq("cycle_id", cycle_id)\
                    .order("id")\
                    .execute()
                if res_rubrics.data:
                    return tuple(f"q{i + 1}" for i in range(len(res_rubrics.data)))

                # Fallback to semester config
                if team_sem_id:
                    res_sem = client.table("semester_config")\
                        .select("evaluation_parameters")\
                        .eq("id", team_sem_id)\
                        .execute()
                    if res_sem.data and res_sem.data[0].get("evaluation_parameters"):
                        params = res_sem.data[0]["evaluation_parameters"]
                        return tuple(f"q{i + 1}" for i in range(len(params)))
        except Exception as e:
            print(f"[evaluation] Error resolving cycle keys: {e}")

    try:
        res = client.table("evaluation_parameters").select("category").execute()
        rows = res.data or []
        # One score key per unique category, in insertion order
        seen: list[str] = []
        for r in rows:
            if r["category"] not in seen:
                seen.append(r["category"])
        if seen:
            return tuple(f"q{i + 1}" for i in range(len(seen)))
    except Exception as e:
        print(f"[evaluation] Could not load score keys: {e}")
    return REQUIRED_SCORE_KEYS


def _get_max_total(client, team_id: int | None = None, semester_id: str | None = None, cycle_id: str | None = None) -> int:
    """Return the sum of max_marks across all criteria for score normalisation."""
    if team_id is not None or semester_id is not None or cycle_id is not None:
        try:
            team_sem_id = semester_id
            if not team_sem_id and team_id is not None:
                from app.db_helpers import resolve_team_semester_id
                team_sem_id = resolve_team_semester_id(client, team_id)

            if not cycle_id and team_id is not None:
                cycle_id = resolve_team_cycle_id(client, team_id)
            if not cycle_id and team_sem_id:
                res_cycle = client.table("presentation_cycles")\
                    .select("id")\
                    .eq("semester_id", team_sem_id)\
                    .eq("status", "active")\
                    .execute()
                if res_cycle.data:
                    cycle_id = res_cycle.data[0]["id"]
            if cycle_id:
                res_rubrics = client.table("presentation_rubrics")\
                    .select("max_marks")\
                    .eq("cycle_id", cycle_id)\
                    .execute()
                if res_rubrics.data:
                    return sum(r["max_marks"] for r in res_rubrics.data)

                # Fallback to semester config
                if team_sem_id:
                    res_sem = client.table("semester_config")\
                        .select("evaluation_parameters")\
                        .eq("id", team_sem_id)\
                        .execute()
                    if res_sem.data and res_sem.data[0].get("evaluation_parameters"):
                        params = res_sem.data[0]["evaluation_parameters"]
                        return sum(p["max_marks"] for p in params)
        except Exception as e:
            print(f"[evaluation] Error resolving cycle max total: {e}")

    try:
        res = client.table("evaluation_parameters").select("max_marks").execute()
        rows = res.data or []
        if rows:
            return sum(r["max_marks"] for r in rows)
    except Exception as e:
        print(f"[evaluation] Could not compute max total: {e}")
    # Legacy fallback: 4 categories × 10 pts each
    return 40


def _build_rubric(client, team_id: int | None = None, panel_id: str | None = None) -> EvaluationParametersResponse:
    if team_id is None:
        semesters_list = []
        try:
            res_sems = client.table("semester_config").select("*").execute()
            for sem in (res_sems.data or []):
                cycles_list = []
                res_cycles = client.table("presentation_cycles")\
                    .select("*")\
                    .eq("semester_id", sem["id"])\
                    .execute()
                for cycle in (res_cycles.data or []):
                    res_rubrics = client.table("presentation_rubrics")\
                        .select("*")\
                        .eq("cycle_id", cycle["id"])\
                        .order("id")\
                        .execute()
                    rubrics_sections = []
                    for r in (res_rubrics.data or []):
                        rubrics_sections.append(RubricSection(
                            category=r["criterion"],
                            criteria=[RubricCriterion(name=r["criterion"], max_marks=r["max_marks"])]
                        ))
                    cycle_total = sum(r["max_marks"] for r in (res_rubrics.data or []))
                    cycles_list.append(CycleRubrics(
                        id=str(cycle["id"]),
                        title=cycle["title"],
                        type=cycle["type"],
                        weightage=cycle["weightage"],
                        rubrics=rubrics_sections,
                        total_maximum=cycle_total
                    ))
                
                # If no cycles are configured for this semester, fall back to default evaluation parameters of the semester config
                if not cycles_list and sem.get("evaluation_parameters"):
                    params = sem["evaluation_parameters"]
                    rubrics_sections = []
                    for p in params:
                        rubrics_sections.append(RubricSection(
                            category=p["name"],
                            criteria=[RubricCriterion(name=p["name"], max_marks=p["max_marks"])]
                        ))
                    cycle_total = sum(p["max_marks"] for p in params)
                    cycles_list.append(CycleRubrics(
                        id="default",
                        title="Default Rubrics",
                        type="default",
                        weightage=100,
                        rubrics=rubrics_sections,
                        total_maximum=cycle_total
                    ))

                semesters_list.append(SemesterRubrics(
                    id=str(sem["id"]),
                    academic_year=sem.get("year") or "",
                    semester_type=sem.get("semester_type") or "",
                    branch=sem.get("branch") or "All",
                    academic_level=str(sem.get("academic_level")) if sem.get("academic_level") is not None else "All",
                    cycles=cycles_list
                ))
        except Exception as e:
            print(f"[evaluation] Error fetching all semester rubrics: {e}")
        
        return EvaluationParametersResponse(sections=[], total_maximum=0, locked=True, semesters=semesters_list)

    if team_id is not None:
        try:
            from app.db_helpers import resolve_team_semester_id
            team_sem_id = resolve_team_semester_id(client, team_id)
            cycle_id = None
            if panel_id:
                cycle_id, _ = resolve_slot_cycle_id(client, panel_id, team_id)
            if not cycle_id:
                cycle_id = resolve_team_cycle_id(client, team_id)
            if not cycle_id and team_sem_id:
                res_cycle = client.table("presentation_cycles")\
                    .select("id")\
                    .eq("semester_id", team_sem_id)\
                    .eq("status", "active")\
                    .execute()
                if res_cycle.data:
                    cycle_id = res_cycle.data[0]["id"]
            if cycle_id:
                res_rubrics = client.table("presentation_rubrics")\
                    .select("*")\
                    .eq("cycle_id", cycle_id)\
                    .order("id")\
                    .execute()
                if res_rubrics.data:
                    sections = []
                    for r in res_rubrics.data:
                        sections.append(RubricSection(
                            category=r["criterion"],
                            criteria=[RubricCriterion(name=r["criterion"], max_marks=r["max_marks"])]
                        ))
                    total = sum(r["max_marks"] for r in res_rubrics.data)
                    return EvaluationParametersResponse(sections=sections, total_maximum=total, locked=True)

                # Fallback to semester config
                res_sem = client.table("semester_config")\
                    .select("evaluation_parameters")\
                    .eq("id", team_sem_id)\
                    .execute()
                if res_sem.data and res_sem.data[0].get("evaluation_parameters"):
                    params = res_sem.data[0]["evaluation_parameters"]
                    sections = []
                    for p in params:
                        sections.append(RubricSection(
                            category=p["name"],
                            criteria=[RubricCriterion(name=p["name"], max_marks=p["max_marks"])]
                        ))
                    total = sum(p["max_marks"] for p in params)
                    return EvaluationParametersResponse(sections=sections, total_maximum=total, locked=True)
        except Exception as e:
            print(f"[evaluation] Error building rubric from cycle/semester: {e}")

    res = client.table("evaluation_parameters").select("*").order("id").execute()
    rows = res.data
    sections_map: dict[str, list[RubricCriterion]] = {}
    for r in rows:
        sections_map.setdefault(r["category"], []).append(RubricCriterion(name=r["criterion_name"], max_marks=r["max_marks"]))
    sections = [RubricSection(category=k, criteria=v) for k, v in sections_map.items()]
    total = sum(c.max_marks for s in sections for c in s.criteria)
    return EvaluationParametersResponse(sections=sections, total_maximum=total, locked=True)


@router.get("/evaluation/parameters", response_model=EvaluationParametersResponse)
def get_parameters(
    user: Annotated[dict, Depends(get_current_user)],
    team_id: int | None = None,
    panel_id: str | None = None,
):
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
    
    if not panel_id and user:
        panel_id = user.get("panel_id")
        
    return _build_rubric(client, team_id, panel_id)


@router.get("/evaluation/session/{team_id}", response_model=EvaluationSessionResponse)
def evaluation_session(
    team_id: int,
    panel_id: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
        
    # Status-only refresh is sufficient when opening the evaluation form
    refresh_slot_statuses(client, panel_id, full_sync=False)

    res_team = client.table("teams").select("id", "name").eq("id", team_id).execute()
    if not res_team.data:
        raise HTTPException(status_code=404, detail="Team not found")
    team = res_team.data[0]
    
    cycle_id, slot_id = resolve_slot_cycle_id(client, panel_id, team_id)
    res_slot = client.table("slots").select("*").eq("id", slot_id).execute() if slot_id else None
    if not res_slot or not res_slot.data:
        res_slot = client.table("slots").select("*").eq("panel_id", panel_id).eq("team_id", team_id).execute()
        if not res_slot.data:
            raise HTTPException(status_code=404, detail="Slot not found for team")
    s = res_slot.data[0]

    now = datetime.now(timezone.utc)
    team_sem_id = None
    if cycle_id:
        team_sem_id = resolve_semester_id_from_cycle(client, cycle_id)
    if not team_sem_id:
        from app.db_helpers import resolve_team_semester_id
        team_sem_id = resolve_team_semester_id(client, team_id)

    existing = None
    if cycle_id:
        from app.db_helpers import resolve_team_string_id
        team_str = resolve_team_string_id(client, team_id, semester_id=team_sem_id)
        res_peval = client.table("presentation_evaluations")\
            .select("*")\
            .eq("cycle_id", cycle_id)\
            .eq("team_id", team_str)\
            .eq("evaluator_id", panel_id)\
            .execute()
        existing = res_peval.data[0] if res_peval.data else None
    else:
        query = client.table("evaluations").select("*").eq("panel_id", panel_id).eq("team_id", team_id)
        if team_sem_id:
            query = query.eq("semester_id", team_sem_id)
        res_eval = query.execute()
        existing = res_eval.data[0] if res_eval.data else None
    
    allow = slot_allows_submission(client, panel_id, team_id, now, slot_id=s["id"]) and existing is None
    ws_val = datetime.fromisoformat(s["window_start"].replace("Z", "+00:00"))
    we_val = datetime.fromisoformat(s["window_end"].replace("Z", "+00:00"))
    
    remaining_seconds = max(0, int((we_val - now).total_seconds())) if allow else 0

    return EvaluationSessionResponse(
        team_id=team["id"],
        team_name=team["name"],
        project_title=get_project_title(client, team_id),
        allow_submission=bool(allow),
        slot_label=s["slot_label"],
        window_start=ws_val,
        window_end=we_val,
        server_now=now,
        evaluation_timer_seconds=settings.evaluation_timer_seconds,
        remaining_seconds=remaining_seconds,
        already_submitted=existing is not None,
        receipt_id=existing["receipt_id"] if existing else None,
        semester_id=str(team_sem_id) if team_sem_id else None,
    )


@router.put("/evaluation/draft/{team_id}")
def save_draft(
    team_id: int,
    panel_id: str,
    body: DraftPayload,
    user: Annotated[dict, Depends(get_current_user)],
):
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    cycle_id, slot_id = resolve_slot_cycle_id(client, panel_id, team_id)
    res_slot = client.table("slots").select("id").eq("id", slot_id).execute() if slot_id else None
    if not res_slot or not res_slot.data:
        res_slot = client.table("slots").select("id").eq("panel_id", panel_id).eq("team_id", team_id).execute()
        if not res_slot.data:
            raise HTTPException(status_code=404, detail="Slot not found")
        
    team_sem_id = None
    if cycle_id:
        team_sem_id = resolve_semester_id_from_cycle(client, cycle_id)
    if not team_sem_id:
        from app.db_helpers import resolve_team_semester_id
        team_sem_id = resolve_team_semester_id(client, team_id)

    has_submitted = False
    if cycle_id:
        from app.db_helpers import resolve_team_string_id
        team_str = resolve_team_string_id(client, team_id, semester_id=team_sem_id)
        res_peval = client.table("presentation_evaluations")\
            .select("id")\
            .eq("cycle_id", cycle_id)\
            .eq("team_id", team_str)\
            .eq("evaluator_id", panel_id)\
            .execute()
        has_submitted = bool(res_peval.data)
    else:
        query_eval = client.table("evaluations").select("id").eq("panel_id", panel_id).eq("team_id", team_id)
        if team_sem_id:
            query_eval = query_eval.eq("semester_id", team_sem_id)
        res_eval = query_eval.execute()
        has_submitted = bool(res_eval.data)

    if has_submitted:
        raise HTTPException(status_code=400, detail="Already submitted; draft locked")

    now = datetime.now(timezone.utc)
    if not slot_allows_submission(client, panel_id, team_id, now, slot_id=res_slot.data[0]["id"]):
        raise HTTPException(status_code=403, detail="Draft only allowed during live slot window")

    query_draft = client.table("evaluation_drafts").select("*").eq("panel_id", panel_id).eq("team_id", team_id)
    if team_sem_id:
        query_draft = query_draft.eq("semester_id", team_sem_id)
    res_draft = query_draft.execute()
    row = res_draft.data[0] if res_draft.data else None

    def coerce(k: str, v: object) -> object:
        if v == "" or v is None:
            return ""
        try:
            return int(v)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"Invalid draft score for {k}") from None

    payload_scores = {k: coerce(k, v) for k, v in body.scores.items()}
    updated_at_str = now.isoformat()
    
    if row:
        update_payload = {
            "scores_json": json.dumps(payload_scores),
            "remarks": body.remarks,
            "updated_at": updated_at_str,
        }
        if team_sem_id:
            update_payload["semester_id"] = team_sem_id
        client.table("evaluation_drafts").update(update_payload).eq("id", row["id"]).execute()
    else:
        from app.db_helpers import resolve_team_uid
        insert_payload = {
            "panel_id": panel_id,
            "team_id": team_id,
            "team_uid": resolve_team_uid(client, team_id, semester_id=team_sem_id),
            "scores_json": json.dumps(payload_scores),
            "remarks": body.remarks,
            "updated_at": updated_at_str,
        }
        if team_sem_id:
            insert_payload["semester_id"] = team_sem_id
        client.table("evaluation_drafts").insert(insert_payload).execute()
        
    return {"saved": True, "updated_at": updated_at_str}


@router.get("/evaluation/submission/{team_id}")
def get_submission(
    team_id: int,
    panel_id: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Secure receipt: immutable record after POST /evaluation/panel."""
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    cycle_id, _ = resolve_slot_cycle_id(client, panel_id, team_id)
    team_sem_id = None
    if cycle_id:
        team_sem_id = resolve_semester_id_from_cycle(client, cycle_id)
    if not team_sem_id:
        from app.db_helpers import resolve_team_semester_id
        team_sem_id = resolve_team_semester_id(client, team_id)

    query = client.table("evaluations").select("*").eq("panel_id", panel_id).eq("team_id", team_id)
    if team_sem_id:
        query = query.eq("semester_id", team_sem_id)
    res_eval = query.execute()
    row = res_eval.data[0] if res_eval.data else None
    if not row:
        raise HTTPException(status_code=404, detail="No submission for this team")
        
    res_team = client.table("teams").select("name").eq("id", team_id).execute()
    team_name = res_team.data[0]["name"] if res_team.data else ""
    
    scores = json.loads(row["scores_json"])
    required_keys = _get_required_score_keys(client, team_id, semester_id=team_sem_id, cycle_id=cycle_id)
    keys = {k: int(scores[k]) for k in required_keys if k in scores}
    max_total = _get_max_total(client, team_id, semester_id=team_sem_id, cycle_id=cycle_id)    
    sub_at = datetime.fromisoformat(row["submitted_at"].replace("Z", "+00:00"))
    return {
        "receipt_id": row["receipt_id"],
        "panel_id": row["panel_id"],
        "team_id": team_id,
        "team_name": team_name,
        "project_title": get_project_title(client, team_id),
        "submitted_at": sub_at.isoformat(),
        "scores": keys,
        "remarks": row["remarks"],
        "final_score_normalized": normalized_score(keys, max_total),
    }


@router.get("/evaluation/draft/{team_id}")
def get_draft(
    team_id: int,
    panel_id: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")

    cycle_id, _ = resolve_slot_cycle_id(client, panel_id, team_id)
    team_sem_id = None
    if cycle_id:
        team_sem_id = resolve_semester_id_from_cycle(client, cycle_id)
    if not team_sem_id:
        from app.db_helpers import resolve_team_semester_id
        team_sem_id = resolve_team_semester_id(client, team_id)

    query = client.table("evaluation_drafts").select("*").eq("panel_id", panel_id).eq("team_id", team_id)
    if team_sem_id:
        query = query.eq("semester_id", team_sem_id)
    res_draft = query.execute()
    row = res_draft.data[0] if res_draft.data else None
    if not row:
        return {"scores": {}, "remarks": ""}
    try:
        scores = json.loads(row["scores_json"])
    except json.JSONDecodeError:
        scores = {}
    return {"scores": scores, "remarks": row["remarks"]}


@router.post("/evaluation/panel", response_model=SubmitEvaluationResponse)
def submit_evaluation(
    body: SubmitEvaluationRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    require_panel_access(body.panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
        
    refresh_slot_statuses(client, body.panel_id)

    cycle_id, slot_id = resolve_slot_cycle_id(client, body.panel_id, body.team_id)

    now = datetime.now(timezone.utc)
    if not slot_allows_submission(client, body.panel_id, body.team_id, now, slot_id=slot_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Submission allowed only during the assigned slot window (time-bound control).",
        )

    team_sem_id = None
    if cycle_id:
        team_sem_id = resolve_semester_id_from_cycle(client, cycle_id)
    if not team_sem_id:
        from app.db_helpers import resolve_team_semester_id
        team_sem_id = resolve_team_semester_id(client, body.team_id)

    has_submitted = False
    if cycle_id:
        from app.db_helpers import resolve_team_string_id
        team_str = resolve_team_string_id(client, body.team_id, semester_id=team_sem_id)
        res_peval = client.table("presentation_evaluations")\
            .select("id")\
            .eq("cycle_id", cycle_id)\
            .eq("team_id", team_str)\
            .eq("evaluator_id", body.panel_id)\
            .execute()
        has_submitted = bool(res_peval.data)
    else:
        query = client.table("evaluations").select("id").eq("panel_id", body.panel_id).eq("team_id", body.team_id)
        if team_sem_id:
            query = query.eq("semester_id", team_sem_id)
        res_eval = query.execute()
        has_submitted = bool(res_eval.data)

    if has_submitted:
        raise HTTPException(status_code=400, detail="Evaluation already locked for this team")

    # Resolve the rubrics list
    rubrics_list = []
    if cycle_id:
        try:
            res_rubrics = client.table("presentation_rubrics")\
                .select("*")\
                .eq("cycle_id", cycle_id)\
                .order("id")\
                .execute()
            if res_rubrics.data:
                rubrics_list = res_rubrics.data
            else:
                # Fallback: check semester config
                res_sem = client.table("semester_config")\
                    .select("evaluation_parameters")\
                    .eq("id", team_sem_id)\
                    .execute()
                if res_sem.data and res_sem.data[0].get("evaluation_parameters"):
                    import uuid
                    params = res_sem.data[0]["evaluation_parameters"]
                    rubrics_to_insert = [
                        {
                            "id": str(uuid.uuid4()),
                            "cycle_id": cycle_id,
                            "criterion": p["name"],
                            "max_marks": p["max_marks"],
                            "weight": 1
                        }
                        for p in params
                    ]
                    client.table("presentation_rubrics").insert(rubrics_to_insert).execute()
                    res_rubrics_refetched = client.table("presentation_rubrics")\
                        .select("*")\
                        .eq("cycle_id", cycle_id)\
                        .order("id")\
                        .execute()
                    rubrics_list = res_rubrics_refetched.data or []
        except Exception as e:
            print(f"[evaluation] Error fetching/inserting rubrics: {e}")

    # Fallback to semester config directly if no cycle_id
    if not rubrics_list and team_sem_id:
        try:
            res_sem = client.table("semester_config")\
                .select("evaluation_parameters")\
                .eq("id", team_sem_id)\
                .execute()
            if res_sem.data and res_sem.data[0].get("evaluation_parameters"):
                params = res_sem.data[0]["evaluation_parameters"]
                rubrics_list = [
                    {"criterion": p["name"], "max_marks": p["max_marks"]}
                    for p in params
                ]
        except Exception as e:
            print(f"[evaluation] Error loading semester config fallback: {e}")

    # Fallback to global evaluation_parameters if still empty
    if not rubrics_list:
        try:
            res_params = client.table("evaluation_parameters").select("*").order("id").execute()
            if res_params.data:
                rubrics_list = [
                    {"criterion": r["criterion_name"], "max_marks": r["max_marks"]}
                    for r in res_params.data
                ]
        except Exception as e:
            print(f"[evaluation] Error fetching global parameters: {e}")

    # Final legacy fallback if absolutely nothing else worked
    if not rubrics_list:
        rubrics_list = [
            {"criterion": f"Criterion {i+1}", "max_marks": 10}
            for i in range(4)
        ]

    required_keys = tuple(f"q{i+1}" for i in range(len(rubrics_list)))

    for i, key in enumerate(required_keys):
        if key not in body.scores:
            raise HTTPException(status_code=422, detail=f"Missing score for {key}")
        val = body.scores[key]
        try:
            n = int(val)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"Invalid score for {key}")
        max_marks = rubrics_list[i]["max_marks"]
        if n < 0 or n > max_marks:
            raise HTTPException(status_code=422, detail=f"Score {key} must be 0–{max_marks}")

    if not (body.remarks and body.remarks.strip()):
        raise HTTPException(status_code=422, detail="Remarks required")

    int_scores = {k: int(body.scores[k]) for k in required_keys}
    max_total = sum(r["max_marks"] for r in rubrics_list)
    receipt = f"REC-{secrets.token_hex(5).upper()}"
    
    eval_payload = {
        "scores_json": json.dumps(int_scores),
        "remarks": body.remarks.strip(),
        "submitted_at": now.isoformat(),
        "receipt_id": receipt,
        "locked": True,
    }

    # Check if a legacy evaluations record already exists for this panel+team+semester.
    # The table has a unique constraint (panel_id, team_id, semester_id), so we must
    # update instead of insert if a record from a previous cycle already exists.
    check_q = client.table("evaluations").select("id").eq("panel_id", body.panel_id).eq("team_id", body.team_id)
    if team_sem_id:
        check_q = check_q.eq("semester_id", team_sem_id)
    existing_eval_res = check_q.execute()

    if existing_eval_res.data:
        # Update the existing legacy record with the latest scores
        existing_eval_id = existing_eval_res.data[0]["id"]
        client.table("evaluations").update(eval_payload).eq("id", existing_eval_id).execute()
    else:
        # First evaluation for this panel+team+semester — insert fresh
        from app.db_helpers import resolve_team_uid
        insert_payload = {
            "panel_id": body.panel_id,
            "team_id": body.team_id,
            "team_uid": resolve_team_uid(client, body.team_id, semester_id=team_sem_id),
            **eval_payload,
        }
        if team_sem_id:
            insert_payload["semester_id"] = team_sem_id
        client.table("evaluations").insert(insert_payload).execute()

    # ── Presentation Cycles Evaluation Insert ────────────────────────
    import uuid
    if cycle_id:
        try:
            if rubrics_list:
                from app.db_helpers import resolve_team_string_id, resolve_team_uid
                team_str = resolve_team_string_id(client, body.team_id, semester_id=team_sem_id)
                
                eval_id = str(uuid.uuid4())
                eval_insert = {
                    "id": eval_id,
                    "cycle_id": cycle_id,
                    "team_id": team_str,
                    "team_uid": resolve_team_uid(client, body.team_id, semester_id=team_sem_id),
                    "evaluator_id": body.panel_id,
                    "evaluator_type": "panel",
                    "total_score": normalized_score(int_scores, max_total),
                    "remarks": body.remarks.strip(),
                    "evaluated_at": now.isoformat()
                }
                client.table("presentation_evaluations").insert(eval_insert).execute()
                
                scores_inserts = []
                for i, r in enumerate(rubrics_list):
                    key = f"q{i+1}"
                    if key in int_scores:
                        scores_inserts.append({
                            "evaluation_id": eval_id,
                            "rubric_id": r["id"],
                            "awarded_marks": int_scores[key]
                        })
                if scores_inserts:
                    client.table("presentation_evaluation_scores").insert(scores_inserts).execute()
        except Exception as e:
            print(f"[evaluation] Error inserting into presentation tables: {e}")

    sync_team_results_from_evaluations(client, body.team_id, semester_id=team_sem_id)

    delete_query = client.table("evaluation_drafts").delete().eq("panel_id", body.panel_id).eq("team_id", body.team_id)
    if team_sem_id:
        delete_query = delete_query.eq("semester_id", team_sem_id)
    delete_query.execute()

    refresh_slot_statuses(client, body.panel_id)

    return SubmitEvaluationResponse(
        receipt_id=receipt,
        panel_id=body.panel_id,
        team_id=body.team_id,
        submitted_at=now,
        final_score_normalized=normalized_score(int_scores, max_total),
    )


@router.get("/evaluation/receipt/{team_id}")
def get_submission_receipt(
    team_id: int,
    panel_id: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Get secure submission receipt for a completed evaluation"""
    require_panel_access(panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
        
    cycle_id, _ = resolve_slot_cycle_id(client, panel_id, team_id)
    team_sem_id = None
    if cycle_id:
        team_sem_id = resolve_semester_id_from_cycle(client, cycle_id)
    if not team_sem_id:
        from app.db_helpers import resolve_team_semester_id
        team_sem_id = resolve_team_semester_id(client, team_id)

    query = client.table("evaluations").select("*").eq("team_id", team_id).eq("panel_id", panel_id)
    if team_sem_id:
        query = query.eq("semester_id", team_sem_id)
    res_eval = query.execute()
    evaluation = res_eval.data[0] if res_eval.data else None
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    res_team = client.table("teams").select("name").eq("id", team_id).execute()
    team_name = res_team.data[0]["name"] if res_team.data else "Unknown"
    
    res_proj = client.table("projects").select("title").eq("team_id", team_id).execute()
    proj_title = res_proj.data[0]["title"] if res_proj.data else "N/A"
    
    scores = json.loads(evaluation["scores_json"])
    
    res_params = client.table("evaluation_parameters").select("*").execute()
    parameters = res_params.data
    
    param_sections = {}
    for param in parameters:
        if param["category"] not in param_sections:
            param_sections[param["category"]] = []
        param_sections[param["category"]].append({
            "name": param["criterion_name"],
            "max_marks": param["max_marks"],
            "score": scores.get(f"q{param['id']}", 0)
        })
    
    sub_at = datetime.fromisoformat(evaluation["submitted_at"].replace("Z", "+00:00"))
    receipt_id = evaluation["receipt_id"]
    return {
        "receipt_id": receipt_id,
        "panel_id": evaluation["panel_id"],
        "team_id": evaluation["team_id"],
        "team_name": team_name,
        "project_title": proj_title,
        "submitted_at": sub_at.isoformat(),
        "total_score": sum(scores.values()),
        "remarks": evaluation["remarks"],
        "verified": evaluation["locked"],
        "semester_id": str(team_sem_id) if team_sem_id else None,
        "digital_signature": f"SHA256:{hashlib.sha256(receipt_id.encode('utf-8')).hexdigest()}",
        "blockchain_hash": f"0x{hashlib.sha256((receipt_id + evaluation['panel_id']).encode('utf-8')).hexdigest()}",
        "parameters": [
            {
                "category": category,
                "score": sum(item["score"] for item in items),
                "max_marks": sum(item["max_marks"] for item in items)
            }
            for category, items in param_sections.items()
        ]
    }


from pydantic import BaseModel

class ExtendSlotPayload(BaseModel):
    panel_id: str
    extend_minutes: int


@router.post("/evaluation/extend/{team_id}", response_model=EvaluationSessionResponse)
def extend_slot(
    team_id: int,
    body: ExtendSlotPayload,
    user: Annotated[dict, Depends(get_current_user)],
):
    require_panel_access(body.panel_id, user)
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
        
    cycle_id, slot_id = resolve_slot_cycle_id(client, body.panel_id, team_id)
    if not slot_id:
        raise HTTPException(status_code=404, detail="No active slot found for team")
        
    # Fetch active slot details from slots table
    res_slot = client.table("slots").select("*").eq("id", slot_id).execute()
    if not res_slot.data:
        raise HTTPException(status_code=404, detail="Slot not found")
    slot_row = res_slot.data[0]
    
    # Resolve the team's string ID
    team_sem_id = None
    if cycle_id:
        team_sem_id = resolve_semester_id_from_cycle(client, cycle_id)
    if not team_sem_id:
        from app.db_helpers import resolve_team_semester_id
        team_sem_id = resolve_team_semester_id(client, team_id)

    team_str = resolve_team_string_id(client, team_id, semester_id=team_sem_id)
    
    # Fetch the corresponding schedule slot
    res_sched = client.table("schedule_slots")\
        .select("*")\
        .eq("team", team_str)\
        .execute()
    
    target_sched_slot = None
    for row in res_sched.data or []:
        if row.get("time") == slot_row.get("slot_label"):
            target_sched_slot = row
            break
            
    if not target_sched_slot and res_sched.data:
        target_sched_slot = res_sched.data[0]
        
    if not target_sched_slot:
        raise HTTPException(status_code=404, detail="Corresponding schedule slot not found")
        
    target_date = target_sched_slot["date"]
    
    # Fetch all schedule slots on the same date to shift them
    res_all_sched = client.table("schedule_slots").select("*").eq("date", target_date).execute()
    all_sched_slots = res_all_sched.data or []
    
    # Helper parsing functions
    import re
    def parse_time_to_minutes(t_str: str) -> int:
        if not t_str:
            return 0
        match = re.match(r"^(\d+):(\d+)\s*(AM|PM)$", t_str.strip(), re.IGNORECASE)
        if not match:
            return 0
        h = int(match.group(1))
        m = int(match.group(2))
        ampm = match.group(3).upper()
        if ampm == "PM" and h != 12:
            h += 12
        if ampm == "AM" and h == 12:
            h = 0
        return h * 60 + m

    def minutes_to_time_str(mins: int) -> str:
        hh = (mins // 60) % 24
        mm = mins % 60
        ampm = "PM" if hh >= 12 else "AM"
        h12 = hh % 12
        if h12 == 0:
            h12 = 12
        return f"{h12}:{mm:02d} {ampm}"

    def parse_slot_time(time_str: str) -> tuple[int, int]:
        if not time_str:
            return 0, 0
        parts = [p.strip() for p in time_str.split("-")]
        if len(parts) < 2:
            return 0, 0
        return parse_time_to_minutes(parts[0]), parse_time_to_minutes(parts[1])
        
    orig_start, orig_end = parse_slot_time(target_sched_slot["time"])
    if orig_start == 0 and orig_end == 0:
        raise HTTPException(status_code=400, detail="Invalid schedule slot time format")
        
    new_end = orig_end + body.extend_minutes
    target_sched_slot["time"] = f"{minutes_to_time_str(orig_start)} - {minutes_to_time_str(new_end)}"
    
    # Update array
    updates = []
    updates.append({
        "id": target_sched_slot["id"],
        "time": target_sched_slot["time"]
    })
    
    # Propagate shift to other downstream slots sharing panel or room on same date
    target_panel = target_sched_slot.get("panel")
    target_room = target_sched_slot.get("room")
    is_online = target_room and target_room.lower() == "online"
    
    for s in all_sched_slots:
        if s["id"] == target_sched_slot["id"]:
            continue
            
        shares_panel = target_panel and s.get("panel") == target_panel
        shares_room = not is_online and target_room and s.get("room") == target_room
        
        if shares_panel or shares_room:
            s_start, s_end = parse_slot_time(s["time"])
            if s_start >= orig_end:
                new_s_start = s_start + body.extend_minutes
                new_s_end = s_end + body.extend_minutes
                s["time"] = f"{minutes_to_time_str(new_s_start)} - {minutes_to_time_str(new_s_end)}"
                updates.append({
                    "id": s["id"],
                    "time": s["time"]
                })
                
    # Batch update schedule_slots in database
    if updates:
        for u in updates:
            client.table("schedule_slots").update({"time": u["time"]}).eq("id", u["id"]).execute()
        
    # Instantly sync schedule_slots changes to slots table
    refresh_slot_statuses(client, body.panel_id, full_sync=True, force_sync=True)
    
    # Return updated evaluation session details
    return evaluation_session(team_id, body.panel_id, user)

