"""Endpoint JSON de busca global consumido pela SPA SvelteKit.

``GET /api/busca`` devolve, no envelope canônico, o MESMO payload que o legado
``/api/busca-global`` (``routes/search.py:global_search_api``) — projetos,
etapas, tarefas e eventos por termo — reaproveitando
``build_global_search_results`` (mesma fonte de verdade). A diferença é apenas o
contorno: aqui usamos ``api_login_required`` (401 JSON) e o envelope
``{ok, data}``, enquanto o legado usa ``@login_required`` (302) e devolve o
payload cru (consumido por ``static/js/.../global-search.js``).

NÃO altera ``/api/busca-global`` (legado). Mantém a mesma lógica de
``q``/``orgao``/``limit``, incluindo o caso ``len(termo) < 2`` -> payload vazio.

Anexa ao ``main_bp`` ÚNICO (``routes/blueprint.py``); NÃO cria blueprint novo.
"""

from __future__ import annotations

from flask import Response, g, request

from ..blueprint import main_bp
from ..orgao_scope import sanitize_orgao_filter_for_current_user
from ..search import (
    GLOBAL_SEARCH_API_MAX_LIMIT,
    GLOBAL_SEARCH_DEFAULT_LIMIT,
    _empty_global_search_payload,
    _normalize_global_search_limit,
    build_global_search_results,
)
from .envelope import ok
from .negotiation import api_login_required

# Termos com menos de 2 caracteres não disparam busca (mesma regra do legado
# ``global_search_api``): evita varreduras amplas com ruído.
GLOBAL_SEARCH_MIN_TERM_LENGTH = 2


@main_bp.route("/api/busca", methods=["GET"])
@api_login_required
def api_busca() -> Response | tuple[Response, int]:
    """Retorna os resultados da busca global no envelope canônico para a SPA.

    Espelha a lógica de ``global_search_api`` (legado): lê ``?q=`` (termo),
    ``?orgao=`` (sanitizado server-side para o usuário corrente) e ``?limit=``
    (clampado a ``[1, GLOBAL_SEARCH_API_MAX_LIMIT]``). Termos com menos de 2
    caracteres retornam o payload vazio canônico (sem varredura). O payload de
    ``build_global_search_results`` já é JSON-safe (strings/ints/urls).

    Returns:
        Envelope ``{"ok": true, "data": {...}}`` com HTTP 200 (payload de busca
        ou payload vazio). ``api_login_required`` devolve 401 JSON quando não há
        sessão.
    """
    search_term = (request.args.get("q") or "").strip()
    selected_orgao_id, _ = sanitize_orgao_filter_for_current_user(
        request.args.get("orgao")
    )
    limit_per_type = _normalize_global_search_limit(
        request.args.get("limit"),
        default_limit=GLOBAL_SEARCH_DEFAULT_LIMIT,
        max_limit=GLOBAL_SEARCH_API_MAX_LIMIT,
    )

    if len(search_term) < GLOBAL_SEARCH_MIN_TERM_LENGTH:
        return ok(_empty_global_search_payload(search_term))

    payload = build_global_search_results(
        search_term,
        g.user,
        limit_per_type=limit_per_type,
        include_has_more=True,
        selected_orgao_id=selected_orgao_id,
    )
    return ok(payload)
