"""Add announcements and milestones tables

Revision ID: daac5f5b8c3f
Revises: 9f70e750aca5
Create Date: 2026-06-12 22:01:37.379081

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'daac5f5b8c3f'
down_revision: Union[str, None] = '9f70e750aca5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create announcements table
    op.create_table('announcements',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),  # "general" | "deadline" | "result" | "schedule"
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.PrimaryKeyConstraint('id')
    )

    # Create milestones table
    op.create_table('milestones',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('semester_id', sa.String(length=255), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('deadline', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default=sa.text("'not_started'")),
        sa.Column('github_url', sa.String(length=500), nullable=True),
        sa.Column('file_url', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['semester_id'], ['semester_config.id'], ),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('milestones')
    op.drop_table('announcements')
