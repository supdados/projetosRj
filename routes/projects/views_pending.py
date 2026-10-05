"""Consulta de Pendentes: resumo global em SQL e objetos apenas da página."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from flask import g
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from models import Etapa, EtapaResponsavel, Project, Task, db
from routes.orgao_scope import expand_orgao_filter_ids, get_user_orgao_options
from routes.shared import (
    get_goal_catalog_context,
    parse_db_integer_id,
    project_orgao_search_filter,
)
from services.authorization import apply_project_visibility
from services.etapa_positions import build_etapa_position_map

PERIOD_OPTIONS = [
    ("atrasados", "Projetos Atrasados"),
    ("7dias", "Próximos 7 Dias"),
    ("14dias", "Próximos 14 Dias"),
    ("21dias", "Próximos 21 Dias"),
]
PERIOD_LABELS = {"atrasados": "Atrasados", **dict(PERIOD_OPTIONS[1:])}
VISIBLE_BUCKETS = {
    "atrasados": ("atrasada",),
    "7dias": ("atrasada", "7dias"),
    "14dias": ("atrasada", "7dias", "14dias"),
    "21dias": ("atrasada", "7dias", "14dias", "21dias"),
}


def _base_project_ids(
    orgao_id: int | None, apenas_orgao: bool, priority: str, search: str
) -> Select:
    query = apply_project_visibility(
        select(Project.id).where(Project.status == "Vigente"), g.user
    )
    if orgao_id is not None:
        query = query.where(
            Project.orgao_id.in_(
                expand_orgao_filter_ids(orgao_id, incluir_descendentes=not apenas_orgao)
            )
        )
    if priority:
        query = query.where(Project.prioridade == priority)
    if search:
        pattern = f"%{search}%"
        criteria = [
            Project.titulo.ilike(pattern),
            project_orgao_search_filter(pattern),
            Project.abep_indicator.ilike(pattern),
        ]
        project_id = parse_db_integer_id(search)
        if project_id is not None:
            criteria.append(Project.id == project_id)
        query = query.where(or_(*criteria))
    return query


def _open_stage_conditions(project_ids: Select) -> tuple[ColumnElement[bool], ...]:
    return (
        Etapa.project_id.in_(project_ids),
        Etapa.done.is_(False),
        Etapa.entry_type != "google_meeting",
    )


def _responsavel_options(project_ids: Select) -> list[str]:
    rows = (
        db.session.query(EtapaResponsavel.label)
        .join(Etapa, Etapa.id == EtapaResponsavel.etapa_id)
        .filter(*_open_stage_conditions(project_ids))
        .distinct()
        .all()
    )
    unique: dict[str, str] = {}
    for (label,) in rows:
        name = " ".join((label or "").split())
        if name:
            unique.setdefault(name.casefold(), name)
    return sorted(unique.values(), key=str.casefold)


def _stage_projection(project_ids: Select, responsible: str, today: date) -> Subquery:
    bucket = case(
        (Etapa.data_fim.is_(None), "sem_data"),
        (Etapa.data_fim < today, "atrasada"),
        (Etapa.data_fim <= today + timedelta(days=7), "7dias"),
        (Etapa.data_fim <= today + timedelta(days=14), "14dias"),
        (Etapa.data_fim <= today + timedelta(days=21), "21dias"),
        else_="futuro",
    )
    query = select(
        Etapa.id, Etapa.project_id, Etapa.data_fim, Etapa.ordem, bucket.label("bucket")
    ).where(*_open_stage_conditions(project_ids))
    if responsible:
        query = query.where(
            Etapa.responsaveis.any(
                func.lower(func.trim(EtapaResponsavel.label))
                == " ".join(responsible.split()).casefold()
            )
        )
    return query.subquery()


def _ranked_projects(stages: Subquery, visible: tuple[str, ...]) -> Subquery:
    visible_count = func.sum(case((stages.c.bucket.in_(visible), 1), else_=0))
    oldest = func.min(case((stages.c.bucket == "atrasada", stages.c.data_fim)))
    return (
        select(
            stages.c.project_id,
            Project.titulo,
            func.coalesce(oldest, date.max).label("sort_date"),
            visible_count.label("visible_count"),
        )
        .join(Project, Project.id == stages.c.project_id)
        .group_by(stages.c.project_id, Project.titulo)
        .having(visible_count > 0)
        .subquery()
    )


def _earlier_score(ranked: Subquery, score: tuple[date, int]) -> ColumnElement[bool]:
    day, count = score
    return or_(
        ranked.c.sort_date < day,
        and_(ranked.c.sort_date == day, ranked.c.visible_count > count),
    )


def _later_score(ranked: Subquery, score: tuple[date, int]) -> ColumnElement[bool]:
    day, count = score
    return or_(
        ranked.c.sort_date > day,
        and_(ranked.c.sort_date == day, ranked.c.visible_count < count),
    )


def _page_ids(ranked: Subquery, offset: int, limit: int) -> list[int]:
    # SQL localiza a janela por atraso/quantidade. Só os empates das bordas são
    # expandidos: lower/collation do banco não reproduzem str.casefold do contrato.
    scores = db.session.execute(
        select(ranked.c.sort_date, ranked.c.visible_count)
        .order_by(ranked.c.sort_date, ranked.c.visible_count.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    if not scores:
        return []
    before = db.session.scalar(
        select(func.count())
        .select_from(ranked)
        .where(_earlier_score(ranked, scores[0]))
    )
    candidates = db.session.execute(
        select(ranked).where(
            ~_earlier_score(ranked, scores[0]), ~_later_score(ranked, scores[-1])
        )
    ).all()
    candidates.sort(
        key=lambda row: (
            row.sort_date,
            -row.visible_count,
            (row.titulo or "").casefold(),
            row.project_id,
        )
    )
    start = offset - int(before or 0)
    return [row.project_id for row in candidates[start : start + limit]]


def _global_maps(stages: Subquery) -> tuple[dict[int, str], dict[int, dict[str, int]]]:
    counts = (
        select(
            Task.etapa_id,
            func.count(Task.id).label("total"),
            func.sum(case((Task.status == "finalizada", 1), else_=0)).label("done"),
        )
        .where(Task.etapa_id.in_(select(stages.c.id)), Task.is_archived.is_(False))
        .group_by(Task.etapa_id)
        .subquery()
    )
    rows = db.session.execute(
        select(
            stages.c.id,
            stages.c.bucket,
            func.coalesce(counts.c.total, 0),
            func.coalesce(counts.c.done, 0),
        )
        .outerjoin(counts, counts.c.etapa_id == stages.c.id)
        .order_by(stages.c.project_id, stages.c.ordem, stages.c.id)
    ).all()
    return (
        {row[0]: row[1] for row in rows},
        {row[0]: {"total": int(row[2]), "done": int(row[3])} for row in rows},
    )


def _summary(stages: Subquery, total_projects: int) -> dict[str, int]:
    counts = {
        "total_projects": total_projects,
        "atrasada": 0,
        "7dias": 0,
        "14dias": 0,
        "21dias": 0,
        "sem_data": 0,
    }
    for bucket, total in db.session.execute(
        select(stages.c.bucket, func.count()).group_by(stages.c.bucket)
    ):
        if bucket in counts:
            counts[bucket] = int(total)
    return counts


def _page_rows(
    project_ids: list[int],
    stages: Subquery,
    bucket_map: dict[int, str],
    visible: tuple[str, ...],
    today: date,
) -> list[dict[str, object]]:
    if not project_ids:
        return []
    projects = {
        project.id: project
        for project in Project.query.options(joinedload(Project.orgao_ref))
        .filter(Project.id.in_(project_ids))
        .all()
    }
    query = Etapa.query.options(selectinload(Etapa.responsaveis)).filter(
        Etapa.id.in_(select(stages.c.id).where(stages.c.project_id.in_(project_ids)))
    )
    rows = query.order_by(
        Etapa.project_id,
        Etapa.data_fim.is_(None),
        Etapa.data_fim,
        Etapa.data_inicio.is_(None),
        Etapa.data_inicio,
        func.coalesce(Etapa.ordem, 10**9),
        Etapa.id,
    ).all()
    by_project: dict[int, list[Etapa]] = defaultdict(list)
    for stage in rows:
        by_project[stage.project_id].append(stage)
    return [
        _project_row(
            projects[project_id], by_project[project_id], bucket_map, visible, today
        )
        for project_id in project_ids
    ]


def _project_row(
    project: Project,
    stages: list[Etapa],
    buckets: dict[int, str],
    visible: tuple[str, ...],
    today: date,
) -> dict[str, object]:
    counts = Counter(buckets[stage.id] for stage in stages)
    shown = [stage for stage in stages if buckets[stage.id] in visible]
    others = [stage for stage in stages if buckets[stage.id] not in visible]
    overdue = [
        (today - stage.data_fim).days
        for stage in stages
        if buckets[stage.id] == "atrasada"
    ]
    return {
        "projeto": project,
        "etapas_visiveis": shown,
        "etapas_outras": others,
        "qtd_visiveis": len(shown),
        "qtd_outras": len(others),
        "qtd_atrasadas": counts["atrasada"],
        "qtd_7dias": counts["7dias"],
        "qtd_14dias": counts["7dias"] + counts["14dias"],
        "qtd_21dias": counts["7dias"] + counts["14dias"] + counts["21dias"],
        "qtd_sem_data": counts["sem_data"],
        "max_overdue_days": max(overdue, default=0),
    }


def build_pending_context(
    selected_orgao_id: int | None,
    *,
    today: date,
    apenas_orgao: bool = False,
    filtro_periodo: str = "atrasados",
    selected_responsavel: str = "",
    selected_priority: str = "",
    search_query: str = "",
    pending_page: int = 1,
) -> dict[str, object]:
    """Pagina antes de carregar Project/Etapa, preservando os mapas globais da API."""
    period = filtro_periodo if filtro_periodo in VISIBLE_BUCKETS else "atrasados"
    project_ids = _base_project_ids(
        selected_orgao_id, apenas_orgao, selected_priority, search_query
    )
    stages = _stage_projection(project_ids, selected_responsavel, today)
    ranked = _ranked_projects(stages, VISIBLE_BUCKETS[period])
    total = int(db.session.scalar(select(func.count()).select_from(ranked)) or 0)
    pages = (total + 14) // 15
    page = max(1, min(pending_page or 1, pages)) if pages else 1
    selected = _page_ids(ranked, (page - 1) * 15, 15) if total else []
    buckets, progress = _global_maps(stages)
    objetivos, _, _ = get_goal_catalog_context()
    return {
        "projetos_com_etapas": _page_rows(
            selected, stages, buckets, VISIBLE_BUCKETS[period], today
        ),
        "objetivos": objetivos,
        "orgaos_options": get_user_orgao_options(g.user),
        "selected_orgao": selected_orgao_id,
        "filtro_periodo": period,
        "selected_responsavel": selected_responsavel,
        "selected_priority": selected_priority,
        "search_query": search_query,
        "responsaveis_options": _responsavel_options(project_ids),
        "period_options": PERIOD_OPTIONS,
        "period_label_map": PERIOD_LABELS,
        "etapa_bucket_map": buckets,
        "etapa_position_map": build_etapa_position_map(selected),
        "etapa_task_progress": progress,
        "summary_counts": _summary(stages, total),
        "pending_page": page,
        "pending_total_pages": pages,
        "pending_per_page": 15,
        "pending_total_projects": total,
    }
