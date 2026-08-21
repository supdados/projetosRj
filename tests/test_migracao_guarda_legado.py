"""Regressão das duas migrações que travavam o upgrade do banco de produção.

`c5f8a1b2d9e0` apagava user_areas/area_catalog/project.area_responsavel em
silêncio; `a4b8c6d2e9f1` dropava um índice que nenhuma migração cria. Os testes
abaixo rodam as revisões de verdade contra SQLite descartável.
"""

from pathlib import Path

import pytest
from flask import Flask
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from app import create_app

_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

_SCHEMA_LEGADO = (
    "CREATE TABLE project (id INTEGER PRIMARY KEY, area_responsavel VARCHAR(100))",
    "CREATE TABLE user_areas (id INTEGER PRIMARY KEY, user_id INTEGER, area VARCHAR(100))",
    "CREATE TABLE area_catalog (id INTEGER PRIMARY KEY, name VARCHAR(100))",
    "INSERT INTO project (id, area_responsavel) VALUES (1, 'CHEGAB')",
    "INSERT INTO user_areas (id, user_id, area) VALUES (1, 1, 'CHEGAB')",
    "INSERT INTO area_catalog (id, name) VALUES (1, 'CHEGAB')",
)

_SCHEMA_ORGAO = (
    "CREATE TABLE orgao_unidade (id INTEGER PRIMARY KEY, sigla VARCHAR(50))",
)


def _preparar_banco(caminho: Path, ddl: tuple[str, ...], revisao: str) -> None:
    """Cria um SQLite com o DDL dado e o carimba na revisão Alembic pedida."""
    engine = create_engine(f"sqlite:///{caminho}", poolclass=NullPool)
    with engine.begin() as conexao:
        for comando in (*ddl, "CREATE TABLE alembic_version (version_num VARCHAR(32))"):
            conexao.execute(text(comando))
        conexao.execute(text("INSERT INTO alembic_version VALUES (:r)"), {"r": revisao})
    engine.dispose()


def _app_em(caminho: Path) -> Flask:
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{caminho}",
            "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": NullPool},
            "SKIP_STARTUP_DB_INIT": True,
        }
    )


def _upgrade(caminho: Path, revisao: str) -> None:
    """Alembic direto: `flask_migrate.upgrade` converteria a exceção em sys.exit(1)."""
    config = Config(str(_MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    with _app_em(caminho).app_context():
        command.upgrade(config, revisao)


def _snapshotar(caminho: Path) -> None:
    engine = create_engine(f"sqlite:///{caminho}", poolclass=NullPool)
    with engine.begin() as conexao:
        conexao.execute(
            text("CREATE TABLE legacy_user_areas AS SELECT * FROM user_areas")
        )
        conexao.execute(
            text("CREATE TABLE legacy_area_catalog AS SELECT * FROM area_catalog")
        )
        conexao.execute(
            text(
                "CREATE TABLE legacy_project_area AS "
                "SELECT id AS project_id, area_responsavel FROM project "
                "WHERE area_responsavel IS NOT NULL"
            )
        )
    engine.dispose()


def test_drop_legacy_aborta_sem_snapshot(tmp_path: Path) -> None:
    banco = tmp_path / "sem_snapshot.sqlite"
    _preparar_banco(banco, _SCHEMA_LEGADO, "b2c4d6e8f0a1")

    with pytest.raises(RuntimeError, match="migrar_producao_v5"):
        _upgrade(banco, "c5f8a1b2d9e0")

    inspector = inspect(create_engine(f"sqlite:///{banco}", poolclass=NullPool))
    assert "user_areas" in inspector.get_table_names()


def test_drop_legacy_roda_com_snapshot(tmp_path: Path) -> None:
    banco = tmp_path / "com_snapshot.sqlite"
    _preparar_banco(banco, _SCHEMA_LEGADO, "b2c4d6e8f0a1")
    _snapshotar(banco)

    _upgrade(banco, "c5f8a1b2d9e0")

    inspector = inspect(create_engine(f"sqlite:///{banco}", poolclass=NullPool))
    tabelas = set(inspector.get_table_names())
    assert not {"user_areas", "area_catalog"} & tabelas
    assert "legacy_user_areas" in tabelas
    assert "area_responsavel" not in {
        c["name"] for c in inspector.get_columns("project")
    }


def test_drop_legacy_aborta_com_snapshot_parcial(tmp_path: Path) -> None:
    """Espelho de ensaio interrompido: existir não basta, tem que estar completo."""
    banco = tmp_path / "snapshot_parcial.sqlite"
    _preparar_banco(banco, _SCHEMA_LEGADO, "b2c4d6e8f0a1")
    engine = create_engine(f"sqlite:///{banco}", poolclass=NullPool)
    with engine.begin() as conexao:
        conexao.execute(
            text("INSERT INTO user_areas (id, user_id, area) VALUES (2, 2, 'SUPIM')")
        )
        conexao.execute(
            text(
                "CREATE TABLE legacy_user_areas AS "
                "SELECT * FROM user_areas WHERE id = 1"
            )
        )
    engine.dispose()

    with pytest.raises(RuntimeError, match="legacy_user_areas tem 1 registro"):
        _upgrade(banco, "c5f8a1b2d9e0")

    inspector = inspect(create_engine(f"sqlite:///{banco}", poolclass=NullPool))
    assert "user_areas" in inspector.get_table_names()


def test_codigo_externo_unique_e_noop_sem_a_coluna(tmp_path: Path) -> None:
    banco = tmp_path / "sem_coluna.sqlite"
    _preparar_banco(banco, _SCHEMA_ORGAO, "f3b9d0c7e2a5")

    _upgrade(banco, "a4b8c6d2e9f1")

    inspector = inspect(create_engine(f"sqlite:///{banco}", poolclass=NullPool))
    assert inspector.get_indexes("orgao_unidade") == []


def test_codigo_externo_unique_cria_indice_unico(tmp_path: Path) -> None:
    banco = tmp_path / "com_coluna.sqlite"
    _preparar_banco(
        banco,
        (
            "CREATE TABLE orgao_unidade (id INTEGER PRIMARY KEY, codigo_externo VARCHAR(80))",
            "CREATE INDEX ix_orgao_unidade_codigo_externo ON orgao_unidade (codigo_externo)",
        ),
        "f3b9d0c7e2a5",
    )

    _upgrade(banco, "a4b8c6d2e9f1")

    inspector = inspect(create_engine(f"sqlite:///{banco}", poolclass=NullPool))
    indices = {
        ix["name"]: ix["unique"] for ix in inspector.get_indexes("orgao_unidade")
    }
    assert indices["ix_orgao_unidade_codigo_externo"]
