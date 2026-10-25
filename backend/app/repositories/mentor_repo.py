from app.repositories.base import BaseRepository
from app.models.mentor import Mentor
from app.schemas.mentor import MentorCreate, MentorUpdate

class MentorRepository(BaseRepository[Mentor, MentorCreate, MentorUpdate]):
    pass

mentor_repo = MentorRepository(Mentor)
