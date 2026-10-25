from app.repositories.base import BaseRepository
from app.models.team_member import TeamMember
from app.schemas.team import TeamMemberCreate, TeamMemberUpdate

class TeamMemberRepository(BaseRepository[TeamMember, TeamMemberCreate, TeamMemberUpdate]):
    pass

team_member_repo = TeamMemberRepository(TeamMember)
