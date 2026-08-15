"""calendar meet_link column

Revision ID: e5f6a7b8c9d0
Revises: d1e2f3a4b5c6
Create Date: 2026-03-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f6a7b8c9d0'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def _column_exists(inspector, table_name, column_name):
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {col['name'] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # tabela ausente = instalação limpa: a baseline de catch-up cria tudo (Sprint 5.3)
    if 'calendar_event' not in inspector.get_table_names():
        return
    if not _column_exists(inspector, 'calendar_event', 'meet_link'):
        op.add_column('calendar_event', sa.Column('meet_link', sa.String(512), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _column_exists(inspector, 'calendar_event', 'meet_link'):
        op.drop_column('calendar_event', 'meet_link')
