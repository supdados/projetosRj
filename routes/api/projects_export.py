"""Endpoint JSON de exportação de projetos consumido pela SPA.

``GET /api/projetos/exportar`` aceita os mesmos filtros de ``GET /api/projetos``
(sem default implícito de status) mais ``?colunas=`` (slugs do registry de
``services/project_export.py``) e devolve o arquivo tabular para download.
``?com_etapas=1`` troca para o formato longo (1 linha por etapa), com as colunas
de etapa em ``?colunas_etapa=``.
A rota legada ``/projects/download`` permanece intocada (KEEP-ENDPOINT).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence

from flask import Response, g, request
from flask_sqlalchemy.query import Query
from sqlalchemy import and_, distinct, func, select

from models import Etapa, Project, db
from services.project_export import (
    DEFAULT_EXPORT_SLUGS,
    DEFAULT_EXPORT_STAGE_SLUGS,
    EXPORT_COLUMNS,
    EXPORT_STAGE_COLUMNS,
    ExportColumn,
    StageExportColumn,
    build_export_headers_with_stages,
    build_export_query,
    build_export_rows,
    build_export_rows_with_stages,
    write_tabular_bytes,
)
from time_utils import utc_now

from ..blueprint import main_bp
from ..orgao_scope import (
    parse_apenas_orgao_flag,
    sanitize_orgao_filter_for_current_user,
)
from ..projects.list_filters import ProjectsListFilters
from .envelope import fail
from .negotiation import api_login_required

MAX_EXPORT_ROWS = 10_000


def _parse_slugs(
    raw: str | None,
    registry: Mapping[str, ExportColumn | StageExportColumn],
    default: Sequence[str],
) -> list[str]:
    """Valida uma lista de slugs separada por vírgula e devolve na ordem recebida."""
    if raw is None:
        return list(default)
    slugs = [slug.strip() for slug in raw.split(",") if slug.strip()]
    if not slugs:
        raise ValueError("Escolha ao menos uma coluna.")
    for slug in slugs:
        if slug not in registry:
            lista = ", ".join(registry)
            raise ValueError(f"Coluna inválida: {slug!r}. Use uma de {lista}.")
    return slugs


def _parse_export_slugs(raw: str | None) -> list[str]:
    """Valida ``?colunas=`` contra o registry de colunas de projeto."""
    return _parse_slugs(raw, EXPORT_COLUMNS, DEFAULT_EXPORT_SLUGS)


def _parse_export_stage_slugs(raw: str | None) -> list[str]:
    """Valida ``?colunas_etapa=`` contra o registry de colunas de etapa."""
    return _parse_slugs(raw, EXPORT_STAGE_COLUMNS, DEFAULT_EXPORT_STAGE_SLUGS)


def _export_filters_from_request(selected_orgao_id: int | None) -> ProjectsListFilters:
    return ProjectsListFilters(
        selected_orgao_id=selected_orgao_id,
        apenas_orgao=parse_apenas_orgao_flag(request.args.get("apenas_orgao")),
        selected_status=request.args.get("status"),
        selected_priority=request.args.get("prioridade"),
        selected_atraso=request.args.get("atraso"),
        selected_special_project=request.args.get("special_project"),
        selected_delivery_type=request.args.get("delivery_type"),
        selected_abep_indicator=request.args.get("abep_indicator"),
        selected_objetivo=request.args.get("objetivo"),
        selected_colecao_id=request.args.get("colecao", type=int),
        excluded_colecao_id=request.args.get("excluir_colecao", type=int),
        search_query=(
            request.args.get("q") or request.args.get("search") or ""
        ).strip(),
    )


def _count_stage_export_rows(query: Query) -> int:
    """Linhas do formato longo: uma por etapa de workflow + uma por projeto sem etapa."""
    ids = query.order_by(None).with_entities(Project.id).subquery()
    escopo = and_(
        Etapa.project_id.in_(select(ids.c.id)),
        Etapa.entry_type != "google_meeting",
    )
    etapas = db.session.query(func.count(Etapa.id)).filter(escopo).scalar() or 0
    com_etapa = (
        db.session.query(func.count(distinct(Etapa.project_id))).filter(escopo).scalar()
        or 0
    )
    return etapas + max(query.count() - com_etapa, 0)


def _teto_excedido_message(com_etapas: bool) -> str:
    unidade = "linhas" if com_etapas else "projetos"
    return f"Exportação acima de 10.000 {unidade} — refine os filtros."


def _export_table(
    projects: list[Project], slugs: list[str], stage_slugs: list[str] | None
) -> tuple[list[str], Iterator[list[str]]]:
    if stage_slugs is None:
        cabecalhos = [EXPORT_COLUMNS[slug].header for slug in slugs]
        return cabecalhos, build_export_rows(projects, slugs)
    return (
        build_export_headers_with_stages(slugs, stage_slugs),
        build_export_rows_with_stages(projects, slugs, stage_slugs),
    )


def _tabular_download_response(
    projects: list[Project], slugs: list[str], stage_slugs: list[str] | None
) -> Response:
    cabecalhos, linhas = _export_table(projects, slugs, stage_slugs)
    body = write_tabular_bytes(cabecalhos, linhas)
    filename = f"projetos-{utc_now().strftime('%Y%m%d-%H%M')}.csv"
    response = Response(body, mimetype="text/csv")
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@main_bp.route("/api/projetos/exportar", methods=["GET"])
@api_login_required
def api_projetos_exportar() -> Response | tuple[Response, int]:
    """Exporta os projetos visíveis (filtros da lista) nas colunas pedidas."""
    selected_orgao_id, invalid_orgao_filter = sanitize_orgao_filter_for_current_user(
        request.args.get("orgao")
    )
    if invalid_orgao_filter:
        return fail(
            "Filtro de órgão inválido para o usuário.",
            status=422,
            code="validation",
        )
    com_etapas = request.args.get("com_etapas") == "1"
    try:
        slugs = _parse_export_slugs(request.args.get("colunas"))
        stage_slugs = (
            _parse_export_stage_slugs(request.args.get("colunas_etapa"))
            if com_etapas
            else None
        )
    except ValueError as exc:
        return fail(str(exc), status=422, code="validation")

    query = build_export_query(_export_filters_from_request(selected_orgao_id), g.user)
    total = _count_stage_export_rows(query) if com_etapas else query.count()
    if total > MAX_EXPORT_ROWS:
        return fail(
            _teto_excedido_message(com_etapas),
            status=422,
            code="validation",
        )
    return _tabular_download_response(query.all(), slugs, stage_slugs)
