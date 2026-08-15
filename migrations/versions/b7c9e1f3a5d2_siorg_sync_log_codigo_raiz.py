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


def upgrade():
    with op.batch_alter_table("siorg_sync_log") as batch_op:
        batch_op.add_column(sa.Column("codigo_raiz", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("siorg_sync_log") as batch_op:
        batch_op.drop_column("codigo_raiz")
