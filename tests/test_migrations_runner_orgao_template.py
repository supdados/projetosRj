"""Cobertura para o step `ensure_orgao_and_template_schema`.

Motivação (achado #1 do ultrareview em 2026-04-24):
bancos legados (MySQL em produção) não ganhavam as colunas introduzidas
pelas migrações `b2c4d6e8f0a1` (`project.orgao_id`) e `d2e4f6a8b1c0`
(auditoria em `StageTemplate`) porque `db.create_all()` só cria tabelas
inexistentes — não adiciona colunas em tabelas já presentes.

Como o SQLite do pytest não permite remover colunas com FK/índice, o teste
não reproduz o banco legado diretamente. Em vez disso, garante:

1. Constantes expõem o conjunto completo de colunas que devem existir.
2. Execução do step num banco já completo é no-op e idempotente.
3. As colunas/índices esperados existem após `db.create_all()` + step.
"""

from sqlalchemy import inspect

from models import db
from scripts.migrations.run_migrations import (
    ALEMBIC_HEAD,
    ORGAO_UNIDADE_INCREMENTAL_COLUMNS,
    PROJECT_ORGAO_COLUMN,
    STAGE_TEMPLATE_AUDIT_COLUMNS,
    ensure_orgao_and_template_schema,
)


def test_alembic_head_matches_latest_migration():
    # Se alguma migração nova for adicionada sem atualizar esta constante,
    # MySQL em produção pode ficar com alembic_version stale após rodar o script.
    assert ALEMBIC_HEAD == "b7c9e1f3a5d2"


def test_stage_template_audit_columns_cover_fase_0_audit_fields():
    expected = {"created_at", "updated_at", "created_by_id", "updated_by_id"}
    assert {name for name, _ in STAGE_TEMPLATE_AUDIT_COLUMNS} == expected


def test_orgao_unidade_incremental_columns_cover_tipo_and_siorg_minimum():
    expected = {
        "tipo_id",
        "codigo_externo",
        "data_inicio_vigencia",
        "data_fim_vigencia",
    }
    assert {name for name, _ in ORGAO_UNIDADE_INCREMENTAL_COLUMNS} == expected


def test_ensure_orgao_and_template_schema_smokes_and_is_idempotent(app):
    with app.app_context():
        first = ensure_orgao_and_template_schema(emit_output=False)
        assert first["success"] is True

        second = ensure_orgao_and_template_schema(emit_output=False)
        assert second["success"] is True
        # Segunda execução não deve adicionar nada novo (nem colunas, nem índices).
        assert second["changes"] == []


def test_stage_template_has_all_audit_columns_after_runner(app):
    with app.app_context():
        ensure_orgao_and_template_schema(emit_output=False)
        inspector = inspect(db.engine)
        columns = {c["name"] for c in inspector.get_columns("StageTemplate")}
        for column_name, _ in STAGE_TEMPLATE_AUDIT_COLUMNS:
            assert column_name in columns, f"StageTemplate sem coluna {column_name}"

        project_columns = {c["name"] for c in inspector.get_columns("project")}
        assert PROJECT_ORGAO_COLUMN[0] in project_columns

        assert "orgao_tipo" in inspector.get_table_names()
        assert "orgao_closure" in inspector.get_table_names()
        orgao_columns = {c["name"] for c in inspector.get_columns("orgao_unidade")}
        for column_name, _ in ORGAO_UNIDADE_INCREMENTAL_COLUMNS:
            assert (
                column_name in orgao_columns
            ), f"orgao_unidade sem coluna {column_name}"
