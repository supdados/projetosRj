"""add etapa_id to task

Revision ID: a7e1c4d9b3f8
Revises: f7a9c3e1b2d4, d2e4f6a8b1c0
Create Date: 2026-05-14 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a7e1c4d9b3f8"
down_revision = ("f7a9c3e1b2d4", "d2e4f6a8b1c0")
branch_labels = None
depends_on = None


def _column_exists(inspector, table_name, column_name):
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def _index_exists(inspector, table_name, index_name):
    if table_name not in inspector.get_table_names():
        return False
    return index_name in {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # tabela ausente = instalação limpa: a baseline de catch-up cria tudo (Sprint 5.3)
    if "task" not in inspector.get_table_names():
        return

    if not _column_exists(inspector, "task", "etapa_id"):
        with op.batch_alter_table("task") as batch_op:
            batch_op.add_column(sa.Column("etapa_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_task_etapa_id",
                "etapa",
                ["etapa_id"],
                ["id"],
            )

    inspector = sa.inspect(bind)
    if not _index_exists(inspector, "task", "ix_task_etapa_id"):
        op.create_index("ix_task_etapa_id", "task", ["etapa_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _index_exists(inspector, "task", "ix_task_etapa_id"):
        op.drop_index("ix_task_etapa_id", table_name="task")

    if _column_exists(inspector, "task", "etapa_id"):
        with op.batch_alter_table("task") as batch_op:
            batch_op.drop_constraint("fk_task_etapa_id", type_="foreignkey")
            batch_op.drop_column("etapa_id")
