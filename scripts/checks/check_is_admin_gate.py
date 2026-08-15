#!/usr/bin/env python3
"""Grep-gate contra novos usos inline de `.is_admin` no fonte (S1/F0-6).

A BASELINE congela os usos inline restantes (21 no nascimento, 17 depois de
S3/S4 pagarem parte deles) e só pode encolher: o gate não
conserta a dívida, impede que ela cresça enquanto as Fases 1-2 a pagam arquivo a
arquivo. Toda checagem de permissão nova nasce em `services/authorization.py`.

Uso:
    python scripts/checks/check_is_admin_gate.py

Sai 0 quando todo uso está na baseline ou na allowlist; 1 quando surge um uso
novo fora dela.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Iterator

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
_SELF: Path = Path(__file__).resolve()

# Módulos onde `.is_admin` é legítimo: o serviço central de autorização, o CRUD
# que grava a própria flag e os serializers que a expõem para a SPA.
ALLOWLIST: frozenset[str] = frozenset(
    {
        "services/authorization.py",
        "routes/api/admin_users.py",
        "routes/api/serializers.py",
        # Política de concessão: única escrita legítima da flag no fonte.
        "services/admin_grant_policy.py",
    }
)

# Baseline congelada em 2026-07-26 (S1/F0-6): nasceu com 21 usos em 14 arquivos;
# S3/F2-2 pagou `routes/projects/crud.py` (centralizado em
# `can_assign_project_to_orgao`), S3/F2-3 pagou `routes/projects/ajax.py`
# (centralizado em `user_can_reassign_project_to_orgao`) e S3/F2-5 pagou metade de
# `routes/tasks/permissions.py` (`_can_view_task` -> `user_can_view_project`; o uso
# restante é `_can_manage_task_restricted_actions`, intocado por decisão de
# produto) => 18 usos em 12 arquivos; S4/F3-8 pagou 1 uso de `routes/dashboard.py`
# (escopo de projeto centralizado em `project_visibility_criterion`) => 17 usos.
# Baixar um número aqui só depois de trocar o uso por chamada ao serviço (S3/S4).
BASELINE: dict[str, int] = {
    "app.py": 1,
    "routes/api/calendars.py": 1,
    "routes/dashboard.py": 2,
    "routes/decorators.py": 1,
    "routes/projects/views.py": 5,
    "routes/search.py": 1,
    "routes/tasks/creation.py": 1,
    "routes/tasks/hub.py": 1,
    "routes/tasks/permissions.py": 1,
    "routes/tasks/queries.py": 1,
    "services/notifications.py": 1,
}

EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "frontend",
        "static",
        "instance",
        "docs",
        "tests",
    }
)

_IS_ADMIN = re.compile(r"\.is_admin\b")


def _iter_source_files(repo_root: Path) -> Iterator[Path]:
    """Percorre os .py do fonte, podando venv/node_modules/tests/frontend."""
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            # O próprio gate cita o padrão na regex e nas mensagens.
            if path.suffix == ".py" and path.resolve() != _SELF:
                yield path


def scan_is_admin_counts(repo_root: Path) -> dict[str, int]:
    """Conta usos de `.is_admin` por arquivo do fonte, ignorando a allowlist."""
    counts: dict[str, int] = {}
    for path in _iter_source_files(repo_root):
        relative = path.relative_to(repo_root).as_posix()
        if relative in ALLOWLIST:
            continue
        hits = len(_IS_ADMIN.findall(path.read_text(encoding="utf-8")))
        if hits:
            counts[relative] = hits
    return counts


def find_new_usages(counts: dict[str, int]) -> list[str]:
    """Lista as violações: arquivos fora da baseline ou acima do limite dela."""
    violations: list[str] = []
    for relative, hits in sorted(counts.items()):
        frozen = BASELINE.get(relative, 0)
        if hits > frozen:
            violations.append(f"{relative}: {hits} usos (baseline {frozen})")
    return violations


def find_stale_baseline(counts: dict[str, int]) -> list[str]:
    """Lista entradas já pagas — o gate segue exit 0, mas a suíte exige lista vazia (baixar a BASELINE junto com o pagamento)."""
    stale: list[str] = []
    for relative, frozen in sorted(BASELINE.items()):
        hits = counts.get(relative, 0)
        if hits < frozen:
            stale.append(f"{relative}: {hits} usos (baseline {frozen})")
    return stale


def main() -> int:
    """Roda o gate no repositório e devolve o exit code do processo."""
    counts = scan_is_admin_counts(REPO_ROOT)
    for line in find_stale_baseline(counts):
        print(f"[baseline desatualizada, pode baixar] {line}")
    violations = find_new_usages(counts)
    if not violations:
        print(f"OK: {sum(counts.values())} usos inline, todos na baseline.")
        return 0
    print("FALHOU: uso novo de is_admin fora de services/authorization.py:")
    for line in violations:
        print(f"  - {line}")
    print("Centralize a checagem no serviço de autorização em vez de inline.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
