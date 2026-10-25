from app.repositories.base import BaseRepository
from app.models.panel import Panel
from app.schemas.panel import PanelCreate, PanelUpdate

class PanelRepository(BaseRepository[Panel, PanelCreate, PanelUpdate]):
    pass

panel_repo = PanelRepository(Panel)
