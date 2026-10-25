import io
import uuid
import pandas as pd
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.student import Student
from app.repositories.student_repo import student_repo
from app.schemas.student import StudentCreate, StudentUpdate

class StudentService:
    @staticmethod
    async def get_students_with_count(
        db: AsyncSession, 
        *, 
        skip: int = 0, 
        limit: int = 100,
        year: Optional[int] = None,
        branch: Optional[str] = None,
        section: Optional[str] = None,
        status: Optional[str] = None,
        semester_id: Optional[uuid.UUID] = None,
        search: Optional[str] = None
    ) -> tuple[List[Student], int]:
        # Merge pagination fetching and total counting into a single query via OVER()
        count_query = func.count().over().label('full_count')
        query = select(Student, count_query)

        if year:
            query = query.where(Student.year == year)
        if branch:
            query = query.where(Student.branch == branch)
        if section:
            query = query.where(Student.section == section)
        if status:
            query = query.where(Student.status == status)
        if semester_id:
            query = query.where(Student.semester_id == semester_id)
        if search:
            query = query.where(
                (Student.name.ilike(f"%{search}%"))
                | (Student.student_id.ilike(f"%{search}%"))
            )

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        rows = result.all()

        if not rows:
            return [], 0

        total_count = rows[0].full_count
        students = [row.Student for row in rows]
        
        return students, total_count

    @classmethod
    def _get_val(cls, row: Dict[str, Any], possible_keys: List[str]) -> Any:
        keys = list(row.keys())
        # 1. Try exact match (alphanumeric only)
        for k in keys:
            clean_k = "".join(c for c in str(k).lower() if c.isalnum())
            for pk in possible_keys:
                clean_pk = "".join(c for c in str(pk).lower() if c.isalnum())
                if clean_k == clean_pk:
                    return row[k]
        
        # 2. Try substring match as fallback
        for k in keys:
            clean_k = "".join(c for c in str(k).lower() if c.isalnum())
            for pk in possible_keys:
                clean_pk = "".join(c for c in str(pk).lower() if c.isalnum())
                if clean_pk in ("email", "emailid", "mail") and ("email" in clean_k or "mail" in clean_k or "gmail" in clean_k):
                    return row[k]
                if clean_pk == "name" and ("name" in clean_k or "candidate" in clean_k or "student" in clean_k):
                    return row[k]
                if clean_pk in ("rollnumber", "studentid") and ("roll" in clean_k or "id" in clean_k or "university" in clean_k or "reg" in clean_k):
                    return row[k]
        return None

    @classmethod
    def _parse_upload(cls, file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))
        
        df.columns = [str(c).strip() for c in df.columns]
        
        cleaned_rows = []
        for row in df.to_dict(orient="records"):
            sid = str(cls._get_val(row, ['Student ID', 'Roll Number', 'Roll', 'id', 'student_id', 'University Roll No', 'Reg No', 'Registration Number', 'RollNo', 'StudentID', 'University Roll Number']) or "").strip()
            email = str(cls._get_val(row, ['Email', 'Email ID', 'Mail', 'Email Address', 'EmailID', 'EmailAddress', 'Gmail', 'Official Email', 'Personal Email', 'E-Mail']) or "").strip()
            name = str(cls._get_val(row, ['Name', 'Student Name', 'Full Name', 'Member Name', 'First Name', 'FirstName', 'Candidate Name', 'Student', 'Candidate']) or "").strip()
            section = str(cls._get_val(row, ['Section', 'Sec', 'Batch', 'Group']) or "A").strip()
            branch = str(cls._get_val(row, ['Branch', 'Course', 'Program', 'Department', 'Dept']) or "B.Tech CS").strip()
            
            # Default fallback for email if not found
            if sid and not email:
                email = f"{sid}@example.com"
                
            cleaned_rows.append({
                "student_id": sid,
                "email": email,
                "name": name,
                "section": section,
                "branch": branch
            })
        return cleaned_rows

    @classmethod
    async def preview_upload(cls, db: AsyncSession, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        rows = cls._parse_upload(file_bytes, filename)
        valid, duplicates, invalid = [], [], []

        # Optimization: Fetch existing IDs and emails in one go
        existing_ids_result = await db.execute(select(Student.student_id))
        existing_ids = {r[0] for r in existing_ids_result.fetchall()}

        existing_emails_result = await db.execute(select(Student.email))
        existing_emails = {r[0] for r in existing_emails_result.fetchall()}

        for row in rows:
            sid = str(row.get("student_id", "")).strip()
            email = str(row.get("email", "")).strip()
            name = str(row.get("name", "")).strip()

            if not sid or not email or not name:
                invalid.append({"row": row, "reason": "Missing required fields"})
                continue

            if sid in existing_ids or email in existing_emails:
                duplicates.append(row)
            else:
                valid.append(row)

        return {"valid": valid, "duplicates": duplicates, "invalid": invalid}

    @classmethod
    async def save_upload(
        cls, db: AsyncSession, file_bytes: bytes, filename: str,
        semester_id: uuid.UUID
    ) -> int:
        from app.models.semester_config import SemesterConfig
        semester = await db.scalar(select(SemesterConfig).where(SemesterConfig.id == semester_id))
        if not semester:
            raise ValueError("Invalid semester ID")

        branch = semester.branch
        academic_year = semester.academic_level

        rows = cls._parse_upload(file_bytes, filename)
        created = 0
        
        for row in rows:
            sid = str(row.get("student_id", "")).strip()
            email = str(row.get("email", "")).strip()
            if not sid or not email:
                continue

            existing = await db.execute(
                select(Student).where(
                    (Student.student_id == sid) | (Student.email == email),
                )
            )
            if existing.scalar_one_or_none():
                continue

            student_in = StudentCreate(
                student_id=sid,
                name=str(row.get("name", "")).strip(),
                email=email,
                year=academic_year,
                branch=branch,
                section=str(row.get("section", "A")).strip(),
                status="active",
                semester_id=semester_id
            )
            await student_repo.create(db, obj_in=student_in)
            created += 1
        return created
