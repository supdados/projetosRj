"""novidades: catálogo de onboardings e quem já viu cada um

Revision ID: d4f7a2c9e1b5
Revises: c8e2f4a6b1d3
Create Date: 2026-11-05 15:00:00.000000

- ``novidade``: uma linha por onboarding anunciável (``slug`` casa com o
  conteúdo em ``frontend/src/lib/novidades/``), com ``ativa`` para ligar e
  desligar sem deploy.
- ``novidade_vista``: quem já viu (e se chegou ao fim) cada novidade.
- Insere a primeira novidade, ``colecoes-2026-11``, JÁ ATIVA: ela abre uma vez
  para cada pessoa na primeira tela depois do login.

Guardas de existência em cada objeto: reexecutar é no-op. Downgrade apaga as
duas tabelas (e com elas o registro de quem já viu).
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "d4f7a2c9e1b5"
down_revision = "c8e2f4a6b1d3"
branch_labels = None
depends_on = None

_NOVIDADE = "novidade"
_VISTA = "novidade_vista"
_IX_VISTA_USER = "ix_novidade_vista_user_id"
_PRIMEIRA = {"slug": "colecoes-2026-11", "titulo": "Coleções"}


def _tabelas() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indices(tabela: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if tabela not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(tabela)}


def _criar_novidade() -> None:
    if _NOVIDADE in _tabelas():
        return
    op.create_table(
        _NOVIDADE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.Column("publicada_em", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_novidade_slug"),
    )


def _criar_vista() -> None:
    if _VISTA in _tabelas():
        return
    op.create_table(
        _VISTA,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("novidade_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("concluida", sa.Boolean(), nullable=False),
        sa.Column("vista_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["novidade_id"], [f"{_NOVIDADE}.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("novidade_id", "user_id", name="uq_novidade_vista"),
    )


def _criar_indice_vista() -> None:
    if _IX_VISTA_USER in _indices(_VISTA):
        return
    op.create_index(_IX_VISTA_USER, _VISTA, ["user_id"])


def _inserir_primeira_novidade() -> None:
    bind = op.get_bind()
    existe = bind.execute(
        sa.text(f"SELECT 1 FROM {_NOVIDADE} WHERE slug = :slug"),
        {"slug": _PRIMEIRA["slug"]},
    ).first()
    if existe:
        return
    # Naive em UTC, como `time_utils.utc_now` grava nas demais tabelas.
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    tabela = sa.table(
        _NOVIDADE,
        sa.column("slug", sa.String),
        sa.column("titulo", sa.String),
        sa.column("ativa", sa.Boolean),
        sa.column("publicada_em", sa.DateTime),
        sa.column("created_at", sa.DateTime),
    )
    op.bulk_insert(
        tabela,
        [{**_PRIMEIRA, "ativa": True, "publicada_em": agora, "created_at": agora}],
    )


def upgrade() -> None:
    _criar_novidade()
    _criar_vista()
    _criar_indice_vista()
    _inserir_primeira_novidade()


def downgrade() -> None:
    # Ordem inversa: as vistas referenciam a novidade.
    if _VISTA in _tabelas():
        op.drop_table(_VISTA)
    if _NOVIDADE in _tabelas():
        op.drop_table(_NOVIDADE)
