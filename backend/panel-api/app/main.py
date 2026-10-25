"""
FastAPI backend for the Panel (and mentor) dashboard using Supabase.
"""

import app.patch_supabase
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.supabase_client import get_supabase_service
from app.routers import auth, evaluation, panel, admin, mentor
from app.scheduler import start_scheduler, scheduler
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.report_path.mkdir(parents=True, exist_ok=True)
    
    client = get_supabase_service()
    if client is not None:
        # Fail LOUD if the service key can't bypass RLS (the 2026-08-28 outage:
        # a stale/disabled key -> PostgREST treats reads as anon -> [] everywhere).
        try:
            probe = client.table("students").select("id").limit(1).execute()
            if not probe.data:
                print("STARTUP CHECK FAILED: service key cannot read `students` (got []). "
                      "SUPABASE_SERVICE_KEY is likely stale/disabled; PostgREST is acting as anon. "
                      "Recreate this container with a valid sb_secret_ key.")
            else:
                print("Startup check OK: service key reads `students`.")
        except Exception as e:
            print(f"STARTUP CHECK errored (cannot reach Supabase): {e}")
        try:
            seed_if_empty(client)
        except Exception as e:
            print(f"Error seeding database: {e}")
    else:
        print("Warning: Supabase service client not configured at lifespan startup.")
    
    # Start scheduler service
    await start_scheduler()
    
    yield
    
    # Stop scheduler service
    await scheduler.stop()


# The real frontends this API serves. `allow_origin_regex=r"https?://.*"` used
# to sit alongside this list below and match literally any origin, defeating an
# allowlist entirely when `allow_credentials=True`. Removed; this list is now
# the only gate, and every hand-rolled CORS header block checks membership in
# it instead of blindly reflecting whatever Origin header the caller sent.
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
    "http://localhost:3003",
    "http://127.0.0.1:3003",
    "https://student.glapms.in",
    "https://admin.glapms.in",
    "https://mentor.glapms.in",
    "https://panel.glapms.in",
    "https://glapms.in",
    "https://www.glapms.in",
    "http://student.glapms.in",
    "http://admin.glapms.in",
    "http://mentor.glapms.in",
    "http://panel.glapms.in",
    "http://glapms.in",
    "http://www.glapms.in",
]


def _add_cors(request: Request, response: JSONResponse) -> JSONResponse:
    """Helper: attach CORS headers to any JSONResponse, only for an allowlisted origin."""
    origin = request.headers.get("origin")
    if origin and origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all exception handler: ensures CORS headers are present on 500 responses
    so the frontend can read the error detail instead of seeing a CORS block."""
    import traceback
    print(f"[UNHANDLED EXCEPTION] {request.method} {request.url.path}")
    traceback.print_exc()
    response = JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )
    return _add_cors(request, response)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def check_freeze_and_locks_middleware(request: Request, call_next):
    from fastapi.responses import JSONResponse, Response
    from app.supabase_client import get_supabase_service
    import re

    if request.method == "OPTIONS":
        origin = request.headers.get("origin")
        headers = {
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Origin, User-Agent, apikey, X-Requested-With, x-admin-api-key",
            "Access-Control-Max-Age": "86400",
        }
        if origin and origin in ALLOWED_ORIGINS:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
        return Response(status_code=204, headers=headers)

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        path = request.url.path
        if "/auth" not in path:
            try:
                client = get_supabase_service()
                if client is not None:
                    active_res = client.table("semester_config").select("*").eq("is_active", True).execute()
                    if active_res.data:
                        team_id = None
                        match = re.search(r"/evaluation/(?:draft|session|submission|receipt)/(\d+)", path)
                        if match:
                            team_id = int(match.group(1))
                        elif path == "/evaluation/panel":
                            try:
                                body_bytes = await request.body()
                                async def receive():
                                    return {"type": "http.request", "body": body_bytes, "more_body": False}
                                request._receive = receive
                                import json
                                body_json = json.loads(body_bytes)
                                team_id = body_json.get("team_id")
                            except Exception:
                                pass
                        
                        sems_to_check = []
                        if team_id:
                            from app.db_helpers import resolve_team_string_id
                            team_str = resolve_team_string_id(client, int(team_id))
                            res_val = client.table("teams_validation").select("semester_id").eq("id", team_str).execute()
                            team_sem_id = res_val.data[0].get("semester_id") if res_val.data else None
                            if team_sem_id:
                                sems_to_check = [s for s in active_res.data if s["id"] == team_sem_id]
                        
                        if not sems_to_check:
                            sems_to_check = active_res.data

                        for sem in sems_to_check:
                            if sem.get("is_locked"):
                                return _add_cors(request, JSONResponse(
                                    status_code=403,
                                    content={"detail": "System is frozen. No modifications allowed."}
                                ))
                            if sem.get("lock_marks") and "/evaluation" in path:
                                return _add_cors(request, JSONResponse(
                                    status_code=403,
                                    content={"detail": "Marks are locked. No evaluations are allowed."}
                                ))
            except Exception as e:
                print(f"Panel middleware lock check error: {e}")

    response = await call_next(request)
    origin = request.headers.get("origin")
    if origin and origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response

app.include_router(auth.router)
app.include_router(panel.router)
app.include_router(mentor.router)
app.include_router(evaluation.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.app_env}


@app.get("/health/supabase")
def health_supabase():
    """Verifies URL + keys against Supabase (Storage API ping)."""
    client = get_supabase_service()
    if client is None:
        return {
            "configured": False,
            "detail": "Set SUPABASE_URL and SUPABASE_SERVICE_KEY in backend/.env",
        }
    try:
        client.storage.list_buckets()
        return {"configured": True, "reachable": True}
    except Exception as e:
        return {"configured": True, "reachable": False, "error": str(e)}

# Trigger reload
