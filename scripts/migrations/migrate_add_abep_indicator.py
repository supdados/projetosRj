#!/usr/bin/env python3
"""
Migração idempotente para adicionar o campo project.abep_indicator.

Compatível com SQLite e MySQL.

Uso:
    python3 scripts/migrations/migrate_add_abep_indicator.py
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect, text
from app import app, db


def main():
    with app.app_context():
        inspector = inspect(db.engine)
        table_names = inspector.get_table_names()

        if 'project' not in table_names:
            print("Tabela 'project' não encontrada. Executando create_all...")
            db.create_all()
            inspector = inspect(db.engine)
            table_names = inspector.get_table_names()
            if 'project' not in table_names:
                print("ERRO: tabela 'project' ainda não existe após create_all.")
                return 1

        columns = {column["name"] for column in inspector.get_columns('project')}
        if 'abep_indicator' in columns:
            print("Coluna 'abep_indicator' já existe. Nada a fazer.")
            return 0

        db.session.execute(text("ALTER TABLE project ADD COLUMN abep_indicator VARCHAR(255)"))
        db.session.commit()
        print("Coluna 'abep_indicator' adicionada com sucesso.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
