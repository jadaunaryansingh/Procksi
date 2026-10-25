import uuid
from datetime import date as date_type
from typing import List, Optional, Tuple, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.schedule import Schedule
from app.models.team import Team
from app.models.panel import Panel
from app.models.panel_mentor import PanelMentor
from app.models.semester_config import SemesterConfig
from app.repositories.schedule_repo import schedule_repo
from app.repositories.team_repo import team_repo
from app.repositories.panel_repo import panel_repo
from app.repositories.semester_repo import semester_repo

class ScheduleService:
    @staticmethod
    async def generate_schedules(
        db: AsyncSession,
        semester_id: uuid.UUID,
        dates: List[str],
        time_slots: List[str],
        rooms: List[str],
        mode: str
    ) -> List[Schedule]:
        semester = await semester_repo.get(db, semester_id)
        if not semester:
            raise ValueError("Semester not found")
        if semester.is_locked:
            raise ValueError("Semester is locked; scheduling not permitted")

        # Get validated teams for this semester
        teams_result = await db.execute(
            select(Team).where(
                Team.semester_id == semester_id,
                Team.is_validated == True,
            )
        )
        teams = teams_result.scalars().all()

        panels = await panel_repo.get_multi(db) # Filter by semester if needed
        # Assuming panel_repo should have a way to filter by semester
        panels = [p for p in panels if p.semester_id == semester_id]

        if not panels:
            raise ValueError("No panels found for this semester")

        occupied_panel_slots: set = set()
        occupied_room_slots: set = set()
        occupied_team_slots: set = set()

        existing_schedules = await schedule_repo.get_multi(db, limit=1000)
        for s in existing_schedules:
            if s.semester_id == semester_id:
                occupied_panel_slots.add((s.panel_id, s.date, s.time_slot))
                occupied_room_slots.add((s.room, s.date, s.time_slot))
                occupied_team_slots.add((s.team_id, s.date, s.time_slot))

        slots = [
            (d, ts, r)
            for d in dates
            for ts in time_slots
            for r in rooms
        ]

        created = []
        slot_idx = 0
        panel_cycle = 0

        for team in teams:
            assigned = False
            attempts = 0
            while not assigned and attempts < len(slots) * len(panels):
                si = (slot_idx + attempts) % len(slots)
                d_str, ts, room = slots[si]
                try:
                    d = date_type.fromisoformat(d_str)
                except ValueError:
                    attempts += 1
                    continue

                panel = panels[panel_cycle % len(panels)]

                if (panel.id, d, ts) in occupied_panel_slots:
                    panel_cycle += 1
                    attempts += 1
                    continue
                if (room, d, ts) in occupied_room_slots:
                    attempts += 1
                    continue
                if (team.id, d, ts) in occupied_team_slots:
                    attempts += 1
                    continue

                if team.mentor_id:
                    conflict_result = await db.execute(
                        select(PanelMentor).where(
                            PanelMentor.panel_id == panel.id,
                            PanelMentor.mentor_id == team.mentor_id,
                        )
                    )
                    if conflict_result.scalar_one_or_none():
                        panel_cycle += 1
                        attempts += 1
                        continue

                schedule_in = {
                    "team_id": team.id,
                    "panel_id": panel.id,
                    "semester_id": semester_id,
                    "room": room,
                    "date": d,
                    "time_slot": ts,
                    "mode": mode,
                }
                schedule = await schedule_repo.create(db, obj_in=schedule_in)
                
                occupied_panel_slots.add((panel.id, d, ts))
                occupied_room_slots.add((room, d, ts))
                occupied_team_slots.add((team.id, d, ts))
                created.append(schedule)
                slot_idx = (si + 1) % len(slots)
                panel_cycle += 1
                assigned = True

            if not assigned:
                raise ValueError(f"Could not assign a conflict-free slot for team {team.id}")

        return created

    @staticmethod
    async def update_schedule(
        db: AsyncSession,
        schedule_id: uuid.UUID,
        room: Optional[str] = None,
        date: Optional[str] = None,
        time_slot: Optional[str] = None,
        mode: Optional[str] = None
    ) -> Schedule:
        schedule = await schedule_repo.get(db, schedule_id)
        if not schedule:
            raise ValueError("Schedule not found")

        semester = await semester_repo.get(db, schedule.semester_id)
        if semester and semester.is_locked:
            raise ValueError("Semester is locked; schedule changes not permitted")

        update_data = {}
        if room:
            new_date = date_type.fromisoformat(date) if date else schedule.date
            new_ts = time_slot or schedule.time_slot
            
            conflict_result = await db.execute(
                select(Schedule).where(
                    Schedule.room == room,
                    Schedule.date == new_date,
                    Schedule.time_slot == new_ts,
                    Schedule.id != schedule_id,
                )
            )
            if conflict_result.scalar_one_or_none():
                raise ValueError("Room is already booked for this date and time slot")
            update_data["room"] = room

        if date:
            update_data["date"] = date_type.fromisoformat(date)
        if time_slot:
            update_data["time_slot"] = time_slot
        if mode:
            update_data["mode"] = mode

        return await schedule_repo.update(db, db_obj=schedule, obj_in=update_data)
