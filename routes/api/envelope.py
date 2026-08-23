"""Envelope canônico de respostas JSON da API da SPA.

Toda rota nova de dados consumida pelo frontend SvelteKit deve responder no
formato único abaixo, para que o cliente (``client.ts``) possa desempacotar de
forma uniforme:

    sucesso:  {"ok": true,  "data": <payload>, "meta": <opcional>}
    erro:     {"ok": false, "error": {"code": <str>, "message": <str>}}

Códigos de erro canônicos (``code``):
    "unauthenticated" | "forbidden" | "not_found" | "validation" | "server"
    Rotas podem usar códigos de domínio além desses quando o cliente precisa
    distinguir o caso (ex.: "csrf" em ``routes/api/errors.py``,
    "sugestoes_indisponiveis" em ``routes/api/collection_suggestions.py``).

NÃO ENVELOPAR (exceções deliberadas):
    - ``/webhook`` (``routes/calendars/webhook.py``): responde text/plain cru
      (``("", 204)`` / ``("token mismatch", 403)``); o Google espera corpo cru.
    - Downloads binários: CSV de projetos (``routes/projects/views.py``) e
      ``send_file`` de anexos — são octet-stream/CSV, não JSON.
    - ``GET /api/projetos/exportar`` (``routes/api/projects_export.py``): o
      sucesso é o próprio text/csv; só as falhas usam o envelope.
    - Endpoints legados (``routes/api/legacy.py``) mantidos por compatibilidade.

Exemplo de uso:
    >>> return ok({"id": 1, "name": "Ana"})
    >>> return ok(items, meta={"page": 1, "page_size": 20, "total": 42})
    >>> return fail("Projeto não encontrado", status=404, code="not_found")
"""

from __future__ import annotations

from typing import Any

from flask import Response, current_app, jsonify


def ok(
    data: Any = None,
    *,
    meta: dict[str, Any] | None = None,
    **extra: Any,
) -> Response:
    """Monta uma resposta de sucesso no envelope canônico.

    Args:
        data: Payload serializável a ser entregue em ``data`` (pode ser ``None``).
        meta: Metadados opcionais (ex.: paginação ``{page, page_size, total}``);
            omitido do corpo quando ``None``.
        **extra: Campos adicionais de topo no envelope (ex.: ``count=...``).
            Use com parcimônia; o contrato padrão é ``{ok, data, meta}``.

    Returns:
        ``flask.Response`` JSON com ``{"ok": true, "data": ..., [meta]}`` e
        HTTP 200.

    Exemplo:
        >>> return ok({"token": "abc"})
    """
    body: dict[str, Any] = {"ok": True, "data": data}
    if meta is not None:
        body["meta"] = meta
    if extra:
        body.update(extra)
    return jsonify(body)


def fail(
    message: str,
    status: int = 400,
    code: str = "validation",
) -> tuple[Response, int]:
    """Monta uma resposta de erro no envelope canônico.

    Args:
        message: Mensagem legível para o usuário/desenvolvedor.
        status: Código HTTP a retornar (default 400).
        code: Código de erro canônico
            ("unauthenticated" | "forbidden" | "not_found" | "validation" |
            "server").

    Returns:
        Tupla ``(flask.Response, status)`` com corpo
        ``{"ok": false, "error": {"code": ..., "message": ...}}``.

    Exemplo:
        >>> return fail("Sessão expirada", status=401, code="unauthenticated")
    """
    body: dict[str, Any] = {
        "ok": False,
        "error": {"code": code, "message": message},
    }
    return jsonify(body), status


# Mensagem única do 404 anti-enumeração (S5/F4-2b): id inexistente e recurso
# invisível (rank 0) devem responder byte a byte o mesmo corpo.
NOT_FOUND_MESSAGE = "Recurso não encontrado."


def fail_not_found() -> tuple[Response, int]:
    """404 canônico anti-enumeração — único corpo permitido para ``not_found``.

    Todo 404 de recurso sob ``/api/*`` (id inexistente, projeto fora do escopo,
    rank 0) deve sair por aqui para que "não existe" e "não é visível" sejam
    indistinguíveis (S5/F4-2b). Não aceita mensagem customizada por design.

    Returns:
        ``fail(NOT_FOUND_MESSAGE, status=404, code="not_found")`` — corpo
        ``{"ok": false, "error": {"code": "not_found", "message": "Recurso não encontrado."}}``.

    Exemplo:
        >>> if project is None or verdict == ACCESS_NOT_FOUND:
        ...     return fail_not_found()
    """
    return fail(NOT_FOUND_MESSAGE, status=404, code="not_found")


def fail_internal(
    exc: Exception,
    log_label: str,
    *,
    status: int = 500,
    code: str = "server",
    public_message: str = "Erro interno do servidor. Tente novamente.",
) -> tuple[Response, int]:
    """Loga a exceção real no servidor e devolve um erro genérico ao cliente.

    Evita vazar ``str(exc)`` (stack/SQL/schema) na resposta — mitiga exposição de
    informação (OWASP A09/A10). Use no ramo ``except Exception`` de mutações; para
    erros de validação de domínio (``except ValueError``) continue usando ``fail``
    com a mensagem curada.

    Args:
        exc: A exceção capturada (logada com traceback via ``logger.exception``).
        log_label: Rótulo curto da operação para o log (ex.: ``"criar projeto"``).
        status: HTTP a retornar (default 500).
        code: Código canônico do envelope (default ``"server"``).
        public_message: Mensagem genérica segura exibida ao usuário.

    Returns:
        ``fail(public_message, status, code)``.

    Exemplo:
        >>> except Exception as exc:
        ...     db.session.rollback()
        ...     return fail_internal(exc, "criar projeto")
    """
    current_app.logger.exception("Falha ao %s: %s", log_label, type(exc).__name__)
    return fail(public_message, status=status, code=code)
