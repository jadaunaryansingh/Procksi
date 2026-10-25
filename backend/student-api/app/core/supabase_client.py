import httpx
import logging
import json
import os
import urllib.parse
import re
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.core.ttl_cache import TTLCache

logger = logging.getLogger(__name__)

# Fallback TTL; every _cached_get call site passes its own.
CACHE_DEFAULT_TTL = 10.0
# Distinguishes "cached None" from "not cached".
_CACHE_MISS = object()

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

def extract_numeric_id(team_id_str: str) -> int:
    if not team_id_str:
        return 0
    s = str(team_id_str).strip()
    
    # 1. Strip standard UUID patterns (36 chars with hyphens)
    clean = re.sub(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "", s).strip()
    target = clean if clean else s

    # 2. Check for -T\d+ or TEAM[-_]?\d+
    match = (
        re.search(r"[-_]?[Tt](\d+)", target, re.IGNORECASE)
        or re.search(r"[-_]?[Tt][Ee][Aa][Mm][-_]?\s*(\d+)", target, re.IGNORECASE)
    )
    if match:
        val = int(match.group(1))
        if 0 < val < 100000:
            return val

    # 3. Check for trailing hyphen/underscore digits
    match_last = re.search(r"[-_](\d+)$", target)
    if match_last:
        val = int(match_last.group(1))
        if 0 < val < 100000:
            return val

    # 4. If target is pure digits
    if target.isdigit():
        val = int(target)
        if 0 < val < 100000:
            return val

    # 5. Fallback to number sequences, ignoring numbers >= 1000 (like 4-digit years '2026')
    nums = re.findall(r"\d+", target)
    for n in reversed(nums):
        val = int(n)
        if 0 < val < 1000:
            return val

    # No real team number found. Return 0 — callers skip the TEAM-{n} variant when
    # this is 0. (The old "last 3 digits of the UUID" fallback is gone: it invented
    # team numbers out of uuids and is exactly how one team's dashboard showed
    # another team's data. Identity now flows through team_uid, never a number.)
    return 0


def get_clean_team_name(team_id: Any, raw_name: Optional[str] = None, tv_id: Optional[str] = None) -> str:
    # 1. Try extracting numeric team ID from tv_id or team_id
    num_id = 0
    if tv_id:
        num_id = extract_numeric_id(str(tv_id))
    if not num_id and team_id:
        num_id = extract_numeric_id(str(team_id))
        
    # 2. Check if raw_name is a valid (non-corrupt) "Team X" name
    name_str = str(raw_name or "").strip()
    is_corrupt = bool(
        re.match(r"^Team\s*\d{6,}$", name_str, re.IGNORECASE)
        or re.match(r"^Team\s*[0-9a-f-]{8,}$", name_str, re.IGNORECASE)
    )
    
    if not num_id and name_str and not is_corrupt and name_str.lower().startswith("team"):
        num_id = extract_numeric_id(name_str)
        
    if num_id > 0:
        return f"Team {num_id}"
        
    if name_str and not is_corrupt and not name_str.lower().startswith("pending"):
        return name_str
        
    fallback_num = extract_numeric_id(str(team_id or tv_id or raw_name or ""))
    return f"Team {fallback_num if fallback_num > 0 else '1'}"


class SupabaseRESTClient:
    def __init__(self):
        self.base_url = (settings.SUPABASE_URL or "").rstrip("/")
        self.key = settings.SUPABASE_SERVICE_KEY or settings.SUPABASE_KEY
        if not self.base_url or not self.key:
            logger.warning("Supabase REST Client: SUPABASE_URL or SUPABASE_KEY is missing from configuration.")
        
        self._client = None
        self._client_loop = None
        
        # Short-lived TTL cache and request coalescing structures.
        # Bounded: a plain dict never swept expired entries, so every key that
        # was not read again (a student who logs in once) stayed for the life of
        # the process. Per-entry TTL because call sites cache for different
        # durations. `_pending_tasks` is self-limiting — entries are removed in
        # the `finally` below.
        self._cache = TTLCache(
            ttl=CACHE_DEFAULT_TTL,
            max_entries=int(os.getenv("PMS_REST_CACHE_MAX", "4096")),
        )
        self._pending_tasks = {}  # Map key -> asyncio.Task

    def _get_client(self) -> httpx.AsyncClient:
        import asyncio
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if (
            self._client is None
            or self._client.is_closed
            or (self._client_loop is not None and loop is not None and self._client_loop is not loop)
        ):
            self.base_url = (settings.SUPABASE_URL or "").rstrip("/")
            self.key = settings.SUPABASE_SERVICE_KEY or settings.SUPABASE_KEY
            self._client_loop = loop
            self._client = httpx.AsyncClient(
                base_url=f"{self.base_url}/rest/v1",
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json"
                },
                timeout=15.0
            )
        return self._client

    async def _cached_get(self, cache_key: str, ttl: float, coro) -> Any:
        import asyncio

        if not hasattr(self, "_cache") or self._cache is None:
            self._cache = TTLCache(ttl=CACHE_DEFAULT_TTL, max_entries=4096)
        if not hasattr(self, "_pending_tasks") or self._pending_tasks is None:
            self._pending_tasks = {}

        # 1. Check cache first
        cached = self._cache.get(cache_key, _CACHE_MISS)
        if cached is not _CACHE_MISS:
            # Close the coroutine to prevent "never awaited" RuntimeWarning
            if hasattr(coro, "close"):
                coro.close()
            return cached

        # 2. Check pending tasks to coalesce concurrent requests
        if cache_key in self._pending_tasks:
            if hasattr(coro, "close"):
                coro.close()
            return await self._pending_tasks[cache_key]

        # 3. Create task and await it
        task = asyncio.create_task(coro)
        self._pending_tasks[cache_key] = task
        try:
            val = await task
            self._cache.set(cache_key, val, ttl=ttl)
            return val
        finally:
            self._pending_tasks.pop(cache_key, None)

    async def _request(
        self,
        endpoint: str,
        method: str = "GET",
        body: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Any:
        try:
            req_headers = {}
            if headers:
                req_headers.update(headers)
            
            client = self._get_client()
            response = await client.request(
                method,
                endpoint.lstrip("/"),
                json=body,
                headers=req_headers
            )
            
            if response.status_code in [201, 204]:
                return []
                
            response.raise_for_status()
            
            if not response.text:
                return []
                
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Supabase REST HTTP error {e.response.status_code} on {method} {endpoint}: {e.response.text}")
            raise e
        except Exception as e:
            logger.error(f"Supabase REST connection error on {method} {endpoint}: {type(e).__name__} - {str(e) or repr(e)}")
            raise e

    async def get_student_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Fetch student profile by email."""
        async def _fetch():
            data = await self._request(f"students?email=eq.{urllib.parse.quote(email)}&limit=1")
            return data[0] if data else None
        return await self._cached_get(f"student_email:{email}", 1.0, _fetch())

    async def resolve_team_uid(self, identifier: Any) -> Optional[str]:
        """Resolve any team identifier to the canonical teams_validation.uid.

        Accepts: a uuid (verified), a teams_validation.id text slug, a legacy
        integer public.teams.id (via team_uid_map), or a bare-number string of one.
        Returns None if it cannot be resolved — never a guessed number.
        """
        if identifier is None:
            return None
        s = str(identifier).strip()
        if not s:
            return None

        async def _fetch():
            if _UUID_RE.match(s):
                r = await self._request(f"teams_validation?uid=eq.{urllib.parse.quote(s)}&select=uid&limit=1")
                return r[0]["uid"] if r else None
            r = await self._request(f"teams_validation?id=eq.{urllib.parse.quote(s)}&select=uid&limit=1")
            if r:
                return r[0]["uid"]
            if re.fullmatch(r"-?\d+", s):
                r = await self._request(f"team_uid_map?old_int_id=eq.{int(s)}&select=uid&limit=1")
                if r:
                    return r[0]["uid"]
            return None

        return await self._cached_get(f"resolve_team_uid:{s}", 30.0, _fetch())

    async def get_team_by_student_id(self, student_id: str, semester_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetch team that contains this student in team_memberships table or members JSONB array."""
        async def _fetch():
            student_id_str = str(student_id).strip()
            sem_filter = f"&semester_id=eq.{urllib.parse.quote(semester_id)}" if semester_id else ""

            # 1. First check team_memberships table (relational source of truth)
            try:
                tm = await self._request(f"team_memberships?student_roll=eq.{urllib.parse.quote(student_id_str)}{sem_filter}&limit=1")
                if tm and tm[0].get("team_uid"):
                    team_uid = tm[0]["team_uid"]
                    tv = await self._request(f"teams_validation?uid=eq.{urllib.parse.quote(str(team_uid))}&limit=1")
                    if tv:
                        return tv[0]
            except Exception:
                pass

            # 2. Try JSONB queries for keys: id, roll, student_id
            for key in ("id", "roll", "student_id"):
                filter_val = f'[{{"{key}":"{student_id_str}"}}]'
                encoded_filter = urllib.parse.quote(filter_val)
                data = await self._request(f"teams_validation?members=cs.{encoded_filter}{sem_filter}&limit=1")
                if data:
                    return data[0]

            # 3. Check plain string list format fallback
            filter_val_str = f'["{student_id_str}"]'
            encoded_filter_str = urllib.parse.quote(filter_val_str)
            data = await self._request(f"teams_validation?members=cs.{encoded_filter_str}{sem_filter}&limit=1")
            if data:
                return data[0]

            # 4. Check leader_roll in teams_validation
            try:
                data = await self._request(f"teams_validation?leader_roll=eq.{urllib.parse.quote(student_id_str)}{sem_filter}&limit=1")
                if data:
                    return data[0]
            except Exception:
                pass

            return None
        return await self._cached_get(f"team_student_id:{student_id}:{semester_id or ''}", 0.5, _fetch())

    async def get_proposal_by_team_id(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Fetch proposal details for a team. Canonical path is proposals.team_uid;
        the legacy teamId string match is kept only as a fallback."""
        team_id_str = team_id
        if isinstance(team_id, int) or (isinstance(team_id, str) and team_id.isdigit()):
            team_id_str = f"TEAM-{team_id}"
        async def _fetch():
            uid = await self.resolve_team_uid(team_id)
            if uid:
                data = await self._request(f"proposals?team_uid=eq.{urllib.parse.quote(uid)}&limit=1")
                if data:
                    return data[0]
            data = await self._request(f"proposals?teamId=eq.{urllib.parse.quote(team_id_str)}&limit=1")
            if not data:
                num_id = extract_numeric_id(team_id_str)
                if num_id:
                    data = await self._request(f"proposals?teamId=eq.TEAM-{num_id}&limit=1")
            return data[0] if data else None
        return await self._cached_get(f"proposal_team_id:{team_id_str}", 5.0, _fetch())

    async def get_latest_approved_proposal_by_team_id(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the newest approved proposal for a team across legacy ID formats."""
        team_id_str = str(team_id)
        num_id = extract_numeric_id(team_id_str)
        variants = list(dict.fromkeys(filter(None, [
            team_id_str,
            f"TEAM-{num_id}" if num_id else None,
            str(num_id) if num_id else None,
        ])))

        async def _fetch():
            uid = await self.resolve_team_uid(team_id)
            if uid:
                data = await self._request(
                    f"proposals?team_uid=eq.{urllib.parse.quote(uid)}&status=ilike.Approved"
                    "&order=submitted_at.desc.nullslast&limit=1"
                )
                if data:
                    return data[0]
            for variant in variants:
                encoded = urllib.parse.quote(str(variant))
                data = await self._request(
                    f"proposals?teamId=eq.{encoded}&status=ilike.Approved"
                    "&order=submitted_at.desc.nullslast&limit=1"
                )
                if data:
                    return data[0]
            return None

        return await self._cached_get(
            f"approved_proposal_team_id:{team_id_str}", 5.0, _fetch()
        )

    async def get_mentor_by_name(self, mentor_name: str) -> Optional[Dict[str, Any]]:
        """Fetch mentor details by name."""
        async def _fetch():
            data = await self._request(f"mentors?name=eq.{urllib.parse.quote(mentor_name)}&limit=1")
            return data[0] if data else None
        return await self._cached_get(f"mentor_name:{mentor_name}", 10.0, _fetch())

    async def get_schedule_slots_by_team(self, team_id: str) -> List[Dict[str, Any]]:
        """Fetch scheduled presentation slots for a team, trying multiple ID formats.
        Handles UUID-prefixed team IDs like 'abc123-T9' stored in schedule_slots.team.
        """
        team_id_str = str(team_id)
        if isinstance(team_id, int) or (isinstance(team_id, str) and team_id.isdigit()):
            team_id_str = f"TEAM-{team_id}"
        num_id = extract_numeric_id(team_id_str)

        # Build list of exact variants to try
        variants = list(dict.fromkeys(filter(None, [
            team_id_str,
            f"TEAM-{num_id}" if num_id else None,
            str(num_id) if num_id else None,
        ])))

        async def _fetch():
            # 1. Try exact matches first
            for variant in variants:
                try:
                    data = await self._request(f"schedule_slots?team=eq.{urllib.parse.quote(str(variant))}")
                    if data:
                        return data
                except Exception:
                    pass

            # 2. Try suffix match: schedule_slots stores UUID-prefixed IDs like "uuid-T9"
            #    Match on the -T{num_id} suffix using ilike
            if num_id:
                try:
                    data = await self._request(
                        f"schedule_slots?team=ilike.{urllib.parse.quote(f'*-T{num_id}')}"
                    )
                    if data:
                        return data
                except Exception:
                    pass

                # 3. Also try ending with just the number
                try:
                    data = await self._request(
                        f"schedule_slots?team=ilike.{urllib.parse.quote(f'*-T{num_id:03d}')}"
                    )
                    if data:
                        return data
                except Exception:
                    pass

            return []

        return await self._cached_get(f"slots_team_id:{team_id_str}", 5.0, _fetch())

    async def get_results_by_team(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Fetch results for a team, trying multiple ID formats."""
        team_id_str = str(team_id)
        if isinstance(team_id, int) or (isinstance(team_id, str) and team_id.isdigit()):
            team_id_str = f"TEAM-{team_id}"
        num_id = extract_numeric_id(team_id_str)
        
        variants = list(dict.fromkeys(filter(None, [
            team_id_str,
            f"TEAM-{num_id}" if num_id else None,
            str(num_id) if num_id else None,
        ])))

        async def _fetch():
            uid = await self.resolve_team_uid(team_id)
            if uid:
                data = await self._request(f"results?team_uid=eq.{urllib.parse.quote(uid)}&limit=1")
                if data:
                    return data[0]
            for variant in variants:
                data = await self._request(f"results?team=eq.{urllib.parse.quote(str(variant))}&limit=1")
                if data:
                    return data[0]
            return None
        return await self._cached_get(f"results_team_id:{team_id_str}", 5.0, _fetch())

    async def get_evaluations_by_team(self, team_id: str) -> List[Dict[str, Any]]:
        """Fetch evaluations for a team from both evaluations and presentation_evaluations tables."""
        team_id_str = str(team_id)
        num_id = extract_numeric_id(team_id_str)
        canonical_team_id = f"TEAM-{num_id}" if num_id else team_id_str
        
        variants = list(dict.fromkeys(filter(None, [
            team_id_str,
            canonical_team_id,
            str(num_id) if num_id else None
        ])))
        
        uid = await self.resolve_team_uid(team_id)

        legacy_evals = []
        if uid:
            try:
                res = await self._request(f"evaluations?team_uid=eq.{urllib.parse.quote(uid)}")
                if res:
                    legacy_evals.extend(res)
            except Exception:
                pass
        if not legacy_evals and num_id:
            try:
                res = await self._request(f"evaluations?team_id=eq.{num_id}")
                if res:
                    legacy_evals.extend(res)
            except Exception:
                pass

        pres_evals = []
        if uid:
            try:
                res = await self._request(f"presentation_evaluations?team_uid=eq.{urllib.parse.quote(uid)}")
                if res:
                    pres_evals.extend(res)
            except Exception:
                pass
        if not pres_evals:
            for var in variants:
                try:
                    res = await self._request(f"presentation_evaluations?team_id=eq.{urllib.parse.quote(var)}")
                    if res:
                        pres_evals.extend(res)
                        break
                except Exception:
                    pass
                
        merged = []
        for e in legacy_evals:
            merged.append({
                "id": e.get("id"),
                "team_id": e.get("team_id"),
                "panel_id": e.get("panel_id"),
                "semester_id": e.get("semester_id"),
                "scores_json": e.get("scores_json"),
                "remarks": e.get("remarks"),
                "submitted_at": e.get("submitted_at"),
                "locked": e.get("locked"),
                "cycle_id": e.get("cycle_id"),
            })
            
        for pe in pres_evals:
            merged.append({
                "id": pe.get("id"),
                "team_id": pe.get("team_id"),
                "panel_id": pe.get("evaluator_id"),
                "evaluator_id": pe.get("evaluator_id"),
                "semester_id": pe.get("semester_id"),
                "total_score": pe.get("total_score"),
                "remarks": pe.get("remarks"),
                "submitted_at": pe.get("evaluated_at"),
                "evaluated_at": pe.get("evaluated_at"),
                "cycle_id": pe.get("cycle_id"),
                "is_presentation_eval": True
            })
            
        return merged

    async def save_proposal(self, team_id: str, semester_id: str, title: str, description: str) -> Dict[str, Any]:
        """Save or update project proposal in proposals table."""
        # Ensure teamId has TEAM- prefix
        team_id_str = team_id
        if isinstance(team_id, int) or (isinstance(team_id, str) and team_id.isdigit()):
            team_id_str = f"TEAM-{team_id}"
            
        existing = await self.get_proposal_by_team_id(team_id_str)
        
        # Invalidate all caches on mutation
        self._cache.clear()
        try:
            from app.api.student_deps import PROFILE_CACHE
            PROFILE_CACHE.clear()
        except Exception:
            pass
        
        from datetime import datetime
        current_date_str = datetime.utcnow().strftime("%Y-%m-%d")

        # The caller passes the team's own semester. Only fall back to an active
        # semester when it is genuinely missing — and even then never blindly pick
        # "the first active": require it to match this team if we can tell.
        supabase_sem_id = semester_id
        if not supabase_sem_id:
            try:
                active_sems = await self._request("semester_config?is_active=eq.true&select=id")
                if active_sems and len(active_sems) == 1:
                    supabase_sem_id = active_sems[0].get("id")
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to query active semester from Supabase: {e}")

        team_uid = await self.resolve_team_uid(team_id)

        if existing:
            # Update existing proposal
            proposal_id = existing["id"]
            fields = {
                "title": title,
                "aiRationale": description,
                "status": "Pending",
                "submittedDate": current_date_str,
                "semester_id": supabase_sem_id
            }
            return await self._request(f"proposals?id=eq.{proposal_id}", method="PATCH", body=fields)
        else:
            # Insert new proposal
            import uuid
            proposal_id = f"PROP-{uuid.uuid4().hex[:8].upper()}"
            row = {
                "id": proposal_id,
                "teamId": team_id_str,
                **({"team_uid": team_uid} if team_uid else {}),
                "title": title,
                "aiRationale": description,
                "status": "Pending",
                "submittedDate": current_date_str,
                "semester_id": supabase_sem_id
            }
            return await self._request("proposals", method="POST", body=[row])

    async def update_team_proposal_details(
        self,
        team_id: str,
        title: str,
        description: str,
        domain: str,
        members: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Update team details in teams_validation table."""
        # Ensure team_id is formatted properly (e.g. TEAM-3)
        team_id_str = team_id
        if isinstance(team_id, int) or (isinstance(team_id, str) and team_id.isdigit()):
            team_id_str = f"TEAM-{team_id}"

        # Invalidate all caches on mutation
        self._cache.clear()
        try:
            from app.api.student_deps import PROFILE_CACHE
            PROFILE_CACHE.clear()
        except Exception:
            pass

        fields = {
            "title": title,
            "description": description,
            "domain": domain
        }

        if members is not None:
            # We need to format members to match what Admin Portal expects if necessary
            # For now, we'll just save the list as is in the JSONB column
            fields["members"] = members
            fields["memberCount"] = len(members)

        uid = await self.resolve_team_uid(team_id)
        if uid:
            return await self._request(f"teams_validation?uid=eq.{urllib.parse.quote(uid)}", method="PATCH", body=fields)
        return await self._request(f"teams_validation?id=eq.{team_id_str}", method="PATCH", body=fields)

    async def remove_student_from_team(self, team_id: str, student_id: str) -> Dict[str, Any]:
        """Atomically remove a student from a team and add them to unassigned_students."""
        # Format team_id to include 'TEAM-' prefix if it is numeric/digit
        team_id_str = str(team_id)
        if isinstance(team_id, int) or (isinstance(team_id, str) and team_id.isdigit()):
            team_id_str = f"TEAM-{team_id}"
            
        # 1. Get current team directly by its ID
        team_data = await self._request(f"teams_validation?id=eq.{team_id_str}&limit=1")
        if not team_data:
            # Fallback: scan all teams for this student
            all_teams = await self._request("teams_validation?select=id,uid,members,memberCount,semester_id")
            team_data = []
            for t in (all_teams or []):
                members = t.get("members", []) or []
                if any(str(m.get("id") or m.get("student_id") or m.get("roll") if isinstance(m, dict) else m).strip() == str(student_id).strip() for m in members):
                    team_data = [t]
                    team_id_str = t["id"]
                    break
        
        if not team_data:
            raise Exception("Team not found")
        
        team = team_data[0]
        # Make sure subsequent requests use team_id_str
        team_id = team_id_str
        current_members = team.get("members", []) or []
        
        # 2. Filter out the student (handle both dict members and plain string/int ids)
        removed_student = next(
            (m for m in current_members
             if str(m.get("id") or m.get("student_id") or m.get("roll") if isinstance(m, dict) else m).strip() == str(student_id).strip()),
            None
        )
        if not removed_student:
            return {"message": "Student not in team"}
            
        new_members = [
            m for m in current_members
            if str(m.get("id") or m.get("student_id") or m.get("roll") if isinstance(m, dict) else m).strip() != str(student_id).strip()
        ]
        
        # 3. Drop the membership row. team_memberships is the source of truth and
        #    a trigger rebuilds teams_validation.members / memberCount from it, so
        #    this must NOT patch the jsonb directly — doing both would let the two
        #    drift, and it is the jsonb copy that cannot enforce one-team-per-
        #    student. Removing the row is also what frees the student to join or
        #    create a team again (they reappear in the available_students view).
        team_uid = team.get("uid")
        if team_uid:
            s_roll = str(removed_student.get("roll") or removed_student.get("student_id") or student_id).strip()
            try:
                delete_filter = f"team_uid=eq.{urllib.parse.quote(str(team_uid))}&or=(student_roll.eq.{urllib.parse.quote(str(student_id))},student_roll.eq.{urllib.parse.quote(s_roll)})"
                await self._request(f"team_memberships?{delete_filter}", method="DELETE")
            except Exception as tm_del_err:
                logger.warning(f"Failed deleting team_memberships row: {tm_del_err}")
                await self._request(
                    f"team_memberships?team_uid=eq.{team_uid}&student_roll=eq.{student_id}",
                    method="DELETE",
                )
        else:
            # No uid resolved (should not happen); fall back to the legacy jsonb
            # write so removal still takes effect rather than silently no-opping.
            await self._request(f"teams_validation?id=eq.{team_id}", method="PATCH", body={
                "members": new_members,
                "memberCount": len(new_members)
            })
        
        # 4. Get full student data for unassigned record
        student_info = removed_student if isinstance(removed_student, dict) else {"id": student_id}
        try:
            sr = await self._request(f"students?id=eq.{student_id}&limit=1")
            if sr:
                student_info = sr[0]
        except Exception:
            pass

        semester_id = team.get("semester_id", "")
        unassigned_row = {
            "id": str(student_id),
            "name": student_info.get("name", ""),
            "roll": student_info.get("roll") or student_info.get("student_id") or str(student_id),
            "branch": student_info.get("branch", ""),
            "semester_id": semester_id,
        }
        
        # 5. Upsert into unassigned_students (delete first to avoid conflict)
        try:
            await self._request(f"unassigned_students?id=eq.{student_id}", method="DELETE")
        except Exception:
            pass
            
        await self._request("unassigned_students", method="POST", body=[unassigned_row])
        
        # 6. Force clear all caches
        self._cache.clear()
        try:
            from app.api.student_deps import PROFILE_CACHE
            PROFILE_CACHE.clear()
        except Exception:
            pass
            
        return {"success": True}

    async def add_student_to_team(self, team_id: str, student_id: str) -> Dict[str, Any]:
        """Atomically add a student to a team and remove them from unassigned_students."""
        # Format team_id to include 'TEAM-' prefix if it is numeric/digit
        team_id_str = str(team_id)
        if isinstance(team_id, int) or (isinstance(team_id, str) and team_id.isdigit()):
            team_id_str = f"TEAM-{team_id}"
        
        # 1. Get student from unassigned
        student_data = await self._request(f"unassigned_students?id=eq.{student_id}&limit=1")
        if not student_data:
            raise Exception("Student is not unassigned or doesn't exist")
        
        student = student_data[0]
        
        # 2. Get current team
        team_res = await self._request(f"teams_validation?id=eq.{team_id_str}&limit=1")
        if not team_res:
            raise Exception("Team not found")
        
        team = team_res[0]
        current_members = team.get("members", [])
        
        # Query active semester_config team_size_max
        max_size = 3
        sem_id = team.get("semester_id")
        try:
            sem_query = f"semester_config?id=eq.{sem_id}&limit=1" if sem_id else "semester_config?is_active=eq.true&limit=1"
            sem_res = await self._request(sem_query)
            if sem_res and sem_res[0].get("team_size_max"):
                max_size = int(sem_res[0].get("team_size_max"))
        except Exception:
            pass

        if len(current_members) >= max_size:
            raise Exception(f"Team is already full ({len(current_members)}/{max_size})")
            
        # 3. Add to members array
        m_branch = student.get("branch") or "BTech CSE"
        if m_branch == "B.Tech CS":
            m_branch = "BTech CSE"
        new_member = {
            "id": str(student["id"]),
            "name": student["name"],
            "email": student.get("email") or f"{student.get('roll') or student['id']}@gla.ac.in",
            "branch": m_branch,
            "roll": student.get("roll")
        }
        current_members.append(new_member)
        
        # 4. Insert the membership row. team_memberships is the source of truth
        #    and a trigger rebuilds teams_validation.members / memberCount from
        #    it, so this must NOT patch the jsonb directly.
        #
        #    A unique (semester_id, student_roll) constraint backs this table, so
        #    if the student is already in a team the insert fails atomically —
        #    two concurrent joins cannot both land. Surface that as a clear error
        #    rather than a raw integrity trace.
        team_uid = team.get("uid")
        if not team_uid:
            raise Exception("Team has no uid; cannot record membership")

        try:
            await self._request("team_memberships", method="POST", body=[{
                "team_uid": team_uid,
                "student_roll": str(student["id"]),
                "semester_id": sem_id or team.get("semester_id"),
                "role": "MEMBER",
            }])
        except Exception as e:
            if "team_memberships_one_team_per_student" in str(e) or "23505" in str(e):
                raise Exception("That student is already in a team.")
            raise

        # 5. Remove from unassigned
        await self._request(f"unassigned_students?id=eq.{student_id}", method="DELETE")
        
        # 6. Force clear all caches
        self._cache.clear()
        try:
            from app.api.student_deps import PROFILE_CACHE
            PROFILE_CACHE.clear()
        except Exception:
            pass
            
        return {"success": True}

    async def get_problem_statements(self) -> List[Dict[str, Any]]:
        """Fetch all available problem statements."""
        async def _fetch():
            return await self._request("problem_statements")
        return await self._cached_get("problem_statements_all", 2.0, _fetch())

    async def get_student_preferences(self, student_id: str) -> Optional[Dict[str, Any]]:
        """Fetch project preferences for a student."""
        async def _fetch():
            data = await self._request(f"student_preferences?student_id=eq.{urllib.parse.quote(student_id)}&limit=1")
            return data[0] if data else None
        return await self._cached_get(f"student_preferences:{student_id}", 5.0, _fetch())

    async def save_student_preferences(self, student_id: str, preferences: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Save or update student project preferences."""
        existing = await self.get_student_preferences(student_id)
        
        # Invalidate cache
        self._cache.pop(f"student_preferences:{student_id}", None)
        
        row = {
            "student_id": student_id,
            "preferences": preferences,
            "submitted": True,
            "updated_at": "now()"
        }
        
        if existing:
            return await self._request(f"student_preferences?student_id=eq.{student_id}", method="PATCH", body=row)
        else:
            return await self._request("student_preferences", method="POST", body=[row])

    async def sync_unassigned_students(self) -> List[Dict[str, Any]]:
        """
        Synchronize the unassigned_students table by comparing students vs teams_validation and team_memberships.
        Returns the list of unassigned students.
        Cached for 5.0 seconds so concurrent calls don't re-run full sync.
        """
        async def _fetch():
            try:
                # 1. Get all students
                all_students = await self._request("students")
                
                # 2. Get all teams and team_memberships to extract strictly unique assigned student IDs/rolls/emails
                teams = await self._request("teams_validation")
                assigned_ids = set()

                # Self-healing: Check team_memberships table (source of truth)
                try:
                    tm_rows = await self._request("team_memberships?select=student_roll,team_uid")
                    active_team_uids = {str(t.get("uid")).strip() for t in (teams or []) if t.get("uid")}
                    for tm in (tm_rows or []):
                        s_roll = tm.get("student_roll")
                        team_uid = tm.get("team_uid")
                        # If team_uid no longer exists in teams_validation, delete orphaned membership row
                        if team_uid and active_team_uids and str(team_uid).strip() not in active_team_uids:
                            try:
                                await self._request(f"team_memberships?team_uid=eq.{urllib.parse.quote(str(team_uid))}", method="DELETE")
                            except Exception:
                                pass
                        elif s_roll:
                            assigned_ids.add(str(s_roll).strip().lower())
                except Exception as tm_err:
                    logger.warning(f"Error reading team_memberships in sync_unassigned_students: {tm_err}")

                for team in (teams or []):
                    # Add leader IDs/rolls (only unique ID fields, never display names)
                    for leader_field in ("leader_id", "leader_roll"):
                        lv = team.get(leader_field)
                        if lv and isinstance(lv, str):
                            assigned_ids.add(lv.strip().lower())

                    raw_members = team.get("members", [])
                    if isinstance(raw_members, str):
                        try:
                            import json as _json
                            members = _json.loads(raw_members)
                        except Exception:
                            members = []
                    else:
                        members = raw_members if isinstance(raw_members, list) else []

                    for m in members:
                        if isinstance(m, str):
                            assigned_ids.add(m.strip().lower())
                        elif isinstance(m, dict):
                            # Extract ONLY strict unique identifier fields (id, roll, student_id, email)
                            for k in ("id", "roll", "student_id", "email"):
                                v = m.get(k)
                                if v:
                                    assigned_ids.add(str(v).strip().lower())
                            st = m.get("student")
                            if isinstance(st, dict):
                                for k in ("id", "roll", "student_id", "email"):
                                    v = st.get(k)
                                    if v:
                                        assigned_ids.add(str(v).strip().lower())
                
                # 3. Identify unassigned and assigned students
                unassigned = []
                assigned_student_ids = []
                for s in (all_students or []):
                    s_id = str(s.get("id") or "").strip()
                    s_roll = str(s.get("student_id") or s.get("roll") or s_id).strip()
                    s_email = str(s.get("email") or "").strip()

                    # Match ONLY on strict unique keys (s_id, s_roll, s_email).
                    # NEVER match on s_name to prevent false assignments for students sharing names.
                    is_assigned = (
                        (s_id and s_id.lower() in assigned_ids) or 
                        (s_roll and s_roll.lower() in assigned_ids) or 
                        (s_email and s_email.lower() in assigned_ids)
                    )
                    if not is_assigned:
                        unassigned.append({
                            "id": s_id,
                            "name": s.get("name") or s.get("student_name") or "Student",
                            "roll": s_roll,
                            "student_id": s_roll,
                            "email": s.get("email") or "",
                            "branch": s.get("branch") or "B.Tech CS",
                            "semester_id": s.get("semester_id")
                        })
                    else:
                        if s_id:
                            assigned_student_ids.append(s_id)
                        if s_roll and s_roll != s_id:
                            assigned_student_ids.append(s_roll)
                
                # 4. Clean up any students from unassigned_students table who are actually assigned to a team
                # Batch delete in chunks of 100 to avoid thousands of sequential REST HTTP requests
                if assigned_student_ids:
                    try:
                        assigned_set = list({str(aid).strip() for aid in assigned_student_ids if aid})
                        chunk_size = 100
                        for i in range(0, len(assigned_set), chunk_size):
                            chunk = assigned_set[i:i+chunk_size]
                            chunk_str = ",".join([urllib.parse.quote(x) for x in chunk])
                            await self._request(f"unassigned_students?id=in.({chunk_str})", method="DELETE")
                            await self._request(f"unassigned_students?roll=in.({chunk_str})", method="DELETE")
                    except Exception as del_err:
                        logger.warning(f"Error purging assigned students from unassigned_students: {del_err}")

                # 5. Refresh unassigned_students table with actual unassigned students
                if unassigned:
                    db_unassigned = [{
                        "id": item["id"],
                        "name": item["name"],
                        "roll": item["roll"],
                        "branch": item["branch"],
                        "semester_id": item["semester_id"],
                    } for item in unassigned]
                    await self._request(
                        "unassigned_students?on_conflict=id",
                        method="POST",
                        body=db_unassigned,
                        headers={"Prefer": "resolution=merge-duplicates"},
                    )

                return unassigned

            except Exception as e:
                logger.error(f"Sync unassigned students failed: {e}")
                # Fallback: return current table content
                return await self._request("unassigned_students")

        return await self._cached_get("sync_unassigned_students_all", 5.0, _fetch())

    async def get_join_requests_for_student(self, student_id: str) -> List[Dict[str, Any]]:
        """Fetch all pending join requests sent by admin for a specific student."""
        async def _fetch():
            data = await self._request(
                f"team_join_requests?student_id=eq.{urllib.parse.quote(str(student_id))}&status=eq.pending"
            )
            return data if data else []
        return await self._cached_get(f"join_requests_student:{student_id}", 5.0, _fetch())

    async def accept_join_request(self, request_id: str, student_id: str, team_id: str) -> Dict[str, Any]:
        """Accept a join request: mark as accepted, add student to team, cancel other pending requests."""
        resolved_at = __import__('datetime').datetime.utcnow().isoformat()
        print(f"[accept_join_request] request_id={request_id!r} student_id={student_id!r} team_id={team_id!r}")

        # 1. Mark this request as accepted
        await self._request(
            f"team_join_requests?id=eq.{request_id}",
            method="PATCH",
            body={"status": "accepted", "resolved_at": resolved_at}
        )

        # 2. Cancel all other pending requests for the same student
        await self._request(
            f"team_join_requests?student_id=eq.{urllib.parse.quote(str(student_id))}&status=eq.pending&id=neq.{request_id}",
            method="PATCH",
            body={"status": "cancelled", "resolved_at": resolved_at}
        )

        # 3. Add student to the team's members array
        # Format team_id to include 'TEAM-' prefix if it is numeric/digit
        team_id_str = str(team_id)
        if isinstance(team_id, int) or (isinstance(team_id, str) and team_id.isdigit()):
            team_id_str = f"TEAM-{team_id}"

        team_data = await self._request(f"teams_validation?id=eq.{urllib.parse.quote(team_id_str)}&limit=1")
        print(f"[accept_join_request] team lookup for {team_id_str!r}: {len(team_data) if team_data else 0} rows")
        if team_data:
            team = team_data[0]
            current_members = team.get("members", []) or []
            
            # Normalize list elements safely if they are serialized as string JSON objects (but keep plain strings as is)
            parsed_members = []
            for m in current_members:
                if isinstance(m, str):
                    m_stripped = m.strip()
                    if (m_stripped.startswith("{") and m_stripped.endswith("}")) or (m_stripped.startswith("[") and m_stripped.endswith("]")):
                        try:
                            import json as _json
                            parsed_members.append(_json.loads(m_stripped))
                        except Exception:
                            parsed_members.append(m_stripped)
                    else:
                        parsed_members.append(m_stripped)
                else:
                    parsed_members.append(m)

            already_in = any(
                str(m.get("id") or m.get("roll") or m.get("student_id") if isinstance(m, dict) else m).strip() == str(student_id).strip()
                for m in parsed_members
            )
            print(f"[accept_join_request] already_in={already_in}, current_member_count={len(parsed_members)}")
            if not already_in:
                # Try to get student info from unassigned_students
                student_info = await self._request(f"unassigned_students?id=eq.{urllib.parse.quote(str(student_id))}&limit=1")
                if student_info:
                    s = student_info[0]
                    new_member = {
                        "id": str(s.get("id")),
                        "name": s.get("name", ""),
                        "branch": s.get("branch", "B.Tech CS"),
                        "roll": s.get("roll", str(student_id))
                    }
                else:
                    # Fallback: get from students table
                    student_info_fb = await self._request(f"students?id=eq.{urllib.parse.quote(str(student_id))}&limit=1")
                    if student_info_fb:
                        s = student_info_fb[0]
                        new_member = {
                            "id": str(s.get("id")),
                            "name": s.get("name", ""),
                            "branch": s.get("branch", "B.Tech CS"),
                            "roll": s.get("student_id") or str(student_id)
                        }
                    else:
                        new_member = {"id": str(student_id), "name": "", "branch": "B.Tech CS", "roll": str(student_id)}

                print(f"[accept_join_request] adding member: {new_member}")

                # Record the membership, not the jsonb. team_memberships is the
                # source of truth and a trigger rebuilds members/memberCount from
                # it. Its unique (semester_id, student_roll) constraint is what
                # makes acceptance safe: if the student joined another team in
                # the meantime, or two leaders accept them at the same moment,
                # exactly one insert succeeds and the rest fail atomically.
                team_uid = team.get("uid")
                if not team_uid:
                    raise Exception("Team has no uid; cannot record membership")

                try:
                    await self._request("team_memberships", method="POST", body=[{
                        "team_uid": team_uid,
                        "student_roll": str(student_id),
                        "semester_id": team.get("semester_id"),
                        "role": "MEMBER",
                    }])
                except Exception as e:
                    if "team_memberships_one_team_per_student" in str(e) or "23505" in str(e):
                        raise Exception(
                            "This student has already joined another team; "
                            "the request can no longer be accepted."
                        )
                    raise

                # Remove from unassigned_students
                try:
                    await self._request(f"unassigned_students?id=eq.{urllib.parse.quote(str(student_id))}", method="DELETE")
                except Exception as del_err:
                    print(f"[accept_join_request] warn: could not delete from unassigned: {del_err}")
        else:
            print(f"[accept_join_request] WARNING: team {team_id!r} not found in teams_validation!")

        # 4. Clear all caches
        self._cache.clear()
        try:
            from app.api.student_deps import PROFILE_CACHE
            PROFILE_CACHE.clear()
        except Exception:
            pass

        return {"success": True}

    async def decline_join_request(self, request_id: str, student_id: str) -> Dict[str, Any]:
        """Decline (cancel) a join request."""
        resolved_at = __import__('datetime').datetime.utcnow().isoformat()
        await self._request(
            f"team_join_requests?id=eq.{request_id}",
            method="PATCH",
            body={"status": "declined", "resolved_at": resolved_at}
        )
        # Invalidate cache for this student's requests
        self._cache.pop(f"join_requests_student:{student_id}", None)
        return {"success": True}


supabase_client = SupabaseRESTClient()
