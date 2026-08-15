#!/usr/bin/env python3
"""Backfill em massa de ``User.cpf_govbr`` a partir do username legado (one-shot).

Contexto (2026-08-15, auditoria §2.8): usuários criados antes do login gov.br
guardam o CPF no ``username`` (com ou sem pontuação) e têm ``cpf_govbr`` vazio.
O callback OIDC compensava isso com um scan O(n) de todos os usuários,
normalizando cada username em Python. Preenchendo a coluna indexada de uma vez,
o vínculo passa a ser resolvido por índice (``routes/auth.py``).

A normalização é a MESMA do scan: ``services.govbr_oidc.normalize_cpf``, a
função que ``routes/auth.py`` importa (nada é copiado aqui).

Idempotente: usuário que já tem ``cpf_govbr`` nunca é reescrito. Quando dois
usuários normalizam para o mesmo CPF (ou o CPF já pertence a outro usuário),
NADA é gravado — a coluna é UNIQUE e a decisão é humana; o conflito é listado.

Uso:
    python3 scripts/migrations/backfill_cpf_govbr.py             # dry-run (default)
    python3 scripts/migrations/backfill_cpf_govbr.py --dry-run   # idem, explícito
    python3 scripts/migrations/backfill_cpf_govbr.py --apply     # grava
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask

from models import User, db
from services.govbr_oidc import normalize_cpf


@dataclass
class CpfBackfillPlan:
    """Plano do backfill: o que gravar e quais CPFs ficaram em conflito."""

    to_write: list[tuple[int, str, str]] = field(default_factory=list)
    conflicts: dict[str, list[str]] = field(default_factory=dict)
    already_filled: int = 0


def _cpf_from_username(username: str | None) -> str | None:
    """CPF normalizado do username legado; ``None`` quando não é um CPF."""
    try:
        return normalize_cpf(username)
    except ValueError:
        return None


def _owner_by_cpf(users: list[User]) -> dict[str, str]:
    """CPF já gravado -> username do dono (a coluna ``cpf_govbr`` é UNIQUE)."""
    return {
        user.cpf_govbr.strip(): user.username
        for user in users
        if (user.cpf_govbr or "").strip()
    }


def _candidates_by_cpf(users: list[User]) -> dict[str, list[User]]:
    """CPF derivado do username -> usuários sem ``cpf_govbr`` que o reivindicam."""
    candidates: dict[str, list[User]] = {}
    for user in users:
        if (user.cpf_govbr or "").strip():
            continue
        cpf = _cpf_from_username(user.username)
        if cpf:
            candidates.setdefault(cpf, []).append(user)
    return candidates


def build_cpf_backfill_plan(users: list[User]) -> CpfBackfillPlan:
    """Decide o backfill sem tocar no banco.

    Exemplo: ``build_cpf_backfill_plan(User.query.all()).to_write``.
    """
    owners = _owner_by_cpf(users)
    plan = CpfBackfillPlan(already_filled=len(owners))
    for cpf, claimants in sorted(_candidates_by_cpf(users).items()):
        disputants = [user.username for user in claimants]
        if cpf in owners:
            disputants.append(owners[cpf])
        if len(disputants) > 1:
            plan.conflicts[cpf] = sorted(disputants)
            continue
        plan.to_write.append((claimants[0].id, claimants[0].username, cpf))
    return plan


def apply_cpf_backfill(plan: CpfBackfillPlan) -> int:
    """Grava o plano (commit único) e devolve quantos usuários foram alterados."""
    for user_id, _username, cpf in plan.to_write:
        db.session.get(User, user_id).cpf_govbr = cpf
    db.session.commit()
    return len(plan.to_write)


def _print_report(plan: CpfBackfillPlan, applied: bool) -> None:
    print(f"Usuários com cpf_govbr já preenchido: {plan.already_filled}")
    for _user_id, username, cpf in plan.to_write:
        print(f"  {'gravado' if applied else 'gravaria'}: {username} -> {cpf}")
    for cpf, disputants in sorted(plan.conflicts.items()):
        print(f"  CONFLITO (não gravado) {cpf}: {', '.join(disputants)}")
    verb = "Gravados" if applied else "Dry-run: gravaria"
    print(
        f"\n{verb} {len(plan.to_write)} usuário(s); {len(plan.conflicts)} conflito(s)."
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preenche User.cpf_govbr a partir do username legado.",
    )
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--apply", action="store_true", help="Grava as alterações.")
    modo.add_argument(
        "--dry-run", action="store_true", help="Só relata (comportamento padrão)."
    )
    return parser.parse_args()


def _standalone_app() -> Flask:
    """App mínimo só com o ORM: importar ``app`` rodaria as migrações do boot."""
    from config import _resolve_database_uri
    from time_utils import register_sqlite_adapters

    flask_app = Flask(__name__)
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = _resolve_database_uri()
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if flask_app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:"):
        register_sqlite_adapters()
    db.init_app(flask_app)
    return flask_app


def main() -> int:
    args = _parse_args()
    with _standalone_app().app_context():
        plan = build_cpf_backfill_plan(User.query.order_by(User.id).all())
        if args.apply:
            apply_cpf_backfill(plan)
        _print_report(plan, applied=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
