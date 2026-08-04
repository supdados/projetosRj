"""Cobertura do step `ensure_user_deleted_at_column` (soft-delete C4).

O fixture `app` cria o schema pelos modelos, então `user.deleted_at` já nasce
presente. Para exercitar o banco legado (deploy anterior ao soft-delete) os
testes derrubam a coluna com DDL cru — ela não participa de índice nem de FK,
então o SQLite aceita o DROP sem rebuild.

Toda leitura/escrita aqui usa SQL cru: com a coluna derrubada, qualquer consulta
via ORM ao modelo `User` quebraria (o SELECT gerado cita a coluna).
"""

from sqlalchemy import inspect, text

from models import db
from scripts.migrations.run_migrations import (
    USER_DELETED_AT_COLUMN,
    USER_DELETED_AT_INDEX,
    _run_migration_steps,
    ensure_user_deleted_at_column,
)
from startup import initialize_database

_INSERT_SEM_COLUNA = (
    "INSERT INTO `user` "
    "(id, username, name, password_hash, is_admin, is_super_admin, "
    "failed_login_attempts) "
    "VALUES (:id, :username, :username, 'x', :is_admin, 0, 0)"
)


def _inserir_usuario_sem_coluna(user_id: int, *, is_admin: bool = False) -> None:
    db.session.execute(
        text(_INSERT_SEM_COLUNA),
        {
            "id": user_id,
            "username": f"u{user_id}",
            "is_admin": 1 if is_admin else 0,
        },
    )
    db.session.commit()


def _derrubar_coluna_deleted_at() -> None:
    """Volta `user` ao formato anterior ao soft-delete.

    O índice sai primeiro: o SQLite recusa o DROP COLUMN enquanto
    `ix_user_deleted_at` referenciar a coluna.
    """
    db.session.execute(text("DROP INDEX IF EXISTS ix_user_deleted_at"))
    db.session.execute(text("ALTER TABLE `user` DROP COLUMN deleted_at"))
    db.session.commit()


def _colunas_user() -> dict[str, dict]:
    return {c["name"]: c for c in inspect(db.engine).get_columns("user")}


def test_constante_da_coluna_e_datetime_nullable():
    assert USER_DELETED_AT_COLUMN == ("deleted_at", "DATETIME")


def test_step_e_noop_no_schema_atual(app):
    with app.app_context():
        primeira = ensure_user_deleted_at_column(emit_output=False)
        segunda = ensure_user_deleted_at_column(emit_output=False)

        assert primeira == {"success": True, "added": False}
        assert segunda == {"success": True, "added": False}


def test_step_cria_a_coluna_quando_ausente(app):
    with app.app_context():
        _derrubar_coluna_deleted_at()

        resultado = ensure_user_deleted_at_column(emit_output=False)

        assert resultado == {"success": True, "added": True}
        assert "deleted_at" in _colunas_user()


def test_step_recria_o_indice_do_modelo(app):
    """A coluna é `index=True` no modelo: o banco legado não pode ficar sem ele."""
    with app.app_context():
        _derrubar_coluna_deleted_at()
        ensure_user_deleted_at_column(emit_output=False)

        indices = {i["name"] for i in inspect(db.engine).get_indexes("user")}
        assert USER_DELETED_AT_INDEX[0] in indices


def test_coluna_nasce_nullable_para_marcar_usuario_ativo(app):
    """None = ativo: a coluna não pode ter NOT NULL nem default."""
    with app.app_context():
        _derrubar_coluna_deleted_at()
        ensure_user_deleted_at_column(emit_output=False)

        assert _colunas_user()["deleted_at"]["nullable"] is True


def test_boot_sobe_de_primeira_em_banco_sem_a_coluna(app):
    """Regressão: primeiro boot na VM de homologação abortava com

    `no such column: user.deleted_at` em `ensure_user_is_super_admin_column` e
    `backfill_task_assignees`. A coluna só era criada por `startup.py` DEPOIS de
    `run_all_migrations`, que já havia falhado e cortado o fluxo.
    """
    with app.app_context():
        _inserir_usuario_sem_coluna(1, is_admin=True)
        _derrubar_coluna_deleted_at()

        resultado = initialize_database()

        assert resultado["success"] is True, resultado
        assert "deleted_at" in _colunas_user()


def test_step_precede_os_steps_que_consultam_user(app):
    with app.app_context():
        nomes = [name for name, _ in _run_migration_steps(emit_output=False)]

        assert nomes.index("ensure_user_deleted_at_column") < nomes.index(
            "ensure_user_is_super_admin_column"
        )
        assert nomes.index("ensure_user_deleted_at_column") < nomes.index(
            "backfill_task_assignees"
        )
