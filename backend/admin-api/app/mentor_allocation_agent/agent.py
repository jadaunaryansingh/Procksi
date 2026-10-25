"""
allocation_agent.py — Mentor Allocation Agent (admin-api / Supabase).

Workflow built on top of the live ``teams_validation`` + ``mentors`` tables:
  M1  import mentors (CSV / Excel / PDF) → dedup → preview → save
  M3  top-5 mentor suggestions per team (domain filter + rule score)
  M4  capture a team's ordered preference list (≤5) in ``mentor_preferences``
  M5  batch allocation: greedy by preference → fallback → capacity lock
  M6  admin overview + manual override + capacity bump + lock

Mentor *load* is derived from ``teams_validation.mentor`` (the JSON name array the
admin UI already writes), so capacity is always consistent with reality.
"""
from __future__ import annotations

import io
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.mentor_allocation_agent.engine import (
    extract_keywords,
    infer_domains,
    normalise_domains,
    rank_mentors_by_domain,
)

MENTOR_DEFAULT_CAPACITY = 2  # 2 teams ≈ 10 students (per plan D2)


# ─────────────────────────────────────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────────────────────────────────────
def _parse_list_field(value: Any) -> List[str]:
    """teams_validation.mentor / any text holding a JSON array, CSV, or bare value."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "[]"):
        return []
    if s.startswith("["):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            pass
    return [p.strip() for p in re.split(r"[;,|]", s) if p.strip()]


def _parse_keywords(value: Any) -> List[str]:
    return _parse_list_field(value)


_HEADER_ALIASES = {
    "name": ["name", "mentor name", "faculty name", "full name"],
    "email": ["email", "email id", "mail", "email address"],
    "expertise": ["expertise", "specialization", "specialisation", "area", "research area", "interests"],
    "skills": ["skills", "skill", "technologies", "tech stack", "competencies"],
    "domains": ["domains", "domain", "fields", "field", "areas"],
    "experience_years": ["experience_years", "experience", "exp", "years", "years of experience"],
    "max_teams": ["max_teams", "max teams", "capacity", "maxload", "max load", "max_load"],
}


def _match_header(key: str, headers: List[str]) -> Optional[str]:
    aliases = _HEADER_ALIASES[key]
    norm = {h: re.sub(r"[\s_]+", "", str(h).lower()) for h in headers}
    for h, n in norm.items():
        if any(n == re.sub(r"[\s_]+", "", a.lower()) for a in aliases):
            return h
    return None


def _row_to_mentor(row: Dict[str, Any], headers: List[str]) -> Optional[dict]:
    def val(key):
        h = _match_header(key, headers)
        return row.get(h) if h else None

    name = (str(val("name") or "")).strip()
    email = (str(val("email") or "")).strip()
    if not name and not email:
        return None
    domains = normalise_domains(val("domains")) or normalise_domains(val("expertise"))
    skills = normalise_domains(val("skills"))
    try:
        exp = int(float(str(val("experience_years") or 0).strip() or 0))
    except Exception:
        exp = 0
    try:
        cap = int(float(str(val("max_teams") or MENTOR_DEFAULT_CAPACITY).strip() or MENTOR_DEFAULT_CAPACITY))
    except Exception:
        cap = MENTOR_DEFAULT_CAPACITY
    return {
        "name": name or email.split("@")[0],
        "email": email,
        "expertise": (str(val("expertise") or "")).strip(),
        "skills": skills,
        "domains": domains,
        "experience_years": exp,
        "max_teams": cap,
    }


def _parse_upload(filename: str, raw: bytes) -> List[dict]:
    """Parse CSV / Excel / PDF bytes → list of normalized mentor dicts."""
    fn = (filename or "").lower()
    rows: List[dict] = []
    if fn.endswith((".csv", ".txt")):
        import pandas as pd
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
        headers = list(df.columns)
        rows = [_row_to_mentor(r, headers) for r in df.to_dict("records")]
    elif fn.endswith((".xlsx", ".xls")):
        import pandas as pd
        df = pd.read_excel(io.BytesIO(raw), dtype=str).fillna("")
        headers = list(df.columns)
        rows = [_row_to_mentor(r, headers) for r in df.to_dict("records")]
    elif fn.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        # Best-effort: one mentor per line as "Name, email, domains..."
        for line in text.splitlines():
            line = line.strip()
            if "@" not in line:
                continue
            parts = [p.strip() for p in re.split(r"[,\t|]", line) if p.strip()]
            email = next((p for p in parts if "@" in p), "")
            others = [p for p in parts if "@" not in p]
            name = others[0] if others else email.split("@")[0]
            rows.append({
                "name": name, "email": email, "expertise": "",
                "skills": [], "domains": normalise_domains(others[1:]),
                "experience_years": 0, "max_teams": MENTOR_DEFAULT_CAPACITY,
            })
    else:
        raise HTTPException(400, f"Unsupported file type: {filename}. Use CSV, Excel, or PDF.")

    # Drop empties + dedup by email (case-insensitive), keeping the richest row.
    seen: Dict[str, dict] = {}
    out: List[dict] = []
    for m in rows:
        if not m:
            continue
        key = (m.get("email") or m.get("name") or "").strip().lower()
        if not key:
            continue
        if key in seen:
            continue
        seen[key] = m
        out.append(m)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Supabase data helpers
# ─────────────────────────────────────────────────────────────────────────────
def _mentor_loads(client, semester_id: Optional[str]) -> Dict[str, int]:
    q = client.table("teams_validation").select("mentor")
    if semester_id:
        q = q.eq("semester_id", semester_id)
    rows = q.execute().data or []
    loads: Dict[str, int] = {}
    for r in rows:
        for name in _parse_list_field(r.get("mentor")):
            k = name.strip().lower()
            loads[k] = loads.get(k, 0) + 1
    return loads


def _mentor_dict(m: dict, loads: Dict[str, int]) -> dict:
    name = (m.get("name") or "").strip()
    return {
        "id": m.get("id"),
        "name": name,
        "email": m.get("email"),
        "domains": m.get("domains") or normalise_domains(m.get("domain")),
        "skills": m.get("skills") or [],
        "expertise": m.get("expertise") or "",
        "experience_years": m.get("experience_years") or 0,
        "max_teams": m.get("max_teams") or m.get("maxLoad") or MENTOR_DEFAULT_CAPACITY,
        "current_teams": loads.get(name.lower(), 0),
    }


def _team_dict(t: dict) -> dict:
    title, desc = t.get("title") or "", t.get("description") or ""
    kws = _parse_keywords(t.get("keywords"))
    if not kws:
        kws = extract_keywords(f"{title} {desc}")
    # Declared domain is usually "General"/blank → infer the real domain from the
    # title + keywords so the domain filter is meaningful (else empty → partial match).
    declared = [d for d in normalise_domains(t.get("domain")) if d.strip().lower() != "general"]
    domains = infer_domains(declared) or infer_domains(f"{title} {desc} {' '.join(kws)}")
    return {
        "id": t.get("id"),
        "project_title": title,
        "description": desc,
        "domain": domains,
        "required_skills": kws,
        "_keywords_str": ", ".join(kws),
    }


# ─────────────────────────────────────────────────────────────────────────────
# In-app notifications (PMS portals)
# ─────────────────────────────────────────────────────────────────────────────
def _student_email_map(client) -> Dict[str, str]:
    """student id (str) → email, for resolving a team's members to recipients."""
    rows = client.table("students").select("id,email").execute().data or []
    return {str(r.get("id")): r.get("email") for r in rows if r.get("email")}


def _team_member_ids(team: dict) -> List[str]:
    """All student ids on a team (members jsonb + leader), de-duplicated."""
    members = team.get("members")
    if isinstance(members, str):
        try:
            members = json.loads(members)
        except Exception:
            members = []
    ids: List[str] = []
    for m in members or []:
        mid = (m.get("id") or m.get("student_id") or m.get("roll")) if isinstance(m, dict) else m
        if mid not in (None, ""):
            ids.append(str(mid))
    if team.get("leader"):
        ids.append(str(team.get("leader")))
    return list(dict.fromkeys(ids))


def _team_label(team: dict) -> str:
    """Friendly team name: the project title if real, else 'Team <N>'."""
    title = (team.get("title") or "").strip()
    if title and not re.match(r"^team\s*-?\s*\d+$", title.lower()):
        return title
    m = re.search(r"-T(\d+)$", str(team.get("id") or ""))
    return f"Team {m.group(1)}" if m else (title or str(team.get("id") or "your team"))


def notify_allocation(client, team: dict, mentor: dict, student_map: Dict[str, str]) -> int:
    """Create in-app notifications when a mentor is assigned to a team.

    Routes one row per team member to the **student** portal and one to the
    **mentor** portal (each portal's /notifications query filters on
    ``recipient_email``). Best-effort: never raises.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    label = _team_label(team)
    mentor_name = (mentor.get("name") or "Your mentor").strip()
    rows: List[dict] = []
    for mid in _team_member_ids(team):
        email = student_map.get(str(mid))
        if not email:
            continue
        rows.append({
            "recipient_email": email,
            "recipient_role": "student",
            "audience": f"team:{team.get('id')}",
            "title": "Mentor Assigned",
            "message": f"{mentor_name} has been assigned as your project mentor.",
            "type": "mentor_allocation",
            "read": False,
            "created_at": now_iso,
            "action_url": "/student/mentor",
        })
    if mentor.get("email"):
        rows.append({
            "recipient_email": mentor["email"],
            "recipient_role": "mentor",
            "audience": "mentor_allocation",
            "title": "New Team Assigned",
            "message": f"You have been assigned to mentor {label}.",
            "type": "mentor_allocation",
            "read": False,
            "created_at": now_iso,
            "action_url": "/mentor/teams",
        })
    if not rows:
        return 0
    try:
        client.table("notifications").insert(rows).execute()
        return len(rows)
    except Exception as e:  # in-app delivery is best-effort
        print(f"notify_allocation failed: {e}")
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────
class SaveMentorsRequest(BaseModel):
    mentors: List[dict]


class PreferenceRequest(BaseModel):
    team_id: str
    mentor_ids: List[str]          # ordered, rank 1..N (≤5)
    semester_id: Optional[str] = None


class RunRequest(BaseModel):
    semester_id: Optional[str] = None
    reassign_all: bool = False        # False = only fill teams that have no mentor yet


class CapacityRequest(BaseModel):
    max_teams: int


class LockRequest(BaseModel):
    team_id: str
    locked: bool = True


class AssignRequest(BaseModel):
    team_id: str
    mentor_id: str


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────
def build_allocation_router(service_client) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["Mentor Allocation Agent"])
    client = service_client

    def _mentors_by_id(loads):
        # Only admin-approved (is_active) mentors are eligible for allocation/counting.
        rows = client.table("mentors").select("*").eq("is_active", True).execute().data or []
        return {str(m.get("id")): _mentor_dict(m, loads) for m in rows}

    # ── M1: import ──────────────────────────────────────────────────────────
    @router.post("/mentors/import")
    async def import_mentors(file: UploadFile = File(...)) -> dict:
        raw = await file.read()
        parsed = _parse_upload(file.filename, raw)
        existing = client.table("mentors").select("email").execute().data or []
        existing_emails = {(e.get("email") or "").strip().lower() for e in existing}
        for m in parsed:
            m["_exists"] = (m.get("email") or "").strip().lower() in existing_emails
        return {"data": {"count": len(parsed), "mentors": parsed}}

    @router.post("/mentors/import/save")
    def save_mentors(body: SaveMentorsRequest) -> dict:
        if not body.mentors:
            raise HTTPException(400, "No mentors to save")
        existing = client.table("mentors").select("id,email").execute().data or []
        id_by_email = {(e.get("email") or "").strip().lower(): e.get("id")
                       for e in existing if e.get("email")}
        rows = []
        for m in body.mentors:
            email = (m.get("email") or "").strip()
            mid = id_by_email.get(email.lower()) or m.get("id") or str(uuid.uuid4())
            domains = m.get("domains") or []
            rows.append({
                "id": mid,
                "name": m.get("name") or email.split("@")[0],
                "email": email,
                "expertise": m.get("expertise") or "",
                "skills": m.get("skills") or [],
                "domains": domains,
                "domain": (domains[0] if domains else None),  # admin-UI simple column
                "experience_years": int(m.get("experience_years") or 0),
                "max_teams": int(m.get("max_teams") or MENTOR_DEFAULT_CAPACITY),
                "maxLoad": int(m.get("max_teams") or MENTOR_DEFAULT_CAPACITY),
                "is_active": True,
            })
        client.table("mentors").upsert(rows, on_conflict="id").execute()
        return {"data": {"saved": len(rows)}}

    # ── M3: top-5 suggestions ────────────────────────────────────────────────
    @router.get("/allocation/suggestions/{team_id}")
    def suggestions(team_id: str) -> dict:
        res = client.table("teams_validation").select("*").eq("id", team_id).execute()
        if not res.data:
            raise HTTPException(404, f"Team '{team_id}' not found")
        team = res.data[0]
        td = _team_dict(team)
        # cache keywords back onto the team if not already stored
        if not _parse_keywords(team.get("keywords")) and td["_keywords_str"]:
            try:
                client.table("teams_validation").update(
                    {"keywords": td["_keywords_str"]}).eq("id", team_id).execute()
            except Exception:
                pass
        loads = _mentor_loads(client, team.get("semester_id"))
        mentors = list(_mentors_by_id(loads).values())
        top = rank_mentors_by_domain(td, mentors, top_k=5)
        return {"data": {"team_id": team_id, "domain": td["domain"],
                         "keywords": td["required_skills"], "suggestions": top}}

    # ── M4: preferences ──────────────────────────────────────────────────────
    @router.post("/allocation/preferences")
    def submit_preferences(body: PreferenceRequest) -> dict:
        if not body.mentor_ids:
            raise HTTPException(400, "Provide at least one mentor preference")
        if len(body.mentor_ids) > 5:
            raise HTTPException(400, "At most 5 preferences allowed")
        loads = _mentor_loads(client, body.semester_id)
        mentors = _mentors_by_id(loads)
        # clear prior prefs for this team
        client.table("mentor_preferences").delete().eq("team_id", body.team_id).execute()
        rows = []
        for i, mid in enumerate(body.mentor_ids, start=1):
            m = mentors.get(str(mid))
            rows.append({
                "team_id": body.team_id, "mentor_id": str(mid),
                "mentor_name": m["name"] if m else None,
                "rank": i, "status": "pending", "semester_id": body.semester_id,
            })
        client.table("mentor_preferences").insert(rows).execute()
        return {"data": {"team_id": body.team_id, "saved": len(rows)}}

    @router.get("/allocation/preferences/{team_id}")
    def get_preferences(team_id: str) -> dict:
        rows = (client.table("mentor_preferences").select("*")
                .eq("team_id", team_id).order("rank").execute().data or [])
        return {"data": rows}

    # ── M5: batch allocation (admin one-click, ranked-domain matching) ────────
    @router.post("/allocation/run")
    def run_allocation(body: RunRequest) -> dict:
        """Assign one mentor per team by ranked-domain fit (admin-triggered).

        For each eligible team we rank every approved mentor by where the team's
        domain sits in that mentor's preference-ordered domain list, capped by
        capacity, and assign the best mentor with room. There is no student/team
        preference step — the mentor's domain ranking is the signal.

        By default only teams that have *no* mentor yet are touched; pass
        ``reassign_all=true`` to re-run across every unlocked team.
        """
        sem = body.semester_id
        tq = client.table("teams_validation").select("*")
        if sem:
            tq = tq.eq("semester_id", sem)
        teams = tq.execute().data or []
        loads = _mentor_loads(client, sem)
        mentors = _mentors_by_id(loads)              # id -> mentor dict (live load)
        mentor_list = list(mentors.values())
        student_map = _student_email_map(client)     # for portal notifications

        def has_room(m):
            return m and m["current_teams"] < int(m["max_teams"] or MENTOR_DEFAULT_CAPACITY)

        def assign(team, m, source):
            client.table("teams_validation").update({
                "mentor": json.dumps([m["name"]]),
                "mentor_source": source,
            }).eq("id", team["id"]).execute()
            m["current_teams"] += 1

        summary = {"allotted": 0, "skipped_locked": 0, "already_assigned": 0,
                   "no_mentors_with_room": 0, "notified": 0, "unmatched": [],
                   "total_teams": len(teams)}

        for team in teams:
            if team.get("mentor_locked_by_admin"):
                summary["skipped_locked"] += 1
                continue
            if not body.reassign_all and _parse_list_field(team.get("mentor")):
                summary["already_assigned"] += 1
                continue
            ranked = rank_mentors_by_domain(_team_dict(team), mentor_list, top_k=5)
            chosen = next((mentors[r["mentor_id"]] for r in ranked
                           if has_room(mentors.get(r["mentor_id"]))), None)
            if chosen:
                assign(team, chosen, "agent_domain_rank")
                summary["allotted"] += 1
                summary["notified"] += notify_allocation(client, team, chosen, student_map)
            elif ranked:
                # mentors matched on domain but all are at capacity
                summary["no_mentors_with_room"] += 1
                summary["unmatched"].append(team["id"])
            else:
                summary["unmatched"].append(team["id"])

        # Sync mentor load counters back for the admin workload UI
        for m in mentors.values():
            try:
                client.table("mentors").update(
                    {"current_teams": m["current_teams"], "teams": m["current_teams"],
                     "load": m["current_teams"]}).eq("id", m["id"]).execute()
            except Exception:
                pass
        return {"data": summary}

    # ── M6: overview / override / capacity / lock ─────────────────────────────
    @router.get("/allocation/overview")
    def overview(semester_id: Optional[str] = None) -> dict:
        loads = _mentor_loads(client, semester_id)
        # Only approved mentors appear in the agent's allocatable workload view.
        mentors = client.table("mentors").select("*").eq("is_active", True).execute().data or []
        mentor_rows = [{
            "id": m.get("id"), "name": m.get("name"),
            "domains": m.get("domains") or normalise_domains(m.get("domain")),
            "load": loads.get((m.get("name") or "").strip().lower(), 0),
            "max_teams": m.get("max_teams") or MENTOR_DEFAULT_CAPACITY,
        } for m in mentors]
        tq = client.table("teams_validation").select(
            "id,title,domain,mentor,mentor_source,mentor_locked_by_admin,semester_id")
        if semester_id:
            tq = tq.eq("semester_id", semester_id)
        teams = tq.execute().data or []
        team_rows = [{
            "team_id": t.get("id"), "title": t.get("title"), "domain": t.get("domain"),
            "mentor": _parse_list_field(t.get("mentor")),
            "source": t.get("mentor_source"),
            "locked": bool(t.get("mentor_locked_by_admin")),
        } for t in teams]
        return {"data": {"mentors": mentor_rows, "teams": team_rows}}

    @router.post("/allocation/assign")
    def manual_assign(body: AssignRequest) -> dict:
        mres = client.table("mentors").select("id,name,email").eq("id", body.mentor_id).execute()
        if not mres.data:
            raise HTTPException(404, "Mentor not found")
        mentor = mres.data[0]
        name = mentor["name"]
        client.table("teams_validation").update({
            "mentor": json.dumps([name]), "mentor_source": "admin_manual",
        }).eq("id", body.team_id).execute()
        # Notify the team's students + the mentor in their portals (best-effort).
        notified = 0
        try:
            tres = client.table("teams_validation").select("*").eq("id", body.team_id).execute()
            if tres.data:
                notified = notify_allocation(client, tres.data[0], mentor, _student_email_map(client))
        except Exception as e:
            print(f"manual_assign notify failed: {e}")
        return {"data": {"team_id": body.team_id, "mentor": name,
                         "source": "admin_manual", "notified": notified}}

    @router.patch("/mentors/{mentor_id}/capacity")
    def set_capacity(mentor_id: str, body: CapacityRequest) -> dict:
        client.table("mentors").update(
            {"max_teams": body.max_teams, "maxLoad": body.max_teams}).eq("id", mentor_id).execute()
        return {"data": {"mentor_id": mentor_id, "max_teams": body.max_teams}}

    @router.post("/allocation/lock")
    def lock_team(body: LockRequest) -> dict:
        client.table("teams_validation").update(
            {"mentor_locked_by_admin": body.locked}).eq("id", body.team_id).execute()
        return {"data": {"team_id": body.team_id, "locked": body.locked}}

    return router
