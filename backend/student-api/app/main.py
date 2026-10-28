from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import auth, student, semester, proposal, team, mentor, schedule, evaluation, result, communication, governance, panel, student_portal
from app.core.config import settings
from app.core.rate_limit import limiter

app = FastAPI(
    title="Procksi Backend",
    description="Project Management System – Admin Dashboard API",
    version="1.0.0",
)

# Per-IP rate limiting for costly/abusable endpoints (unmetered LLM spend,
# bulk writes) that have no other throttle — audit finding L-2. Individual
# routes opt in with @limiter.limit(...); everything else is unaffected.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:3003",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:5176",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
    "http://127.0.0.1:3003",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://127.0.0.1:5176",
    "https://www.procksi.in",
    "https://procksi.in",
    "https://student.procksi.in",
    "https://admin.procksi.in",
    "https://panel.procksi.in",
    "https://mentor.procksi.in",
    "https://procksi-main.vercel.app",
    "https://procksi-student.vercel.app",
    "https://procksi-admin.vercel.app",
    "https://procksi-panel.vercel.app",
    "https://procksi-mentor.vercel.app",
]
if settings.FRONTEND_URL:
    for origin in settings.FRONTEND_URL.split(","):
        if origin.strip() and origin.strip() not in allowed_origins:
            allowed_origins.append(origin.strip())

# `allow_origin_regex=r"https?://.*"` used to sit alongside allow_origins and
# match literally any origin, defeating the allowlist entirely when
# `allow_credentials=True`. Removed; allowed_origins is now the only gate, and
# every hand-rolled CORS header block below checks membership in it too
# instead of blindly reflecting whatever Origin header the caller sent (or, as
# `_add_cors` used to do for a missing Origin, falling back to a bare "*").
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _add_cors(request: Request, response: JSONResponse) -> JSONResponse:
    origin = request.headers.get("origin")
    if origin and origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response

@app.middleware("http")
async def check_freeze_and_locks_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        from fastapi.responses import Response
        origin = request.headers.get("origin")
        headers = {
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Origin, User-Agent, apikey, X-Requested-With",
            "Access-Control-Max-Age": "86400",
        }
        if origin and origin in allowed_origins:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
        return Response(status_code=204, headers=headers)

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        path = request.url.path
        if "/auth" not in path and "/api/auth" not in path and "/admin/publish-results" not in path:
            try:
                from app.core.supabase_client import supabase_client
                active_sems = await supabase_client._request("semester_config?is_active=eq.true&limit=1")
                if active_sems:
                    sem = active_sems[0]
                    if sem.get("is_locked"):
                        return _add_cors(request, JSONResponse(
                            status_code=403,
                            content={"detail": "System is frozen. No modifications allowed."}
                        ))
                    if sem.get("lock_teams") and any(k in path for k in ("/team", "/join-request")):
                        return _add_cors(request, JSONResponse(
                            status_code=403,
                            content={"detail": "Teams are locked. No modifications allowed."}
                        ))
            except Exception as e:
                print(f"Student middleware lock check error: {e}")

    response = await call_next(request)
    origin = request.headers.get("origin")
    if origin and origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# ---------------------------------------------------------------------------
# Global Exception Handlers
# ---------------------------------------------------------------------------
from fastapi import HTTPException

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Only change format for student portal endpoints to ensure others are unaffected
    if request.url.path.startswith("/api/student"):
        if exc.status_code == 401 or (exc.status_code == 403 and exc.detail == "Not authenticated"):
            return _add_cors(request, JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized", "code": "SESSION_EXPIRED"}
            ))
        if isinstance(exc.detail, dict):
            return _add_cors(request, JSONResponse(status_code=exc.status_code, content=exc.detail))
        return _add_cors(request, JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        ))

    # Legacy handler behavior for other portals
    if isinstance(exc.detail, dict):
        return _add_cors(request, JSONResponse(status_code=exc.status_code, content=exc.detail))
    return _add_cors(request, JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {"code": "ERROR", "message": str(exc.detail)},
        },
    ))


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger("uvicorn.error").error(f"Global Exception: {str(exc)}", exc_info=True)

    return _add_cors(request, JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {"code": "INTERNAL_SERVER_ERROR", "message": f"Unexpected error: {str(exc)}"},
        },
    ))

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(auth.student_auth_router)
app.include_router(student.router)
app.include_router(student_portal.router)
app.include_router(semester.router)
app.include_router(proposal.router)
app.include_router(team.router)
app.include_router(mentor.router)
app.include_router(schedule.router)
app.include_router(evaluation.router)
app.include_router(result.router)
app.include_router(communication.router)
app.include_router(governance.router)
app.include_router(panel.router)


@app.on_event("startup")
async def startup_event():
    import asyncio
    import logging
    from app.core.github_sync_scheduler import start_github_sync

    # Fail LOUD if the Supabase service key can't bypass RLS. This is exactly the
    # failure mode of the 2026-08-28 outage: a stale/disabled key makes PostgREST
    # fall back to `anon`, every RLS-protected read returns [], and the portal
    # dies with "Student record not found". A silent [] is indistinguishable from
    # "no data", so check it explicitly at boot.
    try:
        from app.core.supabase_client import supabase_client
        rows = await supabase_client._request("students?select=id&limit=1")
        if not rows:
            logging.getLogger("uvicorn").error(
                "STARTUP CHECK FAILED: service key cannot read `students` (got []). "
                "SUPABASE_SERVICE_KEY is likely stale/disabled and PostgREST is "
                "treating requests as anon. The portal will not work. Recreate the "
                "container so it picks up a valid sb_secret_ key."
            )
        else:
            logging.getLogger("uvicorn").info("Startup check OK: service key reads `students`.")
    except Exception as e:
        logging.getLogger("uvicorn").error(f"STARTUP CHECK errored (cannot reach Supabase): {e}")

    # Start synchronization worker in the background, checking every 60 seconds
    asyncio.create_task(start_github_sync(interval_seconds=60))
    logging.getLogger("uvicorn").info("Successfully started background GitHub analyzer synchronization worker.")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Procksi Backend"}

# Trigger reload
