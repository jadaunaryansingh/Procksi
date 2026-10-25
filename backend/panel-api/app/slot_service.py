from datetime import datetime, timezone, timedelta
import threading
import time
from app.dtutil import utc
from app.cache import get_cached, set_value

# Stand-in enum
class SlotStatus:
    upcoming = "Upcoming"
    active = "Active"
    submitted = "Submitted"
    missed = "Missed"

# Global in-memory cache and lock to prevent concurrent/redundant sync writes per panel
_last_refresh_times = {}
_refresh_lock = threading.Lock()

def refresh_slot_statuses(client, panel_id: str, *, full_sync: bool = True, force_sync: bool = False) -> None:
    """Derive Upcoming / Active / Submitted / Missed from time windows and evaluations.
    When full_sync=True, also syncs schedule_slots → slots (throttled to once per 60s per panel).
    Status-only refresh is throttled to once per 20s per panel.
    When force_sync=True, throttle checks are bypassed."""
    now_ts = time.time()
    
    full_cache_key = f"{panel_id}:full"
    status_cache_key = f"{panel_id}:status"
    
    run_full = False
    run_status = False
    
    with _refresh_lock:
        last_full = _last_refresh_times.get(full_cache_key, 0)
        last_status = _last_refresh_times.get(status_cache_key, 0)
        
        if force_sync:
            run_full = True
            run_status = True
            _last_refresh_times[full_cache_key] = now_ts
            _last_refresh_times[status_cache_key] = now_ts
        elif full_sync:
            if now_ts - last_full >= 60:
                run_full = True
                _last_refresh_times[full_cache_key] = now_ts
                _last_refresh_times[status_cache_key] = now_ts
            elif now_ts - last_status >= 20:
                run_status = True
                _last_refresh_times[status_cache_key] = now_ts
        else:
            if now_ts - last_status >= 20:
                run_status = True
                _last_refresh_times[status_cache_key] = now_ts

    if not run_full and not run_status:
        return

    if run_status and not run_full:
        _apply_status_only(client, panel_id)
        return

    from app.db_helpers import to_numeric_id, get_slot_windows, resolve_team_uid, semester_id_from_cycle
    
    # 1. Fetch matching panel names and IDs
    from app.db_helpers import get_matching_panel_identifiers
    identifiers = get_matching_panel_identifiers(client, panel_id)
        
    # 2. Query schedule_slots for this panel (filtered by active semester)
    try:
        res_sched = client.table("schedule_slots").select("*").in_("panel", identifiers).execute()
        res_sems = client.table("semester_config").select("id").eq("is_active", True).execute()
        active_sem_ids = {s["id"] for s in res_sems.data or []}
        sched_slots = [ss for ss in (res_sched.data or []) if ss.get("semester_id") in active_sem_ids]
    except Exception as e:
        print(f"Error fetching schedule_slots: {e}")
        sched_slots = []
        
    if not sched_slots:
        # If no slots in schedule, clean up non-submitted slots in slots table and return
        try:
            res_slots = client.table("slots").select("id, status").eq("panel_id", panel_id).execute()
            current_slots = res_slots.data or []
            delete_ids = [s["id"] for s in current_slots if s["status"] != SlotStatus.submitted]
            if delete_ids:
                client.table("slots").delete().in_("id", delete_ids).execute()
        except Exception as e:
            print(f"Error cleaning slots when schedule is empty: {e}")
        return

    # 3. Parse sched_slots into structured list
    sched_items = []
    sched_team_strs = []
    sched_team_ids = set()
    unique_teams = {}
    
    for ss in sched_slots:
        team_str = ss["team"]
        team_id = to_numeric_id(team_str)
        if not team_id:
            continue
        sched_team_ids.add(team_id)
        sched_team_strs.append(team_str)
        unique_teams[team_id] = team_str
        
        ws, we = get_slot_windows(ss["date"], ss["time"])
        sched_items.append({
            "team_id": team_id,
            "team_name": team_str,
            "slot_label": ss["time"],
            "window_start": ws,
            "window_end": we,
            "venue": ss["room"],
            "cycle_id": ss.get("cycle_id"),
            "meet_link": ss.get("meetLink") or ss.get("meet_link"),
            # schedule_slots.team is the cohort-correct teams_validation.id slug;
            # carry its semester so team_uid resolves within the right B.Tech year
            # (bare team numbers collide across the concurrently-active cohorts).
            "semester_id": ss.get("semester_id"),
        })
        
    # 4. Batch fetch project titles from teams_validation
    project_titles = {}
    try:
        if sched_team_strs:
            res_team_val = client.table("teams_validation").select("id, title").in_("id", list(set(sched_team_strs))).execute()
            project_titles = {row["id"]: row["title"] for row in (res_team_val.data or []) if row.get("title")}
    except Exception as e:
        print(f"Error batch fetching project titles: {e}")
        
    # 5. Bulk upsert teams
    try:
        teams_data = [{"id": tid, "name": name} for tid, name in unique_teams.items()]
        if teams_data:
            client.table("teams").upsert(teams_data, on_conflict="id").execute()
    except Exception as e:
        print(f"Error bulk upserting teams: {e}")
        
    # 6. Bulk upsert projects
    try:
        projects_data = []
        for tid, name in unique_teams.items():
            title = project_titles.get(name) or name
            projects_data.append({"team_id": tid, "title": title})
        if projects_data:
            client.table("projects").upsert(projects_data, on_conflict="team_id").execute()
    except Exception as e:
        print(f"Error bulk upserting projects: {e}")
            # 7. Batch fetch existing slots for this panel
    existing_slots_map = {}
    try:
        res_slots = client.table("slots").select("*").eq("panel_id", panel_id).execute()
        current_slots = res_slots.data or []
        for s in current_slots:
            existing_slots_map.setdefault((s["team_id"], s.get("cycle_id")), []).append(s)
    except Exception as e:
        print(f"Error batch fetching slots: {e}")
        current_slots = []
        
    # 8. Prepare slots inserts, updates & deletes
    slots_to_insert = []
    slots_to_update = []
    slot_ids_to_delete = []
    now = datetime.now(timezone.utc)
    
    for item in sched_items:
        tid = item["team_id"]
        cid = item.get("cycle_id")
        ws, we = item["window_start"], item["window_end"]
        # Canonical cohort-scoped team link. Resolved from the schedule row's own
        # semester (falls back to cycle -> semester), never from the bare number.
        item_sem_id = item.get("semester_id") or semester_id_from_cycle(client, cid)
        team_uid = resolve_team_uid(client, tid, semester_id=item_sem_id) if item_sem_id else None

        slots_exist = existing_slots_map.get((tid, cid), [])
        if not slots_exist:
            # Create new slot payload
            slots_to_insert.append({
                "panel_id": panel_id,
                "team_id": tid,
                "team_uid": team_uid,
                "slot_label": item["slot_label"],
                "window_start": ws.isoformat(),
                "window_end": we.isoformat(),
                "venue": item["venue"],
                "status": SlotStatus.upcoming,
                "cycle_id": cid,
                "meet_link": item.get("meet_link"),
            })
        else:
            primary_slot = slots_exist[0]
            ws_exist = datetime.fromisoformat(primary_slot["window_start"].replace("Z", "+00:00"))
            we_exist = datetime.fromisoformat(primary_slot["window_end"].replace("Z", "+00:00"))
            time_changed = abs((ws_exist - ws).total_seconds()) > 5 or abs((we_exist - we).total_seconds()) > 5
            
            # Check if meet_link has changed
            meet_link_changed = primary_slot.get("meet_link") != item.get("meet_link")

            # Canonical link drifted (or was never set / set cross-cohort)
            team_uid_changed = bool(team_uid) and primary_slot.get("team_uid") != team_uid

            # Update primary slot if values differ
            if (primary_slot["slot_label"] != item["slot_label"] or
                primary_slot["venue"] != item["venue"] or
                meet_link_changed or
                team_uid_changed or
                time_changed):

                updated_status = primary_slot["status"]
                if time_changed and updated_status == SlotStatus.missed and ws > now:
                    updated_status = SlotStatus.upcoming
                
                update_row = {
                    "id": primary_slot["id"],
                    "panel_id": panel_id,
                    "team_id": tid,
                    "slot_label": item["slot_label"],
                    "window_start": ws.isoformat(),
                    "window_end": we.isoformat(),
                    "venue": item["venue"],
                    "status": updated_status,
                    "cycle_id": cid,
                    "meet_link": item.get("meet_link") if item.get("meet_link") is not None else primary_slot.get("meet_link"),
                }
                # Heal the canonical link on any schedule edit (older rows may hold
                # a cross-cohort team_uid from before this resolver was scoped).
                if team_uid and primary_slot.get("team_uid") != team_uid:
                    update_row["team_uid"] = team_uid
                slots_to_update.append(update_row)
                
            # Queue duplicate slots for deletion
            for extra_slot in slots_exist[1:]:
                if extra_slot["status"] != SlotStatus.submitted:
                    slot_ids_to_delete.append(extra_slot["id"])
                    
    # Queue slots that are no longer in schedule for deletion
    sched_keys = {(item["team_id"], item.get("cycle_id")) for item in sched_items}
    for s in current_slots:
        slot_key = (s["team_id"], s.get("cycle_id"))
        if slot_key not in sched_keys and s["status"] != SlotStatus.submitted:
            slot_ids_to_delete.append(s["id"])
            
    # 9. Execute slots inserts, updates & deletes in bulk
    try:
        if slots_to_insert:
            client.table("slots").insert(slots_to_insert).execute()
    except Exception as e:
        print(f"Error bulk inserting slots: {e}")
        
    try:
        if slots_to_update:
            for s in slots_to_update:
                payload = {k: v for k, v in s.items() if k != "id"}
                client.table("slots").update(payload).eq("id", s["id"]).execute()
    except Exception as e:
        print(f"Error bulk updating slots: {e}")
        
    try:
        if slot_ids_to_delete:
            client.table("slots").delete().in_("id", slot_ids_to_delete).execute()
    except Exception as e:
        print(f"Error bulk deleting slots: {e}")
 
    _apply_status_only(client, panel_id)


def _apply_status_only(client, panel_id: str) -> None:
    """Lightweight pass: update slot statuses from evaluations + clock only.
    Results of the DB fetch are cached per-panel for 15s to avoid redundant
    queries when multiple endpoints run on the same request."""
    now = datetime.now(timezone.utc)

    def _fetch_panel_status_data():
        slots_data = []
        submitted_ids = set()
        try:
            res_slots = client.table("slots").select("*").eq("panel_id", panel_id).order("window_start").execute()
            slots_data = res_slots.data or []
            
            # Query all presentation evaluations (cycle-based)
            res_pevals = client.table("presentation_evaluations")\
                .select("team_id, cycle_id")\
                .execute()
            from app.db_helpers import to_numeric_id
            for pe in (res_pevals.data or []):
                num_id = to_numeric_id(pe["team_id"])
                if num_id:
                    submitted_ids.add((num_id, pe["cycle_id"]))
            
            # Query legacy evaluations
            res_evals = client.table("evaluations").select("team_id").eq("panel_id", panel_id).execute()
            for e in (res_evals.data or []):
                submitted_ids.add((e["team_id"], None))
        except Exception as e:
            print(f"Error fetching slots/evaluations for status refresh: {e}")
        return (slots_data, submitted_ids)

    slots, submitted_team_ids = get_cached(
        f"panel_status_data:{panel_id}", 15.0, _fetch_panel_status_data
    )

    # Also check results table (full-table scan, cached globally for 30s) — only as fallback when no active cycles exist
    try:
        from app.db_helpers import to_numeric_id, get_active_team_string_ids

        res_sems = client.table("semester_config").select("id").eq("is_active", True).execute()
        active_sem_ids = {s["id"] for s in res_sems.data or []}
        active_cycle_ids = []
        if active_sem_ids:
            res_cycles = client.table("presentation_cycles")\
                .select("id")\
                .in_("semester_id", list(active_sem_ids))\
                .eq("status", "active")\
                .execute()
            active_cycle_ids = [c["id"] for c in res_cycles.data or []]

        if not active_cycle_ids:
            def _fetch_results():
                res = client.table("results").select("team, midMarks, proposalMarks, finalMarks").execute()
                return res.data or []

            results_rows = get_cached("results_table", 30.0, _fetch_results)
            active_team_string_ids = get_active_team_string_ids(client)
            extra_ids = set()
            for r in results_rows:
                if r.get("midMarks") is not None or r.get("proposalMarks") is not None or r.get("finalMarks") is not None:
                    if r.get("team") in active_team_string_ids:
                        tid = to_numeric_id(r["team"])
                        if tid:
                            extra_ids.add((tid, None))
            submitted_team_ids = submitted_team_ids | extra_ids
    except Exception as e:
        print(f"Error checking results table for submitted slots in _apply_status_only: {e}")

    status_updates = []
    for s in slots:
        ws_val = datetime.fromisoformat(s["window_start"].replace("Z", "+00:00"))
        we_val = datetime.fromisoformat(s["window_end"].replace("Z", "+00:00"))
        ws, we = utc(ws_val), utc(we_val)

        old_status = s["status"]
        slot_cycle_id = s.get("cycle_id")
        is_submitted = (s["team_id"], slot_cycle_id) in submitted_team_ids

        if is_submitted:
            new_status = SlotStatus.submitted
        elif now > we:
            new_status = SlotStatus.missed
        elif ws <= now <= we:
            new_status = SlotStatus.active
        else:
            new_status = SlotStatus.upcoming

        if (not old_status or old_status.lower() != new_status.lower()) and s.get("panel_id"):
            status_updates.append({**s, "status": new_status})

    if status_updates:
        try:
            for s in status_updates:
                payload = {k: v for k, v in s.items() if k != "id"}
                client.table("slots").update(payload).eq("id", s["id"]).execute()
            # Invalidate the per-panel status data cache so next read sees fresh statuses
            from app.cache import invalidate
            invalidate(f"panel_status_data:{panel_id}")
        except Exception as e:
            print(f"Error batch updating slot statuses: {e}")


def slot_allows_submission(client, panel_id: str, team_id: int, now: datetime | None = None, slot_id: str | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if slot_id:
        res_slot = client.table("slots").select("*").eq("id", slot_id).execute()
    else:
        res_slot = client.table("slots").select("*").eq("panel_id", panel_id).eq("team_id", team_id).execute()
    if not res_slot.data:
        return False
    s = res_slot.data[0]
    
    from app.db_helpers import resolve_team_semester_id
    team_sem_id = resolve_team_semester_id(client, team_id)
    
    res_sems = client.table("semester_config").select("id").eq("is_active", True).execute()
    active_sem_ids = [sem["id"] for sem in res_sems.data or []]
    
    if team_sem_id not in active_sem_ids:
        return False
    
    # Check if this cycle is already evaluated
    slot_cycle_id = s.get("cycle_id")
    if slot_cycle_id:
        from app.db_helpers import resolve_team_string_id
        team_str = resolve_team_string_id(client, team_id)
        res_eval = client.table("presentation_evaluations")\
            .select("id")\
            .eq("cycle_id", slot_cycle_id)\
            .eq("team_id", team_str)\
            .eq("evaluator_id", panel_id)\
            .execute()
        if res_eval.data:
            return False
    else:
        res_eval = client.table("evaluations").select("id").eq("panel_id", panel_id).eq("team_id", team_id).eq("semester_id", team_sem_id).execute()
        if res_eval.data:
            return False
        
    ws_val = datetime.fromisoformat(s["window_start"].replace("Z", "+00:00"))
    we_val = datetime.fromisoformat(s["window_end"].replace("Z", "+00:00"))
    ws, we = utc(ws_val), utc(we_val)
    
    start_buffer = timedelta(hours=2)
    end_buffer = timedelta(seconds=0)
    return (ws - start_buffer) <= now <= (we + end_buffer)



def normalized_score(scores: dict[str, int], max_total: int = 40) -> int:
    """Map sum of section scores to 0–100.
    max_total should equal the sum of max_marks across all evaluation_parameters rows.
    Falls back to the legacy 40-point total (4 × 10) when not provided."""
    if not max_total:
        max_total = 40
    total = sum(scores.values())
    return round((total / max_total) * 100)
