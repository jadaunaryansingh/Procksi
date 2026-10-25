from app.repositories.base import BaseRepository
from app.models.evaluation import Evaluation
from app.schemas.evaluation import EvaluationCreate, EvaluationUpdate

class EvaluationRepository(BaseRepository[Evaluation, EvaluationCreate, EvaluationUpdate]):
    pass

evaluation_repo = EvaluationRepository(Evaluation)
