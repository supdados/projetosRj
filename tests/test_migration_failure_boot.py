"""Regressão bug 2.18: falha parcial de migração não pode ser mascarada no boot.

Antes, um step falhando fazia ``run_all_migrations`` retornar apenas
``{"success": False}``; ``app.py`` acessava ``summary["column_added"]`` →
``KeyError`` engolido por ``except Exception`` e o app subia com schema parcial.
"""

import pytest

import app as app_module
import startup as startup_module
from app import _abort_boot_on_migration_failure, create_app
from scripts.migrations import run_migrations as run_migrations_module
from scripts.migrations.run_migrations import run_all_migrations
from startup import initialize_database


class FakeFailingTaskSchemaStep:
    """Step que simula falha no meio da sequência de migração."""

    def __call__(self, emit_output: bool = True) -> dict:
        return {"success": False, "error": "boom no schema de tarefas", "changes": []}


class FakeFailedMigrationRunner:
    """run_all_migrations que devolve summary completo com success=False."""

    def __call__(
        self, *, emit_output: bool = True, stamp_alembic: bool = False
    ) -> dict:
        return {
            "success": False,
            "failed_steps": ["ensure_task_schema"],
            "step_errors": {"ensure_task_schema": "boom no schema de tarefas"},
            "column_added": False,
            "sync_summary": None,
        }


class FakeDeletedAtEnsurer:
    """Registra se o passo pós-migração foi executado."""

    def __init__(self) -> None:
        self.called = False

    def __call__(self) -> bool:
        self.called = True
        return False


def test_step_failing_mid_run_returns_full_summary_with_error(app, monkeypatch):
    monkeypatch.setattr(
        run_migrations_module, "ensure_task_schema", FakeFailingTaskSchemaStep()
    )
    with app.app_context():
        summary = run_all_migrations(emit_output=False, stamp_alembic=False)

    assert summary["success"] is False
    assert summary["failed_steps"] == ["ensure_task_schema"]
    assert summary["step_errors"] == {"ensure_task_schema": "boom no schema de tarefas"}
    assert summary["column_added"] is False
    assert isinstance(summary["project_columns_added"], list)
    assert "sync_summary" in summary
    assert "task_core_cols" in summary


def test_run_all_migrations_success_keeps_success_contract(app):
    with app.app_context():
        summary = run_all_migrations(emit_output=False, stamp_alembic=False)

    assert summary["success"] is True
    assert summary["failed_steps"] == []
    assert summary["step_errors"] == {}


def test_initialize_database_logs_failure_and_skips_post_steps(
    app, monkeypatch, caplog
):
    fake_ensurer = FakeDeletedAtEnsurer()
    monkeypatch.setattr(
        run_migrations_module, "run_all_migrations", FakeFailedMigrationRunner()
    )
    monkeypatch.setattr(startup_module, "ensure_user_deleted_at_column", fake_ensurer)

    with app.app_context(), caplog.at_level("ERROR", logger="startup"):
        summary = initialize_database()

    assert summary["success"] is False
    assert fake_ensurer.called is False
    assert any("schema_migration_failed" in record.message for record in caplog.records)
    assert any(
        "boom no schema de tarefas" in record.message for record in caplog.records
    )


def test_abort_helper_raises_with_real_error_on_failure():
    failed_summary = FakeFailedMigrationRunner()(emit_output=False)

    with pytest.raises(RuntimeError) as excinfo:
        _abort_boot_on_migration_failure(failed_summary)

    assert "ensure_task_schema" in str(excinfo.value)
    assert "boom no schema de tarefas" in str(excinfo.value)


def test_abort_helper_is_noop_on_success():
    assert _abort_boot_on_migration_failure({"success": True}) is None


def test_create_app_aborts_boot_when_migration_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "initialize_database", FakeFailedMigrationRunner())
    db_path = tmp_path / "boot-abort.sqlite"

    with pytest.raises(RuntimeError, match="ensure_task_schema"):
        create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
                "SKIP_STARTUP_DB_INIT": False,
            }
        )
