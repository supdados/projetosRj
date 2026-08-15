"""orgao unidade table

Revision ID: a1b2c3d4e5f6
Revises: f7a9c3e1b2d4
Create Date: 2026-04-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
# Pai original 7c1d9e4a2b3f (e o 6a4f6d2c1b90) foi apagado em 8b04c3b; religado ao avo sobrevivente.
down_revision = 'f7a9c3e1b2d4'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # sem `user` = instalação limpa: a baseline de catch-up cria tudo (Sprint 5.3)
    if 'user' not in inspector.get_table_names():
        return
    if 'orgao_unidade' in inspector.get_table_names():
        return

    op.create_table(
        'orgao_unidade',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=255), nullable=False),
        sa.Column('sigla', sa.String(length=50), nullable=False),
        sa.Column('tipo', sa.String(length=50), nullable=False),
        sa.Column('pai_id', sa.Integer(), nullable=True),
        sa.Column('ordem', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ['pai_id'],
            ['orgao_unidade.id'],
            name='fk_orgao_unidade_pai',
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_orgao_unidade_pai_ordem',
        'orgao_unidade',
        ['pai_id', 'ordem'],
    )
    op.create_index(
        'ix_orgao_unidade_ativo',
        'orgao_unidade',
        ['ativo'],
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'orgao_unidade' not in inspector.get_table_names():
        return

    existing_indexes = {ix['name'] for ix in inspector.get_indexes('orgao_unidade')}
    if 'ix_orgao_unidade_ativo' in existing_indexes:
        op.drop_index('ix_orgao_unidade_ativo', table_name='orgao_unidade')
    if 'ix_orgao_unidade_pai_ordem' in existing_indexes:
        op.drop_index('ix_orgao_unidade_pai_ordem', table_name='orgao_unidade')

    op.drop_table('orgao_unidade')
