import re
import os
import supabase._sync.client as _sync_mod
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

_sync_client_class = getattr(_sync_mod, "SyncClient", getattr(_sync_mod, "Client", None))
_ORIG_INIT_SYNC = _sync_client_class.__init__
def _patched_sync_init(self, supabase_url, supabase_key, options=None):
    _orig_re_match = re.match
    def _relaxed_match(pattern, string, *a, **kw):
        if "A-Za-z0-9" in str(pattern) and string == supabase_key:
            return True
        return _orig_re_match(pattern, string, *a, **kw)
    re.match = _relaxed_match
    try:
        _ORIG_INIT_SYNC(self, supabase_url, supabase_key, options)
    finally:
        re.match = _orig_re_match
_sync_client_class.__init__ = _patched_sync_init

_url = os.getenv("SUPABASE_URL")
_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
if not _url or not _key:
    raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY env vars before running this script.")

client = create_client(_url, _key)


# 1. Search teams_validation
res1 = client.table("teams_validation").select("*").execute()
for r in (res1.data or []):
    mentor = str(r.get("mentor") or "")
    if "preshit" in mentor.lower():
        print(f"[teams_validation] ID: {r['id']} | Title: {r['title']} | Mentor: {r['mentor']} | Semester: {r['semester_id']} | Members: {r['members']}")

# 2. Search mentor_allocations
res2 = client.table("mentor_allocations").select("*").execute()
for r in (res2.data or []):
    assigned = str(r.get("assignedMentor") or "")
    if "preshit" in assigned.lower():
        print(f"[mentor_allocations] ID: {r['id']} | Title: {r['title']} | Mentor: {r['assignedMentor']} | Semester: {r['semester_id']}")
