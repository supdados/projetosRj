"""Endpoint JSON de exportação de projetos consumido pela SPA.

``GET /api/projetos/exportar`` aceita os mesmos filtros de ``GET /api/projetos``
(sem default implícito de status) mais ``?colunas=`` (slugs do registry de
``services/project_export.py``) e devolve o arquivo tabular para download.
A rota legada ``/projects/download`` permanece intocada (KEEP-ENDPOINT).
"""

from __future__ import annotations

from flask import Response, g, request

from models import Project
from services.project_export import (
    DEFAULT_EXPORT_SLUGS,
    EXPORT_COLUMNS,
    build_export_query,
    build_export_rows,
    write_tabular_bytes,
)
from time_utils import utc_now

from ..blueprint import main_bp
from ..orgao_scope import sanitize_orgao_filter_for_current_user
from ..projects.list_filters import ProjectsListFilters
from .envelope import fail
from .negotiation import api_login_required

MAX_EXPORT_ROWS = 10_000


def _parse_export_slugs(raw: str | None) -> list[str]:
    """Valida ``?colunas=`` e devolve os slugs na ordem recebida."""
    if raw is None:
        return list(DEFAULT_EXPORT_SLUGS)
    slugs = [slug.strip() for slug in raw.split(",") if slug.strip()]
    if not slugs:
        raise ValueError("Escolha ao menos uma coluna.")
    for slug in slugs:
        if slug not in EXPORT_COLUMNS:
            lista = ", ".join(EXPORT_COLUMNS)
            raise ValueError(f"Coluna inválida: {slug!r}. Use uma de {lista}.")
    return slugs


def _export_filters_from_request(selected_orgao_id: int | None) -> ProjectsListFilters:
    return ProjectsListFilters(
        selected_orgao_id=selected_orgao_id,
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


def _tabular_download_response(projects: list[Project], slugs: list[str]) -> Response:
    cabecalhos = [EXPORT_COLUMNS[slug].header for slug in slugs]
    body = write_tabular_bytes(cabecalhos, build_export_rows(projects, slugs))
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
    try:
        slugs = _parse_export_slugs(request.args.get("colunas"))
    except ValueError as exc:
        return fail(str(exc), status=422, code="validation")

    query = build_export_query(_export_filters_from_request(selected_orgao_id), g.user)
    if query.count() > MAX_EXPORT_ROWS:
        return fail(
            "Exportação acima de 10.000 projetos — refine os filtros.",
            status=422,
            code="validation",
        )
    return _tabular_download_response(query.all(), slugs)
