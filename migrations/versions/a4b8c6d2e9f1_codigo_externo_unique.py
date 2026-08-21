"""codigo_externo unico em orgao_unidade

Revision ID: a4b8c6d2e9f1
Revises: f3b9d0c7e2a5
Create Date: 2026-07-14 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a4b8c6d2e9f1"
down_revision = "f3b9d0c7e2a5"
branch_labels = None
depends_on = None

TABELA = "orgao_unidade"
INDICE = "ix_orgao_unidade_codigo_externo"
COLUNA = "codigo_externo"


def _colunas(inspector: sa.Inspector, tabela: str) -> set[str]:
    if tabela not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(tabela)}


def _indices(inspector: sa.Inspector, tabela: str) -> set[str]:
    if tabela not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(tabela)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    # O banco legado de produção nunca teve `codigo_externo` nem o índice: nenhuma
    # migration os criava (só a baseline). Sem esta guarda o DROP INDEX estoura
    # ("no such index" no SQLite, ERROR 1091 no MySQL) e a cadeia inteira morre aqui.
    if COLUNA not in _colunas(inspector, TABELA):
        return

    with op.batch_alter_table(TABELA) as batch_op:
        if INDICE in _indices(inspector, TABELA):
            batch_op.drop_index(INDICE)
        batch_op.create_index(INDICE, [COLUNA], unique=True)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if COLUNA not in _colunas(inspector, TABELA):
        return

    with op.batch_alter_table(TABELA) as batch_op:
        if INDICE in _indices(inspector, TABELA):
            batch_op.drop_index(INDICE)
        batch_op.create_index(INDICE, [COLUNA], unique=False)
