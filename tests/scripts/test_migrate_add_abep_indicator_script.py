from sqlalchemy import inspect, text

from models import db
from scripts.migrations import migrate_add_abep_indicator


def test_migrate_add_abep_indicator_is_idempotent_when_column_already_exists(
    app, monkeypatch, capsys
):
    monkeypatch.setattr(migrate_add_abep_indicator, "app", app)

    result = migrate_add_abep_indicator.main()

    output = capsys.readouterr().out
    assert result == 0
    assert "Coluna 'abep_indicator' já existe. Nada a fazer." in output


def test_migrate_add_abep_indicator_creates_project_table_when_missing(
    app, monkeypatch, capsys
):
    monkeypatch.setattr(migrate_add_abep_indicator, "app", app)

    with app.app_context():
        db.drop_all()

    result = migrate_add_abep_indicator.main()

    output = capsys.readouterr().out
    assert result == 0

    with app.app_context():
        inspector = inspect(db.engine)
        assert "project" in inspector.get_table_names()
        assert "abep_indicator" in {
            column["name"] for column in inspector.get_columns("project")
        }

    assert "Tabela 'project' não encontrada. Executando create_all..." in output


def test_migrate_add_abep_indicator_adds_column_to_legacy_project_table(
    app, monkeypatch, capsys
):
    monkeypatch.setattr(migrate_add_abep_indicator, "app", app)

    with app.app_context():
        db.drop_all()
        db.session.execute(text("""
                CREATE TABLE project (
                    id INTEGER PRIMARY KEY,
                    titulo VARCHAR(200) NOT NULL
                )
                """))
        db.session.commit()

    result = migrate_add_abep_indicator.main()

    output = capsys.readouterr().out
    assert result == 0
    assert "Coluna 'abep_indicator' adicionada com sucesso." in output

    with app.app_context():
        inspector = inspect(db.engine)
        assert "abep_indicator" in {
            column["name"] for column in inspector.get_columns("project")
        }
