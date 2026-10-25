"""add semester_type academic_level is_active to semester_config

Revision ID: a1b2c3d4e5f7
Revises: b96b9a192b5c
Create Date: 2026-04-20 10:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = '89678ff2bacb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create the semester_type enum
    semester_type_enum = sa.Enum('odd', 'even', name='semester_type', create_type=True)
    semester_type_enum.create(op.get_bind(), checkfirst=True)

    # 2. Add semester_type column (nullable first for existing rows)
    op.add_column('semester_config', sa.Column('semester_type', semester_type_enum, nullable=True))
    op.execute("UPDATE semester_config SET semester_type = 'odd' WHERE semester_type IS NULL")
    op.alter_column('semester_config', 'semester_type', nullable=False, server_default='odd')

    # 3. Add academic_level column
    op.add_column('semester_config', sa.Column('academic_level', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE semester_config 
        SET academic_level = sub.rn 
        FROM (
            SELECT id, row_number() over(partition by year order by created_at) as rn 
            FROM semester_config
        ) sub 
        WHERE semester_config.id = sub.id
    """)
    op.alter_column('semester_config', 'academic_level', nullable=False, server_default='4')

    # 4. Add is_active column
    op.add_column('semester_config', sa.Column('is_active', sa.Boolean(), nullable=True))
    op.execute("UPDATE semester_config SET is_active = false WHERE is_active IS NULL")
    # Set the most recent one as active
    op.execute("""
        UPDATE semester_config SET is_active = true
        WHERE id = (SELECT id FROM semester_config ORDER BY created_at DESC LIMIT 1)
    """)
    op.alter_column('semester_config', 'is_active', nullable=False, server_default='false')

    # 5. Add unique constraint on (year, semester_type, academic_level)
    op.create_unique_constraint(
        'uq_semester_identity',
        'semester_config',
        ['year', 'semester_type', 'academic_level']
    )


def downgrade() -> None:
    op.drop_constraint('uq_semester_identity', 'semester_config', type_='unique')
    op.drop_column('semester_config', 'is_active')
    op.drop_column('semester_config', 'academic_level')
    op.drop_column('semester_config', 'semester_type')
    
    # Drop the enum type
    sa.Enum(name='semester_type').drop(op.get_bind(), checkfirst=True)
