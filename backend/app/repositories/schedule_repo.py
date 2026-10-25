from app.repositories.base import BaseRepository
from app.models.schedule import Schedule
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate

class ScheduleRepository(BaseRepository[Schedule, ScheduleCreate, ScheduleUpdate]):
    pass

schedule_repo = ScheduleRepository(Schedule)
