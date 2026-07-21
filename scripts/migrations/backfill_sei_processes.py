"""Backfill: converte ``Project.sei_process`` (texto único legado) em ``ProjectSeiProcess``.

Contexto (2026-07-03): um projeto passou a aceitar MÚLTIPLOS números de
processo SEI, guardados na tabela filha ``project_sei_process``. Este passo
roda a cada boot (via ``run_all_migrations``) com semântica expand-contract:

- Escalar que ainda não existe entre os filhos vira um filho novo — cobre
  tanto o legado pré-feature quanto edições feitas por instância antiga
  durante um rolling deploy (o código velho grava só na coluna).
- Depois a coluna é reescrita como ESPELHO do primeiro filho (o caminho novo
  de escrita, ``replace_project_sei_numbers``, mantém o mesmo espelho): um
  rollback do release continua exibindo o primeiro número em vez de "vazio".

Números removidos pela UI não ressuscitam: a remoção atualiza o espelho junto,
então o escalar nunca fica "à frente" dos filhos. Texto legado que não casa
com o formato é preservado verbatim (sem perda de informação).
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import Project, ProjectSeiProcess, db
from services.sei_process import normalize_sei_number_or_raw


def _absorb_legacy_scalar(project: Project) -> int:
    """Cria um filho para o escalar quando ele ainda não existe na coleção."""
    raw = (project.sei_process or "").strip()
    if not raw:
        return 0
    canonical = normalize_sei_number_or_raw(raw)
    existing = {item.numero.lower() for item in project.sei_processes}
    if not canonical or canonical.lower() in existing:
        return 0
    project.sei_processes.append(
        ProjectSeiProcess(numero=canonical, ordem=len(project.sei_processes))
    )
    return 1


def _mirror_first_number(project: Project) -> None:
    """Reescreve a coluna legada como espelho do primeiro filho (ou ``None``)."""
    project.sei_process = (
        project.sei_processes[0].numero if project.sei_processes else None
    )


def backfill_sei_processes(emit_output: bool = True) -> dict:
    """Passo de migração: coluna legada <-> ``project_sei_process`` (idempotente).

    Returns:
        ``{"success": bool, "migrated": int}``.
    """
    from scripts.migrations.run_migrations import _emit

    _emit(
        "\n-- Backfill de processos SEI (coluna legada -> project_sei_process)...",
        emit_output,
    )
    try:
        db.create_all()
        migrated = 0
        pending = Project.query.filter(Project.sei_process.isnot(None)).all()
        for project in pending:
            migrated += _absorb_legacy_scalar(project)
            _mirror_first_number(project)
        db.session.commit()
        if migrated:
            _emit(f"   ✓ {migrated} processos SEI migrados.", emit_output)
        else:
            _emit("   ✓ Nenhum processo SEI legado pendente.", emit_output)
        return {"success": True, "migrated": migrated}
    except Exception as exc:
        db.session.rollback()
        _emit(f"   ✗ ERRO no backfill de processos SEI: {exc}", emit_output)
        return {"success": False, "error": str(exc), "migrated": 0}
