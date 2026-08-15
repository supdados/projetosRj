"""task status rename

Revision ID: d1e2f3a4b5c6
Revises: c3d2e1f4a5b6
Create Date: 2026-03-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = 'c3d2e1f4a5b6'
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
    if not _has_table("task"):
        return
    # Renomeia os valores de status existentes na tabela task
    op.execute(sa.text("UPDATE task SET status = 'nao_iniciada' WHERE status = 'programado'"))
    op.execute(sa.text("UPDATE task SET status = 'para_validacao' WHERE status = 'validacao'"))
    op.execute(sa.text("UPDATE task SET status = 'finalizada' WHERE status = 'finalizado'"))
    # 'em_andamento' permanece inalterado
    # 'para_ajustes' é novo — nenhum dado existente precisa ser migrado

    # Atualiza o default da coluna para o novo valor padrão
    # batch p/ SQLite: ALTER COLUMN direto não existe no dialeto (Sprint 5.3).
    with op.batch_alter_table('task') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.String(length=20),
            server_default='nao_iniciada',
            existing_nullable=False,
        )


def downgrade():
    # Reverte os valores de status para os nomes anteriores
    op.execute(sa.text("UPDATE task SET status = 'programado' WHERE status = 'nao_iniciada'"))
    op.execute(sa.text("UPDATE task SET status = 'validacao' WHERE status = 'para_validacao'"))
    op.execute(sa.text("UPDATE task SET status = 'finalizado' WHERE status = 'finalizada'"))
    op.execute(sa.text("UPDATE task SET status = 'programado' WHERE status = 'para_ajustes'"))

    # Reverte o default da coluna
    op.alter_column(
        'task', 'status',
        existing_type=sa.String(length=20),
        server_default='programado',
        existing_nullable=False,
    )
