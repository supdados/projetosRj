"""siorg sync log

Revision ID: f3b9d0c7e2a5
Revises: e1d3c5b7a902
Create Date: 2026-07-14 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f3b9d0c7e2a5"
down_revision = "e1d3c5b7a902"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "siorg_sync_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("iniciado_em", sa.DateTime(), nullable=False),
        sa.Column("finalizado_em", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("versao_global", sa.String(length=80), nullable=True),
        sa.Column("hash_manifesto", sa.String(length=128), nullable=True),
        sa.Column("criadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("atualizadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("desativadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("disparado_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["disparado_por_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_siorg_sync_log_iniciado_em",
        "siorg_sync_log",
        ["iniciado_em"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_siorg_sync_log_iniciado_em", table_name="siorg_sync_log")
    op.drop_table("siorg_sync_log")
