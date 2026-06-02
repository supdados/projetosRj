"""Serve o index do bundle SvelteKit (SPA do piloto) via Jinja + csp_nonce.

A SPA do piloto e montada sob ``/spa`` (raiz da SPA) e atende os paths migrados
do piloto — a raiz da SPA e ``/spa/dashboard`` — devolvendo SEMPRE o mesmo index
(client-side routing). O index e renderizado por ``render_template`` para injetar
o ``csp_nonce`` (CSP ``script-src 'self' 'nonce-{nonce}'``, app.py:55) e a
``<meta name="csrf-token">``; NUNCA e servido como arquivo estatico puro.

PATHS EXCLUIDOS (NAO interceptados): por desenho, esta rota so casa o prefixo
``/spa``; portanto ``/api/*``, ``/webhook``, ``/calendar/oauth/*``, ``/auth/*``,
``/login*``, ``/logout``, ``/favicon.ico``, ``/setup_db`` e ``/static/*`` (onde
vive o bundle real, ``static/spa/``) permanecem nas suas rotas originais. Um guard
interno reforca a exclusao para qualquer subpath reservado.

A funcao e anexada ao ``main_bp`` UNICO (``routes/blueprint.py``); NAO criamos
blueprint novo, para preservar os ``url_for("main.xxx")`` existentes.
"""

from __future__ import annotations

import os
import re

from flask import abort, g, render_template

from .blueprint import main_bp

# Caminho do index buildado pelo frontend (adapter-static -> static/spa/).
_BUNDLE_INDEX_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static",
    "spa",
    "index.html",
)

# Prefixos que NUNCA devem ser servidos como SPA, mesmo que cheguem como subpath
# do catch-all. Defesa em profundidade: o mount ja e ``/spa``, mas reforcamos.
_RESERVED_SUBPATH_PREFIXES = (
    "api/",
    "webhook",
    "calendar/oauth",
    "auth/",
    "login",
    "logout",
    "favicon.ico",
    "setup_db",
    "static/",
)

_HEAD_ASSETS_RE = re.compile(
    r'<link\b[^>]*\brel="(?:modulepreload|stylesheet)"[^>]*>',
    re.IGNORECASE,
)
_BODY_RE = re.compile(r"<body[^>]*>(?P<body>.*)</body>", re.IGNORECASE | re.DOTALL)


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


def _is_reserved(subpath: str) -> bool:
    """Indica se o subpath pertence a uma area reservada (nao-SPA)."""
    normalized = subpath.lstrip("/")
    return any(normalized.startswith(prefix) for prefix in _RESERVED_SUBPATH_PREFIXES)


def _render_spa() -> str:
    """Renderiza o index da SPA injetando csp_nonce e a meta csrf-token."""
    nonce = getattr(g, "csp_nonce", "")
    head_assets, body = _read_bundle_fragments(nonce)
    return render_template(
        "spa/index.html",
        spa_head_assets=head_assets,
        spa_body=body,
    )


@main_bp.route("/spa", methods=["GET"])
@main_bp.route("/spa/<path:subpath>", methods=["GET"])
def spa_index(subpath: str = "") -> str:
    """Serve o index da SPA do piloto para a raiz e subpaths client-side.

    Devolve sempre o mesmo index (roteamento e client-side na SPA), permitindo
    que ``/spa`` (raiz) e ``/spa/dashboard`` rendam o Dashboard SvelteKit. Areas
    reservadas (``/spa/api/...`` etc., improvaveis mas possiveis via subpath) sao
    rejeitadas com 404 por seguranca.

    Args:
        subpath: O caminho client-side apos ``/spa`` (vazio para a raiz).

    Returns:
        O HTML do index renderizado via Jinja (com ``csp_nonce`` e csrf-token).
    """
    if subpath and _is_reserved(subpath):
        abort(404)
    return _render_spa()
