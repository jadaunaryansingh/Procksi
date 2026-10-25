"""initial uuid

Revision ID: 001
Revises: 
Create Date: 2024-03-26 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Admins
    op.create_table(
        'admins',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(), unique=True, nullable=False),
        sa.Column('password', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('role', sa.String(), server_default='ADMIN', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # Semesters
    op.create_table(
        'semester_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('semester_type', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_locked', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('proposal_weight', sa.Float(), server_default='30.0', nullable=False),
        sa.Column('mid_weight', sa.Float(), server_default='30.0', nullable=False),
        sa.Column('final_weight', sa.Float(), server_default='40.0', nullable=False),
        sa.UniqueConstraint('year', 'semester_type', name='uq_semester_year_type')
    )

    # Students
    op.create_table(
        'students',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(), unique=True, nullable=False),
        sa.Column('student_id', sa.String(), unique=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('branch', sa.String(), nullable=False),
        sa.Column('section', sa.String(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), server_default='active', nullable=False),
    )

    # Mentors
    op.create_table(
        'mentors',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(), unique=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('expertise', sa.String(), nullable=True),
    )

    # Teams
    op.create_table(
        'teams',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('semester_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('semester_configs.id'), nullable=False),
        sa.Column('mentor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('mentors.id'), nullable=True),
        sa.Column('project_title', sa.String(), nullable=True),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.UniqueConstraint('name', 'semester_id', name='uq_team_name_semester')
    )

    # Team Members
    op.create_table(
        'team_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('teams.id'), nullable=False),
        sa.Column('student_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('students.id'), nullable=False),
        sa.Column('role', sa.String(), server_default='MEMBER', nullable=False),
        sa.UniqueConstraint('student_id', name='uq_student_team_member')
    )
    # Partial unique index for Leader
    op.execute("CREATE UNIQUE INDEX uq_team_leader ON team_members (team_id) WHERE role = 'LEADER'")

    # Proposals
    op.create_table(
        'proposals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('teams.id'), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('ai_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # Panels
    op.create_table(
        'panels',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('semester_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('semester_configs.id'), nullable=False),
    )

    # Panel Mentors
    op.create_table(
        'panel_mentors',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('panel_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('panels.id'), nullable=False),
        sa.Column('mentor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('mentors.id'), nullable=False),
        sa.UniqueConstraint('panel_id', 'mentor_id', name='uq_panel_mentor')
    )

    # Schedules
    op.create_table(
        'schedules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('teams.id'), nullable=False),
        sa.Column('panel_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('panels.id'), nullable=False),
        sa.Column('semester_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('semester_configs.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('room', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
    )

    # Evaluations
    op.create_table(
        'evaluations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('teams.id'), nullable=False),
        sa.Column('schedule_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('schedules.id'), nullable=False),
        sa.Column('panel_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('panels.id'), nullable=False),
        sa.Column('semester_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('semester_configs.id'), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('marks', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('schedule_id', 'type', name='uq_evaluation_schedule_type')
    )

    # Results
    op.create_table(
        'results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('teams.id'), unique=True, nullable=False),
        sa.Column('proposal_score', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('mid_score', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('final_score', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('total_score', sa.Float(), server_default='0.0', nullable=False),
    )

    # Deadlines
    op.create_table(
        'deadlines',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('semester_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('semester_configs.id'), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('due_date', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('semester_id', 'type', name='uq_deadline_semester_type')
    )

    # Audit Logs
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('admin_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('admins.id'), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # Email Logs
    op.create_table(
        'email_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('recipients', sa.JSON(), nullable=False),
        sa.Column('sent_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('admins.id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('email_logs')
    op.drop_table('audit_logs')
    op.drop_table('deadlines')
    op.drop_table('results')
    op.drop_table('evaluations')
    op.drop_table('schedules')
    op.drop_table('panel_mentors')
    op.drop_table('panels')
    op.drop_table('proposals')
    op.execute("DROP INDEX uq_team_leader")
    op.drop_table('team_members')
    op.drop_table('teams')
    op.drop_table('mentors')
    op.drop_table('students')
    op.drop_table('semester_configs')
    op.drop_table('admins')
