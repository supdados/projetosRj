#!/usr/bin/env python3
"""Eleição one-shot do super admin inicial (RBAC S1).

Sprint 5.3: saiu do boot (era parte do step ``ensure_user_is_super_admin_column``
de ``run_migrations``) e virou comando explícito de instalação. Promove o MENOR
id entre os admins ATIVOS, e SÓ quando não existe nenhum super admin (inclusive
soft-deletado) — re-execução nunca reelege.

Uso:
    python3 scripts/migrations/elect_super_admin.py            # dry-run
    python3 scripts/migrations/elect_super_admin.py --apply    # grava
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Mutação de dados pura: importar o app não deve rodar verificação de schema.
os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")

from sqlalchemy import text

from models import db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promove o admin ativo de menor id a super admin inicial."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Grava a promoção (default é dry-run, que só relata o candidato).",
    )
    return parser.parse_args()


def find_initial_super_admin_id() -> int | None:
    """Menor id entre admins ativos, ou None se já existe super admin/nenhum admin.

    Ex.: ``find_initial_super_admin_id() -> 1``.
    """
    # Duas queries: o MySQL (erro 1093) proíbe subquery na tabela do próprio UPDATE.
    ja_existe = db.session.execute(
        text("SELECT COUNT(*) FROM `user` WHERE is_super_admin = 1")
    ).scalar()
    if ja_existe:
        return None
    return db.session.execute(
        text("SELECT MIN(id) FROM `user` WHERE is_admin = 1 AND deleted_at IS NULL")
    ).scalar()


def elect_initial_super_admin() -> int | None:
    """Promove o candidato de ``find_initial_super_admin_id``; devolve o id ou None.

    NÃO commita — o chamador decide. Ex.: ``elect_initial_super_admin() -> 1``.
    """
    alvo = find_initial_super_admin_id()
    if alvo is None:
        return None
    db.session.execute(
        text("UPDATE `user` SET is_super_admin = 1 WHERE id = :uid"), {"uid": alvo}
    )
    return alvo


def main() -> int:
    args = parse_args()
    from app import app

    with app.app_context():
        print(f"Banco: {app.config['SQLALCHEMY_DATABASE_URI']}")
        if not args.apply:
            candidato = find_initial_super_admin_id()
            print(f"Candidato a super admin inicial: {candidato or 'nenhum'}")
            print("\nDry-run: nada gravado. Use --apply para gravar.")
            return 0
        eleito = elect_initial_super_admin()
        db.session.commit()
        print(f"Super admin eleito: {eleito or 'nenhum (já definido ou sem admins)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
