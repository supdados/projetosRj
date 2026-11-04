"""Regressão da revisão ``c8e2f4a6b1d3`` (coleção compartilhada com aceite).

Banco no estado da produção — carimbado em ``b6d1e8a4c7f2`` pela própria
cadeia — com share e item já gravados. Depois do upgrade: o share LEGADO
continua valendo sem aceite (ninguém perde acesso no deploy), um share NOVO
nasce pendente (default do banco virou TRUE) e o item legado fica sem autoria
nem teto. A revisão é idempotente (guardas) e o downgrade devolve o schema.
"""

from __future__ import annotations

import importlib.util
import io
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import sqlalchemy
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from app import create_app
from models import Project, User, db
from services.collection_access import construir_rank_map_de_colecoes
from services.project_collections import listar_colecoes

_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
_ANTERIOR = "b6d1e8a4c7f2"
_REVISAO = "c8e2f4a6b1d3"

_DADOS_DE_PRODUCAO = (
    "INSERT INTO user (id, username, password_hash, name, is_admin,"
    " is_super_admin, failed_login_attempts) VALUES"
    " (1, 'dono', 'x', 'DONO', 0, 0, 0), (2, 'legado', 'x', 'LEGADO', 0, 0, 0),"
    " (3, 'novo', 'x', 'NOVO', 0, 0, 0)",
    "INSERT INTO project (id, titulo, status) VALUES (10, 'Projeto', 'Vigente')",
    "INSERT INTO project_collection (id, owner_user_id, nome, icone, cor, tipo,"
    " ordem) VALUES (1, 1, 'Compartilhada', 'camadas', 'primary', 'custom', 0)",
    "INSERT INTO project_collection_item (id, collection_id, project_id, ordem)"
    " VALUES (1, 1, 10, 0)",
    "INSERT INTO project_collection_share (id, collection_id, user_id, papel,"
    " created_by_user_id) VALUES (1, 1, 2, 'editor', 1)",
)


def _engine(caminho: Path):
    return create_engine(f"sqlite:///{caminho}", poolclass=NullPool)


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


def _alembic(caminho: Path, acao: str, revisao: str) -> None:
    config = Config(str(_MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    with _app_em(caminho).app_context():
        getattr(command, acao)(config, revisao)


def _executar(caminho: Path, *comandos: str) -> list[tuple]:
    engine = _engine(caminho)
    with engine.begin() as conexao:
        resultados = [conexao.execute(text(comando)) for comando in comandos]
        linhas = resultados[-1].all() if resultados[-1].returns_rows else []
    engine.dispose()
    return linhas


def _banco_de_producao(tmp_path: Path) -> Path:
    banco = tmp_path / "producao.sqlite"
    _alembic(banco, "upgrade", _ANTERIOR)
    _executar(banco, *_DADOS_DE_PRODUCAO)
    return banco


def _ddl(caminho: Path) -> str:
    linhas = _executar(caminho, "SELECT sql FROM sqlite_master")
    return "\n".join(sorted(linha[0] or "" for linha in linhas))


def test_share_legado_continua_valendo_e_novo_nasce_pendente(tmp_path: Path) -> None:
    banco = _banco_de_producao(tmp_path)

    _alembic(banco, "upgrade", _REVISAO)
    _executar(
        banco,
        "INSERT INTO project_collection_share (id, collection_id, user_id, papel,"
        " created_by_user_id) VALUES (2, 1, 3, 'viewer', 1)",
    )

    assert _executar(
        banco, "SELECT id, exige_aceite FROM project_collection_share ORDER BY id"
    ) == [(1, 0), (2, 1)]
    assert _executar(
        banco, "SELECT added_by_user_id, rank_teto FROM project_collection_item"
    ) == [(None, None)]
    with _app_em(banco).test_request_context("/"):
        legado, novo = db.session.get(User, 2), db.session.get(User, 3)
        # Item legado sem teto = editor: o rank de hoje é preservado no deploy.
        assert construir_rank_map_de_colecoes(legado) == {10: 20}
        assert construir_rank_map_de_colecoes(novo) == {}
        assert [colecao.id for colecao, _ in listar_colecoes(2)[1:]] == [1]
        assert listar_colecoes(3)[1:] == []
        assert db.session.get(Project, 10) is not None
        db.session.rollback()


def test_upgrade_cria_respostas_e_colunas_novas(tmp_path: Path) -> None:
    banco = _banco_de_producao(tmp_path)

    _alembic(banco, "upgrade", _REVISAO)

    inspector = inspect(_engine(banco))
    assert "project_collection_share_resposta" in inspector.get_table_names()
    unicas = inspector.get_unique_constraints("project_collection_share_resposta")
    assert [u["column_names"] for u in unicas] == [["share_id", "user_id"]]
    indices_item = {
        ix["name"] for ix in inspector.get_indexes("project_collection_item")
    }
    assert "ix_project_collection_item_added_by_user_id" in indices_item
    fks_item = inspector.get_foreign_keys("project_collection_item")
    assert {"added_by_user_id"} in [set(fk["constrained_columns"]) for fk in fks_item]


def test_revisao_e_idempotente(tmp_path: Path) -> None:
    banco = _banco_de_producao(tmp_path)
    _alembic(banco, "upgrade", _REVISAO)
    antes = _ddl(banco)

    _alembic(banco, "stamp", _ANTERIOR)
    _alembic(banco, "upgrade", _REVISAO)

    assert _ddl(banco) == antes


def test_downgrade_devolve_o_schema_e_preserva_os_dados(tmp_path: Path) -> None:
    banco = _banco_de_producao(tmp_path)
    _alembic(banco, "upgrade", _REVISAO)

    _alembic(banco, "downgrade", _ANTERIOR)

    inspector = inspect(_engine(banco))
    assert "project_collection_share_resposta" not in inspector.get_table_names()
    colunas_share = {
        c["name"] for c in inspector.get_columns("project_collection_share")
    }
    colunas_item = {c["name"] for c in inspector.get_columns("project_collection_item")}
    assert "exige_aceite" not in colunas_share
    assert not {"added_by_user_id", "rank_teto"} & colunas_item
    assert _executar(
        banco, "SELECT id, user_id, papel FROM project_collection_share"
    ) == [(1, 2, "editor")]
    assert _executar(banco, "SELECT project_id FROM project_collection_item") == [(10,)]


# ── MySQL renderizado offline (sem servidor: só o DDL que a revisão emitiria) ──

_ARQUIVO_DA_REVISAO = (
    _MIGRATIONS_DIR / "versions" / f"{_REVISAO}_colecao_share_aceite.py"
)
_IX_RESPOSTA_USER = "ix_project_collection_share_resposta_user_id"
_IX_ITEM_ADDED_BY = "ix_project_collection_item_added_by_user_id"
_FK_ITEM_ADDED_BY = "fk_project_collection_item_added_by_user_id"


@dataclass(frozen=True)
class TabelaRefletida:
    """Uma tabela como o MySQL 8 a refletiria (coluna → default refletido)."""

    colunas: dict[str, str | None]
    indices: tuple[str, ...] = ()
    fks: tuple[str, ...] = field(default=())


class InspectorMySQLFalso:
    """Substitui ``sqlalchemy.inspect`` na revisão: devolve um estado fixo."""

    def __init__(self, tabelas: dict[str, TabelaRefletida]) -> None:
        self.tabelas = tabelas

    def get_table_names(self) -> list[str]:
        return list(self.tabelas)

    def get_columns(self, tabela: str) -> list[dict[str, str | None]]:
        colunas = self.tabelas[tabela].colunas
        return [{"name": nome, "default": padrao} for nome, padrao in colunas.items()]

    def get_indexes(self, tabela: str) -> list[dict[str, str]]:
        return [{"name": nome} for nome in self.tabelas[tabela].indices]

    def get_foreign_keys(self, tabela: str) -> list[dict[str, str]]:
        return [{"name": nome} for nome in self.tabelas[tabela].fks]


def _share_pos_upgrade() -> TabelaRefletida:
    return TabelaRefletida({"id": None, "exige_aceite": "'1'"})


def _resposta_pos_upgrade() -> TabelaRefletida:
    # O índice implícito da FK user_id já foi descartado pelo CREATE INDEX
    # explícito: ele é o único que sustenta a FK (o UNIQUE começa por share_id).
    return TabelaRefletida(
        {"id": None, "share_id": None, "user_id": None},
        indices=("uq_collection_share_resposta", _IX_RESPOSTA_USER),
        fks=(
            "project_collection_share_resposta_ibfk_1",
            "project_collection_share_resposta_ibfk_2",
        ),
    )


def _item(*, fk: bool, rank_teto: bool, indice: bool) -> TabelaRefletida:
    colunas: dict[str, str | None] = {"id": None, "added_by_user_id": None}
    if rank_teto:
        colunas["rank_teto"] = None
    return TabelaRefletida(
        colunas,
        indices=(_IX_ITEM_ADDED_BY,) if indice else (),
        fks=(_FK_ITEM_ADDED_BY,) if fk else (),
    )


def _carregar_revisao() -> ModuleType:
    spec = importlib.util.spec_from_file_location("revisao_c8e2", _ARQUIVO_DA_REVISAO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _ddl_mysql(monkeypatch, acao: str, tabelas: dict[str, TabelaRefletida]) -> str:
    monkeypatch.setattr(
        sqlalchemy, "inspect", lambda _bind: InspectorMySQLFalso(tabelas)
    )
    saida = io.StringIO()
    contexto = MigrationContext.configure(
        dialect_name="mysql", opts={"as_sql": True, "output_buffer": saida}
    )
    revisao = _carregar_revisao()
    with Operations.context(contexto):
        getattr(revisao, acao)()
    return saida.getvalue()


def test_downgrade_mysql_nao_derruba_o_indice_que_sustenta_a_fk(monkeypatch) -> None:
    """Regressão: DROP INDEX antes do DROP TABLE dá ERROR 1553 no MySQL."""
    ddl = _ddl_mysql(
        monkeypatch,
        "downgrade",
        {
            "project_collection_share": _share_pos_upgrade(),
            "project_collection_share_resposta": _resposta_pos_upgrade(),
            "project_collection_item": _item(fk=True, rank_teto=True, indice=True),
        },
    )

    assert f"DROP INDEX {_IX_RESPOSTA_USER}" not in ddl
    assert "DROP TABLE project_collection_share_resposta" in ddl
    # No item a FK sai ANTES do índice que a sustenta.
    assert ddl.index(f"DROP FOREIGN KEY {_FK_ITEM_ADDED_BY}") < ddl.index(
        f"DROP INDEX {_IX_ITEM_ADDED_BY}"
    )


def _pos_add_column(*, fk: bool, rank_teto: bool, indice: bool) -> dict:
    return {
        "project_collection_share": _share_pos_upgrade(),
        "project_collection_share_resposta": _resposta_pos_upgrade(),
        "project_collection_item": _item(fk=fk, rank_teto=rank_teto, indice=indice),
    }


def test_upgrade_mysql_retoma_a_fk_quando_a_coluna_ja_existe(monkeypatch) -> None:
    """Queda entre ADD COLUMN (commit implícito) e ADD CONSTRAINT: retomável."""
    ddl = _ddl_mysql(
        monkeypatch, "upgrade", _pos_add_column(fk=False, rank_teto=False, indice=False)
    )

    assert "ADD COLUMN added_by_user_id" not in ddl
    assert (
        f"ADD CONSTRAINT {_FK_ITEM_ADDED_BY} FOREIGN KEY(added_by_user_id) "
        "REFERENCES user (id)"
    ) in ddl
    assert "ADD COLUMN rank_teto" in ddl
    assert f"CREATE INDEX {_IX_ITEM_ADDED_BY}" in ddl


def test_upgrade_mysql_completo_e_no_op(monkeypatch) -> None:
    ddl = _ddl_mysql(
        monkeypatch, "upgrade", _pos_add_column(fk=True, rank_teto=True, indice=True)
    )

    assert ddl.strip() == ""
