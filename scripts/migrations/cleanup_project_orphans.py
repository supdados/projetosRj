"""P1-01: saneia filhos de projetos já apagados, sem alterar vínculos válidos.

Executar no deploy com as escritas suspensas, antes de criar novos projetos:
``python scripts/migrations/cleanup_project_orphans.py`` inventaria;
``python scripts/migrations/cleanup_project_orphans.py --apply`` remove.

Não identifica vínculos cujo ID já foi reutilizado antes da correção: esses
casos exigem confronto com histórico/backup, sem remoção automática por palpite.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from collections.abc import Sequence

from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import Project, ProjectCollectionItem, ProjectMember, StageTemplateUsage, db


def cleanup_project_orphans(session: Session, *, apply: bool = False) -> dict[str, int]:
    """Conta/remove apenas filhos cujo projeto não existe, numa única transação.

    Exemplo: ``cleanup_project_orphans(db.session(), apply=False)``.
    """
    counts: dict[str, int] = {}
    try:
        for model in (ProjectMember, ProjectCollectionItem, StageTemplateUsage):
            parent_exists = (
                session.query(Project.id)
                .filter(Project.id == model.project_id)
                .exists()
            )
            orphans = session.query(model).filter(~parent_exists)
            counts[model.__tablename__] = (
                orphans.delete(synchronize_session=False) if apply else orphans.count()
            )
        if apply:
            session.commit()
        return counts
    except Exception:
        session.rollback()
        raise


def main(argv: Sequence[str] | None = None) -> int:
    """CLI com dry-run padrão; ``main(['--apply'])`` aplica o saneamento."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Remove os órfãos; sem esta opção apenas conta.",
    )
    args = parser.parse_args(argv)
    os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")
    from app import create_app

    app = create_app({"SKIP_STARTUP_DB_INIT": True})
    with app.app_context():
        counts = cleanup_project_orphans(db.session(), apply=args.apply)
    print(json.dumps({"applied": args.apply, "orphans": counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
