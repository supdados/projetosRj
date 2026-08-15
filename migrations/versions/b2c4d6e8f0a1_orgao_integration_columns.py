"""orgao integration columns

Adds Project.orgao_id FK and creates user_orgao association table,
coexisting with the legacy area columns/tables during migration.

Revision ID: b2c4d6e8f0a1
Revises: a1b2c3d4e5f6
Create Date: 2026-04-23 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c4d6e8f0a1'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # tabela ausente = instalação limpa: a baseline de catch-up cria tudo (Sprint 5.3)
    if 'project' not in inspector.get_table_names():
        return

    project_columns = {col['name'] for col in inspector.get_columns('project')}
    if 'orgao_id' not in project_columns:
        with op.batch_alter_table('project') as batch_op:
            batch_op.add_column(sa.Column('orgao_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_project_orgao_id',
                'orgao_unidade',
                ['orgao_id'],
                ['id'],
                ondelete='SET NULL',
            )
            batch_op.create_index('ix_project_orgao_id', ['orgao_id'])

    if 'user_orgao' not in inspector.get_table_names():
        op.create_table(
            'user_orgao',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('orgao_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(
                ['user_id'],
                ['user.id'],
                name='fk_user_orgao_user_id',
                ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['orgao_id'],
                ['orgao_unidade.id'],
                name='fk_user_orgao_orgao_id',
                ondelete='CASCADE',
            ),
            sa.UniqueConstraint('user_id', 'orgao_id', name='uq_user_orgao_user_orgao'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_user_orgao_user_id', 'user_orgao', ['user_id'])
        op.create_index('ix_user_orgao_orgao_id', 'user_orgao', ['orgao_id'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'user_orgao' in inspector.get_table_names():
        existing_indexes = {ix['name'] for ix in inspector.get_indexes('user_orgao')}
        if 'ix_user_orgao_orgao_id' in existing_indexes:
            op.drop_index('ix_user_orgao_orgao_id', table_name='user_orgao')
        if 'ix_user_orgao_user_id' in existing_indexes:
            op.drop_index('ix_user_orgao_user_id', table_name='user_orgao')
        op.drop_table('user_orgao')

    project_columns = {col['name'] for col in inspector.get_columns('project')}
    if 'orgao_id' in project_columns:
        with op.batch_alter_table('project') as batch_op:
            existing_indexes = {ix['name'] for ix in inspector.get_indexes('project')}
            if 'ix_project_orgao_id' in existing_indexes:
                batch_op.drop_index('ix_project_orgao_id')
            batch_op.drop_constraint('fk_project_orgao_id', type_='foreignkey')
            batch_op.drop_column('orgao_id')
