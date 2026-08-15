"""Busca global: escopo, queries por tipo e os dois modos de payload.

Modo dropdown (``limit`` por tipo + ``has_more``) alimenta o GlobalSearchBox e
o legado ``/api/busca-global``; o modo paginado (``page``/``per_page``/
``types``) alimenta a tela ``/busca`` da SPA via ``/api/busca`` com lista plana
na ordem canônica projetos → etapas → tarefas → eventos.

Os ``counts`` do dropdown têm TETO (``GLOBAL_SEARCH_COUNT_CAP``) e vêm com as
chaves opcionais ``meta.counts_capped_at``/``meta.counts_capped``; ausentes (ou
``counts_capped_at=None``) significam contagem exata. O modo paginado mantém
contagem exata — ``pagination`` depende dos totais reais.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from flask import g, jsonify, request
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import joinedload

from models import CalendarEvent, Etapa, EtapaResponsavel, Project, Task, db
from services.authorization import project_visibility_criterion

from .blueprint import main_bp
from .decorators import login_required
from .orgao_scope import (
    expand_orgao_filter_ids,
    sanitize_orgao_filter_for_current_user,
)
from .search_serializers import (
    _serialize_event_rows,
    _serialize_project_rows,
    _serialize_stage_rows,
    _serialize_task_rows,
)
from .shared import parse_db_integer_id, project_orgao_search_filter

GLOBAL_SEARCH_DEFAULT_LIMIT = 5
GLOBAL_SEARCH_API_MAX_LIMIT = 20
GLOBAL_SEARCH_PAGE_SIZE = 40
GLOBAL_SEARCH_PAGE_MAX_PER_PAGE = 100
# Teto do contador do dropdown (typeahead): acima dele o número deixa de importar
# para a decisão do usuário e o COUNT integral passa a custar uma varredura por tecla.
GLOBAL_SEARCH_COUNT_CAP = 100
SEARCH_TYPE_KEYS = ("projects", "stages", "tasks", "events")

_SEARCH_SERIALIZERS = {
    "projects": _serialize_project_rows,
    "stages": _serialize_stage_rows,
    "tasks": _serialize_task_rows,
    "events": _serialize_event_rows,
}


@dataclass(frozen=True)
class _SearchScope:
    user_scope_restricted: bool
    # Criterion §5.3 (subtree de área OR convite ativo); None quando irrestrito.
    project_criterion: object
    selected_subtree_ids: set[int]


def _resolve_search_scope(user, selected_orgao_id) -> _SearchScope:
    if user and not user.is_admin:
        project_criterion = project_visibility_criterion(user)
        user_scope_restricted = True
    else:
        project_criterion = None
        user_scope_restricted = False

    selected_subtree_ids = (
        expand_orgao_filter_ids(selected_orgao_id) if selected_orgao_id else set()
    )
    return _SearchScope(
        user_scope_restricted=user_scope_restricted,
        project_criterion=project_criterion,
        selected_subtree_ids=selected_subtree_ids,
    )


def _prefix_order_for(column, prefix_pattern: str):
    return case(
        (func.lower(func.coalesce(column, "")).like(prefix_pattern), 0), else_=1
    )


def _project_search_query(term: str, user, scope: _SearchScope):
    search_pattern = f"%{term}%"
    search_id = parse_db_integer_id(term)
    project_id_filter = (Project.id == search_id) if search_id is not None else None

    project_text_filters = or_(
        Project.titulo.ilike(search_pattern),
        project_orgao_search_filter(search_pattern),
        Project.short_description.ilike(search_pattern),
        Project.observacao.ilike(search_pattern),
    )

    project_query = Project.query.filter(
        or_(project_id_filter, project_text_filters)
        if project_id_filter is not None
        else project_text_filters
    )
    if scope.user_scope_restricted:
        project_query = project_query.filter(scope.project_criterion)
    if scope.selected_subtree_ids:
        project_query = project_query.filter(
            Project.orgao_id.in_(scope.selected_subtree_ids)
        )
    return project_query.order_by(
        _prefix_order_for(Project.titulo, f"{term.lower()}%"), Project.id.desc()
    )


def _stage_responsavel_search_criterion(search_pattern: str):
    """Casa etapas cujo responsável contém o termo, priorizando a N:N.

    O espelho ``Etapa.responsavel`` é truncado em 100 chars, então uma etapa com
    muitas áreas some da busca se só ele for consultado. Mesma precedência de
    ``routes/projects/views.py::_responsavel_criterion`` (estruturado OU espelho
    quando não há linhas N:N) — unificar os dois na Sprint 3.1.
    """
    estruturado = Etapa.responsaveis.any(EtapaResponsavel.label.ilike(search_pattern))
    legado = and_(~Etapa.responsaveis.any(), Etapa.responsavel.ilike(search_pattern))
    return or_(estruturado, legado)


def _stage_search_query(term: str, user, scope: _SearchScope):
    search_pattern = f"%{term}%"
    stage_query = (
        Etapa.query.join(Project, Etapa.project_id == Project.id)
        .options(joinedload(Etapa.project))
        .filter(
            or_(
                Etapa.descricao.ilike(search_pattern),
                Etapa.comentarios.ilike(search_pattern),
                _stage_responsavel_search_criterion(search_pattern),
            )
        )
    )
    if scope.user_scope_restricted:
        stage_query = stage_query.filter(scope.project_criterion)
    if scope.selected_subtree_ids:
        stage_query = stage_query.filter(
            Project.orgao_id.in_(scope.selected_subtree_ids)
        )
    return stage_query.order_by(
        _prefix_order_for(Etapa.descricao, f"{term.lower()}%"), Etapa.id.desc()
    )


def _task_search_query(term: str, user, scope: _SearchScope):
    search_pattern = f"%{term}%"
    task_query = (
        Task.query.outerjoin(Project, Task.project_id == Project.id)
        .options(joinedload(Task.project))
        .filter(
            or_(
                Task.descricao.ilike(search_pattern),
                Task.responsavel.ilike(search_pattern),
                Task.status.ilike(search_pattern),
                Task.prioridade.ilike(search_pattern),
                Task.tipo_pedido.ilike(search_pattern),
            )
        )
    )
    if scope.user_scope_restricted:
        task_query = task_query.filter(
            or_(
                and_(Task.project_id.isnot(None), scope.project_criterion),
                and_(Task.project_id.is_(None), Task.created_by_id == user.id),
            )
        )
    if scope.selected_subtree_ids:
        task_query = task_query.filter(
            Task.project_id.isnot(None),
            Project.orgao_id.in_(scope.selected_subtree_ids),
        )
    return task_query.order_by(
        _prefix_order_for(Task.descricao, f"{term.lower()}%"), Task.id.desc()
    )


def _event_search_query(term: str, user, scope: _SearchScope):
    search_pattern = f"%{term}%"
    search_id = parse_db_integer_id(term)
    event_id_filter = (CalendarEvent.id == search_id) if search_id is not None else None
    event_text_filters = or_(
        CalendarEvent.title.ilike(search_pattern),
        CalendarEvent.description.ilike(search_pattern),
        CalendarEvent.location.ilike(search_pattern),
    )
    event_query = CalendarEvent.query.filter(
        CalendarEvent.user_id == user.id,
        (
            or_(event_id_filter, event_text_filters)
            if event_id_filter is not None
            else event_text_filters
        ),
    )
    return event_query.order_by(
        _prefix_order_for(CalendarEvent.title, f"{term.lower()}%"),
        CalendarEvent.starts_at.desc(),
        CalendarEvent.id.desc(),
    )


def _empty_global_search_payload(term):
    normalized = (term or "").strip()
    return {
        "query": normalized,
        "meta": {
            "limit_per_type": None,
            "has_more": {
                "projects": False,
                "stages": False,
                "tasks": False,
                "events": False,
                "any": False,
            },
        },
        "counts": {
            "projects": 0,
            "stages": 0,
            "tasks": 0,
            "events": 0,
            "total": 0,
        },
        "results": {
            "projects": [],
            "stages": [],
            "tasks": [],
            "events": [],
        },
    }


def _empty_paginated_search_payload(
    term, selected_types: tuple[str, ...], per_page: int
) -> dict:
    payload = _empty_global_search_payload(term)
    payload["meta"]["pagination"] = {
        "page": 1,
        "per_page": per_page,
        "total_pages": 0,
        "total": 0,
    }
    payload["meta"]["type_counts"] = {key: 0 for key in SEARCH_TYPE_KEYS}
    payload["meta"]["selected_types"] = list(selected_types)
    return payload


def _normalize_global_search_limit(
    raw_limit,
    default_limit=GLOBAL_SEARCH_DEFAULT_LIMIT,
    max_limit=GLOBAL_SEARCH_API_MAX_LIMIT,
):
    if raw_limit is None or raw_limit == "":
        return default_limit
    try:
        parsed = int(raw_limit)
    except (TypeError, ValueError):
        return default_limit
    return max(1, min(parsed, max_limit))


def _capped_count(query, cap: int) -> int:
    """Conta linhas com teto: ``SELECT count(*) FROM (<query> LIMIT cap)``.

    Sem o teto, cada tecla do typeahead dispara um ``COUNT(*)`` integral por tipo
    sobre ``ILIKE '%termo%'`` (varredura completa). Retorna o valor exato abaixo do
    teto e exatamente ``cap`` quando há ``cap`` linhas ou mais.

    Exemplo: ``_capped_count(_project_search_query("de", user, scope), 100)`` -> 100
    quando existem 3 mil projetos com "de" no título.
    """
    if cap < 1:
        raise ValueError(f"cap deve ser >= 1, recebido: {cap!r}")
    limited = query.order_by(None).limit(cap).subquery()
    return db.session.query(func.count()).select_from(limited).scalar() or 0


def _search_queries_by_type(term: str, user, scope: _SearchScope) -> dict:
    return {
        "projects": _project_search_query(term, user, scope),
        "stages": _stage_search_query(term, user, scope),
        "tasks": _task_search_query(term, user, scope),
        "events": _event_search_query(term, user, scope),
    }


def build_global_search_results(
    term,
    user,
    limit_per_type=None,
    include_has_more=False,
    selected_orgao_id=None,
):
    """Monta o payload do dropdown (fatia por tipo + ``has_more`` + ``counts``).

    ``counts[tipo]`` é exato até ``GLOBAL_SEARCH_COUNT_CAP``; a partir dele satura no
    teto e ``meta.counts_capped[tipo]`` vira ``True`` (o consumidor exibe "99+").
    ``meta.counts_capped_at`` traz o teto vigente, ou ``None`` quando nenhum COUNT
    com teto pôde rodar (``limit_per_type=None``, contagem já exata).

    Exemplo: ``build_global_search_results("de", g.user, limit_per_type=5,
    include_has_more=True)``.
    """
    normalized_term = (term or "").strip()
    if not normalized_term:
        return _empty_global_search_payload(normalized_term)

    scope = _resolve_search_scope(user, selected_orgao_id)
    queries = _search_queries_by_type(normalized_term, user, scope)

    effective_limit = limit_per_type
    counts_are_capped = include_has_more and limit_per_type is not None
    if counts_are_capped:
        effective_limit = limit_per_type + 1

    def fetch_rows(query):
        if effective_limit is not None:
            query = query.limit(effective_limit)
        rows = query.all()
        if not include_has_more or limit_per_type is None:
            return rows, False
        if len(rows) > limit_per_type:
            return rows[:limit_per_type], True
        return rows, False

    results = {}
    has_more = {}
    counts = {}
    counts_capped = {}
    for key in SEARCH_TYPE_KEYS:
        rows, rows_has_more = fetch_rows(queries[key])
        results[key] = _SEARCH_SERIALIZERS[key](rows, normalized_term)
        has_more[key] = rows_has_more
        # O contador do dropdown anuncia o TOTAL encontrado, não a fatia exibida —
        # é ele que diz ao usuário se vale abrir a página de busca. O COUNT extra só
        # roda quando a fatia estourou o limite, e sempre com teto.
        if not rows_has_more:
            counts[key] = len(results[key])
            counts_capped[key] = False
            continue
        counts[key] = _capped_count(queries[key], GLOBAL_SEARCH_COUNT_CAP)
        counts_capped[key] = counts[key] >= GLOBAL_SEARCH_COUNT_CAP

    counts["total"] = sum(counts[key] for key in SEARCH_TYPE_KEYS)

    return {
        "query": normalized_term,
        "meta": {
            "limit_per_type": limit_per_type,
            "has_more": {
                **has_more,
                "any": any(has_more.values()),
            },
            "counts_capped_at": GLOBAL_SEARCH_COUNT_CAP if counts_are_capped else None,
            "counts_capped": {
                **counts_capped,
                "any": any(counts_capped.values()),
            },
        },
        "counts": counts,
        "results": results,
    }


def build_paginated_global_search(
    term: str,
    user,
    *,
    selected_types: tuple[str, ...],
    page: int,
    per_page: int,
    selected_orgao_id: int | None = None,
) -> dict:
    normalized_term = (term or "").strip()
    ordered_selected = tuple(k for k in SEARCH_TYPE_KEYS if k in selected_types)
    if not ordered_selected:
        ordered_selected = SEARCH_TYPE_KEYS
    if not normalized_term:
        return _empty_paginated_search_payload(
            normalized_term, ordered_selected, per_page
        )

    scope = _resolve_search_scope(user, selected_orgao_id)
    queries = _search_queries_by_type(normalized_term, user, scope)
    type_counts = {key: query.order_by(None).count() for key, query in queries.items()}

    total = sum(type_counts[key] for key in ordered_selected)
    total_pages = ceil(total / per_page) if total else 0
    page = min(max(page, 1), total_pages) if total_pages else 1

    start = (page - 1) * per_page
    end = start + per_page
    page_results = {key: [] for key in SEARCH_TYPE_KEYS}
    cursor = 0
    for key in ordered_selected:
        type_start, type_end = cursor, cursor + type_counts[key]
        window_lo, window_hi = max(start, type_start), min(end, type_end)
        if window_lo < window_hi:
            rows = (
                queries[key]
                .offset(window_lo - type_start)
                .limit(window_hi - window_lo)
                .all()
            )
            page_results[key] = _SEARCH_SERIALIZERS[key](rows, normalized_term)
        cursor = type_end

    counts = {
        key: type_counts[key] if key in ordered_selected else 0
        for key in SEARCH_TYPE_KEYS
    }
    counts["total"] = total

    return {
        "query": normalized_term,
        "meta": {
            "limit_per_type": None,
            "has_more": {
                "projects": False,
                "stages": False,
                "tasks": False,
                "events": False,
                "any": False,
            },
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
                "total": total,
            },
            "type_counts": type_counts,
            "selected_types": list(ordered_selected),
        },
        "counts": counts,
        "results": page_results,
    }


@main_bp.route("/api/busca-global", methods=["GET"])
@login_required
def global_search_api():
    search_term = (request.args.get("q") or "").strip()
    selected_orgao_id, _ = sanitize_orgao_filter_for_current_user(
        request.args.get("orgao")
    )
    limit_per_type = _normalize_global_search_limit(
        request.args.get("limit"),
        default_limit=GLOBAL_SEARCH_DEFAULT_LIMIT,
        max_limit=GLOBAL_SEARCH_API_MAX_LIMIT,
    )

    if len(search_term) < 2:
        return jsonify(_empty_global_search_payload(search_term))

    payload = build_global_search_results(
        search_term,
        g.user,
        limit_per_type=limit_per_type,
        include_has_more=True,
        selected_orgao_id=selected_orgao_id,
    )
    return jsonify(payload)
