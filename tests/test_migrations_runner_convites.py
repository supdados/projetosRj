"""Cobertura para os steps de tabela da S4 (F3-1 `project_member`, F3-3 `autorizacao_audit`).

O fixture `app` cria o schema pelos modelos, então as duas tabelas já nascem
presentes. Para exercitar o banco legado (deploy anterior à sprint), os testes
derrubam a tabela com DDL cru — nenhuma outra tabela as referencia, então o
SQLite aceita o DROP sem rebuild.
"""

from sqlalchemy import inspect, text

from models import AutorizacaoAudit, ProjectMember, db
from scripts.migrations.run_migrations import (
    AUTORIZACAO_AUDIT_TABLE,
    PROJECT_MEMBER_TABLE,
    _run_migration_steps,
    ensure_autorizacao_audit_table,
    ensure_project_member_table,
)


def _derrubar_tabela(nome: str) -> None:
    db.session.execute(text(f"DROP TABLE {nome}"))
    db.session.commit()


def _indices(nome: str) -> set[str]:
    return {index["name"] for index in inspect(db.engine).get_indexes(nome)}


def _colunas(nome: str) -> set[str]:
    return {coluna["name"] for coluna in inspect(db.engine).get_columns(nome)}


def test_table_constants_match_model_tablenames():
    assert PROJECT_MEMBER_TABLE == ProjectMember.__tablename__
    assert AUTORIZACAO_AUDIT_TABLE == AutorizacaoAudit.__tablename__


def test_novos_steps_registrados_no_runner(app):
    with app.app_context():
        nomes = [name for name, _ in _run_migration_steps(emit_output=False)]

    assert "ensure_project_member_table" in nomes
    assert "ensure_autorizacao_audit_table" in nomes


def test_ensure_project_member_table_is_noop_on_current_schema(app):
    with app.app_context():
        assert ensure_project_member_table(emit_output=False) == {
            "success": True,
            "created": False,
        }
        assert ensure_project_member_table(emit_output=False) == {
            "success": True,
            "created": False,
        }


def test_ensure_project_member_table_creates_and_is_idempotent(app):
    with app.app_context():
        _derrubar_tabela(PROJECT_MEMBER_TABLE)

        first = ensure_project_member_table(emit_output=False)
        assert first == {"success": True, "created": True}

        second = ensure_project_member_table(emit_output=False)
        assert second == {"success": True, "created": False}
        assert PROJECT_MEMBER_TABLE in inspect(db.engine).get_table_names()


def test_project_member_has_expected_columns_after_step(app):
    with app.app_context():
        _derrubar_tabela(PROJECT_MEMBER_TABLE)
        ensure_project_member_table(emit_output=False)

        assert _colunas(PROJECT_MEMBER_TABLE) == {
            "id",
            "project_id",
            "user_id",
            "papel",
            "origem",
            "granted_by_id",
            "created_at",
            "expires_at",
            "revoked_at",
            "revoked_by_id",
        }


def test_project_member_has_unique_and_indexes_after_step(app):
    with app.app_context():
        _derrubar_tabela(PROJECT_MEMBER_TABLE)
        ensure_project_member_table(emit_output=False)

        uniques = inspect(db.engine).get_unique_constraints(PROJECT_MEMBER_TABLE)
        assert {"project_id", "user_id"} == set(
            next(u for u in uniques if u["name"] == "uq_project_member")["column_names"]
        )
        assert {
            "ix_project_member_project_id",
            "ix_project_member_user_id",
        } <= _indices(PROJECT_MEMBER_TABLE)


def test_project_member_cascades_on_project_and_user_delete(app):
    with app.app_context():
        _derrubar_tabela(PROJECT_MEMBER_TABLE)
        ensure_project_member_table(emit_output=False)

        fks = inspect(db.engine).get_foreign_keys(PROJECT_MEMBER_TABLE)
        cascade = {
            fk["constrained_columns"][0]
            for fk in fks
            if fk["options"].get("ondelete") == "CASCADE"
        }
        assert cascade == {"project_id", "user_id"}


def test_ensure_autorizacao_audit_table_is_noop_on_current_schema(app):
    with app.app_context():
        assert ensure_autorizacao_audit_table(emit_output=False) == {
            "success": True,
            "created": False,
        }
        assert ensure_autorizacao_audit_table(emit_output=False) == {
            "success": True,
            "created": False,
        }


def test_ensure_autorizacao_audit_table_creates_and_is_idempotent(app):
    with app.app_context():
        _derrubar_tabela(AUTORIZACAO_AUDIT_TABLE)

        first = ensure_autorizacao_audit_table(emit_output=False)
        assert first == {"success": True, "created": True}

        second = ensure_autorizacao_audit_table(emit_output=False)
        assert second == {"success": True, "created": False}


def test_autorizacao_audit_has_expected_columns_and_indexes_after_step(app):
    with app.app_context():
        _derrubar_tabela(AUTORIZACAO_AUDIT_TABLE)
        ensure_autorizacao_audit_table(emit_output=False)

        assert _colunas(AUTORIZACAO_AUDIT_TABLE) == {
            "id",
            "user_id",
            "ator_id",
            "evento",
            "alvo_tipo",
            "alvo_id",
            "detalhe",
            "criado_em",
        }
        assert {
            "ix_autorizacao_audit_user_id",
            "ix_autorizacao_audit_criado_em",
        } <= _indices(AUTORIZACAO_AUDIT_TABLE)
