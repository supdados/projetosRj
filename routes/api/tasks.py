"""Endpoint JSON do Hub de Tarefas (modo lista) consumido pela SPA SvelteKit.

``GET /api/tarefas`` devolve, no envelope canônico, as tarefas do hub agrupadas
por projeto — a MESMA fonte de verdade da rota Jinja ``/tarefas``, reaproveitada
via ``build_task_hub_context`` (em ``routes/tasks/hub.py``). Respeita o escopo de
órgão server-side (``orgao_scope``); filtro de órgão inválido => 422 (em vez do
redirect 302 do Jinja).

Suporta os mesmos filtros do hub em modo lista (projeto, órgão, prioridade,
tipo, responsável, status) e um parâmetro ``?modo=`` para alternar entre as três
visões da topnav:

    - ``ativas`` (default) — tarefas não arquivadas;
    - ``arquivadas``       — tarefas arquivadas;
    - ``finalizadas``      — tarefas finalizadas (não arquivadas), espelhando o
      atalho ``/tarefas/finalizadas`` (que no Jinja redireciona para arquivadas;
      aqui filtramos por ``status == "finalizada"`` para entregar a lista direto).

Anexa ao ``main_bp`` ÚNICO (``routes/blueprint.py``); NÃO cria blueprint novo.
"""

from __future__ import annotations

from typing import Any

from flask import Response, g, request

from ..blueprint import main_bp
from ..orgao_scope import (
    get_user_orgao_options,
    sanitize_orgao_filter_for_current_user,
)
from ..tasks.hub import HUB_GROUPS_PER_PAGE, build_task_hub_context
from ..tasks.queries import _read_task_filter_values
from .envelope import fail, ok
from .negotiation import api_login_required
from .serializers import serialize_orgao_option, serialize_task_card

#: Modos de listagem aceitos por ``?modo=`` e como cada um mapeia para os
#: parâmetros de ``build_task_hub_context``. ``finalizadas`` reusa o conjunto
#: ativo filtrado por status, espelhando o atalho Jinja sem duplicar query.
_HUB_LIST_MODES = {"ativas", "arquivadas", "finalizadas"}


def _serialize_hub_group(group: dict[str, Any]) -> dict[str, Any]:
    """Serializa um grupo de projeto do hub em payload JSON-safe.

    Reusa ``serialize_task_card`` para cada tarefa do grupo (campos reais; sem
    segredos) e expõe os metadados do projeto já calculados no agrupamento
    (``_group_hub_tasks_by_project``). Anexa ``etapa_id``/``is_first_of_stage``
    a partir dos atributos ``hub_*`` definidos pelo agrupador, para que o cliente
    monte os subgrupos por etapa sem recalcular a hierarquia.

    Args:
        group: Item de ``context["groups"]`` — dict com ``project_*`` e ``tasks``.

    Returns:
        ``dict`` JSON-safe com os dados do projeto e a lista de tarefas.
    """
    tasks = []
    for task in group["tasks"]:
        card = serialize_task_card(task)
        card["etapa_titulo"] = getattr(task, "hub_stage_titulo", None)
        card["etapa_display_id"] = getattr(task, "hub_stage_display_id", None) or None
        card["is_first_of_stage"] = bool(getattr(task, "hub_is_first_of_stage", False))
        tasks.append(card)
    return {
        "key": group["key"],
        "project_id": group["project_id"],
        "project_value": group["project_value"],
        "project_titulo": group["project_titulo"],
        "project_orgao_sigla": group.get("project_orgao_sigla"),
        "tasks": tasks,
    }


def _serialize_task_hub_context(context: dict[str, Any]) -> dict[str, Any]:
    """Converte o contexto do Hub de Tarefas em payload JSON-safe.

    Serializa cada grupo de projeto via ``_serialize_hub_group`` e repassa as
    opções de projeto e os filtros selecionados já resolvidos no backend
    (``build_task_hub_context``), sem recalcular nada no cliente.

    Args:
        context: Saída de ``build_task_hub_context``.

    Returns:
        ``dict`` JSON-safe com ``groups``, ``project_options``, ``filters`` e
        ``total_items``.
    """
    return {
        "groups": [_serialize_hub_group(group) for group in context["groups"]],
        "project_options": context["project_options"],
        "filters": {
            "project": context["selected_project"],
            "prioridade": context["selected_prioridade"],
            "tipo": context["selected_tipo"],
            "status": context["selected_status"],
            "responsavel": context["selected_responsavel"],
            "search": context["selected_search"],
            "selected_orgao": context["selected_orgao"],
        },
        "include_archived": context["include_archived"],
        "total_items": context["total_items"],
        "pagination": context["pagination"],
        # Opções de órgão para o filtro local — MESMA fonte de Pendentes
        # (get_user_orgao_options, escopo server-side), com value = ID de
        # OrgaoUnidade. A SPA antes derivava SIGLAS de project_options e o
        # sanitizador (que espera id) rejeitava qualquer escolha com 422.
        "orgaos_options": [
            serialize_orgao_option(node) for node in get_user_orgao_options(g.user)
        ],
    }


def _resolve_hub_list_mode(raw_mode: str) -> tuple[bool, str, str]:
    """Resolve o ``?modo=`` em (include_archived, status_filter, modo_normalizado).

    Args:
        raw_mode: Valor cru de ``?modo=`` (vazio => "ativas").

    Returns:
        Tupla ``(include_archived, status_override, modo)``:
            - ``ativas``     -> ``(False, "", "ativas")``;
            - ``arquivadas`` -> ``(True, "", "arquivadas")``;
            - ``finalizadas``-> ``(False, "finalizada", "finalizadas")``.
        Modo desconhecido cai em "ativas".
    """
    modo = (raw_mode or "ativas").strip().lower()
    if modo not in _HUB_LIST_MODES:
        modo = "ativas"
    if modo == "arquivadas":
        return True, "", modo
    if modo == "finalizadas":
        return False, "finalizada", modo
    return False, "", modo


@main_bp.route("/api/tarefas", methods=["GET"])
@api_login_required
def api_tarefas() -> Response | tuple[Response, int]:
    """Retorna o Hub de Tarefas (modo lista) no envelope canônico para a SPA.

    Reaproveita ``build_task_hub_context`` (a mesma fonte usada pela rota Jinja
    ``/tarefas``) e respeita o escopo de órgão server-side. O filtro ``?orgao=``
    é sanitizado para o usuário corrente; um valor inválido (fora do escopo)
    resulta em 422 JSON (``validation``) em vez do redirect 302 do fluxo Jinja.
    Os parâmetros ``?project=``, ``?prioridade=``, ``?tipo=`` e ``?responsavel=``
    espelham os filtros do hub; ``?search=`` busca por substring na descrição da
    tarefa ou no título do projeto; ``?modo=`` alterna entre ``ativas`` (default),
    ``arquivadas`` e ``finalizadas``. ``?page=`` pagina por GRUPO de projeto
    (``HUB_GROUPS_PER_PAGE`` grupos/página; metadados em ``pagination``).

    Returns:
        Envelope ``{"ok": true, "data": {...}}`` com HTTP 200; ou
        ``fail(..., 422, "validation")`` quando o filtro de órgão é inválido.
        ``api_login_required`` devolve 401 JSON quando não há sessão.
    """
    filter_values = _read_task_filter_values(request.args)
    selected_orgao_id, invalid_orgao_filter = sanitize_orgao_filter_for_current_user(
        filter_values["orgao_filter"]
    )
    if invalid_orgao_filter:
        return fail(
            "Filtro de órgão inválido para o usuário.",
            status=422,
            code="validation",
        )

    include_archived, status_override, _modo = _resolve_hub_list_mode(
        request.args.get("modo", "")
    )
    status_filter = status_override or filter_values["status_filter"]

    context = build_task_hub_context(
        project_filter=filter_values["project_filter"],
        prioridade_filter=filter_values["prioridade_filter"],
        tipo_filter=filter_values["tipo_filter"],
        status_filter=status_filter,
        responsavel_filter=filter_values["responsavel_filter"],
        search_filter=filter_values["search_filter"],
        selected_orgao_id=selected_orgao_id,
        apenas_orgao=filter_values["apenas_orgao_filter"],
        include_archived=include_archived,
        page=request.args.get("page", 1, type=int),
        per_page=HUB_GROUPS_PER_PAGE,
    )
    return ok(_serialize_task_hub_context(context))
