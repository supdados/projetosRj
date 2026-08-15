"""Negociação de conteúdo e guards de autenticação para a API da SPA.

Centraliza a heurística "o cliente quer JSON?" e oferece decorators que, ao
contrário de ``routes/decorators.py`` (que faz ``flash`` + redirect 302 para o
Jinja), respondem com 401/403 JSON no envelope canônico — comportamento exigido
pela SPA, que precisa de erros estruturados, não de HTML de login.

IMPORTANTE: ``routes/decorators.py`` NÃO é alterado (o Jinja depende do
redirect). O ``_wants_json`` divergente de ``routes/calendars/events.py:24``
permanece como está; ``wants_json`` aqui é a versão única que unifica as
heurísticas:

    - Accept indica JSON (e não HTML); ou
    - cabeçalho ``X-Requested-With: XMLHttpRequest``; ou
    - o path começa com ``/api/``.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from flask import g, request

from .envelope import fail

F = TypeVar("F", bound=Callable[..., Any])


def wants_json() -> bool:
    """Decide se a resposta deve ser JSON (e não HTML).

    Unifica as três heurísticas ``_wants_json`` espalhadas pelo código:
    requisições para ``/api/*``, requisições XHR (``X-Requested-With``) e
    requisições cujo ``Accept`` prefere JSON a HTML.

    Returns:
        ``True`` quando o cliente espera JSON; ``False`` caso contrário.

    Exemplo:
        >>> if wants_json():
        ...     return fail("erro", status=400)
    """
    if request.path.startswith("/api/"):
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    if request.is_json:
        return True
    accept = request.accept_mimetypes
    if not accept:
        return False
    return (
        accept.best == "application/json"
        or accept["application/json"] > accept["text/html"]
    )


def api_login_required(view: F) -> F:
    """Exige sessão autenticada, respondendo 401 JSON quando ausente.

    Diferente de ``routes.decorators.login_required`` (redirect 302 ao login),
    devolve o envelope ``{"ok": false, "error": {"code": "unauthenticated"}}``
    com HTTP 401, adequado para o cliente da SPA.

    Args:
        view: A view function a proteger.

    Returns:
        A view envolvida.
    """

    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if not getattr(g, "user", None):
            return fail(
                "Autenticação necessária.",
                status=401,
                code="unauthenticated",
            )
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


def api_admin_required(view: F) -> F:
    """Exige usuário administrador, respondendo 401/403 JSON caso contrário.

    Devolve 401 ``unauthenticated`` quando não há sessão e 403 ``forbidden``
    quando o usuário autenticado não é admin. Não altera
    ``routes.decorators.admin_required`` (usado pelo Jinja).

    Args:
        view: A view function a proteger.

    Returns:
        A view envolvida.
    """

    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        user = getattr(g, "user", None)
        if not user:
            return fail(
                "Autenticação necessária.",
                status=401,
                code="unauthenticated",
            )
        if not getattr(user, "is_admin", False):
            return fail(
                "Acesso restrito a administradores.",
                status=403,
                code="forbidden",
            )
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]
