"""Endpoint JSON de busca global consumido pela SPA SvelteKit.

``GET /api/busca`` devolve, no envelope canônico, o MESMO payload que o legado
``/api/busca-global`` (``routes/search.py:global_search_api``) — projetos,
etapas, tarefas e eventos por termo — reaproveitando
``build_global_search_results`` (mesma fonte de verdade). A diferença é apenas o
contorno: aqui usamos ``api_login_required`` (401 JSON) e o envelope
``{ok, data}``, enquanto o legado usa ``@login_required`` (302) e devolve o
payload cru (consumido por ``static/js/.../global-search.js``).

Dois modos coexistem:

- **Dropdown** (sem ``?page=``): comportamento original — ``limit`` por tipo
  (default 5, cap 20, ``limit=all`` ilimitado) com ``has_more``.
- **Paginado** (``?page=`` presente): lista plana projetos → etapas → tarefas →
  eventos, filtrada por ``?types=`` (csv) e fatiada por ``?page=``/``?per_page=``
  via ``build_paginated_global_search`` — usado pela tela ``/busca``.

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
    GLOBAL_SEARCH_PAGE_MAX_PER_PAGE,
    GLOBAL_SEARCH_PAGE_SIZE,
    SEARCH_TYPE_KEYS,
    _empty_global_search_payload,
    _empty_paginated_search_payload,
    _normalize_global_search_limit,
    build_global_search_results,
    build_paginated_global_search,
)
from .envelope import ok
from .negotiation import api_login_required

# Termos com menos de 2 caracteres não disparam busca (mesma regra do legado
# ``global_search_api``): evita varreduras amplas com ruído.
GLOBAL_SEARCH_MIN_TERM_LENGTH = 2


def _parse_search_types(raw_types: str | None) -> tuple[str, ...]:
    """Filtra o csv de ``?types=`` para as chaves válidas em ordem canônica."""
    if not raw_types:
        return SEARCH_TYPE_KEYS
    tokens = {token.strip() for token in raw_types.split(",")}
    selected = tuple(key for key in SEARCH_TYPE_KEYS if key in tokens)
    return selected or SEARCH_TYPE_KEYS


def _parse_positive_int(raw_value: str | None, default: int) -> int:
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 1 else default


def _clamp_int(raw_value: str | None, default: int, lo: int, hi: int) -> int:
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(parsed, hi))


@main_bp.route("/api/busca", methods=["GET"])
@api_login_required
def api_busca() -> Response | tuple[Response, int]:
    """Retorna os resultados da busca global no envelope canônico para a SPA.

    Espelha a lógica de ``global_search_api`` (legado): lê ``?q=`` (termo),
    ``?orgao=`` (sanitizado server-side para o usuário corrente) e ``?limit=``
    (clampado a ``[1, GLOBAL_SEARCH_API_MAX_LIMIT]``). Termos com menos de 2
    caracteres retornam o payload vazio canônico (sem varredura). O payload de
    ``build_global_search_results`` já é JSON-safe (strings/ints/urls).

    A presença de ``?page=`` ativa o modo paginado (``types``/``page``/
    ``per_page``); sem ``page`` o comportamento do dropdown é intocado.

    Returns:
        Envelope ``{"ok": true, "data": {...}}`` com HTTP 200 (payload de busca
        ou payload vazio). ``api_login_required`` devolve 401 JSON quando não há
        sessão.
    """
    search_term = (request.args.get("q") or "").strip()
    selected_orgao_id, _ = sanitize_orgao_filter_for_current_user(
        request.args.get("orgao")
    )

    if "page" in request.args:
        selected_types = _parse_search_types(request.args.get("types"))
        page = _parse_positive_int(request.args.get("page"), default=1)
        per_page = _clamp_int(
            request.args.get("per_page"),
            default=GLOBAL_SEARCH_PAGE_SIZE,
            lo=1,
            hi=GLOBAL_SEARCH_PAGE_MAX_PER_PAGE,
        )
        if len(search_term) < GLOBAL_SEARCH_MIN_TERM_LENGTH:
            return ok(
                _empty_paginated_search_payload(search_term, selected_types, per_page)
            )
        return ok(
            build_paginated_global_search(
                search_term,
                g.user,
                selected_types=selected_types,
                page=page,
                per_page=per_page,
                selected_orgao_id=selected_orgao_id,
            )
        )

    # `limit=all`: a TELA de busca (página inteira) traz todos os registros; o
    # dropdown do topo continua mandando `limit=5`. limit_per_type=None => sem
    # LIMIT no SQL e has_more sempre False (não há "ver mais" na página cheia).
    unlimited = request.args.get("limit") == "all"
    limit_per_type = (
        None
        if unlimited
        else _normalize_global_search_limit(
            request.args.get("limit"),
            default_limit=GLOBAL_SEARCH_DEFAULT_LIMIT,
            max_limit=GLOBAL_SEARCH_API_MAX_LIMIT,
        )
    )

    if len(search_term) < GLOBAL_SEARCH_MIN_TERM_LENGTH:
        return ok(_empty_global_search_payload(search_term))

    payload = build_global_search_results(
        search_term,
        g.user,
        limit_per_type=limit_per_type,
        include_has_more=not unlimited,
        selected_orgao_id=selected_orgao_id,
    )
    return ok(payload)
