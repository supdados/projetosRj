"""Largura de `project.special_project` na catch-up `0257819cbe43` (M4).

A produção tem `varchar(20)` e o modelo pede `String(50)`; "Fórum de simplificação"
(22 caracteres) é gravado por `routes/api/projects_write.py` e o MySQL em strict
mode recusa com ERROR 1406. O alter é guardado: só roda quando a largura atual é
menor que 50 e nunca no SQLite, que ignora a largura e não tem ALTER COLUMN TYPE.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

_REVISAO = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0257819cbe43_catch_up_legado_v5.py"
)


def _carregar_revisao() -> ModuleType:
    spec = importlib.util.spec_from_file_location("catch_up_legado_v5", _REVISAO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _banco_legado(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legado.db'}", poolclass=NullPool)
    with engine.begin() as conexao:
        conexao.execute(
            text(
                "CREATE TABLE project (id INTEGER PRIMARY KEY,"
                " special_project VARCHAR(20))"
            )
        )
    return engine


def _rodar(modulo: ModuleType, engine) -> None:
    with engine.begin() as conexao:
        modulo.op = Operations(MigrationContext.configure(conexao))
        modulo._ampliar_special_project()


def test_le_a_largura_declarada_da_coluna(tmp_path: Path) -> None:
    modulo = _carregar_revisao()
    engine = _banco_legado(tmp_path)
    with engine.begin() as conexao:
        modulo.op = Operations(MigrationContext.configure(conexao))
        assert modulo._largura_varchar("project", "special_project") == 20
        assert modulo._largura_varchar("project", "inexistente") is None
        assert modulo._largura_varchar("tabela_inexistente", "x") is None


def test_sqlite_legado_nao_recria_a_tabela(tmp_path: Path) -> None:
    """SQLite não impõe a largura: o alter é pulado em vez de recriar a tabela."""
    modulo = _carregar_revisao()
    engine = _banco_legado(tmp_path)

    _rodar(modulo, engine)

    with engine.begin() as conexao:
        ddl = conexao.execute(
            text("SELECT sql FROM sqlite_master WHERE name = 'project'")
        ).scalar()
    assert "special_project VARCHAR(20)" in ddl


def test_valor_de_22_caracteres_cabe_no_sqlite_legado(tmp_path: Path) -> None:
    modulo = _carregar_revisao()
    engine = _banco_legado(tmp_path)

    _rodar(modulo, engine)

    with engine.begin() as conexao:
        conexao.execute(
            text("INSERT INTO project (id, special_project) VALUES (1, :v)"),
            {"v": "Fórum de simplificação"},
        )
        assert (
            conexao.execute(text("SELECT special_project FROM project")).scalar()
            == "Fórum de simplificação"
        )
