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


def upgrade():
    # Renomeia os valores de status existentes na tabela task
    op.execute(sa.text("UPDATE task SET status = 'nao_iniciada' WHERE status = 'programado'"))
    op.execute(sa.text("UPDATE task SET status = 'para_validacao' WHERE status = 'validacao'"))
    op.execute(sa.text("UPDATE task SET status = 'finalizada' WHERE status = 'finalizado'"))
    # 'em_andamento' permanece inalterado
    # 'para_ajustes' é novo — nenhum dado existente precisa ser migrado

    # Atualiza o default da coluna para o novo valor padrão
    op.alter_column(
        'task', 'status',
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
