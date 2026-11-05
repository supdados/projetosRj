"""Migração d4f7a2c9e1b5: cria as tabelas de novidades e já liga a de Coleções."""

from pathlib import Path

import pytest
from flask_migrate import downgrade, upgrade
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app import create_app
from models import db

_MIGRATIONS = str(Path(__file__).resolve().parents[1] / "migrations")


@pytest.fixture
def app_migrado(tmp_path):
    flask_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'novidades.sqlite'}",
            "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": NullPool},
            "SKIP_STARTUP_DB_INIT": True,
        }
    )
    with flask_app.app_context():
        upgrade(directory=_MIGRATIONS)
        yield flask_app
        db.session.remove()
        db.engine.dispose()


def _novidades() -> list[tuple]:
    with db.engine.connect() as conexao:
        return list(conexao.execute(text("SELECT slug, titulo, ativa FROM novidade")))


def test_upgrade_insere_colecoes_ja_ativa(app_migrado):
    assert _novidades() == [("colecoes-2026-11", "Coleções", 1)]


def test_descer_e_subir_de_novo_nao_duplica(app_migrado):
    downgrade(directory=_MIGRATIONS, revision="c8e2f4a6b1d3")
    upgrade(directory=_MIGRATIONS)
    assert len(_novidades()) == 1
