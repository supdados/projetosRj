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

# Total de usos inline quando o gate nasceu (S1/F0-6): teto histórico, nunca meta.
USOS_NO_NASCIMENTO_DO_GATE = 21

# Derivado do próprio BASELINE — repetir o número aqui foi o que quebrou estes
# testes quando S4 pagou um uso de routes/dashboard.py.
ARQUIVO_COM_VARIOS_USOS, USOS_CONGELADOS = next(
    ((relative, frozen) for relative, frozen in sorted(BASELINE.items()) if frozen > 1),
    max(sorted(BASELINE.items()), key=lambda item: item[1]),
)


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


def test_baseline_so_encolhe_desde_o_nascimento_do_gate():
    assert sum(BASELINE.values()) <= USOS_NO_NASCIMENTO_DO_GATE


def test_baseline_nao_tem_folga_sobre_o_fonte():
    """Baseline acima do fonte seria espaço grátis para reintroduzir uso inline."""
    assert find_stale_baseline(scan_is_admin_counts(REPO_ROOT)) == []


# ── Detecção de violações ─────────────────────────────────────────────────────


def test_arquivo_novo_fora_da_allowlist_reprova():
    violations = find_new_usages({"routes/api/projetos_novos.py": 1})
    assert violations == ["routes/api/projetos_novos.py: 1 usos (baseline 0)"]


def test_uso_extra_em_arquivo_da_baseline_reprova():
    acima = USOS_CONGELADOS + 1
    violations = find_new_usages({ARQUIVO_COM_VARIOS_USOS: acima})
    assert violations == [
        f"{ARQUIVO_COM_VARIOS_USOS}: {acima} usos (baseline {USOS_CONGELADOS})"
    ]


def test_uso_dentro_da_baseline_nao_reprova():
    assert find_new_usages({ARQUIVO_COM_VARIOS_USOS: USOS_CONGELADOS}) == []


def test_uso_removido_apenas_marca_baseline_desatualizada():
    abaixo = USOS_CONGELADOS - 1
    counts = {**BASELINE, ARQUIVO_COM_VARIOS_USOS: abaixo}
    assert find_new_usages(counts) == []
    assert find_stale_baseline(counts) == [
        f"{ARQUIVO_COM_VARIOS_USOS}: {abaixo} usos (baseline {USOS_CONGELADOS})"
    ]


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
