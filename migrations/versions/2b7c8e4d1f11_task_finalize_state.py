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


def _has_table(name):
    """Guarda de instalação limpa (Sprint 5.3): em banco vazio a revisão histórica
    é no-op — o schema completo nasce na revisão baseline de catch-up."""
    import sqlalchemy as _sa
    from alembic import op as _op
    return name in _sa.inspect(_op.get_bind()).get_table_names()


def _has_column(table, column):
    import sqlalchemy as _sa
    from alembic import op as _op
    insp = _sa.inspect(_op.get_bind())
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade():
    if not _has_table("task") or _has_column("task", "is_finalized"):
        return
    op.add_column('task', sa.Column('is_finalized', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('task', sa.Column('finalized_at', sa.DateTime(), nullable=True))
    op.create_index('ix_task_is_finalized', 'task', ['is_finalized'], unique=False)
    op.alter_column('task', 'is_finalized', server_default=None)


def downgrade():
    op.drop_index('ix_task_is_finalized', table_name='task')
    op.drop_column('task', 'finalized_at')
    op.drop_column('task', 'is_finalized')
