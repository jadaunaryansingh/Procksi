"""add scheduled_communications

Revision ID: e1f2a3b4c5d6
Revises: 9f70e750aca5
Create Date: 2026-06-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = '9f70e750aca5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'scheduled_communications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('segment', sa.String(length=100), nullable=True),
        sa.Column('template_code', sa.String(length=100), nullable=True),
        sa.Column('subject', sa.String(length=500), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('team_id', sa.UUID(), nullable=True),
        sa.Column('semester_id', sa.UUID(), nullable=True),
        sa.Column('send_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['admins.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_sched_comm_status_send_at',
        'scheduled_communications',
        ['status', 'send_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_sched_comm_status_send_at', table_name='scheduled_communications')
    op.drop_table('scheduled_communications')
