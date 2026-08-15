#!/usr/bin/env python3
"""Migração de produção (MySQL) — fluxo Alembic da Sprint 5.3.

Preserva o comando histórico:
    python3 scripts/migrations/migrate_production.py

Equivale a `alembic upgrade head` com guarda de dialeto MySQL. Em instalação
LIMPA, rode depois os comandos de dados documentados no README:
    python3 scripts/catalog/sync_objectives_catalog.py
    python3 scripts/migrations/elect_super_admin.py --apply
    python3 scripts/migrations/encrypt_oauth_tokens.py --apply
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# O upgrade roda ANTES de o schema estar no head: a verificação de boot pularia.
os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")


def main() -> int:
    from flask_migrate import upgrade

    from app import app
    from models import db
    from startup import alembic_head_revision, database_schema_revision

    with app.app_context():
        if db.engine.dialect.name != "mysql":
            print(
                "ERRO: este wrapper é exclusivo para MySQL. "
                f"Dialeto detectado no app: {db.engine.dialect.name}"
            )
            return 1

        head = alembic_head_revision()
        print(f"Revisão atual do banco: {database_schema_revision() or 'nenhuma'}")
        print(f"Head do código: {head}")
        upgrade()
        print(f"OK: banco em `alembic upgrade head` ({head}).")
        print(
            "Instalação limpa? Rode agora os comandos de dados do README "
            "(sync_objectives_catalog, elect_super_admin --apply, "
            "encrypt_oauth_tokens --apply)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
