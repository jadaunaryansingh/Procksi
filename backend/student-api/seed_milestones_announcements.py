import asyncio
import uuid
from datetime import datetime
from app.core.database import async_session_factory
from app.models.announcement import Announcement
from app.models.milestone import Milestone

async def seed():
    async with async_session_factory() as db:
        # 1. Clear existing announcements/milestones to allow fresh seeding
        from sqlalchemy import delete
        await db.execute(delete(Milestone))
        await db.execute(delete(Announcement))

        # 2. Add announcements
        ann1 = Announcement(
            id=uuid.uuid4(),
            title="Project Registration Open",
            body="Students can now form teams and select their problem statements.",
            type="general",
            is_active=True
        )
        ann2 = Announcement(
            id=uuid.uuid4(),
            title="Guidelines Updated",
            body="The project evaluation parameters have been updated. Check the portal for details.",
            type="general",
            is_active=True
        )
        ann3 = Announcement(
            id=uuid.uuid4(),
            title="1st Presentation Scheduled",
            body="Your 1st Presentation is scheduled for 10th April at 10:00 AM in Room 401.",
            type="schedule",
            is_active=True
        )
        
        db.add_all([ann1, ann2, ann3])

        # 3. Add milestones for Team 98
        team_id = 98
        semester_id = "aa4bfacd-c016-4be0-a5de-761b59cd302e"

        m1 = Milestone(
            id=uuid.uuid4(),
            team_id=team_id,
            semester_id=semester_id,
            title="Project Scope & Requirements",
            description="Define project goals, modules, and stack.",
            deadline=datetime.strptime("2026-03-25 23:59:59", "%Y-%m-%d %H:%M:%S"),
            status="completed",
            github_url="https://github.com/PMS-2026/team-aa4bfacd"
        )
        m2 = Milestone(
            id=uuid.uuid4(),
            team_id=team_id,
            semester_id=semester_id,
            title="Mid-Term Presentation",
            description="Demonstrate working prototype.",
            deadline=datetime.strptime("2026-04-15 23:59:59", "%Y-%m-%d %H:%M:%S"),
            status="pending"
        )
        m3 = Milestone(
            id=uuid.uuid4(),
            team_id=team_id,
            semester_id=semester_id,
            title="Final Code Submission",
            description="Complete deployment and testing.",
            deadline=datetime.strptime("2026-05-10 23:59:59", "%Y-%m-%d %H:%M:%S"),
            status="pending"
        )

        db.add_all([m1, m2, m3])
        await db.commit()
        print("Announcements and milestones seeded successfully.")

if __name__ == "__main__":
    asyncio.run(seed())
