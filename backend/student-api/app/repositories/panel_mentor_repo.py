from app.repositories.base import BaseRepository
from app.models.panel_mentor import PanelMentor
from app.schemas.panel import PanelMentorCreate, PanelMentorUpdate

class PanelMentorRepository(BaseRepository[PanelMentor, PanelMentorCreate, PanelMentorUpdate]):
    pass

panel_mentor_repo = PanelMentorRepository(PanelMentor)
