"""Endpoint JSON do Dashboard consumido pela SPA SvelteKit.

``GET /api/dashboard`` devolve, no envelope canônico, EXATAMENTE os mesmos dados
que a rota Jinja ``/dashboard`` (``routes/dashboard.py``) monta para o template
``index.html``: projetos recentes, tarefas recentes, contadores agregados e o
catálogo de objetivos. As queries são reaproveitadas via
``build_dashboard_context`` (mesma fonte de verdade), respeitando o escopo de
órgão server-side (``orgao_scope``). Derivados de projeto/tarefa são serializados
prontos — o cliente NÃO os recalcula.

A função é anexada ao ``main_bp`` ÚNICO (``routes/blueprint.py``); NÃO criamos
blueprint novo.
"""

from __future__ import annotations

from typing import Any

from flask import Response, request

from ..blueprint import main_bp
from ..dashboard import build_dashboard_context
from ..orgao_scope import sanitize_orgao_filter_for_current_user
from .envelope import fail, ok
from .negotiation import api_login_required
from .serializers import serialize_project_card, serialize_task_card


def _serialize_dashboard(context: dict[str, Any]) -> dict[str, Any]:
    """Converte o contexto bruto do Dashboard em payload JSON-safe.

    Serializa as listas de modelos (``recent_projects``/``recent_tasks``) e
    repassa os contadores agregados já calculados no backend, preservando os
    mesmos nomes/derivados usados pelo template Jinja.

    Args:
        context: Saída de ``build_dashboard_context`` (modelos + contadores).

    Returns:
        ``dict`` JSON-safe com ``projects``/``tasks`` serializados e os
        contadores ``counts`` agregados.
    """
    return {
        "recent_projects": [
            serialize_project_card(project) for project in context["recent_projects"]
        ],
        "recent_tasks": [serialize_task_card(task) for task in context["recent_tasks"]],
        "objetivos": context["objetivos"],
        "selected_orgao": context["selected_orgao"],
        "counts": {
            "projects": {
                "total": context["num_projects"],
                "urgente": context["count_urgente"],
                "alta": context["count_alta"],
                "media": context["count_media"],
                "baixa": context["count_baixa"],
                "vigente": context["count_vigente"],
                "finalizado": context["count_finalizado"],
                "em_atraso": context["projetos_em_atraso"],
            },
            "tasks": {
                "open_total": context["dashboard_open_tasks_count"],
                "total": context["task_items_total"],
                "nao_iniciada": context["task_items_nao_iniciada"],
                "em_andamento": context["task_items_em_andamento"],
                "para_validacao": context["task_items_para_validacao"],
                "para_ajustes": context["task_items_para_ajustes"],
                "finalizada": context["task_items_finalizada"],
                "urgente": context["task_urgente_count"],
                "alta": context["task_alta_count"],
                "media": context["task_media_count"],
                "baixa": context["task_baixa_count"],
                "atencao": context["task_atencao_count"],
            },
        },
    }


@main_bp.route("/api/dashboard", methods=["GET"])
@api_login_required
def api_dashboard() -> Response | tuple[Response, int]:
    """Retorna os dados do Dashboard no envelope canônico para a SPA.

    Reaproveita ``build_dashboard_context`` (a mesma fonte usada pela rota Jinja)
    e respeita o escopo de órgão server-side. O filtro ``?orgao=`` é sanitizado
    para o usuário corrente; um valor inválido (fora do escopo) resulta em 422
    JSON em vez do redirect 302 do fluxo Jinja.

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

    context = build_dashboard_context(selected_orgao_id)
    return ok(_serialize_dashboard(context))
