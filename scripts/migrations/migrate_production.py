#!/usr/bin/env python3
"""
Wrapper de compatibilidade para produção.

Mantido apenas para preservar o comando histórico:
    python3 scripts/migrations/migrate_production.py

Toda a lógica real de migração agora vive em:
    scripts/migrations/run_migrations.py
"""

import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def build_engine():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return create_engine(database_url)

    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    name = os.getenv("DB_NAME")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "3306")

    if not all([user, password, name]):
        print("ERRO: Configure DATABASE_URL ou DB_USER / DB_PASSWORD / DB_NAME no .env")
        sys.exit(1)

    uri = f"mysql+pymysql://{user}:{quote_plus(password)}@{host}:{port}/{name}"
    return create_engine(uri)


def main():
    engine = build_engine()

    if engine.dialect.name != "mysql":
        print(
            f"ERRO: este wrapper é exclusivo para MySQL. Dialeto detectado: {engine.dialect.name}"
        )
        return 1

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        print(f"ERRO ao conectar: {exc}")
        return 1

    from app import app
    from models import db
    from scripts.migrations.run_migrations import run_all_migrations

    with app.app_context():
        if db.engine.dialect.name != "mysql":
            print(
                "ERRO: a aplicação não está conectada em MySQL. "
                f"Dialeto detectado no app: {db.engine.dialect.name}"
            )
            return 1

        summary = run_all_migrations(emit_output=True, stamp_alembic=True)
        return 0 if summary.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
