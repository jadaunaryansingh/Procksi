from datetime import datetime, time, timedelta, timezone
import re
from app.cache import get_cached, get_or_set, set_value, invalidate_prefix

def to_numeric_id(team_str: str) -> int:
    try:
        if not team_str:
            return 0
        s = str(team_str).strip()

        def parse_with_leading_zero(num_str):
            val = int(num_str)
            if num_str.startswith("0") and val != 0:
                return 10000 + val
            return val

        # 1. Check for -T\d+ suffix (case insensitive)
        t_match = re.search(r"-T(\d+)", s, re.IGNORECASE)
        if t_match:
            return parse_with_leading_zero(t_match.group(1))

        # 2. Check for trailing digits after a hyphen (e.g., TEAM-11)
        last_dash = re.search(r"-(\d+)$", s)
        if last_dash:
            return parse_with_leading_zero(last_dash.group(1))

        # 3. Fallback: match the last digit sequence
        nums = re.findall(r"\d+", s)
        if nums:
            return parse_with_leading_zero(nums[-1])

        return 0
    except Exception:
        return 0


def from_numeric_id(team_id: int) -> str:
    if team_id >= 10000:
        return f"TEAM-{team_id - 10000:03d}"
    return f"TEAM-{team_id}"


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def semester_id_from_cycle(client, cycle_id) -> str | None:
    """presentation_cycles.id -> semester_id. Cached 1h (cycles don't move semesters)."""
    if not cycle_id:
        return None

    def _fetch():
        try:
            res = client.table("presentation_cycles").select("semester_id").eq("id", str(cycle_id)).execute()
            return res.data[0].get("semester_id") if res.data else None
        except Exception as e:
            print(f"semester_id_from_cycle failed for {cycle_id}: {e}")
            return None

    return get_cached(f"cycle_sem:{cycle_id}", 3600.0, _fetch)


def _semester_team_uid_map(client, semester_id: str) -> dict:
    """Per-cohort resolver map for one semester:  key -> teams_validation.uid.

    Keys held for every team in the semester:
      * the exact teams_validation.id slug (str)
      * the slug's numeric id via to_numeric_id(...) (int) — this mirrors exactly
        how panel-api derives the integer team_id from schedule_slots.team, so it
        is the primary inversion path
      * teams_validation.team_number (int) — secondary, only if that int isn't
        already claimed by a slug-suffix above

    Scoped to one semester, so it is unambiguous even though bare team
    numbers / slug suffixes are NOT unique across the concurrently-active
    B.Tech years. Cached 10 min per semester."""

    def _fetch():
        m: dict = {}
        try:
            res = client.table("teams_validation").select("id, uid, team_number").eq("semester_id", semester_id).execute()
            rows = res.data or []
        except Exception as e:
            print(f"_semester_team_uid_map fetch failed for {semester_id}: {e}")
            return m
        # pass 1 — slug + slug-suffix number (primary)
        for r in rows:
            uid = r.get("uid")
            tid = r.get("id")
            if not uid or not tid:
                continue
            m[str(tid)] = uid
            num = to_numeric_id(tid)
            if num:
                m.setdefault(num, uid)
        # pass 2 — team_number (only where no slug suffix already claimed it)
        for r in rows:
            uid = r.get("uid")
            tn = r.get("team_number")
            if not uid or tn is None:
                continue
            try:
                m.setdefault(int(tn), uid)
            except (TypeError, ValueError):
                pass
        return m

    return get_cached(f"team_uid_sem_map:{semester_id}", 600.0, _fetch)


def resolve_team_uid(client, team_id, semester_id: str | None = None) -> str | None:
    """Canonical team identity: legacy int / teams_validation.id slug / uuid ->
    teams_validation.uid. Returns None if unresolvable (never a guessed number).

    Pass semester_id whenever it is known (evaluation / results / slot writes all
    have it): resolution then happens **within that cohort only**, which is the
    reliable path — team numbers and slug suffixes T1..T125 exist in two
    concurrently-active B.Tech years at once, and team_uid_map can only ever
    point at one of them. Without semester_id the legacy cross-cohort map is used
    as a best effort (display-only callers)."""
    if team_id is None:
        return None
    s = str(team_id).strip()
    if not s:
        return None
    if _UUID_RE.match(s):
        return s

    if semester_id:
        sem_map = _semester_team_uid_map(client, semester_id)
        if s in sem_map:
            return sem_map[s]
        num = to_numeric_id(s)
        if num and num in sem_map:
            return sem_map[num]
        # A semester context was supplied but the team isn't in it. Do NOT fall
        # through to the cross-cohort map — that is exactly the misattribution
        # bug this guard exists to prevent.
        return None

    def _fetch():
        m = {}
        try:
            rows = client.table("team_uid_map").select("old_int_id, uid").execute().data or []
            for r in rows:
                m[str(r["old_int_id"])] = r["uid"]
        except Exception as e:
            print(f"resolve_team_uid: team_uid_map fetch failed: {e}")
        try:
            rows = client.table("teams_validation").select("id, uid").execute().data or []
            for r in rows:
                if r.get("id") and r.get("uid"):
                    m[str(r["id"])] = r["uid"]
        except Exception as e:
            print(f"resolve_team_uid: teams_validation fetch failed: {e}")
        return m

    mapping = get_cached("team_uid_map_all", 600.0, _fetch)
    return mapping.get(s)


def resolve_team_string_id(client, team_id: int, semester_id: str | None = None) -> str:
    """Resolve numeric team ID to the actual string ID in teams_validation table, prioritizing active semesters."""
    if semester_id:
        def _fetch_sem_map():
            try:
                res = client.table("teams_validation").select("id").eq("semester_id", semester_id).execute()
                mapping = {}
                for row in res.data or []:
                    tid = row.get("id")
                    if tid:
                        num_id = to_numeric_id(tid)
                        mapping[num_id] = tid
                return mapping
            except Exception as e:
                print(f"Error building team semester map for {semester_id}: {e}")
                return {}
        
        sem_mapping = get_cached(f"team_sem_map:{semester_id}", 600.0, _fetch_sem_map)
        if sem_mapping and team_id in sem_mapping:
            return sem_mapping[team_id]

    def _fetch_map():
        try:
            res_sems = client.table("semester_config").select("id").eq("is_active", True).execute()
            active_sem_ids = {s["id"] for s in res_sems.data or []}
            
            res = client.table("teams_validation").select("id, semester_id").execute()
            mapping = {}
            for row in res.data or []:
                tid = row.get("id")
                sem_id = row.get("semester_id")
                if tid:
                    num_id = to_numeric_id(tid)
                    is_active = sem_id in active_sem_ids
                    existing = mapping.get(num_id)
                    if not existing or (is_active and not existing["is_active"]) or (is_active == existing["is_active"] and len(tid) > len(existing["tid"])):
                        mapping[num_id] = {"tid": tid, "is_active": is_active}
            return {k: v["tid"] for k, v in mapping.items()}
        except Exception as e:
            print(f"Error building team string ID map in db_helpers: {e}")
            return {}

    # Cache for 10 minutes (team configurations change rarely)
    mapping = get_cached("team_string_id_map", 600.0, _fetch_map)
    if mapping and team_id in mapping:
        return mapping[team_id]
    return from_numeric_id(team_id)

def parse_time_part(time_str: str) -> time:
    clean = time_str.strip().lower()
    ampm = "pm" in clean or "am" in clean
    pm = "pm" in clean
    parts = re.sub(r"[ap]m", "", clean).strip().split(":")
    h = int(parts[0]) if parts[0] else 0
    m = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    if ampm:
        if pm and h != 12:
            h += 12
        if not pm and h == 12:
            h = 0
    return time(h, m)

def get_slot_windows(date_str: str, time_range: str):
    try:
        parts = time_range.split("-")
        start_time = parse_time_part(parts[0])
        end_time = parse_time_part(parts[1]) if len(parts) > 1 else start_time
        base_date = datetime.strptime(date_str, "%Y-%m-%d")
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        start_dt = datetime.combine(base_date.date(), start_time).replace(tzinfo=ist_tz).astimezone(timezone.utc)
        end_dt = datetime.combine(base_date.date(), end_time).replace(tzinfo=ist_tz).astimezone(timezone.utc)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        return start_dt, end_dt
    except Exception:
        now = datetime.now(timezone.utc)
        return now, now + timedelta(minutes=30)

def get_matching_panel_identifiers(client, panel_id: str) -> list[str]:
    """Find all names and IDs in the panels table that are equivalent to panel_id or its name,
    ignoring case, hyphens, and common honorifics (like 'sir').
    """
    def normalize(val: str) -> str:
        s = str(val).strip().lower().replace("-", " ")
        s = re.sub(r"\b(dr|mr|ms|mrs|prof|sir)\b", "", s)
        return "".join(s.split())

    norm_target = normalize(panel_id)
    
    # Also resolve name if possible
    res_panel = client.table("panels").select("name").eq("id", panel_id).execute()
    if res_panel.data and res_panel.data[0].get("name"):
        norm_name = normalize(res_panel.data[0]["name"])
    else:
        norm_name = norm_target

    identifiers = {panel_id}
    res_panel_name = res_panel.data[0]["name"] if res_panel.data else None
    if res_panel_name:
        identifiers.add(res_panel_name)

    try:
        res_all = client.table("panels").select("id, name").execute()
        for p in res_all.data or []:
            p_id = p.get("id")
            p_name = p.get("name")
            if p_id and (normalize(p_id) == norm_target or normalize(p_id) == norm_name):
                identifiers.add(p_id)
                if p_name:
                    identifiers.add(p_name)
            if p_name and (normalize(p_name) == norm_target or normalize(p_name) == norm_name):
                identifiers.add(p_name)
                if p_id:
                    identifiers.add(p_id)
    except Exception as e:
        print(f"Error fetching all panels for fuzzy matching: {e}")

    return list(identifiers)


def fetch_slots_from_schedule_slots(client, panel_id: str) -> list[dict]:
    # 1. Get all matching panel names and IDs (e.g. 'Preshit Desai Sir', 'PRESHIT-DESAI', etc.)
    identifiers = get_matching_panel_identifiers(client, panel_id)
    
    # 2. Query schedule_slots
    res_slots = client.table("schedule_slots").select("*").in_("panel", identifiers).execute()
    schedule_rows = res_slots.data or []
    
    # 3. Get evaluations to determine if submitted
    try:
        res_sems = client.table("semester_config").select("id").eq("is_active", True).execute()
        active_sem_ids = [s["id"] for s in res_sems.data or []]
    except Exception as e:
        print(f"Error fetching active semester IDs in db_helpers: {e}")
        active_sem_ids = []

    try:
        if active_sem_ids:
            res_evals = client.table("evaluations").select("team_id").eq("panel_id", panel_id).in_("semester_id", active_sem_ids).execute()
        else:
            res_evals = client.table("evaluations").select("team_id").eq("panel_id", panel_id).execute()
        submitted_team_ids = {row["team_id"] for row in res_evals.data}
    except Exception as e:
        print(f"Error fetching evaluations in db_helpers: {e}")
        submitted_team_ids = set()

    try:
        def _fetch_results():
            res = client.table("results").select("team, midMarks, proposalMarks, finalMarks").execute()
            return res.data or []
        results_rows = get_cached("results_table", 30.0, _fetch_results)
        active_team_string_ids = get_active_team_string_ids(client)
        for r in results_rows:
            if r.get("midMarks") is not None or r.get("proposalMarks") is not None or r.get("finalMarks") is not None:
                if r.get("team") in active_team_string_ids:
                    tid = to_numeric_id(r["team"])
                    if tid:
                        submitted_team_ids.add(tid)
    except Exception as e:
        print(f"Error checking results table for submitted slots in db_helpers: {e}")
    
    now = datetime.now(timezone.utc)
    slots = []
    for row in schedule_rows:
        team_str = row["team"]
        team_id = to_numeric_id(team_str)
        ws, we = get_slot_windows(row["date"], row["time"])
        
        # Determine status
        if team_id in submitted_team_ids:
            status = "Submitted"
        elif now > we:
            status = "Missed"
        elif ws <= now <= we:
            status = "Active"
        else:
            status = "Upcoming"
            
        slots.append({
            "id": row["id"],
            "panel_id": panel_id,
            "team_id": team_id,
            "slot_label": row["time"],
            "window_start": ws.isoformat(),
            "window_end": we.isoformat(),
            "venue": row["room"],
            "status": status,
        })
    return slots

def fetch_teams_from_teams_validation(client) -> list[dict]:
    res_teams = client.table("teams_validation").select("*").execute()
    teams = []
    for t in res_teams.data or []:
        team_id = to_numeric_id(t["id"])
        teams.append({
            "id": team_id,
            "name": t["id"],  # E.g. "TEAM-3"
            "project_title": t.get("title") or t.get("description") or t.get("id"),
        })
    return teams

def get_project_title(client, team_id: int) -> str | None:
    def _fetch():
        uid = resolve_team_uid(client, team_id)
        if uid:
            res = client.table("teams_validation").select("title").eq("uid", uid).execute()
            if res.data:
                return res.data[0]["title"]
        # legacy fallback: numeric -> slug -> teams_validation.id
        res = client.table("teams_validation").select("title").eq("id", resolve_team_string_id(client, team_id)).execute()
        return res.data[0]["title"] if res.data else None
    # Increased TTL: project titles don't change during evaluations
    return get_cached(f"project_title:{team_id}", 300.0, _fetch)


def get_batch_project_titles(client, team_ids: list[int]) -> dict[int, str | None]:
    """Fetch project titles for multiple teams in a single DB call, using the public cache API."""
    if not team_ids:
        return {}

    result: dict[int, str | None] = {}
    missing: list[int] = []

    for tid in team_ids:
        hit, val = _peek_project_title(tid)
        if hit:
            result[tid] = val
        else:
            missing.append(tid)

    if missing:
        # canonical: numeric id -> uid via crosswalk -> teams_validation.uid
        uid_by_tid = {tid: resolve_team_uid(client, tid) for tid in missing}
        uids = [u for u in uid_by_tid.values() if u]
        title_by_uid: dict[str, str | None] = {}
        if uids:
            res = client.table("teams_validation").select("uid, title").in_("uid", uids).execute()
            title_by_uid = {row["uid"]: row.get("title") for row in (res.data or [])}

        # legacy fallback for any tid that didn't resolve to a uid
        unresolved = [tid for tid in missing if not uid_by_tid.get(tid)]
        title_by_num: dict[int, str | None] = {}
        if unresolved:
            team_strs = [resolve_team_string_id(client, tid) for tid in unresolved]
            res = client.table("teams_validation").select("id, title").in_("id", team_strs).execute()
            title_by_num = {to_numeric_id(row["id"]): row.get("title") for row in (res.data or [])}

        for tid in missing:
            u = uid_by_tid.get(tid)
            val = title_by_uid.get(u) if u else title_by_num.get(tid)
            set_value(f"project_title:{tid}", val)
            result[tid] = val

    return result


def _peek_project_title(team_id: int) -> tuple[bool, str | None]:
    """Check cache for a project title without calling factory. TTL=300s."""
    from app.cache import peek
    return peek(f"project_title:{team_id}", 300.0)


def read_stored_meet_link(row: dict) -> str | None:
    for key in ("meetLink", "meet_link", "meetlink"):
        val = row.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return None


def resolve_meet_link(row: dict, *, auto_generate: bool = True) -> str | None:
    return read_stored_meet_link(row)


def get_meet_link_map(client, panel_id: str) -> dict[int, str]:
    """Map team_id → meet link, cached per panel for 120 seconds (links are static)."""
    def _fetch():
        return _compute_meet_link_map(client, panel_id)
    return get_cached(f"meet_link_map:{panel_id}", 120.0, _fetch)

def _compute_meet_link_map(client, panel_id: str) -> dict:
    """Map (team_id, cycle_id) and team_id → meet link for all schedule rows belonging to this panel."""
    identifiers = get_matching_panel_identifiers(client, panel_id)

    res_slots = client.table("slots").select("team_id, cycle_id").eq("panel_id", panel_id).execute()
    panel_team_ids = {s["team_id"] for s in (res_slots.data or [])}

    rows: list[dict] = []

    try:
        res_sched = client.table("schedule_slots").select("*").in_("panel", identifiers).execute()
        if res_sched.data:
            rows.extend(res_sched.data)
    except Exception as e:
        print(f"Error fetching schedule_slots for meet links: {e}")

    # Fallback: match by team id when panel name in schedule_slots differs
    try:
        team_strs = list({resolve_team_string_id(client, tid) for tid in panel_team_ids})
        if team_strs:
            res_by_team = client.table("schedule_slots").select("*").in_("team", team_strs).execute()
            if res_by_team.data:
                # Add rows that we haven't fetched yet
                existing_ids = {r["id"] for r in rows}
                for r in res_by_team.data:
                    if r["id"] not in existing_ids:
                        rows.append(r)
    except Exception as e:
        print(f"Error fetching schedule_slots by team for meet links: {e}")

    link_map = {}
    for row in rows:
        tid = to_numeric_id(row.get("team", ""))
        if not tid:
            continue
        link = resolve_meet_link(row)
        if link:
            cycle_id = row.get("cycle_id")
            # Map by f"{team_id}_{cycle_id}"
            link_map[f"{tid}_{cycle_id}"] = link
            # Also map by team_id as fallback
            if tid not in link_map:
                link_map[tid] = link

    # Fallback: read stored meet_link from panel slots when schedule_slots has no matching row
    for slot in res_slots.data or []:
        tid = slot["team_id"]
        cycle_id = slot.get("cycle_id")
        key = f"{tid}_{cycle_id}"
        if key in link_map:
            continue
        stored_link = slot.get("meet_link")
        if stored_link and str(stored_link).strip():
            link_map[key] = str(stored_link).strip()
            if tid not in link_map:
                link_map[tid] = str(stored_link).strip()

    return link_map


def resolve_results_team_key(client, team_id: int, semester_id: str | None = None) -> str:
    """Find the results.team key for a numeric panel team id. Canonical path is
    team_uid -> teams_validation.id; the numeric scan is a legacy fallback."""
    uid = resolve_team_uid(client, team_id, semester_id=semester_id)

    # 1. an existing results row already tied to this uid wins (keeps upserts stable)
    if uid:
        try:
            r = client.table("results").select("team, semester_id").eq("team_uid", uid).execute()
            for row in r.data or []:
                if not semester_id or row.get("semester_id") == semester_id:
                    return row["team"]
        except Exception as e:
            print(f"Error resolving results team key by uid: {e}")
        # 2. no results row yet -> use the canonical teams_validation.id slug
        try:
            tv = client.table("teams_validation").select("id").eq("uid", uid).execute()
            if tv.data and tv.data[0].get("id"):
                return tv.data[0]["id"]
        except Exception as e:
            print(f"Error resolving teams_validation.id by uid: {e}")

    # 3. legacy: numeric scan of results, then teams.name, then slug map
    try:
        res_all = client.table("results").select("team, semester_id").execute()
        for row in res_all.data or []:
            if to_numeric_id(row.get("team", "")) == team_id:
                if not semester_id or row.get("semester_id") == semester_id:
                    return row["team"]
    except Exception as e:
        print(f"Error resolving results team key: {e}")

    try:
        res_team = client.table("teams").select("name").eq("id", team_id).execute()
        if res_team.data and res_team.data[0].get("name"):
            return res_team.data[0]["name"]
    except Exception as e:
        print(f"Error fetching team name for results sync: {e}")

    return resolve_team_string_id(client, team_id, semester_id=semester_id)


def sync_team_results_from_evaluations(client, team_id: int, semester_id: str | None = None) -> None:
    """Push locked panel evaluation scores into admin results table, supporting both legacy and presentation cycles."""
    import json
    from app.slot_service import normalized_score

    try:
        # The team itself determines the semester — resolve from it, don't guess
        # "the first active" (several batches are active at once).
        active_sem_id = semester_id
        if not active_sem_id:
            try:
                active_sem_id = resolve_team_semester_id(client, team_id)
            except Exception as sem_e:
                print(f"Error resolving team semester in sync: {sem_e}")
        if not active_sem_id:
            try:
                res_sems = client.table("semester_config").select("id").eq("is_active", True).execute()
                active_sem_ids = [s["id"] for s in res_sems.data or []]
                active_sem_id = active_sem_ids[0] if len(active_sem_ids) == 1 else None
            except Exception as sem_e:
                print(f"Error fetching active semester in sync: {sem_e}")

        # Resolve team key (string format) using the correct semester_id context
        team_key = resolve_results_team_key(client, team_id, semester_id=active_sem_id)
        title = get_project_title(client, team_id)

        # 1. Fetch detailed team info from teams_validation
        tv_title = title
        tv_domain = None
        tv_mentor = None
        tv_branch = None
        try:
            res_tv = client.table("teams_validation").select("*").eq("id", team_key).execute()
            if res_tv.data:
                team_data = res_tv.data[0]
                tv_title = team_data.get("title") or tv_title
                tv_domain = team_data.get("domain")
                raw_m = team_data.get("mentor")
                if raw_m and raw_m != "--":
                    try:
                        import json as _json
                        parsed = _json.loads(raw_m)
                        if isinstance(parsed, list):
                            tv_mentor = ", ".join(parsed)
                        else:
                            tv_mentor = str(parsed)
                    except Exception:
                        tv_mentor = str(raw_m)
                
                members = team_data.get("members", [])
                if members and isinstance(members, list):
                    tv_branch = members[0].get("branch")
        except Exception as tv_e:
            print(f"Error fetching detailed team info from teams_validation: {tv_e}")

        # 2. Query cycles to check if we are using dynamic cycles
        cycles = []
        if active_sem_id:
            try:
                res_cycles = client.table("presentation_cycles").select("*").eq("semester_id", active_sem_id).execute()
                cycles = res_cycles.data or []
            except Exception as e:
                print(f"Error checking presentation cycles: {e}")

        proposal_marks = None
        mid_marks = None
        final_marks = None

        if cycles:
            try:
                res_pevals = client.table("presentation_evaluations").select("cycle_id, total_score").eq("team_id", team_key).execute()
                pevals = res_pevals.data or []
                
                cycle_ids = [c["id"] for c in cycles]
                rubrics_data = []
                if cycle_ids:
                    rubrics_data_res = client.table("presentation_rubrics").select("cycle_id, max_marks").in_("cycle_id", cycle_ids).execute()
                    rubrics_data = rubrics_data_res.data or []
                
                rubrics_by_cycle = {}
                for r in rubrics_data:
                    rubrics_by_cycle.setdefault(r["cycle_id"], []).append(r)
                
                pevals_by_cycle = {}
                for pe in pevals:
                    pevals_by_cycle.setdefault(pe["cycle_id"], []).append(pe)
                
                for cycle in cycles:
                    cid = cycle["id"]
                    ctype = cycle.get("type", "").lower()
                    
                    cycle_evals = pevals_by_cycle.get(cid, [])
                    if cycle_evals:
                        avg_normalized = sum(pe["total_score"] for pe in cycle_evals) / len(cycle_evals)
                        scaled_score = round((avg_normalized / 100.0) * cycle.get("weightage", 100))
                        
                        if ctype == "proposal":
                            proposal_marks = scaled_score
                        elif ctype == "mid":
                            mid_marks = scaled_score
                        elif ctype == "final":
                            final_marks = scaled_score
                        else:
                            idx = cycles.index(cycle)
                            if idx == 0:
                                proposal_marks = scaled_score
                            elif idx == 1:
                                mid_marks = scaled_score
                            elif idx == 2:
                                final_marks = scaled_score
            except Exception as e:
                print(f"Error mapping presentation_evaluations to results columns: {e}")

        # 3. Fallback to legacy evaluations
        if proposal_marks is None and mid_marks is None and final_marks is None:
            try:
                res_evals = client.table("evaluations").select("scores_json, semester_id").eq("team_id", team_id).eq("locked", True).execute()
                if res_evals.data:
                    scaled_scores = []
                    for ev in res_evals.data:
                        scores = json.loads(ev["scores_json"])
                        int_scores = {k: int(v) for k, v in scores.items()}
                        scaled_scores.append(round((normalized_score(int_scores) / 100) * 30))
                    mid_marks = round(sum(scaled_scores) / len(scaled_scores))
            except Exception as e:
                print(f"Error fallback syncing legacy evaluations: {e}")

        # 4. Save to results table
        res_existing = client.table("results").select("team").eq("team", team_key).execute()
        
        total_score = None
        if proposal_marks is not None or mid_marks is not None or final_marks is not None:
            total_score = (proposal_marks or 0) + (mid_marks or 0) + (final_marks or 0)

        update_data = {
            "proposalMarks": proposal_marks,
            "midMarks": mid_marks,
            "finalMarks": final_marks,
            "totalScore": total_score
        }
        if active_sem_id:
            update_data["semester_id"] = active_sem_id
        if tv_title:
            update_data["title"] = tv_title
        if tv_domain:
            update_data["domain"] = tv_domain
        if tv_mentor:
            update_data["mentor"] = tv_mentor
        if tv_branch:
            update_data["branch"] = tv_branch

        team_uid = resolve_team_uid(client, team_id, semester_id=active_sem_id)
        if team_uid:
            update_data["team_uid"] = team_uid

        if res_existing.data:
            client.table("results").update(update_data).eq("team", team_key).execute()
        else:
            insert_data = {"team": team_key, **update_data}
            client.table("results").insert(insert_data).execute()

        # Update absent_students status to 'Completed' for this team
        try:
            client.table("absent_students").update({"status": "Completed"}).eq("team", team_key).execute()
            from_num = resolve_team_string_id(client, team_id, semester_id=active_sem_id)
            if from_num != team_key:
                client.table("absent_students").update({"status": "Completed"}).eq("team", from_num).execute()
        except Exception as abs_e:
            print(f"Error updating absent_students status: {abs_e}")
    except Exception as e:
        print(f"Error syncing evaluation to results table: {e}")


def resolve_team_semester_id(client, team_id: int) -> str | None:
    """Resolve the team's semester ID from teams_validation (canonical: by uid)."""
    try:
        uid = resolve_team_uid(client, team_id)
        if uid:
            res = client.table("teams_validation").select("semester_id").eq("uid", uid).execute()
            if res.data:
                return res.data[0].get("semester_id")
        team_str = resolve_team_string_id(client, team_id)
        res = client.table("teams_validation").select("semester_id").eq("id", team_str).execute()
        if res.data:
            return res.data[0].get("semester_id")
    except Exception as e:
        print(f"Error resolving team semester ID for team {team_id}: {e}")
    return None


def get_active_team_string_ids(client) -> set[str]:
    """Return a set of string team IDs for active semesters — cached for 15 seconds."""
    def _fetch():
        try:
            res_sems = client.table("semester_config").select("id").eq("is_active", True).execute()
            active_sem_ids = [s["id"] for s in res_sems.data or []]
            if not active_sem_ids:
                return set()
            res_teams = client.table("teams_validation").select("id").in_("semester_id", active_sem_ids).execute()
            return {t["id"] for t in res_teams.data or []}
        except Exception as e:
            print(f"Error getting active team string IDs: {e}")
            return set()
    return get_cached("active_team_string_ids", 15.0, _fetch)
def get_active_team_ids(client) -> set[int]:
    """Return a set of numeric team IDs for active semesters — cached for 5 minutes.
    FIX (Bug 5): Also includes the database bigint IDs from the teams table so that
    evaluations (which store teams.id as team_id) can be matched correctly.
    """
    def _fetch():
        try:
            res_sems = client.table("semester_config").select("id").eq("is_active", True).execute()
            active_sem_ids = [s["id"] for s in res_sems.data or []]
            if not active_sem_ids:
                return set()
            res_teams = client.table("teams_validation").select("id").in_("semester_id", active_sem_ids).execute()
            # Numeric suffixes from team string IDs (e.g. TEAM-3 → 3)
            suffix_ids = {to_numeric_id(t["id"]) for t in res_teams.data or []}

            # Also resolve teams table bigint IDs for the same teams
            db_bigint_ids: set[int] = set()
            try:
                team_names = [t["id"] for t in res_teams.data or []]
                if team_names:
                    res_db = client.table("teams").select("id,name").in_("name", team_names).execute()
                    for row in res_db.data or []:
                        try:
                            db_bigint_ids.add(int(row["id"]))
                        except (TypeError, ValueError):
                            pass
                    # Fallback: also look up by numeric suffix in bulk if name didn't match
                    if not db_bigint_ids and suffix_ids:
                        try:
                            r2 = client.table("teams").select("id").in_("id", list(suffix_ids)).execute()
                            for row in r2.data or []:
                                try:
                                    db_bigint_ids.add(int(row["id"]))
                                except (TypeError, ValueError):
                                    pass
                        except Exception as loop_e:
                            print(f"get_active_team_ids bulk fallback failed: {loop_e}")
            except Exception as e:
                print(f"get_active_team_ids: teams table lookup failed: {e}")

            return suffix_ids | db_bigint_ids
        except Exception as e:
            print(f"Error getting active team IDs: {e}")
            return set()
    return get_cached("active_team_ids", 15.0, _fetch)
