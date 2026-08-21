#!/usr/bin/env python3
"""
Popula a hierarquia inicial de órgãos do RJ no banco de dados.

Idempotente: identifica unidades existentes pela combinação (sigla, pai_sigla).

Uso:
    python3 scripts/catalog/seed_orgaos_rj.py
    python3 scripts/catalog/seed_orgaos_rj.py --dry-run
"""

import argparse
from pathlib import Path
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Roda DURANTE a migração, contra banco fora do head: importar o app não pode
# disparar verify_schema_version() e matar o script antes do primeiro trabalho.
os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")

from app import app, db
from models import OrgaoUnidade

# (sigla, nome, tipo, pai_sigla|None, ordem)
HIERARQUIA = [
    ("RJ", "Estado do Rio de Janeiro", "Estado", None, 0),
    # SETD
    ("SETD", "Secretaria de Estado de Transformação Digital", "Secretaria", "RJ", 1),
    ("SUPDADOS", "Subsecretaria de Dados e Inovação", "Subsecretaria", "SETD", 0),
    ("SUPINFRA", "Subsecretaria de Infraestrutura Digital", "Subsecretaria", "SETD", 1),
    ("SUPSERV", "Subsecretaria de Serviços Digitais", "Subsecretaria", "SETD", 2),
    (
        "PRODERJ",
        "Centro de Tecnologia de Informação e Comunicação",
        "Autarquia",
        "SETD",
        3,
    ),
    ("CDA", "Coordenação de Dados Abertos", "Coordenação", "SUPDADOS", 0),
    ("CCD", "Coordenação de Ciência de Dados", "Coordenação", "SUPDADOS", 1),
    ("NIA", "Núcleo de Inteligência Artificial", "Núcleo", "SUPDADOS", 2),
    ("COR", "Coordenação de Redes", "Coordenação", "SUPINFRA", 0),
    ("COC", "Coordenação de Cloud", "Coordenação", "SUPINFRA", 1),
    ("COA", "Coordenação de Atendimento ao Cidadão", "Coordenação", "SUPSERV", 0),
    ("COCHAT", "Coordenação de Chatbots", "Coordenação", "SUPSERV", 1),
    # SEFAZ
    ("SEFAZ", "Secretaria de Estado de Fazenda", "Secretaria", "RJ", 2),
    ("SUBREC", "Subsecretaria de Receita", "Subsecretaria", "SEFAZ", 0),
    ("SUBTES", "Subsecretaria de Tesouro", "Subsecretaria", "SEFAZ", 1),
    # SES
    ("SES", "Secretaria de Estado de Saúde", "Secretaria", "RJ", 3),
    ("SUBAP", "Subsecretaria de Atenção Primária", "Subsecretaria", "SES", 0),
    ("SUBVIS", "Subsecretaria de Vigilância em Saúde", "Subsecretaria", "SES", 1),
    ("FSAÚDE", "Fundação Saúde", "Fundação", "SES", 2),
    # SEEDUC
    ("SEEDUC", "Secretaria de Estado de Educação", "Secretaria", "RJ", 4),
    ("SUBPED", "Subsecretaria Pedagógica", "Subsecretaria", "SEEDUC", 0),
    (
        "SUBINFR",
        "Subsecretaria de Infraestrutura Escolar",
        "Subsecretaria",
        "SEEDUC",
        1,
    ),
    # SEPOL
    ("SEPOL", "Secretaria de Estado de Polícia Civil", "Secretaria", "RJ", 5),
    # SEPLAG
    ("SEPLAG", "Secretaria de Estado de Planejamento e Gestão", "Secretaria", "RJ", 6),
    ("SUBGP", "Subsecretaria de Gestão de Pessoas", "Subsecretaria", "SEPLAG", 0),
    # SECID
    ("SECID", "Secretaria de Estado das Cidades", "Secretaria", "RJ", 7),
]


def _masked_db_uri(uri):
    if "://" not in uri or "@" not in uri:
        return uri
    scheme, rest = uri.split("://", 1)
    if ":" in rest and "@" in rest:
        creds, tail = rest.split("@", 1)
        if ":" in creds:
            user, _ = creds.split(":", 1)
            return f"{scheme}://{user}:***@{tail}"
    return uri


def parse_args():
    parser = argparse.ArgumentParser(
        description="Popula a hierarquia inicial de órgãos do RJ.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa sem persistir alterações.",
    )
    return parser.parse_args()


def find_existing(sigla, pai_id):
    return OrgaoUnidade.query.filter_by(sigla=sigla, pai_id=pai_id).first()


def main():
    args = parse_args()

    with app.app_context():
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        print("=" * 72)
        print("SEED DE HIERARQUIA DE ÓRGÃOS — ESTADO DO RJ")
        print("=" * 72)
        print(f"Banco alvo: {_masked_db_uri(db_uri)}")
        print(f"Modo dry-run: {'SIM' if args.dry_run else 'NAO'}")
        print()

        criadas = 0
        atualizadas = 0
        ignoradas = 0
        siglas_para_id = {}

        try:
            for sigla, nome, tipo, pai_sigla, ordem in HIERARQUIA:
                pai_id = siglas_para_id.get(pai_sigla) if pai_sigla else None
                if pai_sigla and pai_id is None:
                    pai_existente = OrgaoUnidade.query.filter_by(
                        sigla=pai_sigla
                    ).first()
                    if pai_existente is None:
                        print(f"[SKIP] {sigla}: pai '{pai_sigla}' não encontrado.")
                        continue
                    pai_id = pai_existente.id

                existente = find_existing(sigla, pai_id)
                if existente is not None:
                    if (
                        existente.nome != nome
                        or existente.tipo != tipo
                        or existente.ordem != ordem
                    ):
                        existente.nome = nome
                        existente.tipo = tipo
                        existente.ordem = ordem
                        atualizadas += 1
                        print(f"[UPD] {sigla}")
                    else:
                        ignoradas += 1
                    siglas_para_id[sigla] = existente.id
                    continue

                novo = OrgaoUnidade(
                    sigla=sigla,
                    nome=nome,
                    tipo=tipo,
                    pai_id=pai_id,
                    ordem=ordem,
                    ativo=True,
                )
                db.session.add(novo)
                db.session.flush()
                siglas_para_id[sigla] = novo.id
                criadas += 1
                print(f"[ADD] {sigla} — {nome}")

            if args.dry_run:
                db.session.rollback()
                print("\ndry-run: rollback executado")
            else:
                db.session.commit()
                print("\ncommit: alterações persistidas")

            print(f"\nResumo:")
            print(f"  - criadas:    {criadas}")
            print(f"  - atualizadas:{atualizadas}")
            print(f"  - inalteradas:{ignoradas}")
            print(f"  - total no banco: {OrgaoUnidade.query.count()}")
            return 0

        except Exception as exc:
            db.session.rollback()
            print(f"\nERRO: {exc}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
