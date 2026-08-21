#!/usr/bin/env python3
"""Verificação legada do campo ABEP — NÃO emite DDL (Sprint 5.4).

Mantido apenas para preservar o comando histórico:
    python3 scripts/migrations/migrate_add_abep_indicator.py

O schema tem um produtor único: `alembic upgrade head`. Este script só
CONFERE se `project.abep_indicator` já existe e diz o que fazer quando não
existe — antes ele chamava `db.create_all()` e o runner aposentado.

Saída: 0 = coluna presente; 1 = banco não migrado (rode `alembic upgrade head`).
"""

from pathlib import Path
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Roda DURANTE a migração, contra banco fora do head: importar o app não pode
# disparar verify_schema_version() e matar o script antes do primeiro trabalho.
os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")

from sqlalchemy import inspect

app = None

UPGRADE_HINT = "Rode `alembic upgrade head` (produtor único de schema)."


def _resolve_app():
    global app
    if app is None:
        from app import app as flask_app

        app = flask_app
    return app


def check_abep_indicator_column(emit_output: bool = True) -> int:
    """Confere `project.abep_indicator` no banco configurado.

    Returns:
        ``0`` quando a coluna existe; ``1`` quando a tabela ou a coluna faltam.

    Example:
        >>> check_abep_indicator_column(emit_output=False)  # doctest: +SKIP
        0
    """
    from models import db

    def emit(message: str) -> None:
        if emit_output:
            print(message)

    inspector = inspect(db.engine)
    if "project" not in inspector.get_table_names():
        emit(f"ERRO: tabela 'project' não existe. {UPGRADE_HINT}")
        return 1

    columns = {column["name"] for column in inspector.get_columns("project")}
    if "abep_indicator" not in columns:
        emit(f"ERRO: coluna 'abep_indicator' ausente. {UPGRADE_HINT}")
        return 1

    emit("Coluna 'abep_indicator' já existe. Nada a fazer.")
    return 0


def main() -> int:
    with _resolve_app().app_context():
        return check_abep_indicator_column()


if __name__ == "__main__":
    raise SystemExit(main())
