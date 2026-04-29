from sqlalchemy import inspect, text

from models import Project, ProjectHistory, User, UserArea, db
from scripts.migrations import run_migrations


def _create_user(username, name):
    user = User(
        username=username,
        name=name,
        orgao='Orgao Teste',
        is_admin=False,
    )
    user.set_password('senha123')
    db.session.add(user)
    db.session.flush()
    return user


def test_migrate_user_areas_is_safe_when_legacy_attribute_no_longer_exists(app, capsys):
    with app.app_context():
        user = _create_user('sem_legacy_area', 'Sem Legacy Area')
        db.session.commit()

        result = run_migrations.migrate_user_areas()

        output = capsys.readouterr().out
        assert result is True
        assert 'Replicação de área legada desativada' in output
        assert UserArea.query.filter_by(user_id=user.id).count() == 0


def test_migrate_user_areas_no_longer_replicates_legacy_db_column(app, capsys):
    """A replicação a partir de user.area_responsavel foi descontinuada.

    Por quê: a função era one-shot mas rodava em todo boot, ressuscitando vínculos
    que o admin já tinha removido em user_areas. user_areas passou a ser fonte única.
    """
    with app.app_context():
        user = _create_user('legacy_area_user', 'Legacy Area User')
        db.session.commit()

        db.session.execute(text("ALTER TABLE user ADD COLUMN area_responsavel VARCHAR(100)"))
        db.session.execute(
            text(
                "UPDATE user SET area_responsavel = 'Auditoria' WHERE id = :user_id"
            ),
            {'user_id': user.id},
        )
        db.session.commit()

        result = run_migrations.migrate_user_areas()

        output = capsys.readouterr().out
        assert result is True
        assert 'Replicação de área legada desativada' in output

        links = UserArea.query.filter_by(user_id=user.id).all()
        assert links == []


def test_create_history_table_adds_verification_entry_when_project_and_user_exist(app, capsys):
    with app.app_context():
        user = _create_user('user_history_script', 'User History Script')
        project = Project(
            titulo='Projeto Migracao',
            area_responsavel='Auditoria',
            orgao='Orgao Teste',
            prioridade='media',
            status='Vigente',
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(project)
        db.session.commit()

        result = run_migrations.create_history_table()

        output = capsys.readouterr().out
        assert result is True
        assert "Tabela 'project_history' criada e verificada." in output

        entry = (
            ProjectHistory.query
            .filter_by(project_id=project.id, user_id=user.id, action_type='migration')
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert entry is not None
        assert 'histórico instalado com sucesso' in entry.action_description


def test_ensure_abep_indicator_column_reports_success_when_column_already_exists(app, capsys):
    with app.app_context():
        result = run_migrations.ensure_abep_indicator_column()

        output = capsys.readouterr().out
        assert result is True
        assert "Coluna 'abep_indicator' ja existe." in output

        inspector = inspect(db.engine)
        assert 'abep_indicator' in {column['name'] for column in inspector.get_columns('project')}


def test_ensure_project_columns_adds_product_link_to_legacy_project_table(app):
    with app.app_context():
        db.drop_all()
        db.session.execute(
            text(
                """
                CREATE TABLE project (
                    id INTEGER PRIMARY KEY,
                    titulo VARCHAR(200) NOT NULL
                )
                """
            )
        )
        db.session.commit()

        result = run_migrations.ensure_project_columns(emit_output=False)

        inspector = inspect(db.engine)
        project_columns = {column['name'] for column in inspector.get_columns('project')}

        assert result['success'] is True
        assert 'project.product_link' in result['added_columns']
        assert 'product_link' in project_columns
        assert run_migrations.ALEMBIC_HEAD == '7c1d9e4a2b3f'
