#!/usr/bin/env python3
"""Backfill: re-encripta tokens OAuth do Google Calendar gravados em plaintext.

Sprint 5.3: este passo saiu do boot (era o step ``encrypt_plaintext_oauth_tokens``
de ``run_migrations``) e virou comando explícito de deploy. Opera em SQL cru
porque as colunas usam o TypeDecorator ``EncryptedText`` — pelo ORM o valor em
repouso nunca seria visível. Idempotente: valores já em formato Fernet são pulados.

Uso:
    python3 scripts/migrations/encrypt_oauth_tokens.py            # dry-run
    python3 scripts/migrations/encrypt_oauth_tokens.py --apply    # grava
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Backfill de dados puro: importar o app não deve rodar verificação de schema.
os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")

from sqlalchemy import inspect, text

from models import db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-encripta tokens OAuth em plaintext (user_calendar_connection)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Grava as alterações (default é dry-run, que só relata contagens).",
    )
    return parser.parse_args()


def _plaintext_token_updates(row: tuple[int, str | None, str | None]) -> dict[str, str]:
    """Colunas a re-encriptar numa linha (id, access_token, refresh_token)."""
    from services.token_crypto import encrypt_value, looks_like_fernet

    _, access, refresh = row
    updates: dict[str, str] = {}
    if access and not looks_like_fernet(access):
        updates["access_token"] = encrypt_value(access)
    if refresh and not looks_like_fernet(refresh):
        updates["refresh_token"] = encrypt_value(refresh)
    return updates


def encrypt_pending_oauth_tokens(*, apply: bool) -> dict[str, int]:
    """Encripta (ou só conta, em dry-run) tokens plaintext; devolve contadores.

    Ex.: ``encrypt_pending_oauth_tokens(apply=False) -> {"rows_scanned": 3,
    "rows_pending": 1, "rows_encrypted": 0}``. Não commita — o chamador decide.
    """
    inspector = inspect(db.engine)
    if "user_calendar_connection" not in inspector.get_table_names():
        return {"rows_scanned": 0, "rows_pending": 0, "rows_encrypted": 0}

    rows = db.session.execute(
        text("SELECT id, access_token, refresh_token FROM user_calendar_connection")
    ).all()

    pending = 0
    encrypted = 0
    for row in rows:
        updates = _plaintext_token_updates(row)
        if not updates:
            continue
        pending += 1
        if not apply:
            continue
        set_clause = ", ".join(f"{col} = :{col}" for col in updates)
        db.session.execute(
            text(
                f"UPDATE user_calendar_connection SET {set_clause} WHERE id = :conn_id"
            ),
            {**updates, "conn_id": row[0]},
        )
        encrypted += 1

    return {
        "rows_scanned": len(rows),
        "rows_pending": pending,
        "rows_encrypted": encrypted,
    }


def main() -> int:
    args = parse_args()
    from app import app

    with app.app_context():
        print(f"Banco: {app.config['SQLALCHEMY_DATABASE_URI']}")
        stats = encrypt_pending_oauth_tokens(apply=args.apply)
        print(f"Conexões de calendário examinadas: {stats['rows_scanned']}")
        print(f"Linhas com token em plaintext: {stats['rows_pending']}")
        if not args.apply:
            print("\nDry-run: nada gravado. Use --apply para gravar.")
            return 0
        db.session.commit()
        print(f"\nGravado: {stats['rows_encrypted']} linha(s) re-encriptada(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
