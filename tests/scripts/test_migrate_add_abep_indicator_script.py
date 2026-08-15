"""Sprint 5.4: o wrapper ABEP só VERIFICA — nunca emite DDL."""

from sqlalchemy import inspect, text

from models import db
from scripts.migrations import migrate_add_abep_indicator


def test_retorna_zero_quando_coluna_ja_existe(app, monkeypatch, capsys):
    monkeypatch.setattr(migrate_add_abep_indicator, "app", app)

    result = migrate_add_abep_indicator.main()

    output = capsys.readouterr().out
    assert result == 0
    assert "Coluna 'abep_indicator' já existe. Nada a fazer." in output


def test_tabela_ausente_falha_mandando_rodar_alembic(app, monkeypatch, capsys):
    monkeypatch.setattr(migrate_add_abep_indicator, "app", app)

    with app.app_context():
        db.drop_all()

    result = migrate_add_abep_indicator.main()

    output = capsys.readouterr().out
    assert result == 1
    assert "tabela 'project' não existe" in output
    assert "alembic upgrade head" in output

    # nao pode ter criado nada: o produtor de schema e o alembic
    with app.app_context():
        assert "project" not in inspect(db.engine).get_table_names()


def test_coluna_ausente_falha_mandando_rodar_alembic(app, monkeypatch, capsys):
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
    assert result == 1
    assert "coluna 'abep_indicator' ausente" in output
    assert "alembic upgrade head" in output

    with app.app_context():
        columns = {
            column["name"] for column in inspect(db.engine).get_columns("project")
        }
        assert "abep_indicator" not in columns
