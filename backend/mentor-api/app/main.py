import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import auth, student, semester, proposal, team, mentor, schedule, evaluation, result, communication, governance, panel, mentor_portal
from app.core.config import settings
from app.core.rate_limit import limiter

logger = logging.getLogger("pms.scheduler")

# How often the Communication Agent checks for due scheduled sends.
_SCHEDULER_POLL_SECONDS = int(os.getenv("PMS_SCHEDULER_POLL_SECONDS", "60"))
_SCHEDULER_ENABLED = False  # Disabled to avoid prepared statement issues with Supabase's pgbouncer


async def _scheduler_loop() -> None:
    """Background poller: fire any due scheduled communications on an interval."""
    from app.core.database import async_session_factory
    from app.services.communication_scheduler import CommunicationScheduler

    while True:
        try:
            async with async_session_factory() as db:
                summary = await CommunicationScheduler.run_due(db)
                if summary["fired"] or summary["failed"]:
                    logger.info("scheduler tick: %s", summary)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a bad tick must not kill the loop
            logger.exception("scheduler tick failed")
        await asyncio.sleep(_SCHEDULER_POLL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from app.core.rest_db import is_configured
        if not is_configured():
            from sqlalchemy import text
            from app.core.database import engine
            async with engine.begin() as conn:
                await conn.execute(text("ALTER TABLE public.mentors ADD COLUMN IF NOT EXISTS phone VARCHAR(50);"))
            logger.info("Checked/added phone column to mentors table successfully.")
    except Exception as e:
        logger.warning(f"Could not alter mentors table on startup (non-fatal): {e}")

    # Warm the connection pool before serving traffic.
    #
    # Establishing the first asyncpg connection to the Supabase pooler costs
    # ~4.3s (TLS handshake + pooler auth); every connection after that is ~0.9s.
    # That one-off cost lands on whichever user request happens to be first, and
    # it sits right at SQL_FALLBACK_TIMEOUT (5s) in mentor_portal — so it would
    # regularly trip the circuit breaker and pin the portal on the slower REST
    # path for 120s, even though Postgres is perfectly reachable.
    #
    # Paying it here means no request ever does. Non-fatal by design: if the
    # database is genuinely unreachable the REST fallback still serves the
    # portal, exactly as before.
    try:
        import time as _time
        from sqlalchemy import text as _text
        from app.core.database import engine as _engine
        _t0 = _time.perf_counter()
        async with _engine.connect() as conn:
            await conn.execute(_text("SELECT 1"))
        logger.info("Database pool warmed in %.2fs", _time.perf_counter() - _t0)
    except Exception as e:
        logger.warning("Could not warm the database pool (non-fatal, REST fallback still applies): %s", e)

    # Fail LOUD if the Supabase service key can't bypass RLS (2026-08-28 outage
    # failure mode: stale/disabled key -> PostgREST acts as anon -> [] everywhere).
    try:
        from app.core import rest_db
        if rest_db.is_configured():
            rows = await rest_db.select("students", columns="id", limit=1)
            if not rows:
                logger.error(
                    "STARTUP CHECK FAILED: service key cannot read `students` (got []). "
                    "SUPABASE_SERVICE_KEY is likely stale/disabled; PostgREST is acting as anon. "
                    "Recreate this container with a valid sb_secret_ key."
                )
            else:
                logger.info("Startup check OK: service key reads `students`.")
    except Exception as e:
        logger.error("STARTUP CHECK errored (cannot reach Supabase): %s", e)

    task = None
    if _SCHEDULER_ENABLED:
        task = asyncio.create_task(_scheduler_loop())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="PMS Backend",
    description="Project Management System – Admin Dashboard API",
    version="1.0.0",
    lifespan=lifespan,
)

# Per-IP rate limiting for costly/abusable endpoints (unmetered GitHub-analysis
# spend) that have no other throttle — audit finding L-2. Individual routes
# opt in with @limiter.limit(...); everything else is unaffected.
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
if settings.FRONTEND_URL:
    for origin in settings.FRONTEND_URL.split(","):
        if origin.strip() and origin.strip() not in allowed_origins:
            allowed_origins.append(origin.strip())

# `allow_origin_regex=r"https?://.*"` used to sit alongside allow_origins and
# match literally any origin, defeating the allowlist entirely when
# `allow_credentials=True`. Removed; allowed_origins is now the only gate, and
# every hand-rolled CORS header block below checks membership in it too
# instead of blindly reflecting whatever Origin header the caller sent.
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
        if "/auth" not in path and "/api/auth" not in path:
            try:
                from app.core.cache import peek, set_value
                hit, sems = peek("system_lock_status", 15.0)
                if not hit:
                    import httpx
                    headers = {
                        "apikey": settings.SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}"
                    }
                    # Multiple batches (different B.Tech years) can be active at
                    # once — fetch them all, don't limit(1).
                    url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/semester_config?is_active=eq.true&select=is_locked,lock_teams"
                    async with httpx.AsyncClient(timeout=4.0) as client:
                        r = await client.get(url, headers=headers)
                        sems = r.json() if (r.status_code == 200 and r.json()) else []
                    set_value("system_lock_status", sems)

                sems = sems or []
                # Global gate only: block when EVERY active batch carries the flag
                # (a true system-wide freeze). Per-batch enforcement is the job of
                # the endpoint-level semester-scoped checks.
                if sems and all(s.get("is_locked") for s in sems):
                    return _add_cors(request, JSONResponse(
                        status_code=403,
                        content={"detail": "System is frozen. No modifications allowed."}
                    ))
                if sems and all(s.get("lock_teams") for s in sems) and any(k in path for k in ("/team", "/join-request")):
                    return _add_cors(request, JSONResponse(
                        status_code=403,
                        content={"detail": "Teams are locked. No modifications allowed."}
                    ))
            except Exception as e:
                print(f"Mentor middleware lock check error: {e}")
    return await call_next(request)


# ---------------------------------------------------------------------------
# Global HTTP exception handler – ensures all errors use the standard shape
# ---------------------------------------------------------------------------
from fastapi import HTTPException

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
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
    return _add_cors(request, JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred"},
        },
    ))

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(student.router)
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
app.include_router(mentor_portal.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "PMS Backend"}

# Trigger reload
