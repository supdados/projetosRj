"""drop caderno size_preset

Revision ID: 6a4f6d2c1b90
Revises: f7a9c3e1b2d4
Create Date: 2026-04-12 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '6a4f6d2c1b90'
down_revision = 'f7a9c3e1b2d4'
branch_labels = None
depends_on = None


def _column_exists(inspector, table_name, column_name):
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {col['name'] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _column_exists(inspector, 'caderno_block', 'size_preset'):
        with op.batch_alter_table('caderno_block', schema=None) as batch_op:
            batch_op.drop_column('size_preset')


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _column_exists(inspector, 'caderno_block', 'size_preset'):
        with op.batch_alter_table('caderno_block', schema=None) as batch_op:
            batch_op.add_column(sa.Column('size_preset', sa.String(length=1), nullable=False, server_default='M'))

        op.execute(
            sa.text(
                """
                UPDATE caderno_block
                SET size_preset = CASE
                    WHEN grid_w >= 12 THEN 'G'
                    WHEN grid_w <= 3 THEN 'P'
                    ELSE 'M'
                END
                """
            )
        )
