#!/usr/bin/env python3
"""
Sincroniza o catalogo canonico de objetivos/resultados/indicadores no banco.

Sincroniza DADOS, nunca schema: o banco precisa estar migrado (`alembic
upgrade head`) antes. Até a Sprint 5.4 este script chamava `db.create_all()`.

Uso:
    python3 scripts/catalog/sync_objectives_catalog.py
    python3 scripts/catalog/sync_objectives_catalog.py --dry-run
"""

import argparse
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

from app import app, db
from models import Objetivo, ResultadoEsperado, Indicador
from catalogs.objectives import sync_goal_catalog_to_db

CATALOG_TABLES = ("objetivo", "resultado_esperado", "indicador")


def _masked_db_uri(uri):
    # mascara credenciais para logs (mysql+pymysql://user:***@host/db)
    if "://" not in uri or "@" not in uri:
        return uri
    scheme, rest = uri.split("://", 1)
    if ":" in rest and "@" in rest:
        creds, tail = rest.split("@", 1)
        if ":" in creds:
            user, _ = creds.split(":", 1)
            return f"{scheme}://{user}:***@{tail}"
    return uri


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sincroniza o catalogo de objetivos/resultados/indicadores no banco atual."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa validacao/sync sem persistir alteracoes.",
    )
    return parser.parse_args()


def missing_catalog_tables() -> list[str]:
    """Lista as tabelas de catalogo ausentes no banco configurado."""
    existing = set(inspect(db.engine).get_table_names())
    return [table for table in CATALOG_TABLES if table not in existing]


def main():
    args = parse_args()

    with app.app_context():
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        print("=" * 72)
        print("SYNC DE CATALOGO (OBJETIVO/RESULTADO/INDICADOR)")
        print("=" * 72)
        print(f"Banco alvo: {_masked_db_uri(db_uri)}")
        print(f"Modo dry-run: {'SIM' if args.dry_run else 'NAO'}")
        print()

        missing = missing_catalog_tables()
        if missing:
            print(
                f"\nERRO: tabelas ausentes: {', '.join(missing)}. "
                "Rode `alembic upgrade head` (produtor unico de schema)."
            )
            return 1

        try:
            summary = sync_goal_catalog_to_db(commit=not args.dry_run)

            if args.dry_run:
                db.session.rollback()
                print("dry-run: rollback executado")
            else:
                print("commit: alteracoes persistidas")

            print("\nResumo da sincronizacao:")
            for key, value in summary.items():
                print(f"- {key}: {value}")

            print("\nTotais apos sincronizacao:")
            print(f"- objetivos: {Objetivo.query.count()}")
            print(f"- resultados_esperados: {ResultadoEsperado.query.count()}")
            print(f"- indicadores: {Indicador.query.count()}")

            print("\nConcluido com sucesso.")
            return 0

        except Exception as exc:
            db.session.rollback()
            print(f"\nERRO: {exc}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
