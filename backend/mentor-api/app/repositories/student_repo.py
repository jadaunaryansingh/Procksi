from app.repositories.base import BaseRepository
from app.models.student import Student
from app.schemas.student import StudentCreate, StudentUpdate

class StudentRepository(BaseRepository[Student, StudentCreate, StudentUpdate]):
    pass

student_repo = StudentRepository(Student)
