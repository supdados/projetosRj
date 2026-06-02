"""Endpoints de sessão da API consumida pela SPA SvelteKit.

Expõe os dados do usuário autenticado (``GET /api/me``) e o token CSRF a ser
re-buscado quando a sessão é longa e o token rotaciona (``GET /api/csrf-token``).
Ambos respondem no envelope canônico (``routes/api/envelope.py``) e usam o guard
``api_login_required`` (401 JSON quando não autenticado), nunca o redirect 302 do
Jinja.

As funções são anexadas ao ``main_bp`` ÚNICO (``routes/blueprint.py``); NÃO
criamos blueprint novo, para preservar os ``url_for("main.xxx")`` existentes.
"""

from __future__ import annotations

from flask import Response, g
from flask_wtf.csrf import generate_csrf

from ..blueprint import main_bp
from .envelope import ok
from .negotiation import api_login_required
from .serializers import serialize_user


@main_bp.route("/api/me", methods=["GET"])
@api_login_required
def api_me() -> Response:
    """Retorna o usuário autenticado para o boot do app shell da SPA.

    A store de auth (``frontend``) carrega este endpoint no boot do layout
    autenticado. Inclui apenas dados seguros (ver ``serialize_user``); NUNCA
    expõe ``password_hash`` nem tokens OAuth.

    Returns:
        Envelope ``{"ok": true, "data": {id, name, username, is_admin,
        orgaos[], auth_provider}}`` com HTTP 200; ``api_login_required``
        devolve 401 JSON quando não há sessão.
    """
    return ok(serialize_user(g.user))


@main_bp.route("/api/csrf-token", methods=["GET"])
@api_login_required
def api_csrf_token() -> Response:
    """Fornece um token CSRF para o cliente re-buscar em falha/rotação.

    A fonte primária do token é a ``<meta name="csrf-token">`` injetada no index
    via Jinja; este endpoint serve para o ``client.ts`` re-obter o token quando
    a sessão longa o rotaciona (e o ``X-CSRFToken`` passa a divergir).

    Returns:
        Envelope ``{"ok": true, "data": {"token": <str>}}`` com HTTP 200.
    """
    return ok({"token": generate_csrf()})
