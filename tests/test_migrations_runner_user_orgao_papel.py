"""Cobertura para o step `ensure_user_orgao_papel_column` (S2/F1-1).

O `app` fixture cria o schema pelos modelos, então `user_orgao.papel` já nasce
presente. Para exercitar o caminho de banco legado (linhas gravadas antes da
coluna existir), os testes derrubam a coluna com DDL cru — ela não participa de
índice nem de FK, então o SQLite aceita o DROP COLUMN sem rebuild de tabela.
"""

from sqlalchemy import inspect, text

from models import OrgaoUnidade, User, UserOrgao, db
from scripts.migrations.run_migrations import (
    USER_ORGAO_PAPEL_COLUMN,
    ensure_user_orgao_papel_column,
)


def _criar_vinculo_legado() -> None:
    """Grava um vínculo user_orgao para simular linha pré-existente."""
    orgao = OrgaoUnidade(sigla="SUPDADOS", nome="Sup. de Dados", tipo="Subsecretaria")
    db.session.add(orgao)
    user = User(username="legado", name="Usuário Legado")
    user.set_password("senha123")
    db.session.add(user)
    db.session.flush()
    db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao.id))
    db.session.commit()


def _derrubar_coluna_papel() -> None:
    """Volta `user_orgao` ao formato anterior à migração."""
    db.session.execute(text("ALTER TABLE user_orgao DROP COLUMN papel"))
    db.session.commit()


def _papeis_gravados() -> list[str]:
    return [row[0] for row in db.session.execute(text("SELECT papel FROM user_orgao"))]


def test_user_orgao_papel_column_is_not_null_with_gestor_default():
    column_name, column_type = USER_ORGAO_PAPEL_COLUMN
    assert column_name == "papel"
    assert column_type == "VARCHAR(10) NOT NULL DEFAULT 'gestor'"


def test_ensure_user_orgao_papel_column_is_noop_on_current_schema(app):
    with app.app_context():
        first = ensure_user_orgao_papel_column(emit_output=False)
        assert first == {"success": True, "added": False}

        second = ensure_user_orgao_papel_column(emit_output=False)
        assert second == {"success": True, "added": False}


def test_ensure_user_orgao_papel_column_backfills_gestor_and_is_idempotent(app):
    with app.app_context():
        _criar_vinculo_legado()
        _derrubar_coluna_papel()

        first = ensure_user_orgao_papel_column(emit_output=False)
        assert first["success"] is True
        assert first["added"] is True
        assert _papeis_gravados() == ["gestor"]

        second = ensure_user_orgao_papel_column(emit_output=False)
        assert second["added"] is False
        assert _papeis_gravados() == ["gestor"]


def test_user_orgao_papel_is_not_nullable_after_step(app):
    with app.app_context():
        _derrubar_coluna_papel()
        ensure_user_orgao_papel_column(emit_output=False)

        colunas = {c["name"]: c for c in inspect(db.engine).get_columns("user_orgao")}
        assert colunas["papel"]["nullable"] is False
        assert "gestor" in str(colunas["papel"]["default"])
