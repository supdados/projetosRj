"""task-only model

Revision ID: b4f6d7e8a901
Revises: 9f2d4b8c1a11
Create Date: 2026-02-26 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4f6d7e8a901'
down_revision = '9f2d4b8c1a11'
branch_labels = None
depends_on = None


def _table_exists(inspector, name):
    return name in inspector.get_table_names()


def _column_exists(inspector, table_name, column_name):
    if not _table_exists(inspector, table_name):
        return False
    return column_name in {col['name'] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Novas tabelas temporárias do modelo final.
    op.create_table(
        'task_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('descricao', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='programado'),
        sa.Column('responsavel', sa.String(length=100), nullable=True),
        sa.Column('ordem', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('prioridade', sa.String(length=20), nullable=True),
        sa.Column('tipo_pedido', sa.String(length=30), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['project_id'], ['project.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'task_comment_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['task_new.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'task_anexo_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('stored_filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('uploaded_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['task_new.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'legacy_task_redirect',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('legacy_task_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('sample_task_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id']),
        sa.ForeignKeyConstraint(['sample_task_id'], ['task_new.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_legacy_task_redirect_legacy_task_id', 'legacy_task_redirect', ['legacy_task_id'], unique=True)

    has_task_item = _table_exists(inspector, 'task_item')
    has_task = _table_exists(inspector, 'task')
    has_prioridade = _column_exists(inspector, 'task_item', 'prioridade')
    has_tipo = _column_exists(inspector, 'task_item', 'tipo_pedido')
    has_is_finalized = _column_exists(inspector, 'task', 'is_finalized')
    has_finalized_at = _column_exists(inspector, 'task', 'finalized_at')

    if has_task_item and has_task:
        prioridade_expr = 'ti.prioridade' if has_prioridade else 'NULL'
        tipo_expr = 'ti.tipo_pedido' if has_tipo else 'NULL'
        archived_expr = 'COALESCE(t.is_finalized, 0)' if has_is_finalized else '0'
        archived_at_expr = 't.finalized_at' if has_finalized_at else 'NULL'

        op.execute(sa.text(f"""
            INSERT INTO task_new (
                id, descricao, status, responsavel, ordem, project_id, created_by_id,
                created_at, prioridade, tipo_pedido, is_archived, archived_at
            )
            SELECT
                ti.id,
                ti.descricao,
                COALESCE(ti.status, 'programado'),
                ti.responsavel,
                COALESCE(ti.ordem, 0),
                t.project_id,
                t.created_by_id,
                COALESCE(ti.created_at, t.created_at, CURRENT_TIMESTAMP),
                {prioridade_expr},
                {tipo_expr},
                {archived_expr},
                {archived_at_expr}
            FROM task_item ti
            JOIN task t ON t.id = ti.task_id
        """))

        if _table_exists(inspector, 'task_item_comment'):
            op.execute(sa.text("""
                INSERT INTO task_comment_new (id, content, user_id, task_id, created_at, updated_at)
                SELECT
                    c.id,
                    c.content,
                    c.user_id,
                    c.task_item_id,
                    c.created_at,
                    c.updated_at
                FROM task_item_comment c
                JOIN task_item ti ON ti.id = c.task_item_id
            """))

        if _table_exists(inspector, 'task_item_anexo'):
            op.execute(sa.text("""
                INSERT INTO task_anexo_new (
                    id, task_id, filename, stored_filename, content_type, uploaded_by_id, created_at
                )
                SELECT
                    a.id,
                    a.task_item_id,
                    a.filename,
                    a.stored_filename,
                    a.content_type,
                    a.uploaded_by_id,
                    a.created_at
                FROM task_item_anexo a
                JOIN task_item ti ON ti.id = a.task_item_id
            """))

        op.execute(sa.text("""
            INSERT INTO legacy_task_redirect (
                legacy_task_id, project_id, sample_task_id, created_at
            )
            SELECT
                t.id,
                t.project_id,
                MIN(ti.id) AS sample_task_id,
                CURRENT_TIMESTAMP
            FROM task t
            LEFT JOIN task_item ti ON ti.task_id = t.id
            GROUP BY t.id, t.project_id
        """))

    # Remove schema antigo e promove o novo.
    if _table_exists(inspector, 'task_item_comment'):
        op.drop_table('task_item_comment')
    if _table_exists(inspector, 'task_item_anexo'):
        op.drop_table('task_item_anexo')
    if _table_exists(inspector, 'task_item'):
        op.drop_table('task_item')
    if _table_exists(inspector, 'task'):
        op.drop_table('task')

    op.rename_table('task_new', 'task')
    op.rename_table('task_comment_new', 'task_comment')
    op.rename_table('task_anexo_new', 'task_anexo')

    op.create_index('ix_task_is_archived', 'task', ['is_archived'], unique=False)
    op.create_index('ix_task_status', 'task', ['status'], unique=False)
    op.create_index('ix_task_project_id', 'task', ['project_id'], unique=False)
    op.create_index('ix_task_created_by_id', 'task', ['created_by_id'], unique=False)
    op.create_index('ix_task_comment_task_id', 'task_comment', ['task_id'], unique=False)
    op.create_index('ix_task_anexo_task_id', 'task_anexo', ['task_id'], unique=False)

    op.alter_column('task', 'status', server_default=None)
    op.alter_column('task', 'ordem', server_default=None)
    op.alter_column('task', 'is_archived', server_default=None)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, 'legacy_task_redirect'):
        op.drop_index('ix_legacy_task_redirect_legacy_task_id', table_name='legacy_task_redirect')
        op.drop_table('legacy_task_redirect')

    op.create_table(
        'task_old',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('titulo', sa.String(length=200), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_finalized', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('finalized_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['project_id'], ['project.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'task_item_old',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('descricao', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('responsavel', sa.String(length=100), nullable=True),
        sa.Column('ordem', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('prioridade', sa.String(length=20), nullable=True),
        sa.Column('tipo_pedido', sa.String(length=30), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['task_old.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'task_item_comment_old',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('task_item_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['task_item_id'], ['task_item_old.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'task_item_anexo_old',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_item_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('stored_filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('uploaded_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_item_id'], ['task_item_old.id']),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.execute(sa.text("""
        INSERT INTO task_old (id, titulo, project_id, created_by_id, created_at, is_finalized, finalized_at)
        SELECT
            t.id,
            t.descricao,
            t.project_id,
            t.created_by_id,
            t.created_at,
            COALESCE(t.is_archived, 0),
            t.archived_at
        FROM task t
    """))
    op.execute(sa.text("""
        INSERT INTO task_item_old (
            id, descricao, status, responsavel, ordem, task_id, created_at, prioridade, tipo_pedido
        )
        SELECT
            t.id,
            t.descricao,
            t.status,
            t.responsavel,
            COALESCE(t.ordem, 0),
            t.id,
            t.created_at,
            t.prioridade,
            t.tipo_pedido
        FROM task t
    """))
    op.execute(sa.text("""
        INSERT INTO task_item_comment_old (
            id, content, user_id, task_item_id, created_at, updated_at
        )
        SELECT
            c.id,
            c.content,
            c.user_id,
            c.task_id,
            c.created_at,
            c.updated_at
        FROM task_comment c
    """))
    op.execute(sa.text("""
        INSERT INTO task_item_anexo_old (
            id, task_item_id, filename, stored_filename, content_type, uploaded_by_id, created_at
        )
        SELECT
            a.id,
            a.task_id,
            a.filename,
            a.stored_filename,
            a.content_type,
            a.uploaded_by_id,
            a.created_at
        FROM task_anexo a
    """))

    op.drop_index('ix_task_is_archived', table_name='task')
    op.drop_index('ix_task_status', table_name='task')
    op.drop_index('ix_task_project_id', table_name='task')
    op.drop_index('ix_task_created_by_id', table_name='task')
    op.drop_index('ix_task_comment_task_id', table_name='task_comment')
    op.drop_index('ix_task_anexo_task_id', table_name='task_anexo')
    op.drop_table('task_comment')
    op.drop_table('task_anexo')
    op.drop_table('task')

    op.rename_table('task_old', 'task')
    op.rename_table('task_item_old', 'task_item')
    op.rename_table('task_item_comment_old', 'task_item_comment')
    op.rename_table('task_item_anexo_old', 'task_item_anexo')
    op.create_index('ix_task_is_finalized', 'task', ['is_finalized'], unique=False)

