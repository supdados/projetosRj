"""Move o EPERJ de SUPIM para SUBDGD (demanda VPT ago/2026).

O SIORG ainda mostra EPERJ sob SUPIM; a mudança oficial lá virá depois. O
ProjetosRJ precisa refletir a estrutura nova desde já — quando o SIORG mudar,
o sync encontrará o pai já correto. Valida a movimentação (ciclo, tipo,
profundidade) e reconstrói a ``orgao_closure``: sem o rebuild o escopo de
permissão continua respondendo pela árvore antiga.

Dry-run por padrão; ``--apply`` grava.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SIGLA_UNIDADE = "EPERJ"
SIGLA_PAI_ATUAL = "SUPIM"
SIGLA_PAI_NOVO = "SUBDGD"


def _buscar_por_sigla(sigla: str):
    from models import OrgaoUnidade

    unidades = OrgaoUnidade.query.filter_by(sigla=sigla).order_by(OrgaoUnidade.id).all()
    if len(unidades) != 1:
        raise SystemExit(
            f"Esperava exatamente 1 unidade com sigla {sigla}, achei {len(unidades)} — abortando."
        )
    return unidades[0]


def mover_eperj(apply: bool) -> None:
    from models import db
    from services.orgao_tree import rebuild_orgao_closure, validate_orgao_move

    eperj = _buscar_por_sigla(SIGLA_UNIDADE)
    pai_atual = _buscar_por_sigla(SIGLA_PAI_ATUAL)
    pai_novo = _buscar_por_sigla(SIGLA_PAI_NOVO)

    if eperj.pai_id == pai_novo.id:
        print(f"{SIGLA_UNIDADE} já está sob {SIGLA_PAI_NOVO} — nada a fazer.")
        return
    if eperj.pai_id != pai_atual.id:
        raise SystemExit(
            f"{SIGLA_UNIDADE} tem pai_id={eperj.pai_id}, esperava {pai_atual.id} "
            f"({SIGLA_PAI_ATUAL}) — estrutura diferente da prevista, abortando."
        )

    erro = validate_orgao_move(eperj, pai_novo.id)
    if erro:
        raise SystemExit(f"Movimentação inválida: {erro}")

    print(f"{SIGLA_UNIDADE} (id {eperj.id}): {SIGLA_PAI_ATUAL} (id {pai_atual.id}) "
          f"-> {SIGLA_PAI_NOVO} (id {pai_novo.id})")
    if not apply:
        print("DRY-RUN: nada gravado. Use --apply para gravar.")
        return

    eperj.pai_id = pai_novo.id
    db.session.flush()
    rebuild_orgao_closure()
    db.session.commit()
    print("Gravado e closure reconstruída.")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="grava (default: dry-run)")
    args = parser.parse_args()

    from app import app

    with app.app_context():
        mover_eperj(apply=args.apply)


if __name__ == "__main__":
    main()
