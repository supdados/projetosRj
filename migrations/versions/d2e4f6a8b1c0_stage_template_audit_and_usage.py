"""stage template audit columns + usage table

Revision ID: d2e4f6a8b1c0
Revises: c5f8a1b2d9e0
Create Date: 2026-04-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd2e4f6a8b1c0'
down_revision = 'c5f8a1b2d9e0'
branch_labels = None
depends_on = None


def _column_exists(inspector, table_name, column_name):
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {col['name'] for col in inspector.get_columns(table_name)}


def _table_exists(inspector, table_name):
    return table_name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, 'StageTemplate'):
        missing_created_at = not _column_exists(inspector, 'StageTemplate', 'created_at')
        missing_updated_at = not _column_exists(inspector, 'StageTemplate', 'updated_at')
        missing_created_by = not _column_exists(inspector, 'StageTemplate', 'created_by_id')
        missing_updated_by = not _column_exists(inspector, 'StageTemplate', 'updated_by_id')

        if any([missing_created_at, missing_updated_at, missing_created_by, missing_updated_by]):
            with op.batch_alter_table('StageTemplate') as batch_op:
                if missing_created_at:
                    batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
                if missing_updated_at:
                    batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))
                if missing_created_by:
                    batch_op.add_column(sa.Column('created_by_id', sa.Integer(), nullable=True))
                    batch_op.create_foreign_key(
                        'fk_stage_template_created_by',
                        'user',
                        ['created_by_id'],
                        ['id'],
                    )
                if missing_updated_by:
                    batch_op.add_column(sa.Column('updated_by_id', sa.Integer(), nullable=True))
                    batch_op.create_foreign_key(
                        'fk_stage_template_updated_by',
                        'user',
                        ['updated_by_id'],
                        ['id'],
                    )

    # StageTemplate ausente = instalação limpa: a baseline de catch-up cria tudo
    # (Sprint 5.3); criar aqui quebraria os FKs no MySQL.
    if not _table_exists(inspector, 'StageTemplate'):
        return

    if not _table_exists(inspector, 'stage_template_usage'):
        op.create_table(
            'stage_template_usage',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('template_id', sa.Integer(), nullable=False),
            sa.Column('project_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('created_by_id', sa.Integer(), nullable=True),
            sa.Column('source', sa.String(length=16), nullable=False),
            sa.ForeignKeyConstraint(['template_id'], ['StageTemplate.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        )
        op.create_index(
            'ix_stage_template_usage_template_id',
            'stage_template_usage',
            ['template_id'],
        )
        op.create_index(
            'ix_stage_template_usage_project_id',
            'stage_template_usage',
            ['project_id'],
        )
        op.create_index(
            'ix_stage_template_usage_template_project',
            'stage_template_usage',
            ['template_id', 'project_id'],
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, 'stage_template_usage'):
        existing_indexes = {ix['name'] for ix in inspector.get_indexes('stage_template_usage')}
        if 'ix_stage_template_usage_template_project' in existing_indexes:
            op.drop_index('ix_stage_template_usage_template_project', table_name='stage_template_usage')
        if 'ix_stage_template_usage_project_id' in existing_indexes:
            op.drop_index('ix_stage_template_usage_project_id', table_name='stage_template_usage')
        if 'ix_stage_template_usage_template_id' in existing_indexes:
            op.drop_index('ix_stage_template_usage_template_id', table_name='stage_template_usage')
        op.drop_table('stage_template_usage')

    if _table_exists(inspector, 'StageTemplate'):
        with op.batch_alter_table('StageTemplate') as batch_op:
            if _column_exists(inspector, 'StageTemplate', 'updated_by_id'):
                batch_op.drop_constraint('fk_stage_template_updated_by', type_='foreignkey')
                batch_op.drop_column('updated_by_id')
            if _column_exists(inspector, 'StageTemplate', 'created_by_id'):
                batch_op.drop_constraint('fk_stage_template_created_by', type_='foreignkey')
                batch_op.drop_column('created_by_id')
            if _column_exists(inspector, 'StageTemplate', 'updated_at'):
                batch_op.drop_column('updated_at')
            if _column_exists(inspector, 'StageTemplate', 'created_at'):
                batch_op.drop_column('created_at')
