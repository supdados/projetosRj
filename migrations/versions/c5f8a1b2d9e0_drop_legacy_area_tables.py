"""drop legacy area columns and tables

Remove a camada legada de `area_responsavel` apos a migracao completa para
`OrgaoUnidade`. Rodar apenas apos `run_backfill_orgaos()` ter sido executado
em producao e confirmado que todos os projects e user_orgao estao vinculados.

Revision ID: c5f8a1b2d9e0
Revises: b2c4d6e8f0a1
Create Date: 2026-04-23 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c5f8a1b2d9e0'
down_revision = 'b2c4d6e8f0a1'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # tabela ausente = instalação limpa: a baseline de catch-up cria tudo (Sprint 5.3)
    if 'project' not in inspector.get_table_names():
        return

    project_columns = {col['name'] for col in inspector.get_columns('project')}
    if 'area_responsavel' in project_columns:
        with op.batch_alter_table('project') as batch_op:
            batch_op.drop_column('area_responsavel')

    table_names = set(inspector.get_table_names())
    if 'user_areas' in table_names:
        existing_indexes = {ix['name'] for ix in inspector.get_indexes('user_areas')}
        for idx_name in existing_indexes:
            op.drop_index(idx_name, table_name='user_areas')
        op.drop_table('user_areas')

    if 'area_catalog' in table_names:
        existing_indexes = {ix['name'] for ix in inspector.get_indexes('area_catalog')}
        for idx_name in existing_indexes:
            op.drop_index(idx_name, table_name='area_catalog')
        op.drop_table('area_catalog')


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_names = set(inspector.get_table_names())

    if 'area_catalog' not in table_names:
        op.create_table(
            'area_catalog',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name'),
        )

    if 'user_areas' not in table_names:
        op.create_table(
            'user_areas',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('area', sa.String(length=100), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['user.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    project_columns = {col['name'] for col in inspector.get_columns('project')}
    if 'area_responsavel' not in project_columns:
        with op.batch_alter_table('project') as batch_op:
            batch_op.add_column(sa.Column('area_responsavel', sa.String(length=100), nullable=True))
