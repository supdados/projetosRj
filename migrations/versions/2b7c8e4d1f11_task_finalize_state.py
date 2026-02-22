"""task finalize state

Revision ID: 2b7c8e4d1f11
Revises: 02390a6c10dd
Create Date: 2026-02-22 12:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2b7c8e4d1f11'
down_revision = '02390a6c10dd'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('task', sa.Column('is_finalized', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('task', sa.Column('finalized_at', sa.DateTime(), nullable=True))
    op.create_index('ix_task_is_finalized', 'task', ['is_finalized'], unique=False)
    op.alter_column('task', 'is_finalized', server_default=None)


def downgrade():
    op.drop_index('ix_task_is_finalized', table_name='task')
    op.drop_column('task', 'finalized_at')
    op.drop_column('task', 'is_finalized')
