"""Regressão da revisão `0257819cbe43` (catch-up legado v5).

A baseline `5a1b53e0c4d2` é clean-install-only, então em banco pré-baseline ela não cria
nada. A catch-up fecha esse gap — e precisa ser no-op quando os objetos já existem.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from flask import Flask
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from app import create_app

_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

_TABELAS_DA_CATCH_UP = {
    "autorizacao_audit",
    "colecao_sugestao_ia",
    "etapa_responsavel",
    "orgao_closure",
    "orgao_tipo",
    "project_collection",
    "project_collection_item",
    "project_collection_share",
    "project_custom_link",
    "project_member",
    "project_sei_process",
    "task_assignee",
}

# Recorte do schema de produção 18/08/2026 logo após a baseline: só as tabelas que a
# catch-up altera ou referencia, sem as colunas/índices que ela precisa acrescentar.
_SCHEMA_PRE_CATCH_UP = (
    "CREATE TABLE user (id INTEGER PRIMARY KEY, username VARCHAR(80) NOT NULL)",
    "CREATE TABLE project (id INTEGER PRIMARY KEY, nome VARCHAR(200))",
    "CREATE TABLE etapa (id INTEGER PRIMARY KEY, project_id INTEGER,"
    " entry_type VARCHAR(30) NOT NULL DEFAULT 'manual')",
    "CREATE TABLE task (id INTEGER PRIMARY KEY, descricao TEXT)",
    "CREATE TABLE task_comment (id INTEGER PRIMARY KEY, content TEXT)",
    "CREATE TABLE orgao_unidade (id INTEGER PRIMARY KEY, sigla VARCHAR(50))",
    "CREATE TABLE user_orgao (id INTEGER PRIMARY KEY, user_id INTEGER, orgao_id INTEGER)",
    "CREATE TABLE siorg_sync_log (id INTEGER PRIMARY KEY, status VARCHAR(20))",
    "INSERT INTO user (id, username) VALUES (1, 'admin')",
    "INSERT INTO user_orgao (id, user_id, orgao_id) VALUES (1, 1, 1)",
)


def _engine(caminho: Path):
    return create_engine(f"sqlite:///{caminho}", poolclass=NullPool)


def _preparar_banco(caminho: Path) -> None:
    engine = _engine(caminho)
    with engine.begin() as conexao:
        for comando in (
            *_SCHEMA_PRE_CATCH_UP,
            "CREATE TABLE alembic_version (version_num VARCHAR(32))",
            "INSERT INTO alembic_version VALUES ('5a1b53e0c4d2')",
        ):
            conexao.execute(text(comando))
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
    config = Config(str(_MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    with _app_em(caminho).app_context():
        command.upgrade(config, revisao)


def _stamp(caminho: Path, revisao: str) -> None:
    engine = _engine(caminho)
    with engine.begin() as conexao:
        conexao.execute(
            text("UPDATE alembic_version SET version_num = :r"), {"r": revisao}
        )
    engine.dispose()


def _ddl(caminho: Path) -> str:
    engine = _engine(caminho)
    with engine.begin() as conexao:
        linhas = conexao.execute(text("SELECT sql FROM sqlite_master")).scalars().all()
    engine.dispose()
    return "\n".join(sorted(linha or "" for linha in linhas))


def _colunas(inspector, tabela: str) -> set[str]:
    return {coluna["name"] for coluna in inspector.get_columns(tabela)}


def test_catch_up_cria_tabelas_colunas_e_indices_ausentes(tmp_path: Path) -> None:
    banco = tmp_path / "legado.sqlite"
    _preparar_banco(banco)

    _upgrade(banco, "0257819cbe43")

    inspector = inspect(_engine(banco))
    assert _TABELAS_DA_CATCH_UP <= set(inspector.get_table_names())
    assert {
        "tipo_id",
        "codigo_externo",
        "data_inicio_vigencia",
        "data_fim_vigencia",
    } <= (_colunas(inspector, "orgao_unidade"))
    assert {"is_super_admin", "deleted_at"} <= _colunas(inspector, "user")
    assert "papel" in _colunas(inspector, "user_orgao")
    assert "mentions" in _colunas(inspector, "task_comment")
    assert "usuarios_escopo_zerado" in _colunas(inspector, "siorg_sync_log")
    indices = {
        ix["name"]: ix["unique"] for ix in inspector.get_indexes("orgao_unidade")
    }
    assert indices["ix_orgao_unidade_codigo_externo"]
    assert "ix_orgao_unidade_tipo_id" in indices
    assert "ix_etapa_entry_type" in {
        ix["name"] for ix in inspector.get_indexes("etapa")
    }
    assert "ix_user_deleted_at" in {ix["name"] for ix in inspector.get_indexes("user")}


def test_catch_up_preenche_defaults_das_colunas_not_null(tmp_path: Path) -> None:
    """Sem server_default o SQLite recusa o ADD COLUMN e o MySQL estoura ERROR 1364."""
    banco = tmp_path / "defaults.sqlite"
    _preparar_banco(banco)

    _upgrade(banco, "0257819cbe43")

    engine = _engine(banco)
    with engine.begin() as conexao:
        assert conexao.execute(text("SELECT is_super_admin FROM user")).scalar() == 0
        assert (
            conexao.execute(text("SELECT papel FROM user_orgao")).scalar() == "gestor"
        )
        conexao.execute(
            text("INSERT INTO user_orgao (user_id, orgao_id) VALUES (1, 2)")
        )
    engine.dispose()


def test_catch_up_e_idempotente(tmp_path: Path) -> None:
    banco = tmp_path / "reexecucao.sqlite"
    _preparar_banco(banco)
    _upgrade(banco, "0257819cbe43")
    antes = _ddl(banco)

    _stamp(banco, "5a1b53e0c4d2")
    _upgrade(banco, "0257819cbe43")

    assert _ddl(banco) == antes
