"""Coluna codigo_raiz em siorg_sync_log (no-op por manifesto é por raiz).

Revision ID: b7c9e1f3a5d2
Revises: a4b8c6d2e9f1
Create Date: 2026-07-14
"""

import sqlalchemy as sa
from alembic import op

revision = "b7c9e1f3a5d2"
down_revision = "a4b8c6d2e9f1"
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
    if not _has_table("siorg_sync_log") or _has_column("siorg_sync_log", "codigo_raiz"):
        return
    with op.batch_alter_table("siorg_sync_log") as batch_op:
        batch_op.add_column(sa.Column("codigo_raiz", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("siorg_sync_log") as batch_op:
        batch_op.drop_column("codigo_raiz")
