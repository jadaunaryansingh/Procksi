import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    mentor = "mentor"
    panel = "panel"
    admin = "admin"


class SlotStatus(str, enum.Enum):
    upcoming = "Upcoming"
    active = "Active"
    submitted = "Submitted"
    missed = "Missed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default=UserRole.panel.value)
    panel_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))

    project: Mapped["Project | None"] = relationship(back_populates="team", uselist=False)
    slots: Mapped[list["Slot"]] = relationship(back_populates="team")


class Project(Base):
    """PDF: projects table separate from teams."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), unique=True)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    team: Mapped["Team"] = relationship(back_populates="project")


class GitHubData(Base):
    """PDF: github_data — repo metrics / sync payload."""

    __tablename__ = "github_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), unique=True)
    repository_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    open_pull_requests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commit_count_30d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_commit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Alert(Base):
    """PDF: alerts — reminders, missed escalations, admin notifications."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    panel_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    alert_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Slot(Base):
    __tablename__ = "slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    panel_id: Mapped[str] = mapped_column(String(64), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slot_label: Mapped[str] = mapped_column(String(64))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default=SlotStatus.upcoming.value)
    meet_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    team: Mapped["Team"] = relationship(back_populates="slots")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    panel_id: Mapped[str] = mapped_column(String(64), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    scores_json: Mapped[str] = mapped_column(Text)
    remarks: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    receipt_id: Mapped[str] = mapped_column(String(64), unique=True)
    locked: Mapped[bool] = mapped_column(default=True)
    semester_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (UniqueConstraint("panel_id", "team_id", "semester_id", name="uq_eval_panel_team_semester"),)


class EvaluationDraft(Base):
    __tablename__ = "evaluation_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    panel_id: Mapped[str] = mapped_column(String(64), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    scores_json: Mapped[str] = mapped_column(Text, default="{}")
    remarks: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    semester_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (UniqueConstraint("panel_id", "team_id", "semester_id", name="uq_draft_panel_team_semester"),)


class EvaluationParameter(Base):
    __tablename__ = "evaluation_parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(512))
    criterion_name: Mapped[str] = mapped_column(String(512))
    max_marks: Mapped[int] = mapped_column(Integer)
