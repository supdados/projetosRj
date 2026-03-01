from sqlalchemy import inspect, text

from app import create_app, ensure_project_abep_indicator_column, initialize_database
from models import db


def _create_isolated_app(tmp_path, filename):
    db_path = tmp_path / filename
    return create_app(
        {
            'TESTING': True,
            'SECRET_KEY': 'test-secret-key',
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'SQLALCHEMY_TRACK_MODIFICATIONS': False,
            'SKIP_STARTUP_DB_INIT': True,
        }
    )


def test_initialize_database_is_idempotent_on_current_schema(app):
    with app.app_context():
        summary = initialize_database()

        assert summary['column_added'] is False
        assert isinstance(summary['task_core_cols'], list)
        assert 'Auditoria' in summary['area_catalog_choices']
        assert set(summary['sync_summary'].keys()) == {
            'objetivos_created',
            'objetivos_updated',
            'resultados_created',
            'resultados_updated',
            'indicadores_created',
            'indicadores_updated',
        }


def test_schema_compatibility_upgrades_legacy_project_and_task_tables(tmp_path):
    isolated_app = _create_isolated_app(tmp_path, 'legacy-schema.sqlite')

    with isolated_app.app_context():
        db.session.execute(
            text(
                """
                CREATE TABLE user (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    password_hash VARCHAR(200) NOT NULL,
                    name VARCHAR(120) NOT NULL,
                    orgao VARCHAR(100),
                    is_admin BOOLEAN NOT NULL DEFAULT 0
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO user (id, username, password_hash, name, orgao, is_admin)
                VALUES (1, 'legacy', 'hash', 'Legacy User', 'Orgao Legacy', 0)
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE project (
                    id INTEGER PRIMARY KEY,
                    titulo VARCHAR(200) NOT NULL,
                    area_responsavel VARCHAR(100),
                    orgao VARCHAR(100),
                    prioridade VARCHAR(20),
                    status VARCHAR(20) NOT NULL DEFAULT 'Vigente',
                    observacao TEXT,
                    objetivo_id INTEGER,
                    resultado_esperado_id INTEGER,
                    special_project VARCHAR(20),
                    sei_process VARCHAR(50),
                    short_description TEXT,
                    delivery_type VARCHAR(50),
                    github_link VARCHAR(500),
                    documentation_link VARCHAR(500)
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO project (
                    id, titulo, area_responsavel, orgao, prioridade, status, observacao
                ) VALUES (
                    1, 'Projeto Legado', 'Auditoria', 'Orgao Legacy', 'alta', 'Vigente', 'Obs legado'
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE task (
                    id INTEGER PRIMARY KEY,
                    titulo TEXT,
                    project_id INTEGER,
                    created_by_id INTEGER,
                    is_finalized BOOLEAN DEFAULT 1,
                    finalized_at DATETIME
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO task (id, titulo, project_id, created_by_id, is_finalized, finalized_at)
                VALUES (1, 'Tarefa Legada', 1, 1, 1, '2026-02-01 12:00:00')
                """
            )
        )
        db.session.commit()

        assert ensure_project_abep_indicator_column() is True
        assert ensure_project_abep_indicator_column() is False

        summary = initialize_database()

        inspector = inspect(db.engine)
        project_columns = {column['name'] for column in inspector.get_columns('project')}
        assert 'abep_indicator' in project_columns

        task_columns = {column['name'] for column in inspector.get_columns('task')}
        assert 'titulo' not in task_columns
        assert {
            'descricao',
            'status',
            'responsavel',
            'ordem',
            'project_id',
            'created_by_id',
            'created_at',
            'prioridade',
            'tipo_pedido',
            'is_archived',
            'archived_at',
            'legacy_parent_task_id',
        }.issubset(task_columns)

        indexes = {index['name'] for index in inspector.get_indexes('task')}
        assert 'ix_task_is_archived' in indexes
        assert 'ix_task_status' in indexes

        migrated_task = db.session.execute(
            text(
                """
                SELECT descricao, status, is_archived, archived_at, created_by_id
                FROM task
                WHERE id = 1
                """
            )
        ).mappings().one()

        assert migrated_task['descricao'] == 'Tarefa Legada'
        assert migrated_task['status'] == 'nao_iniciada'
        assert migrated_task['is_archived'] == 1
        assert migrated_task['archived_at'] is not None
        assert migrated_task['created_by_id'] == 1

        assert summary['column_added'] is False
        assert 'task.rebuilt_task_only' in summary['task_core_cols']
        assert 'Auditoria' in summary['area_catalog_choices']


def test_schema_compatibility_unifies_mixed_task_and_task_item_schema(tmp_path):
    isolated_app = _create_isolated_app(tmp_path, 'mixed-task-schema.sqlite')

    with isolated_app.app_context():
        db.session.execute(
            text(
                """
                CREATE TABLE user (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    password_hash VARCHAR(200) NOT NULL,
                    name VARCHAR(120) NOT NULL,
                    orgao VARCHAR(100),
                    is_admin BOOLEAN NOT NULL DEFAULT 0
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO user (id, username, password_hash, name, orgao, is_admin)
                VALUES (1, 'legacy', 'hash', 'Legacy User', 'Orgao Legacy', 0)
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE project (
                    id INTEGER PRIMARY KEY,
                    titulo VARCHAR(200) NOT NULL,
                    area_responsavel VARCHAR(100),
                    orgao VARCHAR(100),
                    prioridade VARCHAR(20),
                    status VARCHAR(20) NOT NULL DEFAULT 'Vigente',
                    observacao TEXT,
                    objetivo_id INTEGER,
                    resultado_esperado_id INTEGER
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO project (
                    id, titulo, area_responsavel, orgao, prioridade, status, observacao
                ) VALUES (
                    1, 'Projeto Misturado', 'Auditoria', 'Orgao Legacy', 'alta', 'Vigente', 'Obs legado'
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE task (
                    id INTEGER PRIMARY KEY,
                    titulo TEXT,
                    project_id INTEGER,
                    created_by_id INTEGER,
                    created_at DATETIME,
                    is_finalized BOOLEAN DEFAULT 0,
                    finalized_at DATETIME
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO task (id, titulo, project_id, created_by_id, created_at, is_finalized, finalized_at)
                VALUES
                    (1, 'Tarefa Pai Legada', 1, 1, '2026-02-01 09:00:00', 1, '2026-02-03 10:00:00'),
                    (10, 'Tarefa Avulsa Legada', 1, 1, '2026-02-04 11:00:00', 0, NULL)
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE task_item (
                    id INTEGER PRIMARY KEY,
                    descricao TEXT NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    responsavel VARCHAR(100),
                    ordem INTEGER NOT NULL,
                    task_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    prioridade VARCHAR(20),
                    tipo_pedido VARCHAR(30)
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO task_item (
                    id, descricao, status, responsavel, ordem, task_id, created_at, prioridade, tipo_pedido
                ) VALUES
                    (10, 'Item Legado A', 'programado', 'Legacy User', 1, 1, '2026-02-01 09:30:00', 'alta', 'bug'),
                    (11, 'Item Legado B', 'validacao', 'Legacy User', 2, 1, '2026-02-01 10:30:00', 'media', 'melhoria')
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE task_comment (
                    id INTEGER PRIMARY KEY,
                    content TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    task_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO task_comment (id, content, user_id, task_id, created_at)
                VALUES (7, 'Comentário da tarefa avulsa', 1, 10, '2026-02-04 11:30:00')
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE task_item_comment (
                    id INTEGER PRIMARY KEY,
                    content TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    task_item_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO task_item_comment (id, content, user_id, task_item_id, created_at)
                VALUES (7, 'Comentário do item legado', 1, 10, '2026-02-01 12:00:00')
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE task_anexo (
                    id INTEGER PRIMARY KEY,
                    task_id INTEGER NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    stored_filename VARCHAR(255) NOT NULL,
                    content_type VARCHAR(100),
                    uploaded_by_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO task_anexo (id, task_id, filename, stored_filename, content_type, uploaded_by_id, created_at)
                VALUES (5, 10, 'atual.txt', 'atual.txt', 'text/plain', 1, '2026-02-04 12:00:00')
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE task_item_anexo (
                    id INTEGER PRIMARY KEY,
                    task_item_id INTEGER NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    stored_filename VARCHAR(255) NOT NULL,
                    content_type VARCHAR(100),
                    uploaded_by_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO task_item_anexo (id, task_item_id, filename, stored_filename, content_type, uploaded_by_id, created_at)
                VALUES (5, 10, 'legado.txt', 'legado.txt', 'text/plain', 1, '2026-02-01 12:30:00')
                """
            )
        )
        db.session.commit()

        summary = initialize_database()

        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())
        assert 'task_item' not in table_names
        assert 'task_item_comment' not in table_names
        assert 'task_item_anexo' not in table_names

        tasks = db.session.execute(
            text(
                """
                SELECT id, descricao, status, project_id, prioridade, tipo_pedido
                FROM task
                ORDER BY id
                """
            )
        ).mappings().all()
        assert len(tasks) == 3

        imported_item = next(task for task in tasks if task['descricao'] == 'Item Legado A')
        assert imported_item['id'] == 10
        assert imported_item['status'] == 'nao_iniciada'
        assert imported_item['prioridade'] == 'alta'
        assert imported_item['tipo_pedido'] == 'bug'

        preserved_standalone = next(task for task in tasks if task['descricao'] == 'Tarefa Avulsa Legada')
        assert preserved_standalone['id'] != 10
        assert preserved_standalone['status'] == 'nao_iniciada'

        redirect_rows = db.session.execute(
            text(
                """
                SELECT legacy_task_id, sample_task_id
                FROM legacy_task_redirect
                ORDER BY legacy_task_id
                """
            )
        ).mappings().all()
        assert {'legacy_task_id': 1, 'sample_task_id': 10} in redirect_rows
        assert any(row['legacy_task_id'] == 10 and row['sample_task_id'] == preserved_standalone['id'] for row in redirect_rows)

        comments = db.session.execute(
            text(
                """
                SELECT content, task_id
                FROM task_comment
                ORDER BY id
                """
            )
        ).mappings().all()
        assert len(comments) == 2
        assert any(comment['content'] == 'Comentário do item legado' and comment['task_id'] == 10 for comment in comments)
        assert any(comment['content'] == 'Comentário da tarefa avulsa' and comment['task_id'] == preserved_standalone['id'] for comment in comments)

        anexos = db.session.execute(
            text(
                """
                SELECT filename, task_id
                FROM task_anexo
                ORDER BY id
                """
            )
        ).mappings().all()
        assert len(anexos) == 2
        assert any(anexo['filename'] == 'legado.txt' and anexo['task_id'] == 10 for anexo in anexos)
        assert any(anexo['filename'] == 'atual.txt' and anexo['task_id'] == preserved_standalone['id'] for anexo in anexos)

        assert 'task.rebuilt_task_only' in summary['task_core_cols']
        assert 'task.migrated_legacy_items' in summary['task_core_cols']
