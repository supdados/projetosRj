#!/usr/bin/env python3
"""Vinculação inicial dos órgãos locais ao SIORG (one-shot, antes do 1º sync).

Carimba OrgaoUnidade.codigo_externo com o codigo do SIORG casando por sigla
local — só nesta migração; o sync posterior casa exclusivamente por codigo.
Preserva id e FKs (project.orgao_id, user_orgao, etapa_responsavel.area_id).

Uso:
    python3 scripts/migrations/vincular_siorg.py            # dry-run (default)
    python3 scripts/migrations/vincular_siorg.py --apply    # grava
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Roda DURANTE a migração, contra banco fora do head: importar o app não pode
# disparar verify_schema_version() e matar o script antes do primeiro trabalho.
os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")

from app import app, db
from models import EtapaResponsavel, OrgaoUnidade, Project, UserOrgao

# Validado contra siorg-rj/data/estrutura_setd_proderj.csv em 2026-07-14.
SIGLA_LOCAL_PARA_CODIGO_SIORG: dict[str, int] = {
    "SETD": 2,
    # Há duas CHEGAB no SIORG: 4 (SETD) e 36 (Presidência do PRODERJ). A legada é
    # a da SETD — seus 4 usuários têm user.orgao='SETD' e os 78 projetos são da SETD.
    "CHEGAB": 4,
    "SUPDADOS": 24,
    "SUBDGD": 26,
    "SUPEST": 22,
    "SUPIM": 28,
    "SUPPAE": 31,
    "PRODERJ": 34,
    "ASSESP": 5,
    "SUBEDD": 20,
    "EPERJ": 30,
    "DIRPE": 89,
    "DIRGN": 96,
    "GERGD": 98,
    "SUBEXE": 11,
    "ASSTEC": 27,
    "EGPE": 94,
    "AUDITORIA": 8,
    "OUVIDORIA": 10,  # OUVI da SETD, não a do PRODERJ (43)
    "VPT": 58,
    "VPD": 77,
    "VPE": 87,
}


@dataclass
class LinhaVinculo:
    orgao: OrgaoUnidade
    codigo_siorg: Optional[int]
    projetos: int
    vinculos_usuario: int
    etapas_responsavel: int

    @property
    def destino(self) -> str:
        if self.codigo_siorg is None:
            return "legado (sem vínculo SIORG)"
        return str(self.codigo_siorg)


def _masked_db_uri(uri: str) -> str:
    if "://" not in uri or "@" not in uri:
        return uri
    scheme, rest = uri.split("://", 1)
    if ":" in rest and "@" in rest:
        creds, tail = rest.split("@", 1)
        if ":" in creds:
            user, _ = creds.split(":", 1)
            return f"{scheme}://{user}:***@{tail}"
    return uri


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Carimba codigo_externo (SIORG) nos órgãos locais por sigla.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Grava as alterações (default é dry-run).",
    )
    return parser.parse_args()


def _codigo_siorg_para(orgao: OrgaoUnidade) -> Optional[int]:
    sigla = (orgao.sigla or "").strip().upper()
    return SIGLA_LOCAL_PARA_CODIGO_SIORG.get(sigla)


def _contar_referencias(orgao_id: int) -> tuple[int, int, int]:
    projetos = Project.query.filter(Project.orgao_id == orgao_id).count()
    usuarios = UserOrgao.query.filter(UserOrgao.orgao_id == orgao_id).count()
    etapas = EtapaResponsavel.query.filter(EtapaResponsavel.area_id == orgao_id).count()
    return projetos, usuarios, etapas


def _montar_linhas() -> list[LinhaVinculo]:
    linhas: list[LinhaVinculo] = []
    for orgao in OrgaoUnidade.query.order_by(OrgaoUnidade.sigla).all():
        projetos, usuarios, etapas = _contar_referencias(orgao.id)
        linhas.append(
            LinhaVinculo(orgao, _codigo_siorg_para(orgao), projetos, usuarios, etapas)
        )
    return linhas


def _validar_duplicidade(linhas: list[LinhaVinculo]) -> list[str]:
    erros: list[str] = []
    por_codigo: dict[int, list[str]] = {}
    for linha in linhas:
        if linha.codigo_siorg is not None:
            por_codigo.setdefault(linha.codigo_siorg, []).append(linha.orgao.sigla)
    for codigo, siglas in sorted(por_codigo.items()):
        if len(siglas) > 1:
            erros.append(
                f"codigo SIORG {codigo} casado por mais de um órgão local: "
                f"{siglas} (esperado: exatamente um órgão local por codigo)"
            )
    return erros


def _validar_codigo_existente(linhas: list[LinhaVinculo]) -> list[str]:
    erros: list[str] = []
    for linha in linhas:
        atual = (linha.orgao.codigo_externo or "").strip()
        if not atual or linha.codigo_siorg is None:
            continue
        if atual != str(linha.codigo_siorg):
            erros.append(
                f"órgão '{linha.orgao.sigla}' (id={linha.orgao.id}) já tem "
                f"codigo_externo='{atual}', diferente do destino "
                f"'{linha.codigo_siorg}' (esperado: vazio ou igual ao destino)"
            )
    return erros


def _imprimir_tabela(linhas: list[LinhaVinculo]) -> None:
    cab = f"{'SIGLA LOCAL':<16} {'CODIGO SIORG':<28} {'PROJETOS':>9} {'USUARIOS':>9} {'ETAPAS':>7}"
    print(cab)
    print("-" * len(cab))
    for linha in linhas:
        print(
            f"{linha.orgao.sigla:<16} {linha.destino:<28} "
            f"{linha.projetos:>9} {linha.vinculos_usuario:>9} {linha.etapas_responsavel:>7}"
        )


def _aplicar(linhas: list[LinhaVinculo]) -> int:
    gravados = 0
    for linha in linhas:
        if linha.codigo_siorg is None:
            continue
        if (linha.orgao.codigo_externo or "").strip():
            continue
        linha.orgao.codigo_externo = str(linha.codigo_siorg)
        gravados += 1
    db.session.commit()
    return gravados


def main() -> int:
    args = parse_args()
    with app.app_context():
        print("=" * 72)
        print("VINCULAÇÃO INICIAL SIORG → codigo_externo")
        print("=" * 72)
        print(
            f"Banco alvo: {_masked_db_uri(app.config.get('SQLALCHEMY_DATABASE_URI', ''))}"
        )
        print(f"Modo: {'APPLY' if args.apply else 'DRY-RUN'}")
        print()

        linhas = _montar_linhas()
        _imprimir_tabela(linhas)
        print()

        erros = _validar_duplicidade(linhas) + _validar_codigo_existente(linhas)
        if erros:
            for erro in erros:
                print(f"[ERRO] {erro}")
            print("\nNenhuma alteração gravada.")
            return 1

        sem_vinculo = [l.orgao.sigla for l in linhas if l.codigo_siorg is None]
        if sem_vinculo:
            print(f"Legado (sem vínculo SIORG): {', '.join(sem_vinculo)}")

        ja_vinculados = [
            l.orgao.sigla
            for l in linhas
            if l.codigo_siorg is not None and (l.orgao.codigo_externo or "").strip()
        ]
        if ja_vinculados:
            print(f"Já vinculados (sem mudança): {', '.join(ja_vinculados)}")

        if not args.apply:
            pendentes = sum(
                1
                for l in linhas
                if l.codigo_siorg is not None
                and not (l.orgao.codigo_externo or "").strip()
            )
            print(f"\nDry-run: {pendentes} órgão(s) seriam vinculados. Use --apply.")
            return 0

        gravados = _aplicar(linhas)
        print(f"\nGravados: {gravados} órgão(s) com codigo_externo preenchido.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
