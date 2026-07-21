"""Errorhandlers que garantem JSON no envelope canônico para as rotas ``/api/*``.

PROBLEMA (B1): uma exceção não tratada sob ``/api`` virava uma página HTML de
erro 500 do Flask; o cliente SPA (``client.ts``), que sempre faz ``response.json()``,
quebrava com ``Unrecognized token '<'`` ao tentar desempacotar HTML como JSON.

SOLUÇÃO: handlers globais (``@main_bp.app_errorhandler``) para ``Exception`` (500),
``NotFound`` (404) e ``MethodNotAllowed`` (405) que respondem o envelope
``fail(...)`` SOMENTE quando ``request.path`` começa com ``"/api/"``. Para qualquer
outro path (telas Jinja vivas), o handler re-ergue/retorna o erro original para
que o Flask renderize a página de erro HTML padrão — preservando as telas Jinja.

CUIDADOS:
    - NÃO engole os ``fail(...)`` já estruturados: ``fail`` retorna uma tupla
      ``(Response, status)`` (não levanta exceção), então os 4xx canônicos das
      views nunca passam por estes handlers.
    - NÃO conflita com o ``RequestEntityTooLarge`` (413) já tratado em
      ``routes/api/task_attachments.py``: aquele é um handler específico e tem
      precedência sobre o handler genérico de ``Exception`` registrado aqui.
    - ``HTTPException`` levantadas explicitamente nas views ``/api/*`` (ex.:
      ``abort(404)``) caem nos handlers de status apropriados.

Registrado via ``from . import errors`` em ``routes/api/__init__.py``.
"""

from __future__ import annotations

from flask import Response, request
from werkzeug.exceptions import HTTPException, MethodNotAllowed, NotFound

from ..blueprint import main_bp
from .envelope import fail


def _is_api_request() -> bool:
    """Indica se a requisição atual mira o namespace JSON da SPA (``/api/``).

    Returns:
        ``True`` quando ``request.path`` começa com ``"/api/"`` — único caso em
        que devemos responder no envelope canônico em vez de HTML.

    Exemplo:
        >>> # dentro de um request a "/api/projetos": _is_api_request() -> True
        >>> # dentro de um request a "/dashboard":    _is_api_request() -> False
    """
    return request.path.startswith("/api/")


@main_bp.app_errorhandler(NotFound)
def api_not_found(error: NotFound) -> Response | tuple[Response, int] | NotFound:
    """Converte 404 sob ``/api/*`` no envelope ``fail`` (``not_found``).

    Fora de ``/api/*`` re-ergue o ``NotFound`` original para que o Flask renderize
    a página 404 HTML legada das telas Jinja.

    Args:
        error: O ``NotFound`` (404) levantado pelo Werkzeug/roteador.

    Returns:
        ``fail(..., 404, "not_found")`` para paths ``/api/*``; senão o ``error``
        original (HTML padrão do Flask).
    """
    if not _is_api_request():
        return error
    return fail("Recurso não encontrado.", status=404, code="not_found")


@main_bp.app_errorhandler(MethodNotAllowed)
def api_method_not_allowed(
    error: MethodNotAllowed,
) -> Response | tuple[Response, int] | MethodNotAllowed:
    """Converte 405 sob ``/api/*`` no envelope ``fail`` (``validation``).

    O método HTTP não é aceito pela rota; para a SPA isso é um erro de uso do
    cliente (``validation``). Fora de ``/api/*`` re-ergue o erro original (HTML).

    Args:
        error: O ``MethodNotAllowed`` (405) levantado pelo Werkzeug/roteador.

    Returns:
        ``fail(..., 405, "validation")`` para paths ``/api/*``; senão o ``error``
        original (HTML padrão do Flask).
    """
    if not _is_api_request():
        return error
    return fail(
        "Método não permitido para este recurso.", status=405, code="validation"
    )


@main_bp.app_errorhandler(Exception)
def api_internal_error(
    error: Exception,
) -> Response | tuple[Response, int] | Exception:
    """Converte exceções NÃO TRATADAS sob ``/api/*`` no envelope ``fail`` (500).

    Este é o handler genérico de fallback: qualquer exceção que escape de uma view
    ``/api/*`` (e que não seja ``RequestEntityTooLarge``/``NotFound``/
    ``MethodNotAllowed``, tratadas por handlers específicos com precedência) vira um
    500 JSON estruturado em vez do HTML 500 que quebrava o cliente (B1).

    Fora de ``/api/*`` re-ergue a exceção original para preservar o comportamento
    padrão do Flask (página 500 HTML / propagação em ``TESTING``/debug).

    Args:
        error: A exceção não tratada que escapou da view.

    Returns:
        ``fail(..., 500, "server")`` para paths ``/api/*``; senão re-ergue ``error``.

    Raises:
        Exception: re-ergue a exceção original para paths fora de ``/api/*``.
    """
    # HTTPExceptions têm status/semântica próprios (ex.: CSRFError 400, abort(403))
    # e tratamento padrão do Flask — NÃO devem virar 500 aqui (isso quebrava o
    # CSRF 400 das rotas Jinja legadas). Deixa o Flask renderizar a resposta normal.
    if isinstance(error, HTTPException):
        return error
    if not _is_api_request():
        raise error
    return fail("Erro interno do servidor.", status=500, code="server")
