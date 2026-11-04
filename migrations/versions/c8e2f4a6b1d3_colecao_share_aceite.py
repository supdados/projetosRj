"""coleção compartilhada com aceite: exige_aceite, respostas e autoria do item

Revision ID: c8e2f4a6b1d3
Revises: b6d1e8a4c7f2
Create Date: 2026-11-04 14:00:00.000000

Só DDL, sem script de dados:

- ``project_collection_share.exige_aceite`` entra com ``server_default`` FALSE —
  é isso que marca cada share já existente como legado (continua valendo sem
  aceite, ninguém perde acesso no deploy) — e logo depois o default passa a
  TRUE, para que todo share novo nasça convite pendente (falha fechada).
- ``project_collection_share_resposta``: aceite/recusa/saída POR PESSOA (um
  share de órgão alcança N pessoas).
- ``project_collection_item.added_by_user_id`` (quem incluiu) e ``rank_teto``
  (rank de área do incluidor na inclusão). NULL nos itens legados.

Guardas de existência em cada objeto: reexecutar é no-op. No MySQL o DDL não é
transacional; o rollback de uma falha no meio é o backup.

Downgrade DEPOIS de a feature estar em uso apaga as respostas e a coluna
``exige_aceite``: sob o código antigo todo share volta a conceder acesso, ou
seja, convites pendentes, recusados e saídas viram acesso pleno (ninguém além
de quem o dono já autorizou, mas sem o consentimento da pessoa). O rollback
de produção é restaurar o backup pré-deploy; se for mesmo preciso descer a
revisão, apague antes os shares que não devem voltar a valer.
"""

import sqlalchemy as sa
from alembic import op

revision = "c8e2f4a6b1d3"
down_revision = "b6d1e8a4c7f2"
branch_labels = None
depends_on = None

_SHARE = "project_collection_share"
_RESPOSTA = "project_collection_share_resposta"
_ITEM = "project_collection_item"
_IX_RESPOSTA_USER = "ix_project_collection_share_resposta_user_id"
_IX_ITEM_ADDED_BY = "ix_project_collection_item_added_by_user_id"
_FK_ITEM_ADDED_BY = "fk_project_collection_item_added_by_user_id"
_DEFAULTS_VERDADEIROS = frozenset({"1", "true"})


def _tabelas() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _colunas(tabela: str) -> dict[str, dict[str, object]]:
    inspector = sa.inspect(op.get_bind())
    if tabela not in inspector.get_table_names():
        return {}
    return {col["name"]: col for col in inspector.get_columns(tabela)}


def _indices(tabela: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if tabela not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(tabela)}


def _nomes_das_fks(tabela: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if tabela not in inspector.get_table_names():
        return set()
    return {fk["name"] for fk in inspector.get_foreign_keys(tabela) if fk["name"]}


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _default_normalizado(coluna: dict[str, object]) -> str:
    """``'1'``/``(1)``/``true`` → ``1``/``true``: cada dialeto reflete diferente."""
    bruto = str(coluna.get("default") or "")
    return bruto.strip().strip("()").strip("'\"").lower()


def _adicionar_exige_aceite() -> None:
    if "exige_aceite" in _colunas(_SHARE):
        return
    # server_default FALSE só aqui: é o que marca as linhas existentes como legado.
    op.add_column(
        _SHARE,
        sa.Column(
            "exige_aceite", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def _garantir_default_true_em_exige_aceite() -> None:
    """Troca o default para TRUE; checa antes para reexecução não reconstruir."""
    coluna = _colunas(_SHARE).get("exige_aceite")
    if coluna is None or _default_normalizado(coluna) in _DEFAULTS_VERDADEIROS:
        return
    # batch: o SQLite não tem ALTER COLUMN SET DEFAULT (recria a tabela); no
    # MySQL vira ALTER COLUMN ... SET DEFAULT direto.
    with op.batch_alter_table(_SHARE) as batch:
        batch.alter_column(
            "exige_aceite",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=sa.true(),
        )


def _criar_tabela_resposta() -> None:
    if _RESPOSTA in _tabelas():
        return
    op.create_table(
        _RESPOSTA,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("share_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("respondido_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["share_id"], [f"{_SHARE}.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("share_id", "user_id", name="uq_collection_share_resposta"),
    )


def _criar_indice_resposta() -> None:
    if _IX_RESPOSTA_USER in _indices(_RESPOSTA):
        return
    op.create_index(_IX_RESPOSTA_USER, _RESPOSTA, ["user_id"])


def _adicionar_added_by_user_id() -> None:
    """Coluna por dialeto, como ``0257819cbe43._adicionar_orgao_unidade_tipo_id``.

    SQLite só aceita REFERENCES inline no ADD COLUMN; MySQL ignora o inline e
    exige o ADD CONSTRAINT separado (``_criar_fk_added_by``).
    """
    if "added_by_user_id" in _colunas(_ITEM):
        return
    if _sqlite():
        op.execute(
            f"ALTER TABLE {_ITEM} ADD COLUMN added_by_user_id INTEGER "
            "REFERENCES user (id)"
        )
        return
    op.add_column(_ITEM, sa.Column("added_by_user_id", sa.Integer(), nullable=True))


def _criar_fk_added_by() -> None:
    """Guarda PRÓPRIA (pelo nome), separada da guarda da coluna: no MySQL o ADD
    COLUMN commita sozinho (DDL não transacional), e uma queda antes do ADD
    CONSTRAINT faria a reexecução ver a coluna e nunca mais criar a FK."""
    if _sqlite():
        return  # FK inline no próprio ADD COLUMN; SQLite não tem ADD CONSTRAINT.
    if _FK_ITEM_ADDED_BY in _nomes_das_fks(_ITEM):
        return
    op.create_foreign_key(
        _FK_ITEM_ADDED_BY, _ITEM, "user", ["added_by_user_id"], ["id"]
    )


def _adicionar_rank_teto() -> None:
    if "rank_teto" in _colunas(_ITEM):
        return
    op.add_column(_ITEM, sa.Column("rank_teto", sa.SmallInteger(), nullable=True))


def _criar_indice_added_by() -> None:
    if _IX_ITEM_ADDED_BY in _indices(_ITEM):
        return
    op.create_index(_IX_ITEM_ADDED_BY, _ITEM, ["added_by_user_id"])


def upgrade() -> None:
    _adicionar_exige_aceite()
    # Antes da tabela de respostas: no SQLite o batch recria a tabela de shares,
    # e ainda não há FK de outra tabela apontando para ela.
    _garantir_default_true_em_exige_aceite()
    _criar_tabela_resposta()
    _criar_indice_resposta()
    _adicionar_added_by_user_id()
    _criar_fk_added_by()
    _adicionar_rank_teto()
    _criar_indice_added_by()


def _remover_tabela_resposta() -> None:
    """Só o DROP TABLE, que leva junto índices e FKs da tabela nos dois dialetos.

    Sem DROP INDEX antes: no MySQL o ``CREATE INDEX`` de ``user_id`` faz o
    InnoDB descartar o índice implícito da FK, e o explícito passa a ser o
    único que a sustenta — derrubá-lo primeiro dá ERROR 1553 ("needed in a
    foreign key constraint"; bugs.mysql.com/37910) e aborta o downgrade.
    """
    if _RESPOSTA not in _tabelas():
        return
    op.drop_table(_RESPOSTA)


def _remover_fk_added_by_mysql() -> None:
    if _sqlite():
        return  # FK inline sem nome: o batch da remoção da coluna a descarta.
    if _FK_ITEM_ADDED_BY in _nomes_das_fks(_ITEM):
        op.drop_constraint(_FK_ITEM_ADDED_BY, _ITEM, type_="foreignkey")


def _remover_colunas_do_item() -> None:
    colunas = _colunas(_ITEM)
    if not {"added_by_user_id", "rank_teto"} & set(colunas):
        return
    _remover_fk_added_by_mysql()
    with op.batch_alter_table(_ITEM) as batch:
        if _IX_ITEM_ADDED_BY in _indices(_ITEM):
            batch.drop_index(_IX_ITEM_ADDED_BY)
        for nome in ("added_by_user_id", "rank_teto"):
            if nome in colunas:
                batch.drop_column(nome)


def _remover_exige_aceite() -> None:
    if "exige_aceite" not in _colunas(_SHARE):
        return
    with op.batch_alter_table(_SHARE) as batch:
        batch.drop_column("exige_aceite")


def downgrade() -> None:
    # Ordem inversa: respostas referenciam shares; sem elas o batch do share é livre.
    _remover_tabela_resposta()
    _remover_colunas_do_item()
    _remover_exige_aceite()
