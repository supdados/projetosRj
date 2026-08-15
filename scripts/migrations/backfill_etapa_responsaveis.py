#!/usr/bin/env python3
"""Backfill one-shot: espelho ``Etapa.responsavel`` -> N:N ``EtapaResponsavel``.

Sprint 3.1: a N:N é a face canônica e o espelho vira derivado com um único
escritor (services/etapa_responsaveis.py). Etapas antigas só têm o texto — este
passo converte cada uma preservando TODOS os rótulos: diferente do caminho
canônico da API (que colapsa rótulos sem área em "Outras"), aqui cada rótulo
não casado vira linha ``area_id=None`` com o texto original. A barra ("/") só é
tratada como separador quando TODAS as partes casam com sigla viva — senão faz
parte do nome (ex.: "contrato Nº 004/2024"). Idempotente: etapas já com linhas
N:N são puladas.

Uso:
    python3 scripts/migrations/backfill_etapa_responsaveis.py            # dry-run
    python3 scripts/migrations/backfill_etapa_responsaveis.py --apply   # grava
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Backfill de dados puro: garante que importar o app não rode init/migração de schema.
os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")

from sqlalchemy import func

from app import app, db
from models import Etapa, EtapaResponsavel, OrgaoUnidade

_SEPARADORES_FORTES = re.compile(r"[,;\n]+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Converte o espelho Etapa.responsavel em linhas EtapaResponsavel."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Grava as alterações (default é dry-run, que só relata contagens).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Só relata contagens, sem gravar (comportamento default).",
    )
    return parser.parse_args()


def _etapas_pendentes() -> list[Etapa]:
    """Etapas com espelho preenchido e nenhuma linha N:N (alvo do backfill)."""
    return (
        Etapa.query.filter(
            Etapa.responsavel.isnot(None),
            func.trim(Etapa.responsavel) != "",
            ~Etapa.responsaveis.any(),
        )
        .order_by(Etapa.id.asc())
        .all()
    )


def _siglas_vivas() -> dict[str, int]:
    """Mapa sigla casefold -> id de OrgaoUnidade (menor id em caso de empate)."""
    mapa: dict[str, int] = {}
    for unidade in OrgaoUnidade.query.order_by(OrgaoUnidade.id.asc()).all():
        mapa.setdefault((unidade.sigla or "").casefold(), unidade.id)
    return mapa


def _labels_do_espelho(raw: str, siglas: dict[str, int]) -> list[str]:
    """Rótulos individuais do espelho, sem perder nomes que contêm "/"."""
    labels: list[str] = []
    vistos: set[str] = set()
    for parte in _SEPARADORES_FORTES.split(raw):
        nome = " ".join(parte.split())
        if not nome:
            continue
        subpartes = [" ".join(s.split()) for s in nome.split("/")]
        if len(subpartes) > 1 and all(
            s and s.casefold() in siglas for s in subpartes
        ):
            candidatos = subpartes
        else:
            candidatos = [nome]
        for candidato in candidatos:
            if candidato.casefold() in vistos:
                continue
            vistos.add(candidato.casefold())
            labels.append(candidato)
    return labels


def _montar_linhas(
    labels: list[str], siglas: dict[str, int]
) -> list[EtapaResponsavel]:
    linhas: list[EtapaResponsavel] = []
    for ordem, label in enumerate(labels):
        area_id = siglas.get(label.casefold())
        linhas.append(EtapaResponsavel(area_id=area_id, label=label, ordem=ordem))
    return linhas


def _converter_etapas(etapas: list[Etapa], *, aplicar: bool) -> dict[str, object]:
    siglas = _siglas_vivas()
    stats: dict[str, object] = {
        "convertidas": 0,
        "linhas": 0,
        "com_area": 0,
        "sem_area": 0,
        "multi_sem_area": [],
    }
    for etapa in etapas:
        labels = _labels_do_espelho(etapa.responsavel, siglas)
        if not labels:
            continue
        linhas = _montar_linhas(labels, siglas)
        sem_area = [linha.label for linha in linhas if linha.area_id is None]
        stats["convertidas"] += 1
        stats["linhas"] += len(linhas)
        stats["com_area"] += len(linhas) - len(sem_area)
        stats["sem_area"] += len(sem_area)
        if len(sem_area) > 1:
            stats["multi_sem_area"].append((etapa.id, sem_area))
        if aplicar:
            etapa.responsaveis = linhas
            etapa.responsavel = ", ".join(labels)[:100]
    return stats


def _relatar(pendentes: int, stats: dict[str, object]) -> None:
    print(f"Etapas com espelho preenchido e N:N vazia: {pendentes}")
    print(f"Etapas convertíveis: {stats['convertidas']}")
    print(f"Linhas EtapaResponsavel previstas/criadas: {stats['linhas']}")
    print(f"  - rótulos casados com área viva: {stats['com_area']}")
    print(f"  - rótulos sem área (preservados com area_id nulo): {stats['sem_area']}")
    multi = stats["multi_sem_area"]
    if multi:
        print(f"Etapas com 2+ rótulos sem área (todos preservados): {len(multi)}")
        for etapa_id, labels in multi:
            print(f"  - etapa {etapa_id}: {labels}")


def main() -> int:
    args = parse_args()
    if args.apply and args.dry_run:
        print("Use --apply OU --dry-run, não os dois.")
        return 2
    with app.app_context():
        print(f"Banco: {app.config['SQLALCHEMY_DATABASE_URI']}")
        etapas = _etapas_pendentes()
        stats = _converter_etapas(etapas, aplicar=args.apply)
        _relatar(len(etapas), stats)
        if not args.apply:
            print("\nDry-run: nada gravado. Use --apply para gravar.")
            return 0
        db.session.commit()
        print(f"\nGravado: {stats['convertidas']} etapa(s) backfillada(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
