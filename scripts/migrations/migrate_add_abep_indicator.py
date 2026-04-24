#!/usr/bin/env python3
"""
Wrapper legado para a antiga migração dedicada do campo ABEP.

Mantido apenas para preservar o comando histórico:
    python3 scripts/migrations/migrate_add_abep_indicator.py

A lógica real de schema agora vive em:
    scripts/migrations/run_migrations.py
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect

app = None


def main():
    global app
    if app is None:
        from app import app as flask_app

        app = flask_app
    from models import db
    from scripts.migrations.run_migrations import ensure_project_columns

    with app.app_context():
        inspector = inspect(db.engine)
        table_names = inspector.get_table_names()

        if "project" not in table_names:
            print("Tabela 'project' não encontrada. Executando create_all...")
            db.create_all()
            inspector = inspect(db.engine)
            table_names = inspector.get_table_names()
            if "project" not in table_names:
                print("ERRO: tabela 'project' ainda não existe após create_all.")
                return 1

        columns = {column["name"] for column in inspector.get_columns("project")}
        if "abep_indicator" in columns:
            print("Coluna 'abep_indicator' já existe. Nada a fazer.")
            return 0

        summary = ensure_project_columns(emit_output=False)
        if not summary.get("success"):
            return 1

        if "project.abep_indicator" in summary.get("added_columns", []):
            print("Coluna 'abep_indicator' adicionada com sucesso.")
            return 0

        print("Coluna 'abep_indicator' já existe. Nada a fazer.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
