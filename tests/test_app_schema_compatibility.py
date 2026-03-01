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
