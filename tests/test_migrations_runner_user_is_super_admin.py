"""Cobertura do step `ensure_user_is_super_admin_column` (super admin).

O fixture `app` cria o schema pelos modelos, então `user.is_super_admin` já
nasce presente. Para exercitar o banco legado (deploy anterior à migração) os
testes derrubam a coluna com DDL cru — ela não participa de índice nem de FK,
então o SQLite aceita o DROP sem rebuild.

Toda leitura/escrita aqui usa SQL cru: com a coluna derrubada, qualquer consulta
via ORM ao modelo `User` quebraria (o SELECT gerado cita a coluna).
"""

from sqlalchemy import inspect, text

from models import db
from scripts.migrations.run_migrations import (
    USER_IS_SUPER_ADMIN_COLUMN,
    _run_migration_steps,
    ensure_user_is_super_admin_column,
)
from startup import initialize_database

_INSERT_COM_COLUNA = (
    "INSERT INTO `user` "
    "(id, username, name, password_hash, is_admin, is_super_admin, "
    "failed_login_attempts, deleted_at) "
    "VALUES (:id, :username, :username, 'x', :is_admin, :is_super_admin, 0, "
    ":deleted_at)"
)

_INSERT_SEM_COLUNA = (
    "INSERT INTO `user` "
    "(id, username, name, password_hash, is_admin, failed_login_attempts, deleted_at) "
    "VALUES (:id, :username, :username, 'x', :is_admin, 0, :deleted_at)"
)


def _inserir_usuario(
    user_id: int,
    *,
    is_admin: bool = False,
    is_super_admin: bool = False,
    removido: bool = False,
    tem_coluna: bool = True,
) -> None:
    """Grava um usuário com id EXPLÍCITO (a eleição depende do MIN(id))."""
    sql = _INSERT_COM_COLUNA if tem_coluna else _INSERT_SEM_COLUNA
    params = {
        "id": user_id,
        "username": f"u{user_id}",
        "is_admin": 1 if is_admin else 0,
        "deleted_at": "2026-01-01 00:00:00" if removido else None,
    }
    if tem_coluna:
        params["is_super_admin"] = 1 if is_super_admin else 0
    db.session.execute(text(sql), params)
    db.session.commit()


def _derrubar_coluna_is_super_admin() -> None:
    """Volta `user` ao formato anterior à migração."""
    db.session.execute(text("ALTER TABLE `user` DROP COLUMN is_super_admin"))
    db.session.commit()


def _super_admin_ids() -> set[int]:
    return {
        row[0]
        for row in db.session.execute(
            text("SELECT id FROM `user` WHERE is_super_admin = 1")
        )
    }


def _colunas_user() -> dict[str, dict]:
    return {c["name"]: c for c in inspect(db.engine).get_columns("user")}


def test_constante_da_coluna_e_boolean_not_null_default_zero():
    assert USER_IS_SUPER_ADMIN_COLUMN == (
        "is_super_admin",
        "BOOLEAN NOT NULL DEFAULT 0",
    )


def test_step_e_noop_no_schema_atual(app):
    with app.app_context():
        primeira = ensure_user_is_super_admin_column(emit_output=False)
        segunda = ensure_user_is_super_admin_column(emit_output=False)

        assert primeira["success"] is True
        assert primeira["added"] is False
        assert segunda == {"success": True, "added": False, "elected_user_id": None}


def test_step_cria_coluna_e_elege_o_menor_admin_ativo(app):
    with app.app_context():
        _inserir_usuario(10, is_admin=True)
        _inserir_usuario(20, is_admin=True)
        _inserir_usuario(5)
        _derrubar_coluna_is_super_admin()

        resultado = ensure_user_is_super_admin_column(emit_output=False)

        assert resultado["success"] is True
        assert resultado["added"] is True
        assert resultado["elected_user_id"] == 10
        assert _super_admin_ids() == {10}


def test_backfill_nao_reelege_quando_ja_existe_super_admin(app):
    with app.app_context():
        _inserir_usuario(50, is_admin=True)
        ensure_user_is_super_admin_column(emit_output=False)
        assert _super_admin_ids() == {50}

        # Admin com id MENOR criado depois da eleição não rouba o posto.
        _inserir_usuario(7, is_admin=True)
        segunda = ensure_user_is_super_admin_column(emit_output=False)

        assert segunda["elected_user_id"] is None
        assert _super_admin_ids() == {50}


def test_eleicao_ignora_admins_soft_deletados(app):
    with app.app_context():
        _inserir_usuario(3, is_admin=True, removido=True)
        _inserir_usuario(9, is_admin=True)

        resultado = ensure_user_is_super_admin_column(emit_output=False)

        assert resultado["elected_user_id"] == 9
        assert _super_admin_ids() == {9}


def test_base_sem_admin_ativo_nao_promove_ninguem(app):
    with app.app_context():
        _inserir_usuario(1)
        _inserir_usuario(2, is_admin=True, removido=True)

        resultado = ensure_user_is_super_admin_column(emit_output=False)

        assert resultado["success"] is True
        assert resultado["elected_user_id"] is None
        assert _super_admin_ids() == set()


def test_super_admin_soft_deletado_impede_nova_eleicao(app):
    with app.app_context():
        _inserir_usuario(4, is_admin=True, is_super_admin=True, removido=True)
        _inserir_usuario(8, is_admin=True)

        resultado = ensure_user_is_super_admin_column(emit_output=False)

        assert resultado["elected_user_id"] is None
        assert _super_admin_ids() == {4}


def test_coluna_ja_criada_pelo_modelo_ainda_recebe_backfill(app):
    """Cenário `db.create_all()`: coluna existe, mas ninguém foi eleito."""
    with app.app_context():
        _inserir_usuario(11, is_admin=True)
        _inserir_usuario(12, is_admin=True)

        resultado = ensure_user_is_super_admin_column(emit_output=False)

        assert resultado["added"] is False
        assert resultado["elected_user_id"] == 11
        assert _super_admin_ids() == {11}


def test_coluna_nao_e_nullable_apos_o_step(app):
    with app.app_context():
        _derrubar_coluna_is_super_admin()
        ensure_user_is_super_admin_column(emit_output=False)

        assert _colunas_user()["is_super_admin"]["nullable"] is False


def test_step_registrado_no_runner_e_boot_idempotente(app):
    with app.app_context():
        nomes = [name for name, _ in _run_migration_steps(emit_output=False)]
        assert "ensure_user_is_super_admin_column" in nomes

        assert initialize_database()["success"] is True
        assert initialize_database()["success"] is True


def test_boot_sobe_de_primeira_em_banco_sem_a_coluna(app):
    """Regressão: o step tem de vir antes de qualquer step que use o ORM de User.

    Com ele registrado no fim, `backfill_task_assignees` fazia
    `User.query...all()` e o SELECT citava a coluna inexistente — o primeiro boot
    após o deploy abortava com OperationalError.
    """
    with app.app_context():
        _inserir_usuario(1, is_admin=True)
        _derrubar_coluna_is_super_admin()

        resultado = initialize_database()

        assert resultado["success"] is True, resultado
        assert _super_admin_ids() == {1}


def test_step_precede_os_steps_que_consultam_user_pelo_orm(app):
    with app.app_context():
        nomes = [name for name, _ in _run_migration_steps(emit_output=False)]

        assert nomes.index("ensure_user_is_super_admin_column") < nomes.index(
            "backfill_task_assignees"
        )
