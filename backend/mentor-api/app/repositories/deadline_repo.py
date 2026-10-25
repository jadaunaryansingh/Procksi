from app.repositories.base import BaseRepository
from app.models.deadline import Deadline
from app.schemas.governance import DeadlineCreate, DeadlineUpdate

class DeadlineRepository(BaseRepository[Deadline, DeadlineCreate, DeadlineUpdate]):
    pass

deadline_repo = DeadlineRepository(Deadline)
