import json
import logging

from sqlalchemy import inspect, text

from models import db


def ensure_user_deleted_at_column():
    """Garante a coluna ``user.deleted_at`` (soft-delete C4) em bancos existentes.

    Padrão aditivo: inspeciona o schema atual e só executa o
    ``ALTER TABLE ... ADD COLUMN`` quando a coluna
    falta. None = ativo; timestamp = removido. Em testes a coluna já vem por
    ``create_all`` a partir do modelo; aqui cobrimos o banco de dev no boot.

    Cinto de segurança: a coluna canônica é criada pelo step
    ``run_migrations.ensure_user_deleted_at_column``, que roda antes dos steps que
    consultam User.
    """
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()
    if "user" not in table_names:
        return False

    column_names = {column["name"] for column in inspector.get_columns("user")}
    if "deleted_at" in column_names:
        return False

    db.session.execute(text("ALTER TABLE user ADD COLUMN deleted_at DATETIME"))
    db.session.commit()
    return True


def ensure_task_comment_mentions_column():
    """Garante ``task_comment.mentions`` (menções resolvidas) em bancos existentes.

    Mesmo padrão aditivo das demais ``ensure_*``. NULL nas linhas antigas é o
    sinal de "comentário anterior ao recurso" — o front cai no realce heurístico
    nesses casos, sem precisar reprocessar histórico.

    Cinto de segurança: a coluna canônica é criada por
    ``run_migrations.ensure_task_schema`` (TASK_COMMENT_INCREMENTAL_COLUMNS).
    """
    inspector = inspect(db.engine)
    if "task_comment" not in inspector.get_table_names():
        return False

    column_names = {column["name"] for column in inspector.get_columns("task_comment")}
    if "mentions" in column_names:
        return False

    db.session.execute(text("ALTER TABLE task_comment ADD COLUMN mentions JSON"))
    db.session.commit()
    return True


def _log_migration_failure(summary: dict) -> None:
    logging.getLogger(__name__).error(
        json.dumps(
            {
                "event": "schema_migration_failed",
                "failed_steps": summary.get("failed_steps", []),
                "step_errors": summary.get("step_errors", {}),
            },
            ensure_ascii=False,
        )
    )


def initialize_database() -> dict:
    """
    Inicializa/normaliza o schema usando a rotina canônica de migração.
    """
    from scripts.migrations.run_migrations import run_all_migrations

    summary = run_all_migrations(emit_output=False, stamp_alembic=False)
    if not summary.get("success"):
        _log_migration_failure(summary)
        return summary
    # Soft-delete C4: garante user.deleted_at no banco de dev no próximo boot,
    # sem migração manual (aditivo, mesmo padrão das demais ensure_*).
    ensure_user_deleted_at_column()
    ensure_task_comment_mentions_column()
    return summary
