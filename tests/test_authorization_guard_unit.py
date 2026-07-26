"""Testes do grep-gate de `.is_admin` (scripts/checks/check_is_admin_gate.py)."""

import subprocess
import sys
from pathlib import Path

from scripts.checks.check_is_admin_gate import (
    BASELINE,
    REPO_ROOT,
    find_new_usages,
    find_stale_baseline,
    scan_is_admin_counts,
)

GATE_SCRIPT = REPO_ROOT / "scripts" / "checks" / "check_is_admin_gate.py"


def _write(root: Path, relative: str, body: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


# ── Estado atual do repositório ───────────────────────────────────────────────


def test_gate_passa_no_repositorio_atual():
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FALHOU" not in result.stdout


def test_fonte_atual_nao_tem_uso_novo():
    assert find_new_usages(scan_is_admin_counts(REPO_ROOT)) == []


def test_baseline_congelada_em_21_usos():
    assert sum(BASELINE.values()) == 21


# ── Detecção de violações ─────────────────────────────────────────────────────


def test_arquivo_novo_fora_da_allowlist_reprova():
    violations = find_new_usages({"routes/api/projetos_novos.py": 1})
    assert violations == ["routes/api/projetos_novos.py: 1 usos (baseline 0)"]


def test_uso_extra_em_arquivo_da_baseline_reprova():
    violations = find_new_usages({"routes/dashboard.py": 4})
    assert violations == ["routes/dashboard.py: 4 usos (baseline 3)"]


def test_uso_dentro_da_baseline_nao_reprova():
    assert find_new_usages({"routes/dashboard.py": 3}) == []


def test_uso_removido_apenas_marca_baseline_desatualizada():
    counts = {**scan_is_admin_counts(REPO_ROOT), "routes/dashboard.py": 1}
    assert find_new_usages(counts) == []
    assert find_stale_baseline(counts) == ["routes/dashboard.py: 1 usos (baseline 3)"]


# ── Escopo da varredura ───────────────────────────────────────────────────────


def test_scan_conta_fonte_e_pula_allowlist(tmp_path):
    _write(tmp_path, "routes/qualquer.py", "if g.user.is_admin:\n    pass\n")
    _write(tmp_path, "routes/api/serializers.py", '{"is_admin": user.is_admin}\n')
    assert scan_is_admin_counts(tmp_path) == {"routes/qualquer.py": 1}


def test_scan_ignora_tests_venv_e_frontend(tmp_path):
    _write(tmp_path, "tests/test_x.py", "user.is_admin\n")
    _write(tmp_path, ".venv/lib/mod.py", "user.is_admin\n")
    _write(tmp_path, "frontend/build.py", "user.is_admin\n")
    assert scan_is_admin_counts(tmp_path) == {}


def test_scan_conta_multiplas_ocorrencias_por_arquivo(tmp_path):
    _write(tmp_path, "routes/x.py", "a.is_admin or b.is_admin\nc.is_admin_flag\n")
    assert scan_is_admin_counts(tmp_path) == {"routes/x.py": 2}
