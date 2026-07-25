"""Serve a SPA SvelteKit (CSR) nos PATHS NATIVOS, com deep-link e F5 robustos.

ABORDAGEM
---------
1) ``frontend/svelte.config.js`` passa a usar ``paths.base = ''`` (RAIZ). Assim o
   roteador client-side casa com os PATHS NATIVOS das telas migradas
   (``/dashboard``, ``/projetos``, ``/projetos/pendentes``, ``/projetos/<id>``,
   ``/tarefas``, ``/admin/*``, ``/busca``, ``/calendarios``). Com ``base=''`` o
   bootstrap referencia os assets em ``/_app/...`` (raiz).
2) Os ASSETS continuam fisicamente em ``static/spa/_app/`` (adapter-static). Como
   o cliente os pede em ``/_app/...`` (raiz), esta rota serve ``/_app/<path>`` a
   partir de ``static/spa/_app/`` (arquivos imutaveis e versionados por hash).
3) O INDEX e servido via ``_render_spa()`` (Jinja, com ``%CSP_NONCE%``
   substituido em runtime — NUNCA estatico cru, senao a CSP bloqueia o bootstrap)
   nos paths nativos das telas migradas QUE NAO POSSUEM rota Jinja viva de mesma
   URL: ``/projetos``, ``/projetos/pendentes``, ``/projetos/<id>``,
   ``/projetos/<id>/historico``, ``/admin``, ``/admin/usuarios``,
   ``/admin/usuarios/novo``, ``/admin/usuarios/<id>`` e ``/admin/orgaos``
   (read-only SIORG). Sao atendidos por um catch-all dinamico
   ``/<path:spa_path>`` (rank MENOR que rotas estaticas — Werkzeug prioriza rotas
   estaticas — entao so casa o que nenhuma rota Jinja atendeu), restrito ao
   matcher de paths migrados; qualquer outro path -> 404 (preserva o comportamento
   atual). Deep-link e F5 nesses paths resolvem a rota client-side correta.

ESTADO ATUAL
------------
A migração Jinja->SPA está COMPLETA: nenhuma tela de aplicação renderiza mais
Jinja — só o fluxo de auth Gov.br (``templates/auth/*``, ``base.html`` no login/
troca de senha) permanece (congelado). Os deep-links legados ``/projects`` e
``/project/<id>`` viraram redirect 302 -> ``/projetos`` e ``/projetos/<id>``
(KEEP-ENDPOINT: ``target_url`` persistido em notificacoes, links da busca e
redirects de produção apontam pra ca). ``/dashboard``, ``/tarefas`` e
``/calendarios`` seguem como KEEP-ENDPOINT servindo ``_render_spa()``; ``/busca``,
``/admin/*`` sao servidos pelo catch-all. Cortadas na migração:
``/etapa/<id>/edit``, ``/project/<id>/history``, ``/admin/users*``,
``/project/<id>/edit``, ``/projetos_pendentes`` e o cluster ``/projects``
(list/detail/add/edit/delete/concluir/import/stage-tasks) — tudo 100% SPA via
``/api/*``.

EXCLUSOES (nunca SPA): ``/api/*``, ``/webhook``, ``/calendar/oauth/*``,
``/auth/*``, ``/login*``, ``/logout``, ``/static/*``, ``/favicon.ico``,
``/setup_db``, ``/_app/*`` e o proprio ``/spa`` legado.

A funcao e anexada ao ``main_bp`` UNICO; NAO criamos blueprint novo, para
preservar os ``url_for("main.xxx")`` existentes.
"""

from __future__ import annotations

import os
import re
import secrets

from flask import abort, g, render_template, send_from_directory

from .blueprint import main_bp

# Diretorio do bundle buildado (adapter-static -> static/spa/).
_BUNDLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static",
    "spa",
)
_BUNDLE_INDEX_PATH = os.path.join(_BUNDLE_DIR, "index.html")
# Assets imutaveis do SvelteKit; com base='' o cliente os pede em /_app/...
_BUNDLE_APP_DIR = os.path.join(_BUNDLE_DIR, "_app")

# Prefixos que NUNCA sao servidos como SPA, mesmo via catch-all. Defesa em
# profundidade alem das rotas estaticas dedicadas (api/auth/login/...).
_RESERVED_SUBPATH_PREFIXES = (
    "api/",
    "api",
    "webhook",
    "calendar/oauth",
    "auth/",
    "login",
    "logout",
    "favicon.ico",
    "setup_db",
    "static/",
    "static",
    "_app/",
    "_app",
    "spa/",
    "spa",
)

# Conjunto exato (sem barra inicial) e padroes dinamicos. SO inclui paths
# migrados que NAO possuem rota Jinja viva de mesma URL (os colidentes — ver
# "ESTADO ATUAL" no docstring — continuam no Jinja e nao entram aqui).
# Atualizar quando uma tela for migrada para um path nativo livre OU quando uma
# rota Jinja colidente for cortada (entao seu path entra aqui e o catch-all passa
# a servi-lo, pois sem a rota estatica o dinamico finalmente casa).
_MIGRATED_EXACT_PATHS = frozenset(
    {
        "projetos",
        "projetos/pendentes",
        "admin",
        "admin/usuarios",
        "admin/usuarios/novo",
        # Telas do Grupo B cujas rotas Jinja canonicas foram cortadas: agora o
        # catch-all serve a SPA nesses paths nativos (deep-link/F5).
        # Órgãos read-only (SIORG): subpáginas novo/<id>/tipos foram cortadas.
        "admin/orgaos",
        "admin/templates",
        "busca",
        # Cut-over dashboard/tarefas/calendarios: as rotas Flask ESTATICAS
        # dessas URLs permanecem registradas como KEEP-ENDPOINT servindo
        # _render_spa() (routes/dashboard.py::dashboard,
        # routes/tasks/views.py::list_tasks,
        # routes/calendars/views.py::calendars_hub) e tem prioridade no
        # Werkzeug sobre este catch-all — as entradas abaixo sao defesa em
        # profundidade/documentacao do estado migrado, nao o caminho ativo.
        # NAO adicionar "tarefas/arquivadas", padrao dinamico "tarefas/\d+"
        # nem "projeto/\d+/tarefas": a SPA NAO tem rota client-side para esses
        # paths (servir a shell neles cai no 404 do SvelteKit). Os endpoints
        # Flask correspondentes (list_tasks_archived, task_detail,
        # project_tasks) sao redirect resolvers 302 VIVOS (URLs persistidas em
        # notificacoes no banco) que apontam para /tarefas com query params.
        "dashboard",
        "tarefas",
        "calendarios",
    }
)
# Segmentos dinamicos das telas migradas (``<id>`` numerico). re.fullmatch.
_MIGRATED_DYNAMIC_PATTERNS = (
    re.compile(r"projetos/\d+"),
    re.compile(r"projetos/\d+/historico"),
    re.compile(r"admin/usuarios/\d+"),
)

_HEAD_ASSETS_RE = re.compile(
    r'<link\b[^>]*\brel="(?:modulepreload|stylesheet)"[^>]*>',
    re.IGNORECASE,
)
_BODY_RE = re.compile(r"<body[^>]*>(?P<body>.*)</body>", re.IGNORECASE | re.DOTALL)


def _is_migrated_spa_path(normalized: str) -> bool:
    """Indica se ``normalized`` (sem barra inicial) e um path de tela migrada."""
    if normalized in _MIGRATED_EXACT_PATHS:
        return True
    return any(p.fullmatch(normalized) for p in _MIGRATED_DYNAMIC_PATTERNS)


def _is_reserved(subpath: str) -> bool:
    """Indica se o subpath pertence a uma area reservada (nao-SPA)."""
    normalized = subpath.lstrip("/")
    return any(normalized.startswith(prefix) for prefix in _RESERVED_SUBPATH_PREFIXES)


def _read_bundle_fragments(nonce: str) -> tuple[str, str]:
    """Le o index buildado e extrai (head_assets, body) com o nonce injetado.

    Os nomes de arquivo do bundle sao hasheados a cada build, entao as tags de
    asset (modulepreload/stylesheet) e o script de bootstrap do SvelteKit sao
    lidos do proprio bundle em vez de fixados no template Jinja. O placeholder
    ``%CSP_NONCE%`` deixado pelo frontend e substituido pelo ``nonce`` vivo desta
    requisicao.

    Args:
        nonce: O ``csp_nonce`` desta requisicao (de ``g.csp_nonce``).

    Returns:
        Tupla ``(head_assets_html, body_html)`` pronta para ``| safe`` no Jinja.

    Raises:
        Aborta 404 quando o bundle ainda nao foi buildado (sem ``static/spa/``).
    """
    if not os.path.exists(_BUNDLE_INDEX_PATH):
        # O bundle real vem do frontend (npm run build). Sem ele, nao ha SPA.
        abort(404)

    with open(_BUNDLE_INDEX_PATH, encoding="utf-8") as bundle_file:
        raw = bundle_file.read()

    raw = raw.replace("%CSP_NONCE%", nonce)

    head_assets = "\n".join(_HEAD_ASSETS_RE.findall(raw))
    body_match = _BODY_RE.search(raw)
    body = body_match.group("body").strip() if body_match else ""
    return head_assets, body


def _ensure_csp_nonce() -> str:
    """Garante um ``g.csp_nonce`` vivo e o devolve.

    O override de paths migrados roda como ``before_app_request`` ANTES de
    ``assign_csp_nonce`` (app.py) na ordem de registro; ao curto-circuitar a
    request, ``assign_csp_nonce`` nem chega a rodar. Geramos o nonce aqui e o
    gravamos em ``g`` para que o MESMO valor apareca no body e no header CSP
    (``set_security_headers`` em ``after_request`` le ``g.csp_nonce``).
    """
    nonce = getattr(g, "csp_nonce", "") or ""
    if not nonce:
        nonce = secrets.token_urlsafe(16)
        g.csp_nonce = nonce
    return nonce


def _render_spa() -> str:
    """Renderiza o index da SPA injetando csp_nonce e a meta csrf-token."""
    nonce = _ensure_csp_nonce()
    head_assets, body = _read_bundle_fragments(nonce)
    return render_template(
        "spa/index.html",
        spa_head_assets=head_assets,
        spa_body=body,
    )


@main_bp.route("/_app/<path:asset_path>", methods=["GET"])
def spa_app_asset(asset_path: str):
    """Serve os assets imutaveis do SvelteKit (base='' -> /_app/...).

    O bundle grava os assets em ``static/spa/_app/``; com ``paths.base=''`` o
    bootstrap os referencia em ``/_app/...`` (raiz). Esta rota faz a ponte. Os
    arquivos sao versionados por hash (immutable), entao sao seguros para
    cache longo.

    Args:
        asset_path: Caminho do asset relativo a ``static/spa/_app/``.

    Returns:
        O arquivo do bundle (404 se inexistente).
    """
    return send_from_directory(_BUNDLE_APP_DIR, asset_path)


@main_bp.route("/spa", methods=["GET"])
@main_bp.route("/spa/<path:subpath>", methods=["GET"])
def spa_index(subpath: str = "") -> str:
    """Compat: serve o index da SPA na raiz legada ``/spa`` e subpaths.

    Mantida para nao quebrar links antigos para ``/spa``; o roteamento atual
    usa os paths nativos. Areas reservadas sao rejeitadas com 404.

    Args:
        subpath: O caminho client-side apos ``/spa`` (vazio para a raiz).

    Returns:
        O HTML do index renderizado via Jinja (com ``csp_nonce`` e csrf-token).
    """
    if subpath and _is_reserved(subpath):
        abort(404)
    return _render_spa()


@main_bp.route("/<path:spa_path>", methods=["GET"])
def spa_native_path(spa_path: str) -> str:
    """Catch-all dinamico: serve a SPA nos paths nativos migrados SEM rota Jinja.

    Tem rank menor que as rotas estaticas (Werkzeug prioriza rotas estaticas),
    entao so casa o que nenhuma rota Jinja existente atendeu: ``/projetos*``,
    ``/admin``, ``/admin/usuarios*``, ``/admin/orgaos``,
    ``/admin/templates`` e ``/busca``. ``/dashboard``, ``/tarefas`` e
    ``/calendarios`` tambem constam no matcher, mas na
    pratica sao atendidos pelas rotas estaticas KEEP-ENDPOINT que ja devolvem
    ``_render_spa()`` (defesa em profundidade). Paths NAO migrados (ou
    reservados) -> 404, preservando o comportamento atual (telas Jinja vivas
    continuam nas suas rotas; URLs desconhecidas seguem 404).

    Args:
        spa_path: Caminho apos a raiz (sem barra inicial).

    Returns:
        O index da SPA renderizado via Jinja.
    """
    if _is_reserved(spa_path) or not _is_migrated_spa_path(spa_path):
        abort(404)
    return _render_spa()
