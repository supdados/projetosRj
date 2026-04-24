"""Backfill de OrgaoUnidade a partir de dados legados de area.

Migra dados do modelo flat (tabelas `area_catalog`/`user_areas` e coluna
`project.area_responsavel`) para o modelo hierarquico (`OrgaoUnidade` +
`user_orgao` + `project.orgao_id`). Usa SQL raw porque os modelos ORM
`UserArea`/`AreaCatalog` e a coluna `Project.area_responsavel` ja foram
removidos do codigo fonte.

Deve rodar **antes** da migration `c5f8a1b2d9e0` (drop legacy). Sequencia
em homologacao e producao:

1. Deploy do codigo que removeu os modelos de area (este deploy).
2. Aplicar migration `b2c4d6e8f0a1` se ainda nao aplicada (adiciona
   orgao_unidade, project.orgao_id, user_orgao).
3. Rodar `run_backfill_orgaos()` (este script).
4. Aplicar migration `c5f8a1b2d9e0` (drop area_responsavel, user_areas,
   area_catalog).

Idempotente: rodar 2x nao duplica linhas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from flask import current_app
from sqlalchemy import func, inspect, text

from models import OrgaoUnidade, db

SETD_SIGLA = "SETD"
SETD_NOME = "Secretaria de Estado de Transformacao Digital"
SETD_TIPO = "Secretaria"
DEFAULT_CHILD_TIPO = "Subsecretaria"


@dataclass
class BackfillReport:
    setd_created: bool = False
    orgaos_created: list[str] = field(default_factory=list)
    orgaos_reused: list[str] = field(default_factory=list)
    projects_linked: int = 0
    projects_unmatched: list[str] = field(default_factory=list)
    user_orgaos_linked: int = 0
    user_areas_unmatched: list[str] = field(default_factory=list)

    def log(self) -> None:
        logger = current_app.logger
        logger.info("[backfill_orgaos] SETD criada: %s", self.setd_created)
        logger.info(
            "[backfill_orgaos] orgaos criados: %d %s",
            len(self.orgaos_created),
            self.orgaos_created,
        )
        logger.info(
            "[backfill_orgaos] orgaos reusados: %d %s",
            len(self.orgaos_reused),
            self.orgaos_reused,
        )
        logger.info(
            "[backfill_orgaos] projects com orgao_id setado: %d", self.projects_linked
        )
        if self.projects_unmatched:
            logger.warning(
                "[backfill_orgaos] project.area_responsavel sem match: %s",
                self.projects_unmatched,
            )
        logger.info(
            "[backfill_orgaos] vinculos user_orgao criados: %d", self.user_orgaos_linked
        )
        if self.user_areas_unmatched:
            logger.warning(
                "[backfill_orgaos] user_areas.area sem match: %s",
                self.user_areas_unmatched,
            )


def _normalize_sigla(raw: Optional[str]) -> str:
    if raw is None:
        return ""
    return " ".join(str(raw).strip().split())


def _ensure_setd(report: BackfillReport) -> OrgaoUnidade:
    setd = OrgaoUnidade.query.filter(
        func.lower(OrgaoUnidade.sigla) == SETD_SIGLA.lower()
    ).first()
    if setd is not None:
        return setd

    rj_root = (
        OrgaoUnidade.query.filter(func.lower(OrgaoUnidade.tipo) == "estado")
        .filter(OrgaoUnidade.pai_id.is_(None))
        .first()
    )

    setd = OrgaoUnidade(
        sigla=SETD_SIGLA,
        nome=SETD_NOME,
        tipo=SETD_TIPO,
        pai_id=rj_root.id if rj_root else None,
        ordem=0,
        ativo=True,
    )
    db.session.add(setd)
    db.session.flush()
    report.setd_created = True
    return setd


def _find_orgao_by_sigla(sigla: str) -> Optional[OrgaoUnidade]:
    if not sigla:
        return None
    return OrgaoUnidade.query.filter(
        func.lower(OrgaoUnidade.sigla) == sigla.lower()
    ).first()


def _collect_legacy_area_names(tables: set[str]) -> list[str]:
    candidates: list[str] = []

    if "area_catalog" in tables:
        rows = db.session.execute(text("SELECT name FROM area_catalog")).all()
        candidates.extend(row[0] for row in rows)
    if "user_areas" in tables:
        rows = db.session.execute(
            text("SELECT DISTINCT area FROM user_areas WHERE area IS NOT NULL")
        ).all()
        candidates.extend(row[0] for row in rows)
    if "project" in tables:
        project_columns = {
            col["name"] for col in inspect(db.engine).get_columns("project")
        }
        if "area_responsavel" in project_columns:
            rows = db.session.execute(
                text(
                    "SELECT DISTINCT area_responsavel FROM project "
                    "WHERE area_responsavel IS NOT NULL"
                )
            ).all()
            candidates.extend(row[0] for row in rows)

    seen: set[str] = set()
    unique: list[str] = []
    for raw in candidates:
        normalized = _normalize_sigla(raw)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def _ensure_area_orgaos(
    area_names: list[str],
    setd: OrgaoUnidade,
    report: BackfillReport,
) -> dict[str, int]:
    sigla_to_id: dict[str, int] = {}
    next_ordem = _next_ordem_under(setd.id)

    for sigla in area_names:
        existing = _find_orgao_by_sigla(sigla)
        if existing is not None:
            sigla_to_id[sigla.lower()] = existing.id
            report.orgaos_reused.append(sigla)
            continue

        novo = OrgaoUnidade(
            sigla=sigla,
            nome=sigla,
            tipo=DEFAULT_CHILD_TIPO,
            pai_id=setd.id,
            ordem=next_ordem,
            ativo=True,
        )
        db.session.add(novo)
        db.session.flush()
        sigla_to_id[sigla.lower()] = novo.id
        report.orgaos_created.append(sigla)
        next_ordem += 1

    return sigla_to_id


def _next_ordem_under(pai_id: Optional[int]) -> int:
    current_max = (
        db.session.query(func.max(OrgaoUnidade.ordem))
        .filter(OrgaoUnidade.pai_id == pai_id)
        .scalar()
    )
    return (current_max + 1) if current_max is not None else 0


def _backfill_projects(
    sigla_to_id: dict[str, int],
    report: BackfillReport,
    tables: set[str],
) -> None:
    project_columns = {col["name"] for col in inspect(db.engine).get_columns("project")}
    if "area_responsavel" not in project_columns or "orgao_id" not in project_columns:
        return

    rows = db.session.execute(
        text(
            "SELECT id, area_responsavel FROM project "
            "WHERE orgao_id IS NULL AND area_responsavel IS NOT NULL"
        )
    ).all()
    for project_id, area_responsavel in rows:
        sigla = _normalize_sigla(area_responsavel)
        orgao_id = sigla_to_id.get(sigla.lower())
        if orgao_id is None:
            report.projects_unmatched.append(sigla)
            continue
        db.session.execute(
            text("UPDATE project SET orgao_id = :orgao_id WHERE id = :project_id"),
            {"orgao_id": orgao_id, "project_id": project_id},
        )
        report.projects_linked += 1


def _backfill_user_orgaos(
    sigla_to_id: dict[str, int],
    report: BackfillReport,
    tables: set[str],
) -> None:
    if "user_areas" not in tables or "user_orgao" not in tables:
        return

    existing_pairs_rows = db.session.execute(
        text("SELECT user_id, orgao_id FROM user_orgao")
    ).all()
    existing_pairs = {(row[0], row[1]) for row in existing_pairs_rows}

    rows = db.session.execute(
        text("SELECT user_id, area FROM user_areas WHERE area IS NOT NULL")
    ).all()
    for user_id, area in rows:
        sigla = _normalize_sigla(area)
        orgao_id = sigla_to_id.get(sigla.lower())
        if orgao_id is None:
            report.user_areas_unmatched.append(sigla)
            continue
        key = (user_id, orgao_id)
        if key in existing_pairs:
            continue
        db.session.execute(
            text(
                "INSERT INTO user_orgao (user_id, orgao_id) VALUES (:user_id, :orgao_id)"
            ),
            {"user_id": user_id, "orgao_id": orgao_id},
        )
        existing_pairs.add(key)
        report.user_orgaos_linked += 1


def run_backfill_orgaos(dry_run: bool = False) -> BackfillReport:
    """Executa backfill idempotente. Requer app_context ativo.

    Retorna BackfillReport com contagens. Se tabelas legadas nao existirem
    mais (ex: migration c5f8a1b2d9e0 ja aplicada), retorna report vazio.
    """
    report = BackfillReport()
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    if "orgao_unidade" not in tables:
        current_app.logger.warning(
            "[backfill_orgaos] tabela orgao_unidade nao existe; rodar migration b2c4d6e8f0a1 primeiro."
        )
        return report

    setd = _ensure_setd(report)
    area_names = _collect_legacy_area_names(tables)
    sigla_to_id = _ensure_area_orgaos(area_names, setd, report)
    sigla_to_id.setdefault(SETD_SIGLA.lower(), setd.id)

    _backfill_projects(sigla_to_id, report, tables)
    _backfill_user_orgaos(sigla_to_id, report, tables)

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()

    report.log()
    return report
