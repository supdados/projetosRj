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
    if not _has_table("user") or _has_table("siorg_sync_log"):
        return
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
