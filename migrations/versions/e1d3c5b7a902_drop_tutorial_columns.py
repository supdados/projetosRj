"""drop tutorial columns (project.is_tutorial, user.tutorial_visto)

O tutorial foi descartado pela equipe (faxina de codigo morto v5.0).
Esta migracao remove as colunas orfas deixadas pelos modelos.

Revision ID: e1d3c5b7a902
Revises: a7e1c4d9b3f8
Create Date: 2026-06-02

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e1d3c5b7a902"
down_revision = "a7e1c4d9b3f8"
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
    if not _has_column("project", "is_tutorial"):
        return
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_column("is_tutorial")

    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("tutorial_visto")


def downgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(
            sa.Column(
                "tutorial_visto",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )

    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_tutorial",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )
