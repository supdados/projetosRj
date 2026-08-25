"""Endpoints JSON de projetos (telas de leitura) consumidos pela SPA SvelteKit.

Fase 2 (telas de leitura). Dois endpoints, ambos no envelope canônico e
protegidos por ``api_login_required`` (401 JSON):

    - ``GET /api/projetos-pendentes`` — reaproveita
      ``build_projetos_pendentes_context``. Respeita o escopo de órgão
      server-side (``orgao_scope``); filtro de órgão inválido => 422.
    - ``GET /api/projetos/<id>/historico`` — sucessor da extinta rota Jinja
      ``/project/<id>/history``, reaproveitando ``build_project_history_context``
      e validando o acesso via ``require_project_rank`` (404 idêntico para
      projeto inexistente e para projeto fora do escopo do usuário).

Anexa ao ``main_bp`` ÚNICO (``routes/blueprint.py``); NÃO cria blueprint novo.
"""

from __future__ import annotations

from typing import Any

from flask import Response, request
from werkzeug.exceptions import NotFound

from services.authorization import PAPEL_LEITOR, require_project_rank

from ..blueprint import main_bp
from ..orgao_scope import (
    parse_apenas_orgao_flag,
    sanitize_orgao_filter_for_current_user,
)
from ..projects.views import (
    build_project_history_context,
    build_projects_list_context,
    build_projetos_pendentes_context,
)
from .envelope import fail, fail_not_found, ok
from .negotiation import api_login_required
from .serializers import (
    serialize_orgao_option,
    serialize_pending_project_row,
    serialize_project_card,
    serialize_project_history_entry,
)


def _serialize_pending_context(context: dict[str, Any]) -> dict[str, Any]:
    """Converte o contexto de "Projetos Pendentes" em payload JSON-safe.

    Serializa cada linha (projeto + etapas + contadores) via
    ``serialize_pending_project_row`` e repassa os derivados de listagem já
    calculados no backend (mapas de bucket/progresso, contadores agregados e
    metadados de paginação), preservando os mesmos nomes do template Jinja.

    Args:
        context: Saída de ``build_projetos_pendentes_context``.

    Returns:
        ``dict`` JSON-safe com ``projetos`` serializados, mapas auxiliares,
        ``summary_counts`` e a paginação.
    """
    period_label_map = context["period_label_map"]
    return {
        "projetos": [
            serialize_pending_project_row(row) for row in context["projetos_com_etapas"]
        ],
        "filtro_periodo": context["filtro_periodo"],
        # Rótulo legível do período selecionado, derivado da MESMA fonte de
        # verdade do Jinja (``period_label_map``). O front consome este campo em
        # vez de recalcular o rótulo (débito técnico #4 — evita drift).
        "periodo_label": period_label_map.get(
            context["filtro_periodo"], context["filtro_periodo"]
        ),
        "period_label_map": period_label_map,
        "period_options": [
            {"value": value, "label": label}
            for value, label in context["period_options"]
        ],
        "selected_responsavel": context["selected_responsavel"],
        "selected_priority": context["selected_priority"],
        "search_query": context["search_query"],
        "selected_orgao": context["selected_orgao"],
        "responsaveis_options": context["responsaveis_options"],
        "orgaos_options": [
            serialize_orgao_option(node) for node in context["orgaos_options"]
        ],
        "etapa_bucket_map": {
            str(etapa_id): bucket
            for etapa_id, bucket in context["etapa_bucket_map"].items()
        },
        # Posição 1-based de cada etapa na lista completa do projeto — permite
        # ao front exibir a MESMA numeração "<projeto>.<posição>" do Detalhe.
        "etapa_position_map": {
            str(etapa_id): position
            for etapa_id, position in context["etapa_position_map"].items()
        },
        "etapa_task_progress": {
            str(etapa_id): progress
            for etapa_id, progress in context["etapa_task_progress"].items()
        },
        "summary_counts": context["summary_counts"],
        "pagination": {
            "page": context["pending_page"],
            "per_page": context["pending_per_page"],
            "total_pages": context["pending_total_pages"],
            "total": context["pending_total_projects"],
        },
    }


@main_bp.route("/api/projetos-pendentes", methods=["GET"])
@api_login_required
def api_projetos_pendentes() -> Response | tuple[Response, int]:
    """Retorna os dados de "Projetos Pendentes" no envelope canônico para a SPA.

    Reaproveita ``build_projetos_pendentes_context`` (a mesma fonte usada pela
    rota Jinja) e respeita o escopo de órgão server-side. O filtro ``?orgao=`` é
    sanitizado para o usuário corrente; um valor inválido (fora do escopo)
    resulta em 422 JSON em vez do redirect 302 do fluxo Jinja. Os parâmetros
    ``?periodo=``, ``?responsavel=`` e ``?page=`` espelham os da tela Jinja.

    Returns:
        Envelope ``{"ok": true, "data": {...}}`` com HTTP 200; ou
        ``fail(..., 422, "validation")`` quando o filtro de órgão é inválido.
        ``api_login_required`` devolve 401 JSON quando não há sessão.
    """
    selected_orgao_id, invalid_orgao_filter = sanitize_orgao_filter_for_current_user(
        request.args.get("orgao")
    )
    if invalid_orgao_filter:
        return fail(
            "Filtro de órgão inválido para o usuário.",
            status=422,
            code="validation",
        )

    context = build_projetos_pendentes_context(
        selected_orgao_id,
        apenas_orgao=parse_apenas_orgao_flag(request.args.get("apenas_orgao")),
        filtro_periodo=(request.args.get("periodo") or "atrasados").strip(),
        selected_responsavel=(request.args.get("responsavel") or "").strip(),
        selected_priority=(request.args.get("prioridade") or "").strip(),
        search_query=(
            request.args.get("q") or request.args.get("search") or ""
        ).strip(),
        pending_page=request.args.get("page", 1, type=int),
    )
    return ok(_serialize_pending_context(context))


def _card_com_favorito(project: Any, favoritos: set[int]) -> dict[str, Any]:
    """Card da lista + ``favorito`` (estrela), resolvido do conjunto pré-carregado."""
    card = serialize_project_card(project)
    card["favorito"] = project.id in favoritos
    return card


def _serialize_projects_list_context(context: dict[str, Any]) -> dict[str, Any]:
    """Converte o contexto da Lista de Projetos em payload JSON-safe.

    Serializa cada projeto via ``serialize_project_card`` e repassa os filtros
    selecionados, as opções de filtro (incluindo ``orgaos_options`` e os
    indicadores ABEP) e a paginação, preservando a fonte de verdade de
    ``build_projects_list_context`` (sem recalcular nada no cliente).

    Args:
        context: Saída de ``build_projects_list_context``.

    Returns:
        ``dict`` JSON-safe com ``projetos`` serializados, ``filters``
        selecionados, ``options`` de filtro e ``pagination``.
    """
    favoritos = context["favorito_project_ids"]
    return {
        "projetos": [
            _card_com_favorito(project, favoritos) for project in context["projects"]
        ],
        "filters": {
            "status": context["selected_status"],
            "prioridade": context["selected_priority"],
            "atraso": context["selected_atraso"],
            "special_project": context["selected_special_project"],
            "delivery_type": context["selected_delivery_type"],
            "abep_indicator": context["selected_abep_indicator"],
            "objetivo": context["selected_objetivo"],
            "colecao": context["selected_colecao"],
            "q": context["search_query"],
            "selected_orgao": context["selected_orgao"],
        },
        "options": {
            "special_projects_options": context["special_projects_options"],
            "delivery_types_options": context["delivery_types_options"],
            "abep_indicadores_options": context["abep_indicadores_options"],
            "priorities": context["priorities"],
            "statuses": context["statuses"],
            "atrasos_options": [
                {"value": value, "label": label}
                for value, label in context["atrasos_options"]
            ],
            "orgaos_options": [
                serialize_orgao_option(node) for node in context["orgaos_options"]
            ],
            # Picker de escrita do modal Criar Projeto: shape {id, sigla, nome,
            # pai_id} de scoped_orgao_options (já JSON-safe), rank >= editor.
            "orgaos_assignable_options": context["orgaos_assignable_options"],
        },
        "pagination": {
            "page": context["page"],
            "per_page": context["per_page"],
            "total": context["total_projects"],
            "total_pages": context["total_pages"],
        },
    }


@main_bp.route("/api/projetos", methods=["GET"])
@api_login_required
def api_projetos() -> Response | tuple[Response, int]:
    """Retorna a Lista de Projetos no envelope canônico para a SPA.

    Reaproveita ``build_projects_list_context`` (a mesma fonte usada pela rota
    Jinja ``/projects``) e respeita o escopo de órgão server-side. O filtro
    ``?orgao=`` é sanitizado para o usuário corrente; um valor inválido (fora do
    escopo) resulta em 422 JSON (``validation``) em vez do redirect 302 do fluxo
    Jinja. Os parâmetros ``?status=`` (default "Vigente"), ``?prioridade=``,
    ``?atraso=``, ``?special_project=``, ``?delivery_type=``,
    ``?abep_indicator=``, ``?objetivo=``, ``?q=`` (busca) e ``?page=`` espelham
    os filtros da tela Jinja (``?q`` é o alias JSON de ``?search``). ``?colecao=``
    restringe à coleção do PRÓPRIO usuário (id de outro dono = lista vazia) e
    ``?excluir_colecao=`` faz o inverso — omite os projetos já pertencentes à
    coleção (picker "adicionar projetos"). ``?per_page=`` ajusta o tamanho da
    página entre 1 e 100 (default 40).

    Returns:
        Envelope ``{"ok": true, "data": {...}}`` com HTTP 200; ou
        ``fail(..., 422, "validation")`` quando o filtro de órgão é inválido.
        ``api_login_required`` devolve 401 JSON quando não há sessão.
    """
    selected_orgao_id, invalid_orgao_filter = sanitize_orgao_filter_for_current_user(
        request.args.get("orgao")
    )
    if invalid_orgao_filter:
        return fail(
            "Filtro de órgão inválido para o usuário.",
            status=422,
            code="validation",
        )

    selected_status = request.args.get("status")
    if selected_status is None:
        selected_status = "Vigente"

    context = build_projects_list_context(
        selected_priority=request.args.get("prioridade"),
        selected_status=selected_status,
        selected_orgao_id=selected_orgao_id,
        apenas_orgao=parse_apenas_orgao_flag(request.args.get("apenas_orgao")),
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
        page=request.args.get("page", 1, type=int),
        # Teto de 100: o picker precisa de uma janela maior, sem virar dump.
        per_page=max(1, min(request.args.get("per_page", 40, type=int), 100)),
    )
    return ok(_serialize_projects_list_context(context))


def _serialize_history_context(context: dict[str, Any]) -> dict[str, Any]:
    """Converte o contexto de histórico de projeto em payload JSON-safe.

    Serializa o cabeçalho do projeto via ``serialize_project_card`` e cada
    entrada via ``serialize_project_history_entry``.

    Args:
        context: Saída de ``build_project_history_context`` (``project`` +
            ``history``).

    Returns:
        ``dict`` JSON-safe com ``project`` e ``history``.
    """
    return {
        "project": serialize_project_card(context["project"]),
        "history": [
            serialize_project_history_entry(entry) for entry in context["history"]
        ],
    }


@main_bp.route("/api/projetos/<int:project_id>/historico", methods=["GET"])
@api_login_required
def api_projeto_historico(project_id: int) -> Response | tuple[Response, int]:
    """Retorna o histórico de um projeto no envelope canônico para a SPA.

    Reaproveita ``build_project_history_context`` e valida o acesso via
    ``require_project_rank`` no rank ``leitor``. Diferente da rota Jinja (flash +
    redirect), devolve erro estruturado: 404 idêntico para projeto inexistente e
    para projeto invisível ao usuário (S5/F4-2b).

    Args:
        project_id: ID do projeto cujo histórico será carregado.

    Returns:
        Envelope ``{"ok": true, "data": {...}}`` com HTTP 200; ou
        ``fail_not_found()``. ``api_login_required`` devolve 401 JSON quando não
        há sessão.
    """
    try:
        context = build_project_history_context(project_id)
    except NotFound:
        return fail_not_found()

    denied = require_project_rank(context["project"], PAPEL_LEITOR)
    if denied:
        return denied

    return ok(_serialize_history_context(context))
