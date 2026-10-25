"""Time-based firing for the Communication Agent.

Lets the PRD's sequenced triggers ("kickoff now, team-formation a few days later")
run on their own. A scheduled row lives in ``scheduled_communications``; a
background poller (see ``app.main``) calls :meth:`CommunicationScheduler.run_due`
on an interval and dispatches anything whose ``send_at`` has passed.

The timing/mapping logic (``is_due``, ``build_sequence``, ``to_send_kwargs``) is
pure and unit-tested; the DB-bound methods are thin wrappers.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

from app.services.communication_service import SEGMENTS, TEMPLATES, CommunicationService

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.scheduled_communication import ScheduledCommunication

PENDING = "pending"
SENT = "sent"
FAILED = "failed"
CANCELLED = "cancelled"


# --------------------------------------------------------------------------- #
# Pure helpers (no DB)
# --------------------------------------------------------------------------- #
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC so comparisons never raise."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def is_due(send_at: datetime, now: Optional[datetime] = None) -> bool:
    return _as_aware(send_at) <= _as_aware(now or utcnow())


def effective_segment(segment: Optional[str], template_code: Optional[str]) -> Optional[str]:
    """The segment that will actually be used: explicit, else the template default."""
    if segment:
        return segment
    return TEMPLATES.get(template_code or "", {}).get("default_segment")


def validate_target(segment: Optional[str], template_code: Optional[str]) -> str:
    """Resolve + validate the audience for a scheduled item; raises ValueError."""
    seg = effective_segment(segment, template_code)
    if not seg:
        raise ValueError("A segment or a template_code with a default segment is required")
    if seg not in SEGMENTS:
        raise ValueError(f"Unknown audience segment: '{seg}'")
    return seg


def build_sequence(steps: list[dict], *, base: Optional[datetime] = None) -> list[dict]:
    """Expand ``[{...step..., offset_days}]`` into concrete ``send_at`` plans.

    e.g. ``[{kickoff, 0}, {team_formation, 3}]`` -> kickoff now, team-formation
    three days later.
    """
    base = base or utcnow()
    plans = []
    for step in steps:
        offset = float(step.get("offset_days", 0) or 0)
        plan = {k: v for k, v in step.items() if k != "offset_days"}
        plan["send_at"] = base + timedelta(days=offset)
        plans.append(plan)
    return plans


def to_send_kwargs(sched: "ScheduledCommunication") -> dict[str, Any]:
    """Map a scheduled row onto CommunicationService.send keyword args."""
    return dict(
        segment=sched.segment,
        template_code=sched.template_code,
        subject=sched.subject,
        body=sched.body,
        context=sched.context or {},
        team_id=sched.team_id,
        semester_id=sched.semester_id,
    )


def serialize(sched: "ScheduledCommunication") -> dict[str, Any]:
    return {
        "id": str(sched.id),
        "segment": sched.segment,
        "template_code": sched.template_code,
        "subject": sched.subject,
        "send_at": sched.send_at.isoformat() if sched.send_at else None,
        "status": sched.status,
        "sent_at": sched.sent_at.isoformat() if sched.sent_at else None,
        "result": sched.result,
    }


# --------------------------------------------------------------------------- #
# DB-bound orchestration
# --------------------------------------------------------------------------- #
class CommunicationScheduler:
    @staticmethod
    async def schedule(
        db: "AsyncSession",
        *,
        send_at: datetime,
        segment: Optional[str] = None,
        template_code: Optional[str] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        context: Optional[dict] = None,
        team_id: Optional[uuid.UUID] = None,
        semester_id: Optional[uuid.UUID] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> "ScheduledCommunication":
        from app.models.scheduled_communication import ScheduledCommunication

        validate_target(segment, template_code)  # fail fast on a bad audience
        row = ScheduledCommunication(
            send_at=send_at,
            segment=segment,
            template_code=template_code,
            subject=subject,
            body=body,
            context=context or {},
            team_id=team_id,
            semester_id=semester_id,
            created_by=created_by,
            status=PENDING,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @classmethod
    async def schedule_sequence(
        cls,
        db: "AsyncSession",
        steps: list[dict],
        *,
        base: Optional[datetime] = None,
        semester_id: Optional[uuid.UUID] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> list["ScheduledCommunication"]:
        created = []
        for plan in build_sequence(steps, base=base):
            created.append(
                await cls.schedule(
                    db,
                    send_at=plan["send_at"],
                    segment=plan.get("segment"),
                    template_code=plan.get("template_code"),
                    subject=plan.get("subject"),
                    body=plan.get("body"),
                    context=plan.get("context"),
                    semester_id=semester_id,
                    created_by=created_by,
                )
            )
        return created

    @staticmethod
    async def list_scheduled(
        db: "AsyncSession", *, status: Optional[str] = PENDING, limit: int = 100
    ) -> list["ScheduledCommunication"]:
        from sqlalchemy import select

        from app.models.scheduled_communication import ScheduledCommunication

        q = select(ScheduledCommunication)
        if status:
            q = q.where(ScheduledCommunication.status == status)
        q = q.order_by(ScheduledCommunication.send_at).limit(limit)
        return list((await db.execute(q)).scalars().all())

    @staticmethod
    async def cancel(db: "AsyncSession", sched_id: uuid.UUID) -> bool:
        from app.models.scheduled_communication import ScheduledCommunication

        row = await db.get(ScheduledCommunication, sched_id)
        if row is None or row.status != PENDING:
            return False
        row.status = CANCELLED
        db.add(row)
        await db.commit()
        return True

    @classmethod
    async def run_due(
        cls,
        db: "AsyncSession",
        *,
        now: Optional[datetime] = None,
        mailer=None,
    ) -> dict[str, int]:
        """Dispatch every pending item whose time has come. Returns a summary.

        Assumes a single poller instance (the dev/default deployment). Each item
        is committed individually so one failure can't roll back the rest.
        """
        from sqlalchemy import select

        from app.models.scheduled_communication import ScheduledCommunication

        now = now or utcnow()
        rows = (
            await db.execute(
                select(ScheduledCommunication)
                .where(
                    ScheduledCommunication.status == PENDING,
                    ScheduledCommunication.send_at <= now,
                )
                .order_by(ScheduledCommunication.send_at)
            )
        ).scalars().all()

        fired = failed = 0
        for sched in rows:
            try:
                result = await CommunicationService.send(
                    db, admin_id=sched.created_by, mailer=mailer, **to_send_kwargs(sched)
                )
                sched.status = SENT
                sched.sent_at = utcnow()
                sched.result = {"sent": result["sent"]}
                fired += 1
            except Exception as e:  # noqa: BLE001 - record and continue
                sched.status = FAILED
                sched.result = {"error": str(e)}
                failed += 1
            db.add(sched)
            await db.commit()

        return {"due": len(rows), "fired": fired, "failed": failed}
