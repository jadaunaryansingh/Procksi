from app.repositories.base import BaseRepository
from app.models.admin import Admin
from app.schemas.admin import AdminCreate, AdminUpdate

class AdminRepository(BaseRepository[Admin, AdminCreate, AdminUpdate]):
    pass

admin_repo = AdminRepository(Admin)
