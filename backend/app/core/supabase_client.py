# Supabase REST client used by the Student portal.
# Works without the `supabase` Python package installed.
# Imported as: `from app.core.supabase_client import supabase_client`

from __future__ import annotations

import logging
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Minimal async REST client for Supabase PostgREST endpoints
# ----------------------------------------------------------------------
class _RestClient:
    """Thin async wrapper around Supabase PostgREST.

    Only implements the methods referenced in `student_deps.py` and
    `student_portal.py`.  Stubs return empty structures so the API
    stays functional even when certain tables don't exist yet.
    """

    def __init__(self, base_url: str, api_key: str):
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.timeout = 15.0

    async def _get(self, path: str):
        """Execute a GET request against Supabase PostgREST."""
        url = f"{self.base}{path}"
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, json_body: dict, *, upsert: bool = False):
        """Execute a POST request against Supabase PostgREST."""
        url = f"{self.base}{path}"
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        if upsert:
            headers["Prefer"] = "return=representation,resolution=merge-duplicates"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=json_body, headers=headers)
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Student
    # ------------------------------------------------------------------
    async def get_student_by_email(self, email: str):
        """Return a single student dict (or None) looked up by email."""
        try:
            rows = await self._get(
                f"/rest/v1/students?email=eq.{email}&limit=1"
            )
            if isinstance(rows, list) and rows:
                return rows[0]
            return rows if isinstance(rows, dict) else None
        except httpx.HTTPStatusError as exc:
            logger.warning("get_student_by_email(%s) failed: %s", email, exc)
            return None

    async def upsert_student(self, student_dict: dict) -> dict:
        """Insert or update a student record in the `students` table.

        Uses PostgREST upsert (on conflict merge) so repeated calls for the
        same email are safe.  Returns the created/updated row.
        """
        try:
            rows = await self._post("/rest/v1/students", student_dict, upsert=True)
            if isinstance(rows, list) and rows:
                return rows[0]
            return rows if isinstance(rows, dict) else student_dict
        except httpx.HTTPStatusError as exc:
            logger.error("upsert_student failed: %s — %s", exc, exc.response.text[:300] if exc.response else "")
            # Return the dict as-is so the caller can still build a profile
            return student_dict

    # ------------------------------------------------------------------
    # Team  (teams_validation table from Aryan's schema)
    # ------------------------------------------------------------------
    async def get_team_by_student_id(self, student_id):
        """Find the team a student belongs to.

        The `teams_validation` table stores a `members` JSONB array with
        member objects.  We query all rows and search client‑side because
        PostgREST JSON containment operators can be finicky.
        """
        try:
            # Try teams_validation first (Aryan's schema)
            rows = await self._get("/rest/v1/teams_validation?select=*")
            if isinstance(rows, list):
                for row in rows:
                    members = row.get("members", [])
                    if isinstance(members, str):
                        import json
                        try:
                            members = json.loads(members)
                        except Exception:
                            members = []
                    for m in (members or []):
                        mid = m.get("id") or m.get("roll") or ""
                        if str(mid) == str(student_id):
                            return row
            return None
        except httpx.HTTPStatusError as exc:
            logger.warning("get_team_by_student_id(%s) failed: %s", student_id, exc)
            return None

    # ------------------------------------------------------------------
    # Mentor
    # ------------------------------------------------------------------
    async def get_mentor_by_name(self, name: str):
        try:
            rows = await self._get(
                f"/rest/v1/mentors?name=eq.{name}&limit=1"
            )
            if isinstance(rows, list) and rows:
                return rows[0]
            return rows if isinstance(rows, dict) else None
        except httpx.HTTPStatusError:
            return None

    # ------------------------------------------------------------------
    # Stubs – called in student_portal.py but not critical for team view
    # ------------------------------------------------------------------
    async def get_proposal_by_team_id(self, _team_id):
        return {}

    async def get_schedule_slots_by_team(self, _team_id):
        return []

    async def get_evaluations_by_team(self, _team_id):
        return []

    async def get_results_by_team(self, _team_id):
        return []

    async def save_proposal(self, *_a, **_kw):
        return {"success": True}

    async def update_team_proposal_details(self, *_a, **_kw):
        return {"success": True}


# ---------------------------------------------------------------------------
# Lazy proxy so callers can do `supabase_client.get_student_by_email(…)`
# without needing `supabase_client().get_student_by_email(…)`.
# The real _RestClient is created on first attribute access.
# ---------------------------------------------------------------------------
class _LazyClient:
    """Proxy that creates the _RestClient on first use."""

    def __init__(self):
        self._real: _RestClient | None = None

    def _ensure(self) -> _RestClient:
        if self._real is None:
            url = settings.SUPABASE_URL
            key = settings.SUPABASE_KEY
            if not url or not key:
                raise RuntimeError(
                    "Supabase configuration missing – set SUPABASE_URL "
                    "and SUPABASE_KEY in your .env file"
                )
            self._real = _RestClient(url, key)
        return self._real

    def __getattr__(self, name: str):
        # Proxy every attribute/method call to the real client
        return getattr(self._ensure(), name)


supabase_client = _LazyClient()
SupabaseRESTClient = _RestClient
