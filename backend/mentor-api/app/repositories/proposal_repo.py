from app.repositories.base import BaseRepository
from app.models.proposal import Proposal
from app.schemas.proposal import ProposalCreate, ProposalUpdate

class ProposalRepository(BaseRepository[Proposal, ProposalCreate, ProposalUpdate]):
    pass

proposal_repo = ProposalRepository(Proposal)
