"""catch-up legado v5: converge o banco pré-baseline ao schema dos modelos

Revision ID: 0257819cbe43
Revises: 5a1b53e0c4d2
Create Date: 2026-08-18 18:59:49.112926

A baseline `5a1b53e0c4d2` é clean-install-only (`if 'user' in tables: return`): em banco
existente ela não cria nada, e o runner custom que cobria esse buraco
(`scripts/migrations/run_migrations.py`) foi removido na Sprint 5. Esta revisão fecha o gap
medido contra a produção de 18/08/2026 — 12 tabelas, 9 colunas, 4 índices e a largura de
`project.special_project` — com guarda de existência em cada objeto, de modo que em
instalação limpa ela é no-op integral e reexecutá-la é idempotente.

Decisão registrada: as 9 FKs ausentes em task/task_anexo/task_comment/legacy_task_redirect
NÃO são criadas aqui — no SQLite exigiriam rebuild via batch de tabelas referenciadas por
outras (`task` <- task_anexo/task_comment), risco desproporcional para os 0 órfãos medidos.
"""

from typing import Callable

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0257819cbe43"
down_revision = "5a1b53e0c4d2"
branch_labels = None
depends_on = None


def _tabelas() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _colunas(tabela: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if tabela not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(tabela)}


def _indices(tabela: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if tabela not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(tabela)}


def _criar_autorizacao_audit() -> None:
    op.create_table(
        "autorizacao_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ator_id", sa.Integer(), nullable=False),
        sa.Column("evento", sa.String(length=40), nullable=False),
        sa.Column("alvo_tipo", sa.String(length=20), nullable=False),
        sa.Column("alvo_id", sa.Integer(), nullable=False),
        sa.Column("detalhe", sa.JSON(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_autorizacao_audit_criado_em", "autorizacao_audit", ["criado_em"]
    )
    op.create_index("ix_autorizacao_audit_user_id", "autorizacao_audit", ["user_id"])


def _criar_orgao_tipo() -> None:
    op.create_table(
        "orgao_tipo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("nivel", sa.Integer(), nullable=False),
        sa.Column("descricao", sa.String(length=255), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("permite_raiz", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_orgao_tipo_ativo", "orgao_tipo", ["ativo"])
    op.create_index("ix_orgao_tipo_nivel", "orgao_tipo", ["nivel"])


def _criar_orgao_closure() -> None:
    op.create_table(
        "orgao_closure",
        sa.Column("ancestor_id", sa.Integer(), nullable=False),
        sa.Column("descendant_id", sa.Integer(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ancestor_id"], ["orgao_unidade.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["descendant_id"], ["orgao_unidade.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("ancestor_id", "descendant_id"),
    )
    op.create_index(
        "ix_orgao_closure_ancestor_depth", "orgao_closure", ["ancestor_id", "depth"]
    )
    op.create_index("ix_orgao_closure_descendant", "orgao_closure", ["descendant_id"])


def _criar_etapa_responsavel() -> None:
    op.create_table(
        "etapa_responsavel",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("etapa_id", sa.Integer(), nullable=False),
        sa.Column("area_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["area_id"], ["orgao_unidade.id"]),
        sa.ForeignKeyConstraint(["etapa_id"], ["etapa.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("etapa_id", "area_id", name="uq_etapa_responsavel_area"),
    )
    op.create_index("ix_etapa_responsavel_etapa_id", "etapa_responsavel", ["etapa_id"])


def _criar_task_assignee() -> None:
    op.create_table(
        "task_assignee",
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "user_id"),
    )
    op.create_index("ix_task_assignee_user_id", "task_assignee", ["user_id"])


def _criar_project_collection() -> None:
    op.create_table(
        "project_collection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("descricao", sa.String(length=200), nullable=True),
        sa.Column("icone", sa.String(length=30), nullable=False),
        sa.Column("cor", sa.String(length=20), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id", "nome", name="uq_project_collection_owner_nome"
        ),
    )
    op.create_index(
        "ix_project_collection_owner_user_id", "project_collection", ["owner_user_id"]
    )


def _criar_project_collection_item() -> None:
    op.create_table(
        "project_collection_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["project_collection.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "project_id", name="uq_collection_item"),
    )
    op.create_index(
        "ix_project_collection_item_collection_id",
        "project_collection_item",
        ["collection_id"],
    )
    op.create_index(
        "ix_project_collection_item_project_id",
        "project_collection_item",
        ["project_id"],
    )


def _criar_project_collection_share() -> None:
    op.create_table(
        "project_collection_share",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("orgao_id", sa.Integer(), nullable=True),
        sa.Column("papel", sa.String(length=20), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["project_collection.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["orgao_id"], ["orgao_unidade.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id", "orgao_id", name="uq_collection_share_orgao"
        ),
        sa.UniqueConstraint(
            "collection_id", "user_id", name="uq_collection_share_user"
        ),
    )
    op.create_index(
        "ix_project_collection_share_collection_id",
        "project_collection_share",
        ["collection_id"],
    )
    op.create_index(
        "ix_project_collection_share_orgao_id", "project_collection_share", ["orgao_id"]
    )
    op.create_index(
        "ix_project_collection_share_user_id", "project_collection_share", ["user_id"]
    )


def _criar_colecao_sugestao_ia() -> None:
    op.create_table(
        "colecao_sugestao_ia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("lote_id", sa.String(length=32), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("descricao", sa.String(length=200), nullable=True),
        sa.Column("justificativa", sa.Text(), nullable=False),
        sa.Column("project_ids", sa.JSON(), nullable=False),
        sa.Column("assinatura", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("colecao_id", sa.Integer(), nullable=True),
        sa.Column("modelo_id", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decidido_em", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["colecao_id"], ["project_collection.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_colecao_sugestao_user_status", "colecao_sugestao_ia", ["user_id", "status"]
    )


def _criar_project_custom_link() -> None:
    op.create_table(
        "project_custom_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_custom_link_project_id", "project_custom_link", ["project_id"]
    )


def _criar_project_member() -> None:
    op.create_table(
        "project_member",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("papel", sa.String(length=10), nullable=False),
        sa.Column(
            "origem", sa.String(length=20), server_default="convite", nullable=False
        ),
        sa.Column("granted_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["granted_by_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revoked_by_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )
    op.create_index("ix_project_member_project_id", "project_member", ["project_id"])
    op.create_index("ix_project_member_user_id", "project_member", ["user_id"])


def _criar_project_sei_process() -> None:
    op.create_table(
        "project_sei_process",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.String(length=50), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "numero", name="uq_project_sei_numero"),
    )
    op.create_index(
        "ix_project_sei_process_project_id", "project_sei_process", ["project_id"]
    )


# Ordem importa: cada tabela só nasce depois dos alvos das suas FKs.
_CRIADORES_DE_TABELA: tuple[tuple[str, Callable[[], None]], ...] = (
    ("orgao_tipo", _criar_orgao_tipo),
    ("orgao_closure", _criar_orgao_closure),
    ("autorizacao_audit", _criar_autorizacao_audit),
    ("etapa_responsavel", _criar_etapa_responsavel),
    ("task_assignee", _criar_task_assignee),
    ("project_custom_link", _criar_project_custom_link),
    ("project_member", _criar_project_member),
    ("project_sei_process", _criar_project_sei_process),
    ("project_collection", _criar_project_collection),
    ("project_collection_item", _criar_project_collection_item),
    ("project_collection_share", _criar_project_collection_share),
    ("colecao_sugestao_ia", _criar_colecao_sugestao_ia),
)


def _criar_tabelas_ausentes() -> None:
    existentes = _tabelas()
    for nome, criar in _CRIADORES_DE_TABELA:
        if nome not in existentes:
            criar()


def _adicionar_coluna(tabela: str, coluna: sa.Column) -> None:
    if coluna.name in _colunas(tabela):
        return
    op.add_column(tabela, coluna)


def _adicionar_orgao_unidade_tipo_id() -> None:
    """Única coluna nova com FK; os dois dialetos exigem caminhos diferentes.

    SQLite não tem ALTER TABLE ADD CONSTRAINT (só aceita REFERENCES inline no ADD COLUMN,
    e apenas com default NULL); MySQL, ao contrário, parseia e IGNORA REFERENCES inline.
    """
    if "tipo_id" in _colunas("orgao_unidade"):
        return
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE orgao_unidade ADD COLUMN tipo_id INTEGER "
            "REFERENCES orgao_tipo (id) ON DELETE RESTRICT"
        )
        return
    op.add_column("orgao_unidade", sa.Column("tipo_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_orgao_unidade_tipo_id",
        "orgao_unidade",
        "orgao_tipo",
        ["tipo_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def _criar_colunas_ausentes() -> None:
    _adicionar_orgao_unidade_tipo_id()
    _adicionar_coluna(
        "orgao_unidade",
        sa.Column("codigo_externo", sa.String(length=80), nullable=True),
    )
    _adicionar_coluna(
        "orgao_unidade", sa.Column("data_inicio_vigencia", sa.Date(), nullable=True)
    )
    _adicionar_coluna(
        "orgao_unidade", sa.Column("data_fim_vigencia", sa.Date(), nullable=True)
    )
    _adicionar_coluna(
        "siorg_sync_log", sa.Column("usuarios_escopo_zerado", sa.Text(), nullable=True)
    )
    _adicionar_coluna("task_comment", sa.Column("mentions", sa.JSON(), nullable=True))
    _adicionar_coluna("user", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    # NOT NULL sem server_default: o SQLite RECUSA o ADD COLUMN e o MySQL aceita mas
    # deixa a coluna sem DEFAULT, quebrando INSERTs parciais do backfill (ERROR 1364).
    _adicionar_coluna(
        "user",
        sa.Column(
            "is_super_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
    )
    _adicionar_coluna(
        "user_orgao",
        sa.Column(
            "papel", sa.String(length=10), nullable=False, server_default="gestor"
        ),
    )


def _largura_varchar(tabela: str, coluna: str) -> int | None:
    inspector = sa.inspect(op.get_bind())
    if tabela not in inspector.get_table_names():
        return None
    for col in inspector.get_columns(tabela):
        if col["name"] == coluna:
            return getattr(col["type"], "length", None)
    return None


def _ampliar_special_project() -> None:
    """`project.special_project` nasceu `varchar(20)` no legado; o modelo pede 50.

    "Fórum de simplificação" (22 caracteres) é uma das opções gravadas por
    `routes/api/projects_write.py`, e em MySQL strict mode a coluna curta recusa o
    valor com ERROR 1406. O SQLite ignora a largura declarada de VARCHAR, e
    `ALTER COLUMN ... TYPE` nem existe lá — trocar o tipo exigiria recriar a tabela,
    risco sem retorno para um limite que o dialeto não aplica.

    O MODIFY do MySQL reescreve a coluna inteira e derruba o COMMENT legado
    ("Projeto especial: ABEP ou TCE"), que já não valia com a terceira opção.
    """
    if op.get_bind().dialect.name == "sqlite":
        return
    largura = _largura_varchar("project", "special_project")
    if largura is None or largura >= 50:
        return
    op.alter_column(
        "project",
        "special_project",
        type_=sa.String(length=50),
        existing_type=sa.String(length=largura),
        existing_nullable=True,
    )


def _criar_indice(
    tabela: str, nome: str, colunas: list[str], *, unique: bool = False
) -> None:
    if nome in _indices(tabela):
        return
    op.create_index(nome, tabela, colunas, unique=unique)


def _criar_indices_ausentes() -> None:
    _criar_indice("etapa", "ix_etapa_entry_type", ["entry_type"])
    _criar_indice("user", "ix_user_deleted_at", ["deleted_at"])
    _criar_indice("orgao_unidade", "ix_orgao_unidade_tipo_id", ["tipo_id"])
    _criar_indice(
        "orgao_unidade",
        "ix_orgao_unidade_codigo_externo",
        ["codigo_externo"],
        unique=True,
    )


def upgrade() -> None:
    _criar_tabelas_ausentes()
    _criar_colunas_ausentes()
    _ampliar_special_project()
    _criar_indices_ausentes()


def downgrade() -> None:
    # Sem downgrade: a revisão só preenche o que falta e não distingue o que ela criou
    # do que a baseline já havia criado — reverter apagaria dados legítimos.
    pass
