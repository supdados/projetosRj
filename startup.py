from sqlalchemy import inspect, text

from models import db


def ensure_project_abep_indicator_column():
    """Garante a coluna project.abep_indicator em bancos existentes."""
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()
    if 'project' not in table_names:
        return False

    column_names = {column["name"] for column in inspector.get_columns('project')}
    if 'abep_indicator' in column_names:
        return False

    db.session.execute(text("ALTER TABLE project ADD COLUMN abep_indicator VARCHAR(255)"))
    db.session.commit()
    return True


def ensure_task_core_columns():
    """Garante colunas essenciais do novo modelo único de tarefas."""
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()
    added = []

    if 'task' in table_names:
        if db.engine.dialect.name == 'sqlite':
            columns = {col["name"] for col in inspector.get_columns('task')}
            # Guard para bancos legados: se ainda existe `titulo`, recria a tabela no schema task-only.
            if 'titulo' in columns:
                first_user_id = db.session.execute(text("SELECT id FROM user ORDER BY id ASC LIMIT 1")).scalar()
                fallback_user_id = int(first_user_id) if first_user_id else 1

                def col_expr(name, default_sql='NULL', coalesce_default=None):
                    if name not in columns:
                        return default_sql
                    if coalesce_default is None:
                        return name
                    return f"COALESCE({name}, {coalesce_default})"

                descricao_expr = "COALESCE(titulo, '')"
                if 'descricao' in columns:
                    descricao_expr = "COALESCE(descricao, titulo, '')"

                status_expr = col_expr('status', default_sql="'nao_iniciada'", coalesce_default="'nao_iniciada'")
                responsavel_expr = col_expr('responsavel')
                ordem_expr = col_expr('ordem', default_sql='0', coalesce_default='0')
                project_expr = col_expr('project_id')
                created_by_expr = col_expr('created_by_id', default_sql=str(fallback_user_id), coalesce_default=str(fallback_user_id))
                created_at_expr = col_expr('created_at', default_sql='CURRENT_TIMESTAMP', coalesce_default='CURRENT_TIMESTAMP')
                prioridade_expr = col_expr('prioridade')
                tipo_pedido_expr = col_expr('tipo_pedido')

                if 'is_archived' in columns:
                    is_archived_expr = "COALESCE(is_archived, 0)"
                elif 'is_finalized' in columns:
                    is_archived_expr = "COALESCE(is_finalized, 0)"
                else:
                    is_archived_expr = '0'

                if 'archived_at' in columns:
                    archived_at_expr = 'archived_at'
                elif 'finalized_at' in columns:
                    archived_at_expr = 'finalized_at'
                else:
                    archived_at_expr = 'NULL'

                db.session.execute(text("PRAGMA foreign_keys=OFF"))
                db.session.execute(text("DROP TABLE IF EXISTS task_task_only_tmp"))
                db.session.execute(
                    text(
                        """
                        CREATE TABLE task_task_only_tmp (
                            id INTEGER PRIMARY KEY,
                            descricao TEXT NOT NULL,
                            status VARCHAR(20) NOT NULL DEFAULT 'nao_iniciada',
                            responsavel VARCHAR(100),
                            ordem INTEGER NOT NULL DEFAULT 0,
                            project_id INTEGER,
                            created_by_id INTEGER NOT NULL,
                            created_at DATETIME NOT NULL,
                            prioridade VARCHAR(20),
                            tipo_pedido VARCHAR(30),
                            is_archived BOOLEAN NOT NULL DEFAULT 0,
                            archived_at DATETIME,
                            FOREIGN KEY(project_id) REFERENCES project(id),
                            FOREIGN KEY(created_by_id) REFERENCES user(id)
                        )
                        """
                    )
                )
                db.session.execute(
                    text(
                        f"""
                        INSERT INTO task_task_only_tmp (
                            id,
                            descricao,
                            status,
                            responsavel,
                            ordem,
                            project_id,
                            created_by_id,
                            created_at,
                            prioridade,
                            tipo_pedido,
                            is_archived,
                            archived_at
                        )
                        SELECT
                            id,
                            {descricao_expr},
                            {status_expr},
                            {responsavel_expr},
                            {ordem_expr},
                            {project_expr},
                            {created_by_expr},
                            {created_at_expr},
                            {prioridade_expr},
                            {tipo_pedido_expr},
                            {is_archived_expr},
                            {archived_at_expr}
                        FROM task
                        """
                    )
                )
                db.session.execute(text("DROP TABLE task"))
                db.session.execute(text("ALTER TABLE task_task_only_tmp RENAME TO task"))
                db.session.execute(text("PRAGMA foreign_keys=ON"))
                db.session.commit()
                added.append('task.rebuilt_task_only')

                inspector = inspect(db.engine)

        columns = {col["name"] for col in inspector.get_columns('task')}
        if 'descricao' not in columns and 'titulo' in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN descricao TEXT"))
            db.session.execute(text("UPDATE task SET descricao = titulo WHERE descricao IS NULL"))
            added.append('task.descricao')
        if 'status' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'nao_iniciada'"))
            added.append('task.status')
        if 'responsavel' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN responsavel VARCHAR(100)"))
            added.append('task.responsavel')
        if 'ordem' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN ordem INTEGER NOT NULL DEFAULT 0"))
            added.append('task.ordem')
        if 'legacy_parent_task_id' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN legacy_parent_task_id INTEGER"))
            added.append('task.legacy_parent_task_id')
        if 'prioridade' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN prioridade VARCHAR(20)"))
            added.append('task.prioridade')
        if 'tipo_pedido' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN tipo_pedido VARCHAR(30)"))
            added.append('task.tipo_pedido')
        if 'is_archived' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT 0"))
            added.append('task.is_archived')
        if 'archived_at' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN archived_at DATETIME NULL"))
            added.append('task.archived_at')
        if added:
            db.session.commit()

        # Índices para acelerar listagens.
        inspector = inspect(db.engine)
        indexes = {idx['name'] for idx in inspector.get_indexes('task')}
        if 'ix_task_is_archived' not in indexes:
            db.session.execute(text("CREATE INDEX ix_task_is_archived ON task (is_archived)"))
            db.session.commit()
            added.append('task.ix_task_is_archived')
        if 'ix_task_status' not in indexes:
            db.session.execute(text("CREATE INDEX ix_task_status ON task (status)"))
            db.session.commit()
            added.append('task.ix_task_status')

    return added


def initialize_database():
    """
    Inicializa/normaliza o schema usando a rotina canônica de migração.
    """
    from scripts.migrations.run_migrations import run_all_migrations

    return run_all_migrations(emit_output=False, stamp_alembic=False)
