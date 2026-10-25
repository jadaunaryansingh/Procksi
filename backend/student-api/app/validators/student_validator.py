import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.student_repo import student_repo

class StudentValidator:
    @staticmethod
    async def validate_student_exists(db: AsyncSession, student_id: uuid.UUID) -> bool:
        student = await student_repo.get(db, student_id)
        return student is not None

    @staticmethod
    def validate_roll_number(roll_number: str) -> bool:
        # Basic validation for roll number format
        return len(roll_number) >= 5 and roll_number.isalnum()
