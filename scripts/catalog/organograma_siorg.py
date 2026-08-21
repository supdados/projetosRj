#!/usr/bin/env python3
"""Importa o organograma real do SIORG-RJ para `orgao_tipo`/`orgao_unidade`.

A identidade de uma unidade é o `codigo_externo` (o `codigo` do SIORG), nunca a
sigla: CHEGAB, ASSJUR, ASSCOM, CORREG e OUVI aparecem duas vezes na estrutura
(uma na SETD, outra no PRODERJ).

Uso:
    python3 scripts/catalog/organograma_siorg.py            # dry-run
    python3 scripts/catalog/organograma_siorg.py --apply
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import OrgaoTipo, OrgaoUnidade, db
from models.orgao import slugify_orgao_tipo
from services.orgao_tree import rebuild_orgao_closure

CSV_PADRAO: Path = PROJECT_ROOT / "catalogs" / "estrutura_setd_proderj.csv"

# Tipos do SIORG não existem em DEFAULT_ORGAO_TIPOS; nivel/permite_raiz aqui
# replicam o organograma já validado em instance/projetosrj-v5.0.db.
PERFIL_TIPO_SIORG: dict[str, tuple[int, bool]] = {
    "ENTE": (0, True),
    "ORGAO": (0, True),
    "ENTIDADE": (99, False),
    "UA": (99, False),
    "UC": (99, False),
}
NIVEL_TIPO_DESCONHECIDO = 99


@dataclass(frozen=True)
class UnidadeSiorg:
    """Uma linha da estrutura do SIORG, já tipada."""

    codigo: int
    codigo_pai: int | None
    nome: str
    sigla: str
    tipo: str
    ordem: int


# ECENTRAL existe no area_catalog legado mas não no SIORG; fica sob o Gabinete
# do Secretário (código 3), como no organograma de dev.
UNIDADES_COMPLEMENTARES: tuple[UnidadeSiorg, ...] = (
    UnidadeSiorg(
        codigo=99,
        codigo_pai=3,
        nome="Encarregado Central",
        sigla="ECENTRAL",
        tipo="UA",
        ordem=0,
    ),
    # VPG idem: área legada distinta das quatro VPs do SIORG; fica sob o PRODERJ (34).
    UnidadeSiorg(
        codigo=100,
        codigo_pai=34,
        nome="Vice-Presidência Geral",
        sigla="VPG",
        tipo="UA",
        ordem=0,
    ),
)

# Sigla do `area_catalog` legado -> `codigo_externo` do SIORG. Mapa fechado:
# derivado do organograma de dev, não recalcular.
ALIAS_SIGLA_LEGADA: dict[str, int] = {
    "SETD": 2,
    "PRODERJ": 34,
    "SUBEDD": 20,
    "SUBDGD": 26,
    "SUBEXE": 11,
    "SUPDADOS": 24,
    "SUPEST": 22,
    "SUPIM": 28,
    "SUPPAE": 31,
    "EPERJ": 30,
    "ASSESP": 5,
    "ASSTEC": 27,
    "ECENTRAL": 99,
    "Auditoria": 8,
    "Ouvidoria": 10,
    "CHEGAB": 4,
    "DIRGN": 96,
    "DIRIT": 71,
    "DIRPE": 89,
    "DIRPL": 47,
    "DIRSI": 62,
    "DIRSS": 65,
    "EGPE": 94,
    "GERGD": 98,
    "GERII": 70,
    "GERRC": 97,
    "GAR": 67,
    "GFS": 69,
    "GSS": 66,
    "GERS": 68,
    "GDB": 76,
    "RH-PRODERJ": 48,
    "VPD": 77,
    "VPE": 87,
    "VPT": 58,
    "VPG": 100,
}

# Siglas legadas que representam duas unidades ao mesmo tempo, não uma unidade.
VINCULOS_DUPLOS: dict[str, tuple[int, int]] = {
    "GAR/GFS": (67, 69),
    "GSS/GFS": (66, 69),
}


@dataclass
class RelatorioEstrutura:
    """Resultado de `importar_estrutura`, legível em dry-run e em apply."""

    dry_run: bool
    total_lidas: int
    tipos_criados: list[str]
    criadas: list[str]
    atualizadas: list[str]
    inalteradas: int
    pais_religados: int
    arvore: list[str]

    def resumo(self) -> str:
        modo = "dry-run" if self.dry_run else "aplicado"
        return (
            f"[{modo}] {self.total_lidas} lidas · {len(self.criadas)} criadas · "
            f"{len(self.atualizadas)} atualizadas · {self.inalteradas} inalteradas · "
            f"{self.pais_religados} pais religados · "
            f"{len(self.tipos_criados)} tipos criados"
        )


def ler_estrutura(csv_path: Path = CSV_PADRAO) -> list[UnidadeSiorg]:
    """Lê o CSV do SIORG e acrescenta as unidades complementares do legado.

    Exemplo: `ler_estrutura()` devolve 100 unidades (98 do SIORG + ECENTRAL + VPG).
    """
    with csv_path.open(encoding="utf-8", newline="") as arquivo:
        unidades = [_linha_para_unidade(linha) for linha in csv.DictReader(arquivo)]
    unidades.extend(UNIDADES_COMPLEMENTARES)
    _validar_codigos_unicos(unidades)
    return unidades


def _linha_para_unidade(linha: dict[str, str]) -> UnidadeSiorg:
    codigo_pai = (linha.get("codigo_pai") or "").strip()
    return UnidadeSiorg(
        codigo=int(linha["codigo"]),
        codigo_pai=int(codigo_pai) if codigo_pai else None,
        nome=(linha["nome"] or "").strip(),
        sigla=(linha["sigla"] or "").strip(),
        tipo=(linha["tipo"] or "").strip().upper(),
        ordem=int((linha.get("ordenacao") or "0").strip() or 0),
    )


def _validar_codigos_unicos(unidades: list[UnidadeSiorg]) -> None:
    vistos: set[int] = set()
    for unidade in unidades:
        if unidade.codigo in vistos:
            raise ValueError(
                f"código SIORG duplicado: {unidade.codigo} ({unidade.sigla}); "
                "cada unidade precisa de um código único"
            )
        vistos.add(unidade.codigo)


def _garantir_tipos(nomes: set[str]) -> tuple[dict[str, OrgaoTipo], list[str]]:
    """Cria os `OrgaoTipo` do SIORG que ainda não existem, preservando os atuais."""
    tipos = {tipo.nome: tipo for tipo in OrgaoTipo.query.all()}
    criados: list[str] = []
    for nome in sorted(nomes):
        if nome in tipos:
            continue
        tipos[nome] = _novo_tipo(nome)
        criados.append(nome)
    db.session.flush()
    return tipos, criados


def _novo_tipo(nome: str) -> OrgaoTipo:
    nivel, permite_raiz = PERFIL_TIPO_SIORG.get(nome, (NIVEL_TIPO_DESCONHECIDO, False))
    tipo = OrgaoTipo(
        nome=nome,
        slug=slugify_orgao_tipo(nome),
        nivel=nivel,
        ativo=True,
        is_system=False,
        permite_raiz=permite_raiz,
    )
    db.session.add(tipo)
    return tipo


def _indexar_por_codigo() -> dict[int, OrgaoUnidade]:
    linhas = OrgaoUnidade.query.filter(OrgaoUnidade.codigo_externo.isnot(None)).all()
    return {
        int(linha.codigo_externo): linha
        for linha in linhas
        if str(linha.codigo_externo).strip().isdigit()
    }


def resolver_orgao_id_por_codigo() -> dict[int, int]:
    """Mapa `codigo_externo` do SIORG -> `orgao_unidade.id` gravado no banco.

    Exemplo: `resolver_orgao_id_por_codigo()[ALIAS_SIGLA_LEGADA["CHEGAB"]]` dá o
    id da CHEGAB da SETD (código 4), não a homônima do PRODERJ (código 36).
    """
    return {codigo: linha.id for codigo, linha in _indexar_por_codigo().items()}


def _aplicar_campos(
    linha: OrgaoUnidade, unidade: UnidadeSiorg, tipo: OrgaoTipo
) -> bool:
    novos: dict[str, object] = {
        "nome": unidade.nome,
        "sigla": unidade.sigla,
        "tipo": unidade.tipo,
        "tipo_id": tipo.id,
        "ordem": unidade.ordem,
    }
    mudou = any(getattr(linha, campo) != valor for campo, valor in novos.items())
    for campo, valor in novos.items():
        setattr(linha, campo, valor)
    return mudou


def _criar_unidade(unidade: UnidadeSiorg, tipo: OrgaoTipo) -> OrgaoUnidade:
    linha = OrgaoUnidade(codigo_externo=str(unidade.codigo), ativo=True)
    _aplicar_campos(linha, unidade, tipo)
    db.session.add(linha)
    return linha


def _upsert_unidade(
    unidade: UnidadeSiorg, tipo: OrgaoTipo, existentes: dict[int, OrgaoUnidade]
) -> str:
    alvo = existentes.get(unidade.codigo)
    if alvo is None:
        existentes[unidade.codigo] = _criar_unidade(unidade, tipo)
        return "criada"
    return "atualizada" if _aplicar_campos(alvo, unidade, tipo) else "inalterada"


def _resolver_pai_id(
    unidade: UnidadeSiorg, existentes: dict[int, OrgaoUnidade]
) -> int | None:
    if unidade.codigo_pai is None:
        return None
    pai = existentes.get(unidade.codigo_pai)
    if pai is None:
        raise ValueError(
            f"unidade {unidade.codigo} ({unidade.sigla}) aponta para codigo_pai "
            f"{unidade.codigo_pai}, que não existe na estrutura importada"
        )
    return pai.id


def _ligar_pais(
    unidades: list[UnidadeSiorg], existentes: dict[int, OrgaoUnidade]
) -> int:
    """Segunda passada: só aqui todos os ids existem para resolver `codigo_pai`."""
    religados = 0
    for unidade in unidades:
        pai_id = _resolver_pai_id(unidade, existentes)
        linha = existentes[unidade.codigo]
        if linha.pai_id == pai_id:
            continue
        linha.pai_id = pai_id
        religados += 1
    db.session.flush()
    return religados


def _linhas_arvore(
    filhos: dict[int | None, list[OrgaoUnidade]], pai_id: int | None, nivel: int
) -> Iterator[str]:
    for linha in filhos.get(pai_id, []):
        yield f"{'  ' * nivel}{linha.sigla} — {linha.nome} [{linha.tipo}]"
        yield from _linhas_arvore(filhos, linha.id, nivel + 1)


def renderizar_arvore(existentes: dict[int, OrgaoUnidade]) -> list[str]:
    """Árvore indentada das unidades importadas, ordenada por `ordem` e sigla."""
    filhos: dict[int | None, list[OrgaoUnidade]] = defaultdict(list)
    for linha in existentes.values():
        filhos[linha.pai_id].append(linha)
    for grupo in filhos.values():
        grupo.sort(key=lambda linha: (linha.ordem, linha.sigla))
    return list(_linhas_arvore(filhos, None, 0))


def importar_estrutura(
    csv_path: Path = CSV_PADRAO, *, dry_run: bool = True
) -> RelatorioEstrutura:
    """Faz upsert idempotente do organograma do SIORG e reconstrói a closure.

    Roda dentro de um app context. Em dry-run tudo é executado e revertido, de
    modo que o relatório é fiel ao que o `--apply` faria.

    Exemplo: `importar_estrutura(dry_run=False).resumo()` num banco vazio relata
    99 criadas e 5 tipos criados.
    """
    unidades = ler_estrutura(csv_path)
    tipos, tipos_criados = _garantir_tipos({unidade.tipo for unidade in unidades})
    existentes = _indexar_por_codigo()
    acoes: dict[str, list[str]] = {"criada": [], "atualizada": [], "inalterada": []}
    for unidade in unidades:
        acao = _upsert_unidade(unidade, tipos[unidade.tipo], existentes)
        acoes[acao].append(f"{unidade.codigo} {unidade.sigla}")
    db.session.flush()
    religados = _ligar_pais(unidades, existentes)
    rebuild_orgao_closure()
    relatorio = RelatorioEstrutura(
        dry_run=dry_run,
        total_lidas=len(unidades),
        tipos_criados=tipos_criados,
        criadas=acoes["criada"],
        atualizadas=acoes["atualizada"],
        inalteradas=len(acoes["inalterada"]),
        pais_religados=religados,
        arvore=renderizar_arvore(existentes),
    )
    _finalizar(dry_run)
    return relatorio


def _finalizar(dry_run: bool) -> None:
    if dry_run:
        db.session.rollback()
        return
    db.session.commit()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importa o organograma do SIORG-RJ (dry-run por padrão)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Grava as alterações (default é dry-run, que reverte tudo no fim).",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=CSV_PADRAO,
        help=f"Caminho do CSV da estrutura (default: {CSV_PADRAO}).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    # Este script roda justamente quando o banco ainda não está no head.
    os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")
    from app import app

    with app.app_context():
        print(f"Banco: {app.config['SQLALCHEMY_DATABASE_URI']}")
        relatorio = importar_estrutura(args.csv, dry_run=not args.apply)
    print("\n".join(relatorio.arvore))
    print(relatorio.resumo())
    if relatorio.dry_run:
        print("Dry-run: nada gravado. Use --apply para gravar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
