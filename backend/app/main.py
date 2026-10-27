import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, student, student_portal, semester, proposal, team, mentor, schedule, evaluation, result, communication, governance, panel
from app.core.config import settings

logger = logging.getLogger("procksi.scheduler")

# How often the Communication Agent checks for due scheduled sends.
_SCHEDULER_POLL_SECONDS = int(os.getenv("PROCKSI_SCHEDULER_POLL_SECONDS", "60"))
_SCHEDULER_ENABLED = os.getenv("PROCKSI_SCHEDULER_ENABLED", "1") != "0"


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
    title="Procksi Backend",
    description="Project Management System – Admin Dashboard API",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
allowed_origins = [origin.strip() for origin in settings.FRONTEND_URL.split(",") if origin.strip()]

# Add all common localhost origins for development
localhost_origins = [
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
]

for origin in localhost_origins:
    if origin not in allowed_origins:
        allowed_origins.append(origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _add_cors(request: Request, response: JSONResponse) -> JSONResponse:
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# ---------------------------------------------------------------------------
# Global HTTP exception handler – ensures all errors use the standard shape
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        # Pass through structured detail if already set
        if isinstance(exc.detail, dict):
            return _add_cors(request, JSONResponse(status_code=exc.status_code, content=exc.detail))
        return _add_cors(request, JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {"code": "ERROR", "message": str(exc.detail)},
            },
        ))
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


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Procksi Backend"}
