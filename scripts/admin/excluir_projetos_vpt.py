"""Exclui os projetos da demanda de saneamento da VPT (ago/2026), um a um.

A lista vem de ``exclusao_projetos_vpt_2026-08.csv`` (id + título extraídos da
planilha "ConsolidadoVPT_Saneamento_V2.xlsx", aba TotalVPT). Cada id só é
excluído se o título do banco casar com o da planilha — divergência ou id
inexistente pula e reporta, nunca apaga.

Semântica igual à rota ``DELETE /api/projetos/<id>`` (cascade ORM leva etapas,
indicadores, SEI, links e histórico), com uma diferença deliberada: as tarefas
do projeto são excluídas junto — o delete da rota as deixaria órfãs
(``project_id=NULL``) e elas ressurgiriam como tarefas pessoais do criador.

Dry-run por padrão; ``--apply`` grava em lotes com commit por lote.
Pré-requisito em produção: mysqldump antes de rodar com --apply.
"""

import csv
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CSV_PADRAO = Path(__file__).with_name("exclusao_projetos_vpt_2026-08.csv")
TAMANHO_LOTE = 50


def carregar_lista_exclusao(caminho: Path) -> list[tuple[int, str]]:
    """Lê os pares (id, titulo) do CSV da demanda."""
    with open(caminho, encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    if not linhas:
        raise SystemExit(f"CSV vazio: {caminho}")
    return [(int(linha["id"]), linha["titulo"].strip()) for linha in linhas]


def conferir_projeto(project, titulo_planilha: str) -> str | None:
    """Devolve o motivo para pular, ou None quando o projeto confere."""
    if project is None:
        return "id inexistente no banco"
    titulo_banco = (project.titulo or "").strip()
    if titulo_banco.casefold() != titulo_planilha.casefold():
        return f'título divergente: banco="{titulo_banco}" planilha="{titulo_planilha}"'
    return None


def excluir_projetos(apply: bool, caminho_csv: Path) -> dict:
    from models import Project, Task, db

    lista = carregar_lista_exclusao(caminho_csv)
    resumo = {"planilha": len(lista), "excluidos": 0, "tarefas_excluidas": 0, "pulados": []}
    pendentes_no_lote = 0

    for project_id, titulo_planilha in lista:
        project = db.session.get(Project, project_id)
        motivo = conferir_projeto(project, titulo_planilha)
        if motivo:
            resumo["pulados"].append((project_id, motivo))
            print(f"  PULADO #{project_id}: {motivo}")
            continue

        tarefas = Task.query.filter_by(project_id=project_id).all()
        print(
            f"  excluir #{project_id} \"{project.titulo[:60]}\" · "
            f"etapas={len(project.etapas)} tarefas={len(tarefas)} historico={len(project.history)}"
        )
        resumo["excluidos"] += 1
        resumo["tarefas_excluidas"] += len(tarefas)

        if not apply:
            continue
        for tarefa in tarefas:
            db.session.delete(tarefa)
        db.session.delete(project)
        pendentes_no_lote += 1
        if pendentes_no_lote >= TAMANHO_LOTE:
            db.session.commit()
            pendentes_no_lote = 0

    if apply and pendentes_no_lote:
        db.session.commit()
    return resumo


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="grava (default: dry-run)")
    parser.add_argument("--csv", type=Path, default=CSV_PADRAO, help="lista id,titulo")
    args = parser.parse_args()

    from app import app

    with app.app_context():
        resumo = excluir_projetos(apply=args.apply, caminho_csv=args.csv)

    modo = "APLICADO" if args.apply else "DRY-RUN (nada gravado; use --apply)"
    print(f"\n{modo}")
    print(f"  na planilha: {resumo['planilha']}")
    print(f"  excluídos:   {resumo['excluidos']} (com {resumo['tarefas_excluidas']} tarefas)")
    print(f"  pulados:     {len(resumo['pulados'])}")
    if resumo["pulados"]:
        print("\nPulados exigem decisão humana — nada deles foi tocado:")
        for project_id, motivo in resumo["pulados"]:
            print(f"  #{project_id}: {motivo}")


if __name__ == "__main__":
    main()
