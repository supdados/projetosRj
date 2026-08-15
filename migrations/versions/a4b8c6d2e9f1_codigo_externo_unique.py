"""codigo_externo unico em orgao_unidade

Revision ID: a4b8c6d2e9f1
Revises: f3b9d0c7e2a5
Create Date: 2026-07-14 12:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a4b8c6d2e9f1"
down_revision = "f3b9d0c7e2a5"
branch_labels = None
depends_on = None


def upgrade():
    # batch p/ SQLite; NULLs múltiplos são permitidos em unique index (SQLite/MySQL).
    with op.batch_alter_table("orgao_unidade") as batch_op:
        batch_op.drop_index("ix_orgao_unidade_codigo_externo")
        batch_op.create_index(
            "ix_orgao_unidade_codigo_externo", ["codigo_externo"], unique=True
        )


def downgrade():
    with op.batch_alter_table("orgao_unidade") as batch_op:
        batch_op.drop_index("ix_orgao_unidade_codigo_externo")
        batch_op.create_index(
            "ix_orgao_unidade_codigo_externo", ["codigo_externo"], unique=False
        )
