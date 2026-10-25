import uuid
import random
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.semester_config import SemesterConfig
from app.models.student import Student
from app.models.mentor import Mentor
from app.models.audit_log import AuditLog
from app.repositories.team_repo import team_repo
from app.repositories.semester_repo import semester_repo
from app.repositories.audit_log_repo import audit_log_repo

class TeamService:
    @staticmethod
    async def list_teams_with_members(
        db: AsyncSession, page: int = 1, limit: int = 100,
        branch: Optional[str] = None,
        mentor_id: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        semester_id: Optional[uuid.UUID] = None,
    ) -> Tuple[List[dict], int]:
        # Build base query with eager-loads
        query = (
            select(Team)
            .options(
                selectinload(Team.members).selectinload(TeamMember.student),
                selectinload(Team.mentor),
                selectinload(Team.proposals)
            )
        )

        # Apply filters
        if mentor_id:
            query = query.where(Team.mentor_id == uuid.UUID(mentor_id))
        if status:
            if status == "valid":
                query = query.where(Team.is_validated == True)
            else:
                query = query.where(Team.status == status)
        if search:
            query = query.where(
                Team.project_title.ilike(f"%{search}%") | Team.name.ilike(f"%{search}%")
            )
        if semester_id:
            query = query.where(Team.semester_id == semester_id)

        # Count total (for pagination)
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # Paginate
        query = query.offset((page - 1) * limit).limit(limit)
        result = await db.execute(query)
        teams = result.scalars().all()

        # If filtering by branch, do post-filter (branch is on student, not team)
        if branch:
            teams = [
                t for t in teams
                if any(m.student and m.student.branch == branch for m in t.members)
            ]
            total = len(teams)
        
        data = []
        for t in teams:
            # Get latest proposal if it exists
            latest_proposal = None
            if t.proposals:
                latest_proposal = sorted(t.proposals, key=lambda x: x.id, reverse=True)[0]

            data.append({
                "id": str(t.id),
                "name": t.name,
                "project_title": t.project_title,
                "mentor_id": str(t.mentor_id) if t.mentor_id else None,
                "mentor": {
                    "id": str(t.mentor.id),
                    "name": t.mentor.name,
                    "expertise": t.mentor.expertise
                } if t.mentor else None,
                "proposal": {
                    "id": str(latest_proposal.id),
                    "title": latest_proposal.title,
                    "description": latest_proposal.description,
                } if latest_proposal else None,
                "semester_id": str(t.semester_id),
                "is_validated": t.is_validated,
                "is_overridden": t.is_overridden,
                "validation_status": "valid" if t.is_validated else t.status, # Derived status for frontend logic
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "students": [
                    {
                        "id": str(m.student.id),
                        "student_id": m.student.student_id,
                        "name": m.student.name,
                        "email": m.student.email,
                        "branch": m.student.branch,
                        "section": m.student.section,
                        "role": m.role,
                        "is_leader": m.role == "LEADER"
                    }
                    for m in t.members
                ],
            })
        return data, total

    @staticmethod
    async def get_team_stats(db: AsyncSession, semester_id: Optional[uuid.UUID] = None) -> dict:
        """
        Return the count of teams in each status: valid, pending, invalid
        """
        # Optimized: Single query with group by
        query = select(Team.status, func.count()).group_by(Team.status)
        if semester_id:
            query = query.where(Team.semester_id == semester_id)
        result = await db.execute(query)
        stats_map = {row[0]: row[1] for row in result.all()}
        
        return {
            "valid": stats_map.get("valid", 0),
            "pending": stats_map.get("pending", 0),
            "invalid": stats_map.get("invalid", 0),
            "total": sum(stats_map.values())
        }

    @staticmethod
    async def validate_team(db: AsyncSession, team_id: uuid.UUID) -> Team:
        # Get active semester config to enforce current rules
        semester = await semester_repo.get_active(db)
        if not semester:
            # Fallback to team's own semester if no global active one exists
            query = (
                select(Team)
                .where(Team.id == team_id)
                .options(selectinload(Team.semester), selectinload(Team.members))
            )
            result = await db.execute(query)
            team = result.scalar_one_or_none()
            if not team:
                raise ValueError("Team not found")
            semester = team.semester
        else:
            query = select(Team).where(Team.id == team_id).options(selectinload(Team.members))
            result = await db.execute(query)
            team = result.scalar_one_or_none()
            if not team:
                raise ValueError("Team not found")

        if not semester:
            raise ValueError("Semester configuration not found for validation")

        if semester.is_locked:
            raise ValueError("Semester is locked; team validation not permitted")

        member_count = len(team.members)
        
        # Determine status automatically
        new_status = "valid"
        if member_count < semester.team_size_min or member_count > semester.team_size_max:
            new_status = "invalid"

        return await team_repo.update(db, db_obj=team, obj_in={
            "is_validated": True if new_status == "valid" else False,
            "status": new_status
        })

    @staticmethod
    async def manual_override(db: AsyncSession, team_id: uuid.UUID, admin_id: str, reason: str) -> Team:
        team = await team_repo.get(db, team_id)
        if not team:
            raise ValueError("Team not found")

        team = await team_repo.update(db, db_obj=team, obj_in={
            "is_validated": True, 
            "status": "valid",
            "is_overridden": True
        })

        # Log the override
        await audit_log_repo.create(db, obj_in={
            "admin_id": admin_id,
            "action": f"manual_override: {reason}",
            "entity_type": "team",
            "entity_id": str(team.id)
        })

        return team

    @staticmethod
    async def validate_all_teams(db: AsyncSession) -> int:
        """
        Run validation for all teams against the active semester config.
        """
        # Get active semester config
        semester = await semester_repo.get_active(db)
        if not semester:
            raise ValueError("No active semester configuration found; cannot perform validation")

        # Get all teams with their members
        query = select(Team).options(selectinload(Team.members))
        result = await db.execute(query)
        teams = result.scalars().all()
        
        count = 0
        for team in teams:
            # Skip overridden teams
            if team.is_overridden:
                continue

            member_count = len(team.members)
            new_status = "valid"
            if member_count < semester.team_size_min or member_count > semester.team_size_max:
                new_status = "invalid"

            team.status = new_status
            team.is_validated = (new_status == "valid")
            count += 1
        
        await db.commit()
        return count

    @staticmethod
    async def get_unassigned_students(db: AsyncSession) -> List[Student]:
        # Unassigned students: active students not in any team
        query = (
            select(Student)
            .outerjoin(TeamMember, Student.id == TeamMember.student_id)
            .where(TeamMember.id == None)
            .where(Student.status == "active")
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def bulk_assign_students(db: AsyncSession, admin_id: str) -> int:
        semester = await semester_repo.get_active(db)
        if not semester:
            raise ValueError("No active semester configuration found.")

        if semester.is_locked:
            raise ValueError("Semester is locked; cannot form new teams.")

        unassigned = await TeamService.get_unassigned_students(db)
        if not unassigned:
            return 0
            
        chunk_size = semester.team_size_max
        teams_created = 0
        
        # Group into basic chunks
        for i in range(0, len(unassigned), chunk_size):
            chunk = unassigned[i:i + chunk_size]
            
            # Create a team
            new_team_name = f"Auto Formed {uuid.uuid4().hex[:6].upper()}"
            new_team = Team(
                semester_id=semester.id,
                name=new_team_name,
                project_title=f"Pending ({new_team_name})",
                status="valid" if len(chunk) >= chunk_size else "invalid",
                is_validated=True if len(chunk) >= chunk_size else False
            )
            db.add(new_team)
            await db.flush() # get new_team.id
            
            # Add members
            for idx, student in enumerate(chunk):
                member = TeamMember(
                    team_id=new_team.id,
                    student_id=student.id,
                    role="LEADER" if idx == 0 else "MEMBER"
                )
                db.add(member)

            teams_created += 1

        await audit_log_repo.create(db, obj_in={
            "admin_id": admin_id,
            "action": f"bulk_assign: created {teams_created} teams for {len(unassigned)} students",
            "entity_type": "team",
            "entity_id": "bulk"
        })

        await db.commit()
        return teams_created

    @staticmethod
    async def force_assign_student(db: AsyncSession, student_id: uuid.UUID, team_id: Optional[uuid.UUID] = None) -> Team:
        """
        Force assign a student.
        - If team_id is provided: add student to that team (if team_size < max).
        - If team_id is None: create a new team with avg/max team size using random unassigned students.
        """
        student = await db.execute(select(Student).where(Student.id == student_id))
        student = student.scalar_one_or_none()
        if not student:
            raise ValueError("Student not found")
        
        existing = await db.execute(select(TeamMember).where(TeamMember.student_id == student_id))
        if existing.scalar_one_or_none():
            raise ValueError("Student already in a team")

        if team_id:
            # Add to existing team (with size check)
            team = await db.execute(
                select(Team)
                .where(Team.id == team_id)
                .options(selectinload(Team.members), selectinload(Team.semester))
            )
            team = team.scalar_one_or_none()
            if not team:
                raise ValueError("Target team not found")

            semester = team.semester
            if semester and len(team.members) >= semester.team_size_max:
                raise ValueError(f"Team already at max size ({semester.team_size_max})")
            
            member = TeamMember(team_id=team.id, student_id=student.id, role="MEMBER")
            db.add(member)
            await db.commit()
            return team
        else:
            # Create a new team with avg/max team size using random unassigned students
            semester = await semester_repo.get_active(db)
            if not semester:
                raise ValueError("Active semester required")

            # Calculate target team size: average of min and max (rounded up)
            target_size = (semester.team_size_min + semester.team_size_max + 1) // 2
            if target_size < 1:
                target_size = semester.team_size_max

            # Get all other unassigned students to fill the team
            all_unassigned = await TeamService.get_unassigned_students(db)
            # Remove current student from list (they'll be the leader)
            other_unassigned = [s for s in all_unassigned if s.id != student_id]

            # Pick random students to fill the team
            fill_count = min(target_size - 1, len(other_unassigned))
            selected_others = random.sample(other_unassigned, fill_count) if fill_count > 0 else []

            total_members = 1 + len(selected_others)

            new_team_name = f"Formed {uuid.uuid4().hex[:6].upper()}"
            new_team = Team(
                semester_id=semester.id,
                name=new_team_name,
                project_title=f"Pending ({new_team_name})",
                status="valid" if total_members >= semester.team_size_min else "invalid",
                is_validated=total_members >= semester.team_size_min
            )
            db.add(new_team)
            await db.flush()

            # Add leader
            leader_member = TeamMember(team_id=new_team.id, student_id=student.id, role="LEADER")
            db.add(leader_member)

            # Add other members
            for s in selected_others:
                member = TeamMember(team_id=new_team.id, student_id=s.id, role="MEMBER")
                db.add(member)

            await db.commit()
            return new_team

    @staticmethod
    async def create_custom_team(db: AsyncSession, leader_id: uuid.UUID, member_ids: List[uuid.UUID]) -> Team:
        semester = await semester_repo.get_active(db)
        if not semester:
            raise ValueError("Active semester required")

        total_members = 1 + len(member_ids)
        if total_members > semester.team_size_max:
            raise ValueError(f"Team size exceeds maximum allowed ({semester.team_size_max})")

        # Verify students
        all_ids = [leader_id] + member_ids
        students_query = select(Student).where(Student.id.in_(all_ids))
        result = await db.execute(students_query)
        students = result.scalars().all()
        if len(students) != len(all_ids):
            raise ValueError("Some students not found")

        # Check existing teams
        existing = await db.execute(select(TeamMember).where(TeamMember.student_id.in_(all_ids)))
        if existing.scalars().first():
            raise ValueError("One or more students already in a team")

        new_team_name = f"Custom Formed {uuid.uuid4().hex[:6].upper()}"
        new_team = Team(
            semester_id=semester.id,
            name=new_team_name,
            project_title=f"Pending ({new_team_name})",
            status="valid" if total_members >= semester.team_size_min else "invalid",
            is_validated=total_members >= semester.team_size_min
        )
        db.add(new_team)
        await db.flush()

        # Add leader
        leader_member = TeamMember(team_id=new_team.id, student_id=leader_id, role="LEADER")
        db.add(leader_member)

        # Add members
        for s_id in member_ids:
            member = TeamMember(team_id=new_team.id, student_id=s_id, role="MEMBER")
            db.add(member)

        await db.commit()
        return new_team

    @staticmethod
    async def force_assign_to_team(db: AsyncSession, student_id: uuid.UUID, team_id: uuid.UUID) -> dict:
        """
        Assign a specific student to a specific team, checking team_size_max.
        Returns team info.
        """
        student = await db.execute(select(Student).where(Student.id == student_id))
        student = student.scalar_one_or_none()
        if not student:
            raise ValueError("Student not found")

        existing = await db.execute(select(TeamMember).where(TeamMember.student_id == student_id))
        if existing.scalar_one_or_none():
            raise ValueError("Student already in a team")

        team = await db.execute(
            select(Team)
            .where(Team.id == team_id)
            .options(selectinload(Team.members), selectinload(Team.semester))
        )
        team = team.scalar_one_or_none()
        if not team:
            raise ValueError("Target team not found")

        # Use active semester rules
        semester = await semester_repo.get_active(db)
        if not semester:
            # Fallback to team's own
            semester = team.semester

        if semester and len(team.members) >= semester.team_size_max:
            raise ValueError(f"Team is full ({len(team.members)}/{semester.team_size_max})")

        member = TeamMember(team_id=team.id, student_id=student.id, role="MEMBER")
        db.add(member)
        await db.commit()

        return {
            "team_id": str(team.id),
            "team_name": team.name,
            "student_id": str(student.id),
            "student_name": student.name,
            "new_size": len(team.members) + 1
        }

    @staticmethod
    async def get_filter_options(db: AsyncSession) -> dict:
        """
        Return distinct branch, mentor, and status values for filters.
        """
        # Get distinct branches from students who are in teams
        branch_query = (
            select(Student.branch)
            .distinct()
            .where(Student.status == "active")
            .order_by(Student.branch)
        )
        branch_result = await db.execute(branch_query)
        branches = [row[0] for row in branch_result.all() if row[0]]

        # Get mentors who have teams
        mentor_query = (
            select(Mentor.id, Mentor.name)
            .join(Team, Mentor.id == Team.mentor_id)
            .distinct()
            .order_by(Mentor.name)
        )
        mentor_result = await db.execute(mentor_query)
        mentors = [{"id": str(row[0]), "name": row[1]} for row in mentor_result.all()]

        # Get distinct project domains (from project titles - extract common words)
        # For now, return all unique project titles as "domains"
        domain_query = (
            select(Team.project_title)
            .distinct()
            .where(Team.project_title != "Pending Proposal")
            .order_by(Team.project_title)
        )
        domain_result = await db.execute(domain_query)
        domains = [row[0] for row in domain_result.all() if row[0]]

        return {
            "branches": branches,
            "mentors": mentors,
            "domains": domains,
            "statuses": ["valid", "pending", "invalid"]
        }

    @staticmethod
    async def get_project_conflicts(db: AsyncSession) -> List[dict]:
        """
        Detect project title repetitions across teams in the active semester.
        Uses NVIDIA NIM AI Semantic Matching to catch different words with the same meaning.
        """
        from app.services.ai_service import get_embedding, cosine_similarity

        semester = await semester_repo.get_active(db)
        if not semester:
            return []

        # Get all teams for active semester that have an actual title
        query = (
            select(Team)
            .where(Team.semester_id == semester.id)
            .where(~Team.project_title.ilike("Pending%"))
        )
        result = await db.execute(query)
        teams = result.scalars().all()
        
        # Pre-fill missing embeddings dynamically
        dirty = False
        for team in teams:
            if not team.embedding or len(team.embedding) == 0:
                emb = await get_embedding(team.project_title)
                team.embedding = emb
                dirty = True
        
        if dirty:
            await db.commit()
            
        conflicts = []
        covered_ids = set()
        
        for i, t1 in enumerate(teams):
            if t1.id in covered_ids:
                continue
            
            group = [t1]
            t1_title = t1.project_title.lower().strip()
            
            for j in range(i + 1, len(teams)):
                t2 = teams[j]
                if t2.id in covered_ids:
                    continue
                
                t2_title = t2.project_title.lower().strip()
                
                # Check exact text match first
                is_exact = t1_title == t2_title
                
                # AI Semantic Match
                similarity = 1.0 if is_exact else cosine_similarity(t1.embedding, t2.embedding)
                
                if similarity >= 0.75: # Strict semantic similarity threshold
                    t2._match_type = "Exact Text" if is_exact else f"Semantic ({similarity*100:.1f}%)"
                    group.append(t2)
            
            if len(group) > 1:
                # Add all IDs in this group to covered
                for t in group:
                    covered_ids.add(t.id)
                
                # Find worst match type for label
                match_type = "Exact Text"
                for t in group[1:]:
                    if getattr(t, "_match_type", "") != "Exact Text":
                        match_type = getattr(t, "_match_type", "High Semantic")
                        break

                conflicts.append({
                    "id": f"CONFLICT-{t1.id.hex[:4].upper()}",
                    "title": t1.project_title,
                    "teams": [t.name for t in group],
                    "team_ids": [str(t.id) for t in group],
                    "similarity": match_type,
                    "status": "Blocked",
                    "date": t1.created_at.strftime('%b %d, %Y') if t1.created_at else "Unknown"
                })
        
        return conflicts

    @staticmethod
    async def get_detailed_unassigned(db: AsyncSession) -> List[dict]:
        """
        Return unassigned students with more context (e.g. why they are unassigned).
        Reason is inferred from enrollment timing relative to the semester.
        """
        from app.models.team_member import TeamMember
        from app.models.deadline import Deadline

        semester = await semester_repo.get_active(db)

        # Get active students not in any team
        query = (
            select(Student)
            .outerjoin(TeamMember, Student.id == TeamMember.student_id)
            .where(TeamMember.id == None)
            .where(Student.status == "active")
        )
        result = await db.execute(query)
        students = result.scalars().all()

        # Try to get the team formation deadline for reason inference
        team_deadline = None
        if semester:
            dl_query = select(Deadline).where(
                Deadline.semester_id == semester.id,
                Deadline.type == "team",
            )
            dl_result = await db.execute(dl_query)
            team_deadline = dl_result.scalar_one_or_none()

        data = []
        for s in students:
            # Infer reason from timing
            if team_deadline and s.created_at and s.created_at > team_deadline.due_date:
                reason = "Late enrollment"
            elif semester and s.created_at and s.created_at > semester.created_at:
                reason = "No team formed"
            else:
                reason = "No team formed"

            data.append({
                "id": str(s.id),
                "roll": s.student_id,
                "name": s.name,
                "branch": s.branch,
                "section": s.section,
                "reason": reason,
                "pastTeam": "--",
            })
        return data

    @staticmethod
    async def get_allocation_audit_logs(
        db: AsyncSession, page: int = 1, limit: int = 20
    ) -> tuple[list[dict], int]:
        """
        Fetch audit logs related to project allocations and team operations.
        Joins with admin table to include the admin's name.
        """
        from app.models.admin import Admin

        entity_types = ["project_allocation", "team"]
        skip = (page - 1) * limit

        logs, total = await audit_log_repo.get_logs_by_entity_types(
            db, entity_types, skip=skip, limit=limit
        )

        # Batch-fetch admin names
        admin_ids = list({log.admin_id for log in logs})
        admin_map = {}
        if admin_ids:
            admin_q = select(Admin.id, Admin.name).where(Admin.id.in_(admin_ids))
            admin_result = await db.execute(admin_q)
            admin_map = {row[0]: row[1] for row in admin_result.all()}

        formatted = []
        for log in logs:
            formatted.append({
                "id": str(log.id),
                "admin_id": str(log.admin_id),
                "admin_name": admin_map.get(log.admin_id, "System"),
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": str(log.entity_id),
                "timestamp": log.timestamp.isoformat(),
            })

        return formatted, total

    @staticmethod
    async def get_allocation_summary(db: AsyncSession) -> dict:
        """
        Compute allocation-level stats in a single call:
        - locked_ps: number of project title conflicts
        - stranded_students: students without a team
        - total_overrides: number of allocation audit logs
        - total_teams: total teams in active semester
        - allocation_rate: % of active students assigned to a team
        """
        semester = await semester_repo.get_active(db)
        if not semester:
            return {
                "locked_ps": 0,
                "stranded_students": 0,
                "total_overrides": 0,
                "total_teams": 0,
                "allocation_rate": 100.0,
            }

        # Total teams
        team_count_q = select(func.count()).select_from(Team).where(Team.semester_id == semester.id)
        total_teams = (await db.execute(team_count_q)).scalar() or 0

        # Total active students
        student_count_q = select(func.count()).select_from(Student).where(Student.status == "active")
        total_students = (await db.execute(student_count_q)).scalar() or 0

        # Unassigned students
        unassigned_q = (
            select(func.count())
            .select_from(Student)
            .outerjoin(TeamMember, Student.id == TeamMember.student_id)
            .where(TeamMember.id == None)
            .where(Student.status == "active")
        )
        stranded = (await db.execute(unassigned_q)).scalar() or 0

        # Conflicts (reuse logic but just count)
        conflicts = await TeamService.get_project_conflicts(db)
        locked_ps = len(conflicts)

        # Override count
        override_q = (
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_type.in_(["project_allocation", "team"]))
        )
        total_overrides = (await db.execute(override_q)).scalar() or 0

        # Allocation rate
        assigned = total_students - stranded
        allocation_rate = round((assigned / total_students * 100), 1) if total_students > 0 else 100.0

        return {
            "locked_ps": locked_ps,
            "stranded_students": stranded,
            "total_overrides": total_overrides,
            "total_teams": total_teams,
            "allocation_rate": allocation_rate,
        }


