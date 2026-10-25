from app.repositories.base import BaseRepository
from app.models.team import Team
from app.schemas.team import TeamCreate, TeamUpdate

class TeamRepository(BaseRepository[Team, TeamCreate, TeamUpdate]):
    pass

team_repo = TeamRepository(Team)
