"""add_mentor_password

Revision ID: c1a2b3d4e5f6
Revises: b96b9a192b5c
Create Date: 2026-03-28 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, None] = '8a739fb6a7e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add password column as nullable first (safe for existing rows)
    op.add_column('mentors', sa.Column('password', sa.String(length=255), nullable=True))

    # 2. Set a placeholder for any existing mentors (will need real passwords set by admin)
    op.execute("UPDATE mentors SET password = 'NEEDS_RESET' WHERE password IS NULL")

    # 3. Make password NOT NULL now that all rows have a value
    op.alter_column('mentors', 'password',
                     existing_type=sa.String(length=255),
                     nullable=False)

    # 4. Make email unique (matching the model change)
    op.create_unique_constraint('uq_mentors_email', 'mentors', ['email'])


def downgrade() -> None:
    op.drop_constraint('uq_mentors_email', 'mentors', type_='unique')
    op.drop_column('mentors', 'password')
